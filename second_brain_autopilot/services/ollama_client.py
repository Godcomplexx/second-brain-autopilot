from __future__ import annotations

import json
import urllib.request
from typing import Any

_DEFAULT_BASE_URL = "http://127.0.0.1:11434"
_DEFAULT_TIMEOUT = 180
_DEFAULT_TEMPERATURE = 0.35


def chat(
    messages: list[dict[str, str]],
    model: str,
    base_url: str = _DEFAULT_BASE_URL,
    timeout: int = _DEFAULT_TIMEOUT,
    temperature: float = _DEFAULT_TEMPERATURE,
) -> str:
    body: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": temperature},
    }
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/chat",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        data = json.loads(response.read().decode("utf-8"))
    return data["message"]["content"]


def list_models(
    base_url: str = _DEFAULT_BASE_URL,
    timeout: int = 2,
) -> list[str]:
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/tags",
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        data = json.loads(response.read().decode("utf-8"))
    return [m.get("name") for m in data.get("models", [])]
