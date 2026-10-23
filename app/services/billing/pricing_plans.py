"""DB-backed pricing plans.

The `pricing_plans` table (migrations/add_pricing_plans.sql) is the single
source of truth for subscription plan pricing and limits, editable from the
superadmin panel. DEFAULT_PRICING_PLANS in app/core/billing_defaults.py is
kept only as the first-run seed and as the fallback when the table is
unavailable (e.g. migration not yet applied, SQLite test databases).
"""
import copy
import logging
from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session

from app.core.billing_defaults import DEFAULT_PRICING_PLANS
from app.models.pricing_plan import PricingPlan

logger = logging.getLogger(__name__)

# Fields a superadmin may edit via PUT /superadmin/pricing-plans/{plan_id}.
EDITABLE_FIELDS = (
    "name",
    "price_monthly",
    "price_annually",
    "max_students",
    "max_teachers",
    "max_storage_gb",
    "ai_credits_monthly",
    "proctoring_type",
    "description",
    "features",
    "is_popular",
)


def plan_to_dict(plan: PricingPlan) -> dict:
    """Serialize a PricingPlan row to the exact frontend plan shape."""
    return {
        "id": plan.id,
        "name": plan.name,
        "price_monthly": plan.price_monthly,
        "price_annually": plan.price_annually,
        "max_students": plan.max_students,
        "max_teachers": plan.max_teachers,
        "max_storage_gb": plan.max_storage_gb,
        "ai_credits_monthly": plan.ai_credits_monthly,
        "proctoring_type": plan.proctoring_type,
        "description": plan.description or "",
        "features": list(plan.features or []),
        "is_popular": bool(plan.is_popular),
    }


def _seed_defaults(db: Session) -> None:
    """Insert DEFAULT_PRICING_PLANS rows (sort_order follows list order)."""
    for idx, plan in enumerate(DEFAULT_PRICING_PLANS):
        db.add(
            PricingPlan(
                id=plan["id"],
                name=plan["name"],
                price_monthly=plan["price_monthly"],
                price_annually=plan["price_annually"],
                max_students=plan["max_students"],
                max_teachers=plan["max_teachers"],
                max_storage_gb=plan["max_storage_gb"],
                ai_credits_monthly=plan["ai_credits_monthly"],
                proctoring_type=plan["proctoring_type"],
                description=plan.get("description", ""),
                features=list(plan.get("features", [])),
                is_popular=bool(plan.get("is_popular", False)),
                sort_order=idx,
            )
        )
    db.commit()


def _ensure_seeded(db: Session) -> None:
    if db.query(PricingPlan).count() == 0:
        _seed_defaults(db)


def get_pricing_plans(db: Session) -> List[dict]:
    """All pricing plans ordered by sort_order.

    Seeds the table from DEFAULT_PRICING_PLANS on first read. On any DB
    error (table missing, connection issue) falls back to the defaults so
    public/admin consumers never break.
    """
    try:
        _ensure_seeded(db)
        rows = (
            db.query(PricingPlan)
            .order_by(PricingPlan.sort_order, PricingPlan.id)
            .all()
        )
        return [plan_to_dict(row) for row in rows]
    except Exception as e:
        logger.warning(f"[PricingPlans] DB read failed, using defaults: {e}")
        try:
            db.rollback()
        except Exception:
            pass
        return copy.deepcopy(DEFAULT_PRICING_PLANS)


def get_pricing_plan_row(db: Session, plan_id: str) -> Optional[PricingPlan]:
    """Fetch one plan row, seeding defaults first if the table is empty."""
    _ensure_seeded(db)
    return db.query(PricingPlan).filter(PricingPlan.id == plan_id).first()


def get_plan_price_map(db: Session) -> dict:
    """{plan_id: price_monthly} for MRR/revenue estimates — always DB-backed
    (get_pricing_plans falls back to the defaults when the table is missing)."""
    return {p["id"]: p["price_monthly"] for p in get_pricing_plans(db)}


def update_pricing_plan(db: Session, plan_id: str, fields: dict) -> Optional[dict]:
    """Apply already-validated fields to a plan row and persist.

    Returns the updated plan dict, or None when plan_id is unknown. When
    is_popular is set true, it is cleared on every other plan so at most
    one plan is popular at a time.
    """
    plan = get_pricing_plan_row(db, plan_id)
    if plan is None:
        return None

    if fields.get("is_popular"):
        db.query(PricingPlan).filter(PricingPlan.id != plan_id).update(
            {"is_popular": False}
        )

    for key in EDITABLE_FIELDS:
        if key in fields:
            setattr(plan, key, fields[key])
    plan.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(plan)
    return plan_to_dict(plan)
