from app.core.config import settings
from app.services.ai.base import AIServiceInterface
from app.services.ai.mock_adapter import mock_ai_service
from app.services.ai.gemini_adapter import gemini_ai_service


def get_ai_service() -> AIServiceInterface:
    if settings.AI_PROVIDER == "gemini":
        return gemini_ai_service
    return mock_ai_service
