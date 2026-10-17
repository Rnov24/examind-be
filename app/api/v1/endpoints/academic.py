from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session, joinedload, selectinload
from app.core.database import get_db
from app.core.exceptions import AppException
from app.core.dependencies import get_current_active_user, require_teacher, require_teacher_or_admin
from app.core.timing import log_query_timing
from app.models.user import User
from app.models.academic import Class, ClassMember
from app.schemas.academic import (
    ClassCreate,
    ClassUpdate,
    ClassResponse,
    ClassDetailResponse,
    ClassMemberAdd,
    ClassMemberResponse,
)
from app.schemas.auth import UserResponse
from app.schemas.common import ApiResponse, PaginatedResponse

router = APIRouter(prefix="/classes", tags=["Classes & Academics"])


@router.get("", response_model=PaginatedResponse[ClassResponse])
def get_classes(
    page: int = Query(1, ge=1, description="Nomor halaman"),
    page_size: int = Query(20, ge=1, le=100, description="Jumlah data per halaman"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    with log_query_timing("get_classes"):
        if current_user.role == "admin":
            query = db.query(Class)
        elif current_user.role == "teacher":
            query = db.query(Class).filter(Class.created_by == current_user.id)
        else:  # student
            class_ids = [m.class_id for m in db.query(ClassMember).filter(ClassMember.user_id == current_user.id).all()]
            if not class_ids:
                return PaginatedResponse.ok(
                    data=[],
                    page=page,
                    page_size=page_size,
                    total=0,
                    message="Daftar kelas berhasil dimuat",
                )
            query = db.query(Class).filter(Class.id.in_(class_ids))

        total = query.count()
        classes = (
            query.options(
                joinedload(Class.creator),
                selectinload(Class.members),
            )
            .order_by(Class.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )

        results = []
        for c in classes:
            res = ClassResponse(
                id=c.id,
                name=c.name,
                grade_level=c.grade_level,
                academic_year=c.academic_year,
                created_by=c.created_by,
                created_at=c.created_at,
                members_count=len(c.members),
                creator_name=c.creator.full_name if c.creator else None,
            )
            results.append(res)

        return PaginatedResponse.ok(
            data=results,
            page=page,
            page_size=page_size,
            total=total,
            message="Daftar kelas berhasil dimuat",
        )


@router.post("", response_model=ApiResponse[ClassResponse])
def create_class(
    request: ClassCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    new_class = Class(
        name=request.name,
        grade_level=request.grade_level,
        academic_year=request.academic_year,
        created_by=current_user.id,
    )
    db.add(new_class)
    db.commit()
    db.refresh(new_class)

    # Automatically add the teacher as a class member with teacher role
    teacher_member = ClassMember(
        class_id=new_class.id,
        user_id=current_user.id,
        role="teacher",
    )
    db.add(teacher_member)
    db.commit()
    db.refresh(new_class)

    res = ClassResponse(
        id=new_class.id,
        name=new_class.name,
        grade_level=new_class.grade_level,
        academic_year=new_class.academic_year,
        created_by=new_class.created_by,
        created_at=new_class.created_at,
        members_count=len(new_class.members),
        creator_name=current_user.full_name,
    )
    return ApiResponse.ok(data=res, message="Kelas berhasil dibuat")


@router.get("/{class_id}", response_model=ApiResponse[ClassDetailResponse])
def get_class_detail(
    class_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    cls = db.query(Class).filter(Class.id == class_id).first()
    if not cls:
        raise AppException(
            message="Kelas tidak ditemukan.",
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="CLASS_NOT_FOUND",
        )

    # Convert members
    members_data = []
    for m in cls.members:
        user_res = UserResponse.model_validate(m.user) if m.user else None
        members_data.append(
            ClassMemberResponse(
                id=m.id,
                class_id=m.class_id,
                user_id=m.user_id,
                role=m.role,
                joined_at=m.joined_at,
                user=user_res,
            )
        )

    detail = ClassDetailResponse(
        id=cls.id,
        name=cls.name,
        grade_level=cls.grade_level,
        academic_year=cls.academic_year,
        created_by=cls.created_by,
        created_at=cls.created_at,
        members_count=len(cls.members),
        creator_name=cls.creator.full_name if cls.creator else None,
        members=members_data,
    )
    return ApiResponse.ok(data=detail, message="Detail kelas berhasil dimuat")


@router.put("/{class_id}", response_model=ApiResponse[ClassResponse])
def update_class(
    class_id: int,
    request: ClassUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    cls = db.query(Class).filter(Class.id == class_id).first()
    if not cls:
        raise AppException(
            message="Kelas tidak ditemukan.",
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="CLASS_NOT_FOUND",
        )

    if current_user.role != "admin" and cls.created_by != current_user.id:
        raise AppException(
            message="Anda tidak memiliki izin untuk mengubah kelas ini.",
            status_code=status.HTTP_403_FORBIDDEN,
            error_code="FORBIDDEN",
        )

    if request.name is not None:
        cls.name = request.name
    if request.grade_level is not None:
        cls.grade_level = request.grade_level
    if request.academic_year is not None:
        cls.academic_year = request.academic_year

    db.commit()
    db.refresh(cls)

    res = ClassResponse(
        id=cls.id,
        name=cls.name,
        grade_level=cls.grade_level,
        academic_year=cls.academic_year,
        created_by=cls.created_by,
        created_at=cls.created_at,
        members_count=len(cls.members),
        creator_name=cls.creator.full_name if cls.creator else None,
    )
    return ApiResponse.ok(data=res, message="Data kelas berhasil diperbarui")


@router.delete("/{class_id}", response_model=ApiResponse[dict])
def delete_class(
    class_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    cls = db.query(Class).filter(Class.id == class_id).first()
    if not cls:
        raise AppException(
            message="Kelas tidak ditemukan.",
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="CLASS_NOT_FOUND",
        )

    if current_user.role != "admin" and cls.created_by != current_user.id:
        raise AppException(
            message="Anda tidak memiliki izin untuk menghapus kelas ini.",
            status_code=status.HTTP_403_FORBIDDEN,
            error_code="FORBIDDEN",
        )

    db.delete(cls)
    db.commit()
    return ApiResponse.ok(data={"deleted_id": class_id}, message="Kelas berhasil dihapus")


@router.post("/{class_id}/members", response_model=ApiResponse[ClassMemberResponse])
def add_class_member(
    class_id: int,
    request: ClassMemberAdd,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    cls = db.query(Class).filter(Class.id == class_id).first()
    if not cls:
        raise AppException(
            message="Kelas tidak ditemukan.",
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="CLASS_NOT_FOUND",
        )

    target_user = db.query(User).filter(User.id == request.user_id).first()
    if not target_user:
        raise AppException(
            message="Pengguna yang dipilih tidak ditemukan.",
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="USER_NOT_FOUND",
        )

    # Check if already a member
    existing = (
        db.query(ClassMember)
        .filter(ClassMember.class_id == class_id, ClassMember.user_id == request.user_id)
        .first()
    )
    if existing:
        raise AppException(
            message="Pengguna sudah terdaftar sebagai anggota kelas ini.",
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="ALREADY_MEMBER",
        )

    member = ClassMember(
        class_id=class_id,
        user_id=request.user_id,
        role=request.role or target_user.role,
    )
    db.add(member)
    db.commit()
    db.refresh(member)

    res = ClassMemberResponse(
        id=member.id,
        class_id=member.class_id,
        user_id=member.user_id,
        role=member.role,
        joined_at=member.joined_at,
        user=UserResponse.model_validate(target_user),
    )
    return ApiResponse.ok(data=res, message="Anggota berhasil ditambahkan ke kelas")


@router.delete("/{class_id}/members/{user_id}", response_model=ApiResponse[dict])
def remove_class_member(
    class_id: int,
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    member = (
        db.query(ClassMember)
        .filter(ClassMember.class_id == class_id, ClassMember.user_id == user_id)
        .first()
    )
    if not member:
        raise AppException(
            message="Keanggotaan tidak ditemukan.",
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="MEMBER_NOT_FOUND",
        )

    db.delete(member)
    db.commit()
    return ApiResponse.ok(data={"removed_user_id": user_id}, message="Anggota berhasil dikeluarkan dari kelas")


@router.get("/users/students", response_model=PaginatedResponse[UserResponse])
def get_all_students(
    page: int = Query(1, ge=1, description="Nomor halaman"),
    page_size: int = Query(20, ge=1, le=100, description="Jumlah data per halaman"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    with log_query_timing("get_all_students"):
        query = db.query(User).filter(User.role == "student", User.is_active == True)
        total = query.count()
        students = (
            query.order_by(User.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        results = [UserResponse.model_validate(s) for s in students]
        return PaginatedResponse.ok(
            data=results,
            page=page,
            page_size=page_size,
            total=total,
            message="Daftar siswa berhasil dimuat",
        )
