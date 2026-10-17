from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, Enum, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    identifier = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(120), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(150), nullable=False)
    role = Column(Enum("superadmin", "admin", "teacher", "student", name="user_roles"), nullable=False, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="SET NULL"), nullable=True, index=True)
    avatar_url = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True, index=True)
    is_email_verified = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    tenant = relationship("Tenant", back_populates="users")
    classes_created = relationship("Class", back_populates="creator", cascade="all, delete-orphan")
    class_memberships = relationship("ClassMember", back_populates="user", cascade="all, delete-orphan")
    question_banks = relationship("QuestionBank", back_populates="teacher", cascade="all, delete-orphan")
    exams_created = relationship("Exam", back_populates="teacher")
    exam_sessions = relationship("ExamSession", back_populates="student", cascade="all, delete-orphan")

    @property
    def tenant_name(self):
        return self.tenant.name if self.tenant else None


