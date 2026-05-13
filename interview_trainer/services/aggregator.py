from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from . import config, ollama_client, openai_client, llm_router, note_parser


_PROMPT_FILE = Path(__file__).resolve().parent.parent / "prompts" / "aggregator.txt"
_PROMPT: str | None = None
_PROMPT_MTIME: float = 0.0


def _get_prompt() -> str:
    global _PROMPT, _PROMPT_MTIME
    mtime = _PROMPT_FILE.stat().st_mtime
    if _PROMPT is None or mtime != _PROMPT_MTIME:
        _PROMPT = _PROMPT_FILE.read_text(encoding="utf-8").strip()
        _PROMPT_MTIME = mtime
    return _PROMPT


def _trim(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n\n[...truncated...]"


def _repair_json(text: str) -> str:
    """Close unclosed brackets/braces left by truncated LLM output."""
    text = text.rstrip().rstrip(",")
    stack: list[str] = []
    in_string = False
    escape_next = False
    for ch in text:
        if escape_next:
            escape_next = False
            continue
        if ch == "\\" and in_string:
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch in "{[":
            stack.append(ch)
        elif ch in "}]" and stack:
            stack.pop()
    closing = {"{": "}", "[": "]"}
    for opener in reversed(stack):
        text += closing[opener]
    return text


def _extract_json(text: str) -> Any:
    # 1. Pull out ```json ... ``` block if present, else use full text
    match = re.search(r"```json\s*(.*?)(?:```|$)", text, re.DOTALL)
    raw = match.group(1).strip() if match else text.strip()

    # 2. Try direct parse
    try:
        return json.loads(raw)
    except Exception:
        pass

    # 3. Try repairing truncated JSON
    try:
        return json.loads(_repair_json(raw))
    except Exception:
        pass

    # 4. Salvage segments array even if outer object is broken
    seg_match = re.search(r'"segments"\s*:\s*(\[.*)', raw, re.DOTALL)
    if seg_match:
        try:
            seg_text = _repair_json(seg_match.group(1))
            segments = json.loads(seg_text)
            return {"segments": segments, "tasks": []}
        except Exception:
            pass

    # 5. Extract individual segment objects that look complete (have all 4 required keys)
    seg_objects = re.findall(
        r'\{[^{}]*"topic"\s*:[^{}]*"folder_key"\s*:[^{}]*"filename"\s*:[^{}]*"content"\s*:[^{}]*\}',
        raw, re.DOTALL,
    )
    if seg_objects:
        segments = []
        for obj in seg_objects:
            try:
                segments.append(json.loads(_repair_json(obj)))
            except Exception:
                pass
        if segments:
            return {"segments": segments, "tasks": []}

    # 6. Last resort: find any {...} in full text
    obj_match = re.search(r"\{.*\}", text, re.DOTALL)
    if obj_match:
        try:
            return json.loads(_repair_json(obj_match.group(0)))
        except Exception:
            pass

    raise ValueError("No JSON found in LLM response")


_MAX_SEGMENT_CONTENT = 1500  # chars — matches the prompt instruction to the LLM


_HABIT_KEYS = ("english", "3d", "learning", "reading", "walking", "training")


def _normalize_result(raw_result: dict[str, Any]) -> dict[str, Any]:
    segments = raw_result.get("segments", [])
    for seg in segments:
        content = seg.get("content", "")
        if len(content) > _MAX_SEGMENT_CONTENT:
            seg["content"] = content[:_MAX_SEGMENT_CONTENT] + "\n\n— see source note for full text —"

    raw_habits = raw_result.get("habits", {})
    habits = {k: min(1, max(0, int(float(raw_habits.get(k, 0) or 0)))) for k in _HABIT_KEYS}

    return {
        "segments": segments,
        "tasks": raw_result.get("tasks", []),
        "habits": habits,
    }


def aggregate(
    rel_paths: list[str],
    provider: str = "ollama",
    api_key: str = "",
    user_model: str | None = None,
    base_url: str | None = None,
    existing_files: list[str] | None = None,
) -> dict[str, Any]:
    app = config.get_app()
    max_chars = app.get("aggregator_prompt_max_chars", 24000)
    note_max = app.get("max_note_chars", 8000)

    notes_text_parts: list[str] = []
    for rel in rel_paths:
        parsed = note_parser.load_note(rel)
        chunk = f"## Note: {rel}\n\n{_trim(parsed['body'], note_max)}"
        notes_text_parts.append(chunk)

    combined = _trim("\n\n---\n\n".join(notes_text_parts), max_chars)

    if existing_files:
        file_list = "\n".join(f"- {f}" for f in existing_files)
        combined += f"\n\n---\nExisting vault files (if the topic matches one of these, use that EXACT filename):\n{file_list}"

    messages = [
        {"role": "system", "content": _get_prompt()},
        {"role": "user", "content": combined},
    ]

    route = llm_router.resolve(
        mode="aggregator",
        provider=provider,
        user_model=user_model,
        base_url=base_url,
    )

    if route["provider"] == "openai":
        raw = openai_client.chat(
            messages, route["model"], api_key,
            base_url=route["base_url"], timeout=route["timeout"],
        )
    else:
        raw = ollama_client.chat(
            messages, route["model"],
            base_url=route["base_url"], timeout=route["timeout"],
        )

    try:
        result = _normalize_result(_extract_json(raw))
    except Exception:
        result = {"segments": [], "tasks": [], "raw_response": raw, "parse_error": True}

    return {
        "sources": rel_paths,
        "result": result,
        "raw_llm": raw,
    }
