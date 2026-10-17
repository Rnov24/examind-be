import pytest
import hmac
import logging
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.core.config import settings
from app.core.database import Base, get_db
from app.core.rate_limit import get_client_ip
from app.models.user import User
from app.models.tenant import Tenant, TenantRegistrationCode
from app.models.verification import EmailVerification
from app.core.security import get_password_hash


# ---------------------------------------------------------------------------
# Part 1: Edge Guard Middleware Tests
# ---------------------------------------------------------------------------

def test_edge_guard_disabled_when_secret_empty():
    """When EDGE_SECRET is empty, edge lock is disabled: all requests pass unchanged."""
    with patch.object(settings, "EDGE_SECRET", ""), patch.object(settings, "EDGE_ENFORCE", False):
        client = TestClient(app)
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"


def test_edge_guard_phase1_missing_secret_allowed_and_logged(caplog):
    """When EDGE_SECRET is set and EDGE_ENFORCE=False (phase 1):
    Requests with missing/invalid secret are logged as warnings but allowed.
    """
    with patch.object(settings, "EDGE_SECRET", "super-secret-123"), patch.object(settings, "EDGE_ENFORCE", False):
        client = TestClient(app)
        with caplog.at_level(logging.WARNING, logger="examind.edge_guard"):
            resp = client.get("/health")
            assert resp.status_code == 200
            assert any("[EdgeGuard] request without valid edge secret: /health" in r.message for r in caplog.records)


def test_edge_guard_phase1_wrong_secret_allowed_and_logged(caplog):
    """When EDGE_SECRET is set and EDGE_ENFORCE=False (phase 1):
    Requests with wrong secret are logged as warnings but allowed.
    """
    with patch.object(settings, "EDGE_SECRET", "super-secret-123"), patch.object(settings, "EDGE_ENFORCE", False):
        client = TestClient(app)
        with caplog.at_level(logging.WARNING, logger="examind.edge_guard"):
            resp = client.get("/health", headers={"X-Examind-Edge-Secret": "wrong-secret"})
            assert resp.status_code == 200
            assert any("[EdgeGuard] request without valid edge secret: /health" in r.message for r in caplog.records)


def test_edge_guard_valid_secret_allowed_no_warning(caplog):
    """When EDGE_SECRET is valid: allowed without warnings."""
    with patch.object(settings, "EDGE_SECRET", "super-secret-123"), patch.object(settings, "EDGE_ENFORCE", True):
        client = TestClient(app)
        with caplog.at_level(logging.WARNING, logger="examind.edge_guard"):
            resp = client.get("/health", headers={"X-Examind-Edge-Secret": "super-secret-123"})
            assert resp.status_code == 200
            assert not any("[EdgeGuard]" in r.message for r in caplog.records)


def test_edge_guard_phase2_enforce_blocks_direct_request():
    """When EDGE_SECRET is set and EDGE_ENFORCE=True (phase 2):
    Non-exempt endpoints return 403 EDGE_FORBIDDEN on missing/wrong secret.
    """
    with patch.object(settings, "EDGE_SECRET", "super-secret-123"), patch.object(settings, "EDGE_ENFORCE", True):
        client = TestClient(app)
        # Hit /api/v1/auth/schools or similar non-exempt endpoint without edge secret
        resp = client.get("/api/v1/auth/schools")
        assert resp.status_code == 403
        data = resp.json()
        assert data["success"] is False
        assert data["message"] == "Akses langsung ditolak."
        assert data["error"]["code"] == "EDGE_FORBIDDEN"

        # Wrong secret also blocked with 403
        resp_wrong = client.get("/api/v1/auth/schools", headers={"X-Examind-Edge-Secret": "wrong"})
        assert resp_wrong.status_code == 403
        assert resp_wrong.json()["error"]["code"] == "EDGE_FORBIDDEN"


def test_edge_guard_phase2_health_exempt_from_enforcement(caplog):
    """/health is EXEMPT from enforcement in phase 2, but still logged."""
    with patch.object(settings, "EDGE_SECRET", "super-secret-123"), patch.object(settings, "EDGE_ENFORCE", True):
        client = TestClient(app)
        with caplog.at_level(logging.WARNING, logger="examind.edge_guard"):
            resp = client.get("/health")
            assert resp.status_code == 200
            assert resp.json()["status"] == "healthy"
            assert any("[EdgeGuard] request without valid edge secret: /health" in r.message for r in caplog.records)


