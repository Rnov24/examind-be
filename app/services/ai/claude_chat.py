"""Anthropic Claude chat adapter via the Messages API."""
import logging
from typing import Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

CLAUDE_MESSAGES_ENDPOINT = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"

DEFAULT_CLAUDE_MODEL = "claude-3-5-sonnet-20241022"


def chat_via_claude(
    message: str,
    history: Optional[List[Dict[str, str]]] = None,
    system_instruction: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    temperature: float = 0.5,
    timeout_seconds: float = 30.0,
    json_mode: bool = False,
    max_tokens: int = 2048,
) -> Optional[str]:
    """Calls the Anthropic Messages API. Returns reply text, or None on any failure.

    The Messages API has no native JSON mode; when json_mode is True we instruct
    the model to emit pure JSON in the system prompt instead.
    """
    if not api_key:
        logger.info("[Claude] no API key configured")
        return None
    model = model or DEFAULT_CLAUDE_MODEL

    system_text = system_instruction or ""
    if json_mode:
        system_text = (
            system_text
            + "\n\nOutput pure JSON only. No markdown fences, no commentary, no extra text."
        )

    messages: List[Dict[str, str]] = []
    for h in history or []:
        role = h.get("role", "user")
        if role not in ("user", "assistant"):
            role = "user"
        messages.append({"role": role, "content": h.get("content", "")})
    messages.append({"role": "user", "content": message})

    headers = {
        "x-api-key": api_key.strip(),
        "anthropic-version": ANTHROPIC_VERSION,
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "max_tokens": max(1, int(max_tokens)),
        "system": system_text,
        "messages": messages,
        "temperature": temperature,
    }
    try:
        with httpx.Client(timeout=timeout_seconds) as client:
            resp = client.post(CLAUDE_MESSAGES_ENDPOINT, headers=headers, json=payload)
            if resp.status_code != 200:
                logger.warning(f"[Claude] status={resp.status_code} body={resp.text[:300]}")
                return None
            data = resp.json()
            blocks = data.get("content") or []
            texts = [
                b.get("text", "")
                for b in blocks
                if isinstance(b, dict) and b.get("type") == "text"
            ]
            return "".join(texts).strip() or None
    except Exception as e:
        logger.warning(f"[Claude] request failed: {e}")
        return None
