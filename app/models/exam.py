from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, Boolean, Enum, DateTime, ForeignKey, Numeric, UniqueConstraint
from sqlalchemy.orm import relationship
from app.core.database import Base


class Exam(Base):
    __tablename__ = "exams"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    teacher_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    class_id = Column(Integer, ForeignKey("classes.id", ondelete="RESTRICT"), nullable=False)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    duration_minutes = Column(Integer, nullable=False)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    randomize_questions = Column(Boolean, default=True)
    randomize_options = Column(Boolean, default=True)
    proctoring_level = Column(
        Enum("disabled", "single_camera", "dual_camera", name="proctoring_levels"),
        default="dual_camera",
    )
    explanation_policy = Column(
        Enum("instant", "after_exam_closed", name="explanation_policies"),
        default="after_exam_closed",
    )
    status = Column(
        Enum("draft", "published", "in_progress", "completed", "archived", name="exam_statuses"),
        default="draft",
    )
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    teacher = relationship("User", back_populates="exams_created")
    class_ = relationship("Class", back_populates="exams")
    exam_questions = relationship(
        "ExamQuestion",
        back_populates="exam",
        cascade="all, delete-orphan",
        order_by="ExamQuestion.order_index",
    )
    sessions = relationship("ExamSession", back_populates="exam", cascade="all, delete-orphan")


class ExamQuestion(Base):
    __tablename__ = "exam_questions"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    exam_id = Column(Integer, ForeignKey("exams.id", ondelete="CASCADE"), nullable=False)
    question_id = Column(Integer, ForeignKey("questions.id", ondelete="CASCADE"), nullable=False)
    order_index = Column(Integer, nullable=False)
    allocated_points = Column(Numeric(5, 2), nullable=False, default=10.00)

    __table_args__ = (
        UniqueConstraint("exam_id", "question_id", name="uq_exam_question"),
    )

    # Relationships
    exam = relationship("Exam", back_populates="exam_questions")
    question = relationship("Question", back_populates="exam_questions")
