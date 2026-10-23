"""Role-scoped notifications derived from real database rows.

Every item comes from an actual table (tenants, exam_sessions,
proctoring_logs) — nothing is fabricated. Each notification kind is built
best-effort: if one query fails, that kind is skipped silently so the
endpoint as a whole never 500s.
"""
import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_active_user
from app.models.exam import Exam
from app.models.proctoring import ProctoringLog
from app.models.session import ExamSession
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.common import ApiResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/notifications", tags=["Notifications"])

JAKARTA_OFFSET = timedelta(hours=7)
MAX_ITEMS = 10


def _iso(dt):
    return dt.isoformat() if dt else None


def _jakarta_today_window_utc():
    """(start_utc, end_utc) covering today's Asia/Jakarta calendar day."""
    today_jakarta = (datetime.utcnow() + JAKARTA_OFFSET).date()
    start_utc = datetime.combine(today_jakarta, datetime.min.time()) - JAKARTA_OFFSET
    return start_utc, start_utc + timedelta(days=1)


def _violations_per_exam(db, since, extra_filters):
    """Aggregate medium/high proctoring violations per exam since `since`.

    extra_filters: list of SQLAlchemy filter clauses scoping the sessions
    (tenant / teacher). Returns one notification item per exam.
    """
    rows = (
        db.query(
            Exam.id,
            Exam.title,
            func.count(ProctoringLog.id),
            func.max(ProctoringLog.event_timestamp),
            func.sum(func.if_(ProctoringLog.severity == "high", 1, 0))
            if False
            else func.count(ProctoringLog.id),
        )
        .join(ExamSession, ProctoringLog.session_id == ExamSession.id)
        .join(Exam, ExamSession.exam_id == Exam.id)
        .join(User, ExamSession.student_id == User.id)
        .filter(
            ProctoringLog.event_timestamp >= since,
            ProctoringLog.severity.in_(["high", "medium"]),
            *extra_filters,
        )
        .group_by(Exam.id, Exam.title)
        .all()
    )
    items = []
    for exam_id, title, count, last_at, _ in rows:
        # Determine whether any high-severity log exists for this exam.
        has_high = (
            db.query(ProctoringLog.id)
            .join(ExamSession, ProctoringLog.session_id == ExamSession.id)
            .filter(
                ExamSession.exam_id == exam_id,
                ProctoringLog.event_timestamp >= since,
                ProctoringLog.severity == "high",
            )
            .first()
            is not None
        )
        items.append(
            {
                "id": f"proctoring-violations-{exam_id}",
                "kind": "proctoring_violations",
                "title": "Pelanggaran proctoring terdeteksi",
                "body": f"{count} pelanggaran (sedang/berat) pada ujian '{title}' dalam 24 jam terakhir.",
                "created_at": _iso(last_at),
                "severity": "critical" if has_high else "warning",
            }
        )
    return items


def _sessions_submitted_today(db, extra_filters):
    """One aggregate item for sessions submitted today (Jakarta), or None."""
    start_utc, end_utc = _jakarta_today_window_utc()
    count, last_at = (
        db.query(func.count(ExamSession.id), func.max(ExamSession.submit_time))
        .join(User, ExamSession.student_id == User.id)
        .filter(
            ExamSession.submit_time.isnot(None),
            ExamSession.submit_time >= start_utc,
            ExamSession.submit_time < end_utc,
            *extra_filters,
        )
        .one()
    )
    if not count:
        return None
    return {
        "id": "sessions-submitted-today",
        "kind": "sessions_submitted_today",
        "title": "Sesi ujian selesai hari ini",
        "body": f"{count} sesi ujian telah diselesaikan hari ini.",
        "created_at": _iso(last_at),
        "severity": "info",
    }


