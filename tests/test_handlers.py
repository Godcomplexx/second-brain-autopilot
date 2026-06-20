"""Tests for api/handlers.py — business logic via callable send/error."""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

_TRAINER = Path(__file__).resolve().parent.parent / "interview_trainer"
if str(_TRAINER) not in sys.path:
    sys.path.insert(0, str(_TRAINER))

from api import handlers


class Capture:
    """Captures the last send/error call for assertion."""
    def __init__(self):
        self.data = None
        self.status = None
        self.error_msg = None
        self.error_status = None

    def send(self, data, status=200):
        self.data = data
        self.status = status

    def error(self, message, status=400):
        self.error_msg = message
        self.error_status = status


# ── handle_health ─────────────────────────────────────────────────────────────

class TestHandleHealth:
    def test_returns_vault_status(self, vault_config, tmp_vault):
        c = Capture()
        handlers.handle_health(c.send, c.error)
        assert c.status == 200
        assert "vault_exists" in c.data
        assert "ollama" in c.data

    def test_vault_exists_true_when_path_set(self, vault_config, tmp_vault):
        c = Capture()
        handlers.handle_health(c.send, c.error)
        assert c.data["vault_exists"] is True


# ── handle_get_config / handle_post_config ────────────────────────────────────

class TestHandleConfig:
    def test_get_returns_all_sections(self, vault_config):
        c = Capture()
        handlers.handle_get_config(c.send, c.error)
        assert c.status == 200
        assert "app" in c.data
        assert "obsidian" in c.data

    def test_post_unknown_target_errors(self, vault_config):
        c = Capture()
        handlers.handle_post_config({"target": "unknown", "updates": {}}, c.send, c.error)
        assert c.error_status == 400
        assert "Unknown config target" in c.error_msg

    def test_post_non_dict_updates_errors(self, vault_config):
        c = Capture()
        handlers.handle_post_config({"target": "app", "updates": "bad"}, c.send, c.error)
        assert c.error_status == 400


# ── handle_scan ───────────────────────────────────────────────────────────────

class TestHandleScan:
    def test_returns_notes_list(self, vault_config, tmp_vault, data_dir):
        (tmp_vault / "02 Daily" / "2025-06-01.md").write_text("note", encoding="utf-8")
        c = Capture()
        handlers.handle_scan(c.send, c.error)
        assert c.status == 200
        assert "notes" in c.data
        assert c.data["count"] == 1


# ── handle_preview ────────────────────────────────────────────────────────────

class TestHandlePreview:
    def test_missing_source_rel_errors(self, vault_config, data_dir):
        c = Capture()
        handlers.handle_preview({"segments": [{}]}, c.send, c.error)
        assert c.error_status == 400

    def test_missing_segments_errors(self, vault_config, data_dir):
        c = Capture()
        handlers.handle_preview({"source_rel": "note.md", "segments": []}, c.send, c.error)
        assert c.error_status == 400

    def test_valid_preview_returns_list(self, vault_config, tmp_vault, data_dir):
        c = Capture()
        handlers.handle_preview({
            "source_rel": "02 Daily/2025-06-01.md",
            "segments": [{
                "folder_key": "knowledge_folder",
                "filename": "Out.md",
                "content": "body",
                "connections": [],
            }],
        }, c.send, c.error)
        assert c.status == 200
        assert "previews" in c.data
        assert len(c.data["previews"]) == 1


# ── handle_write ──────────────────────────────────────────────────────────────

