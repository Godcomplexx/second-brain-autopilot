"""Safe, atomic file I/O confined to the configured vault.

All public functions resolve paths relative to the vault root and raise
ValueError if the resolved path would escape the vault (path traversal,
symlink escape, absolute path injection).

Atomic writes use a sibling temp file + Path.replace() so a crash during
write never leaves a half-written file.
"""
from __future__ import annotations

import os
import tempfile
import logging
from pathlib import Path

from . import config

_LOGGER = logging.getLogger(__name__)


class PathTraversalError(ValueError):
    """Raised when a requested path escapes the vault root."""


def _vault_root() -> Path:
    obs = config.get_obsidian()
    return Path(obs["vault_path"]).resolve()


def safe_resolve(rel: str, *, allow_absolute: bool = False) -> Path:
    """Resolve *rel* inside the vault, refusing traversal attempts.

    Raises PathTraversalError if the resolved path is outside the vault.
    The *.md* extension is NOT enforced here — callers that require it
    should check themselves.
    """
    if not allow_absolute and os.path.isabs(rel):
        raise PathTraversalError(f"Absolute paths are not allowed: {rel!r}")

    root = _vault_root()
    candidate = (root / rel).resolve()

    # On Windows, resolve() follows symlinks so this also blocks symlink escapes
    try:
        candidate.relative_to(root)
    except ValueError:
        raise PathTraversalError(
            f"Path {rel!r} resolves outside the vault root ({root})"
        )
    return candidate


def require_md(path: Path) -> None:
    """Raise ValueError if *path* does not have a .md suffix."""
    if path.suffix.lower() != ".md":
        raise ValueError(f"Only .md files are allowed, got: {path.name!r}")


def atomic_write(path: Path, text: str, encoding: str = "utf-8") -> None:
    """Write *text* to *path* atomically using a temp file + rename.

    Creates parent directories as needed.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=".tmp-", suffix=".md")
    try:
        with os.fdopen(fd, "w", encoding=encoding) as fh:
            fh.write(text)
        Path(tmp_name).replace(path)
    except (OSError, UnicodeEncodeError):
        try:
            os.unlink(tmp_name)
        except OSError as cleanup_error:
            _LOGGER.debug(
                "Could not remove temporary file %s: %s",
                tmp_name,
                cleanup_error,
            )
        raise


def read_text(rel: str, encoding: str = "utf-8") -> str:
    """Read a vault file by relative path, with traversal protection."""
    path = safe_resolve(rel)
    return path.read_text(encoding=encoding, errors="ignore")


def write_text(rel: str, text: str, encoding: str = "utf-8") -> None:
    """Atomically write *text* to a vault file by relative path."""
    path = safe_resolve(rel)
    require_md(path)
    atomic_write(path, text, encoding)
