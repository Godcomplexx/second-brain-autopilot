from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import config, index_store

_MARKER_START = "<!-- AI_AGGREGATED_START"
_MARKER_END = "<!-- AI_AGGREGATED_END -->"


def _source_re(source: str) -> re.Pattern:
    return re.compile(
        r"<!-- AI_AGGREGATED_START:source=" + re.escape(source) + r"[^>]*-->.*?<!-- AI_AGGREGATED_END -->",
        re.DOTALL,
    )


def _build_marker_start(source: str, date: str) -> str:
    return f"{_MARKER_START}:source={source}:date={date} -->"


def _build_block(content: str, source: str, date: str, connections: list[str] | None = None) -> str:
    body = content.strip()
    if connections:
        conn_lines = "\n".join(f"- {c}" for c in connections)
        body += f"\n\n## Connections\n\n{conn_lines}"
    return f"{_build_marker_start(source, date)}\n{body}\n{_MARKER_END}"


def _resolve_target_path(obs: dict[str, Any], folder_key: str, filename: str, mkdir: bool = False) -> Path:
    vault = Path(obs["vault_path"])
    folder = obs.get(folder_key, folder_key)
    target = vault / folder / filename
    if mkdir:
        target.parent.mkdir(parents=True, exist_ok=True)
    return target


def write_aggregation(
    source_rel: str,
    target_folder_key: str,
    target_filename: str,
    content: str,
    connections: list[str] | None = None,
    scan_hash: str = "",
) -> dict[str, Any]:
    obs = config.get_obsidian()
    source_path = Path(obs["vault_path"]) / source_rel
    if not source_path.exists():
        return {"success": False, "error": f"Source file not found: {source_rel}"}

    current_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()

    if scan_hash:
        # Compare against the hash captured at scan time
        ok = current_hash == scan_hash
    else:
        # Fallback: compare against last-written hash in the index
        record = index_store.get_note_record(source_rel)
        ok = (not record) or record.get("hash") == current_hash

    if not ok:
        return {
            "success": False,
            "error": f"Source file '{source_rel}' has changed since scan. Re-scan and re-aggregate before writing.",
        }

    target_path = _resolve_target_path(obs, target_folder_key, target_filename, mkdir=True)
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    block = _build_block(content, source_rel, date_str, connections)

    if target_path.exists():
        existing = target_path.read_text(encoding="utf-8")
        src_re = _source_re(source_rel)
        if src_re.search(existing):
            updated = src_re.sub(block, existing)
        else:
            updated = existing.rstrip() + "\n\n" + block + "\n"
    else:
        updated = block + "\n"

    target_path.write_text(updated, encoding="utf-8")
    target_rel = str(target_path.relative_to(Path(obs["vault_path"]))).replace("\\", "/")

    # Caller (server handler) is responsible for updating the index once all
    # segments for this source have been written successfully.
    return {
        "success": True,
        "target_path": target_rel,
        "source": source_rel,
        "date": date_str,
        "source_hash": current_hash,
    }


def preview_write(
    source_rel: str,
    target_folder_key: str,
    target_filename: str,
    content: str,
    connections: list[str] | None = None,
) -> dict[str, Any]:
    obs = config.get_obsidian()
    target_path = _resolve_target_path(obs, target_folder_key, target_filename, mkdir=False)
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    block = _build_block(content, source_rel, date_str, connections)
    target_rel = str(target_path.relative_to(Path(obs["vault_path"]))).replace("\\", "/")

    existing_content = ""
    if target_path.exists():
        existing_content = target_path.read_text(encoding="utf-8")

    return {
        "source": source_rel,
        "target_path": target_rel,
        "target_exists": target_path.exists(),
        "block_preview": block,
        "existing_content_snippet": existing_content[:400] if existing_content else "",
    }
