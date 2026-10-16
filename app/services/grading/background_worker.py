import json
from datetime import datetime
from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.models.session import ExamSession, StudentAnswer
from app.models.exam import ExamQuestion
from app.models.question import Question
from app.services.ai import get_ai_service
from app.services.grading.confidence_calculator import calculate_ai_confidence


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
    except Exception as exc:
        print(f"[GradingWorker] Error grading session {session_id}: {exc}")
        db.rollback()
    finally:
        db.close()
