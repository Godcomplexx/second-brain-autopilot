"""Preview and safely export generated systems to an Obsidian vault."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from . import config, record_store, storage, system_store

_UNSAFE_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _system(system_id: int) -> dict[str, Any]:
    system = system_store.get(system_id)
    if system is None:
        raise LookupError("system not found")
    return system


def render(system_id: int) -> dict[str, str]:
    system = _system(system_id)
    lines = [
        f"# {system['system_name']}",
        "",
        system["description"],
        "",
        "## Tables",
        "",
    ]
    for entity in system["entities"]:
        lines.extend([f"### {entity['name']}", ""])
        fields = ", ".join(field["name"] for field in entity["fields"])
        lines.extend([f"Fields: {fields}", ""])
        records = record_store.list_for_entity(int(entity["id"]))
        if records:
            headers = [field["name"] for field in entity["fields"]]
            keys = [field["key"] for field in entity["fields"]]
            lines.append("| " + " | ".join(headers) + " |")
            lines.append("| " + " | ".join("---" for _ in headers) + " |")
            for record in records:
                cells = [_cell(record["values"].get(key)) for key in keys]
                lines.append("| " + " | ".join(cells) + " |")
            lines.append("")

    lines.extend(["## Habits", ""])
    if system["habits"]:
        lines.extend(
            f"- [ ] {habit['name']}"
            + (f" — {habit['target']}" if habit["target"] else "")
            for habit in system["habits"]
        )
    else:
        lines.append("_No habits configured._")

    lines.extend(["", "## Weekly metrics", ""])
    if system["metrics"]:
        lines.extend(
            f"- {metric['name']}: {metric['target']:g} {metric['unit']}".rstrip()
            for metric in system["metrics"]
        )
    else:
        lines.append("_No metrics configured._")

    daily = [f"## {system['system_name']}", ""]
    daily.extend(f"{habit['name']}:: 0" for habit in system["habits"])
    if system["metrics"]:
        daily.extend(["", "### Metrics"])
        daily.extend(f"{metric['name']}:: 0" for metric in system["metrics"])
    return {
        "system_markdown": "\n".join(lines).strip() + "\n",
        "daily_template": "\n".join(daily).strip() + "\n",
    }


def export(system_id: int, output_path: str | None = None) -> dict[str, Any]:
    system = _system(system_id)
    rendered = render(system_id)
    if output_path is None:
        folder = config.get_obsidian().get("tracking_folder", "06 Tracking")
        filename = _UNSAFE_FILENAME.sub("", system["system_name"]).strip(" .")
        output_path = f"{folder}/{filename or 'Tracking System'}.md"
    target = storage.safe_resolve(output_path)
    storage.require_md(target)
    storage.atomic_write(target, rendered["system_markdown"])
    return {
        "path": output_path.replace("\\", "/"),
        "daily_template": rendered["daily_template"],
    }


def _cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "✓" if value else "—"
    return str(value).replace("|", "\\|").replace("\n", "<br>")
