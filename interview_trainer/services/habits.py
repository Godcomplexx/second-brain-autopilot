"""Habit read/write logic for daily Obsidian notes."""
from __future__ import annotations

import datetime
import hashlib
import re
from pathlib import Path
from typing import Any

from . import config, index_store, storage


def _habit_keys() -> list[str]:
    return config.get_app().get(
        "habit_keys",
        ["english", "3d", "learning", "reading", "walking", "training"],
    )


def set_note_field(note_path: Path, key: str, value: int) -> bool:
    """Write ``key:: value`` into a note. Returns True if content changed."""
    text = note_path.read_text(encoding="utf-8", errors="ignore")
    pattern = re.compile(rf"^{re.escape(key)}::\s*\d+(?:\.\d+)?", re.MULTILINE)
    new_line = f"{key}:: {value}"
    new_text = pattern.sub(new_line, text) if pattern.search(text) else text.rstrip() + f"\n{new_line}\n"
    if new_text == text:
        return False
    storage.atomic_write(note_path, new_text)
    return True


def sync_hash(note_path: Path, source_rel: str) -> None:
    new_hash = hashlib.sha256(note_path.read_bytes()).hexdigest()
    index_store.update_note_hash(source_rel, new_hash)


def write_habits_to_note(source_rel: str, habits: dict[str, Any]) -> bool:
    """Write detected habit values into the source daily note.

    Only updates a field when the new value is *higher* than the existing one
    (so a manual 1 is never downgraded to AI's 0).
    Returns True if the note was changed.
    """
    obs = config.get_obsidian()
    note_path = Path(obs.get("vault_path", "")) / source_rel
    if not note_path.exists():
        return False
    text = note_path.read_text(encoding="utf-8", errors="ignore")
    changed = False
    for key, raw_val in habits.items():
        if not raw_val:
            continue
        pattern = re.compile(rf"^{re.escape(key)}::\s*(\d+(?:\.\d+)?)", re.MULTILINE)
        m = pattern.search(text)
        existing = float(m.group(1)) if m else 0.0
        new_val = int(max(existing, float(raw_val)))
        if new_val == int(existing):
            continue
        new_line = f"{key}:: {new_val}"
        text = pattern.sub(new_line, text) if m else text.rstrip() + f"\n{new_line}\n"
        changed = True
    if changed:
        storage.atomic_write(note_path, text)
    return changed


def get_all_records() -> list[dict[str, Any]]:
    """Read habit fields from all daily notes and return a list of records."""
    obs = config.get_obsidian()
    vault = Path(obs.get("vault_path", ""))
    daily_folder = obs.get("daily_folder", "02 Daily")
    daily_path = vault / daily_folder
    keys = _habit_keys()
    keys_pattern = "|".join(re.escape(k) for k in keys)
    field_re = re.compile(rf"^({keys_pattern})::\s*(\d+(?:\.\d+)?)", re.MULTILINE)

    records: list[dict[str, Any]] = []
    if not daily_path.exists():
        return records

    for f in sorted(daily_path.glob("*.md")):
        try:
            datetime.date.fromisoformat(f.stem)
        except ValueError:
            continue
        text = f.read_text(encoding="utf-8", errors="ignore")
        rec: dict[str, Any] = {"date": f.stem, **{k: 0 for k in keys}}
        for m in field_re.finditer(text):
            rec[m.group(1)] = float(m.group(2))
        records.append(rec)

    return records


def toggle(key: str, value: int | None = None) -> dict[str, Any]:
    """Toggle or set a single habit field in today's daily note.

    Returns a dict with ok, key, value, date on success.
    Raises ValueError for unknown key or missing today's note.
    """
    valid = tuple(_habit_keys())
    if key not in valid:
        raise ValueError(f"invalid habit key: '{key}'. Allowed: {list(valid)}")

    obs = config.get_obsidian()
    vault = Path(obs.get("vault_path", ""))
    daily_folder = obs.get("daily_folder", "02 Daily")
    today = datetime.date.today().isoformat()
    note_path = vault / daily_folder / f"{today}.md"

    if not note_path.exists():
        raise FileNotFoundError(f"Today's note not found: {today}.md")

    if value is None:
        text = note_path.read_text(encoding="utf-8", errors="ignore")
        m = re.search(rf"^{re.escape(key)}::\s*(\d+(?:\.\d+)?)", text, re.MULTILINE)
        current = float(m.group(1)) if m else 0.0
        value = 0 if current >= 1 else 1

    rel_path = f"{daily_folder}/{today}.md"
    set_note_field(note_path, key, int(value))
    sync_hash(note_path, rel_path)
    return {"ok": True, "key": key, "value": value, "date": today}
