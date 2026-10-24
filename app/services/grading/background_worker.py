import asyncio
import json
import logging
import re
from datetime import datetime
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.database import SessionLocal
from app.models.session import ExamSession, StudentAnswer
from app.models.exam import ExamQuestion
from app.models.question import Question
from app.services.ai import get_ai_service
from app.services.grading.confidence_calculator import calculate_ai_confidence
from app.services.email.resend_service import send_exam_result_email
from app.services.reporting.pdf_exporter import generate_pdf_student_result

logger = logging.getLogger("examind.grading")


def _run_coroutine_safely(coro):
    """Run an async coroutine from synchronous or threaded context."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()
    else:
        return asyncio.run(coro)


def _send_result_email_safe(db: Session, session: ExamSession, answers: list[StudentAnswer]):
    """Safely generate PDF result and email it to the student.

    Grading result has already been committed; this function must NEVER raise or break grading.
    """
    try:
        if not getattr(settings, "EXAM_RESULT_EMAIL_ENABLED", True):
            logger.info(f"[GradingWorker] EXAM_RESULT_EMAIL_ENABLED is False; skipping result email for session {session.id}.")
            return

        student = session.student
        student_email = (student.email or "").strip() if student and student.email else ""
        if not student_email:
            # Skip silently if the student has no email address
            logger.info(f"[GradingWorker] Session {session.id}: Student has no email address; skipping result email.")
            return

        # 1. Generate PDF
        pdf_buffer = generate_pdf_student_result(db, session.id)
        pdf_bytes = pdf_buffer.getvalue() if hasattr(pdf_buffer, "getvalue") else pdf_buffer.read()
        if not pdf_bytes:
            logger.warning(f"[GradingWorker] Session {session.id}: Generated PDF buffer is empty.")
            return

        # 2. Sanitize filename: hasil-ujian-{exam_id}-{student_identifier}.pdf
        exam_id_raw = session.exam_id
        student_id_raw = student.identifier if (student and student.identifier) else session.student_id
        safe_exam_id = re.sub(r"[^a-zA-Z0-9_\-]", "_", str(exam_id_raw).strip()) or "exam"
        safe_student_id = re.sub(r"[^a-zA-Z0-9_\-]", "_", str(student_id_raw).strip()) or "student"
        pdf_filename = f"hasil-ujian-{safe_exam_id}-{safe_student_id}.pdf"

        # 3. Calculate MCQ counts & grade predicate
        mcq_correct = 0
        mcq_wrong = 0
        mcq_unanswered = 0
        for ans in answers:
            q = ans.question
            if q and getattr(q, "question_type", None) == "multiple_choice":
                resp = (ans.student_response or "").strip()
                if not resp:
                    mcq_unanswered += 1
                elif ans.is_correct:
                    mcq_correct += 1
                else:
                    mcq_wrong += 1

        total_score = float(session.total_score or 0.0)
        is_aborted = session.status == "aborted"
        grade_predicate = "Gugur" if is_aborted else ("Tuntas (KKM)" if total_score >= 75.0 else "Belum Tuntas")

        exam_title = session.exam.title if session.exam and session.exam.title else "Ujian"
        student_name = student.full_name if student and student.full_name else "Siswa"

        # 4. Dispatch email via Resend
        email_result = _run_coroutine_safely(
            send_exam_result_email(
                to_email=student_email,
                student_name=student_name,
                exam_title=exam_title,
                score=total_score,
                pdf_bytes=pdf_bytes,
                pdf_filename=pdf_filename,
                grade_predicate=grade_predicate,
                summary_counts={
                    "correct": mcq_correct,
                    "wrong": mcq_wrong,
                    "unanswered": mcq_unanswered,
                },
            )
        )

        # 5. Production mock guard pattern
        if (email_result or {}).get("mock") and getattr(settings, "ENVIRONMENT", "").lower() == "production":
            logger.warning(
                f"[GradingWorker] Session {session.id}: Email service returned mock in production environment. "
                "Result email delivery skipped."
            )
            return

        logger.info(f"[GradingWorker] Successfully dispatched result email for session {session.id} to {student_email}.")
    except Exception as exc:
        logger.error(f"[GradingWorker] Failed to dispatch result email for session {session.id}: {exc}", exc_info=True)


def grade_exam_session_async(session_id: int):
    """Background task executed after student submission.

    Evaluates all essay questions asynchronously.
    """
    db: Session = SessionLocal()
    try:
        session = db.query(ExamSession).filter(ExamSession.id == session_id).first()
        if not session:
            return

        ai_service = get_ai_service()

        answers = db.query(StudentAnswer).filter(StudentAnswer.session_id == session_id).all()
        total_session_score = 0.0

        for ans in answers:
            q: Question = ans.question
            if not q:
                continue

            eq = (
                db.query(ExamQuestion)
                .filter(ExamQuestion.exam_id == session.exam_id, ExamQuestion.question_id == q.id)
                .first()
            )
            allocated_points = float(eq.allocated_points) if eq else float(q.default_points)

            if q.question_type == "multiple_choice":
                # Already scored in instant evaluator
                total_session_score += float(ans.final_score or 0.0)
                # Generate formative explanation if not yet generated
                if not ans.ai_explanation:
                    ans.ai_explanation = ai_service.generate_explanation(
                        prompt=q.prompt,
                        correct_answer=q.correct_answer or "",
                        student_response=ans.student_response or "",
                        is_correct=bool(ans.is_correct),
                    )
            else:
                # Essay evaluation
                student_resp = ans.student_response or ""
                rubric = q.rubric_json if isinstance(q.rubric_json, dict) else {}
                ideal = q.correct_answer or ""

                grading_res = ai_service.grade_essay(
                    prompt=q.prompt,
                    rubric=rubric,
                    ideal_answer=ideal,
                    student_answer=student_resp,
                    allocated_points=allocated_points,
                )

                # Normalized essay score mapped to allocated points
                pct_score = grading_res.get("total_score", 0.0) / 100.0
                computed_score = round(pct_score * allocated_points, 2)

                ans.auto_score = computed_score
                if ans.teacher_override_score is None:
                    ans.final_score = computed_score

                ans.ai_confidence_level = grading_res.get("confidence_level", "medium")
                ans.ai_grading_rationale = grading_res.get("rationale")
                ans.ai_explanation = grading_res.get("explanation")
                ans.graded_at = datetime.utcnow()

                total_session_score += float(ans.final_score or 0.0)

        session.total_score = round(total_session_score, 2)
        session.status = "graded"
        db.commit()

        # Safely attempt sending the result PDF email (never raises or affects grading)
        _send_result_email_safe(db, session, answers)
    except Exception as exc:
        logger.error(f"[GradingWorker] Error grading session {session_id}: {exc}", exc_info=True)
        db.rollback()
    finally:
        db.close()
