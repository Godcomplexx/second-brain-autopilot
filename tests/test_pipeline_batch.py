"""Tests for pipeline batch mode (stage 9)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from services import pipeline


def _fake_aggregate(rel_paths, **kwargs):
    """Stub that returns a minimal valid aggregation result."""
    return {
        "sources": rel_paths,
        "result": {
            "segments": [
                {
                    "topic": f"Topic for {rel_paths[0]}",
                    "folder_key": "knowledge_folder",
                    "filename": "Out.md",
                    "content": "body",
                    "connections": [],
                    "reason": "",
                }
            ],
            "tasks": [{"text": f"Task from {rel_paths[0]}", "due": "", "priority": ""}],
            "habits": {},
        },
    }


def _fail_aggregate(rel_paths, **kwargs):
    raise RuntimeError(f"LLM unavailable for {rel_paths[0]}")


class TestRunAggregateSingleContract:
    def test_rejects_multiple_paths(self, vault_config, tmp_vault, data_dir):
        with pytest.raises(ValueError, match="exactly 1"):
            pipeline.run_aggregate(["a.md", "b.md"])

    def test_accepts_single_path(self, vault_config, tmp_vault, data_dir):
        (tmp_vault / "02 Daily" / "2025-06-01.md").write_text("note", encoding="utf-8")
        with patch("services.pipeline.aggregator.aggregate", side_effect=_fake_aggregate):
            result = pipeline.run_aggregate(["02 Daily/2025-06-01.md"])
        assert result["sources"] == ["02 Daily/2025-06-01.md"]


class TestRunBatchAggregate:
    def test_processes_each_note_independently(self, vault_config, tmp_vault, data_dir):
        for name in ["2025-06-01.md", "2025-06-02.md"]:
            (tmp_vault / "02 Daily" / name).write_text("note", encoding="utf-8")

        with patch("services.pipeline.aggregator.aggregate", side_effect=_fake_aggregate):
            results = pipeline.run_batch_aggregate([
                "02 Daily/2025-06-01.md",
                "02 Daily/2025-06-02.md",
            ])

        assert len(results) == 2
        assert results[0]["sources"] == ["02 Daily/2025-06-01.md"]
        assert results[1]["sources"] == ["02 Daily/2025-06-02.md"]

    def test_failure_in_one_note_does_not_stop_others(self, vault_config, tmp_vault, data_dir):
        for name in ["2025-06-01.md", "2025-06-02.md", "2025-06-03.md"]:
            (tmp_vault / "02 Daily" / name).write_text("note", encoding="utf-8")

        call_count = 0
        def side_effect(rel_paths, **kwargs):
            nonlocal call_count
            call_count += 1
            if rel_paths[0].endswith("2025-06-02.md"):
                raise RuntimeError("LLM fail")
            return _fake_aggregate(rel_paths, **kwargs)

        with patch("services.pipeline.aggregator.aggregate", side_effect=side_effect):
            results = pipeline.run_batch_aggregate([
                "02 Daily/2025-06-01.md",
                "02 Daily/2025-06-02.md",
                "02 Daily/2025-06-03.md",
            ])

        assert call_count == 3  # all three attempted
        assert len(results) == 3
        assert results[1]["result"].get("parse_error") is True
        assert results[1]["result"].get("error") is not None
        # other notes succeeded
        assert not results[0]["result"].get("parse_error")
        assert not results[2]["result"].get("parse_error")

    def test_failed_note_not_indexed(self, vault_config, tmp_vault, data_dir):
        from services import index_store

        (tmp_vault / "02 Daily" / "2025-06-01.md").write_text("note", encoding="utf-8")

        with patch("services.pipeline.aggregator.aggregate", side_effect=_fail_aggregate):
            results = pipeline.run_batch_aggregate(["02 Daily/2025-06-01.md"])

        assert results[0]["result"].get("parse_error") is True
        # task index must not contain entries for the failed note
        tasks = index_store.get_tasks()
        assert not any(t.get("source") == "02 Daily/2025-06-01.md" for t in tasks)

    def test_tasks_indexed_per_source(self, vault_config, tmp_vault, data_dir):
        from services import index_store

        for name in ["2025-06-01.md", "2025-06-02.md"]:
            (tmp_vault / "02 Daily" / name).write_text("note", encoding="utf-8")

        with patch("services.pipeline.aggregator.aggregate", side_effect=_fake_aggregate):
            pipeline.run_batch_aggregate([
                "02 Daily/2025-06-01.md",
                "02 Daily/2025-06-02.md",
            ])

        tasks = index_store.get_tasks()
        sources = {t["source"] for t in tasks}
        assert "02 Daily/2025-06-01.md" in sources
        assert "02 Daily/2025-06-02.md" in sources
