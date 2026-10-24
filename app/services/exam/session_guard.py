import uuid
from datetime import datetime
from typing import Tuple
from sqlalchemy.orm import Session
from app.models.exam import Exam
from app.models.session import ExamSession
from app.core.exceptions import AppException
from fastapi import status


def generate_pairing_token(session_id: int) -> str:
    """Generates unique UUID token for mobile companion QR pairing."""
    return str(uuid.uuid4())


def get_or_create_exam_session(
    db: Session,
    exam: Exam,
    student_id: int,
    client_ip: str = None,
    user_agent: str = None,
) -> Tuple[ExamSession, bool, str]:
    """Retrieves active session or creates a new one, validating time and state.

    Returns: (session, is_new, pairing_token)
    """
    now = datetime.utcnow()

    # Time validation: exam must be active and published
    if exam.status not in ["published", "in_progress"]:
        raise AppException(
            message=f"Ujian ini belum dipublikasikan atau sudah ditutup (Status: {exam.status}).",
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="EXAM_NOT_ACTIVE",
        )

    # Mode-aware window gating. Applies to NEW sessions only — a student
    # resuming an existing session is never locked out by a moved window.
    mode = getattr(exam, "exam_mode", None) or "live"
    existing = (
        db.query(ExamSession)
        .filter(ExamSession.exam_id == exam.id, ExamSession.student_id == student_id)
        .first()
    )
    if existing is None:
        if now < exam.start_time:
            # Neither mode may start before the window opens. Live adds the
            # simultaneous-start rule (everyone at the same fixed time).
            if mode == "live":
                raise AppException(
                    message=(
                        "Ujian live belum dimulai. Semua siswa mulai serentak pada "
                        f"{exam.start_time.strftime('%d %b %Y %H:%M')} WIB."
                    ),
                    status_code=status.HTTP_400_BAD_REQUEST,
                    error_code="EXAM_NOT_STARTED",
                )
            raise AppException(
                message=(
                    "Jendela pengerjaan belum dibuka. Ujian mandiri ini bisa "
                    f"dikerjakan mulai {exam.start_time.strftime('%d %b %Y %H:%M')} WIB."
                ),
                status_code=status.HTTP_400_BAD_REQUEST,
                error_code="EXAM_NOT_STARTED",
            )
        if now > exam.end_time:
            # Both modes: no new session after the window closes.
            raise AppException(
                message=(
                    "Jendela pengerjaan ujian sudah ditutup "
                    f"({exam.end_time.strftime('%d %b %Y %H:%M')} WIB)."
                ),
                status_code=status.HTTP_400_BAD_REQUEST,
                error_code="EXAM_ENDED",
            )

    if existing:
        if existing.status == "aborted":
            raise AppException(
                message="Sesi ujian Anda telah didiskualifikasi (dibatalkan) karena pelanggaran protokol keamanan.",
                status_code=status.HTTP_403_FORBIDDEN,
                error_code="EXAM_DISQUALIFIED",
            )
        if existing.status in ["submitted", "grading_in_progress", "graded"]:
            raise AppException(
                message="Sesi ujian ini telah dikumpulkan dan tidak dapat dimulai kembali.",
                status_code=status.HTTP_400_BAD_REQUEST,
                error_code="EXAM_ALREADY_SUBMITTED",
            )
        # Reuse the persisted pairing token so the QR shown earlier in the
        # session stays valid; legacy sessions without one get one minted.
        token = existing.pairing_token or generate_pairing_token(existing.id)
        if not existing.pairing_token:
            existing.pairing_token = token
            db.commit()
        return existing, False, token

    # Create new session: mint and PERSIST the pairing token so the
    # companion WebSocket can validate it later.
    token = generate_pairing_token(0)
    session = ExamSession(
        exam_id=exam.id,
        student_id=student_id,
        start_time=now,
        status="in_progress",
        total_score=0.00,
        integrity_score=100,
        companion_paired=False,
        pairing_token=token,
        client_ip=client_ip,
        user_agent=user_agent,
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    return session, True, token
