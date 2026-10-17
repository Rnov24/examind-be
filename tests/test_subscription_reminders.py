import re
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, AsyncMock

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.tenant import Tenant, TenantRegistrationCode, SubscriptionReminderLog
from app.models.user import User
from app.services.email.resend_service import render_subscription_reminder_html
from app.services.billing.subscription_reminders import (
    check_and_send_reminders,
    backfill_existing_tenants,
)


EMOJI_PATTERN = re.compile(
    r"[\U00010000-\U0010ffff\u2600-\u26ff\u2700-\u27bf\u2300-\u23ff\u2b50\u203c-\u2049\u25aa-\u25fe]"
)


def _assert_anti_slop(html: str):
    """Enforce strict anti-slop email constraints."""
    assert "<style" not in html.lower(), "Email template must not contain <style> tags"
    assert "</style>" not in html.lower()
    assert '<link rel="stylesheet"' not in html.lower()
    assert "linear-gradient" not in html.lower(), "Email template must not contain linear gradients"
    assert "radial-gradient" not in html.lower(), "Email template must not contain radial gradients"
    assert not EMOJI_PATTERN.search(html), "Email template must not contain emojis"
    assert "#150f23" in html.lower(), "Header band or elements must include midnight-violet #150f23"
    assert "#c2ef4e" in html.lower(), "Accent rule must include lime #c2ef4e"
    assert "max-width: 600px" in html, "Email layout must respect max-width: 600px"


