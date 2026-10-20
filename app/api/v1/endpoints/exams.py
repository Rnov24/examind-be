from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session, joinedload, selectinload
from app.core.database import get_db
from app.core.exceptions import AppException
from app.core.dependencies import get_current_active_user, require_teacher
from app.core.timing import log_query_timing
from app.models.user import User
from app.models.academic import Class, ClassMember
from app.models.exam import Exam, ExamQuestion
from app.models.question import Question
from app.schemas.exam import (
    ExamCreate,
    ExamUpdate,
    ExamResponse,
    ExamDetailResponse,
    ExamQuestionItem,
    ExamQuestionResponse,
)
from app.schemas.question import QuestionResponse
from app.schemas.common import ApiResponse, PaginatedResponse

router = APIRouter(prefix="/exams", tags=["Exam Management & Publishing"])


def build_exam_response(
    exam: Exam,
    teacher_name: Optional[str] = None,
    class_name: Optional[str] = None,
    total_points: Optional[float] = None,
) -> ExamResponse:
    pts = total_points if total_points is not None else sum(float(eq.allocated_points) for eq in exam.exam_questions)
    return ExamResponse(
        id=exam.id,
        teacher_id=exam.teacher_id,
        class_id=exam.class_id,
        title=exam.title,
        description=exam.description,
        duration_minutes=exam.duration_minutes,
        start_time=exam.start_time,
        end_time=exam.end_time,
        randomize_questions=exam.randomize_questions,
        randomize_options=exam.randomize_options,
        proctoring_level=exam.proctoring_level,
        explanation_policy=exam.explanation_policy,
        status=exam.status,
        created_at=exam.created_at,
        questions_count=len(exam.exam_questions),
        total_points=pts,
        teacher_name=teacher_name or (exam.teacher.full_name if exam.teacher else None),
        class_name=class_name or (exam.class_.name if exam.class_ else None),
    )


