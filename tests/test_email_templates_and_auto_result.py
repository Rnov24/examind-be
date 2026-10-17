import re
import io
import pytest
import logging
from unittest.mock import patch, AsyncMock, MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.database import Base
from app.models.user import User
from app.models.tenant import Tenant
from app.models.academic import Class
from app.models.exam import Exam, ExamQuestion
from app.models.question import Question, QuestionBank
from app.models.session import ExamSession, StudentAnswer
from app.services.email.resend_service import (
    render_otp_html,
    render_password_reset_html,
    render_password_reset_success_html,
    render_exam_result_html,
    send_email_via_resend,
    send_exam_result_email,
)
from app.services.grading.background_worker import grade_exam_session_async


# ---------------------------------------------------------------------------
# Part 1: HTML Email Template Redesign & Anti-Slop Discipline Tests
# ---------------------------------------------------------------------------

EMOJI_PATTERN = re.compile(
    r"[\U00010000-\U0010ffff\u2600-\u26ff\u2700-\u27bf\u2300-\u23ff\u2b50\u203c-\u2049\u25aa-\u25fe]"
)


def _assert_anti_slop_compliance(html: str):
    """Enforce strict anti-slop email constraints."""
    # 1. No <style> tags (all CSS must be inline)
    assert "<style" not in html.lower(), "Email template must not contain <style> tags"
    assert "</style>" not in html.lower()

    # 2. No external CSS
    assert '<link rel="stylesheet"' not in html.lower()

    # 3. No linear or radial gradients
    assert "linear-gradient" not in html.lower(), "Email template must not contain linear gradients"
    assert "radial-gradient" not in html.lower(), "Email template must not contain radial gradients"

    # 4. No emojis anywhere
    assert not EMOJI_PATTERN.search(html), "Email template must not contain emojis"

    # 5. EXAMIND Palette: midnight-violet #150f23 and lime #c2ef4e present
    assert "#150f23" in html.lower(), "Header band or elements must include midnight-violet #150f23"
    assert "#c2ef4e" in html.lower(), "Accent rule or score must include lime #c2ef4e"

    # 6. Max-width 600px respected
    assert "max-width: 600px" in html, "Email layout must respect max-width: 600px"

    # 7. System font stack (no webfonts like Plus Jakarta Sans)
    assert "-apple-system" in html
    assert "'Segoe UI'" in html or "'segoe ui'" in html.lower()
    assert "Plus Jakarta Sans" not in html, "Webfonts like Plus Jakarta Sans should not be referenced in email clients"


def test_render_otp_html_compliance():
    """Verify render_otp_html adheres to anti-slop rules, EXAMIND palette, and monospace code box."""
    html = render_otp_html(otp_code="849201", purpose="email_verification", expires_in_minutes=10)
    _assert_anti_slop_compliance(html)

    # Monospace OTP box with violet tint (#ede9fe) and accent-violet digits (#6a5fc1)
    assert "849201" in html
    assert "#ede9fe" in html.lower()
    assert "#6a5fc1" in html.lower()
    assert "10 menit" in html
    assert "Verifikasi Alamat Email" in html

    # Also test purpose="security"
    sec_html = render_otp_html(otp_code="112233", purpose="security", expires_in_minutes=5)
    _assert_anti_slop_compliance(sec_html)
    assert "112233" in sec_html
    assert "5 menit" in sec_html


def test_render_password_reset_html_compliance():
    """Verify render_password_reset_html adheres to anti-slop rules, button, code box, and clean links."""
    html = render_password_reset_html(
        user_name="Ahmad Dahlan",
        reset_url="https://cbt.examind.id/auth/reset-password?token=xyz",
        token_code="492019",
        expires_in_minutes=15,
    )
    _assert_anti_slop_compliance(html)

    assert "Ahmad Dahlan" in html
    assert "https://cbt.examind.id/auth/reset-password?token=xyz" in html
    assert "492019" in html
    assert "#ede9fe" in html.lower()
    assert "#6a5fc1" in html.lower()
    assert "15 menit" in html


def test_render_password_reset_success_html_compliance():
    """Verify render_password_reset_success_html adheres to anti-slop rules and clear notification copy."""
    html = render_password_reset_success_html(user_name="Siti Rahmah")
    _assert_anti_slop_compliance(html)

    assert "Siti Rahmah" in html
    assert "Kata Sandi Berhasil Diperbarui" in html


