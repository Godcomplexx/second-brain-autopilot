"""Shared fixtures for all tests.

Every test that touches file I/O gets an isolated tmp_vault — no real
Obsidian files are read or written.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Make interview_trainer importable without installing as a package
_TRAINER = Path(__file__).resolve().parent.parent / "interview_trainer"
if str(_TRAINER) not in sys.path:
    sys.path.insert(0, str(_TRAINER))


@pytest.fixture()
def tmp_vault(tmp_path: Path) -> Path:
    """Return a temporary vault root with standard folder layout."""
    (tmp_path / "02 Daily").mkdir()
    (tmp_path / "05 Knowledge").mkdir()
    (tmp_path / "04 Areas").mkdir()
    (tmp_path / "03 Projects").mkdir()
    (tmp_path / "06 Tracking").mkdir()
    return tmp_path


@pytest.fixture()
def vault_config(tmp_vault: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    """Patch services.config so all modules use the tmp vault."""
    obs = {
        "vault_path": str(tmp_vault),
        "daily_folder": "02 Daily",
        "knowledge_folder": "05 Knowledge",
        "areas_folder": "04 Areas",
        "projects_folder": "03 Projects",
        "tracking_folder": "06 Tracking",
        "archive_folder": "07 Archive",
        "tasks_file": "06 Tracking/Task Inbox.md",
    }
    app_cfg = {
        "health_check_timeout": 2,
        "scan_extensions": [".md"],
        "max_note_chars": 8000,
        "aggregator_prompt_max_chars": 24000,
        "preview_truncate_chars": 600,
        "hash_algorithm": "sha256",
        "habit_keys": ["english", "3d", "learning", "reading", "walking", "training"],
    }

    from services import config as cfg_mod
    monkeypatch.setattr(cfg_mod, "_CACHE", {"obsidian": obs, "app": app_cfg, "models": {}})
    return obs


@pytest.fixture()
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect index_store data files to a tmp directory."""
    d = tmp_path / "data"
    d.mkdir()
    from services import index_store
    monkeypatch.setattr(index_store, "_PROCESSED_FILE", d / "processed_notes.json")
    monkeypatch.setattr(index_store, "_TASK_INDEX_FILE", d / "task_index.json")
    return d
