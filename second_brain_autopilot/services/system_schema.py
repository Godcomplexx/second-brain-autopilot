"""Validation and normalization for LLM-generated tracking-system configs."""
from __future__ import annotations

import re
import unicodedata
from datetime import date
from typing import Any

FIELD_TYPES = frozenset({"text", "long_text", "number", "date", "boolean", "select"})
MAX_ENTITIES = 5
MAX_FIELDS = 10
MAX_HABITS = 8
MAX_METRICS = 8
_KEY_RE = re.compile(r"[^a-z0-9]+")


def _required_text(value: Any, path: str, max_length: int = 120) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path} must be a non-empty string")
    clean = value.strip()
    if len(clean) > max_length:
        raise ValueError(f"{path} must be at most {max_length} characters")
    return clean


def _optional_text(value: Any, path: str, max_length: int = 1000) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError(f"{path} must be a string")
    clean = value.strip()
    if len(clean) > max_length:
        raise ValueError(f"{path} must be at most {max_length} characters")
    return clean


def _unique_name(name: str, seen: set[str], path: str) -> None:
    key = name.casefold()
    if key in seen:
        raise ValueError(f"{path} contains duplicate name {name!r}")
    seen.add(key)


def _field_key(value: Any, name: str, index: int) -> str:
    if value is not None:
        raw = _required_text(value, f"fields[{index}].key", 64).lower()
        key = _KEY_RE.sub("_", raw).strip("_")
    else:
        ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
        key = _KEY_RE.sub("_", ascii_name.lower()).strip("_")
    return key or f"field_{index + 1}"


def normalize_system_config(raw: Any) -> dict[str, Any]:
    """Return canonical config or raise ValueError on an unsafe/invalid shape."""
    if not isinstance(raw, dict):
        raise ValueError("system config must be an object")

    name = _required_text(raw.get("system_name"), "system_name")
    description = _optional_text(raw.get("description"), "description", 2000)
    raw_entities = raw.get("entities")
    if not isinstance(raw_entities, list) or not raw_entities:
        raise ValueError("entities must be a non-empty array")
    if len(raw_entities) > MAX_ENTITIES:
        raise ValueError(f"entities cannot contain more than {MAX_ENTITIES} items")

    entity_names: set[str] = set()
    entities: list[dict[str, Any]] = []
    for entity_index, raw_entity in enumerate(raw_entities):
        path = f"entities[{entity_index}]"
        if not isinstance(raw_entity, dict):
            raise ValueError(f"{path} must be an object")
        entity_name = _required_text(raw_entity.get("name"), f"{path}.name")
        _unique_name(entity_name, entity_names, "entities")
        raw_fields = raw_entity.get("fields")
        if not isinstance(raw_fields, list) or not raw_fields:
            raise ValueError(f"{path}.fields must be a non-empty array")
        if len(raw_fields) > MAX_FIELDS:
            raise ValueError(f"{path}.fields cannot contain more than {MAX_FIELDS} items")

        field_names: set[str] = set()
        field_keys: set[str] = set()
        fields: list[dict[str, Any]] = []
        for field_index, raw_field in enumerate(raw_fields):
            field_path = f"{path}.fields[{field_index}]"
            if not isinstance(raw_field, dict):
                raise ValueError(f"{field_path} must be an object")
            field_name = _required_text(raw_field.get("name"), f"{field_path}.name")
            _unique_name(field_name, field_names, f"{path}.fields")
            field_type = _required_text(
                raw_field.get("type"), f"{field_path}.type", 24
            ).lower()
            if field_type not in FIELD_TYPES:
                raise ValueError(
                    f"{field_path}.type must be one of {sorted(FIELD_TYPES)}"
                )
            key = _field_key(raw_field.get("key"), field_name, field_index)
            if key in field_keys:
                raise ValueError(f"{path}.fields contains duplicate key {key!r}")
            field_keys.add(key)

            options = raw_field.get("options", [])
            if field_type == "select":
                if not isinstance(options, list) or not (1 <= len(options) <= 20):
                    raise ValueError(f"{field_path}.options must contain 1 to 20 values")
                normalized_options = [
                    _required_text(option, f"{field_path}.options", 80)
                    for option in options
                ]
                if len({option.casefold() for option in normalized_options}) != len(
                    normalized_options
                ):
                    raise ValueError(f"{field_path}.options contains duplicates")
            else:
                if options not in (None, []):
                    raise ValueError(f"{field_path}.options is only valid for select fields")
                normalized_options = []

            fields.append({
                "name": field_name,
                "key": key,
                "type": field_type,
                "required": bool(raw_field.get("required", False)),
                "options": normalized_options,
            })
        entities.append({"name": entity_name, "fields": fields})

    habits = _normalize_habits(raw.get("habits", []))
    metrics = _normalize_metrics(raw.get("metrics", raw.get("weekly_kpi", [])))
    return {
        "system_name": name,
        "description": description,
        "entities": entities,
        "habits": habits,
        "metrics": metrics,
    }


