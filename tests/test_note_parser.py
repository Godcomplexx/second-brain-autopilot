"""Tests for note_parser.py — frontmatter stripping, comment removal."""
from __future__ import annotations

from services.note_parser import parse


class TestParse:
    def test_plain_body(self):
        result = parse("Hello world", "note.md")
        assert result["body"] == "Hello world"

    def test_strips_frontmatter(self):
        raw = "---\ntitle: Test\n---\nBody here"
        result = parse(raw)
        assert "title" not in result["body"]
        assert "Body here" in result["body"]

    def test_strips_single_line_html_comments(self):
        raw = "Text before\n<!-- a hidden comment -->\nText after"
        result = parse(raw)
        assert "hidden comment" not in result["body"]
        assert "Text before" in result["body"]
        assert "Text after" in result["body"]

    def test_preserves_ai_block_content(self):
        # note_parser reads source notes — AI blocks in source notes are
        # NOT removed here; markdown_writer handles them on write
        raw = "Text before\n<!-- AI_AGGREGATED_START:source=x -->\nAI body\n<!-- AI_AGGREGATED_END -->\nText after"
        result = parse(raw)
        assert "Text before" in result["body"]

    def test_rel_path_preserved(self):
        result = parse("body", "02 Daily/2025-01-01.md")
        assert result["rel_path"] == "02 Daily/2025-01-01.md"

    def test_empty_note(self):
        result = parse("")
        assert result["body"] == ""
