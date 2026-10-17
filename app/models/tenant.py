from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, Enum, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base


class Tenant(Base):
    __tablename__ = "tenants"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(150), nullable=False)
    code = Column(String(50), unique=True, nullable=False, index=True)
    domain = Column(String(100), unique=True, nullable=True)
    subscription_plan = Column(
        Enum("starter", "pro", "enterprise", name="tenant_plans"),
        default="pro",
        nullable=False,
    )
    subscription_status = Column(
        Enum("active", "trial", "past_due", "canceled", name="tenant_subscription_statuses"),
        default="active",
        nullable=False,
    )
    max_students = Column(Integer, default=500, nullable=False)
    max_teachers = Column(Integer, default=50, nullable=False)
    max_storage_gb = Column(Integer, default=10, nullable=False)
    ai_credits_monthly = Column(Integer, default=1000, nullable=False)
    ai_credits_used = Column(Integer, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    subscription_due_date = Column(DateTime, nullable=True)
    grace_period_ends = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    users = relationship("User", back_populates="tenant", cascade="all, delete-orphan")
    registration_codes = relationship("TenantRegistrationCode", back_populates="tenant", cascade="all, delete-orphan")
    reminder_logs = relationship("SubscriptionReminderLog", back_populates="tenant", cascade="all, delete-orphan")


class SubscriptionReminderLog(Base):
    __tablename__ = "subscription_reminders_log"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    stage = Column(String(50), nullable=False, index=True)
    sent_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    tenant = relationship("Tenant", back_populates="reminder_logs")


class TenantRegistrationCode(Base):
    __tablename__ = "tenant_registration_codes"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(Enum("admin", "teacher", "student", name="registration_code_roles"), nullable=False, index=True)
    code = Column(String(50), unique=True, nullable=False, index=True)
    description = Column(String(255), nullable=True)
    max_uses = Column(Integer, default=0, nullable=False)  # 0 = unlimited
    used_count = Column(Integer, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    tenant = relationship("Tenant", back_populates="registration_codes")

