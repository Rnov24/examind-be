"""OpenAI-compatible chat providers for EXAMIND: openai, deepseek, openrouter, ollama."""
import logging
from typing import Dict, Any, List, Optional

import httpx

logger = logging.getLogger(__name__)

# Plain HTTPS chat-completions endpoints (OpenAI-compatible).
CHAT_COMPLETIONS_ENDPOINTS = {
    "openai": "https://api.openai.com/v1/chat/completions",
    "deepseek": "https://api.deepseek.com/chat/completions",
}

# Sensible default models per provider (used when the task config does not pin one).
DEFAULT_MODELS = {
    "openai": "gpt-4o-mini",
    "deepseek": "deepseek-chat",
    "openrouter": "openai/gpt-4o-mini",
    "ollama": "llama3.1",
}


def _build_messages(
    message: str,
    history: Optional[List[Dict[str, str]]],
    system_instruction: Optional[str],
) -> List[Dict[str, str]]:
    messages: List[Dict[str, str]] = []
    if system_instruction:
        messages.append({"role": "system", "content": system_instruction})
    for h in history or []:
        role = h.get("role", "user")
        if role not in ("user", "assistant", "system"):
            role = "user"
        messages.append({"role": role, "content": h.get("content", "")})
    messages.append({"role": "user", "content": message})
    return messages


def chat_openai_compat(
    provider: str,
    message: str,
    history: Optional[List[Dict[str, str]]] = None,
    system_instruction: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    temperature: float = 0.5,
    timeout_seconds: float = 30.0,
    json_mode: bool = False,
) -> Optional[str]:
    """Calls an OpenAI-compatible chat-completions endpoint (openai / deepseek).

    Returns reply text, or None on any failure.
    """
    if not api_key:
        logger.info(f"[OpenAICompat] no API key configured for provider={provider}")
        return None
    endpoint = CHAT_COMPLETIONS_ENDPOINTS.get(provider)
    if not endpoint:
        logger.warning(f"[OpenAICompat] no chat endpoint known for provider={provider}")
        return None
    model = model or DEFAULT_MODELS.get(provider, "")

    payload: Dict[str, Any] = {
        "model": model,
        "messages": _build_messages(message, history, system_instruction),
        "temperature": temperature,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    headers = {
        "Authorization": f"Bearer {api_key.strip()}",
        "Content-Type": "application/json",
    }
    try:
        with httpx.Client(timeout=timeout_seconds) as client:
            resp = client.post(endpoint, headers=headers, json=payload)
            if resp.status_code != 200:
                logger.warning(
                    f"[OpenAICompat] provider={provider} status={resp.status_code} body={resp.text[:300]}"
                )
                return None
            data = resp.json()
            choices = data.get("choices") or []
            if choices:
                return (choices[0].get("message") or {}).get("content") or ""
            return None
    except Exception as e:
        logger.warning(f"[OpenAICompat] provider={provider} request failed: {e}")
        return None


def chat_via_ollama(
    message: str,
    history: Optional[List[Dict[str, str]]] = None,
    system_instruction: Optional[str] = None,
    base_url: Optional[str] = None,
    model: Optional[str] = None,
    temperature: float = 0.5,
    timeout_seconds: float = 60.0,
    json_mode: bool = False,
) -> Optional[str]:
    """Calls a local Ollama server via POST {base}/api/chat (Ollama message format).

    Returns reply text, or None on any failure.
    """
    base = (base_url or "http://localhost:11434").strip().rstrip("/")
    url = f"{base}/api/chat"
    model = model or DEFAULT_MODELS["ollama"]

    payload: Dict[str, Any] = {
        "model": model,
        "messages": _build_messages(message, history, system_instruction),
        "stream": False,
        "options": {"temperature": temperature},
    }
    if json_mode:
        payload["format"] = "json"

    try:
        with httpx.Client(timeout=timeout_seconds) as client:
            resp = client.post(url, json=payload)
            if resp.status_code != 200:
                logger.warning(f"[Ollama] status={resp.status_code} body={resp.text[:300]}")
                return None
            data = resp.json()
            return (data.get("message") or {}).get("content") or ""
    except Exception as e:
        logger.warning(f"[Ollama] request failed: {e}")
        return None


def chat_via_provider(
    provider: str,
    message: str,
    history: Optional[List[Dict[str, str]]] = None,
    system_instruction: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    temperature: float = 0.5,
    timeout_seconds: float = 30.0,
    json_mode: bool = False,
) -> Optional[str]:
    """Dispatches to the right OpenAI-compatible chat function by provider name.

    Supported: openai, deepseek, openrouter, ollama. Returns None for unknown providers.
    """
    provider = (provider or "").strip().lower()
    if provider in ("openai", "deepseek"):
        return chat_openai_compat(
            provider=provider,
            message=message,
            history=history,
            system_instruction=system_instruction,
            api_key=api_key,
            model=model,
            temperature=temperature,
            timeout_seconds=timeout_seconds,
            json_mode=json_mode,
        )
    if provider == "openrouter":
        # Single source of truth for OpenRouter chat lives in openrouter_chat.py.
        from app.services.ai.openrouter_chat import chat_via_openrouter
        return chat_via_openrouter(
            message=message,
            history=history,
            system_instruction=system_instruction,
            api_key=api_key,
            model=model,
            temperature=temperature,
            timeout_seconds=timeout_seconds,
            json_mode=json_mode,
        )
    if provider == "ollama":
        return chat_via_ollama(
            message=message,
            history=history,
            system_instruction=system_instruction,
            base_url=api_key,  # for ollama the "key" slot carries OLLAMA_BASE_URL
            model=model,
            temperature=temperature,
            timeout_seconds=timeout_seconds,
            json_mode=json_mode,
        )
    logger.warning(f"[OpenAICompat] unknown provider '{provider}'")
    return None
