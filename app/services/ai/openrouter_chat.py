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
    json_mode: bool = False,
    user=None,
    db=None,
) -> Optional[str]:
    """Calls OpenRouter chat completions API. Returns reply text or None on failure.

    When `user` and `db` are provided, scoped chatbot tools are enabled:
    the model may issue up to 2 rounds of tool calls, executed server-side
    with identity enforced from the authenticated `user` (see chatbot_tools).
    Without user/db, behaves exactly as before (single plain call).
    """
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

    messages: List[Dict[str, Any]] = []
    if system_instruction:
        messages.append({"role": "system", "content": system_instruction})
    for h in history or []:
        role = h.get("role", "user")
        if role not in ("user", "assistant", "system"):
            role = "user"
        messages.append({"role": role, "content": h.get("content", "")})
    messages.append({"role": "user", "content": message})

    tools_enabled = user is not None and db is not None

    headers = {
        "Authorization": f"Bearer {api_key.strip()}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://examind.id",
        "X-Title": "EXAMIND CBT Education Platform",
    }
    base_payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }
    if json_mode:
        base_payload["response_format"] = {"type": "json_object"}

    if not tools_enabled:
        return _post(base_payload, headers, timeout_seconds)

    # Scoped tool loop: rounds 0-1 may execute tools, round 2 is tools-free
    # so the model must answer. Bounds latency/cost.
    from app.services.ai.chatbot_tools import TOOL_DEFINITIONS_OPENAI, execute_tool
    convo = list(messages)
    try:
        with httpx.Client(timeout=timeout_seconds) as client:
            for round_idx in range(3):
                payload = dict(base_payload)
                payload["messages"] = list(convo)
                if round_idx < 2:
                    payload["tools"] = TOOL_DEFINITIONS_OPENAI
                else:
                    payload.pop("tools", None)
                resp = client.post(OPENROUTER_CHAT_ENDPOINT, headers=headers, json=payload)
                if resp.status_code != 200:
                    logger.error(f"[OpenRouterChat] status {resp.status_code}: {resp.text[:300]}")
                    return None
                data = resp.json()
                choices = data.get("choices", [])
                if not choices:
                    return None
                msg = choices[0].get("message", {}) or {}
                tool_calls = msg.get("tool_calls") or []
                if not tool_calls:
                    return msg.get("content", "") or None

                # Append the assistant message, then one tool message per call.
                convo.append({
                    "role": "assistant",
                    "content": msg.get("content") or "",
                    "tool_calls": tool_calls,
                })
                for call in tool_calls:
                    fn = (call.get("function") or {})
                    tool_name = fn.get("name", "")
                    try:
                        tool_args = json.loads(fn.get("arguments") or "{}")
                    except Exception:
                        tool_args = {}
                    result_text = execute_tool(tool_name, user, db, tool_args)
                    logger.info(
                        f"[OpenRouterChat] tool round {round_idx + 1}: executed {tool_name} "
                        f"for user_id={getattr(user, 'id', '?')}"
                    )
                    convo.append({
                        "role": "tool",
                        "tool_call_id": call.get("id", ""),
                        "content": result_text,
                    })
        return None
    except Exception as e:
        logger.warning(f"[OpenRouterChat] request failed: {e}")
        return None


def _post(payload: Dict[str, Any], headers: Dict[str, str], timeout_seconds: float) -> Optional[str]:
    """Single plain chat request (no tools)."""
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
