from __future__ import annotations

from pathlib import Path

import pytest

from services import record_store, system_exporter, system_store
from services.storage import PathTraversalError
from tests.test_system_schema import valid_config


def test_preview_and_export(
    systems_db: Path, vault_config: dict, tmp_vault: Path
) -> None:
    system = system_store.create(valid_config())
    record_store.create(
        system["entities"][0]["id"],
        {"company": "Acme", "status": "offer", "date": "2026-06-29"},
    )
    preview = system_exporter.render(system["id"])
    assert "| Acme | offer | 2026-06-29 |" in preview["system_markdown"]
    assert "English:: 0" in preview["daily_template"]

    result = system_exporter.export(system["id"])
    exported = tmp_vault / result["path"]
    assert exported.exists()
    assert exported.read_text(encoding="utf-8").startswith("# Career Move")


def test_export_blocks_path_traversal(systems_db: Path, vault_config: dict) -> None:
    system = system_store.create(valid_config())
    with pytest.raises(PathTraversalError):
        system_exporter.export(system["id"], "../outside.md")
