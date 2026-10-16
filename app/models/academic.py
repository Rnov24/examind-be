from datetime import datetime
from sqlalchemy import Column, Integer, String, Enum, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from app.core.database import Base


class Class(Base):
    __tablename__ = "classes"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    grade_level = Column(String(20), nullable=False)
    academic_year = Column(String(20), nullable=False)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    creator = relationship("User", back_populates="classes_created")
    members = relationship("ClassMember", back_populates="class_", cascade="all, delete-orphan")
    exams = relationship("Exam", back_populates="class_")


class ClassMember(Base):
    __tablename__ = "class_members"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    class_id = Column(Integer, ForeignKey("classes.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role = Column(Enum("teacher", "student", name="class_member_roles"), nullable=False)
    joined_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("class_id", "user_id", name="uq_class_user"),
    )

    # Relationships
    class_ = relationship("Class", back_populates="members")
    user = relationship("User", back_populates="class_memberships")
