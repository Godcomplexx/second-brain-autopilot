"""Aggregate → preview → write pipeline.

Single-note mode: one source → LLM call → segments/tasks/habits → write.
Batch mode: each source is processed independently; a failure in one note
does not affect the others and never marks them as processed.
"""
from __future__ import annotations

import os
from typing import Any

from . import (
    aggregator,
    habits as habits_svc,
    index_store,
    markdown_writer,
    task_manager,
    vault_scanner,
)


def run_aggregate(
    rel_paths: list[str],
    provider: str = "ollama",
    api_key: str = "",
    user_model: str | None = None,
    base_url: str | None = None,
) -> dict[str, Any]:
    """Aggregate ONE source note via LLM and pre-index its tasks.

    rel_paths must contain exactly one entry (single-note contract).
    For multi-note processing use run_batch_aggregate.
    """
    if len(rel_paths) != 1:
        raise ValueError(
            f"run_aggregate expects exactly 1 rel_path, got {len(rel_paths)}. "
            "Use run_batch_aggregate for multiple notes."
        )
    api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
    existing_files = vault_scanner.list_knowledge_files()
    result = aggregator.aggregate(
        rel_paths,
        provider=provider,
        api_key=api_key,
        user_model=user_model,
        base_url=base_url,
        existing_files=existing_files,
    )
    if not result["result"].get("parse_error"):
        task_manager.store_tasks_from_aggregation(rel_paths[0], result["result"])
    return result


def run_batch_aggregate(
    rel_paths: list[str],
    provider: str = "ollama",
    api_key: str = "",
    user_model: str | None = None,
    base_url: str | None = None,
) -> list[dict[str, Any]]:
    """Aggregate multiple notes independently, one LLM call per note.

    Returns a list of per-note result dicts (same shape as run_aggregate).
    Each note has its own sources, result, and task index entry.
    A failure for one note is captured in that note's result and does not
    stop processing of the remaining notes.
    """
    api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
    existing_files = vault_scanner.list_knowledge_files()
    jobs: list[dict[str, Any]] = []

    for rel in rel_paths:
        try:
            result = aggregator.aggregate(
                [rel],
                provider=provider,
                api_key=api_key,
                user_model=user_model,
                base_url=base_url,
                existing_files=existing_files,
            )
            if not result["result"].get("parse_error"):
                task_manager.store_tasks_from_aggregation(rel, result["result"])
        except Exception as exc:
            result = {
                "sources": [rel],
                "result": {
                    "segments": [],
                    "tasks": [],
                    "habits": {},
                    "parse_error": True,
                    "error": str(exc),
                },
            }
        jobs.append(result)

    return jobs


def run_preview(source_rel: str, segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Generate write previews for all segments without touching the vault."""
    return [
        markdown_writer.preview_write(
            source_rel,
            seg.get("folder_key", "knowledge_folder"),
            seg.get("filename", "Note.md"),
            seg.get("content", ""),
            seg.get("connections") or [],
        )
        for seg in segments
    ]


def run_write(
    source_rel: str,
    segments: list[dict[str, Any]],
    tasks: list[dict[str, Any]],
    habits_data: dict[str, Any],
    scan_hash: str,
) -> dict[str, Any]:
    """Write all segments atomically, then update index, tasks, and habits.

    Raises on the first segment failure — no partial state is committed to
    the index because mark_processed is called only after all writes succeed.
    """
    results = []
    for seg in segments:
        r = markdown_writer.write_aggregation(
            source_rel,
            seg.get("folder_key", "knowledge_folder"),
            seg.get("filename", "Note.md"),
            seg.get("content", ""),
            seg.get("connections") or [],
            scan_hash=scan_hash,
        )
        if not r["success"]:
            raise RuntimeError(r["error"])
        results.append(r)

    # Single atomic index update with all targets after all writes succeed
    all_targets = list(dict.fromkeys(r["target_path"] for r in results))
    source_hash = results[0]["source_hash"]
    index_store.mark_processed(source_rel, source_hash, all_targets)

    tasks_result: dict[str, Any] = {}
    if tasks:
        tasks_result = task_manager.write_tasks_to_vault(tasks, source_rel)

    habits_written = False
    if habits_data:
        habits_written = habits_svc.write_habits_to_note(source_rel, habits_data)
        if habits_written:
            from pathlib import Path
            from . import config
            obs = config.get_obsidian()
            note_path = Path(obs.get("vault_path", "")) / source_rel
            if note_path.exists():
                habits_svc.sync_hash(note_path, source_rel)

    return {
        "written": results,
        "tasks_written": tasks_result,
        "habits_written": habits_written,
    }
