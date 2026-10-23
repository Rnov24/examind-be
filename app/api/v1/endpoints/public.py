"""Public landing page data — no authentication required.

Returns real pricing plans (the same source of truth used for billing) and
honest platform counters read live from the database. Nothing is invented:
if the database is unreachable, counters are omitted rather than fabricated.
"""
import logging

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.rate_limit import limiter, global_key
from app.models.tenant import Tenant
from app.models.user import User
from app.models.exam import Exam
from app.models.session import ExamSession
from app.models.inquiry import Inquiry
from app.schemas.common import ApiResponse
from app.services.billing.pricing_plans import get_pricing_plans

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/public", tags=["Public"])


@router.get("/landing")
def get_landing_data(db: Session = Depends(get_db)):
    stats = {}
    try:
        stats = {
            "active_schools": db.query(func.count(Tenant.id)).filter(Tenant.is_active == True).scalar() or 0,
            "total_users": db.query(func.count(User.id)).scalar() or 0,
            "total_exams": db.query(func.count(Exam.id)).scalar() or 0,
            "total_sessions": db.query(func.count(ExamSession.id)).scalar() or 0,
        }
    except Exception as e:
        logger.warning(f"[PublicLanding] stats query failed: {e}")

    return ApiResponse.ok(
        data={
            "plans": get_pricing_plans(db),
            "stats": stats,
        },
        message="Data publik landing berhasil dimuat",
    )


class InquiryCreate(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=150)
    role: str | None = Field(default=None, max_length=150)
    school_name: str = Field(..., min_length=2, max_length=200)
    whatsapp: str = Field(..., min_length=8, max_length=30)
    package_interest: str | None = Field(default=None, max_length=200)
    student_count_range: str | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None, max_length=2000)


@router.post("/inquiries")
@limiter.limit("5/minute", key_func=global_key)
@limiter.limit("30/hour", key_func=global_key)
def create_inquiry(request: Request, payload: InquiryCreate, db: Session = Depends(get_db)):
    """Persist a landing-page consultation inquiry.

    The landing form used to be local-only theatre (a success banner with no
    server behind it). This endpoint makes submissions real; the superadmin
    sees them via GET /superadmin/inquiries and the notification feed.
    """
    inquiry = Inquiry(
        full_name=payload.full_name.strip(),
        role=(payload.role or "").strip() or None,
        school_name=payload.school_name.strip(),
        whatsapp=payload.whatsapp.strip(),
        package_interest=(payload.package_interest or "").strip() or None,
        student_count_range=(payload.student_count_range or "").strip() or None,
        notes=(payload.notes or "").strip() or None,
        status="new",
    )
    db.add(inquiry)
    db.commit()
    db.refresh(inquiry)
    return ApiResponse.ok(
        data={"id": inquiry.id, "status": inquiry.status},
        message="Permohonan konsultasi berhasil terkirim",
    )