from fastapi import Request

@app.get("/_test_client_ip")
def _test_ip_endpoint(req: Request):
    return {
        "client_host": req.client.host if req.client else None,
        "limiter_ip": get_client_ip(req),
    }


def test_edge_guard_cf_connecting_ip_trusted_when_secret_valid():
    """When edge secret is valid, CF-Connecting-IP is trusted and patches scope['client']."""
    with patch.object(settings, "EDGE_SECRET", "super-secret-123"), patch.object(settings, "EDGE_ENFORCE", True):
        client = TestClient(app)

        cf_ip = "203.0.113.195"
        headers = {
            "X-Examind-Edge-Secret": "super-secret-123",
            "CF-Connecting-IP": cf_ip,
        }

        resp = client.get("/_test_client_ip", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["client_host"] == cf_ip
        assert data["limiter_ip"] == cf_ip


def test_edge_guard_cf_connecting_ip_not_trusted_when_secret_invalid():
    """When edge secret is missing/wrong, CF-Connecting-IP must NOT be trusted."""
    with patch.object(settings, "EDGE_SECRET", "super-secret-123"), patch.object(settings, "EDGE_ENFORCE", False):
        client = TestClient(app)

        spoofed_ip = "198.51.100.99"
        headers = {
            "X-Examind-Edge-Secret": "wrong-secret",
            "CF-Connecting-IP": spoofed_ip,
        }

        resp = client.get("/_test_client_ip", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        # client_host must NOT be spoofed_ip (it will be testclient default e.g. "testclient")
        assert data["client_host"] != spoofed_ip


# ---------------------------------------------------------------------------
# Part 2: Email verification via OTP on registration Tests
# ---------------------------------------------------------------------------

@pytest.fixture
def db_session():
    """In-memory SQLite database session with all schemas created."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    session = TestingSessionLocal()

    # Seed an active Tenant and Registration Code
    tenant = Tenant(
        id=1,
        name="SMA Negeri 1 Testing",
        code="SMAN1TEST",
        domain="sman1test.sch.id",
        is_active=True,
    )
    session.add(tenant)

    reg_code = TenantRegistrationCode(
        id=1,
        code="TESTCODE2026",
        role="student",
        tenant_id=1,
        max_uses=10,
        used_count=0,
        is_active=True,
    )
    session.add(reg_code)

    session.commit()

    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def auth_client(db_session):
    """TestClient overriding get_db dependency with test in-memory SQLite session."""
    from app.core.rate_limit import limiter
    limiter.enabled = False

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    # Disable edge secret checking during auth tests
    with patch.object(settings, "EDGE_SECRET", ""):
        client = TestClient(app, raise_server_exceptions=False)
        yield client
    app.dependency_overrides.clear()
    limiter.enabled = True


def test_register_creates_unverified_user_sends_otp_no_jwt(auth_client, db_session):
    """Registration creates user with is_email_verified=False, sends OTP, and returns no JWT."""
    with patch("app.api.v1.endpoints.auth.send_otp_email", new_callable=AsyncMock) as mock_send_email:
        mock_send_email.return_value = {"id": "msg_123", "mock": True}

        payload = {
            "registration_code": "TESTCODE2026",
            "role": "student",
            "tenant_id": 1,
            "full_name": "Budi Santoso",
            "identifier": "NISN001122",
            "email": "budi.santoso@siswa.sch.id",
            "password": "Password123!",
            "confirm_password": "Password123!",
        }

        resp = auth_client.post("/api/v1/auth/register", json=payload)
        assert resp.status_code == 200
        data = resp.json()

        # Check response structure
        assert data["success"] is True
        assert data["message"] == "Pendaftaran berhasil. Kode verifikasi telah dikirim ke email Anda."
        assert data["data"]["requires_verification"] is True
        assert data["data"]["email"] == "budi.santoso@siswa.sch.id"
        assert data["data"]["expires_in_minutes"] == 10
        # No JWT token in response
        assert "access_token" not in data["data"]

        # Check user in DB is_email_verified is False
        user = db_session.query(User).filter(User.email == "budi.santoso@siswa.sch.id").first()
        assert user is not None
        assert user.is_email_verified is False
        assert user.full_name == "Budi Santoso"

        # Check OTP email was dispatched
        mock_send_email.assert_called_once()
        assert mock_send_email.call_args[1]["to_email"] == "budi.santoso@siswa.sch.id"
        assert mock_send_email.call_args[1]["purpose"] == "email_verification"
        assert mock_send_email.call_args[1]["expires_in_minutes"] == 10

        # Check EmailVerification record created in DB
        otp_record = (
            db_session.query(EmailVerification)
            .filter(EmailVerification.email == "budi.santoso@siswa.sch.id")
            .first()
        )
        assert otp_record is not None
        assert otp_record.purpose == "email_verification"
        assert otp_record.is_used is False


def test_login_unverified_user_returns_403(auth_client, db_session):
    """Login with unverified user must return 403 EMAIL_NOT_VERIFIED without issuing a token."""
    # Create unverified user
    user = User(
        identifier="NISN009988",
        email="unverified@siswa.sch.id",
        password_hash=get_password_hash("Password123!"),
        full_name="Unverified User",
        role="student",
        tenant_id=1,
        is_active=True,
        is_email_verified=False,
    )
    db_session.add(user)
    db_session.commit()

    resp = auth_client.post(
        "/api/v1/auth/login",
        json={"identifier": "NISN009988", "password": "Password123!"},
    )
    assert resp.status_code == 403
    data = resp.json()
    assert data["success"] is False
    assert data["error"]["code"] == "EMAIL_NOT_VERIFIED"
    assert "Email Anda belum diverifikasi" in data["message"]
    assert "data" not in data or data["data"] is None


def test_verify_otp_flips_is_email_verified_and_allows_login(auth_client, db_session):
    """After verifying OTP, is_email_verified flips to True and login succeeds."""
    # Register user first
    with patch("app.api.v1.endpoints.auth.send_otp_email", new_callable=AsyncMock) as mock_send_email:
        mock_send_email.return_value = {"id": "msg_123", "mock": True}

        payload = {
            "registration_code": "TESTCODE2026",
            "role": "student",
            "tenant_id": 1,
            "full_name": "Siti Rahma",
            "identifier": "NISN003344",
            "email": "siti.rahma@siswa.sch.id",
            "password": "Password123!",
            "confirm_password": "Password123!",
        }
        reg_resp = auth_client.post("/api/v1/auth/register", json=payload)
        assert reg_resp.status_code == 200

        # Login fails before verification
        fail_login = auth_client.post(
            "/api/v1/auth/login",
            json={"identifier": "NISN003344", "password": "Password123!"},
        )
        assert fail_login.status_code == 403
        assert fail_login.json()["error"]["code"] == "EMAIL_NOT_VERIFIED"

        # Fetch the generated OTP from DB
        otp_record = (
            db_session.query(EmailVerification)
            .filter(EmailVerification.email == "siti.rahma@siswa.sch.id", EmailVerification.is_used == False)
            .first()
        )
        assert otp_record is not None
        otp_code = otp_record.otp_code

        # Call verify_otp
        verify_resp = auth_client.post(
            "/api/v1/auth/otp/verify",
            json={
                "email": "siti.rahma@siswa.sch.id",
                "otp_code": otp_code,
                "purpose": "email_verification",
            },
        )
        assert verify_resp.status_code == 200
        assert verify_resp.json()["data"]["is_email_verified"] is True

        # Check user in DB
        db_session.expire_all()
        user = db_session.query(User).filter(User.email == "siti.rahma@siswa.sch.id").first()
        assert user.is_email_verified is True

        # Login now succeeds!
        success_login = auth_client.post(
            "/api/v1/auth/login",
            json={"identifier": "NISN003344", "password": "Password123!"},
        )
        assert success_login.status_code == 200
        token_data = success_login.json()["data"]
        assert "access_token" in token_data
        assert token_data["user"]["email"] == "siti.rahma@siswa.sch.id"


def test_re_registration_deletes_stale_unverified_account(auth_client, db_session):
    """Registering again with same email/identifier when unverified deletes stale account and allows fresh registration."""
    with patch("app.api.v1.endpoints.auth.send_otp_email", new_callable=AsyncMock) as mock_send_email:
        mock_send_email.return_value = {"id": "msg_123", "mock": True}

        # 1. First registration
        payload = {
            "registration_code": "TESTCODE2026",
            "role": "student",
            "tenant_id": 1,
            "full_name": "Stale Account",
            "identifier": "NISN_STALE",
            "email": "stale@siswa.sch.id",
            "password": "Password123!",
            "confirm_password": "Password123!",
        }
        resp1 = auth_client.post("/api/v1/auth/register", json=payload)
        assert resp1.status_code == 200

        user1 = db_session.query(User).filter(User.email == "stale@siswa.sch.id").first()
        assert user1 is not None
        user1_id = user1.id
        assert user1.is_email_verified is False

        # 2. Second registration with same email and new password/name
        payload2 = {
            "registration_code": "TESTCODE2026",
            "role": "student",
            "tenant_id": 1,
            "full_name": "Fresh Attempt",
            "identifier": "NISN_STALE",
            "email": "stale@siswa.sch.id",
            "password": "NewPassword456!",
            "confirm_password": "NewPassword456!",
        }
        resp2 = auth_client.post("/api/v1/auth/register", json=payload2)
        assert resp2.status_code == 200

        # Check DB: only 1 user exists and has the new name
        users = db_session.query(User).filter(User.email == "stale@siswa.sch.id").all()
        assert len(users) == 1
        assert users[0].full_name == "Fresh Attempt"
        assert users[0].is_email_verified is False


def test_re_registration_with_verified_user_fails(auth_client, db_session):
    """Registering with an already verified user's email/identifier fails with USER_ALREADY_EXISTS."""
    # Create verified user
    user = User(
        identifier="NISN_VERIFIED",
        email="verified@siswa.sch.id",
        password_hash=get_password_hash("Password123!"),
        full_name="Verified User",
        role="student",
        tenant_id=1,
        is_active=True,
        is_email_verified=True,
    )
    db_session.add(user)
    db_session.commit()

    payload = {
        "registration_code": "TESTCODE2026",
        "role": "student",
        "tenant_id": 1,
        "full_name": "Another Person",
        "identifier": "NISN_VERIFIED",
        "email": "verified@siswa.sch.id",
        "password": "Password123!",
        "confirm_password": "Password123!",
    }
    resp = auth_client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "USER_ALREADY_EXISTS"


def test_register_email_dispatch_failure_rolls_back_user(auth_client, db_session):
    """If send_otp_email raises an exception, the created user is rolled back cleanly."""
    with patch("app.api.v1.endpoints.auth.send_otp_email", new_callable=AsyncMock) as mock_send_email:
        mock_send_email.side_effect = RuntimeError("SMTP connection timeout")

        payload = {
            "registration_code": "TESTCODE2026",
            "role": "student",
            "tenant_id": 1,
            "full_name": "Rollback Test",
            "identifier": "NISN_ROLLBACK",
            "email": "rollback@siswa.sch.id",
            "password": "Password123!",
            "confirm_password": "Password123!",
        }

        # The registration code initial count
        reg_code = db_session.query(TenantRegistrationCode).filter(TenantRegistrationCode.code == "TESTCODE2026").first()
        initial_used = reg_code.used_count

        resp = auth_client.post("/api/v1/auth/register", json=payload)
        assert resp.status_code == 500

        # Check DB: user must NOT exist
        db_session.expire_all()
        user = db_session.query(User).filter(User.email == "rollback@siswa.sch.id").first()
        assert user is None

        # Registration code usage must not be consumed
        reg_code = db_session.query(TenantRegistrationCode).filter(TenantRegistrationCode.code == "TESTCODE2026").first()
        assert reg_code.used_count == initial_used


def test_register_production_mock_guard_raises_503(auth_client, db_session):
    """In production environment, unconfigured email service (mock=True) raises 503 and rolls back user."""
    with patch("app.api.v1.endpoints.auth.send_otp_email", new_callable=AsyncMock) as mock_send_email, \
         patch.object(settings, "ENVIRONMENT", "production"):
        mock_send_email.return_value = {"id": "mock_id", "mock": True}

        payload = {
            "registration_code": "TESTCODE2026",
            "role": "student",
            "tenant_id": 1,
            "full_name": "Prod Guard Test",
            "identifier": "NISN_PROD_GUARD",
            "email": "prodguard@siswa.sch.id",
            "password": "Password123!",
            "confirm_password": "Password123!",
        }

        resp = auth_client.post("/api/v1/auth/register", json=payload)
        assert resp.status_code == 503
        data = resp.json()
        assert data["error"]["code"] == "EMAIL_SERVICE_UNCONFIGURED"

        # User must NOT exist in DB
        db_session.expire_all()
        user = db_session.query(User).filter(User.email == "prodguard@siswa.sch.id").first()
        assert user is None
