from __future__ import annotations

from typing import Any

from . import config as _config

_FALLBACK_MODEL = "gemma4:e4b"
_FALLBACK_TIMEOUT = 120


def resolve(
    mode: str,
    provider: str = "ollama",
    user_model: str | None = None,
    base_url: str | None = None,
) -> dict[str, Any]:
    """Return {provider, model, base_url, timeout} for the given request context.

    Priority:
    1. cloud_override (if enabled in models.json)
    2. explicit user_model + provider from UI
    3. auto-route by mode from models.json routes
    """
    cfg = _config.get_models()

    cloud = cfg.get("cloud_override", {})
    if cloud.get("enabled"):
        return {
            "provider": cloud.get("provider", "openai"),
            "model": cloud.get("model", "gpt-4.1-mini"),
            "base_url": "https://api.openai.com/v1",
            "timeout": _FALLBACK_TIMEOUT,
        }

    ollama_base = (base_url or cfg.get("ollama_base_url", "http://127.0.0.1:11434")).rstrip("/")
    fallback = cfg.get("fallback", {"model": _FALLBACK_MODEL, "timeout": _FALLBACK_TIMEOUT})

    if user_model:
        if provider == "openai":
            return {
                "provider": "openai",
                "model": user_model,
                "base_url": "https://api.openai.com/v1",
                "timeout": _FALLBACK_TIMEOUT,
            }
        routes = cfg.get("routes") or {}
        mode_cfg = routes.get(mode) or fallback
        timeout = mode_cfg.get("timeout", _FALLBACK_TIMEOUT)
        return {"provider": "ollama", "model": user_model, "base_url": ollama_base, "timeout": timeout}

    routes = cfg.get("routes") or {}
    route = routes.get(mode) or fallback
    return {
        "provider": "ollama",
        "model": route["model"],
        "base_url": ollama_base,
        "timeout": route.get("timeout", _FALLBACK_TIMEOUT),
    }
