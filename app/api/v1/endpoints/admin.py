import time
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import text, func
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.core.database import get_db
from app.core.exceptions import AppException
from app.core.dependencies import require_admin
from app.core.security import get_password_hash
from app.core.tenant_scope import is_superadmin, user_in_scope
from app.core.timing import log_query_timing
from app.models.user import User
from app.models.academic import Class
from app.models.question import QuestionBank
from app.models.exam import Exam
from app.models.session import ExamSession
from app.schemas.auth import UserResponse
from app.schemas.common import ApiResponse, PaginatedResponse
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
    with log_query_timing("get_admin_stats"):
        # Measure real database round-trip latency
        t0 = time.perf_counter()
        db.execute(text("SELECT 1"))
        latency_ms = (time.perf_counter() - t0) * 1000.0

        # SCOPE FIX: all counts are scoped to the current admin's tenant.
        # Models without tenant_id (Class, QuestionBank, Exam, ExamSession) are
        # scoped through their owner users via subqueries (same pattern as retrieval.py).
        tenant_id = current_user.tenant_id
        teacher_ids_subq = None
        student_ids_subq = None
        class_filter = None
        bank_filter = None
        exam_filter = None
        session_filter = None
        if tenant_id:
            teacher_ids_subq = db.query(User.id).filter(User.tenant_id == tenant_id, User.role == "teacher")
            student_ids_subq = db.query(User.id).filter(User.tenant_id == tenant_id, User.role == "student")
            class_filter = Class.created_by.in_(teacher_ids_subq)
            bank_filter = QuestionBank.teacher_id.in_(teacher_ids_subq)
            exam_filter = Exam.teacher_id.in_(teacher_ids_subq)
            session_filter = ExamSession.student_id.in_(student_ids_subq)

        user_query = db.query(User.role, func.count(User.id))
        if tenant_id:
            user_query = user_query.filter(User.tenant_id == tenant_id)
        user_counts = dict(user_query.group_by(User.role).all())
        total_users = sum(user_counts.values())
        total_admins = user_counts.get("admin", 0)
        total_teachers = user_counts.get("teacher", 0)
        total_students = user_counts.get("student", 0)

        class_query = db.query(Class)
        if class_filter is not None:
            class_query = class_query.filter(class_filter)
        total_classes = class_query.count()

        bank_query = db.query(QuestionBank)
        if bank_filter is not None:
            bank_query = bank_query.filter(bank_filter)
        total_banks = bank_query.count()

        exam_query = db.query(Exam)
        if exam_filter is not None:
            exam_query = exam_query.filter(exam_filter)
        total_exams = exam_query.count()

        session_query = db.query(ExamSession.status, func.count(ExamSession.id))
        if session_filter is not None:
            session_query = session_query.filter(session_filter)
        session_counts = dict(session_query.group_by(ExamSession.status).all())
        total_sessions = sum(session_counts.values())
        active_sessions = session_counts.get("in_progress", 0) + session_counts.get("ready", 0)
        completed_sessions = session_counts.get("submitted", 0) + session_counts.get("graded", 0)
        disqualified_sessions = session_counts.get("disqualified", 0)

        active_cameras = len(ws_hub.companion_streams)
        if not is_superadmin(current_user) and current_user.tenant_id is not None:
            # Scope the live-camera count to this tenant: companion streams
            # are keyed by session id; resolve each session's student tenant.
            tenant_session_ids = {
                s.id
                for s in db.query(ExamSession.id)
                .join(User, ExamSession.student_id == User.id)
                .filter(User.tenant_id == current_user.tenant_id)
                .all()
            }
            active_cameras = sum(1 for sid in ws_hub.companion_streams if sid in tenant_session_ids)

        stats = AdminStatsResponse(
            total_users=total_users,
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


@router.get("/users", response_model=PaginatedResponse[UserResponse])
def list_users(
    role: Optional[str] = Query(None, description="Filter role (admin, teacher, student)"),
    search: Optional[str] = Query(None, description="Pencarian nama atau identifier"),
    page: int = Query(1, ge=1, description="Nomor halaman"),
    page_size: int = Query(20, ge=1, le=100, description="Jumlah data per halaman"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    with log_query_timing("list_users"):
        query = db.query(User)
        # Tenant isolation: a school admin lists ONLY their own school's users.
        # Superadmin (tenant_id NULL) legitimately sees everyone.
        if not is_superadmin(current_user):
            query = query.filter(User.tenant_id == current_user.tenant_id)
        if role and role != "all":
            query = query.filter(User.role == role)
        if search:
            s = f"%{search}%"
            query = query.filter((User.full_name.ilike(s)) | (User.identifier.ilike(s)) | (User.email.ilike(s)))

        total = query.count()
        users = (
            query.order_by(User.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        results = [UserResponse.model_validate(u) for u in users]
        return PaginatedResponse.ok(
            data=results,
            page=page,
            page_size=page_size,
            total=total,
            message="Daftar pengguna berhasil dimuat",
        )


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
        # Tenant isolation: a school admin can only create users inside
        # their own school. The tenant is derived from the caller, never
        # from the request (the payload has no tenant field by design).
        # A superadmin creating here keeps tenant_id NULL (legacy behavior).
        tenant_id=None if is_superadmin(current_user) else current_user.tenant_id,
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
    if not target_user or not user_in_scope(db, current_user, target_user):
        # 404 (not 403) so a school admin cannot probe whether a user id
        # exists in another school.
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
