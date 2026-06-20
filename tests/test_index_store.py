"""Tests for index_store.py — processed notes index and task index."""
from __future__ import annotations

import pytest

from services import index_store


class TestProcessedNotes:
    def test_empty_by_default(self, data_dir):
        assert index_store.get_processed() == {}

    def test_mark_and_retrieve(self, data_dir):
        index_store.mark_processed("daily/note.md", "abc123", ["knowledge/Out.md"])
        rec = index_store.get_note_record("daily/note.md")
        assert rec is not None
        assert rec["hash"] == "abc123"
        assert "knowledge/Out.md" in rec["targets"]
        assert "processed_at" in rec

    def test_overwrite_preserves_all_targets(self, data_dir):
        index_store.mark_processed("note.md", "h1", ["A.md", "B.md"])
        index_store.mark_processed("note.md", "h2", ["C.md"])
        rec = index_store.get_note_record("note.md")
        assert rec["hash"] == "h2"
        assert rec["targets"] == ["C.md"]

    def test_update_note_hash(self, data_dir):
        index_store.mark_processed("note.md", "old", [])
        index_store.update_note_hash("note.md", "new")
        assert index_store.get_note_record("note.md")["hash"] == "new"

    def test_update_hash_noop_when_not_found(self, data_dir):
        index_store.update_note_hash("ghost.md", "xyz")
        assert index_store.get_note_record("ghost.md") is None


class TestTaskIndex:
    def test_empty_by_default(self, data_dir):
        assert index_store.get_tasks() == []

    def test_replace_tasks_for_source(self, data_dir):
        tasks = [{"text": "Do X", "source": "note.md", "due": "", "priority": "", "done": False}]
        index_store.replace_tasks_for_source("note.md", tasks)
        stored = index_store.get_tasks()
        assert len(stored) == 1
        assert stored[0]["text"] == "Do X"

    def test_replace_removes_old_source_tasks(self, data_dir):
        old = [{"text": "Old task", "source": "note.md", "due": "", "priority": "", "done": False}]
        index_store.replace_tasks_for_source("note.md", old)
        new = [{"text": "New task", "source": "note.md", "due": "", "priority": "", "done": False}]
        index_store.replace_tasks_for_source("note.md", new)
        tasks = index_store.get_tasks()
        texts = [t["text"] for t in tasks]
        assert "Old task" not in texts
        assert "New task" in texts

    def test_different_sources_coexist(self, data_dir):
        index_store.replace_tasks_for_source("a.md", [
            {"text": "Task A", "source": "a.md", "due": "", "priority": "", "done": False}
        ])
        index_store.replace_tasks_for_source("b.md", [
            {"text": "Task B", "source": "b.md", "due": "", "priority": "", "done": False}
        ])
        tasks = index_store.get_tasks()
        assert len(tasks) == 2

    def test_toggle_task_done(self, data_dir):
        index_store.replace_tasks_for_source("n.md", [
            {"text": "Toggle me", "source": "n.md", "due": "", "priority": "", "done": False}
        ])
        result = index_store.toggle_task("Toggle me", "n.md")
        assert result is not None
        assert result["done"] is True

    def test_toggle_task_undone(self, data_dir):
        index_store.replace_tasks_for_source("n.md", [
            {"text": "Toggle me", "source": "n.md", "due": "", "priority": "", "done": True}
        ])
        result = index_store.toggle_task("Toggle me", "n.md")
        assert result["done"] is False

    def test_toggle_returns_none_when_not_found(self, data_dir):
        result = index_store.toggle_task("ghost task", "nowhere.md")
        assert result is None
