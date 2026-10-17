import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session

from app.models.tenant import Tenant, SubscriptionReminderLog
from app.models.user import User
from app.services.email.resend_service import (
    send_email_via_resend,
    render_subscription_reminder_html,
)

logger = logging.getLogger("examind.billing.reminders")


async def check_and_send_reminders(
    db: Session,
    as_of: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Find tenants approaching due date or in grace period, dispatch warning emails, and update statuses.

    Stages:
      - 'due_in_7': Due in 7 days (or within 4-7 days if not previously sent)
      - 'due_in_3': Due in 3 days (or within 1-3 days if not previously sent)
      - 'due_today': Due today (0 days until due)
      - 'grace_period': Past due date, but within grace period
      - 'expired': Past grace period (transitions subscription_status to 'past_due')

    Guarantees:
      - Idempotent: exactly one email per stage per billing cycle (logged in SubscriptionReminderLog).
      - Recipient: primary admin user of the tenant.
      - Log-only on individual email failure (does not crash overall loop).
    """
    now = as_of or datetime.utcnow()
    logger.info(f"[SubscriptionReminders] Running reminder check as of {now.isoformat()}...")

    # Fetch active or pending tenants with configured due date
    tenants: List[Tenant] = (
        db.query(Tenant)
        .filter(
            Tenant.is_active == True,
            Tenant.subscription_status.in_(["active", "trial", "past_due"]),
            Tenant.subscription_due_date.isnot(None),
        )
        .all()
    )

    reminders_dispatched: List[Dict[str, Any]] = []
    status_transitions = 0
    skipped_count = 0

    for tenant in tenants:
        due_date = tenant.subscription_due_date
        grace_ends = tenant.grace_period_ends

        # Calculate calendar days until due
        days_until_due = (due_date.date() - now.date()).days

        # Determine whether grace period has expired
        if grace_ends:
            is_grace_expired = now > grace_ends
        else:
            fallback_grace = due_date + timedelta(days=7)
            is_grace_expired = now > fallback_grace

        # Determine candidate stage
        candidate_stage: Optional[str] = None

        if days_until_due > 7:
            candidate_stage = None
        elif 3 < days_until_due <= 7:
            candidate_stage = "due_in_7"
        elif 0 < days_until_due <= 3:
            candidate_stage = "due_in_3"
        elif days_until_due == 0:
            candidate_stage = "due_today"
        elif not is_grace_expired:
            candidate_stage = "grace_period"
        else:
            candidate_stage = "expired"

        # Requirement 5: Status transition when grace_period_ends passes
        if is_grace_expired and tenant.subscription_status != "past_due":
            logger.info(
                f"[SubscriptionReminders] Tenant {tenant.id} ({tenant.code}) grace period ended; "
                f"transitioning subscription_status '{tenant.subscription_status}' -> 'past_due'."
            )
            tenant.subscription_status = "past_due"
            db.commit()
            db.refresh(tenant)
            status_transitions += 1

        if not candidate_stage:
            continue

        # Check if this stage has already been sent for the current cycle
        cycle_cutoff = due_date - timedelta(days=35)
        already_sent = (
            db.query(SubscriptionReminderLog)
            .filter(
                SubscriptionReminderLog.tenant_id == tenant.id,
                SubscriptionReminderLog.stage == candidate_stage,
                SubscriptionReminderLog.sent_at >= cycle_cutoff,
            )
            .first()
        )

        if already_sent:
            logger.debug(
                f"[SubscriptionReminders] Stage '{candidate_stage}' already sent to tenant {tenant.id} on {already_sent.sent_at}; skipping."
            )
            skipped_count += 1
            continue

        # Find recipient: tenant admin's email (first admin user of the tenant)
        admin_user = (
            db.query(User)
            .filter(
                User.tenant_id == tenant.id,
                User.role == "admin",
                User.is_active == True,
            )
            .order_by(User.id.asc())
            .first()
        )
        if not admin_user:
            admin_user = (
                db.query(User)
                .filter(
                    User.tenant_id == tenant.id,
                    User.role == "admin",
                )
                .order_by(User.id.asc())
                .first()
            )

        if not admin_user or not admin_user.email:
            logger.warning(
                f"[SubscriptionReminders] Tenant {tenant.id} ({tenant.name}) has no active admin user with email; skipping email dispatch."
            )
            continue

        # Dispatch warning email via Resend
        try:
            clean_tenant_name = tenant.name.strip() if tenant.name else "Institusi Sekolah"
            subjects = {
                "due_in_7": f"[Pengingat] Masa Aktif Langganan EXAMIND Berakhir dalam 7 Hari - {clean_tenant_name}",
                "due_in_3": f"[Peringatan] Masa Aktif Langganan EXAMIND Berakhir dalam 3 Hari - {clean_tenant_name}",
                "due_today": f"[Pemberitahuan] Masa Langganan EXAMIND Berakhir Hari Ini - {clean_tenant_name}",
                "grace_period": f"[Penting] Langganan EXAMIND Jatuh Tempo - Masa Tenggang Aktif - {clean_tenant_name}",
                "expired": f"[Penting] Masa Tenggang Langganan EXAMIND Telah Berakhir - {clean_tenant_name}",
            }
            subject = subjects.get(candidate_stage, f"[Pemberitahuan] Status Langganan EXAMIND - {clean_tenant_name}")

            html_content = render_subscription_reminder_html(
                tenant_name=clean_tenant_name,
                stage=candidate_stage,
                due_date=due_date,
                grace_period_ends=grace_ends,
                plan_name=tenant.subscription_plan,
                admin_name=admin_user.full_name,
            )

            email_result = await send_email_via_resend(
                to_email=admin_user.email,
                subject=subject,
                html_content=html_content,
            )

            # Record log entry to guarantee idempotence and prevent duplicates
            log_record = SubscriptionReminderLog(
                tenant_id=tenant.id,
                stage=candidate_stage,
                sent_at=now,
            )
            db.add(log_record)
            db.commit()

            reminders_dispatched.append(
                {
                    "tenant_id": tenant.id,
                    "tenant_name": tenant.name,
                    "recipient": admin_user.email,
                    "stage": candidate_stage,
                    "sent_at": now.isoformat(),
                    "email_response": email_result,
                }
            )
            logger.info(
                f"[SubscriptionReminders] Sent '{candidate_stage}' warning email to {admin_user.email} (Tenant {tenant.id})."
            )

        except Exception as exc:
            logger.error(
                f"[SubscriptionReminders] Failed to send '{candidate_stage}' reminder to tenant {tenant.id}: {exc}",
                exc_info=True,
            )

    return {
        "tenants_checked": len(tenants),
        "emails_sent": len(reminders_dispatched),
        "status_transitions": status_transitions,
        "skipped_already_sent": skipped_count,
        "reminders": reminders_dispatched,
    }


def backfill_existing_tenants(db: Session, overwrite: bool = False) -> int:
    """One-off backfill utility: sets subscription_due_date = created_at + 30 days

    and grace_period_ends = due_date + 7 days for existing tenants.
    """
    query = db.query(Tenant)
    if not overwrite:
        query = query.filter(Tenant.subscription_due_date.is_(None))

    tenants = query.all()
    count = 0
    now = datetime.utcnow()

    for t in tenants:
        base_time = t.created_at or now
        due_date = base_time + timedelta(days=30)
        grace_ends = due_date + timedelta(days=7)

        t.subscription_due_date = due_date
        t.grace_period_ends = grace_ends
        count += 1

    db.commit()
    logger.info(f"[SubscriptionReminders] Backfilled due dates for {count} existing tenants.")
    return count
