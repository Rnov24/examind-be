from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, Boolean, Enum, DateTime, ForeignKey, Numeric, JSON, UniqueConstraint
from sqlalchemy.orm import relationship
from app.core.database import Base


class ExamSession(Base):
    __tablename__ = "exam_sessions"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    exam_id = Column(Integer, ForeignKey("exams.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    start_time = Column(DateTime, default=datetime.utcnow, nullable=False)
    submit_time = Column(DateTime, nullable=True)
    status = Column(
        Enum("in_progress", "submitted", "grading_in_progress", "graded", "aborted", name="session_statuses"),
        default="in_progress",
        index=True,
    )
    total_score = Column(Numeric(5, 2), default=0.00)
    integrity_score = Column(Integer, default=100)
    companion_paired = Column(Boolean, default=False)
    client_ip = Column(String(45), nullable=True)
    user_agent = Column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint("exam_id", "student_id", name="uq_student_exam"),
    )

    # Relationships
    exam = relationship("Exam", back_populates="sessions")
    student = relationship("User", back_populates="exam_sessions")
    answers = relationship("StudentAnswer", back_populates="session", cascade="all, delete-orphan")
    autosave_snapshot = relationship("AutosaveSnapshot", back_populates="session", uselist=False, cascade="all, delete-orphan")
    proctoring_logs = relationship("ProctoringLog", back_populates="session", cascade="all, delete-orphan")


class StudentAnswer(Base):
    __tablename__ = "student_answers"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey("exam_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    question_id = Column(Integer, ForeignKey("questions.id", ondelete="CASCADE"), nullable=False, index=True)
    student_response = Column(Text, nullable=True)
    is_correct = Column(Boolean, nullable=True)
    auto_score = Column(Numeric(5, 2), default=0.00)
    teacher_override_score = Column(Numeric(5, 2), nullable=True)
    final_score = Column(Numeric(5, 2), default=0.00)
    ai_confidence_level = Column(Enum("low", "medium", "high", name="ai_confidence_levels"), nullable=True, index=True)
    ai_grading_rationale = Column(Text, nullable=True)
    ai_explanation = Column(Text, nullable=True)
    teacher_notes = Column(Text, nullable=True)
    graded_at = Column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint("session_id", "question_id", name="uq_session_question"),
    )

    # Relationships
    session = relationship("ExamSession", back_populates="answers")
    question = relationship("Question", back_populates="student_answers")


class AutosaveSnapshot(Base):
    __tablename__ = "autosave_snapshots"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey("exam_sessions.id", ondelete="CASCADE"), unique=True, nullable=False)
    answers_payload = Column(JSON, nullable=False)
    last_saved_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    session = relationship("ExamSession", back_populates="autosave_snapshot")
