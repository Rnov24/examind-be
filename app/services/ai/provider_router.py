"""Round-robin provider router for EXAMIND AI tasks.

Each task (TASK_CHATBOT, TASK_QUESTION_GEN, TASK_ESSAY_GRADING, TASK_TUTOR_CHAT, ...)
can list several providers in its config. route_chat() cycles through them in
round-robin order and tries each one until a provider returns non-empty text.

Round-robin state is in-memory (per task_id) and thread-safe; it resets on
redeploy, which is acceptable.

EXCLUDED: TASK_SHORT_ANSWER_GRADING and TASK_CHATBOT_GUARDRAIL stay on the
Respan/OpenRouter decisions API and must never be routed here.
"""
import json
import logging
import threading
from typing import Dict, Any, List, Optional, Callable

logger = logging.getLogger(__name__)

# Tasks that must stay on the Respan decisions API — never round-robined.
EXCLUDED_TASKS = {"TASK_SHORT_ANSWER_GRADING", "TASK_CHATBOT_GUARDRAIL"}

# Vault key name per provider (ollama uses a base URL, not a key).
PROVIDER_KEY_NAMES = {
    "openai": "OPENAI_API_KEY",
    "claude": "CLAUDE_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "ollama": "OLLAMA_BASE_URL",
}

# Fallback models when the task config does not pin a model for the provider.
DEFAULT_MODELS = {
    "openai": "gpt-4o-mini",
    "claude": "claude-3-5-sonnet-20241022",
    "deepseek": "deepseek-chat",
    "openrouter": "openai/gpt-4o-mini",
    "ollama": "llama3.1",
}

_lock = threading.Lock()
_counters: Dict[str, int] = {}


def _task_defaults() -> Dict[str, Dict[str, Any]]:
    # Lazy import: superadmin pulls in models/db, and must not be imported at module load.
    from app.api.v1.endpoints.superadmin import DEFAULT_AI_TASKS
    return {t["task_id"]: t for t in DEFAULT_AI_TASKS}


def get_task_config(task_id: str) -> Dict[str, Any]:
    """Merged task config: DEFAULT_AI_TASKS defaults overlaid with vault JSON.

    Vault JSON shape: {provider, model, api_key, temperature, max_tokens}.
    providers_supported always comes from the defaults.
    """
    defaults = _task_defaults().get(task_id, {})
    config: Dict[str, Any] = {
        "provider": defaults.get("default_provider", "gemini"),
        "model": defaults.get("default_model", ""),
        "temperature": defaults.get("default_temperature", 0.5),
        "max_tokens": defaults.get("default_max_tokens", 2048),
        "providers_supported": list(defaults.get("providers_supported", ["gemini"])),
        "api_key": "",
        "configured": False,
    }
    try:
        from app.core.secret_manager import get_secret
        raw = get_secret(task_id)
        if raw:
            saved = json.loads(raw)
            if isinstance(saved, dict):
                config["configured"] = True
                for k in ("provider", "model", "api_key", "temperature", "max_tokens"):
                    v = saved.get(k)
                    if v not in (None, ""):
                        config[k] = v
    except Exception as e:
        logger.warning(f"[ProviderRouter] failed to load vault config for {task_id}: {e}")
    return config


def _provider_order(task_id: str, providers: List[str]) -> List[str]:
    """Round-robin rotation: each call for a task starts at the next provider."""
    with _lock:
        idx = _counters.get(task_id, 0)
        _counters[task_id] = idx + 1
    n = len(providers)
    start = idx % n
    return [providers[(start + i) % n] for i in range(n)]


def _resolve_key(provider: str, config: Dict[str, Any]) -> Optional[str]:
    # A task-level dedicated key wins when the task's configured provider matches.
    if config.get("provider") == provider and config.get("api_key"):
        return config["api_key"]
    key_name = PROVIDER_KEY_NAMES.get(provider)
    if not key_name:
        return None
    try:
        from app.core.secret_manager import get_secret
        val = get_secret(key_name)
        if val:
            return val
    except Exception:
        pass
    try:
        from app.core.config import settings
        val = getattr(settings, key_name, "") or ""
        return val.strip() or None
    except Exception:
        return None


