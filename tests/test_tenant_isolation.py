"""Tenant isolation tests — a school admin must NEVER see another school's data.

Two schools (tenants A and B) with a full fixture each: admin, teacher,
students, class, question bank, exam, sessions. Every test authenticates
with a REAL JWT (create_access_token) and overrides ONLY get_db, so the
full auth + scoping path is exercised. Cross-tenant access must return 404
(the codebase convention: never confirm another tenant's resource exists).

Run: .venv/bin/python -m pytest tests/test_tenant_isolation.py -v
"""
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.websockets import WebSocketDisconnect

from app.main import app
from app.core.database import Base, get_db
from app.core.security import create_access_token
from app.models.academic import Class, ClassMember
from app.models.exam import Exam, ExamQuestion
from app.models.proctoring import ProctoringLog
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
        Class(id=1, name="Kelas A", grade_level="10", academic_year="2025/2026", created_by=4),
        Class(id=2, name="Kelas B", grade_level="10", academic_year="2025/2026", created_by=5),
        ClassMember(class_id=1, user_id=6, role="student"),
        ClassMember(class_id=1, user_id=7, role="student"),
        ClassMember(class_id=2, user_id=8, role="student"),
        QuestionBank(id=1, teacher_id=4, title="Bank A", subject="Matematika"),
        QuestionBank(id=2, teacher_id=5, title="Bank B", subject="Matematika"),
        Question(id=1, bank_id=1, question_type="multiple_choice", prompt="Soal A",
                 options_json=[{"id": "A", "text": "1"}, {"id": "B", "text": "2"}],
                 correct_answer="A"),
        Question(id=2, bank_id=2, question_type="multiple_choice", prompt="Soal B",
                 options_json=[{"id": "A", "text": "1"}, {"id": "B", "text": "2"}],
                 correct_answer="B"),
    ])
    db.add_all([
        Exam(id=1, teacher_id=4, class_id=1, title="Ujian A", duration_minutes=60,
             start_time=now - timedelta(hours=1), end_time=now + timedelta(hours=2),
             status="published"),
        Exam(id=2, teacher_id=5, class_id=2, title="Ujian B", duration_minutes=60,
             start_time=now - timedelta(hours=1), end_time=now + timedelta(hours=2),
             status="published"),
        ExamQuestion(exam_id=1, question_id=1, order_index=1, allocated_points=10),
        ExamQuestion(exam_id=2, question_id=2, order_index=1, allocated_points=10),
    ])
    db.add_all([
        ExamSession(id=1, exam_id=1, student_id=6, start_time=now - timedelta(minutes=10),
                    status="submitted", total_score=8.0, integrity_score=95,
                    pairing_token="pair-token-a1"),
        ExamSession(id=2, exam_id=2, student_id=8, start_time=now - timedelta(minutes=10),
                    status="submitted", total_score=9.0, integrity_score=100,
                    pairing_token="pair-token-b"),
        StudentAnswer(id=1, session_id=1, question_id=1, student_response="A",
                      is_correct=True, auto_score=10, final_score=10),
        StudentAnswer(id=2, session_id=2, question_id=2, student_response="B",
                      is_correct=True, auto_score=10, final_score=10),
        ProctoringLog(id=1, session_id=1, event_type="face_absent",
                      camera_source="primary_camera", severity="high",
                      duration_seconds=8, event_timestamp=now),
    ])
    db.commit()

    app.dependency_overrides[get_db] = lambda: db
    try:
        yield db
    finally:
        app.dependency_overrides.pop(get_db, None)
        db.close()


PAIR_TOKEN = "pair-token-a1"


def _token(user_id: int) -> str:
    return create_access_token(data={"sub": str(user_id)})


def _auth(user_id: int):
    return {"Authorization": f"Bearer {_token(user_id)}"}


@pytest.fixture
def client(db_session):
    return TestClient(app, raise_server_exceptions=False)


# --- Admin user management ---------------------------------------------------

def test_admin_lists_only_own_tenant_users(client):
    resp = client.get("/api/v1/admin/users", headers=_auth(2))  # Admin A
    assert resp.status_code == 200
    ids = {u["id"] for u in resp.json()["data"]}
    assert ids == {2, 4, 6, 7}  # admin/teacher/students of school A only
    assert 3 not in ids and 5 not in ids and 8 not in ids and 1 not in ids


def test_admin_cannot_toggle_other_tenant_user(client):
    resp = client.patch("/api/v1/admin/users/3/toggle-status", headers=_auth(2))
    assert resp.status_code == 404
    # ...and the target is untouched
    resp2 = client.patch("/api/v1/admin/users/6/toggle-status", headers=_auth(2))
    assert resp2.status_code == 200
    assert resp2.json()["data"]["is_active"] is False


