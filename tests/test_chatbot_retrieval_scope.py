import pytest
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # Ensure all SQLAlchemy models are registered
from app.core.database import Base
from app.core.cache import memory_cache
from app.models.tenant import Tenant, TenantRegistrationCode
from app.models.user import User
from app.models.academic import Class, ClassMember
from app.models.exam import Exam
from app.models.session import ExamSession
from app.models.proctoring import ProctoringLog
from app.models.secret import SystemSecret
from app.services.ai.retrieval import build_scoped_user_context

# Secret values used for seeding - must NEVER appear in any context
RAW_SECRET_1 = "SUPER_SECRET_VALUE_DO_NOT_LEAK_XYZ123"
RAW_SECRET_2 = "ANOTHER_SECRET_RE_API_KEY_456"


@pytest.fixture
def db_session():
    """In-memory SQLite database session with seeded multi-tenant data."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()

    # Clear memory cache before and after tests
    memory_cache.clear()

    now = datetime.utcnow()

    # 1. Seed Tenants
    t1 = Tenant(
        id=1,
        name="SMA Negeri 1 Harapan",
        code="SMAN1",
        subscription_plan="pro",
        subscription_status="active",
        is_active=True,
        subscription_due_date=now + timedelta(days=5),
    )
    t2 = Tenant(
        id=2,
        name="SMA Swasta Cendekia",
        code="SMACEN",
        subscription_plan="starter",
        subscription_status="active",
        is_active=True,
        subscription_due_date=now + timedelta(days=10),
    )
    session.add_all([t1, t2])
    session.commit()

    # 2. Seed Users across roles
    u_superadmin = User(
        id=1,
        identifier="SA-001",
        email="superadmin@examind.id",
        password_hash="fakehash",
        full_name="Super Administrator",
        role="superadmin",
        is_active=True,
        tenant_id=None,
    )
    u_admin1 = User(
        id=2,
        identifier="ADM-SMAN1",
        email="admin@sman1.sch.id",
        password_hash="fakehash",
        full_name="Admin SMAN 1",
        role="admin",
        is_active=True,
        tenant_id=1,
    )
    u_admin2 = User(
        id=3,
        identifier="ADM-SMACEN",
        email="admin@cendekia.sch.id",
        password_hash="fakehash",
        full_name="Admin Cendekia",
        role="admin",
        is_active=True,
        tenant_id=2,
    )
    u_teacher1 = User(
        id=4,
        identifier="GURU-SMAN1",
        email="guru@sman1.sch.id",
        password_hash="fakehash",
        full_name="Guru Fisika SMAN1",
        role="teacher",
        is_active=True,
        tenant_id=1,
    )
    u_student1 = User(
        id=5,
        identifier="SISWA-SMAN1",
        email="budi@sman1.sch.id",
        password_hash="fakehash",
        full_name="Budi Pratama",
        role="student",
        is_active=True,
        tenant_id=1,
    )
    u_teacher2 = User(
        id=6,
        identifier="GURU-SMACEN",
        email="guru@cendekia.sch.id",
        password_hash="fakehash",
        full_name="Guru Kimia Cendekia",
        role="teacher",
        is_active=True,
        tenant_id=2,
    )
    u_student2 = User(
        id=7,
        identifier="SISWA-SMACEN",
        email="ani@cendekia.sch.id",
        password_hash="fakehash",
        full_name="Ani Wijaya",
        role="student",
        is_active=True,
        tenant_id=2,
    )
    session.add_all([
        u_superadmin, u_admin1, u_admin2,
        u_teacher1, u_student1, u_teacher2, u_student2,
    ])
    session.commit()

    # 3. Seed Classes and ClassMembers
    c1 = Class(id=1, name="Kelas X IPA 1", grade_level="10", academic_year="2026/2027", created_by=4)
    c2 = Class(id=2, name="Kelas XI IPA 2", grade_level="11", academic_year="2026/2027", created_by=6)
    session.add_all([c1, c2])
    session.commit()

    cm1 = ClassMember(id=1, class_id=1, user_id=5, role="student")
    cm2 = ClassMember(id=2, class_id=2, user_id=7, role="student")
    session.add_all([cm1, cm2])
    session.commit()

    # 4. Seed Exams and Sessions
    e1 = Exam(
        id=1,
        teacher_id=4,
        class_id=1,
        title="Ujian Fisika Dasar",
        duration_minutes=60,
        start_time=now - timedelta(days=2),
        end_time=now + timedelta(days=2),
        status="published",
    )
    e2 = Exam(
        id=2,
        teacher_id=6,
        class_id=2,
        title="Ujian Kimia Organik",
        duration_minutes=60,
        start_time=now - timedelta(days=2),
        end_time=now + timedelta(days=2),
        status="published",
    )
    session.add_all([e1, e2])
    session.commit()

    sess1 = ExamSession(
        id=1,
        exam_id=1,
        student_id=5,
        start_time=now - timedelta(days=1),
        submit_time=now - timedelta(hours=22),
        status="graded",
        total_score=88.5,
        integrity_score=95,
    )
    sess2 = ExamSession(
        id=2,
        exam_id=2,
        student_id=7,
        start_time=now - timedelta(days=1),
        submit_time=now - timedelta(hours=22),
        status="graded",
        total_score=72.0,
        integrity_score=68,
    )
    session.add_all([sess1, sess2])
    session.commit()

    # 5. Seed Proctoring Log
    plog = ProctoringLog(
        id=1,
        session_id=1,
        event_type="tab_switch",
        camera_source="system_event",
        severity="low",
        event_timestamp=now - timedelta(hours=23),
        reviewed_by_teacher=False,
    )
    session.add(plog)
    session.commit()

    # 6. Seed Registration Codes
    rc1 = TenantRegistrationCode(
        id=1,
        tenant_id=1,
        role="teacher",
        code="REG-SMAN1-GURU-2026",
        description="Kode Guru SMAN 1",
        max_uses=10,
        used_count=1,
        is_active=True,
    )
    rc2 = TenantRegistrationCode(
        id=2,
        tenant_id=2,
        role="student",
        code="REG-CENDEKIA-MURID-2026",
        description="Kode Siswa Cendekia",
        max_uses=50,
        used_count=5,
        is_active=True,
    )
    session.add_all([rc1, rc2])
    session.commit()

    # 7. Seed Secrets metadata with secret values
    sec1 = SystemSecret(
        id=1,
        key_name="GEMINI_API_KEY",
        service_name="gemini",
        encrypted_value=RAW_SECRET_1,
        description="Gemini Model API Key",
        is_active=True,
    )
    sec2 = SystemSecret(
        id=2,
        key_name="RESEND_API_KEY",
        service_name="resend",
        encrypted_value=RAW_SECRET_2,
        description="Resend Transactional Mail",
        is_active=True,
    )
    session.add_all([sec1, sec2])
    session.commit()

    try:
        yield session
    finally:
        memory_cache.clear()
        session.close()
        Base.metadata.drop_all(bind=engine)


def test_superadmin_retrieval_scope_contains_all_platform_data(db_session):
    """Superadmin must receive platform-wide data: all tenants, finance, codes, secret names (no secret values)."""
    superadmin = db_session.query(User).filter(User.role == "superadmin").first()
    memory_cache.clear()

    context = build_scoped_user_context(superadmin, db_session)

    # 1. Contains both tenant names and codes
    assert "SMA Negeri 1 Harapan" in context
    assert "SMAN1" in context
    assert "SMA Swasta Cendekia" in context
    assert "SMACEN" in context

    # 2. Contains SaaS finance summary (MRR, ARR, ARPU)
    assert "MRR" in context
    assert "ARR" in context
    assert "ARPU" in context

    # 3. Contains registration code values for onboarding
    assert "REG-SMAN1-GURU-2026" in context
    assert "REG-CENDEKIA-MURID-2026" in context

    # 4. Contains secret NAMES and providers (metadata only)
    assert "GEMINI_API_KEY" in context
    assert "RESEND_API_KEY" in context
    assert "gemini" in context.lower()

    # 5. NEVER contains secret values
    assert RAW_SECRET_1 not in context
    assert RAW_SECRET_2 not in context

    # 6. Contains proctoring aggregates and subscription due dates
    assert "tab_switch" in context or "Integritas" in context
    assert "Jatuh Tempo" in context or "due" in context.lower()


def test_admin_retrieval_scope_is_isolated_to_own_tenant(db_session):
    """Tenant Admin must only see their own tenant's data, not other tenants' data."""
    admin1 = db_session.query(User).filter(User.identifier == "ADM-SMAN1").first()
    memory_cache.clear()

    context = build_scoped_user_context(admin1, db_session)

    # 1. Contains own tenant data
    assert "SMA Negeri 1 Harapan" in context
    assert "REG-SMAN1-GURU-2026" in context

    # 2. Must NOT contain other tenant's name, code, or registration codes
    assert "SMA Swasta Cendekia" not in context
    assert "SMACEN" not in context
    assert "REG-CENDEKIA-MURID-2026" not in context

    # 3. NEVER contains secret values
    assert RAW_SECRET_1 not in context
    assert RAW_SECRET_2 not in context


def test_teacher_and_student_never_leak_other_tenants_or_secrets(db_session):
    """Teacher and Student contexts must NOT leak other tenants, registration codes, or secret names/values."""
    teacher1 = db_session.query(User).filter(User.identifier == "GURU-SMAN1").first()
    student1 = db_session.query(User).filter(User.identifier == "SISWA-SMAN1").first()

    for user in [teacher1, student1]:
        memory_cache.clear()
        context = build_scoped_user_context(user, db_session)

        # Must not leak other tenant data
        assert "SMA Swasta Cendekia" not in context
        assert "SMACEN" not in context
        assert "REG-CENDEKIA-MURID-2026" not in context
        assert "REG-SMAN1-GURU-2026" not in context

        # Must not leak secret names or providers
        assert "GEMINI_API_KEY" not in context
        assert "RESEND_API_KEY" not in context

        # Must never leak secret values
        assert RAW_SECRET_1 not in context
        assert RAW_SECRET_2 not in context


def test_global_audit_no_secret_value_in_any_context(db_session):
    """Exhaustive check: iterate over every user in the database, verifying 0 secret values leaked."""
    users = db_session.query(User).all()
    assert len(users) >= 7

    for u in users:
        memory_cache.clear()
        ctx = build_scoped_user_context(u, db_session)

        # Strict assertion against secret values
        assert RAW_SECRET_1 not in ctx, f"Secret 1 leaked for role {u.role} (user {u.identifier})"
        assert RAW_SECRET_2 not in ctx, f"Secret 2 leaked for role {u.role} (user {u.identifier})"
