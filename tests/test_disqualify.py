"""Disqualify tests — Finding 1 (pre-demo recheck).

POST /proctoring/session/disqualify used to 500 on live TiDB: the handler
writes ProctoringLog(event_type="teacher_disqualification",
camera_source="human_supervisor"), but neither value existed in the
proctoring_logs column enums, so the INSERT failed with
DataError 1265 and the session stayed in_progress. The 500 body also
leaked the raw SQL INSERT via the global exception handler's str(exc).

Run: .venv/bin/python -m pytest tests/test_disqualify.py -v
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
from app.models.proctoring import ProctoringLog
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
        Class(id=1, name="Kelas A", grade_level="10", academic_year="2025/2026", created_by=4),
        ClassMember(class_id=1, user_id=6, role="student"),
        Exam(id=1, teacher_id=4, class_id=1, title="Ujian A", duration_minutes=60,
             start_time=now - timedelta(hours=1), end_time=now + timedelta(hours=2),
             status="published"),
        ExamSession(id=1, exam_id=1, student_id=6, start_time=now - timedelta(minutes=10),
                    status="in_progress", total_score=0, integrity_score=100),
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


def test_teacher_disqualify_succeeds_and_ends_session(client, db_session):
    resp = client.post("/api/v1/proctoring/session/disqualify", headers=_auth(4),
                       json={"session_id": 1, "reason": "curang", "notes": "membuka HP"})
    assert resp.status_code == 200
    assert resp.json()["success"] is True
    assert resp.json()["data"]["status"] == "aborted"

    session = db_session.query(ExamSession).filter(ExamSession.id == 1).first()
    assert session.status == "aborted"
    assert float(session.total_score) == 0
    assert session.integrity_score == 0
    assert session.submit_time is not None

    log = (db_session.query(ProctoringLog)
           .filter(ProctoringLog.session_id == 1)
           .order_by(ProctoringLog.id.desc()).first())
    assert log is not None
    assert log.event_type == "teacher_disqualification"
    assert log.camera_source == "human_supervisor"
    assert log.severity == "high"
    assert log.reviewed_by_teacher is True
    assert log.teacher_verdict == "confirmed_violation"


def test_disqualify_db_error_returns_500_without_sql_in_body(client, db_session, monkeypatch):
    # Simulate the live failure: the INSERT blows up in the DB driver and
    # the exception text carries the raw statement + parameters.
    def _boom():
        raise Exception(
            "pymysql.err.DataError: (1265, \"Data truncated for column 'event_type'\") "
            "[SQL: INSERT INTO proctoring_logs (session_id, event_type, camera_source, "
            "severity) VALUES (%(session_id)s, %(event_type)s, %(camera_source)s, "
            "%(severity)s)] [parameters: {'session_id': 1, "
            "'event_type': 'teacher_disqualification'}]"
        )
    monkeypatch.setattr(db_session, "commit", _boom)

    resp = client.post("/api/v1/proctoring/session/disqualify", headers=_auth(4),
                       json={"session_id": 1, "reason": "curang"})
    assert resp.status_code == 500
    body = resp.text
    for fragment in ("INSERT", "pymysql", "1265", "proctoring_logs",
                     "Data truncated", "DataError", "VALUES", "parameters"):
        assert fragment not in body, f"leaked SQL/driver fragment in body: {fragment}"
    assert resp.json()["message"] == "Terjadi kesalahan internal pada server."
    assert resp.json()["error"]["code"] == "INTERNAL_SERVER_ERROR"
