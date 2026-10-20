"""Public landing page data — no authentication required.

Returns real pricing plans (the same source of truth used for billing) and
honest platform counters read live from the database. Nothing is invented:
if the database is unreachable, counters are omitted rather than fabricated.
"""
import logging

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.billing_defaults import DEFAULT_PRICING_PLANS
from app.core.database import get_db
from app.models.tenant import Tenant
from app.models.user import User
from app.models.exam import Exam
from app.models.session import ExamSession
from app.schemas.common import ApiResponse

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
            "plans": DEFAULT_PRICING_PLANS,
            "stats": stats,
        },
        message="Data publik landing berhasil dimuat",
    )