def _resolve_model(provider: str, config: Dict[str, Any]) -> str:
    # Honor the task's pinned model for its configured provider; otherwise a sane default.
    if config.get("provider") == provider and config.get("model"):
        return config["model"]
    return DEFAULT_MODELS.get(provider, "")


def _try_provider(
    provider: str,
    config: Dict[str, Any],
    message: str,
    history: Optional[List[Dict[str, str]]],
    system_instruction: Optional[str],
    temperature: float,
    timeout_seconds: float,
    json_mode: bool,
    gemini_fn: Optional[Callable[[], Optional[str]]],
) -> Optional[str]:
    provider = (provider or "").strip().lower()
    if provider == "gemini":
        if gemini_fn is None:
            logger.warning("[ProviderRouter] gemini selected but no gemini_fn supplied; skipping")
            return None
        return gemini_fn()
    if provider == "claude":
        from app.services.ai.claude_chat import chat_via_claude
        return chat_via_claude(
            message=message,
            history=history,
            system_instruction=system_instruction,
            api_key=_resolve_key("claude", config),
            model=_resolve_model("claude", config),
            temperature=temperature,
            timeout_seconds=timeout_seconds,
            json_mode=json_mode,
            max_tokens=int(config.get("max_tokens") or 2048),
        )
    if provider in ("openai", "deepseek", "openrouter", "ollama"):
        from app.services.ai.openai_compat import chat_via_provider
        return chat_via_provider(
            provider=provider,
            message=message,
            history=history,
            system_instruction=system_instruction,
            api_key=_resolve_key(provider, config),
            model=_resolve_model(provider, config),
            temperature=temperature,
            timeout_seconds=timeout_seconds,
            json_mode=json_mode,
        )
    logger.warning(f"[ProviderRouter] unknown provider '{provider}'; skipping")
    return None


def route_chat(
    task_id: str,
    message: str,
    history: Optional[List[Dict[str, str]]] = None,
    system_instruction: Optional[str] = None,
    temperature: Optional[float] = None,
    timeout_seconds: float = 30.0,
    json_mode: bool = False,
    gemini_fn: Optional[Callable[[], Optional[str]]] = None,
) -> Optional[str]:
    """Round-robin chat across the task's providers. Returns text or None if all fail.

    Each call advances the rotation for task_id, then tries providers in rotated
    order until one returns non-empty text.
    """
    if task_id in EXCLUDED_TASKS:
        logger.warning(f"[ProviderRouter] task {task_id} is excluded from round-robin; refusing")
        return None

    config = get_task_config(task_id)
    providers = [p for p in dict.fromkeys(config.get("providers_supported") or []) if p]
    if not providers:
        providers = [config.get("provider") or "gemini"]

    order = _provider_order(task_id, providers)
    temp = float(temperature if temperature is not None else config.get("temperature", 0.5))

    for attempt, provider in enumerate(order, 1):
        try:
            text = _try_provider(
                provider, config, message, history, system_instruction,
                temp, timeout_seconds, json_mode, gemini_fn,
            )
        except Exception as e:
            logger.warning(
                f"[ProviderRouter] task={task_id} provider={provider} attempt={attempt} error={e}"
            )
            continue
        if text and text.strip():
            logger.info(f"[ProviderRouter] task={task_id} provider={provider} attempt={attempt} ok")
            return text.strip()
        logger.warning(
            f"[ProviderRouter] task={task_id} provider={provider} attempt={attempt} failed_or_empty"
        )

    logger.warning(f"[ProviderRouter] task={task_id} all {len(order)} providers failed")
    return None
