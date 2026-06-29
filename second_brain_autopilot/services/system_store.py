"""Transactional persistence and retrieval of generated systems."""
from __future__ import annotations

import json
import sqlite3
from typing import Any

from . import database
from .system_schema import normalize_system_config


def create(config: dict[str, Any], source_prompt: str = "") -> dict[str, Any]:
    normalized = normalize_system_config(config)
    with database.connection() as db:
        cursor = db.execute(
            "INSERT INTO systems(name, description, source_prompt) VALUES (?, ?, ?)",
            (normalized["system_name"], normalized["description"], source_prompt),
        )
        system_id = int(cursor.lastrowid)
        for entity_pos, entity in enumerate(normalized["entities"]):
            entity_cursor = db.execute(
                "INSERT INTO entities(system_id, name, position) VALUES (?, ?, ?)",
                (system_id, entity["name"], entity_pos),
            )
            entity_id = int(entity_cursor.lastrowid)
            for field_pos, field in enumerate(entity["fields"]):
                db.execute(
                    """
                    INSERT INTO fields(
                        entity_id, name, field_key, field_type,
                        required, options_json, position
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        entity_id,
                        field["name"],
                        field["key"],
                        field["type"],
                        int(field["required"]),
                        json.dumps(field["options"], ensure_ascii=False),
                        field_pos,
                    ),
                )
        for position, habit in enumerate(normalized["habits"]):
            db.execute(
                "INSERT INTO habits(system_id, name, target, position) VALUES (?, ?, ?, ?)",
                (system_id, habit["name"], habit["target"], position),
            )
        for position, metric in enumerate(normalized["metrics"]):
            db.execute(
                """
                INSERT INTO metrics(system_id, name, target, unit, position)
                VALUES (?, ?, ?, ?, ?)
                """,
                (system_id, metric["name"], metric["target"], metric["unit"], position),
            )
    result = get(system_id)
    if result is None:
        raise RuntimeError("created system could not be loaded")
    return result


def list_all() -> list[dict[str, Any]]:
    with database.connection() as db:
        rows = db.execute(
            """
            SELECT s.id, s.name, s.description, s.created_at, s.updated_at,
                   COUNT(DISTINCT e.id) AS entity_count,
                   COUNT(DISTINCT r.id) AS record_count
            FROM systems s
            LEFT JOIN entities e ON e.system_id = s.id
            LEFT JOIN records r ON r.entity_id = e.id
            GROUP BY s.id
            ORDER BY s.updated_at DESC, s.id DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def get(system_id: int) -> dict[str, Any] | None:
    with database.connection() as db:
        system = db.execute(
            "SELECT * FROM systems WHERE id = ?", (system_id,)
        ).fetchone()
        if system is None:
            return None
        entities = db.execute(
            "SELECT id, name FROM entities WHERE system_id = ? ORDER BY position, id",
            (system_id,),
        ).fetchall()
        result_entities: list[dict[str, Any]] = []
        for entity in entities:
            fields = db.execute(
                """
                SELECT id, name, field_key, field_type, required, options_json
                FROM fields WHERE entity_id = ? ORDER BY position, id
                """,
                (entity["id"],),
            ).fetchall()
            result_entities.append({
                "id": entity["id"],
                "name": entity["name"],
                "fields": [_public_field(field) for field in fields],
            })
        habits = [
            dict(row)
            for row in db.execute(
                "SELECT id, name, target FROM habits WHERE system_id = ? "
                "ORDER BY position, id",
                (system_id,),
            ).fetchall()
        ]
        metrics = [
            dict(row)
            for row in db.execute(
                "SELECT id, name, target, unit FROM metrics WHERE system_id = ? "
                "ORDER BY position, id",
                (system_id,),
            ).fetchall()
        ]
    return {
        "id": system["id"],
        "system_name": system["name"],
        "description": system["description"],
        "source_prompt": system["source_prompt"],
        "created_at": system["created_at"],
        "updated_at": system["updated_at"],
        "entities": result_entities,
        "habits": habits,
        "metrics": metrics,
    }


def delete(system_id: int) -> bool:
    with database.connection() as db:
        cursor = db.execute("DELETE FROM systems WHERE id = ?", (system_id,))
        return cursor.rowcount > 0


def _public_field(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "key": row["field_key"],
        "type": row["field_type"],
        "required": bool(row["required"]),
        "options": json.loads(row["options_json"]),
    }
