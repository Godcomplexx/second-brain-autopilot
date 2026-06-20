"""Tests for vault_scanner.py — scanning, hashing, status detection."""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from services import vault_scanner


class TestScanDailyNotes:
    def test_returns_empty_when_folder_missing(self, vault_config):
        vault_config["daily_folder"] = "nonexistent"
        notes = vault_scanner.scan_daily_notes()
        assert notes == []

    def test_finds_markdown_files(self, tmp_vault: Path, vault_config, data_dir):
        (tmp_vault / "02 Daily" / "2025-01-01.md").write_text("hello", encoding="utf-8")
        notes = vault_scanner.scan_daily_notes()
        assert len(notes) == 1
        assert notes[0]["name"] == "2025-01-01"

    def test_status_new_for_unprocessed(self, tmp_vault: Path, vault_config, data_dir):
        (tmp_vault / "02 Daily" / "2025-06-01.md").write_text("content", encoding="utf-8")
        notes = vault_scanner.scan_daily_notes()
        assert notes[0]["status"] == "new"

    def test_status_processed_when_hash_matches(self, tmp_vault: Path, vault_config, data_dir):
        note = tmp_vault / "02 Daily" / "2025-06-01.md"
        note.write_text("content", encoding="utf-8")
        content_hash = hashlib.sha256(note.read_bytes()).hexdigest()

        from services import index_store
        index_store.mark_processed("02 Daily/2025-06-01.md", content_hash, [])

        notes = vault_scanner.scan_daily_notes()
        assert notes[0]["status"] == "processed"

    def test_status_changed_when_hash_differs(self, tmp_vault: Path, vault_config, data_dir):
        note = tmp_vault / "02 Daily" / "2025-06-01.md"
        note.write_text("original", encoding="utf-8")

        from services import index_store
        index_store.mark_processed("02 Daily/2025-06-01.md", "old_hash_abc", [])

        notes = vault_scanner.scan_daily_notes()
        assert notes[0]["status"] == "changed"

    def test_newest_first_order(self, tmp_vault: Path, vault_config, data_dir):
        for name in ["2025-01-01", "2025-06-15", "2025-03-10"]:
            (tmp_vault / "02 Daily" / f"{name}.md").write_text("x", encoding="utf-8")
        notes = vault_scanner.scan_daily_notes()
        names = [n["name"] for n in notes]
        assert names == sorted(names, reverse=True)

    def test_limit_respected(self, tmp_vault: Path, vault_config, data_dir):
        for i in range(40):
            (tmp_vault / "02 Daily" / f"2025-01-{i+1:02d}.md").write_text("x", encoding="utf-8")
        notes = vault_scanner.scan_daily_notes(limit=10)
        assert len(notes) == 10

    def test_scan_extensions_applied(self, tmp_vault: Path, vault_config, data_dir, monkeypatch):
        (tmp_vault / "02 Daily" / "2025-01-01.md").write_text("markdown", encoding="utf-8")
        (tmp_vault / "02 Daily" / "2025-01-02.txt").write_text("text file", encoding="utf-8")

        from services import config as cfg
        app = dict(cfg.get_app())
        app["scan_extensions"] = [".txt"]
        monkeypatch.setitem(cfg._CACHE, "app", app)

        notes = vault_scanner.scan_daily_notes()
        assert all(n["name"].endswith("") for n in notes)
        names = [n["name"] for n in notes]
        assert "2025-01-02" in names
        assert "2025-01-01" not in names
