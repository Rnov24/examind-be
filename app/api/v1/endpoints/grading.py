from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session, joinedload, selectinload
from app.core.database import get_db
from app.core.exceptions import AppException
from app.core.dependencies import require_teacher
from app.core.timing import log_query_timing
from app.models.user import User
from app.models.exam import Exam, ExamQuestion
from app.models.session import ExamSession, StudentAnswer
from app.models.question import Question
from app.schemas.session import StudentExamResultResponse, StudentAnswerDetail
from app.schemas.common import ApiResponse, PaginatedResponse

router = APIRouter(prefix="/grading", tags=["AI Essay Grading & Teacher Override"])


class GradeOverrideRequest(BaseModel):
    teacher_override_score: float
    teacher_notes: Optional[str] = None


class SessionGradingSummary(BaseModel):
    session_id: int
    exam_id: int
    student_id: int
    student_name: str
    student_identifier: str
    status: str
    total_score: float
    integrity_score: int
    lowest_confidence_level: str
    needs_review: bool
    submit_time: Optional[datetime] = None


@router.get("/exam/{exam_id}/sessions", response_model=PaginatedResponse[SessionGradingSummary])
def list_exam_sessions_for_grading(
    exam_id: int,
    page: int = Query(1, ge=1, description="Nomor halaman"),
    page_size: int = Query(20, ge=1, le=100, description="Jumlah data per halaman"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    with log_query_timing("list_exam_sessions_for_grading"):
        query = (
            db.query(ExamSession)
            .filter(ExamSession.exam_id == exam_id)
        )
        total = query.count()
        sessions = (
            query.options(joinedload(ExamSession.student))
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )

        session_ids = [s.id for s in sessions]
        confidence_map = {}
        if session_ids:
            answers = (
                db.query(StudentAnswer.session_id, StudentAnswer.ai_confidence_level)
                .filter(
                    StudentAnswer.session_id.in_(session_ids),
                    StudentAnswer.ai_confidence_level.isnot(None),
                )
                .all()
            )
            for sid, conf in answers:
                confidence_map.setdefault(sid, []).append(conf)

        results = []
        for s in sessions:
            confidences = confidence_map.get(s.id, [])

            if "low" in confidences:
                lowest_conf = "low"
                needs_review = True
            elif "medium" in confidences:
                lowest_conf = "medium"
                needs_review = False
            else:
                lowest_conf = "high"
                needs_review = False

            results.append(
                SessionGradingSummary(
                    session_id=s.id,
                    exam_id=s.exam_id,
                    student_id=s.student_id,
                    student_name=s.student.full_name if s.student else "Siswa",
                    student_identifier=s.student.identifier if s.student else "-",
                    status=s.status,
                    total_score=float(s.total_score or 0.0),
                    integrity_score=s.integrity_score,
                    lowest_confidence_level=lowest_conf,
                    needs_review=needs_review,
                    submit_time=s.submit_time,
                )
            )

        # Sort so sessions needing review (low confidence) appear at the top
        results.sort(key=lambda x: (not x.needs_review, x.lowest_confidence_level != "low"))

        return PaginatedResponse.ok(
            data=results,
            page=page,
            page_size=page_size,
            total=total,
            message="Daftar sesi penilaian ujian berhasil dimuat",
        )


@router.get("/session/{session_id}", response_model=ApiResponse[StudentExamResultResponse])
def get_session_grading_detail(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    session = db.query(ExamSession).filter(ExamSession.id == session_id).first()
    if not session:
        raise AppException(
            message="Sesi tidak ditemukan.",
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="SESSION_NOT_FOUND",
        )

    exam = (
        db.query(Exam)
        .options(selectinload(Exam.exam_questions).selectinload(ExamQuestion.question))
        .filter(Exam.id == session.exam_id)
        .first()
    )
    if not exam:
        raise AppException(
            message="Paket ujian tidak ditemukan.",
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="EXAM_NOT_FOUND",
        )
    answers_detail = []
    max_score = 0.0

    # One query for all answers in this session (no per-question N+1).
    answers_by_question = {
        a.question_id: a
        for a in db.query(StudentAnswer)
        .filter(StudentAnswer.session_id == session.id)
        .all()
    }

    for eq in exam.exam_questions:
        q = eq.question
        if not q:
            continue
        pts = float(eq.allocated_points)
        max_score += pts

        ans = answers_by_question.get(q.id)

        answers_detail.append(
            StudentAnswerDetail(
                id=ans.id if ans else 0,
                question_id=q.id,
                question_type=q.question_type,
                prompt=q.prompt,
                options_json=q.options_json,
                correct_answer=q.correct_answer,
                student_response=ans.student_response if ans else None,
                is_correct=ans.is_correct if ans else None,
                allocated_points=pts,
                auto_score=float(ans.auto_score or 0.0) if ans else 0.0,
                teacher_override_score=float(ans.teacher_override_score) if ans and ans.teacher_override_score is not None else None,
                final_score=float(ans.final_score or 0.0) if ans else 0.0,
                ai_confidence_level=ans.ai_confidence_level if ans else None,
                ai_grading_rationale=ans.ai_grading_rationale if ans else None,
                ai_explanation=ans.ai_explanation if ans else None,
                teacher_notes=ans.teacher_notes if ans else None,
                rubric_json=q.rubric_json,
            )
        )

    res = StudentExamResultResponse(
        session_id=session.id,
        exam_id=exam.id,
        exam_title=exam.title,
        subject=exam.class_.name if exam.class_ else "Ujian",
        student_name=session.student.full_name if session.student else "Siswa",
        student_identifier=session.student.identifier if session.student else "-",
        status=session.status,
        start_time=session.start_time,
        submit_time=session.submit_time,
        total_score=float(session.total_score or 0.0),
        max_score=max_score,
        integrity_score=session.integrity_score,
        explanation_policy=exam.explanation_policy,
        answers=answers_detail,
    )
    return ApiResponse.ok(data=res, message="Detail lembar jawaban siswa berhasil dimuat")


@router.put("/answer/{answer_id}/override", response_model=ApiResponse[dict])
def override_answer_score(
    answer_id: int,
    request: GradeOverrideRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    ans = db.query(StudentAnswer).filter(StudentAnswer.id == answer_id).first()
    if not ans:
        raise AppException(
            message="Jawaban siswa tidak ditemukan.",
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="ANSWER_NOT_FOUND",
        )

    ans.teacher_override_score = request.teacher_override_score
    ans.final_score = request.teacher_override_score
    if request.teacher_notes is not None:
        ans.teacher_notes = request.teacher_notes
    ans.graded_at = datetime.utcnow()

    # Recalculate session total score
    session = ans.session
    all_answers = db.query(StudentAnswer).filter(StudentAnswer.session_id == session.id).all()
    total_score = sum([float(a.final_score or 0.0) for a in all_answers])
    session.total_score = round(total_score, 2)
    session.status = "graded"

    db.commit()

    return ApiResponse.ok(
        data={"answer_id": ans.id, "new_final_score": float(ans.final_score), "session_total": float(session.total_score)},
        message="Nilai berhasil dioverride oleh guru",
    )
