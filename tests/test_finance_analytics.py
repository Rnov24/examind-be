import pytest
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.tenant import Tenant
from app.models.user import User
from app.api.v1.endpoints.superadmin import get_superadmin_finance_analytics


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


@pytest.fixture
def mock_superadmin():
    return User(
        id=999,
        identifier="superadmin_test",
        email="superadmin@examind.id",
        role="superadmin",
        is_active=True,
    )


def test_finance_analytics_honest_mrr_and_invoices(db_session, mock_superadmin):
    """Test that get_superadmin_finance_analytics computes honest MRR history

    buckets based on real created_at dates, and honest invoice records.
    """
    # 1. Setup tenants with different created_at dates
    t1 = Tenant(
        id=1,
        name="SMA Negeri 1 Jakarta",
        code="SMAN1JKT",
        subscription_plan="starter",
        subscription_status="active",
        is_active=True,
        created_at=datetime(2026, 7, 15, 10, 0, 0),
    )
    t2 = Tenant(
        id=2,
        name="SMA Labschool Rawamangun",
        code="LABSCHOOL",
        subscription_plan="pro",
        subscription_status="active",
        is_active=True,
        created_at=datetime(2026, 9, 10, 14, 30, 0),
    )
    t3 = Tenant(
        id=3,
        name="SMA Taruna Nusantara",
        code="TARNUS",
        subscription_plan="enterprise",
        subscription_status="active",
        is_active=True,
        created_at=datetime(2026, 10, 5, 8, 15, 0),
    )
    # Inactive / canceled tenant created in June 2026 - should NOT contribute to MRR
    t4 = Tenant(
        id=4,
        name="Sekolah Canceled",
        code="CANCELED_SCH",
        subscription_plan="pro",
        subscription_status="canceled",
        is_active=False,
        created_at=datetime(2026, 6, 1, 9, 0, 0),
    )

    db_session.add_all([t1, t2, t3, t4])
    db_session.commit()

    # Call the endpoint handler
    response = get_superadmin_finance_analytics(db=db_session, current_user=mock_superadmin)
    data = response.data

    # Required keys must all exist
    required_keys = [
        "mrr",
        "arr",
        "arpu",
        "mrr_history",
        "recent_invoices",
        "plan_distribution",
        "plan_revenue",
    ]
    for key in required_keys:
        assert key in data, f"Key '{key}' missing from finance response"

    # Total MRR: starter (1.5M) + pro (3.5M) + enterprise (7.5M) = 12.5M
    assert data["mrr"] == 12_500_000
    assert data["arr"] == 12_500_000 * 12
    # 3 active tenants: 12.5M // 3 = 4,166,666
    assert data["arpu"] == 12_500_000 // 3

    # Check MRR history buckets (6 months ending in current month: Mei -> Okt 2026)
    history = data["mrr_history"]
    assert len(history) == 6

    # Verify months order: Mei 2026, Jun 2026, Jul 2026, Agu 2026, Sep 2026, Okt 2026
    months = [h["month"] for h in history]
    assert months == ["Mei 2026", "Jun 2026", "Jul 2026", "Agu 2026", "Sep 2026", "Okt 2026"]

    # Month 0: Mei 2026 - no tenants existed -> honestly 0
    assert history[0]["mrr"] == 0
    assert history[0]["schools"] == 0

    # Month 1: Jun 2026 - only t4 existed, but t4 is canceled -> honestly 0
    assert history[1]["mrr"] == 0
    assert history[1]["schools"] == 0

    # Month 2: Jul 2026 - t1 existed (starter = 1.5M)
    assert history[2]["mrr"] == 1_500_000
    assert history[2]["schools"] == 1

    # Month 3: Agu 2026 - still only t1 existed (starter = 1.5M)
    assert history[3]["mrr"] == 1_500_000
    assert history[3]["schools"] == 1

    # Month 4: Sep 2026 - t1 + t2 existed (1.5M + 3.5M = 5M)
    assert history[4]["mrr"] == 5_000_000
    assert history[4]["schools"] == 2

    # Month 5: Okt 2026 - t1 + t2 + t3 existed (1.5M + 3.5M + 7.5M = 12.5M)
    assert history[5]["mrr"] == 12_500_000
    assert history[5]["schools"] == 3

    # Check honest invoices
    invoices = data["recent_invoices"]
    assert len(invoices) == 4

    # Never fabricate BCA Virtual Account
    for inv in invoices:
        assert inv["payment_method"] != "BCA Virtual Account", "Fabricated payment method detected"
        assert inv["period"] != "Okt 2026 - Nov 2026", "Fabricated period detected"

    # Map invoices by tenant_id
    inv_map = {inv["tenant_id"]: inv for inv in invoices}

    # Tenant 1 invoice: July 2026
    assert inv_map[1]["period"] == "Jul 2026"
    assert inv_map[1]["amount"] == 1_500_000
    assert inv_map[1]["plan"] == "STARTER"
    assert "Jul 2026" in inv_map[1]["date"]
    assert inv_map[1]["status"] == "paid"

    # Tenant 2 invoice: September 2026
    assert inv_map[2]["period"] == "Sep 2026"
    assert inv_map[2]["amount"] == 3_500_000
    assert inv_map[2]["plan"] == "PRO"
    assert "Sep 2026" in inv_map[2]["date"]
    assert inv_map[2]["status"] == "paid"

    # Tenant 3 invoice: October 2026
    assert inv_map[3]["period"] == "Okt 2026"
    assert inv_map[3]["amount"] == 7_500_000
    assert inv_map[3]["plan"] == "ENTERPRISE"
    assert "Okt 2026" in inv_map[3]["date"]
    assert inv_map[3]["status"] == "paid"

    # Tenant 4 invoice: June 2026, inactive/canceled
    assert inv_map[4]["period"] == "Jun 2026"
    assert inv_map[4]["amount"] == 3_500_000
    assert inv_map[4]["status"] == "past_due"


def test_finance_analytics_empty_database(db_session, mock_superadmin):
    """Test get_superadmin_finance_analytics with zero tenants: all values honestly 0."""
    response = get_superadmin_finance_analytics(db=db_session, current_user=mock_superadmin)
    data = response.data

    assert data["mrr"] == 0
    assert data["arr"] == 0
    assert data["arpu"] == 0
    assert data["active_tenants"] == 0
    assert data["plan_distribution"] == {"starter": 0, "pro": 0, "enterprise": 0}
    assert data["plan_revenue"] == {"starter": 0, "pro": 0, "enterprise": 0}
    assert data["recent_invoices"] == []
    assert len(data["mrr_history"]) == 6
    for h in data["mrr_history"]:
        assert h["mrr"] == 0
        assert h["schools"] == 0


def test_finance_analytics_null_created_at_handled_honestly(db_session, mock_superadmin):
    """Test tenant with null created_at produces honest fallback values without crashing."""
    t = Tenant(
        id=10,
        name="Sekolah Tanpa Tanggal",
        code="NOTDATE",
        subscription_plan="starter",
        subscription_status="active",
        is_active=True,
        created_at=None,
    )
    db_session.add(t)
    db_session.commit()

    response = get_superadmin_finance_analytics(db=db_session, current_user=mock_superadmin)
    data = response.data

    assert len(data["recent_invoices"]) == 1
    inv = data["recent_invoices"][0]
    assert inv["period"] == "-"
    assert inv["date"] == "-"
    assert inv["payment_method"] == "-"
    assert inv["status"] == "paid"
    assert inv["amount"] == 1_500_000
