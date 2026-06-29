"""CRUD for records belonging to dynamically defined entities."""
from __future__ import annotations

import json
import sqlite3
from typing import Any

from . import database
from .system_schema import validate_record_values


def _fields(db: sqlite3.Connection, entity_id: int) -> list[dict[str, Any]]:
    entity = db.execute("SELECT id FROM entities WHERE id = ?", (entity_id,)).fetchone()
    if entity is None:
        raise LookupError("entity not found")
    rows = db.execute(
        """
        SELECT id, name, field_key, field_type, required, options_json
        FROM fields WHERE entity_id = ? ORDER BY position, id
        """,
        (entity_id,),
    ).fetchall()
    return [
        {
            "id": row["id"],
            "name": row["name"],
            "key": row["field_key"],
            "type": row["field_type"],
            "required": bool(row["required"]),
            "options": json.loads(row["options_json"]),
        }
        for row in rows
    ]


def create(entity_id: int, values: dict[str, Any]) -> dict[str, Any]:
    with database.connection() as db:
        fields = _fields(db, entity_id)
        clean = validate_record_values(fields, values)
        cursor = db.execute("INSERT INTO records(entity_id) VALUES (?)", (entity_id,))
        record_id = int(cursor.lastrowid)
        by_key = {field["key"]: field for field in fields}
        for key, value in clean.items():
            db.execute(
                "INSERT INTO record_values(record_id, field_id, value_json) "
                "VALUES (?, ?, ?)",
                (record_id, by_key[key]["id"], json.dumps(value, ensure_ascii=False)),
            )
    result = get(record_id)
    if result is None:
        raise RuntimeError("created record could not be loaded")
    return result


def list_for_entity(entity_id: int) -> list[dict[str, Any]]:
    with database.connection() as db:
        fields = _fields(db, entity_id)
        rows = db.execute(
            "SELECT id, entity_id, created_at, updated_at FROM records "
            "WHERE entity_id = ? ORDER BY id DESC",
            (entity_id,),
        ).fetchall()
        return [_hydrate(db, row, fields) for row in rows]


def get(record_id: int) -> dict[str, Any] | None:
    with database.connection() as db:
        row = db.execute(
            "SELECT id, entity_id, created_at, updated_at FROM records WHERE id = ?",
            (record_id,),
        ).fetchone()
        if row is None:
            return None
        return _hydrate(db, row, _fields(db, int(row["entity_id"])))


def update(record_id: int, values: dict[str, Any]) -> dict[str, Any] | None:
    with database.connection() as db:
        record = db.execute(
            "SELECT id, entity_id FROM records WHERE id = ?", (record_id,)
        ).fetchone()
        if record is None:
            return None
        fields = _fields(db, int(record["entity_id"]))
        clean = validate_record_values(fields, values, partial=True)
        by_key = {field["key"]: field for field in fields}
        for key, value in clean.items():
            db.execute(
                """
                INSERT INTO record_values(record_id, field_id, value_json)
                VALUES (?, ?, ?)
                ON CONFLICT(record_id, field_id)
                DO UPDATE SET value_json = excluded.value_json
                """,
                (record_id, by_key[key]["id"], json.dumps(value, ensure_ascii=False)),
            )
        db.execute(
            "UPDATE records SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (record_id,),
        )
    return get(record_id)


def delete(record_id: int) -> bool:
    with database.connection() as db:
        cursor = db.execute("DELETE FROM records WHERE id = ?", (record_id,))
        return cursor.rowcount > 0


def _hydrate(
    db: sqlite3.Connection,
    row: sqlite3.Row,
    fields: list[dict[str, Any]],
) -> dict[str, Any]:
    values = {
        field["key"]: None
        for field in fields
    }
    value_rows = db.execute(
        """
        SELECT f.field_key, rv.value_json
        FROM record_values rv
        JOIN fields f ON f.id = rv.field_id
        WHERE rv.record_id = ?
        """,
        (row["id"],),
    ).fetchall()
    for value_row in value_rows:
        values[value_row["field_key"]] = json.loads(value_row["value_json"])
    return {
        "id": row["id"],
        "entity_id": row["entity_id"] if "entity_id" in row.keys() else None,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "values": values,
    }
