import time
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import text
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.core.database import get_db
from app.core.exceptions import AppException
from app.core.dependencies import require_admin
from app.core.security import get_password_hash
from app.models.user import User
from app.models.academic import Class
from app.models.question import QuestionBank
from app.models.exam import Exam
from app.models.session import ExamSession
from app.schemas.auth import UserResponse
from app.schemas.common import ApiResponse
from app.services.proctoring.websocket_hub import ws_hub

router = APIRouter(prefix="/admin", tags=["Admin Management"])


class AdminStatsResponse(BaseModel):
    total_users: int
    total_admins: int
    total_teachers: int
    total_students: int
    total_classes: int
    total_question_banks: int
    total_exams: int
    total_sessions: int
    active_sessions: int
    completed_sessions: int
    disqualified_sessions: int
    database_status: str
    edge_cv_status: str


class AdminUserCreate(BaseModel):
    identifier: str
    email: str
    password: str
    full_name: str
    role: str
    avatar_url: Optional[str] = None


@router.get("/stats", response_model=ApiResponse[AdminStatsResponse])
def get_admin_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    # Measure real database round-trip latency
    t0 = time.perf_counter()
    db.execute(text("SELECT 1"))
    latency_ms = (time.perf_counter() - t0) * 1000.0

    users = db.query(User).all()
    total_admins = sum(1 for u in users if u.role == "admin")
    total_teachers = sum(1 for u in users if u.role == "teacher")
    total_students = sum(1 for u in users if u.role == "student")

    total_classes = db.query(Class).count()
    total_banks = db.query(QuestionBank).count()
    total_exams = db.query(Exam).count()

    sessions = db.query(ExamSession).all()
    total_sessions = len(sessions)
    active_sessions = sum(1 for s in sessions if s.status in ["in_progress", "ready"])
    completed_sessions = sum(1 for s in sessions if s.status in ["submitted", "graded"])
    disqualified_sessions = sum(1 for s in sessions if s.status == "disqualified")

    active_cameras = len(ws_hub.companion_streams)

    stats = AdminStatsResponse(
        total_users=len(users),
        total_admins=total_admins,
        total_teachers=total_teachers,
        total_students=total_students,
        total_classes=total_classes,
        total_question_banks=total_banks,
        total_exams=total_exams,
        total_sessions=total_sessions,
        active_sessions=active_sessions,
        completed_sessions=completed_sessions,
        disqualified_sessions=disqualified_sessions,
        database_status=f"Connected ({latency_ms:.0f} ms)",
        edge_cv_status=f"{active_cameras} kamera terhubung",
    )
    return ApiResponse.ok(data=stats, message="Statistik institusi berhasil dimuat")


@router.get("/users", response_model=ApiResponse[List[UserResponse]])
def list_users(
    role: Optional[str] = Query(None, description="Filter role (admin, teacher, student)"),
    search: Optional[str] = Query(None, description="Pencarian nama atau identifier"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    query = db.query(User)
    if role and role != "all":
        query = query.filter(User.role == role)
    if search:
        s = f"%{search}%"
        query = query.filter((User.full_name.ilike(s)) | (User.identifier.ilike(s)) | (User.email.ilike(s)))

    users = query.order_by(User.id.desc()).all()
    results = [UserResponse.model_validate(u) for u in users]
    return ApiResponse.ok(data=results, message="Daftar pengguna berhasil dimuat")


@router.post("/users", response_model=ApiResponse[UserResponse])
def create_user_by_admin(
    payload: AdminUserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    if payload.role not in ["admin", "teacher", "student"]:
        raise AppException(
            message="Role tidak valid. Pilihan: admin, teacher, student.",
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="INVALID_ROLE",
        )

    existing = db.query(User).filter((User.identifier == payload.identifier) | (User.email == payload.email)).first()
    if existing:
        raise AppException(
            message="Identifier atau Email sudah terdaftar dalam sistem.",
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="USER_EXISTS",
        )

    new_user = User(
        identifier=payload.identifier,
        email=payload.email,
        password_hash=get_password_hash(payload.password),
        full_name=payload.full_name,
        role=payload.role,
        avatar_url=payload.avatar_url,
        is_active=True,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return ApiResponse.ok(data=UserResponse.model_validate(new_user), message="Pengguna berhasil dibuat")


@router.patch("/users/{user_id}/toggle-status", response_model=ApiResponse[UserResponse])
def toggle_user_status(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    if user_id == current_user.id:
        raise AppException(
            message="Anda tidak dapat menonaktifkan akun administrator Anda sendiri.",
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="CANNOT_DEACTIVATE_SELF",
        )

    target_user = db.query(User).filter(User.id == user_id).first()
    if not target_user:
        raise AppException(
            message="Pengguna tidak ditemukan.",
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="USER_NOT_FOUND",
        )

    target_user.is_active = not target_user.is_active
    db.commit()
    db.refresh(target_user)

    status_text = "diaktifkan" if target_user.is_active else "dinonaktifkan"
    return ApiResponse.ok(
        data=UserResponse.model_validate(target_user),
        message=f"Status pengguna berhasil {status_text}",
    )