def test_render_exam_result_html_compliance():
    """Verify NEW render_exam_result_html displays score, predicate, MCQ summary, PDF notice, and platform link."""
    html = render_exam_result_html(
        student_name="Budi Pratama",
        exam_title="Penilaian Akhir Semester Matematika",
        score=85.5,
        grade_predicate="Tuntas (KKM)",
        correct_count=18,
        wrong_count=2,
        unanswered_count=0,
        platform_url="https://cbt.examind.id",
    )
    _assert_anti_slop_compliance(html)

    # Contents
    assert "Budi Pratama" in html
    assert "Penilaian Akhir Semester Matematika" in html
    assert "85.5" in html
    assert "Tuntas (KKM)" in html
    assert "Benar" in html and "18" in html
    assert "Salah" in html and "2" in html
    assert "Kosong" in html and "0" in html
    # PDF attachment note
    assert "PDF" in html or "pdf" in html
    # Plain text link to platform (CTA-less)
    assert "https://cbt.examind.id" in html

    # Also test with summary_counts dict
    html_dict = render_exam_result_html(
        student_name="Dewi Lestari",
        exam_title="Biologi Molekuler",
        score=70,
        grade_predicate="Belum Tuntas",
        summary_counts={"correct": 14, "wrong": 5, "unanswered": 1},
    )
    _assert_anti_slop_compliance(html_dict)
    assert "Dewi Lestari" in html_dict
    assert "Biologi Molekuler" in html_dict
    assert "70" in html_dict
    assert "Belum Tuntas" in html_dict
    assert "14" in html_dict
    assert "5" in html_dict
    assert "1" in html_dict


# ---------------------------------------------------------------------------
# Part 2: Resend API Attachments & Backward Compatibility Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_send_email_via_resend_with_attachments():
    """Verify send_email_via_resend includes attachments in payload for Resend API."""
    mock_response = MagicMock()
    mock_response.is_success = True
    mock_response.json.return_value = {"id": "resend_att_123", "from": "test@examind.id"}

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post, \
         patch("app.core.secret_manager.get_secret", return_value=""), \
         patch.object(settings, "RESEND_API_KEY", "re_test_key_12345"):
        mock_post.return_value = mock_response

        attachments = [
            {"content": "JVBERi0xLjQK...", "filename": "hasil-ujian-1-nisn01.pdf"}
        ]
        res = await send_email_via_resend(
            to_email="student@siswa.sch.id",
            subject="Hasil Ujian",
            html_content="<p>Hasil ujian Anda</p>",
            attachments=attachments,
        )

        assert res["id"] == "resend_att_123"
        mock_post.assert_called_once()
        sent_json = mock_post.call_args[1]["json"]
        assert sent_json["to"] == ["student@siswa.sch.id"]
        assert sent_json["subject"] == "Hasil Ujian"
        assert sent_json["attachments"] == attachments


@pytest.mark.asyncio
async def test_send_email_via_resend_backward_compatibility():
    """Verify send_email_via_resend without attachments does not include 'attachments' key in payload."""
    mock_response = MagicMock()
    mock_response.is_success = True
    mock_response.json.return_value = {"id": "resend_no_att_456"}

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post, \
         patch("app.core.secret_manager.get_secret", return_value=""), \
         patch.object(settings, "RESEND_API_KEY", "re_test_key_12345"):
        mock_post.return_value = mock_response

        res = await send_email_via_resend(
            to_email="student@siswa.sch.id",
            subject="Kode OTP",
            html_content="<p>Kode OTP</p>",
        )

        assert res["id"] == "resend_no_att_456"
        mock_post.assert_called_once()
        sent_json = mock_post.call_args[1]["json"]
        assert "attachments" not in sent_json


# ---------------------------------------------------------------------------
# Part 3: Grading Worker Auto-Email Hook Tests
# ---------------------------------------------------------------------------

