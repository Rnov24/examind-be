from typing import List, Optional
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.exceptions import AppException
from app.core.dependencies import get_current_active_user, require_teacher
from app.models.user import User
from app.models.question import QuestionBank, Question
from app.schemas.question import (
    QuestionBankCreate,
    QuestionBankUpdate,
    QuestionBankResponse,
    QuestionBankDetailResponse,
    QuestionCreate,
    QuestionUpdate,
    QuestionResponse,
)
from app.schemas.common import ApiResponse

router = APIRouter(prefix="/questions", tags=["Question Bank & Items"])


# --- Question Bank Endpoints ---

@router.get("/banks", response_model=ApiResponse[List[QuestionBankResponse]])
def list_question_banks(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    if current_user.role == "admin":
        banks = db.query(QuestionBank).all()
    else:
        banks = db.query(QuestionBank).filter(QuestionBank.teacher_id == current_user.id).all()

    results = []
    for b in banks:
        res = QuestionBankResponse(
            id=b.id,
            teacher_id=b.teacher_id,
            title=b.title,
            subject=b.subject,
            description=b.description,
            created_at=b.created_at,
            questions_count=len(b.questions),
        )
        results.append(res)

    return ApiResponse.ok(data=results, message="Daftar bank soal berhasil dimuat")


@router.post("/banks", response_model=ApiResponse[QuestionBankResponse])
def create_question_bank(
    request: QuestionBankCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    bank = QuestionBank(
        teacher_id=current_user.id,
        title=request.title,
        subject=request.subject,
        description=request.description,
    )
    db.add(bank)
    db.commit()
    db.refresh(bank)

    res = QuestionBankResponse(
        id=bank.id,
        teacher_id=bank.teacher_id,
        title=bank.title,
        subject=bank.subject,
        description=bank.description,
        created_at=bank.created_at,
        questions_count=0,
    )
    return ApiResponse.ok(data=res, message="Bank soal berhasil dibuat")


@router.get("/banks/{bank_id}", response_model=ApiResponse[QuestionBankDetailResponse])
def get_question_bank_detail(
    bank_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    bank = db.query(QuestionBank).filter(QuestionBank.id == bank_id).first()
    if not bank:
        raise AppException(
            message="Bank soal tidak ditemukan.",
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="BANK_NOT_FOUND",
        )

    res = QuestionBankDetailResponse(
        id=bank.id,
        teacher_id=bank.teacher_id,
        title=bank.title,
        subject=bank.subject,
        description=bank.description,
        created_at=bank.created_at,
        questions_count=len(bank.questions),
        questions=[QuestionResponse.model_validate(q) for q in bank.questions],
    )
    return ApiResponse.ok(data=res, message="Detail bank soal berhasil dimuat")


@router.put("/banks/{bank_id}", response_model=ApiResponse[QuestionBankResponse])
def update_question_bank(
    bank_id: int,
    request: QuestionBankUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    bank = db.query(QuestionBank).filter(QuestionBank.id == bank_id).first()
    if not bank:
        raise AppException(
            message="Bank soal tidak ditemukan.",
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="BANK_NOT_FOUND",
        )

    if current_user.role != "admin" and bank.teacher_id != current_user.id:
        raise AppException(
            message="Anda tidak berhak mengubah bank soal ini.",
            status_code=status.HTTP_403_FORBIDDEN,
            error_code="FORBIDDEN",
        )

    if request.title is not None:
        bank.title = request.title
    if request.subject is not None:
        bank.subject = request.subject
    if request.description is not None:
        bank.description = request.description

    db.commit()
    db.refresh(bank)

    res = QuestionBankResponse(
        id=bank.id,
        teacher_id=bank.teacher_id,
        title=bank.title,
        subject=bank.subject,
        description=bank.description,
        created_at=bank.created_at,
        questions_count=len(bank.questions),
    )
    return ApiResponse.ok(data=res, message="Bank soal berhasil diperbarui")


@router.delete("/banks/{bank_id}", response_model=ApiResponse[dict])
def delete_question_bank(
    bank_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    bank = db.query(QuestionBank).filter(QuestionBank.id == bank_id).first()
    if not bank:
        raise AppException(
            message="Bank soal tidak ditemukan.",
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="BANK_NOT_FOUND",
        )

    if current_user.role != "admin" and bank.teacher_id != current_user.id:
        raise AppException(
            message="Anda tidak berhak menghapus bank soal ini.",
            status_code=status.HTTP_403_FORBIDDEN,
            error_code="FORBIDDEN",
        )

    db.delete(bank)
    db.commit()
    return ApiResponse.ok(data={"deleted_bank_id": bank_id}, message="Bank soal berhasil dihapus")


# --- Question Items Endpoints ---

@router.post("/banks/{bank_id}/items", response_model=ApiResponse[QuestionResponse])
def add_question_item(
    bank_id: int,
    request: QuestionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    bank = db.query(QuestionBank).filter(QuestionBank.id == bank_id).first()
    if not bank:
        raise AppException(
            message="Bank soal tidak ditemukan.",
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="BANK_NOT_FOUND",
        )

    # Convert Pydantic schemas to serializable JSON dicts if needed
    options_data = None
    if request.options_json:
        options_data = [
            opt.model_dump() if hasattr(opt, "model_dump") else opt
            for opt in request.options_json
        ]

    rubric_data = None
    if request.rubric_json:
        rubric_data = (
            request.rubric_json.model_dump()
            if hasattr(request.rubric_json, "model_dump")
            else request.rubric_json
        )

    question = Question(
        bank_id=bank_id,
        question_type=request.question_type,
        prompt=request.prompt,
        options_json=options_data,
        correct_answer=request.correct_answer,
        rubric_json=rubric_data,
        explanation=request.explanation,
        difficulty=request.difficulty,
        default_points=request.default_points,
    )
    db.add(question)
    db.commit()
    db.refresh(question)

    res = QuestionResponse.model_validate(question)
    return ApiResponse.ok(data=res, message="Butir soal berhasil ditambahkan ke bank soal")


@router.put("/items/{question_id}", response_model=ApiResponse[QuestionResponse])
def update_question_item(
    question_id: int,
    request: QuestionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    question = db.query(Question).filter(Question.id == question_id).first()
    if not question:
        raise AppException(
            message="Butir soal tidak ditemukan.",
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="QUESTION_NOT_FOUND",
        )

    if request.question_type is not None:
        question.question_type = request.question_type
    if request.prompt is not None:
        question.prompt = request.prompt
    if request.options_json is not None:
        question.options_json = [
            opt.model_dump() if hasattr(opt, "model_dump") else opt
            for opt in request.options_json
        ]
    if request.correct_answer is not None:
        question.correct_answer = request.correct_answer
    if request.rubric_json is not None:
        question.rubric_json = (
            request.rubric_json.model_dump()
            if hasattr(request.rubric_json, "model_dump")
            else request.rubric_json
        )
    if request.explanation is not None:
        question.explanation = request.explanation
    if request.difficulty is not None:
        question.difficulty = request.difficulty
    if request.default_points is not None:
        question.default_points = request.default_points

    db.commit()
    db.refresh(question)

    res = QuestionResponse.model_validate(question)
    return ApiResponse.ok(data=res, message="Butir soal berhasil diperbarui")


@router.delete("/items/{question_id}", response_model=ApiResponse[dict])
def delete_question_item(
    question_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    question = db.query(Question).filter(Question.id == question_id).first()
    if not question:
        raise AppException(
            message="Butir soal tidak ditemukan.",
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="QUESTION_NOT_FOUND",
        )

    db.delete(question)
    db.commit()
    return ApiResponse.ok(data={"deleted_question_id": question_id}, message="Butir soal berhasil dihapus")
