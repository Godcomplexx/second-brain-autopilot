"""Generate a validated tracking-system config without persisting it."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from . import aggregator, llm_router, ollama_client, openai_client
from .system_schema import normalize_system_config

_PROMPT_FILE = Path(__file__).resolve().parent.parent / "prompts" / "system_builder.txt"
_INPUT_KEYS = (
    "main_goal",
    "time_horizon",
    "current_situation",
    "track_items",
    "constraints",
    "style",
)


def _call(messages: list[dict[str, str]], route: dict[str, Any], api_key: str) -> str:
    if route["provider"] == "openai":
        return openai_client.chat(
            messages,
            route["model"],
            api_key,
            base_url=route["base_url"],
            timeout=route["timeout"],
        )
    return ollama_client.chat(
        messages,
        route["model"],
        base_url=route["base_url"],
        timeout=route["timeout"],
    )


def generate(
    request: dict[str, Any],
    *,
    provider: str = "ollama",
    api_key: str = "",
    user_model: str | None = None,
    base_url: str | None = None,
) -> dict[str, Any]:
    goal = request.get("main_goal")
    if not isinstance(goal, str) or not goal.strip():
        raise ValueError("main_goal must be a non-empty string")

    context: dict[str, str] = {}
    for key in _INPUT_KEYS:
        value = request.get(key, "")
        if value is None:
            value = ""
        if not isinstance(value, str):
            raise ValueError(f"{key} must be a string")
        if len(value) > 4000:
            raise ValueError(f"{key} must be at most 4000 characters")
        context[key] = value.strip()

    messages = [
        {
            "role": "system",
            "content": _PROMPT_FILE.read_text(encoding="utf-8").strip(),
        },
        {
            "role": "user",
            "content": json.dumps(context, ensure_ascii=False, indent=2),
        },
    ]
    route = llm_router.resolve(
        mode="system_builder",
        provider=provider,
        user_model=user_model,
        base_url=base_url,
    )

    last_error: Exception | None = None
    for attempt in range(2):
        try:
            raw = _call(messages, route, api_key)
            parsed = aggregator._extract_json(raw)
            return normalize_system_config(parsed)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt == 0:
                time.sleep(0.25)
    assert last_error is not None
    raise last_error
