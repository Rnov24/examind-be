from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, ConfigDict
from app.schemas.question import QuestionResponse


class ExamQuestionItem(BaseModel):
    question_id: int
    order_index: int = 1
    allocated_points: float = 10.00


class ExamBase(BaseModel):
    title: str
    description: Optional[str] = None
    class_id: int
    duration_minutes: int = 90
    start_time: datetime
    end_time: datetime
    randomize_questions: bool = True
    randomize_options: bool = True
    proctoring_level: str = "dual_camera"  # disabled, single_camera, dual_camera
    explanation_policy: str = "after_exam_closed"  # instant, after_exam_closed
    exam_mode: str = "live"  # live | non_live


class ExamCreate(ExamBase):
    questions: Optional[List[ExamQuestionItem]] = []


class ExamUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    class_id: Optional[int] = None
    duration_minutes: Optional[int] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    randomize_questions: Optional[bool] = None
    randomize_options: Optional[bool] = None
    proctoring_level: Optional[str] = None
    explanation_policy: Optional[str] = None
    exam_mode: Optional[str] = None  # live | non_live
    status: Optional[str] = None


class ExamQuestionResponse(BaseModel):
    id: int
    exam_id: int
    question_id: int
    order_index: int
    allocated_points: float
    question: Optional[QuestionResponse] = None

    model_config = ConfigDict(from_attributes=True)


class ExamResponse(ExamBase):
    id: int
    teacher_id: int
    status: str
    created_at: Optional[datetime] = None
    questions_count: int = 0
    total_points: float = 0.0
    teacher_name: Optional[str] = None
    class_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ExamDetailResponse(ExamResponse):
    exam_questions: List[ExamQuestionResponse] = []
