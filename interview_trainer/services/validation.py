"""Input validation helpers for API handlers.

Each function raises ValueError with a human-readable message on invalid input.
Callers translate ValueError → HTTP 400.
"""
from __future__ import annotations

from typing import Any

from . import storage

VALID_FOLDER_KEYS = frozenset({
    "knowledge_folder",
    "areas_folder",
    "projects_folder",
    "tracking_folder",
    "archive_folder",
})


def require_str(body: dict[str, Any], key: str) -> str:
    val = body.get(key, "")
    if not isinstance(val, str) or not val.strip():
        raise ValueError(f"'{key}' is required and must be a non-empty string")
    return val.strip()


def require_list(body: dict[str, Any], key: str) -> list:
    val = body.get(key)
    if not isinstance(val, list) or len(val) == 0:
        raise ValueError(f"'{key}' is required and must be a non-empty list")
    return val


def validate_source_rel(source_rel: str) -> None:
    """Raise ValueError if source_rel is unsafe."""
    try:
        storage.safe_resolve(source_rel)
    except storage.PathTraversalError as exc:
        raise ValueError(str(exc)) from exc


def validate_segments(segments: list[Any]) -> None:
    """Raise ValueError if any segment has an invalid folder_key or filename."""
    for i, seg in enumerate(segments):
        if not isinstance(seg, dict):
            raise ValueError(f"segment[{i}] must be an object")
        folder_key = seg.get("folder_key", "")
        filename = (seg.get("filename") or "").strip()
        if folder_key not in VALID_FOLDER_KEYS:
            raise ValueError(
                f"segment[{i}]: unknown folder_key '{folder_key}'. "
                f"Allowed: {sorted(VALID_FOLDER_KEYS)}"
            )
        if not filename or not filename.endswith(".md"):
            raise ValueError(
                f"segment[{i}]: filename must be a non-empty .md name, got '{filename}'"
            )
