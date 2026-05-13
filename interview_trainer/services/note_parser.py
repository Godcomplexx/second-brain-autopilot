from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from . import config

_FRONTMATTER_RE = re.compile(r"^---\s*\n.*?\n---\s*\n", re.DOTALL)
_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)


def load_note(rel_path: str) -> dict[str, Any]:
    obs = config.get_obsidian()
    vault = Path(obs["vault_path"])
    path = vault / rel_path
    raw = path.read_text(encoding="utf-8")
    return parse(raw, rel_path)


def parse(raw: str, rel_path: str = "") -> dict[str, Any]:
    body = raw
    fm_match = _FRONTMATTER_RE.match(raw)
    if fm_match:
        body = raw[fm_match.end():]
    body = _COMMENT_RE.sub("", body)
    return {"rel_path": rel_path, "body": body.strip()}
