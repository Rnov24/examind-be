"""Student session history — GET /student/sessions.

A student must see their own exam sessions, newest first, with the
honest status (including a disqualified / aborted session), and must
never see another student's sessions. Teachers and admins are not
students, so require_student must 403 them.

Fixture style mirrors tests/test_student_exam_security.py: in-memory
SQLite, real JWTs, ONLY get_db overridden.

Run: .venv/bin/python -m pytest tests/test_student_sessions.py -v
"""
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.core.database import Base, get_db
from app.core.security import create_access_token
from app.models.academic import Class, ClassMember
from app.models.exam import Exam
from app.models.session import ExamSession
from app.models.tenant import Tenant
from app.models.user import User


def _user(uid, identifier, email, role, tenant_id, name):
    return User(
        id=uid,
        identifier=identifier,
        email=email,
        password_hash="fakehash",
        full_name=name,
        role=role,
        tenant_id=tenant_id,
        is_active=True,
        is_email_verified=True,
    )


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()

    now = datetime.now()
    db.add_all([
        Tenant(id=1, name="Sekolah A", code="SCH-A"),
        _user(4, "TCH-A", "guru-a@sch-a.id", "teacher", 1, "Guru A"),
        _user(6, "SIS-A1", "siswa-a1@sch-a.id", "student", 1, "Siswa A1"),
        _user(7, "SIS-A2", "siswa-a2@sch-a.id", "student", 1, "Siswa A2"),
        _user(9, "ADM-A", "admin-a@sch-a.id", "admin", 1, "Admin A"),
        # Student 12 has no session at all.
        _user(12, "SIS-A3", "siswa-a3@sch-a.id", "student", 1, "Siswa A3"),
    ])
    db.add_all([
        Class(id=1, name="Kelas A", grade_level="10", academic_year="2025/2026", created_by=4),
        ClassMember(class_id=1, user_id=6, role="student"),
        ClassMember(class_id=1, user_id=7, role="student"),
        ClassMember(class_id=1, user_id=12, role="student"),
        # Exam 3 exists but NEITHER student has a session on it —
        # never-started exams must not appear in the history.
        Exam(id=1, teacher_id=4, class_id=1, title="Matematika Bab 1",
             duration_minutes=60, start_time=now - timedelta(days=3),
             end_time=now - timedelta(days=2), status="completed",
             exam_mode="live"),
        Exam(id=2, teacher_id=4, class_id=1, title="Fisika Bab 2",
             duration_minutes=60, start_time=now - timedelta(days=2),
             end_time=now - timedelta(days=1), status="completed",
             exam_mode="live"),
        Exam(id=3, teacher_id=4, class_id=1, title="Kimia Bab 3",
             duration_minutes=60, start_time=now - timedelta(hours=1),
             end_time=now + timedelta(hours=2), status="published",
             exam_mode="live"),
        Exam(id=4, teacher_id=4, class_id=1, title="Biologi Bab 4",
             duration_minutes=60, start_time=now - timedelta(hours=1),
             end_time=now + timedelta(hours=2), status="published",
             exam_mode="live"),
    ])
    db.add_all([
        # Student 6, OLDEST first in insertion order: graded 3 days ago.
        ExamSession(id=100, exam_id=1, student_id=6,
                    start_time=now - timedelta(days=3),
                    begun_at=now - timedelta(days=3),
                    submit_time=now - timedelta(days=3) + timedelta(minutes=40),
                    status="graded", total_score=40.0, integrity_score=95,
                    pairing_token="tok-100"),
        # Student 6: aborted (disqualified) 2 days ago — must appear,
        # with its honest status and the zeroed score.
        ExamSession(id=101, exam_id=2, student_id=6,
                    start_time=now - timedelta(days=2),
                    begun_at=now - timedelta(days=2),
                    submit_time=now - timedelta(days=2) + timedelta(minutes=5),
                    status="aborted", total_score=0.0, integrity_score=0,
                    pairing_token="tok-101"),
        # Student 6: grading_in_progress, submitted 10 minutes ago —
        # the NEWEST of student 6's sessions.
        ExamSession(id=102, exam_id=4, student_id=6,
                    start_time=now - timedelta(minutes=30),
                    begun_at=now - timedelta(minutes=30),
                    submit_time=now - timedelta(minutes=10),
                    status="grading_in_progress", total_score=10.0,
                    integrity_score=100, pairing_token="tok-102"),
        # Student 7: graded session on the SAME exam 1 — must never
        # appear in student 6's history (and vice versa).
        ExamSession(id=103, exam_id=1, student_id=7,
                    start_time=now - timedelta(days=3),
                    begun_at=now - timedelta(days=3),
                    submit_time=now - timedelta(days=3) + timedelta(minutes=50),
                    status="graded", total_score=90.0, integrity_score=100,
                    pairing_token="tok-103"),
        # Student 7: in_progress session, never submitted — submit_time
        # is NULL, so it sorts by start_time and carries submitted_at None.
        ExamSession(id=104, exam_id=4, student_id=7,
                    start_time=now - timedelta(minutes=20),
                    begun_at=now - timedelta(minutes=20),
                    submit_time=None,
                    status="in_progress", total_score=0.0, integrity_score=100,
                    pairing_token="tok-104"),
    ])
    db.commit()

    app.dependency_overrides[get_db] = lambda: db
    try:
        yield db
    finally:
        app.dependency_overrides.pop(get_db, None)
        db.close()


