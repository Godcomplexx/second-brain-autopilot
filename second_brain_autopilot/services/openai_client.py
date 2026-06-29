from __future__ import annotations

import json
import urllib.request
from typing import Any

_DEFAULT_BASE_URL = "https://api.openai.com/v1"
_DEFAULT_TIMEOUT = 120
_DEFAULT_TEMPERATURE = 0.35


def chat(
    messages: list[dict[str, str]],
    model: str,
    api_key: str,
    base_url: str = _DEFAULT_BASE_URL,
    timeout: int = _DEFAULT_TIMEOUT,
    temperature: float = _DEFAULT_TEMPERATURE,
) -> str:
    body: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        data = json.loads(response.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"]
