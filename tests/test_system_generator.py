from __future__ import annotations

import json

import pytest

from services import system_generator
from tests.test_system_schema import valid_config


def test_generate_returns_validated_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        system_generator.llm_router,
        "resolve",
        lambda **kwargs: {
            "provider": "ollama",
            "model": "test",
            "base_url": "http://localhost",
            "timeout": 1,
        },
    )
    monkeypatch.setattr(
        system_generator,
        "_call",
        lambda messages, route, api_key: f"```json\n{json.dumps(valid_config())}\n```",
    )
    result = system_generator.generate({"main_goal": "Find a job"})
    assert result["system_name"] == "Career Move"


def test_generate_requires_goal() -> None:
    with pytest.raises(ValueError, match="main_goal"):
        system_generator.generate({})
