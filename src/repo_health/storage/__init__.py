"""Persistent engineering memory over SQLite (Stage 2).

Only Repo Health's own database is ever modified. See
``storage.schema`` for the versioned memory schema, ``storage.paths``
for location resolution, ``storage.db`` for connections, and
``storage.records`` for the persistence operations.
"""

from __future__ import annotations

from repo_health.storage.db import (
    DatabaseStats,
    connect,
    connect_readonly,
    get_stats,
    init_db,
)
from repo_health.storage.paths import DEFAULT_DB_PATH, ENV_VAR, resolve_db_path
from repo_health.storage.records import (
    create_run,
    get_findings_for_run,
    get_observations_for_finding,
    get_repository,
    get_repository_id,
    get_results_for_run,
    get_run,
    list_runs,
    record_analyzer_result,
    record_observation,
    upsert_repository,
)
from repo_health.storage.schema import MEMORY_SCHEMA_VERSION, migrate

__all__ = [
    "DEFAULT_DB_PATH",
    "ENV_VAR",
    "MEMORY_SCHEMA_VERSION",
    "DatabaseStats",
    "connect",
    "connect_readonly",
    "create_run",
    "get_findings_for_run",
    "get_observations_for_finding",
    "get_repository",
    "get_repository_id",
    "get_results_for_run",
    "get_run",
    "get_stats",
    "init_db",
    "list_runs",
    "migrate",
    "record_analyzer_result",
    "record_observation",
    "resolve_db_path",
    "upsert_repository",
]
