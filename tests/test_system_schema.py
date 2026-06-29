from __future__ import annotations

import pytest

from services.system_schema import normalize_system_config, validate_record_values


def valid_config() -> dict:
    return {
        "system_name": "Career Move",
        "description": "Track a focused relocation plan.",
        "entities": [{
            "name": "Applications",
            "fields": [
                {"name": "Company", "type": "text", "required": True},
                {
                    "name": "Status",
                    "type": "select",
                    "options": ["saved", "applied", "offer"],
                },
                {"name": "Date", "type": "date"},
            ],
        }],
        "habits": [{"name": "English", "target": "60 min/day"}],
        "metrics": [{"name": "Applications", "target": 10, "unit": "per week"}],
    }


def test_normalizes_config_and_generates_keys() -> None:
    config = normalize_system_config(valid_config())
    assert config["entities"][0]["fields"][0]["key"] == "company"
    assert config["metrics"][0]["target"] == 10.0


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda c: c["entities"].append(c["entities"][0].copy()), "duplicate name"),
        (lambda c: c["entities"][0]["fields"][0].update(type="money"), "must be one of"),
        (lambda c: c["entities"][0]["fields"][1].update(options=[]), "1 to 20"),
        (lambda c: c.update(entities=[]), "non-empty array"),
    ],
)
def test_rejects_invalid_configs(change, message: str) -> None:
    config = valid_config()
    change(config)
    with pytest.raises(ValueError, match=message):
        normalize_system_config(config)


def test_validates_dynamic_values() -> None:
    fields = normalize_system_config(valid_config())["entities"][0]["fields"]
    clean = validate_record_values(
        fields,
        {"company": "Acme", "status": "applied", "date": "2026-06-29"},
    )
    assert clean["status"] == "applied"

    with pytest.raises(ValueError, match="must be one of"):
        validate_record_values(fields, {"company": "Acme", "status": "unknown"})
    with pytest.raises(ValueError, match="ISO date"):
        validate_record_values(fields, {"company": "Acme", "date": "29/06/2026"})
