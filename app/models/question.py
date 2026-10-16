from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, Enum, DateTime, ForeignKey, Numeric, JSON
from sqlalchemy.orm import relationship
from app.core.database import Base


class QuestionBank(Base):
    __tablename__ = "question_banks"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    teacher_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(200), nullable=False)
    subject = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    teacher = relationship("User", back_populates="question_banks")
    questions = relationship("Question", back_populates="bank", cascade="all, delete-orphan")


class Question(Base):
    __tablename__ = "questions"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    bank_id = Column(Integer, ForeignKey("question_banks.id", ondelete="CASCADE"), nullable=False)
    question_type = Column(
        Enum("multiple_choice", "short_essay", "long_essay", name="question_types"),
        nullable=False,
    )
    prompt = Column(Text, nullable=False)
    options_json = Column(JSON, nullable=True)  # [{"id":"A","text":"..."},{"id":"B","text":"..."}]
    correct_answer = Column(Text, nullable=True)  # "A" or ideal answer key for essay
    rubric_json = Column(JSON, nullable=True)  # Multi-dimensional rubric
    explanation = Column(Text, nullable=True)
    difficulty = Column(Enum("easy", "medium", "hard", name="difficulty_levels"), default="medium")
    default_points = Column(Numeric(5, 2), default=10.00)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    bank = relationship("QuestionBank", back_populates="questions")
    exam_questions = relationship("ExamQuestion", back_populates="question", cascade="all, delete-orphan")
    student_answers = relationship("StudentAnswer", back_populates="question")
