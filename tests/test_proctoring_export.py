"""Camera-log Excel export — GET /proctoring/exam/{exam_id}/export/excel.

One row per proctoring log for the exam. Role scoping must match the logs
endpoint GET /proctoring/exam/{exam_id}/logs: admin + exam-owning teacher
may export; a non-owner teacher gets the same 404, a student the same 403.

Run: .venv/bin/python -m pytest tests/test_proctoring_export.py -v
"""
import io
from datetime import datetime, timedelta

import openpyxl
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.core.database import Base, get_db
from app.core.security import create_access_token
from app.models.academic import Class
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
        Tenant(id=2, name="Sekolah B", code="SCH-B"),
        _user(2, "ADM-A", "admin-a@sch-a.id", "admin", 1, "Admin A"),
        _user(4, "TCH-A", "guru-a@sch-a.id", "teacher", 1, "Guru A"),
        _user(5, "TCH-B", "guru-b@sch-b.id", "teacher", 2, "Guru B"),
        _user(6, "SIS-A1", "siswa-a1@sch-a.id", "student", 1, "Siswa A1"),
        _user(7, "SIS-A2", "siswa-a2@sch-a.id", "student", 1, "Siswa A2"),
    ])
    db.add_all([
        Class(id=1, name="Kelas A", grade_level="10", academic_year="2025/2026", created_by=4),
        Class(id=2, name="Kelas B", grade_level="10", academic_year="2025/2026", created_by=5),
        Exam(id=1, teacher_id=4, class_id=1, title="Ujian A", duration_minutes=60,
             start_time=now - timedelta(hours=1), end_time=now + timedelta(hours=2),
             status="published"),
        Exam(id=2, teacher_id=5, class_id=2, title="Ujian B", duration_minutes=60,
             start_time=now - timedelta(hours=1), end_time=now + timedelta(hours=2),
             status="published"),
        ExamSession(id=1, exam_id=1, student_id=6, start_time=now - timedelta(minutes=10),
                    status="submitted", total_score=8.0, integrity_score=95),
        ExamSession(id=2, exam_id=1, student_id=7, start_time=now - timedelta(minutes=10),
                    status="submitted", total_score=9.0, integrity_score=88),
        ExamSession(id=3, exam_id=2, student_id=6, start_time=now - timedelta(minutes=10),
                    status="submitted", total_score=7.0, integrity_score=100),
        # Three logs of different types / severities / verdicts, exam 1 only.
        ProctoringLog(id=1, session_id=1, event_type="gaze_away",
                      camera_source="primary_camera", severity="medium",
                      duration_seconds=5, event_timestamp=now - timedelta(minutes=8),
                      reviewed_by_teacher=False, teacher_verdict="pending"),
        ProctoringLog(id=2, session_id=1, event_type="phone_detected",
                      camera_source="secondary_camera", severity="high",
                      duration_seconds=12, event_timestamp=now - timedelta(minutes=6),
                      snapshot_url="https://example.test/snap1.png",
                      reviewed_by_teacher=True, teacher_verdict="confirmed_violation"),
        ProctoringLog(id=3, session_id=2, event_type="tab_switch",
                      camera_source="system_event", severity="low",
                      duration_seconds=1, event_timestamp=now - timedelta(minutes=4),
                      reviewed_by_teacher=True, teacher_verdict="ignored_false_positive"),
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


EXPECTED_HEADERS = [
    "No",
    "Waktu Kejadian",
    "Nama Siswa",
    "NISN / ID",
    "ID Sesi",
    "Jenis Kejadian",
    "Tingkat Keparahan",
    "Durasi (detik)",
    "Sumber Kamera",
    "Verdict Guru",
    "Sudah Direview",
    "Skor Integritas Sesi Saat Ini (%)",
    "Tautan Snapshot",
]


def _load_workbook(resp):
    assert resp.status_code == 200, resp.text
    assert "spreadsheetml.sheet" in resp.headers["content-type"]
    wb = openpyxl.load_workbook(io.BytesIO(resp.content))
    return wb.active


def test_admin_can_export_camera_log_excel(client):
    resp = client.get("/api/v1/proctoring/exam/1/export/excel", headers=_auth(2))
    ws = _load_workbook(resp)
    assert resp.headers["content-disposition"].endswith("laporan_kamera_exam_1.xlsx")

    assert [c.value for c in ws[4]] == EXPECTED_HEADERS
    rows = list(ws.iter_rows(min_row=5, values_only=True))
    assert len(rows) == 3

    # Chronological order; row 1 = gaze_away (Siswa A1, session 1).
    assert rows[0][2] == "Siswa A1"
    assert rows[0][3] == "SIS-A1"
    assert rows[0][4] == 1
    assert rows[0][5] == "gaze_away"
    assert rows[0][6] == "medium"
    assert rows[0][7] == 5
    assert rows[0][8] == "primary_camera"
    assert rows[0][9] == "pending"
    assert rows[0][10] == "Belum"
    assert rows[0][11] == 95  # session 1 current integrity score
    assert rows[0][12] == "-"

    # Row 2 = phone_detected, high severity, confirmed, reviewed, snapshot kept.
    assert rows[1][5] == "phone_detected"
    assert rows[1][6] == "high"
    assert rows[1][7] == 12
    assert rows[1][8] == "secondary_camera"
    assert rows[1][9] == "confirmed_violation"
    assert rows[1][10] == "Ya"
    assert rows[1][12] == "https://example.test/snap1.png"

    # Row 3 = tab_switch on session 2 (Siswa A2, integrity 88).
    assert rows[2][2] == "Siswa A2"
    assert rows[2][4] == 2
    assert rows[2][5] == "tab_switch"
    assert rows[2][6] == "low"
    assert rows[2][9] == "ignored_false_positive"
    assert rows[2][11] == 88


def test_owner_teacher_can_export_camera_log_excel(client):
    resp = client.get("/api/v1/proctoring/exam/1/export/excel", headers=_auth(4))
    ws = _load_workbook(resp)
    rows = list(ws.iter_rows(min_row=5, values_only=True))
    assert len(rows) == 3


def test_non_owner_teacher_gets_same_denial_as_logs(client):
    export_resp = client.get("/api/v1/proctoring/exam/1/export/excel", headers=_auth(5))
    logs_resp = client.get("/api/v1/proctoring/exam/1/logs", headers=_auth(5))
    assert export_resp.status_code == 404
    assert export_resp.status_code == logs_resp.status_code


def test_student_gets_same_denial_as_logs(client):
    export_resp = client.get("/api/v1/proctoring/exam/1/export/excel", headers=_auth(6))
    logs_resp = client.get("/api/v1/proctoring/exam/1/logs", headers=_auth(6))
    assert export_resp.status_code == 403
    assert export_resp.status_code == logs_resp.status_code


def test_export_exam_without_logs_returns_header_only(client):
    resp = client.get("/api/v1/proctoring/exam/2/export/excel", headers=_auth(5))
    ws = _load_workbook(resp)
    assert [c.value for c in ws[4]] == EXPECTED_HEADERS
    assert list(ws.iter_rows(min_row=5, values_only=True)) == []
