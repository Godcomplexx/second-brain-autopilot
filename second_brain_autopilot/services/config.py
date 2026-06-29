from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent

_FILE_MAP = {
    "obsidian": "obsidian.json",
    "models":   "models.json",
    "app":      "app_config.json",
}

_CACHE: dict[str, dict[str, Any]] = {}


def _load(key: str) -> dict[str, Any]:
    if key not in _CACHE:
        path = _ROOT / "config" / _FILE_MAP[key]
        if not path.exists():
            raise FileNotFoundError(
                f"Config file not found: {path}\n"
                f"Copy {path.stem}.example.json to {path.name} and fill in your settings."
            )
        _CACHE[key] = json.loads(path.read_text(encoding="utf-8"))
    return _CACHE[key]


def get_obsidian() -> dict[str, Any]:
    return _load("obsidian")


def get_app() -> dict[str, Any]:
    return _load("app")


def get_models() -> dict[str, Any]:
    return _load("models")


def invalidate(key: str) -> None:
    _CACHE.pop(key, None)
