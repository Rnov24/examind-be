"""OpenRouter chat adapter (OpenAI-compatible) for the EXAMIND AI Assistant chatbot."""
import logging
import json
from typing import Dict, Any, List, Optional

import httpx

logger = logging.getLogger(__name__)

OPENROUTER_CHAT_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"


def chat_via_openrouter(
    message: str,
    history: Optional[List[Dict[str, str]]] = None,
    system_instruction: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    temperature: float = 0.5,
    timeout_seconds: float = 30.0,
) -> Optional[str]:
    """Calls OpenRouter chat completions API. Returns reply text or None on failure."""
    if not api_key:
        try:
            from app.core.secret_manager import get_secret
            api_key = get_secret("OPENROUTER_API_KEY")
        except Exception:
            api_key = None
    if not api_key:
        from app.core.config import settings
        api_key = settings.OPENROUTER_API_KEY or None
    if not api_key:
        logger.info("[OpenRouterChat] No API key configured.")
        return None

    # Resolve model from TASK_CHATBOT config if not given
    if not model:
        try:
            from app.core.secret_manager import get_secret
            task_raw = get_secret("TASK_CHATBOT")
            if task_raw:
                task_cfg = json.loads(task_raw)
                if isinstance(task_cfg, dict) and task_cfg.get("provider") == "openrouter":
                    model = task_cfg.get("model") or None
                    if task_cfg.get("temperature") is not None:
                        temperature = float(task_cfg["temperature"])
        except Exception:
            pass
    model = model or "openai/gpt-4o-mini"

    messages: List[Dict[str, str]] = []
    if system_instruction:
        messages.append({"role": "system", "content": system_instruction})
    for h in history or []:
        role = h.get("role", "user")
        if role not in ("user", "assistant", "system"):
            role = "user"
        messages.append({"role": role, "content": h.get("content", "")})
    messages.append({"role": "user", "content": message})

    headers = {
        "Authorization": f"Bearer {api_key.strip()}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://examind.id",
        "X-Title": "EXAMIND CBT Education Platform",
    }
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }

    try:
        with httpx.Client(timeout=timeout_seconds) as client:
            resp = client.post(OPENROUTER_CHAT_ENDPOINT, headers=headers, json=payload)
            if resp.status_code != 200:
                logger.error(f"[OpenRouterChat] status {resp.status_code}: {resp.text[:300]}")
                return None
            data = resp.json()
            choices = data.get("choices", [])
            if choices:
                return choices[0].get("message", {}).get("content", "")
            return None
    except Exception as e:
        logger.warning(f"[OpenRouterChat] request failed: {e}")
        return None


def should_use_openrouter_for_chatbot() -> bool:
    """Checks if TASK_CHATBOT is configured to use the openrouter provider."""
    try:
        from app.core.secret_manager import get_secret
        task_raw = get_secret("TASK_CHATBOT")
        if task_raw:
            task_cfg = json.loads(task_raw)
            return isinstance(task_cfg, dict) and task_cfg.get("provider") == "openrouter"
    except Exception:
        pass
    return False