@pytest.fixture
def grading_db():
    """In-memory SQLite database seeded with an exam, student, and submission."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    session = TestingSession()

    tenant = Tenant(id=1, name="SMA Negeri 1", code="SMAN1", is_active=True)
    session.add(tenant)

    teacher = User(
        id=1,
        identifier="GURU001",
        email="guru@sman1.sch.id",
        password_hash="hash",
        full_name="Pak Budi Guru",
        role="teacher",
        tenant_id=1,
        is_active=True,
    )
    student = User(
        id=2,
        identifier="NISN100200",
        email="student.test@sman1.sch.id",
        password_hash="hash",
        full_name="Andi Mahasiswa",
        role="student",
        tenant_id=1,
        is_active=True,
    )
    session.add_all([teacher, student])

    cls = Class(id=1, name="XII IPA 1", grade_level="12", academic_year="2025/2026", created_by=1)
    session.add(cls)

    qbank = QuestionBank(id=1, teacher_id=1, title="Bank Soal Fisika", subject="Fisika")
    session.add(qbank)

    from datetime import datetime, timedelta
    exam = Exam(
        id=10,
        teacher_id=1,
        class_id=1,
        title="Ujian Akhir Semester Fisika",
        duration_minutes=60,
        start_time=datetime.utcnow(),
        end_time=datetime.utcnow() + timedelta(hours=2),
        status="published",
    )
    session.add(exam)

    q1 = Question(
        id=101,
        bank_id=1,
        prompt="Berapa kecepatan cahaya?",
        question_type="multiple_choice",
        correct_answer="3x10^8 m/s",
        options_json=["3x10^8 m/s", "3x10^6 m/s"],
        default_points=50.0,
    )
    q2 = Question(
        id=102,
        bank_id=1,
        prompt="Jelaskan hukum Newton 1",
        question_type="short_essay",
        correct_answer="Inersia",
        default_points=50.0,
    )
    session.add_all([q1, q2])

    eq1 = ExamQuestion(exam_id=10, question_id=101, order_index=1, allocated_points=50.0)
    eq2 = ExamQuestion(exam_id=10, question_id=102, order_index=2, allocated_points=50.0)
    session.add_all([eq1, eq2])

    exam_session = ExamSession(
        id=1001,
        exam_id=10,
        student_id=2,
        status="submitted",
        start_time=datetime.utcnow() - timedelta(minutes=45),
        submit_time=datetime.utcnow(),
    )
    session.add(exam_session)

    ans1 = StudentAnswer(
        session_id=1001,
        question_id=101,
        student_response="3x10^8 m/s",
        is_correct=True,
        final_score=50.0,
    )
    ans2 = StudentAnswer(
        session_id=1001,
        question_id=102,
        student_response="Benda cenderung mempertahankan keadaan diam atau bergerak lurus beraturan.",
        final_score=40.0,
    )
    session.add_all([ans1, ans2])

    session.commit()

    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def test_grading_worker_auto_email_success(grading_db):
    """Test full flow: session graded -> PDF generated -> auto-email dispatched with sanitized filename."""
    with patch("app.services.grading.background_worker.SessionLocal", return_value=grading_db), \
         patch("app.services.grading.background_worker.send_exam_result_email", new_callable=AsyncMock) as mock_send_email:
        mock_send_email.return_value = {"id": "msg_success_1", "mock": False}

        grade_exam_session_async(1001)

        # Check grading result committed
        grading_db.expire_all()
        session = grading_db.query(ExamSession).filter(ExamSession.id == 1001).first()
        assert session.status == "graded"
        assert float(session.total_score) > 0.0

        # Check email attempted
        mock_send_email.assert_called_once()
        call_kwargs = mock_send_email.call_args[1]

        assert call_kwargs["to_email"] == "student.test@sman1.sch.id"
        assert call_kwargs["student_name"] == "Andi Mahasiswa"
        assert call_kwargs["exam_title"] == "Ujian Akhir Semester Fisika"
        assert call_kwargs["pdf_filename"] == "hasil-ujian-10-NISN100200.pdf"

        # Check PDF bytes generated
        pdf_bytes = call_kwargs["pdf_bytes"]
        assert isinstance(pdf_bytes, bytes)
        assert len(pdf_bytes) > 0
        assert pdf_bytes.startswith(b"%PDF")

        # Check MCQ counts
        assert call_kwargs["summary_counts"]["correct"] == 1
        assert call_kwargs["summary_counts"]["wrong"] == 0
        assert call_kwargs["summary_counts"]["unanswered"] == 0


def test_grading_worker_email_failure_does_not_break_grading(grading_db, caplog):
    """Test that email dispatch failure logs error and NEVER breaks or rolls back grading."""
    with patch("app.services.grading.background_worker.SessionLocal", return_value=grading_db), \
         patch("app.services.grading.background_worker.send_exam_result_email", new_callable=AsyncMock) as mock_send_email:
        # Simulate fatal network/API exception
        mock_send_email.side_effect = RuntimeError("SMTP Timeout / Resend down")

        with caplog.at_level(logging.ERROR, logger="examind.grading"):
            grade_exam_session_async(1001)

        # Grading MUST be committed
        grading_db.expire_all()
        session = grading_db.query(ExamSession).filter(ExamSession.id == 1001).first()
        assert session.status == "graded"
        assert float(session.total_score) > 0.0

        # Error must be logged
        assert any("[GradingWorker] Failed to dispatch result email" in r.message for r in caplog.records)


def test_grading_worker_production_mock_guard_skips_cleanly(grading_db, caplog):
    """In production, if email service returns mock=True, log warning and skip without failing grading."""
    with patch("app.services.grading.background_worker.SessionLocal", return_value=grading_db), \
         patch("app.services.grading.background_worker.send_exam_result_email", new_callable=AsyncMock) as mock_send_email, \
         patch.object(settings, "ENVIRONMENT", "production"):
        mock_send_email.return_value = {"id": "mock_id", "mock": True}

        with caplog.at_level(logging.WARNING, logger="examind.grading"):
            grade_exam_session_async(1001)

        grading_db.expire_all()
        session = grading_db.query(ExamSession).filter(ExamSession.id == 1001).first()
        assert session.status == "graded"

        # Warning logged about mock in production
        assert any("Email service returned mock in production environment" in r.message for r in caplog.records)


def test_grading_worker_skips_when_student_has_no_email(grading_db):
    """If student has no email address, auto-email is skipped silently and grading succeeds."""
    student = grading_db.query(User).filter(User.id == 2).first()
    student.email = ""
    grading_db.commit()

    with patch("app.services.grading.background_worker.SessionLocal", return_value=grading_db), \
         patch("app.services.grading.background_worker.send_exam_result_email", new_callable=AsyncMock) as mock_send_email:

        grade_exam_session_async(1001)

        grading_db.expire_all()
        session = grading_db.query(ExamSession).filter(ExamSession.id == 1001).first()
        assert session.status == "graded"
        mock_send_email.assert_not_called()


def test_grading_worker_skips_when_config_flag_disabled(grading_db):
    """If EXAM_RESULT_EMAIL_ENABLED is False, auto-email is skipped and grading succeeds."""
    with patch("app.services.grading.background_worker.SessionLocal", return_value=grading_db), \
         patch("app.services.grading.background_worker.send_exam_result_email", new_callable=AsyncMock) as mock_send_email, \
         patch.object(settings, "EXAM_RESULT_EMAIL_ENABLED", False):

        grade_exam_session_async(1001)

        grading_db.expire_all()
        session = grading_db.query(ExamSession).filter(ExamSession.id == 1001).first()
        assert session.status == "graded"
        mock_send_email.assert_not_called()


def test_filename_sanitization_with_special_characters(grading_db):
    """Verify student identifiers with spaces, colons, or slashes are sanitized cleanly."""
    student = grading_db.query(User).filter(User.id == 2).first()
    student.identifier = "NISN/2026:TEST#01 "
    grading_db.commit()

    with patch("app.services.grading.background_worker.SessionLocal", return_value=grading_db), \
         patch("app.services.grading.background_worker.send_exam_result_email", new_callable=AsyncMock) as mock_send_email:
        mock_send_email.return_value = {"id": "msg_1", "mock": False}

        grade_exam_session_async(1001)

        mock_send_email.assert_called_once()
        filename = mock_send_email.call_args[1]["pdf_filename"]
        assert filename == "hasil-ujian-10-NISN_2026_TEST_01.pdf"
        assert "/" not in filename
        assert ":" not in filename
        assert "#" not in filename