@router.get("", response_model=PaginatedResponse[ExamResponse])
def list_exams(
    page: int = Query(1, ge=1, description="Nomor halaman"),
    page_size: int = Query(20, ge=1, le=100, description="Jumlah data per halaman"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    with log_query_timing("list_exams"):
        if current_user.role == "admin":
            query = db.query(Exam)
        elif current_user.role == "teacher":
            query = db.query(Exam).filter(Exam.teacher_id == current_user.id)
        else:  # student
            class_ids = [m.class_id for m in db.query(ClassMember).filter(ClassMember.user_id == current_user.id).all()]
            if not class_ids:
                return PaginatedResponse.ok(
                    data=[],
                    page=page,
                    page_size=page_size,
                    total=0,
                    message="Daftar paket ujian berhasil dimuat",
                )
            query = db.query(Exam).filter(Exam.class_id.in_(class_ids), Exam.status.in_(["published", "in_progress", "completed"]))

        total = query.count()
        exams = (
            query.options(
                joinedload(Exam.teacher),
                joinedload(Exam.class_),
                selectinload(Exam.exam_questions),
            )
            .order_by(Exam.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )

        results = [build_exam_response(e) for e in exams]
        return PaginatedResponse.ok(
            data=results,
            page=page,
            page_size=page_size,
            total=total,
            message="Daftar paket ujian berhasil dimuat",
        )


@router.post("", response_model=ApiResponse[ExamResponse])
def create_exam(
    request: ExamCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    # Validation: end_time > start_time
    if request.end_time <= request.start_time:
        raise AppException(
            message="Waktu berakhir ujian (end_time) harus lebih besar dari waktu mulai (start_time).",
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="INVALID_TIME_RANGE",
        )

    cls = db.query(Class).filter(Class.id == request.class_id).first()
    if not cls:
        raise AppException(
            message="Kelas target tidak ditemukan.",
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="CLASS_NOT_FOUND",
        )

    exam = Exam(
        teacher_id=current_user.id,
        class_id=request.class_id,
        title=request.title,
        description=request.description,
        duration_minutes=request.duration_minutes,
        start_time=request.start_time,
        end_time=request.end_time,
        randomize_questions=request.randomize_questions,
        randomize_options=request.randomize_options,
        proctoring_level=request.proctoring_level,
        explanation_policy=request.explanation_policy,
        status="draft",
    )
    db.add(exam)
    db.commit()
    db.refresh(exam)

    # Attach questions if provided
    total_pts = 0.0
    if request.questions:
        for idx, q_item in enumerate(request.questions, start=1):
            eq = ExamQuestion(
                exam_id=exam.id,
                question_id=q_item.question_id,
                order_index=q_item.order_index or idx,
                allocated_points=q_item.allocated_points,
            )
            db.add(eq)
            total_pts += float(q_item.allocated_points)
        db.commit()
        db.refresh(exam)

    res = build_exam_response(exam, teacher_name=current_user.full_name, class_name=cls.name, total_points=total_pts)
    return ApiResponse.ok(data=res, message="Paket ujian berhasil dibuat")


@router.get("/{exam_id}", response_model=ApiResponse[ExamDetailResponse])
def get_exam_detail(
    exam_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    exam = (
        db.query(Exam)
        .options(selectinload(Exam.exam_questions).selectinload(ExamQuestion.question))
        .filter(Exam.id == exam_id)
        .first()
    )
    if not exam:
        raise AppException(
            message="Paket ujian tidak ditemukan.",
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="EXAM_NOT_FOUND",
        )

    eq_list = []
    total_pts = 0.0
    for eq in exam.exam_questions:
        q_res = None
        if eq.question:
            q_res = QuestionResponse.model_validate(eq.question)
            if current_user.role == "student":
                q_res.correct_answer = None
                q_res.rubric_json = None
                q_res.explanation = None

        pts = float(eq.allocated_points)
        total_pts += pts
        eq_list.append(
            ExamQuestionResponse(
                id=eq.id,
                exam_id=eq.exam_id,
                question_id=eq.question_id,
                order_index=eq.order_index,
                allocated_points=pts,
                question=q_res,
            )
        )

    base_res = build_exam_response(exam, total_points=total_pts)
    res = ExamDetailResponse(
        **base_res.model_dump(),
        exam_questions=eq_list,
    )
    return ApiResponse.ok(data=res, message="Detail paket ujian berhasil dimuat")


@router.put("/{exam_id}", response_model=ApiResponse[ExamResponse])
def update_exam(
    exam_id: int,
    request: ExamUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam:
        raise AppException(
            message="Paket ujian tidak ditemukan.",
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="EXAM_NOT_FOUND",
        )

    if request.title is not None:
        exam.title = request.title
    if request.description is not None:
        exam.description = request.description
    if request.class_id is not None:
        exam.class_id = request.class_id
    if request.duration_minutes is not None:
        exam.duration_minutes = request.duration_minutes
    if request.start_time is not None:
        exam.start_time = request.start_time
    if request.end_time is not None:
        exam.end_time = request.end_time
    if request.randomize_questions is not None:
        exam.randomize_questions = request.randomize_questions
    if request.randomize_options is not None:
        exam.randomize_options = request.randomize_options
    if request.proctoring_level is not None:
        exam.proctoring_level = request.proctoring_level
    if request.explanation_policy is not None:
        exam.explanation_policy = request.explanation_policy
    if request.status is not None:
        exam.status = request.status

    db.commit()
    db.refresh(exam)

    total_pts = sum([float(eq.allocated_points) for eq in exam.exam_questions])
    res = ExamResponse(
        id=exam.id,
        teacher_id=exam.teacher_id,
        class_id=exam.class_id,
        title=exam.title,
        description=exam.description,
        duration_minutes=exam.duration_minutes,
        start_time=exam.start_time,
        end_time=exam.end_time,
        randomize_questions=exam.randomize_questions,
        randomize_options=exam.randomize_options,
        proctoring_level=exam.proctoring_level,
        explanation_policy=exam.explanation_policy,
        status=exam.status,
        created_at=exam.created_at,
        questions_count=len(exam.exam_questions),
        total_points=total_pts,
        teacher_name=exam.teacher.full_name if exam.teacher else None,
        class_name=exam.class_.name if exam.class_ else None,
    )
    return ApiResponse.ok(data=res, message="Paket ujian berhasil diperbarui")


@router.post("/{exam_id}/publish", response_model=ApiResponse[ExamResponse])
def publish_exam(
    exam_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam:
        raise AppException(
            message="Paket ujian tidak ditemukan.",
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="EXAM_NOT_FOUND",
        )

    if not exam.exam_questions:
        raise AppException(
            message="Paket ujian harus memiliki minimal satu butir soal sebelum dapat dipublikasikan.",
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="EMPTY_EXAM",
        )

    exam.status = "published"
    db.commit()
    db.refresh(exam)

    res = build_exam_response(exam)
    return ApiResponse.ok(data=res, message="Paket ujian berhasil dipublikasikan untuk kelas target")


@router.post("/{exam_id}/questions", response_model=ApiResponse[ExamQuestionResponse])
def add_question_to_exam(
    exam_id: int,
    request: ExamQuestionItem,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam:
        raise AppException(
            message="Paket ujian tidak ditemukan.",
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="EXAM_NOT_FOUND",
        )

    question = db.query(Question).filter(Question.id == request.question_id).first()
    if not question:
        raise AppException(
            message="Butir soal tidak ditemukan.",
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="QUESTION_NOT_FOUND",
        )

    existing = (
        db.query(ExamQuestion)
        .filter(ExamQuestion.exam_id == exam_id, ExamQuestion.question_id == request.question_id)
        .first()
    )
    if existing:
        raise AppException(
            message="Butir soal ini sudah terdaftar di dalam paket ujian.",
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="DUPLICATE_QUESTION",
        )

    eq = ExamQuestion(
        exam_id=exam_id,
        question_id=request.question_id,
        order_index=request.order_index,
        allocated_points=request.allocated_points,
    )
    db.add(eq)
    db.commit()
    db.refresh(eq)

    q_res = QuestionResponse.model_validate(question)
    res = ExamQuestionResponse(
        id=eq.id,
        exam_id=eq.exam_id,
        question_id=eq.question_id,
        order_index=eq.order_index,
        allocated_points=float(eq.allocated_points),
        question=q_res,
    )
    return ApiResponse.ok(data=res, message="Soal berhasil ditambahkan ke paket ujian")


@router.delete("/{exam_id}/questions/{question_id}", response_model=ApiResponse[dict])
def remove_question_from_exam(
    exam_id: int,
    question_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    eq = (
        db.query(ExamQuestion)
        .filter(ExamQuestion.exam_id == exam_id, ExamQuestion.question_id == question_id)
        .first()
    )
    if not eq:
        raise AppException(
            message="Alokasi soal tidak ditemukan di ujian ini.",
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="EXAM_QUESTION_NOT_FOUND",
        )

    db.delete(eq)
    db.commit()
    return ApiResponse.ok(data={"removed_question_id": question_id}, message="Soal berhasil dihapus dari paket ujian")
