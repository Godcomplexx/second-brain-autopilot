"""Tests for aggregator.py — JSON parsing, repair, normalisation, validation."""
from __future__ import annotations

import pytest

from services.aggregator import (
    _extract_json,
    _repair_json,
    _normalize_result,
    _extract_checkbox_tasks,
    _merge_tasks,
    _validate_segment,
    _sanitize_filename,
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


# ── _sanitize_filename ────────────────────────────────────────────────────────

class TestSanitizeFilename:
    def test_adds_md_extension(self):
        assert _sanitize_filename("MyNote").endswith(".md")

    def test_preserves_valid_name(self):
        assert _sanitize_filename("My Note.md") == "My Note.md"

    def test_strips_dangerous_chars(self):
        name = _sanitize_filename("../etc/passwd.md")
        assert "/" not in name
        assert ".." not in name

    def test_empty_becomes_note(self):
        assert _sanitize_filename("") == "Note.md"

    def test_only_bad_chars_becomes_note(self):
        assert _sanitize_filename("///") == "Note.md"


# ── _validate_segment ─────────────────────────────────────────────────────────

class TestValidateSegment:
    def _valid(self, **overrides):
        base = {
            "topic": "Python",
            "folder_key": "knowledge_folder",
            "filename": "Python.md",
            "content": "body",
            "connections": [],
        }
        base.update(overrides)
        return base

    def test_valid_segment_passes(self):
        seg = _validate_segment(self._valid(), 0)
        assert seg["topic"] == "Python"
        assert seg["folder_key"] == "knowledge_folder"

    def test_unknown_folder_key_falls_back(self):
        seg = _validate_segment(self._valid(folder_key="bad_folder"), 0)
        assert seg["folder_key"] == "knowledge_folder"

    def test_non_dict_raises(self):
        with pytest.raises(ValueError):
            _validate_segment("not a dict", 0)

    def test_content_truncated_at_max(self):
        long_content = "x" * 2000
        seg = _validate_segment(self._valid(content=long_content), 0)
        assert len(seg["content"]) <= 1600

    def test_connections_cleaned(self):
        seg = _validate_segment(self._valid(connections=["  Note A  ", "", None, "Note B"]), 0)
        assert seg["connections"] == ["Note A", "Note B"]

    def test_connections_non_list_becomes_empty(self):
        seg = _validate_segment(self._valid(connections="not a list"), 0)
        assert seg["connections"] == []


# ── _normalize_result — segment limit ─────────────────────────────────────────

class TestNormalizeResultSegmentLimit:
    def test_caps_at_max_segments(self):
        segs = [
            {"topic": f"T{i}", "folder_key": "knowledge_folder",
             "filename": f"T{i}.md", "content": "x"}
            for i in range(25)
        ]
        result = _normalize_result({"segments": segs, "tasks": []})
        assert len(result["segments"]) <= 20

    def test_invalid_tasks_filtered_out(self):
        raw = {
            "segments": [],
            "tasks": [
                {"text": "valid task", "due": "", "priority": ""},
                {"text": "", "due": "", "priority": ""},   # empty text
                "not a dict",                               # wrong type
            ],
        }
        result = _normalize_result(raw)
        assert len(result["tasks"]) == 1
        assert result["tasks"][0]["text"] == "valid task"
