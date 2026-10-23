from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from app.schemas.question import QuestionResponse


class AnswerItem(BaseModel):
    question_id: int
    response: Optional[str] = None


class AutosaveRequest(BaseModel):
    session_id: int
    answers: List[AnswerItem]


class AutosaveResponse(BaseModel):
    saved_items_count: int
    last_saved_at: datetime


class ExamStartResponse(BaseModel):
    session_id: int
    exam: Dict[str, Any]
    pairing_token: str
    companion_qr_url: str
    duration_remaining_seconds: int
    questions: List[Dict[str, Any]]
    # ISO timestamp when the student actually began answering (after the
    # setup wizard); None while still preparing. Lets the client skip the
    # wizard on a mid-exam resume.
    begun_at: Optional[datetime] = None


class SubmitExamRequest(BaseModel):
    session_id: int


class SubmitExamResponse(BaseModel):
    session_id: int
    status: str
    submitted_at: datetime
    message: str


class AbortExamRequest(BaseModel):
    session_id: int
    reason: str
    details: Optional[str] = None


class AbortExamResponse(BaseModel):
    session_id: int
    status: str
    aborted_at: datetime
    reason: str
    message: str


class StudentAnswerDetail(BaseModel):
    id: int
    question_id: int
    question_type: str
    prompt: str
    options_json: Optional[Any] = None
    correct_answer: Optional[str] = None
    student_response: Optional[str] = None
    is_correct: Optional[bool] = None
    allocated_points: float
    auto_score: float
    teacher_override_score: Optional[float] = None
    final_score: float
    ai_confidence_level: Optional[str] = None
    ai_grading_rationale: Optional[str] = None
    ai_explanation: Optional[str] = None
    teacher_notes: Optional[str] = None
    rubric_json: Optional[Any] = None


class StudentExamResultResponse(BaseModel):
    session_id: int
    exam_id: int
    exam_title: str
    subject: str
    student_name: str
    student_identifier: str
    status: str
    start_time: datetime
    submit_time: Optional[datetime] = None
    total_score: float
    max_score: float
    integrity_score: int
    explanation_policy: str
    answers: List[StudentAnswerDetail] = []
