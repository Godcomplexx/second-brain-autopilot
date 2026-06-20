"""Tests for aggregator.py — JSON parsing, repair, normalisation."""
from __future__ import annotations

import pytest

from services.aggregator import (
    _extract_json,
    _repair_json,
    _normalize_result,
    _extract_checkbox_tasks,
    _merge_tasks,
)


# ── _repair_json ──────────────────────────────────────────────────────────────

class TestRepairJson:
    def test_already_valid(self):
        assert _repair_json('{"a": 1}') == '{"a": 1}'

    def test_closes_open_brace(self):
        result = _repair_json('{"a": 1')
        import json
        assert json.loads(result) == {"a": 1}

    def test_closes_nested(self):
        result = _repair_json('{"a": {"b": [1, 2')
        import json
        data = json.loads(result)
        assert data["a"]["b"] == [1, 2]

    def test_strips_trailing_comma(self):
        result = _repair_json('{"a": 1,')
        import json
        assert json.loads(result) == {"a": 1}

    def test_string_with_braces_not_counted(self):
        raw = '{"key": "value with { brace"'
        import json
        assert json.loads(_repair_json(raw)) == {"key": "value with { brace"}


# ── _extract_json ─────────────────────────────────────────────────────────────

class TestExtractJson:
    def test_plain_json(self):
        data = _extract_json('{"segments": [], "tasks": []}')
        assert data == {"segments": [], "tasks": []}

    def test_fenced_code_block(self):
        text = '```json\n{"segments": [], "tasks": []}\n```'
        data = _extract_json(text)
        assert data["segments"] == []

    def test_partial_response_segments_salvage(self):
        raw = (
            '{"segments": ['
            '{"topic": "T", "folder_key": "knowledge_folder", '
            '"filename": "T.md", "content": "body"}'
            # no closing ] or }
        )
        data = _extract_json(raw)
        assert len(data["segments"]) == 1
        assert data["segments"][0]["topic"] == "T"

    def test_raises_on_garbage(self):
        with pytest.raises(ValueError, match="No JSON"):
            _extract_json("this is not json at all, no braces")


# ── _normalize_result ─────────────────────────────────────────────────────────

class TestNormalizeResult:
    def test_truncates_long_segment_content(self):
        long_content = "x" * 2000
        raw = {"segments": [{"content": long_content}], "tasks": [], "habits": {}}
        result = _normalize_result(raw)
        assert len(result["segments"][0]["content"]) <= 1600

    def test_habits_clamped_to_0_1(self):
        raw = {"segments": [], "tasks": [], "habits": {"english": 5, "3d": -1, "learning": 0}}
        result = _normalize_result(raw)
        assert result["habits"]["english"] == 1
        assert result["habits"]["3d"] == 0

    def test_missing_habits_defaults_to_zero(self):
        raw = {"segments": [], "tasks": []}
        result = _normalize_result(raw)
        for k in ("english", "3d", "learning", "reading", "walking", "training"):
            assert result["habits"][k] == 0


# ── _extract_checkbox_tasks ───────────────────────────────────────────────────

class TestExtractCheckboxTasks:
    def test_finds_checkbox(self):
        body = "- [ ] Buy milk\n- [x] Done task\n"
        tasks = _extract_checkbox_tasks([body])
        assert any(t["text"] == "Buy milk" for t in tasks)

    def test_ignores_checked(self):
        body = "- [x] Already done\n"
        tasks = _extract_checkbox_tasks([body])
        assert not any(t["text"] == "Already done" for t in tasks)

    def test_finds_numbered(self):
        body = "1. First item\n2. Second item\n"
        tasks = _extract_checkbox_tasks([body])
        assert any(t["text"] == "First item" for t in tasks)

    def test_skips_long_numbered(self):
        long_text = "a" * 130
        body = f"1. {long_text}\n"
        tasks = _extract_checkbox_tasks([body])
        assert len(tasks) == 0


# ── _merge_tasks ──────────────────────────────────────────────────────────────

class TestMergeTasks:
    def test_no_duplicates(self):
        llm = [{"text": "Do X", "due": "", "priority": "high"}]
        checkbox = [{"text": "Do X", "due": "", "priority": ""}]
        merged = _merge_tasks(llm, checkbox)
        assert len(merged) == 1

    def test_adds_unique_checkbox(self):
        llm = [{"text": "Do X", "due": "", "priority": ""}]
        checkbox = [{"text": "Do Y", "due": "", "priority": ""}]
        merged = _merge_tasks(llm, checkbox)
        assert len(merged) == 2

    def test_case_insensitive_dedup(self):
        llm = [{"text": "do x", "due": "", "priority": ""}]
        checkbox = [{"text": "Do X", "due": "", "priority": ""}]
        merged = _merge_tasks(llm, checkbox)
        assert len(merged) == 1
