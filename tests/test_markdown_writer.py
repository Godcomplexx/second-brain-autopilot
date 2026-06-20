"""Tests for markdown_writer.py — AI block creation, hash guard, update."""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from services import markdown_writer


class TestBuildBlock:
    def test_contains_markers(self):
        from services.markdown_writer import _build_block
        block = _build_block("body text", "source.md", "2025-01-01")
        assert "<!-- AI_AGGREGATED_START" in block
        assert "<!-- AI_AGGREGATED_END -->" in block

    def test_contains_content(self):
        from services.markdown_writer import _build_block
        block = _build_block("my content", "source.md", "2025-01-01")
        assert "my content" in block

    def test_connections_appended(self):
        from services.markdown_writer import _build_block
        block = _build_block("body", "s.md", "2025-01-01", connections=["Note A", "Note B"])
        assert "## Connections" in block
        assert "- Note A" in block


class TestWriteAggregation:
    def test_creates_new_file(self, tmp_vault: Path, vault_config, data_dir):
        source = tmp_vault / "02 Daily" / "2025-06-01.md"
        source.write_text("original note", encoding="utf-8")
        scan_hash = hashlib.sha256(source.read_bytes()).hexdigest()

        result = markdown_writer.write_aggregation(
            source_rel="02 Daily/2025-06-01.md",
            target_folder_key="knowledge_folder",
            target_filename="MyNote.md",
            content="extracted content",
            scan_hash=scan_hash,
        )

        assert result["success"] is True
        target = tmp_vault / "05 Knowledge" / "MyNote.md"
        assert target.exists()
        assert "extracted content" in target.read_text(encoding="utf-8")

    def test_blocks_on_hash_mismatch(self, tmp_vault: Path, vault_config, data_dir):
        source = tmp_vault / "02 Daily" / "2025-06-01.md"
        source.write_text("original", encoding="utf-8")

        result = markdown_writer.write_aggregation(
            source_rel="02 Daily/2025-06-01.md",
            target_folder_key="knowledge_folder",
            target_filename="Out.md",
            content="content",
            scan_hash="wrong_hash_000",
        )

        assert result["success"] is False
        assert "changed" in result["error"].lower() or "hash" in result["error"].lower()

    def test_updates_existing_block_for_same_source(self, tmp_vault: Path, vault_config, data_dir):
        source = tmp_vault / "02 Daily" / "2025-06-01.md"
        source.write_text("note", encoding="utf-8")
        scan_hash = hashlib.sha256(source.read_bytes()).hexdigest()

        markdown_writer.write_aggregation(
            source_rel="02 Daily/2025-06-01.md",
            target_folder_key="knowledge_folder",
            target_filename="Out.md",
            content="first version",
            scan_hash=scan_hash,
        )

        # mark_processed is now the caller's responsibility; do it manually
        from services import index_store
        index_store.mark_processed("02 Daily/2025-06-01.md", scan_hash, ["05 Knowledge/Out.md"])

        scan_hash2 = hashlib.sha256(source.read_bytes()).hexdigest()
        markdown_writer.write_aggregation(
            source_rel="02 Daily/2025-06-01.md",
            target_folder_key="knowledge_folder",
            target_filename="Out.md",
            content="second version",
            scan_hash=scan_hash2,
        )

        text = (tmp_vault / "05 Knowledge" / "Out.md").read_text(encoding="utf-8")
        assert "second version" in text
        assert "first version" not in text

    def test_multiple_sources_in_same_file(self, tmp_vault: Path, vault_config, data_dir):
        for name in ["2025-06-01.md", "2025-06-02.md"]:
            note = tmp_vault / "02 Daily" / name
            note.write_text(f"note {name}", encoding="utf-8")
            h = hashlib.sha256(note.read_bytes()).hexdigest()
            markdown_writer.write_aggregation(
                source_rel=f"02 Daily/{name}",
                target_folder_key="knowledge_folder",
                target_filename="Shared.md",
                content=f"content from {name}",
                scan_hash=h,
            )

        text = (tmp_vault / "05 Knowledge" / "Shared.md").read_text(encoding="utf-8")
        assert "content from 2025-06-01.md" in text
        assert "content from 2025-06-02.md" in text

    def test_source_not_found_returns_error(self, tmp_vault: Path, vault_config, data_dir):
        result = markdown_writer.write_aggregation(
            source_rel="02 Daily/ghost.md",
            target_folder_key="knowledge_folder",
            target_filename="Out.md",
            content="x",
            scan_hash="abc",
        )
        assert result["success"] is False

    def test_returns_source_hash_on_success(self, tmp_vault: Path, vault_config, data_dir):
        source = tmp_vault / "02 Daily" / "2025-06-01.md"
        source.write_text("content", encoding="utf-8")
        scan_hash = hashlib.sha256(source.read_bytes()).hexdigest()

        result = markdown_writer.write_aggregation(
            source_rel="02 Daily/2025-06-01.md",
            target_folder_key="knowledge_folder",
            target_filename="Out.md",
            content="body",
            scan_hash=scan_hash,
        )
        assert result["success"] is True
        assert result["source_hash"] == scan_hash


class TestPreviewWrite:
    def test_no_mkdir_side_effect(self, tmp_vault: Path, vault_config, data_dir):
        new_folder = tmp_vault / "05 Knowledge" / "SubFolder"
        assert not new_folder.exists()

        markdown_writer.preview_write(
            source_rel="02 Daily/note.md",
            target_folder_key="knowledge_folder",
            target_filename="SubFolder/Deep.md",
            content="preview content",
        )

        assert not new_folder.exists()

    def test_returns_block_preview(self, tmp_vault: Path, vault_config, data_dir):
        result = markdown_writer.preview_write(
            source_rel="02 Daily/note.md",
            target_folder_key="knowledge_folder",
            target_filename="Out.md",
            content="preview body",
        )
        assert "preview body" in result["block_preview"]
        assert result["target_exists"] is False
