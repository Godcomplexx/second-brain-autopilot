"""Tests for storage.py — path traversal protection and atomic writes."""
from __future__ import annotations

from pathlib import Path

import pytest

from services import storage
from services.storage import PathTraversalError, atomic_write, require_md, safe_resolve


class TestSafeResolve:
    def test_simple_relative_path(self, vault_config, tmp_vault):
        path = safe_resolve("02 Daily/note.md")
        assert path == (tmp_vault / "02 Daily" / "note.md").resolve()

    def test_blocks_dotdot_traversal(self, vault_config, tmp_vault):
        with pytest.raises(PathTraversalError):
            safe_resolve("../etc/passwd")

    def test_blocks_nested_dotdot(self, vault_config, tmp_vault):
        with pytest.raises(PathTraversalError):
            safe_resolve("05 Knowledge/../../secret.md")

    def test_blocks_absolute_path(self, vault_config, tmp_vault):
        with pytest.raises(PathTraversalError):
            safe_resolve("/etc/passwd")

    def test_path_inside_vault_ok(self, vault_config, tmp_vault):
        path = safe_resolve("05 Knowledge/sub/note.md")
        assert str(tmp_vault) in str(path)


class TestRequireMd:
    def test_accepts_md(self, tmp_vault):
        require_md(tmp_vault / "note.md")  # no exception

    def test_rejects_txt(self, tmp_vault):
        with pytest.raises(ValueError, match="Only .md"):
            require_md(tmp_vault / "note.txt")

    def test_rejects_no_extension(self, tmp_vault):
        with pytest.raises(ValueError):
            require_md(tmp_vault / "note")


class TestAtomicWrite:
    def test_writes_content(self, tmp_vault):
        target = tmp_vault / "test.md"
        atomic_write(target, "hello world")
        assert target.read_text() == "hello world"

    def test_creates_parent_dirs(self, tmp_vault):
        target = tmp_vault / "new" / "deep" / "note.md"
        atomic_write(target, "content")
        assert target.exists()

    def test_no_tmp_file_left_after_success(self, tmp_vault):
        target = tmp_vault / "note.md"
        atomic_write(target, "data")
        tmp_files = list(tmp_vault.glob(".tmp-*"))
        assert tmp_files == []

    def test_overwrites_existing(self, tmp_vault):
        target = tmp_vault / "note.md"
        target.write_text("old")
        atomic_write(target, "new")
        assert target.read_text() == "new"
