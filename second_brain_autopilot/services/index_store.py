from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent
_PROCESSED_FILE = _ROOT / "data" / "processed_notes.json"
_TASK_INDEX_FILE = _ROOT / "data" / "task_index.json"


def _read(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default if default is not None else {}


def _write(path: Path, data: Any) -> None:
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def get_processed() -> dict[str, Any]:
    return _read(_PROCESSED_FILE, {})


def mark_processed(rel_path: str, content_hash: str, targets: list[str]) -> None:
    from datetime import datetime, timezone
    data = get_processed()
    data[rel_path] = {
        "hash": content_hash,
        "processed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "targets": targets,
    }
    _write(_PROCESSED_FILE, data)


def get_note_record(rel_path: str) -> dict[str, Any] | None:
    return get_processed().get(rel_path)


def update_note_hash(rel_path: str, new_hash: str) -> None:
    data = get_processed()
    if rel_path in data:
        data[rel_path]["hash"] = new_hash
        _write(_PROCESSED_FILE, data)


def get_tasks() -> list[dict[str, Any]]:
    return _read(_TASK_INDEX_FILE, [])


def replace_tasks_for_source(source: str, new_tasks: list[dict[str, Any]]) -> None:
    existing = [t for t in get_tasks() if t.get("source") != source]
    existing.extend(new_tasks)
    _write(_TASK_INDEX_FILE, existing)


def toggle_task(text: str, source: str) -> dict[str, Any] | None:
    tasks = get_tasks()
    for t in tasks:
        if t.get("text") == text and t.get("source") == source:
            t["done"] = not t.get("done", False)
            _write(_TASK_INDEX_FILE, tasks)
            return t
    return None
