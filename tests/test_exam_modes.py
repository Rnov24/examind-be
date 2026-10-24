"""Exam modes — live (simultaneous, fixed start) vs non-live (independent
start inside the window, personal clock from begun_at, hard-capped at
end_time). Mirrors the test_tenant_isolation fixture style: in-memory
SQLite, real JWTs, ONLY get_db overridden.

Run: .venv/bin/python -m pytest tests/test_exam_modes.py -v
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

    now = datetime.utcnow()
    db.add_all([
        Tenant(id=1, name="Sekolah A", code="SCH-A"),
        _user(4, "TCH-A", "guru-a@sch-a.id", "teacher", 1, "Guru A"),
        _user(6, "SIS-A1", "siswa-a1@sch-a.id", "student", 1, "Siswa A1"),
        _user(7, "SIS-A2", "siswa-a2@sch-a.id", "student", 1, "Siswa A2"),
    ])
    db.add_all([
        Class(id=1, name="Kelas A", grade_level="10", academic_year="2025/2026", created_by=4),
        ClassMember(class_id=1, user_id=6, role="student"),
        ClassMember(class_id=1, user_id=7, role="student"),
        QuestionBank(id=1, teacher_id=4, title="Bank A", subject="Matematika"),
        Question(id=1, bank_id=1, question_type="multiple_choice", prompt="Soal A",
                 options_json=[{"id": "A", "text": "1"}, {"id": "B", "text": "2"}],
                 correct_answer="A"),
    ])
    db.add_all([
        # 1: LIVE, starts in 1h — early start must be rejected.
        Exam(id=1, teacher_id=4, class_id=1, title="Live Nanti", duration_minutes=60,
             start_time=now + timedelta(hours=1), end_time=now + timedelta(hours=3),
             status="published", exam_mode="live"),
        # 2: LIVE, started 50 min ago, ends in 5 min — remaining must clamp
        # to ~300s even though the 60-min duration has 10 min left.
        Exam(id=2, teacher_id=4, class_id=1, title="Live Hampir Habis", duration_minutes=60,
             start_time=now - timedelta(minutes=50), end_time=now + timedelta(minutes=5),
             status="published", exam_mode="live"),
        # 3: NON-LIVE, window opened 1h ago, closes in 2h — mid-window start OK.
        Exam(id=3, teacher_id=4, class_id=1, title="Mandiri", duration_minutes=60,
             start_time=now - timedelta(hours=1), end_time=now + timedelta(hours=2),
             status="published", exam_mode="non_live"),
        # 4: NON-LIVE, window already closed — start must be rejected.
        Exam(id=4, teacher_id=4, class_id=1, title="Mandiri Tutup", duration_minutes=60,
             start_time=now - timedelta(hours=3), end_time=now - timedelta(hours=1),
             status="published", exam_mode="non_live"),
        ExamQuestion(exam_id=1, question_id=1, order_index=1, allocated_points=10),
        ExamQuestion(exam_id=2, question_id=1, order_index=1, allocated_points=10),
        ExamQuestion(exam_id=3, question_id=1, order_index=1, allocated_points=10),
        ExamQuestion(exam_id=4, question_id=1, order_index=1, allocated_points=10),
    ])
    # Student 6 already began live exam 2 fifty minutes ago (begun_at set).
    db.add(
        ExamSession(id=10, exam_id=2, student_id=6,
                    start_time=now - timedelta(minutes=50),
                    begun_at=now - timedelta(minutes=50),
                    status="in_progress", total_score=0.0, integrity_score=100,
                    pairing_token="tok-10")
    )
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


# --- LIVE: fixed start, shared clock -----------------------------------------

def test_live_rejects_early_start(client):
    resp = client.post("/api/v1/student/exam/1/start", headers=_auth(6))
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "EXAM_NOT_STARTED"
    assert "serentak" in resp.json()["message"]


def test_live_remaining_clamps_to_end_time(client, db_session):
    # Resume of the session begun 50 min ago on a 60-min exam ending in 5 min.
    resp = client.post("/api/v1/student/exam/2/start", headers=_auth(6))
    assert resp.status_code == 200
    remaining = resp.json()["data"]["duration_remaining_seconds"]
    # Duration alone would leave ~600s; the end_time cap leaves ~300s.
    assert 240 <= remaining <= 300


def test_live_begin_also_clamps_to_end_time(client, db_session):
    resp = client.post("/api/v1/student/exam/2/begin", headers=_auth(6))
    assert resp.status_code == 200
    remaining = resp.json()["data"]["duration_remaining_seconds"]
    assert 240 <= remaining <= 300


# --- NON-LIVE: independent start inside the window ---------------------------

def test_non_live_allows_mid_window_start(client):
    resp = client.post("/api/v1/student/exam/3/start", headers=_auth(6))
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["exam"]["exam_mode"] == "non_live"
    # No begun_at yet: full duration (60 min = 3600s), end_time is 2h away.
    assert data["duration_remaining_seconds"] == 3600


def test_non_live_rejects_start_after_end_time(client):
    resp = client.post("/api/v1/student/exam/4/start", headers=_auth(6))
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "EXAM_ENDED"


def test_non_live_remaining_uses_begun_at_then_clamps(client, db_session):
    # Student 7 starts non-live exam 3, then we rewind their begun_at 50 min
    # and shrink the window so end_time is 5 min away: remaining must be
    # ~300s (the end_time cap), not ~600s (the duration remainder).
    resp = client.post("/api/v1/student/exam/3/start", headers=_auth(7))
    assert resp.status_code == 200
    session = db_session.query(ExamSession).filter(
        ExamSession.exam_id == 3, ExamSession.student_id == 7
    ).first()
    now = datetime.utcnow()
    session.begun_at = now - timedelta(minutes=50)
    exam = db_session.query(Exam).filter(Exam.id == 3).first()
    exam.end_time = now + timedelta(minutes=5)
    db_session.commit()

    resp = client.post("/api/v1/student/exam/3/start", headers=_auth(7))
    assert resp.status_code == 200
    remaining = resp.json()["data"]["duration_remaining_seconds"]
    assert 240 <= remaining <= 300


# --- Create / update validation ----------------------------------------------

def test_non_live_create_rejects_duration_longer_than_window(client):
    now = datetime.utcnow()
    resp = client.post(
        "/api/v1/exams",
        headers=_auth(4),
        json={
            "title": "Mandiri Terlalu Panjang",
            "class_id": 1,
            "duration_minutes": 120,
            "start_time": (now + timedelta(hours=1)).isoformat(),
            "end_time": (now + timedelta(hours=2)).isoformat(),
            "exam_mode": "non_live",
        },
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INVALID_NON_LIVE_WINDOW"


def test_create_defaults_to_live_and_returns_mode(client):
    now = datetime.utcnow()
    resp = client.post(
        "/api/v1/exams",
        headers=_auth(4),
        json={
            "title": "Tanpa Mode",
            "class_id": 1,
            "duration_minutes": 60,
            "start_time": (now + timedelta(hours=1)).isoformat(),
            "end_time": (now + timedelta(hours=3)).isoformat(),
        },
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["exam_mode"] == "live"


def test_update_can_switch_mode_and_validates_window(client):
    now = datetime.utcnow()
    # Switch exam 3 (non-live, 60-min duration, 3h window) to live: fine.
    resp = client.put("/api/v1/exams/3", headers=_auth(4), json={"exam_mode": "live"})
    assert resp.status_code == 200
    assert resp.json()["data"]["exam_mode"] == "live"
    # Shrink its window below the 60-min duration, then switch back: rejected.
    # (start is now-1h, so end must come within now to make window < 60 min.)
    resp = client.put(
        "/api/v1/exams/3",
        headers=_auth(4),
        json={"end_time": (now - timedelta(minutes=10)).isoformat()},
    )
    assert resp.status_code == 200  # live has no window-length rule
    resp = client.put("/api/v1/exams/3", headers=_auth(4), json={"exam_mode": "non_live"})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INVALID_NON_LIVE_WINDOW"


def test_invalid_mode_rejected(client):
    resp = client.put("/api/v1/exams/3", headers=_auth(4), json={"exam_mode": "serentak"})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INVALID_EXAM_MODE"
