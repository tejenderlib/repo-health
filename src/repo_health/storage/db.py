"""SQLite connections and database initialization (Stage 2).

Only Repo Health's own database file is ever created or modified here.
Target repositories are never touched: this module performs no reads or
writes outside the database path it is given.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from repo_health.core.exceptions import DatabaseError
from repo_health.storage import schema as schema_module
from repo_health.storage.paths import resolve_db_path


@contextmanager
def connect(path: str | Path) -> Iterator[sqlite3.Connection]:
    """Yield a read-write connection with foreign keys enforced.

    Commits on clean exit, rolls back on error, and always closes.
    """
    location = str(path)
    try:
        conn = sqlite3.connect(location)
    except sqlite3.Error as exc:
        raise DatabaseError(f"cannot open database at {location}: {exc}") from exc
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        yield conn
    except sqlite3.Error as exc:
        conn.rollback()
        raise DatabaseError(f"database operation failed at {location}: {exc}") from exc
    except Exception:
        conn.rollback()
        raise
    else:
        conn.commit()
    finally:
        conn.close()


@contextmanager
def connect_readonly(path: str | Path) -> Iterator[sqlite3.Connection]:
    """Yield a read-only connection; fails if the database is missing."""
    location = str(path)
    try:
        conn = sqlite3.connect(f"file:{location}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        raise DatabaseError(
            f"cannot open database read-only at {location}: {exc}"
        ) from exc
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        yield conn
    except sqlite3.Error as exc:
        raise DatabaseError(f"database operation failed at {location}: {exc}") from exc
    finally:
        conn.close()


def init_db(explicit: str | Path | None = None) -> Path:
    """Create and migrate the database; return its path (idempotent)."""
    path = resolve_db_path(explicit)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise DatabaseError(f"cannot create {path.parent}: {exc}") from exc
    try:
        with connect(path) as conn:
            version = schema_module.migrate(conn)
    except DatabaseError:
        raise
    except sqlite3.Error as exc:
        raise DatabaseError(f"cannot initialize database at {path}: {exc}") from exc
    if version != schema_module.MEMORY_SCHEMA_VERSION:
        raise DatabaseError(f"unexpected schema version {version} at {path}")
    return path