def test_admin_created_user_lands_in_own_tenant(client, db_session):
    resp = client.post(
        "/api/v1/admin/users",
        headers=_auth(2),
        json={"identifier": "TCH-A2", "email": "guru-a2@sch-a.id",
              "password": "Secret123!", "full_name": "Guru A2", "role": "teacher"},
    )
    assert resp.status_code == 200
    created = db_session.query(User).filter(User.identifier == "TCH-A2").first()
    assert created is not None
    assert created.tenant_id == 1  # forced from the caller, not the payload


# --- Exams -------------------------------------------------------------------

def test_admin_cannot_read_other_tenant_exam(client):
    resp = client.get("/api/v1/exams/2", headers=_auth(2))  # Admin A -> exam B
    assert resp.status_code == 404
    resp = client.get("/api/v1/exams", headers=_auth(2))
    assert resp.status_code == 200
    assert {e["id"] for e in resp.json()["data"]} == {1}


def test_teacher_cannot_read_or_modify_other_tenant_exam(client):
    assert client.get("/api/v1/exams/2", headers=_auth(4)).status_code == 404
    assert client.put("/api/v1/exams/2", headers=_auth(4),
                      json={"title": "Disusupi"}).status_code == 404
    assert client.post("/api/v1/exams/2/publish", headers=_auth(4)).status_code == 404
    # ...and cannot attach another school's question to their own exam
    assert client.post("/api/v1/exams/1/questions", headers=_auth(4),
                       json={"question_id": 2, "order_index": 2,
                             "allocated_points": 5}).status_code == 404


def test_teacher_cannot_create_exam_for_other_tenant_class(client):
    resp = client.post("/api/v1/exams", headers=_auth(4), json={
        "class_id": 2, "title": "Ujian Siluman", "duration_minutes": 30,
        "start_time": (datetime.utcnow() + timedelta(hours=1)).isoformat(),
        "end_time": (datetime.utcnow() + timedelta(hours=2)).isoformat(),
    })
    assert resp.status_code == 404


# --- Classes / question banks -----------------------------------------------

def test_teacher_cannot_read_other_tenant_class_or_bank(client):
    assert client.get("/api/v1/classes/2", headers=_auth(4)).status_code == 404
    assert client.get("/api/v1/questions/banks/2", headers=_auth(4)).status_code == 404
    assert client.put("/api/v1/questions/banks/2", headers=_auth(4),
                      json={"title": "Disusupi"}).status_code == 404
    assert client.delete("/api/v1/questions/banks/2", headers=_auth(4)).status_code == 404
    assert client.put("/api/v1/questions/items/2", headers=_auth(4),
                      json={"prompt": "Disusupi"}).status_code == 404


def test_admin_class_list_is_tenant_scoped(client):
    resp = client.get("/api/v1/classes", headers=_auth(2))
    assert resp.status_code == 200
    assert {c["id"] for c in resp.json()["data"]} == {1}
    resp = client.get("/api/v1/classes/2", headers=_auth(2))
    assert resp.status_code == 404


def test_teacher_student_list_excludes_other_tenant(client):
    resp = client.get("/api/v1/classes/users/students", headers=_auth(4))
    assert resp.status_code == 200
    assert {s["id"] for s in resp.json()["data"]} == {6, 7}
    resp = client.get("/api/v1/classes/users/students", headers=_auth(2))
    assert resp.status_code == 200
    assert {s["id"] for s in resp.json()["data"]} == {6, 7}


def test_add_member_rejects_other_tenant_student(client):
    resp = client.post("/api/v1/classes/1/members", headers=_auth(2),
                       json={"user_id": 8, "role": "student"})
    assert resp.status_code == 404


# --- Sessions, grading, analytics, proctoring -------------------------------

def test_teacher_cannot_read_or_override_other_tenant_session(client):
    assert client.get("/api/v1/grading/session/2", headers=_auth(4)).status_code == 404
    assert client.get("/api/v1/grading/exam/2/sessions", headers=_auth(4)).status_code == 404
    assert client.put("/api/v1/grading/answer/2/override", headers=_auth(4),
                      json={"teacher_override_score": 0}).status_code == 404
    # ...and an admin from school A cannot either
    assert client.get("/api/v1/grading/session/2", headers=_auth(2)).status_code == 404
    assert client.get("/api/v1/analytics/exam/2/items", headers=_auth(2)).status_code == 404
    assert client.get("/api/v1/proctoring/exam/2/logs", headers=_auth(2)).status_code == 404