@pytest.fixture
def db_session():
    """In-memory SQLite database session for unit tests."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def test_render_subscription_reminder_html_compliance():
    """Verify render_subscription_reminder_html adheres to anti-slop rules for all stages."""
    now = datetime(2026, 10, 17, 10, 0, 0)
    due_date = now + timedelta(days=3)
    grace_ends = due_date + timedelta(days=7)

    stages = ["due_in_7", "due_in_3", "due_today", "grace_period", "expired"]
    for stage in stages:
        html = render_subscription_reminder_html(
            tenant_name="SMA Negeri 1 Jakarta",
            stage=stage,
            due_date=due_date,
            grace_period_ends=grace_ends,
            plan_name="Pro",
            admin_name="Kepala Sekolah",
            portal_url="https://app.examind.id",
        )
        _assert_anti_slop(html)
        assert "SMA Negeri 1 Jakarta" in html
        assert "Kepala Sekolah" in html
        assert "https://app.examind.id" in html


@pytest.mark.asyncio
async def test_tenant_due_in_3_days_gets_email_once_and_second_run_sends_nothing(db_session):
    """Scenario 1: Tenant due in 3 days gets `due_in_3` email once. Second run sends nothing."""
    now = datetime(2026, 10, 17, 7, 0, 0)
    due_date = now + timedelta(days=3)
    grace_ends = due_date + timedelta(days=7)

    tenant = Tenant(
        name="SMA Harapan Bangsa",
        code="shb-edu",
        subscription_plan="pro",
        subscription_status="active",
        created_at=now - timedelta(days=27),
        subscription_due_date=due_date,
        grace_period_ends=grace_ends,
        is_active=True,
    )
    db_session.add(tenant)
    db_session.commit()
    db_session.refresh(tenant)

    admin = User(
        identifier="admin_shb",
        email="admin@shb.sch.id",
        password_hash="mock_hash",
        full_name="Admin Harapan Bangsa",
        role="admin",
        tenant_id=tenant.id,
        is_active=True,
    )
    db_session.add(admin)
    db_session.commit()

    with patch("app.services.billing.subscription_reminders.send_email_via_resend", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = {"id": "mock_email_123", "status": "sent"}

        # Run 1: Should send due_in_3 email
        result1 = await check_and_send_reminders(db_session, as_of=now)
        assert result1["emails_sent"] == 1
        assert len(result1["reminders"]) == 1
        assert result1["reminders"][0]["stage"] == "due_in_3"
        assert result1["reminders"][0]["tenant_id"] == tenant.id
        assert result1["reminders"][0]["recipient"] == "admin@shb.sch.id"

        mock_send.assert_awaited_once()
        args, kwargs = mock_send.call_args
        assert kwargs["to_email"] == "admin@shb.sch.id"
        assert "3 Hari" in kwargs["subject"]
        assert not EMOJI_PATTERN.search(kwargs["subject"])

        # Check DB log table
        logs = db_session.query(SubscriptionReminderLog).filter(
            SubscriptionReminderLog.tenant_id == tenant.id
        ).all()
        assert len(logs) == 1
        assert logs[0].stage == "due_in_3"

        # Run 2: Same day/time. Must send NOTHING (idempotent duplicate prevention)
        result2 = await check_and_send_reminders(db_session, as_of=now)
        assert result2["emails_sent"] == 0
        assert len(result2["reminders"]) == 0

        # mock_send should still only have been called once across both runs
        assert mock_send.await_count == 1


@pytest.mark.asyncio
async def test_expired_grace_period_transitions_status_to_past_due(db_session):
    """Scenario 2: Expired grace period sets subscription_status = 'past_due'."""
    now = datetime(2026, 10, 17, 7, 0, 0)
    due_date = now - timedelta(days=10)
    grace_ends = now - timedelta(days=2)  # Grace expired 2 days ago

    tenant = Tenant(
        name="SMA Nusa Bangsa",
        code="nusa-bangsa",
        subscription_plan="starter",
        subscription_status="active",
        created_at=now - timedelta(days=40),
        subscription_due_date=due_date,
        grace_period_ends=grace_ends,
        is_active=True,
    )
    db_session.add(tenant)
    db_session.commit()
    db_session.refresh(tenant)

    admin = User(
        identifier="admin_nusa",
        email="admin@nusabangsa.sch.id",
        password_hash="mock_hash",
        full_name="Admin Nusa Bangsa",
        role="admin",
        tenant_id=tenant.id,
        is_active=True,
    )
    db_session.add(admin)
    db_session.commit()

    with patch("app.services.billing.subscription_reminders.send_email_via_resend", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = {"id": "mock_email_456", "status": "sent"}

        result = await check_and_send_reminders(db_session, as_of=now)

        # Refresh tenant from DB
        db_session.refresh(tenant)
        assert tenant.subscription_status == "past_due"
        assert result["status_transitions"] == 1
        assert result["emails_sent"] == 1
        assert result["reminders"][0]["stage"] == "expired"


@pytest.mark.asyncio
async def test_all_reminder_stages_dispatch_correctly(db_session):
    """Verify due_in_7, due_today, and grace_period stages dispatch expected emails."""
    now = datetime(2026, 10, 17, 7, 0, 0)

    # 1. Tenant due in 7 days
    t7 = Tenant(
        name="Sekolah 7 Hari",
        code="sch7",
        subscription_plan="pro",
        subscription_status="active",
        subscription_due_date=now + timedelta(days=7),
        grace_period_ends=now + timedelta(days=14),
        is_active=True,
    )
    # 2. Tenant due today
    t0 = Tenant(
        name="Sekolah Hari Ini",
        code="sch0",
        subscription_plan="pro",
        subscription_status="active",
        subscription_due_date=now,
        grace_period_ends=now + timedelta(days=7),
        is_active=True,
    )
    # 3. Tenant in grace period (due 3 days ago, grace ends in 4 days)
    t_grace = Tenant(
        name="Sekolah Grace",
        code="schgrace",
        subscription_plan="enterprise",
        subscription_status="active",
        subscription_due_date=now - timedelta(days=3),
        grace_period_ends=now + timedelta(days=4),
        is_active=True,
    )

    db_session.add_all([t7, t0, t_grace])
    db_session.commit()

    for idx, t in enumerate([t7, t0, t_grace]):
        db_session.refresh(t)
        u = User(
            identifier=f"admin_{t.code}",
            email=f"{t.code}@sekolah.id",
            password_hash="mock",
            full_name=f"Admin {t.name}",
            role="admin",
            tenant_id=t.id,
            is_active=True,
        )
        db_session.add(u)
    db_session.commit()

    with patch("app.services.billing.subscription_reminders.send_email_via_resend", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = {"id": "mock_id", "status": "sent"}

        result = await check_and_send_reminders(db_session, as_of=now)
        assert result["emails_sent"] == 3
        stages_sent = {r["stage"] for r in result["reminders"]}
        assert stages_sent == {"due_in_7", "due_today", "grace_period"}

        # Grace period tenant should still have status 'active' because grace has not expired
        db_session.refresh(t_grace)
        assert t_grace.subscription_status == "active"


def test_backfill_existing_tenants(db_session):
    """Verify backfill helper sets subscription_due_date = created_at + 30d and grace = due_date + 7d."""
    base_created = datetime(2026, 9, 1, 10, 0, 0)
    t = Tenant(
        name="Sekolah Lama",
        code="lama",
        subscription_plan="pro",
        subscription_status="active",
        created_at=base_created,
        subscription_due_date=None,
        grace_period_ends=None,
        is_active=True,
    )
    db_session.add(t)
    db_session.commit()
    db_session.refresh(t)

    updated_count = backfill_existing_tenants(db_session)
    assert updated_count == 1

    db_session.refresh(t)
    expected_due = base_created + timedelta(days=30)
    expected_grace = expected_due + timedelta(days=7)
    assert t.subscription_due_date == expected_due
    assert t.grace_period_ends == expected_grace
