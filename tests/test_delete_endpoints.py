"""Delete-endpoint tests — Blocker 6 (exam delete 405, class delete 500).

- DELETE /exams/{id}: 200 when the exam has no sessions/answers, 409 when
  sessions or answers reference it (history is never cascade-deleted),
  404 cross-tenant (never confirm another tenant's resource exists).
- DELETE /classes/{id}: 409 (no SQL text in the body) when the class still
  has exams or members, 200 only when truly empty, 404 cross-tenant.

Same harness as test_tenant_isolation.py: in-memory SQLite, REAL JWTs,
only get_db overridden, so the full auth + scoping path is exercised.

Run: .venv/bin/python -m pytest tests/test_delete_endpoints.py -v
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
from app.models.exam import Exam, ExamQuestion
from app.models.question import Question, QuestionBank
from app.models.session import ExamSession, StudentAnswer
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

    now = datetime.utcnow()
    db.add_all([
        Tenant(id=1, name="Sekolah A", code="SCH-A"),
        Tenant(id=2, name="Sekolah B", code="SCH-B"),
        _user(1, "SUPER", "super@examind.id", "superadmin", None, "Super Admin"),
        _user(2, "ADM-A", "admin-a@sch-a.id", "admin", 1, "Admin A"),
        _user(3, "ADM-B", "admin-b@sch-b.id", "admin", 2, "Admin B"),
        _user(4, "TCH-A", "guru-a@sch-a.id", "teacher", 1, "Guru A"),
        _user(5, "TCH-B", "guru-b@sch-b.id", "teacher", 2, "Guru B"),
        _user(6, "SIS-A1", "siswa-a1@sch-a.id", "student", 1, "Siswa A1"),
        _user(7, "SIS-A2", "siswa-a2@sch-a.id", "student", 1, "Siswa A2"),
        _user(8, "SIS-B", "siswa-b@sch-b.id", "student", 2, "Siswa B"),
    ])
    db.add_all([
        # Class 1: teacher A, members + an exam that HAS a session.
        Class(id=1, name="Kelas A", grade_level="10", academic_year="2025/2026", created_by=4),
        # Class 2: teacher B (other tenant), one exam, no sessions.
        Class(id=2, name="Kelas B", grade_level="10", academic_year="2025/2026", created_by=5),
        # Class 3: teacher A, NO members, two session-less exams.
        Class(id=3, name="Kelas A Kosong", grade_level="10", academic_year="2025/2026", created_by=4),
        # Class 4: teacher A, NO members, NO exams — truly empty.
        Class(id=4, name="Kelas A Hampa", grade_level="10", academic_year="2025/2026", created_by=4),
        # Class 5: teacher A, members but NO exams.
        Class(id=5, name="Kelas A Anggota", grade_level="10", academic_year="2025/2026", created_by=4),
        ClassMember(class_id=1, user_id=6, role="student"),
        ClassMember(class_id=1, user_id=7, role="student"),
        ClassMember(class_id=5, user_id=6, role="student"),
        QuestionBank(id=1, teacher_id=4, title="Bank A", subject="Matematika"),
        Question(id=1, bank_id=1, question_type="multiple_choice", prompt="Soal A",
                 options_json=[{"id": "A", "text": "1"}, {"id": "B", "text": "2"}],
                 correct_answer="A"),
    ])
    db.add_all([
        # Exam 1: teacher A, class 1 — HAS a submitted session + answer.
        Exam(id=1, teacher_id=4, class_id=1, title="Ujian A", duration_minutes=60,
             start_time=now - timedelta(hours=1), end_time=now + timedelta(hours=2),
             status="published"),
        # Exam 2: teacher B, class 2 — other tenant, no sessions.
        Exam(id=2, teacher_id=5, class_id=2, title="Ujian B", duration_minutes=60,
             start_time=now - timedelta(hours=1), end_time=now + timedelta(hours=2),
             status="published"),
        # Exam 3: teacher A, class 3 — draft, no sessions (teacher delete target).
        Exam(id=3, teacher_id=4, class_id=3, title="Ujian A Draft", duration_minutes=60,
             start_time=now + timedelta(hours=1), end_time=now + timedelta(hours=2),
             status="draft"),
        # Exam 4: teacher A, class 3 — draft, no sessions (admin delete target).
        Exam(id=4, teacher_id=4, class_id=3, title="Ujian A Draft 2", duration_minutes=60,
             start_time=now + timedelta(hours=1), end_time=now + timedelta(hours=2),
             status="draft"),
        ExamQuestion(exam_id=1, question_id=1, order_index=1, allocated_points=10),
    ])
    db.add_all([
        ExamSession(id=1, exam_id=1, student_id=6, start_time=now - timedelta(minutes=10),
                    status="submitted", total_score=8.0, integrity_score=95),
        StudentAnswer(id=1, session_id=1, question_id=1, student_response="A",
                      is_correct=True, auto_score=10, final_score=10),
    ])
    db.commit()

    app.dependency_overrides[get_db] = lambda: db
    try:
        yield db
    finally:
        app.dependency_overrides.pop(get_db, None)
        db.close()


def _token(user_id: int) -> str:
    return create_access_token(data={"sub": str(user_id)})


def _auth(user_id: int):
    return {"Authorization": f"Bearer {_token(user_id)}"}


@pytest.fixture
def client(db_session):
    return TestClient(app, raise_server_exceptions=False)


# --- DELETE /exams/{id} -------------------------------------------------------

def test_delete_empty_exam_returns_200(client, db_session):
    resp = client.delete("/api/v1/exams/3", headers=_auth(4))  # Guru A, own draft
    assert resp.status_code == 200
    assert resp.json()["success"] is True
    assert resp.json()["data"]["deleted_id"] == 3
    assert db_session.query(Exam).filter(Exam.id == 3).first() is None


def test_admin_can_delete_own_tenant_exam_without_sessions(client, db_session):
    resp = client.delete("/api/v1/exams/4", headers=_auth(2))  # Admin A, teacher A's draft
    assert resp.status_code == 200
    assert db_session.query(Exam).filter(Exam.id == 4).first() is None


def test_delete_exam_with_sessions_returns_409(client, db_session):
    resp = client.delete("/api/v1/exams/1", headers=_auth(4))  # Guru A, has a session
    assert resp.status_code == 409
    assert resp.json()["success"] is False
    # History is never deleted under the exam: session + answer survive.
    assert db_session.query(ExamSession).filter(ExamSession.id == 1).first() is not None
    assert db_session.query(StudentAnswer).filter(StudentAnswer.id == 1).first() is not None
    assert db_session.query(Exam).filter(Exam.id == 1).first() is not None


def test_delete_exam_cross_tenant_returns_404(client, db_session):
    # Teacher A and Admin A must not even learn exam 2 (school B) exists.
    assert client.delete("/api/v1/exams/2", headers=_auth(4)).status_code == 404
    assert client.delete("/api/v1/exams/2", headers=_auth(2)).status_code == 404
    assert db_session.query(Exam).filter(Exam.id == 2).first() is not None


# --- DELETE /classes/{id} -----------------------------------------------------

def test_delete_class_with_exams_returns_409_without_sql_in_body(client, db_session):
    resp = client.delete("/api/v1/classes/1", headers=_auth(4))  # has exam 1 + members
    assert resp.status_code == 409
    body = resp.text
    # Pre-fix this returned 500 with the raw statement in the body
    # ("IntegrityError: Column 'class_id' cannot be null" / UPDATE exams ...).
    # No SQL text may ever leak into a response body on this path.
    for fragment in ("IntegrityError", "UPDATE", "class_id", "SET", "sqlalchemy"):
        assert fragment not in body, f"leaked SQL fragment in body: {fragment}"
    assert db_session.query(Class).filter(Class.id == 1).first() is not None


def test_delete_class_with_members_returns_409(client, db_session):
    resp = client.delete("/api/v1/classes/5", headers=_auth(4))  # members, no exams
    assert resp.status_code == 409
    assert "anggota" in resp.json()["message"]
    assert db_session.query(Class).filter(Class.id == 5).first() is not None


def test_delete_empty_class_returns_200(client, db_session):
    resp = client.delete("/api/v1/classes/4", headers=_auth(4))  # no exams, no members
    assert resp.status_code == 200
    assert resp.json()["success"] is True
    assert resp.json()["data"]["deleted_id"] == 4
    assert db_session.query(Class).filter(Class.id == 4).first() is None


def test_delete_class_cross_tenant_returns_404(client, db_session):
    assert client.delete("/api/v1/classes/2", headers=_auth(4)).status_code == 404
    assert client.delete("/api/v1/classes/2", headers=_auth(2)).status_code == 404
    assert db_session.query(Class).filter(Class.id == 2).first() is not None