def _superadmin_items(db):
    items = []
    now = datetime.utcnow()

    # Schools registered in the last 7 days
    try:
        tenants = (
            db.query(Tenant)
            .filter(Tenant.created_at >= now - timedelta(days=7))
            .order_by(Tenant.created_at.desc())
            .all()
        )
        for t in tenants:
            items.append(
                {
                    "id": f"tenant-new-{t.id}",
                    "kind": "tenant_registered",
                    "title": "Sekolah baru terdaftar",
                    "body": f"{t.name} ({t.code}) terdaftar dengan paket {t.subscription_plan}.",
                    "created_at": _iso(t.created_at),
                    "severity": "info",
                }
            )
    except Exception as e:
        logger.warning(f"[Notifications] new tenants query failed: {e}")

    # Subscriptions due within 7 days, or grace period already over
    try:
        tenants = (
            db.query(Tenant)
            .filter(
                (
                    (Tenant.subscription_due_date.isnot(None))
                    & (Tenant.subscription_due_date <= now + timedelta(days=7))
                    & (Tenant.subscription_due_date >= now - timedelta(days=30))
                )
                | (
                    (Tenant.grace_period_ends.isnot(None))
                    & (Tenant.grace_period_ends < now)
                )
            )
            .all()
        )
        for t in tenants:
            grace_over = t.grace_period_ends is not None and t.grace_period_ends < now
            items.append(
                {
                    "id": f"tenant-due-{t.id}",
                    "kind": "subscription_due",
                    "title": "Langganan jatuh tempo",
                    "body": (
                        f"Masa tenggang langganan {t.name} ({t.code}) telah berakhir."
                        if grace_over
                        else f"Langganan {t.name} ({t.code}) jatuh tempo pada "
                        f"{t.subscription_due_date.strftime('%d-%m-%Y') if t.subscription_due_date else '-'}."
                    ),
                    "created_at": _iso(t.grace_period_ends if grace_over else t.subscription_due_date),
                    "severity": "critical" if grace_over else "warning",
                }
            )
    except Exception as e:
        logger.warning(f"[Notifications] due tenants query failed: {e}")

    # High-severity proctoring violations in the last 24h, per exam
    try:
        since = now - timedelta(hours=24)
        rows = (
            db.query(
                Exam.id,
                Exam.title,
                func.count(ProctoringLog.id),
                func.max(ProctoringLog.event_timestamp),
            )
            .join(ExamSession, ProctoringLog.session_id == ExamSession.id)
            .join(Exam, ExamSession.exam_id == Exam.id)
            .filter(
                ProctoringLog.event_timestamp >= since,
                ProctoringLog.severity == "high",
            )
            .group_by(Exam.id, Exam.title)
            .all()
        )
        for exam_id, title, count, last_at in rows:
            items.append(
                {
                    "id": f"proctoring-high-{exam_id}",
                    "kind": "proctoring_violations_high",
                    "title": "Pelanggaran berat terdeteksi",
                    "body": f"{count} pelanggaran berat pada ujian '{title}' dalam 24 jam terakhir.",
                    "created_at": _iso(last_at),
                    "severity": "critical",
                }
            )
    except Exception as e:
        logger.warning(f"[Notifications] high violations query failed: {e}")

    return items


def _admin_items(db, user):
    items = []
    if user.tenant_id is None:
        return items
    since = datetime.utcnow() - timedelta(hours=24)
    try:
        items.extend(
            _violations_per_exam(db, since, [User.tenant_id == user.tenant_id])
        )
    except Exception as e:
        logger.warning(f"[Notifications] admin violations query failed: {e}")
    try:
        item = _sessions_submitted_today(db, [User.tenant_id == user.tenant_id])
        if item:
            item["id"] = f"sessions-submitted-today-tenant-{user.tenant_id}"
            items.append(item)
    except Exception as e:
        logger.warning(f"[Notifications] admin sessions query failed: {e}")
    return items


def _teacher_items(db, user):
    items = []
    since = datetime.utcnow() - timedelta(hours=24)
    try:
        items.extend(
            _violations_per_exam(db, since, [Exam.teacher_id == user.id])
        )
    except Exception as e:
        logger.warning(f"[Notifications] teacher violations query failed: {e}")
    try:
        own_exam_ids = db.query(Exam.id).filter(Exam.teacher_id == user.id).subquery()
        item = _sessions_submitted_today(db, [ExamSession.exam_id.in_(own_exam_ids)])
        if item:
            item["id"] = f"sessions-submitted-today-teacher-{user.id}"
            items.append(item)
    except Exception as e:
        logger.warning(f"[Notifications] teacher sessions query failed: {e}")
    return items


@router.get("")
def list_notifications(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Notifications derived from real data, scoped to the caller's role."""
    role = current_user.role
    if role == "superadmin":
        items = _superadmin_items(db)
    elif role == "admin":
        items = _admin_items(db, current_user)
    elif role == "teacher":
        items = _teacher_items(db, current_user)
    else:  # student and any other role: no fabricated items
        items = []

    items.sort(key=lambda i: i.get("created_at") or "", reverse=True)
    return ApiResponse.ok(
        data={"items": items[:MAX_ITEMS]},
        message="Notifikasi berhasil dimuat",
    )
