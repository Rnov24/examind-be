from typing import Dict, Any, List
from sqlalchemy.orm import Session
from app.models.session import ExamSession, StudentAnswer
from app.models.exam import ExamQuestion
from app.models.question import Question


def evaluate_instant_mcq(
    db: Session,
    session: ExamSession,
    submitted_answers: Dict[int, str],
) -> float:
    """Instantly grades all MCQ items in O(N) time and creates/updates StudentAnswer rows.

    Returns the accumulated score from MCQs.
    """
    exam_questions = (
        db.query(ExamQuestion)
        .filter(ExamQuestion.exam_id == session.exam_id)
        .all()
    )

    total_mcq_score = 0.0

    for eq in exam_questions:
        q: Question = eq.question
        if not q:
            continue

        resp = submitted_answers.get(q.id)

        # Check existing answer record
        ans_record = (
            db.query(StudentAnswer)
            .filter(StudentAnswer.session_id == session.id, StudentAnswer.question_id == q.id)
            .first()
        )
        if not ans_record:
            ans_record = StudentAnswer(
                session_id=session.id,
                question_id=q.id,
            )
            db.add(ans_record)

        ans_record.student_response = resp

        if q.question_type == "multiple_choice":
            allocated = float(eq.allocated_points)
            is_correct = (
                resp is not None
                and q.correct_answer is not None
                and resp.strip().upper() == q.correct_answer.strip().upper()
            )
            ans_record.is_correct = is_correct
            score = allocated if is_correct else 0.0
            ans_record.auto_score = score
            ans_record.final_score = score
            ans_record.ai_confidence_level = "high"
            ans_record.ai_grading_rationale = (
                f"Jawaban siswa '{resp}' {'cocok' if is_correct else 'tidak cocok'} dengan kunci '{q.correct_answer}'."
            )
            total_mcq_score += score
        else:
            # Essay is deferred to background worker
            ans_record.is_correct = None
            ans_record.auto_score = 0.0
            ans_record.final_score = 0.0
            ans_record.ai_confidence_level = "medium"

    db.commit()
    return total_mcq_score
