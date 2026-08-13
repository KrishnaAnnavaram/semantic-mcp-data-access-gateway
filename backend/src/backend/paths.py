"""Locate the repository root without counting directory levels.

Three packages sit at three different depths, so `parents[N]` is a different N in
each and silently wrong the moment a file moves. Walking up for a marker is
depth-independent: it keeps working after a restructure.
"""

from __future__ import annotations

from pathlib import Path

MARKERS = (".git", "docker-compose.yml")


def repo_root(start: Path | None = None) -> Path:
    here = (start or Path(__file__)).resolve()
    for candidate in (here, *here.parents):
        if any((candidate / m).exists() for m in MARKERS):
            return candidate
    raise RuntimeError(f"repository root not found above {here}")


REPO_ROOT = repo_root()
DATA_DIR = REPO_ROOT / "data"
DOCS_DIR = REPO_ROOT / "docs"
MIGRATIONS_DIR = REPO_ROOT / "postgres" / "migrations"
KNOWLEDGE_DIR = REPO_ROOT / "knowledge"
