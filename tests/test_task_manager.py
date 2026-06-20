"""Tests for task_manager.py — formatting, storing, writing to vault."""
from __future__ import annotations

from pathlib import Path

import pytest

from services import task_manager, index_store


class TestFormatTaskLine:
    def test_basic(self):
        line = task_manager.format_task_line({"text": "Do X", "done": False, "due": "", "priority": ""})
        assert line == "- [ ] Do X"

    def test_done(self):
        line = task_manager.format_task_line({"text": "Done", "done": True, "due": "", "priority": ""})
        assert "- [x]" in line

    def test_due_date(self):
        line = task_manager.format_task_line({"text": "T", "done": False, "due": "2025-12-31", "priority": ""})
        assert "2025-12-31" in line

    def test_priority_emoji(self):
        line = task_manager.format_task_line({"text": "T", "done": False, "due": "", "priority": "high"})
        assert "🔴" in line


class TestStoreTasksFromAggregation:
    def test_stores_tasks_for_source(self, data_dir, vault_config):
        result = {"tasks": [{"text": "Buy milk", "due": "", "priority": ""}], "segments": []}
        count = task_manager.store_tasks_from_aggregation("02 Daily/note.md", result)
        assert count == 1
        tasks = index_store.get_tasks()
        assert tasks[0]["source"] == "02 Daily/note.md"

    def test_skips_empty_text(self, data_dir, vault_config):
        result = {"tasks": [{"text": "", "due": "", "priority": ""}], "segments": []}
        count = task_manager.store_tasks_from_aggregation("note.md", result)
        assert count == 0

    def test_replaces_existing_tasks_for_source(self, data_dir, vault_config):
        r1 = {"tasks": [{"text": "Old", "due": "", "priority": ""}]}
        task_manager.store_tasks_from_aggregation("note.md", r1)
        r2 = {"tasks": [{"text": "New", "due": "", "priority": ""}]}
        task_manager.store_tasks_from_aggregation("note.md", r2)
        texts = [t["text"] for t in index_store.get_tasks()]
        assert "Old" not in texts
        assert "New" in texts


class TestWriteTasksToVault:
    def test_creates_task_inbox(self, tmp_vault: Path, vault_config, data_dir):
        tasks = [{"text": "Buy bread", "due": "", "priority": "low", "done": False}]
        result = task_manager.write_tasks_to_vault(tasks, "02 Daily/2025-06-01.md")
        assert result["written"] == 1
        inbox = tmp_vault / "06 Tracking" / "Task Inbox.md"
        assert inbox.exists()
        assert "Buy bread" in inbox.read_text(encoding="utf-8")

    def test_no_tasks_skipped(self, tmp_vault: Path, vault_config, data_dir):
        result = task_manager.write_tasks_to_vault([], "note.md")
        assert result["written"] == 0
        assert result["skipped"] is True

    def test_idempotent_on_same_source(self, tmp_vault: Path, vault_config, data_dir):
        tasks = [{"text": "Task X", "due": "", "priority": "", "done": False}]
        task_manager.write_tasks_to_vault(tasks, "02 Daily/2025-06-01.md")
        task_manager.write_tasks_to_vault(tasks, "02 Daily/2025-06-01.md")
        content = (tmp_vault / "06 Tracking" / "Task Inbox.md").read_text(encoding="utf-8")
        assert content.count("Task X") == 1