def _auth(user_id: int):
    return {"Authorization": f"Bearer {create_access_token(data={'sub': str(user_id)})}"}


@pytest.fixture
def client(db_session):
    return TestClient(app, raise_server_exceptions=False)


def test_student_sees_own_sessions_newest_first(client):
    resp = client.get("/api/v1/student/sessions", headers=_auth(6))
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    rows = body["data"]
    # Exactly student 6's three sessions, newest (by submitted_at) first.
    assert [r["session_id"] for r in rows] == [102, 101, 100]
    newest, aborted, oldest = rows
    assert newest["status"] == "grading_in_progress"
    assert newest["exam_id"] == 4
    assert newest["exam_title"] == "Biologi Bab 4"
    assert newest["class_name"] == "Kelas A"
    assert newest["total_score"] == 10.0
    assert newest["integrity_score"] == 100
    assert newest["submitted_at"] is not None
    assert newest["begun_at"] is not None
    # The disqualified session shows up with its honest status.
    assert aborted["status"] == "aborted"
    assert aborted["exam_title"] == "Fisika Bab 2"
    assert aborted["total_score"] == 0.0
    assert aborted["integrity_score"] == 0
    # The oldest graded session keeps its real score.
    assert oldest["status"] == "graded"
    assert oldest["exam_title"] == "Matematika Bab 1"
    assert oldest["total_score"] == 40.0
    assert oldest["integrity_score"] == 95
    # Exact field set — no extra data (and no other student's data).
    assert set(newest.keys()) == {
        "session_id", "exam_id", "exam_title", "class_name", "status",
        "total_score", "integrity_score", "submitted_at", "begun_at",
    }


def test_other_student_session_is_absent(client):
    # Student 7's graded session 103 (score 90.0, same exam 1) must not
    # appear anywhere in student 6's history — not by id, not by score.
    resp = client.get("/api/v1/student/sessions", headers=_auth(6))
    rows = resp.json()["data"]
    assert all(r["session_id"] != 103 for r in rows)
    assert all(r["total_score"] != 90.0 for r in rows)
    # And the mirror: student 7 sees only their own two sessions.
    resp = client.get("/api/v1/student/sessions", headers=_auth(7))
    rows = resp.json()["data"]
    assert [r["session_id"] for r in rows] == [104, 103]
    assert rows[0]["status"] == "in_progress"
    assert rows[0]["submitted_at"] is None
    assert rows[1]["total_score"] == 90.0
    # Never-started exam 3 has no session row for either student.
    assert all(r["exam_id"] != 3 for r in rows)


def test_student_with_no_sessions_gets_empty_list(client):
    resp = client.get("/api/v1/student/sessions", headers=_auth(12))
    assert resp.status_code == 200
    assert resp.json()["data"] == []


def test_teacher_and_admin_get_403(client):
    for user_id in (4, 9):
        resp = client.get("/api/v1/student/sessions", headers=_auth(user_id))
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "FORBIDDEN_ROLE"


def test_unauthenticated_gets_401(client):
    resp = client.get("/api/v1/student/sessions")
    assert resp.status_code == 401
