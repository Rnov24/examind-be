from datetime import datetime
from typing import List, Optional, Dict, Any, Union
from pydantic import BaseModel, Field, ConfigDict


class OptionSchema(BaseModel):
    id: str  # e.g. "A", "B", "C", "D"
    text: str
    is_correct: Optional[bool] = None
    rationale: Optional[str] = None


class RubricDimension(BaseModel):
    max: float
    criteria: str


class RubricSchema(BaseModel):
    dimension_1_concept: RubricDimension = Field(
        default_factory=lambda: RubricDimension(max=40, criteria="Pemahaman esensi konsep materi")
    )
    dimension_2_argument: RubricDimension = Field(
        default_factory=lambda: RubricDimension(max=30, criteria="Kelengkapan bukti dan alur penalaran")
    )
    dimension_3_terminology: RubricDimension = Field(
        default_factory=lambda: RubricDimension(max=15, criteria="Ketepatan istilah teknis/ilmiah")
    )
    dimension_4_clarity: RubricDimension = Field(
        default_factory=lambda: RubricDimension(max=15, criteria="Runtutan logika dan kejelasan bahasa")
    )


class QuestionBase(BaseModel):
    question_type: str = "multiple_choice"  # multiple_choice, short_essay, long_essay
    prompt: str
    options_json: Optional[Union[List[OptionSchema], List[Dict[str, Any]]]] = None
    correct_answer: Optional[str] = None
    rubric_json: Optional[Union[RubricSchema, Dict[str, Any]]] = None
    explanation: Optional[str] = None
    difficulty: str = "medium"  # easy, medium, hard
    default_points: float = 10.00


class QuestionCreate(QuestionBase):
    bank_id: Optional[int] = None


class QuestionUpdate(BaseModel):
    question_type: Optional[str] = None
    prompt: Optional[str] = None
    options_json: Optional[Union[List[OptionSchema], List[Dict[str, Any]]]] = None
    correct_answer: Optional[str] = None
    rubric_json: Optional[Union[RubricSchema, Dict[str, Any]]] = None
    explanation: Optional[str] = None
    difficulty: Optional[str] = None
    default_points: Optional[float] = None


class QuestionResponse(QuestionBase):
    id: int
    bank_id: int
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class QuestionBankBase(BaseModel):
    title: str
    subject: str
    description: Optional[str] = None


class QuestionBankCreate(QuestionBankBase):
    pass


class QuestionBankUpdate(BaseModel):
    title: Optional[str] = None
    subject: Optional[str] = None
    description: Optional[str] = None


class QuestionBankResponse(QuestionBankBase):
    id: int
    teacher_id: int
    created_at: Optional[datetime] = None
    questions_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class QuestionBankDetailResponse(QuestionBankResponse):
    questions: List[QuestionResponse] = []


class AIGenerateRequest(BaseModel):
    subject: str = "Fisika"
    topic_content: str
    grade_level: str = "12"
    mcq_count: int = 5
    essay_count: int = 2
    difficulty: str = "medium"
    api_key: Optional[str] = None


class GeneratedQuestionMCQ(BaseModel):
    prompt: str
    difficulty: str = "medium"
    bloom_level: str = "C3"
    options: List[OptionSchema]
    correct_option_id: str
    explanation: str
    points: float = 10.0


class GeneratedQuestionEssay(BaseModel):
    prompt: str
    difficulty: str = "hard"
    bloom_level: str = "C4"
    rubric: Dict[str, Any]
    ideal_answer: Optional[str] = None
    explanation: Optional[str] = None
    points: float = 20.0


class AIGenerateData(BaseModel):
    mcq_questions: List[GeneratedQuestionMCQ]
    essay_questions: List[GeneratedQuestionEssay]
