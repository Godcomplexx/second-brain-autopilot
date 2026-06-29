from __future__ import annotations

import sqlite3

import pytest

from services import database, record_store, system_store
from tests.test_system_schema import valid_config


def test_migration_and_system_crud(systems_db) -> None:
    created = system_store.create(valid_config(), "Find a remote job")
    assert systems_db.exists()
    assert created["system_name"] == "Career Move"
    assert created["entities"][0]["fields"][0]["key"] == "company"
    assert system_store.list_all()[0]["entity_count"] == 1

    assert system_store.delete(created["id"]) is True
    assert system_store.get(created["id"]) is None


def test_record_crud_and_type_validation(systems_db) -> None:
    system = system_store.create(valid_config())
    entity_id = system["entities"][0]["id"]
    record = record_store.create(
        entity_id,
        {"company": "Acme", "status": "applied", "date": "2026-06-29"},
    )
    assert record["values"]["company"] == "Acme"
    assert record_store.list_for_entity(entity_id)[0]["entity_id"] == entity_id

    updated = record_store.update(record["id"], {"status": "offer"})
    assert updated is not None
    assert updated["values"]["status"] == "offer"

    with pytest.raises(ValueError, match="must be one of"):
        record_store.update(record["id"], {"status": "invalid"})
    assert record_store.delete(record["id"]) is True


def test_create_rolls_back_whole_system_on_database_error(systems_db) -> None:
    database.initialize()
    with sqlite3.connect(systems_db) as db:
        db.execute(
            """
            CREATE TRIGGER reject_entity BEFORE INSERT ON entities
            WHEN NEW.name = 'Applications'
            BEGIN SELECT RAISE(ABORT, 'rejected for test'); END
            """
        )

    with pytest.raises(sqlite3.IntegrityError, match="rejected for test"):
        system_store.create(valid_config())
    assert system_store.list_all() == []
