from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from app.core.config import settings


def _connect_args() -> dict:
    """TiDB Cloud (and other managed MySQL) requires TLS.

    Enabled automatically for tidbcloud hosts, or explicitly via DB_SSL_CA.
    Uses certifi's CA bundle so it works in minimal containers (Modal, etc.).
    Local XAMPP (no TLS) is untouched.
    """
    url = settings.DATABASE_URL or ""
    ca_path = settings.DB_SSL_CA
    if ca_path or "tidbcloud.com" in url:
        import certifi

        return {"ssl": {"ca": ca_path or certifi.where()}}
    return {}


# Engine configuration with connection pooling and keep-alive
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=3600,
    echo=False,
    connect_args=_connect_args(),
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """FastAPI Dependency for database session lifecycle."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
