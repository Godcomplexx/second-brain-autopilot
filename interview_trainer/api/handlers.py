"""HTTP request handlers — one method per API endpoint.

Each handler receives a pre-parsed body dict and a ``send`` callable
``(data, status=200) -> None`` for the response, plus an ``error`` callable
``(message, status=400) -> None``. This decouples business logic from the
HTTP layer so handlers are unit-testable without a live HTTP server.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Callable

from services import (
    config,
    habits as habits_svc,
    index_store,
    ollama_client,
    pipeline,
    storage,
    vault_scanner,
    validation,
)

Send = Callable[[Any, int], None]
Error = Callable[[str, int], None]

_CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
_LOGGER = logging.getLogger(__name__)


# ── Health ────────────────────────────────────────────────────────────────────

def handle_health(send: Send, error: Error) -> None:
    obs = config.get_obsidian()
    models = config.get_models()
    base_url = models.get("ollama_base_url", "http://127.0.0.1:11434")
    timeout = config.get_app().get("health_check_timeout", 2)

    ollama_ok = False
    ollama_models: list[str] = []
    try:
        ollama_models = ollama_client.list_models(base_url=base_url, timeout=timeout)
        ollama_ok = True
    except OSError as exc:
        _LOGGER.debug("Ollama health check failed: %s", exc)

    vault_path = obs.get("vault_path", "")
    vault_ok = Path(vault_path).exists() if vault_path else False
    daily_ok = vault_ok and (Path(vault_path) / obs.get("daily_folder", "02 Daily")).exists()

    send({
        "ollama": ollama_ok,
        "ollama_models": ollama_models,
        "vault_exists": vault_ok,
        "daily_exists": daily_ok,
        "vault_path": vault_path,
    }, 200)


# ── Config ────────────────────────────────────────────────────────────────────

def handle_get_config(send: Send, error: Error) -> None:
    send({
        "app": config.get_app(),
        "obsidian": config.get_obsidian(),
        "models": config.get_models(),
    }, 200)


def handle_post_config(body: dict[str, Any], send: Send, error: Error) -> None:
    target = body.get("target")
    updates = body.get("updates", {})
    config_map = {
        "obsidian": _CONFIG_DIR / "obsidian.json",
        "models":   _CONFIG_DIR / "models.json",
        "app":      _CONFIG_DIR / "app_config.json",
    }
    if target not in config_map:
        error(f"Unknown config target: {target!r}. Allowed: {list(config_map)}", 400)
        return
    if not isinstance(updates, dict):
        error("'updates' must be an object", 400)
        return
    path = config_map[target]
    try:
        current = json.loads(path.read_text(encoding="utf-8"))
        current.update(updates)
        path.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
        config.invalidate(target)
        send({"ok": True, "config": current}, 200)
    except Exception as exc:
        error(str(exc), 500)


# ── Scan ──────────────────────────────────────────────────────────────────────

def handle_scan(send: Send, error: Error) -> None:
    try:
        notes = vault_scanner.scan_daily_notes()
        send({"notes": notes, "count": len(notes)}, 200)
    except Exception as exc:
        error(str(exc), 500)


# ── Aggregate ─────────────────────────────────────────────────────────────────

def handle_aggregate(body: dict[str, Any], send: Send, error: Error) -> None:
    try:
        rel_paths = validation.require_list(body, "rel_paths")
    except ValueError as exc:
        error(str(exc), 400)
        return

    provider = body.get("provider", "ollama")
    api_key = body.get("apiKey", "") or os.environ.get("OPENAI_API_KEY", "")
    user_model = body.get("model") or None
    base_url = (body.get("baseUrl") or "").rstrip("/") or None

    try:
        if len(rel_paths) == 1:
            # Single-note: return one result dict (existing UI contract)
            result = pipeline.run_aggregate(
                rel_paths,
                provider=provider,
                api_key=api_key,
                user_model=user_model,
                base_url=base_url,
            )
            send(result, 200)
        else:
            # Batch: each note processed independently, return list
            results = pipeline.run_batch_aggregate(
                rel_paths,
                provider=provider,
                api_key=api_key,
                user_model=user_model,
                base_url=base_url,
            )
            send({"batch": True, "results": results, "count": len(results)}, 200)
    except Exception as exc:
        error(str(exc), 500)


# ── Preview ───────────────────────────────────────────────────────────────────

def handle_preview(body: dict[str, Any], send: Send, error: Error) -> None:
    try:
        source_rel = validation.require_str(body, "source_rel")
        segments = validation.require_list(body, "segments")
    except ValueError as exc:
        error(str(exc), 400)
        return

    try:
        previews = pipeline.run_preview(source_rel, segments)
        send({"previews": previews}, 200)
    except Exception as exc:
        error(str(exc), 500)


# ── Write ─────────────────────────────────────────────────────────────────────

def handle_write(body: dict[str, Any], send: Send, error: Error) -> None:
    try:
        source_rel = validation.require_str(body, "source_rel")
        segments = validation.require_list(body, "segments")
        scan_hash = validation.require_str(body, "scan_hash")
        validation.validate_source_rel(source_rel)
        validation.validate_segments(segments)
    except ValueError as exc:
        error(str(exc), 400)
        return

    tasks = body.get("tasks") or []
    habits_data = body.get("habits") or {}

    try:
        result = pipeline.run_write(source_rel, segments, tasks, habits_data, scan_hash)
        send(result, 200)
    except RuntimeError as exc:
        # segment write failure (hash conflict, missing source, etc.)
        error(str(exc), 409)
    except Exception as exc:
        error(str(exc), 500)


# ── Tasks ─────────────────────────────────────────────────────────────────────

def handle_toggle_task(body: dict[str, Any], send: Send, error: Error) -> None:
    text = body.get("text", "")
    source = body.get("source", "")
    if not text:
        error("'text' is required", 400)
        return

    task = index_store.toggle_task(text, source)
    if task is None:
        error("task not found", 404)
        return

    # Mirror done-state to Task Inbox.md
    obs = config.get_obsidian()
    vault = Path(obs.get("vault_path", ""))
    tasks_file = vault / obs.get("tasks_file", "06 Tracking/Task Inbox.md")
    if tasks_file.exists():
        import re
        content = tasks_file.read_text(encoding="utf-8", errors="ignore")
        new_mark = "x" if task["done"] else " "
        old_mark = " " if task["done"] else "x"
        content = re.sub(
            rf"^- \[{old_mark}\] {re.escape(text)}",
            f"- [{new_mark}] {text}",
            content, flags=re.MULTILINE,
        )
        storage.atomic_write(tasks_file, content)

    send({"ok": True, "done": task["done"]}, 200)


# ── Habits ────────────────────────────────────────────────────────────────────

def handle_get_habits(send: Send, error: Error) -> None:
    try:
        records = habits_svc.get_all_records()
        send({"habits": records}, 200)
    except Exception as exc:
        error(str(exc), 500)


def handle_habit_toggle(body: dict[str, Any], send: Send, error: Error) -> None:
    key = body.get("key", "")
    value = body.get("value")

    try:
        result = habits_svc.toggle(key, value)
        send(result, 200)
    except FileNotFoundError as exc:
        error(str(exc), 404)
    except ValueError as exc:
        error(str(exc), 400)
    except Exception as exc:
        error(str(exc), 500)


# ── Index ─────────────────────────────────────────────────────────────────────

def handle_get_index(send: Send, error: Error) -> None:
    send({
        "processed": index_store.get_processed(),
        "tasks": index_store.get_tasks(),
    }, 200)
