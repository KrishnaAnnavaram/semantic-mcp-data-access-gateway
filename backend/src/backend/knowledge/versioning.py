"""Deterministic content identities used to invalidate derived Redis work."""

from __future__ import annotations

import hashlib
from pathlib import Path


def corpus_version(root: Path) -> str:
    """Hash relative paths and bytes; timestamps never define knowledge."""
    digest = hashlib.sha256()
    if not root.is_dir():
        return "missing"
    paths = sorted(path for path in root.rglob("*.md") if path.is_file())
    for path in paths:
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()