def test_teacher_cannot_disqualify_or_warn_other_tenant_session(client):
    assert client.post("/api/v1/proctoring/session/disqualify", headers=_auth(4),
                       json={"session_id": 2, "reason": "curang"}).status_code == 404
    assert client.post("/api/v1/proctoring/send-warning", headers=_auth(4),
                       json={"session_id": 2, "message_text": "hei",
                             "urgency": "high"}).status_code == 404
    assert client.post("/api/v1/proctoring/log-event", headers=_auth(4),
                       json={"session_id": 2, "event_type": "face_absent",
                             "camera_source": "primary_camera", "severity": "high",
                             "duration_seconds": 5}).status_code == 404


def test_student_cannot_start_or_read_other_tenant_exam(client):
    # Siswa A1 is not enrolled in class B -> cannot start exam B at all
    assert client.post("/api/v1/student/exam/2/start", headers=_auth(6)).status_code == 404
    # Siswa A2 never took exam A -> cannot read siswa A1's result
    assert client.get("/api/v1/student/exam/1/result", headers=_auth(7)).status_code == 404
    # Siswa B cannot take exam A either
    assert client.post("/api/v1/student/exam/1/start", headers=_auth(8)).status_code == 404
    # ...and cannot inject a fake violation into siswa A1's session
    assert client.post("/api/v1/proctoring/log-event", headers=_auth(8),
                       json={"session_id": 1, "event_type": "face_absent",
                             "camera_source": "primary_camera", "severity": "high",
                             "duration_seconds": 5}).status_code == 404


# --- Secrets (privilege escalation) ------------------------------------------

def test_school_admin_cannot_touch_platform_secrets(client):
    assert client.get("/api/v1/superadmin/secrets", headers=_auth(2)).status_code == 403
    assert client.post("/api/v1/superadmin/secrets", headers=_auth(2),
                       json={"key_name": "X", "service_name": "test",
                             "value": "pwned"}).status_code == 403
    assert client.get("/api/v1/superadmin/secrets/tasks", headers=_auth(2)).status_code == 403


# --- Superadmin still sees everything ----------------------------------------

def test_superadmin_unaffected(client):
    assert client.get("/api/v1/exams/2", headers=_auth(1)).status_code == 200
    assert client.get("/api/v1/grading/session/2", headers=_auth(1)).status_code == 200
    resp = client.get("/api/v1/admin/users", headers=_auth(1))
    assert resp.status_code == 200
    assert {u["id"] for u in resp.json()["data"]} >= {2, 3, 4, 5, 6, 7, 8}


# --- WebSockets ---------------------------------------------------------------

@pytest.fixture
def ws_client(db_session):
    """Patch the WS module's SessionLocal to the in-memory test engine,
    since the WS handlers bypass the get_db dependency override."""
    import app.api.v1.endpoints.proctoring_ws as ws_mod
    from sqlalchemy.orm import sessionmaker as _sm
    engine = db_session.get_bind()
    factory = _sm(autocommit=False, autoflush=False, bind=engine)
    orig = ws_mod.SessionLocal
    ws_mod.SessionLocal = factory
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        ws_mod.SessionLocal = orig


def test_ws_live_monitor_requires_auth_and_tenant_access(ws_client):
    # No token -> 4401
    with pytest.raises(WebSocketDisconnect) as ei:
        with ws_client.websocket_connect("/ws/exam/1/live-monitor"):
            pass
    assert ei.value.code == 4401
    # Admin B's token for school A's exam -> 4403
    with pytest.raises(WebSocketDisconnect) as ei:
        with ws_client.websocket_connect(
            f"/ws/exam/1/live-monitor?token={_token(3)}"
        ):
            pass
    assert ei.value.code == 4403
    # Admin A for school A's exam -> connects
    with ws_client.websocket_connect(
        f"/ws/exam/1/live-monitor?token={_token(2)}"
    ) as ws:
        ws.send_text("ping")
        ws.close()


def test_ws_companion_validates_pairing_token(ws_client):
    # Wrong token -> 4403
    with pytest.raises(WebSocketDisconnect) as ei:
        with ws_client.websocket_connect(
            f"/ws/proctoring/1/companion?token={'wrong-token-1'}"
        ):
            pass
    assert ei.value.code == 4403
    # Correct persisted token -> connects
    with ws_client.websocket_connect(
        f"/ws/proctoring/1/companion?token={PAIR_TOKEN}"
    ) as ws:
        ws.send_text("ping")
        ws.close()
