from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from . import config, index_store


def _hash_file(path: Path, algorithm: str = "sha256") -> str:
    h = hashlib.new(algorithm)
    h.update(path.read_bytes())
    return h.hexdigest()


def scan_daily_notes(limit: int = 30) -> list[dict[str, Any]]:
    obs = config.get_obsidian()
    app = config.get_app()
    vault = Path(obs["vault_path"])
    daily_dir = vault / obs["daily_folder"]
    extensions = tuple(app.get("scan_extensions", [".md"]))

    if not daily_dir.exists():
        return []

    processed = index_store.get_processed()
    results: list[dict[str, Any]] = []

    for path in sorted(p for ext in extensions for p in daily_dir.glob(f"*{ext}")):

        rel = str(path.relative_to(vault)).replace("\\", "/")
        content_hash = _hash_file(path)
        record = processed.get(rel)
        status = "new"
        if record:
            status = "changed" if record.get("hash") != content_hash else "processed"

        results.append({
            "rel_path": rel,
            "name": path.stem,
            "size": path.stat().st_size,
            "hash": content_hash,
            "status": status,
            "targets": record.get("targets", []) if record else [],
            "processed_at": record.get("processed_at", "") if record else "",
        })

    # newest first (daily notes are named YYYY-MM-DD so lexicographic = chronological)
    results.sort(key=lambda x: x["name"], reverse=True)
    return results[:limit]


def list_knowledge_files() -> list[str]:
    obs = config.get_obsidian()
    vault = Path(obs["vault_path"])
    folder_keys = ["knowledge_folder", "areas_folder", "projects_folder", "tracking_folder"]
    files: list[str] = []
    for key in folder_keys:
        folder_name = obs.get(key, "")
        if not folder_name:
            continue
        folder = vault / folder_name
        if folder.exists():
            for f in sorted(folder.rglob("*.md")):
                if not f.name.startswith("."):
                    files.append(f.name)
    return files