def _normalize_habits(raw_habits: Any) -> list[dict[str, str]]:
    if not isinstance(raw_habits, list):
        raise ValueError("habits must be an array")
    if len(raw_habits) > MAX_HABITS:
        raise ValueError(f"habits cannot contain more than {MAX_HABITS} items")
    seen: set[str] = set()
    habits: list[dict[str, str]] = []
    for index, habit in enumerate(raw_habits):
        path = f"habits[{index}]"
        if isinstance(habit, str):
            name, target = _required_text(habit, path), ""
        elif isinstance(habit, dict):
            name = _required_text(habit.get("name"), f"{path}.name")
            target = _optional_text(habit.get("target"), f"{path}.target", 120)
        else:
            raise ValueError(f"{path} must be a string or object")
        _unique_name(name, seen, "habits")
        habits.append({"name": name, "target": target})
    return habits


def _normalize_metrics(raw_metrics: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_metrics, list):
        raise ValueError("metrics must be an array")
    if len(raw_metrics) > MAX_METRICS:
        raise ValueError(f"metrics cannot contain more than {MAX_METRICS} items")
    seen: set[str] = set()
    metrics: list[dict[str, Any]] = []
    for index, metric in enumerate(raw_metrics):
        path = f"metrics[{index}]"
        if not isinstance(metric, dict):
            raise ValueError(f"{path} must be an object")
        name = _required_text(metric.get("name"), f"{path}.name")
        _unique_name(name, seen, "metrics")
        target = metric.get("target")
        if isinstance(target, bool) or not isinstance(target, (int, float)):
            raise ValueError(f"{path}.target must be a number")
        metrics.append({
            "name": name,
            "target": float(target),
            "unit": _optional_text(metric.get("unit"), f"{path}.unit", 40),
        })
    return metrics


def validate_record_values(
    fields: list[dict[str, Any]], raw_values: Any, *, partial: bool = False
) -> dict[str, Any]:
    """Validate public record values against canonical field definitions."""
    if not isinstance(raw_values, dict):
        raise ValueError("values must be an object")
    by_key = {field["key"]: field for field in fields}
    unknown = set(raw_values) - set(by_key)
    if unknown:
        raise ValueError(f"unknown field keys: {', '.join(sorted(unknown))}")
    if not partial:
        missing = [
            field["key"] for field in fields
            if field["required"] and field["key"] not in raw_values
        ]
        if missing:
            raise ValueError(f"missing required fields: {', '.join(missing)}")

    result: dict[str, Any] = {}
    for key, value in raw_values.items():
        field = by_key[key]
        if value in (None, "") and not field["required"]:
            result[key] = None
            continue
        field_type = field["type"]
        if field_type in {"text", "long_text"}:
            if not isinstance(value, str):
                raise ValueError(f"{key} must be a string")
            limit = 10000 if field_type == "long_text" else 500
            if len(value) > limit:
                raise ValueError(f"{key} must be at most {limit} characters")
            result[key] = value
        elif field_type == "number":
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{key} must be a number")
            result[key] = value
        elif field_type == "boolean":
            if not isinstance(value, bool):
                raise ValueError(f"{key} must be a boolean")
            result[key] = value
        elif field_type == "date":
            if not isinstance(value, str):
                raise ValueError(f"{key} must be an ISO date")
            try:
                date.fromisoformat(value)
            except ValueError as exc:
                raise ValueError(f"{key} must be an ISO date") from exc
            result[key] = value
        elif field_type == "select":
            if value not in field["options"]:
                raise ValueError(f"{key} must be one of {field['options']}")
            result[key] = value
    return result