class TestHandleWrite:
    def _make_source(self, tmp_vault):
        note = tmp_vault / "02 Daily" / "2025-06-01.md"
        note.write_text("source note content", encoding="utf-8")
        return note, hashlib.sha256(note.read_bytes()).hexdigest()

    def test_missing_source_rel_errors(self, vault_config, data_dir):
        c = Capture()
        handlers.handle_write({}, c.send, c.error)
        assert c.error_status == 400

    def test_missing_scan_hash_errors(self, vault_config, data_dir):
        c = Capture()
        handlers.handle_write({
            "source_rel": "02 Daily/note.md",
            "segments": [{"folder_key": "knowledge_folder", "filename": "Out.md", "content": "x"}],
            "scan_hash": "",
        }, c.send, c.error)
        assert c.error_status == 400

    def test_invalid_folder_key_errors(self, vault_config, tmp_vault, data_dir):
        note, h = self._make_source(tmp_vault)
        c = Capture()
        handlers.handle_write({
            "source_rel": "02 Daily/2025-06-01.md",
            "segments": [{"folder_key": "bad_folder", "filename": "Out.md", "content": "x"}],
            "scan_hash": h,
        }, c.send, c.error)
        assert c.error_status == 400
        assert "folder_key" in c.error_msg

    def test_non_md_filename_errors(self, vault_config, tmp_vault, data_dir):
        note, h = self._make_source(tmp_vault)
        c = Capture()
        handlers.handle_write({
            "source_rel": "02 Daily/2025-06-01.md",
            "segments": [{"folder_key": "knowledge_folder", "filename": "Out.txt", "content": "x"}],
            "scan_hash": h,
        }, c.send, c.error)
        assert c.error_status == 400

    def test_traversal_in_source_rel_errors(self, vault_config, data_dir):
        c = Capture()
        handlers.handle_write({
            "source_rel": "../etc/passwd",
            "segments": [{"folder_key": "knowledge_folder", "filename": "Out.md", "content": "x"}],
            "scan_hash": "abc",
        }, c.send, c.error)
        assert c.error_status == 400

    def test_successful_write(self, vault_config, tmp_vault, data_dir):
        note, h = self._make_source(tmp_vault)
        c = Capture()
        handlers.handle_write({
            "source_rel": "02 Daily/2025-06-01.md",
            "segments": [{"folder_key": "knowledge_folder", "filename": "Out.md", "content": "body"}],
            "scan_hash": h,
        }, c.send, c.error)
        assert c.status == 200
        assert c.error_msg is None
        assert len(c.data["written"]) == 1

    def test_hash_conflict_returns_409(self, vault_config, tmp_vault, data_dir):
        note, _ = self._make_source(tmp_vault)
        c = Capture()
        handlers.handle_write({
            "source_rel": "02 Daily/2025-06-01.md",
            "segments": [{"folder_key": "knowledge_folder", "filename": "Out.md", "content": "x"}],
            "scan_hash": "wrong_hash_000",
        }, c.send, c.error)
        assert c.error_status == 409


# ── handle_toggle_task ────────────────────────────────────────────────────────

class TestHandleToggleTask:
    def test_missing_text_errors(self, vault_config, data_dir):
        c = Capture()
        handlers.handle_toggle_task({"text": ""}, c.send, c.error)
        assert c.error_status == 400

    def test_not_found_returns_404(self, vault_config, data_dir):
        c = Capture()
        handlers.handle_toggle_task({"text": "ghost task", "source": "n.md"}, c.send, c.error)
        assert c.error_status == 404


# ── handle_habit_toggle ───────────────────────────────────────────────────────

class TestHandleHabitToggle:
    def test_invalid_key_errors(self, vault_config, data_dir):
        c = Capture()
        handlers.handle_habit_toggle({"key": "invalid_key"}, c.send, c.error)
        assert c.error_status == 400

    def test_missing_today_note_returns_404(self, vault_config, tmp_vault, data_dir):
        c = Capture()
        handlers.handle_habit_toggle({"key": "english", "value": 1}, c.send, c.error)
        assert c.error_status == 404

    def test_valid_toggle(self, vault_config, tmp_vault, data_dir):
        import datetime
        today = datetime.date.today().isoformat()
        (tmp_vault / "02 Daily" / f"{today}.md").write_text("english:: 0\n", encoding="utf-8")
        c = Capture()
        handlers.handle_habit_toggle({"key": "english", "value": 1}, c.send, c.error)
        assert c.status == 200
        assert c.data["ok"] is True
        assert c.data["value"] == 1


# ── handle_get_index ──────────────────────────────────────────────────────────

class TestHandleGetIndex:
    def test_returns_processed_and_tasks(self, vault_config, data_dir):
        c = Capture()
        handlers.handle_get_index(c.send, c.error)
        assert c.status == 200
        assert "processed" in c.data
        assert "tasks" in c.data
