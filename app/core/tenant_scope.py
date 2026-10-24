"""Tenant isolation helpers — the single source of truth for "may this user
touch this row?".

Model layout (why joins are needed):
- User.tenant_id scopes a user to exactly one school (superadmin has NULL).
- Exam, ExamSession, Class, QuestionBank have NO tenant_id column; they are
  scoped through their owner users:
    Exam        -> exam.teacher.tenant_id
    ExamSession -> session.student.tenant_id (and session.exam.teacher_id)
    Class       -> class.creator.tenant_id
    QuestionBank -> bank.teacher.tenant_id

Conventions:
- Superadmin (tenant_id NULL) legitimately sees everything.
- Cross-tenant AND cross-owner access both raise 404 (not 403) so the
  existence of another tenant's resources is never leaked. The student
  endpoints already used 404 for "not yours"; this module extends that
  convention to every resource, replacing the handful of 403s that used to
  confirm a resource exists before refusing it.
- Never trust a tenant_id from the request body/query — the caller's tenant
  is always derived from current_user.tenant_id.
"""
from fastapi import status
from sqlalchemy.orm import Session

from app.core.exceptions import AppException
from app.models.academic import Class, ClassMember
from app.models.exam import Exam
from app.models.question import QuestionBank
from app.models.session import ExamSession
from app.models.user import User


def _not_found(message: str, code: str) -> AppException:
    return AppException(
        message=message,
        status_code=status.HTTP_404_NOT_FOUND,
        error_code=code,
    )


def is_superadmin(user: User) -> bool:
    return user.role == "superadmin"


def same_tenant(user: User, tenant_id) -> bool:
    """True when the caller's tenant matches (superadmin always matches)."""
    if is_superadmin(user):
        return True
    return user.tenant_id is not None and user.tenant_id == tenant_id


# --- Exam -------------------------------------------------------------------

def exam_accessible(db: Session, user: User, exam: Exam) -> bool:
    if is_superadmin(user):
        return True
    if user.role == "admin":
        teacher = exam.teacher or db.query(User).filter(User.id == exam.teacher_id).first()
        return teacher is not None and teacher.tenant_id == user.tenant_id and user.tenant_id is not None
    if user.role == "teacher":
        return exam.teacher_id == user.id
    if user.role == "student":
        return (
            db.query(ClassMember)
            .filter(ClassMember.class_id == exam.class_id, ClassMember.user_id == user.id)
            .first()
            is not None
        )
    return False


def require_exam(db: Session, user: User, exam_id: int) -> Exam:
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam or not exam_accessible(db, user, exam):
        raise _not_found("Paket ujian tidak ditemukan.", "EXAM_NOT_FOUND")
    return exam


# --- ExamSession ------------------------------------------------------------

def session_accessible(db: Session, user: User, session: ExamSession) -> bool:
    if is_superadmin(user):
        return True
    if user.role == "student":
        return session.student_id == user.id
    if user.role == "admin":
        student = session.student or db.query(User).filter(User.id == session.student_id).first()
        return (
            student is not None
            and student.tenant_id == user.tenant_id
            and user.tenant_id is not None
        )
    if user.role == "teacher":
        exam = session.exam or db.query(Exam).filter(Exam.id == session.exam_id).first()
        return exam is not None and exam.teacher_id == user.id
    return False


def require_session(db: Session, user: User, session_id: int) -> ExamSession:
    session = db.query(ExamSession).filter(ExamSession.id == session_id).first()
    if not session or not session_accessible(db, user, session):
        raise _not_found("Sesi ujian tidak ditemukan.", "SESSION_NOT_FOUND")
    return session


# --- Class ------------------------------------------------------------------

def class_accessible(db: Session, user: User, cls: Class, *, write: bool = False) -> bool:
    if is_superadmin(user):
        return True
    if user.role == "admin":
        creator = cls.creator or db.query(User).filter(User.id == cls.created_by).first()
        return (
            creator is not None
            and creator.tenant_id == user.tenant_id
            and user.tenant_id is not None
        )
    if user.role == "teacher":
        if cls.created_by == user.id:
            return True
        if write:
            return False
        # Read: a teacher who is a member of the class may view it.
        return (
            db.query(ClassMember)
            .filter(ClassMember.class_id == cls.id, ClassMember.user_id == user.id)
            .first()
            is not None
        )
    if user.role == "student":
        if write:
            return False
        return (
            db.query(ClassMember)
            .filter(ClassMember.class_id == cls.id, ClassMember.user_id == user.id)
            .first()
            is not None
        )
    return False


def require_class(db: Session, user: User, class_id: int, *, write: bool = False) -> Class:
    cls = db.query(Class).filter(Class.id == class_id).first()
    if not cls or not class_accessible(db, user, cls, write=write):
        raise _not_found("Kelas tidak ditemukan.", "CLASS_NOT_FOUND")
    return cls


# --- QuestionBank -----------------------------------------------------------

def bank_accessible(db: Session, user: User, bank: QuestionBank) -> bool:
    if is_superadmin(user):
        return True
    if user.role == "admin":
        teacher = bank.teacher or db.query(User).filter(User.id == bank.teacher_id).first()
        return teacher is not None and teacher.tenant_id == user.tenant_id and user.tenant_id is not None
    if user.role == "teacher":
        return bank.teacher_id == user.id
    return False


def require_bank(db: Session, user: User, bank_id: int) -> QuestionBank:
    bank = db.query(QuestionBank).filter(QuestionBank.id == bank_id).first()
    if not bank or not bank_accessible(db, user, bank):
        raise _not_found("Bank soal tidak ditemukan.", "BANK_NOT_FOUND")
    return bank


# --- User (for admin user management) ---------------------------------------

def user_in_scope(db: Session, user: User, target: User) -> bool:
    """May `user` manage/read `target`? Superadmin: anyone. Admin: only
    users of their own tenant. Teachers/students: nobody via this helper."""
    if is_superadmin(user):
        return True
    if user.role == "admin":
        return target.tenant_id == user.tenant_id and user.tenant_id is not None
    return False
