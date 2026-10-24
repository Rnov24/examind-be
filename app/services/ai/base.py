from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from app.schemas.question import AIGenerateRequest, AIGenerateData


class AIServiceInterface(ABC):
    @abstractmethod
    def generate_questions(self, request: AIGenerateRequest) -> AIGenerateData:
        pass

    @abstractmethod
    def grade_essay(
        self, prompt: str, rubric: Dict[str, Any], ideal_answer: str, student_answer: str,
        allocated_points: float = 10.0,
    ) -> Dict[str, Any]:
        pass

    @abstractmethod
    def generate_explanation(
        self, prompt: str, correct_answer: str, student_response: str, is_correct: bool
    ) -> str:
        pass

    @abstractmethod
    def chat_assistant(
        self,
        message: str,
        history: Optional[List[Dict[str, str]]] = None,
        context: Optional[str] = None,
        scoped_context: Optional[str] = None,
        api_key: Optional[str] = None,
        role: Optional[str] = None,
    ) -> str:
        """Global AI assistant for answering scoped database queries (grades, tests, schedules)
        and platform educational inquiries.
        """
        pass

    @abstractmethod
    def chat_question_explanation(
        self,
        question_context: Dict[str, Any],
        message: str,
        history: Optional[List[Dict[str, str]]] = None,
        api_key: Optional[str] = None,
    ) -> str:
        """Post-test question-level Socratic tutor for explaining why answers were correct/incorrect,
        clarifying underlying concepts, and answering student doubts.
        """
        pass
