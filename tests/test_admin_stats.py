import re
import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.exc import OperationalError

from app.main import app
from app.core.database import Base, get_db
from app.core.dependencies import require_admin
from app.models.user import User
from app.services.proctoring.websocket_hub import ws_hub


@pytest.fixture
def db_session():
    """In-memory SQLite database session."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    session = TestingSessionLocal()
    admin = User(
        id=1,
        identifier="ADMIN-TEST",
        email="admin@test.sch.id",
        password_hash="fakehash",
        full_name="Admin Test",
        role="admin",
        is_active=True,
    )
    session.add(admin)
    session.commit()

    try:
        yield session
    finally:
        session.close()


def test_admin_stats_database_status_latency_and_camera_count(db_session):
    admin_user = db_session.query(User).filter(User.role == "admin").first()

    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[require_admin] = lambda: admin_user

    # Initial state: 0 active cameras
    saved_streams = dict(ws_hub.companion_streams)
    ws_hub.companion_streams.clear()

    try:
        client = TestClient(app)
        resp = client.get("/api/v1/admin/stats")
        assert resp.status_code == 200
        data = resp.json()["data"]

        # 1. database_status must report real round-trip latency
        assert re.match(r"^Connected \(\d+ ms\)$", data["database_status"])
        assert "Connected (MySQL" not in data["database_status"]

        # 2. edge_cv_status must report active cameras honestly
        assert data["edge_cv_status"] == "0 kamera terhubung"
        assert "Online (Client" not in data["edge_cv_status"]

        # 3. Test with active companion camera streams
        ws_hub.companion_streams[101] = MagicMock()
        ws_hub.companion_streams[102] = MagicMock()

        resp2 = client.get("/api/v1/admin/stats")
        assert resp2.status_code == 200
        data2 = resp2.json()["data"]
        assert data2["edge_cv_status"] == "2 kamera terhubung"
    finally:
        ws_hub.companion_streams.clear()
        ws_hub.companion_streams.update(saved_streams)
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(require_admin, None)


def test_admin_stats_db_failure_surfaces_uncaught(db_session):
    """Ensure query failures are not caught-and-faked."""
    admin_user = db_session.query(User).filter(User.role == "admin").first()

    mock_db = MagicMock(wraps=db_session)
    mock_db.execute.side_effect = OperationalError("SELECT 1", {}, Exception("DB down"))

    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[require_admin] = lambda: admin_user

    try:
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/admin/stats")
        # Should fail with 500 or error, NOT return 200 with fake status
        assert resp.status_code == 500
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(require_admin, None)
