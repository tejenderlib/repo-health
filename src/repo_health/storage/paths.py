"""Database path resolution (Stage 2).

Precedence: explicit argument, then the ``REPO_HEALTH_DB`` environment
variable, then the default ``~/.local/share/repo-health/memory.db``.
Resolving a path never creates files; creation happens in
``storage.db.init_db``.
"""

from __future__ import annotations

import os
from pathlib import Path

ENV_VAR = "REPO_HEALTH_DB"
DEFAULT_DB_PATH = Path.home() / ".local" / "share" / "repo-health" / "memory.db"


def resolve_db_path(explicit: str | Path | None = None) -> Path:
    """Return the database path without touching the filesystem."""
    if explicit is not None:
        return Path(explicit).expanduser()
    configured = os.environ.get(ENV_VAR, "").strip()
    if configured != "":
        return Path(configured).expanduser()
    return DEFAULT_DB_PATH
