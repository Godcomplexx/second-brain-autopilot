from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

from . import config, index_store


PRIORITY_EMOJI = {"high": "🔴", "medium": "🟡", "low": "🟢"}


def format_task_line(task: dict[str, Any]) -> str:
    done_mark = "x" if task.get("done") else " "
    text = task.get("text", "")
    due = task.get("due", "")
    priority = task.get("priority", "")
    parts = [f"- [{done_mark}] {text}"]
    if due:
        parts.append(f" 📅 {due}")
    if priority and priority in PRIORITY_EMOJI:
        parts.append(f" {PRIORITY_EMOJI[priority]}")
    source = task.get("source", "")
    if source:
        parts.append(f" [[{source}]]")
    return "".join(parts)


def format_task_block(tasks: list[dict[str, Any]]) -> str:
    if not tasks:
        return "_No tasks extracted._"
    return "\n".join(format_task_line(t) for t in tasks)


def store_tasks_from_aggregation(source_rel: str, result: dict[str, Any]) -> int:
    raw_tasks = result.get("tasks", [])
    tasks = [
        {
            "text": t.get("text", ""),
            "due": t.get("due", ""),
            "priority": t.get("priority", ""),
            "done": False,
            "source": source_rel,
        }
        for t in raw_tasks
        if t.get("text")
    ]
    if tasks:
        index_store.replace_tasks_for_source(source_rel, tasks)
    return len(tasks)


def write_tasks_to_vault(tasks: list[dict[str, Any]], source_rel: str) -> dict[str, Any]:
    if not tasks:
        return {"written": 0, "skipped": True}

    obs = config.get_obsidian()
    vault = Path(obs["vault_path"])
    tasks_file = vault / obs.get("tasks_file", "06 Tracking/Task Inbox.md")
    tasks_file.parent.mkdir(parents=True, exist_ok=True)

    today = datetime.utcnow().strftime("%Y-%m-%d")
    source_stem = Path(source_rel).stem

    lines: list[str] = []
    for t in tasks:
        if not t.get("text"):
            continue
        lines.append(format_task_line({**t, "done": False, "source": source_stem}))

    if not lines:
        return {"written": 0, "skipped": True}

    header = f"## {today} — from [[{source_stem}]]"
    block = f"\n{header}\n" + "\n".join(lines) + "\n"

    existing = tasks_file.read_text(encoding="utf-8") if tasks_file.exists() else ""
    if header in existing:
        existing = re.sub(
            r"\n" + re.escape(header) + r"\n.*?(?=\n##|\Z)",
            block,
            existing,
            flags=re.DOTALL,
        )
        tasks_file.write_text(existing, encoding="utf-8")
    else:
        tasks_file.write_text(existing + block, encoding="utf-8")

    return {"written": len(lines), "tasks_file": str(tasks_file.relative_to(vault)).replace("\\", "/")}
