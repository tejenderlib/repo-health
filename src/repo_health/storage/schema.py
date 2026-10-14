"""Memory schema and migrations (Stage 2).

The memory schema stores repository metadata, analysis runs, analyzer
execution results (including unavailable-evidence records), canonical
findings scoped per repository, and per-run observations. It stores
finding descriptions and short evidence summaries only: never entire
source files, and never secret values (redaction is the analyzers'
responsibility; see docs/rules.md section 10).

Schema-v3 note: the previously established schema v3 definition is
unavailable, so this schema makes no schema-v3 compatibility claim.
It is versioned independently as "memory schema vN".

Migrations are forward-only ``(version, description, sql)`` entries applied
in order. Each migration runs inside its own transaction: either all of
its statements and its migration record are applied, or none are. A
failed migration rolls back fully and stops the sequence, so a retry
resumes at the same version. Re-running migration over an up-to-date
database is a no-op.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from repo_health.core.exceptions import DatabaseError

MEMORY_SCHEMA_VERSION = 3

_MIGRATION_1_SQL = """
CREATE TABLE IF NOT EXISTS migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS repositories (
    id INTEGER PRIMARY KEY,
    key TEXT NOT NULL UNIQUE,
    root TEXT NOT NULL,
    name TEXT NOT NULL,
    remote TEXT,
    revision TEXT,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS analysis_runs (
    id INTEGER PRIMARY KEY,
    repository_id INTEGER NOT NULL REFERENCES repositories(id),
    created_at TEXT NOT NULL,
    status TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS analyzer_results (
    id INTEGER PRIMARY KEY,
    run_id INTEGER NOT NULL REFERENCES analysis_runs(id),
    analyzer TEXT NOT NULL,
    status TEXT NOT NULL,
    checks_json TEXT NOT NULL DEFAULT '[]',
    uncovered_checks_json TEXT NOT NULL DEFAULT '[]',
    unavailable_evidence_json TEXT NOT NULL DEFAULT '[]',
    errors_json TEXT NOT NULL DEFAULT '[]',
    UNIQUE (run_id, analyzer)
);
CREATE TABLE IF NOT EXISTS findings (
    id TEXT PRIMARY KEY,
    analyzer TEXT NOT NULL,
    rule TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    severity TEXT NOT NULL,
    path TEXT NOT NULL DEFAULT '',
    locator TEXT NOT NULL DEFAULT '',
    fingerprint TEXT NOT NULL DEFAULT '',
    evidence TEXT NOT NULL,
    recommendation TEXT NOT NULL DEFAULT '',
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS observations (
    run_id INTEGER NOT NULL REFERENCES analysis_runs(id),
    finding_id TEXT NOT NULL REFERENCES findings(id),
    analyzer TEXT NOT NULL,
    evidence_state TEXT NOT NULL DEFAULT 'known',
    observed_at TEXT NOT NULL,
    PRIMARY KEY (run_id, finding_id)
);
CREATE INDEX IF NOT EXISTS idx_runs_repository ON analysis_runs(repository_id);
CREATE INDEX IF NOT EXISTS idx_results_run ON analyzer_results(run_id);
CREATE INDEX IF NOT EXISTS idx_observations_finding ON observations(finding_id);
"""

_MIGRATION_2_SQL = """
CREATE TABLE findings_new (
    repository_id INTEGER NOT NULL REFERENCES repositories(id),
    id TEXT NOT NULL,
    analyzer TEXT NOT NULL,
    rule TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    severity TEXT NOT NULL,
    path TEXT NOT NULL DEFAULT '',
    locator TEXT NOT NULL DEFAULT '',
    fingerprint TEXT NOT NULL DEFAULT '',
    evidence TEXT NOT NULL,
    recommendation TEXT NOT NULL DEFAULT '',
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    PRIMARY KEY (repository_id, id)
);
INSERT INTO findings_new (repository_id, id, analyzer, rule, title,
    description, severity, path, locator, fingerprint, evidence,
    recommendation, first_seen, last_seen)
SELECT analysis_runs.repository_id, findings.id, findings.analyzer,
    findings.rule, findings.title, findings.description, findings.severity,
    findings.path, findings.locator, findings.fingerprint, findings.evidence,
    findings.recommendation, MIN(observations.observed_at),
    MAX(observations.observed_at)
FROM findings
JOIN observations ON observations.finding_id = findings.id
JOIN analysis_runs ON analysis_runs.id = observations.run_id
GROUP BY analysis_runs.repository_id, findings.id, findings.analyzer,
    findings.rule, findings.title, findings.description, findings.severity,
    findings.path, findings.locator, findings.fingerprint, findings.evidence,
    findings.recommendation;
CREATE TABLE observations_backup AS
SELECT observations.*, analysis_runs.repository_id AS backup_repository_id
FROM observations
JOIN analysis_runs ON analysis_runs.id = observations.run_id;
DROP TABLE observations;
DROP TABLE findings;
ALTER TABLE findings_new RENAME TO findings;
CREATE TABLE observations (
    run_id INTEGER NOT NULL REFERENCES analysis_runs(id),
    repository_id INTEGER NOT NULL,
    finding_id TEXT NOT NULL,
    analyzer TEXT NOT NULL,
    evidence_state TEXT NOT NULL DEFAULT 'known',
    observed_at TEXT NOT NULL,
    PRIMARY KEY (run_id, finding_id),
    FOREIGN KEY (repository_id, finding_id)
        REFERENCES findings (repository_id, id)
);
INSERT INTO observations (run_id, repository_id, finding_id, analyzer,
    evidence_state, observed_at)
SELECT run_id, backup_repository_id, finding_id, analyzer, evidence_state,
    observed_at
FROM observations_backup;
DROP TABLE observations_backup;
CREATE INDEX idx_observations_finding ON observations(finding_id);
"""

_MIGRATION_3_SQL = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_runs_repository_row
    ON analysis_runs (repository_id, id);
CREATE TABLE observations_new (
    run_id INTEGER NOT NULL REFERENCES analysis_runs(id),
    repository_id INTEGER NOT NULL,
    finding_id TEXT NOT NULL,
    analyzer TEXT NOT NULL,
    evidence_state TEXT NOT NULL DEFAULT 'known',
    observed_at TEXT NOT NULL,
    PRIMARY KEY (run_id, finding_id),
    FOREIGN KEY (repository_id, finding_id)
        REFERENCES findings (repository_id, id),
    FOREIGN KEY (repository_id, run_id)
        REFERENCES analysis_runs (repository_id, id)
);
INSERT INTO observations_new (run_id, repository_id, finding_id, analyzer,
    evidence_state, observed_at)
SELECT run_id, repository_id, finding_id, analyzer, evidence_state,
    observed_at
FROM observations;
DROP TABLE observations;
ALTER TABLE observations_new RENAME TO observations;
CREATE INDEX idx_observations_finding ON observations(finding_id);
"""

MIGRATIONS: tuple[tuple[int, str, str], ...] = (
    (1, "initial memory schema", _MIGRATION_1_SQL),
    (2, "scope canonical findings by repository", _MIGRATION_2_SQL),
    (3, "enforce observation run/repository agreement", _MIGRATION_3_SQL),
)


def utc_now() -> str:
    """Current UTC time as an ISO-8601 string (metadata only)."""
    return datetime.now(UTC).isoformat()


def applied_versions(conn: sqlite3.Connection) -> tuple[int, ...]:
    """Return the sorted migration versions recorded in the database."""
    try:
        rows = conn.execute(
            "SELECT version FROM migrations ORDER BY version"
        ).fetchall()
    except sqlite3.Error as exc:
        raise DatabaseError(f"cannot read migration state: {exc}") from exc
    return tuple(int(row[0]) for row in rows)


def _split_statements(sql: str) -> list[str]:
    """Split migration SQL into individual statements.

    Migrations must keep statements simple: no semicolons inside string
    literals or trigger bodies.
    """
    return [part.strip() for part in sql.split(";") if part.strip()]


def migrate(conn: sqlite3.Connection) -> int:
    """Apply pending migrations idempotently; return the schema version.

    ``executescript`` is deliberately not used: it implicitly commits any
    pending transaction and applies statements one by one, so a mid-script
    failure would leave partial schema changes behind. Instead each
    migration executes statement by statement inside an explicit
    transaction that is rolled back on any error.

    The connection must have no open transaction; each applied migration
    is committed before the next begins.
    """
    if conn.in_transaction:
        raise DatabaseError("cannot migrate with an open transaction")
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS migrations ("
            "version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        conn.commit()
        applied = set(applied_versions(conn))
        for version, _description, sql in MIGRATIONS:
            if version in applied:
                continue
            conn.execute("BEGIN")
            try:
                for statement in _split_statements(sql):
                    conn.execute(statement)
                conn.execute(
                    "INSERT INTO migrations (version, applied_at) VALUES (?, ?)",
                    (version, utc_now()),
                )
            except Exception:
                conn.rollback()
                raise
            conn.commit()
        conn.execute(f"PRAGMA user_version = {MEMORY_SCHEMA_VERSION}")
    except DatabaseError:
        raise
    except sqlite3.Error as exc:
        raise DatabaseError(f"cannot migrate database: {exc}") from exc
    versions = applied_versions(conn)
    if not versions or versions[-1] != MEMORY_SCHEMA_VERSION:
        raise DatabaseError("migration left the database at an unexpected version")
    return versions[-1]
