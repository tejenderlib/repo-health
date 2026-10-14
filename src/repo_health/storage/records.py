"""Persistence of repositories, runs, results, findings, and observations.

All functions take an open connection owned by the caller (see
``storage.db.connect``) and never commit: the connection context controls
transactions. Every ``sqlite3.Error`` is wrapped in ``DatabaseError`` so
storage failures stay distinguishable from analysis results.
"""

from __future__ import annotations

import json
import sqlite3

from repo_health.core.exceptions import DatabaseError, ValidationError
from repo_health.models import (
    AnalysisRun,
    AnalyzerResult,
    AnalyzerStatus,
    EvidenceState,
    Finding,
    Observation,
    Repository,
    RunStatus,
    Severity,
)
from repo_health.storage.schema import utc_now


def _encode_str_list(values: tuple[str, ...]) -> str:
    return json.dumps(sorted(values))


def _decode_str_list(text: str, context: str) -> tuple[str, ...]:
    try:
        decoded = json.loads(text)
    except ValueError as exc:
        raise DatabaseError(f"stored {context} is not valid JSON: {exc}") from exc
    if not isinstance(decoded, list) or not all(
        isinstance(item, str) for item in decoded
    ):
        raise DatabaseError(f"stored {context} is not a list of strings")
    return tuple(decoded)


def upsert_repository(
    conn: sqlite3.Connection, repo: Repository, now: str | None = None
) -> int:
    """Insert or refresh a repository row; return its row id (stable per key)."""
    seen = now if now is not None else utc_now()
    try:
        row = conn.execute(
            "INSERT INTO repositories (key, root, name, remote, revision,"
            " first_seen, last_seen) VALUES (?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT (key) DO UPDATE SET root = excluded.root,"
            " name = excluded.name, remote = excluded.remote,"
            " revision = excluded.revision, last_seen = excluded.last_seen"
            " RETURNING id",
            (
                repo.key(),
                repo.root,
                repo.name,
                repo.remote,
                repo.revision,
                seen,
                seen,
            ),
        ).fetchone()
    except sqlite3.Error as exc:
        raise DatabaseError(f"cannot store repository {repo.key()}: {exc}") from exc
    if row is None:  # pragma: no cover - defensive; RETURNING always yields a row
        raise DatabaseError(f"cannot store repository {repo.key()}: no row returned")
    return int(row[0])


def get_repository(conn: sqlite3.Connection, key: str) -> Repository | None:
    """Return the repository stored under ``key``, or None if absent."""
    try:
        row = conn.execute(
            "SELECT root, name, remote, revision FROM repositories WHERE key = ?",
            (key,),
        ).fetchone()
    except sqlite3.Error as exc:
        raise DatabaseError(f"cannot read repository {key}: {exc}") from exc
    if row is None:
        return None
    try:
        return Repository(
            root=str(row["root"]),
            name=str(row["name"]),
            remote=None if row["remote"] is None else str(row["remote"]),
            revision=None if row["revision"] is None else str(row["revision"]),
        )
    except ValidationError as exc:
        raise DatabaseError(f"stored repository {key} is invalid: {exc}") from exc


def create_run(
    conn: sqlite3.Connection,
    repository_id: int,
    status: RunStatus,
    notes: str = "",
    now: str | None = None,
) -> int:
    """Insert an analysis run; return its row id."""
    if not isinstance(status, RunStatus):
        raise ValidationError(f"status must be a RunStatus member, got {status!r}")
    try:
        cursor = conn.execute(
            "INSERT INTO analysis_runs (repository_id, created_at, status, notes)"
            " VALUES (?, ?, ?, ?)",
            (
                repository_id,
                now if now is not None else utc_now(),
                status.value,
                notes.strip(),
            ),
        )
    except sqlite3.Error as exc:
        raise DatabaseError(f"cannot store analysis run: {exc}") from exc
    row_id = cursor.lastrowid
    if row_id is None:  # pragma: no cover - defensive
        raise DatabaseError("cannot store analysis run: no row id returned")
    return int(row_id)


def get_run(conn: sqlite3.Connection, run_id: int) -> AnalysisRun | None:
    """Return the run stored under ``run_id``, or None if absent."""
    try:
        row = conn.execute(
            "SELECT analysis_runs.id AS id, repositories.key AS rkey,"
            " analysis_runs.created_at AS created_at,"
            " analysis_runs.status AS status, analysis_runs.notes AS notes"
            " FROM analysis_runs JOIN repositories"
            " ON repositories.id = analysis_runs.repository_id"
            " WHERE analysis_runs.id = ?",
            (run_id,),
        ).fetchone()
    except sqlite3.Error as exc:
        raise DatabaseError(f"cannot read analysis run {run_id}: {exc}") from exc
    if row is None:
        return None
    try:
        return AnalysisRun(
            id=int(row["id"]),
            repository_key=str(row["rkey"]),
            created_at=str(row["created_at"]),
            status=RunStatus(str(row["status"])),
            notes=str(row["notes"]),
        )
    except (ValidationError, ValueError) as exc:
        raise DatabaseError(f"stored analysis run {run_id} is invalid: {exc}") from exc


def list_runs(conn: sqlite3.Connection, repository_id: int) -> list[AnalysisRun]:
    """Return a repository's runs in insertion order (deterministic)."""
    try:
        rows = conn.execute(
            "SELECT id FROM analysis_runs WHERE repository_id = ? ORDER BY id",
            (repository_id,),
        ).fetchall()
    except sqlite3.Error as exc:
        raise DatabaseError(f"cannot list analysis runs: {exc}") from exc
    runs: list[AnalysisRun] = []
    for row in rows:
        run = get_run(conn, int(row["id"]))
        if run is None:  # pragma: no cover - defensive; row was just selected
            raise DatabaseError("analysis run vanished during listing")
        runs.append(run)
    return runs


def _repository_id_for_run(conn: sqlite3.Connection, run_id: int) -> int:
    """Return the repository owning ``run_id``; fail on unknown runs."""
    try:
        row = conn.execute(
            "SELECT repository_id FROM analysis_runs WHERE id = ?", (run_id,)
        ).fetchone()
    except sqlite3.Error as exc:
        raise DatabaseError(
            f"cannot resolve repository for run {run_id}: {exc}"
        ) from exc
    if row is None:
        raise DatabaseError(f"unknown analysis run {run_id}")
    return int(row[0])


def _upsert_finding(
    conn: sqlite3.Connection,
    finding: Finding,
    repository_id: int,
    now: str | None,
) -> None:
    seen = now if now is not None else utc_now()
    data = finding.to_dict()
    try:
        conn.execute(
            "INSERT INTO findings (repository_id, id, analyzer, rule, title,"
            " description, severity, path, locator, fingerprint, evidence,"
            " recommendation, first_seen, last_seen)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT (repository_id, id) DO UPDATE SET"
            " analyzer = excluded.analyzer, rule = excluded.rule,"
            " title = excluded.title, description = excluded.description,"
            " severity = excluded.severity, path = excluded.path,"
            " locator = excluded.locator, fingerprint = excluded.fingerprint,"
            " evidence = excluded.evidence,"
            " recommendation = excluded.recommendation,"
            " last_seen = excluded.last_seen",
            (
                repository_id,
                data["id"],
                data["analyzer"],
                data["rule"],
                data["title"],
                data["description"],
                data["severity"],
                data["path"],
                data["locator"],
                data["fingerprint"],
                data["evidence"],
                data["recommendation"],
                seen,
                seen,
            ),
        )
    except sqlite3.Error as exc:
        raise DatabaseError(f"cannot store finding {finding.id}: {exc}") from exc


def record_observation(
    conn: sqlite3.Connection,
    run_id: int,
    finding: Finding,
    evidence_state: EvidenceState = EvidenceState.KNOWN,
    now: str | None = None,
) -> Observation:
    """Store a finding and its observation in a run (both idempotent)."""
    if not isinstance(evidence_state, EvidenceState):
        raise ValidationError(
            f"evidence_state must be an EvidenceState member, got {evidence_state!r}"
        )
    repository_id = _repository_id_for_run(conn, run_id)
    _upsert_finding(conn, finding, repository_id, now)
    seen = now if now is not None else utc_now()
    try:
        conn.execute(
            "INSERT INTO observations (run_id, repository_id, finding_id, analyzer,"
            " evidence_state, observed_at) VALUES (?, ?, ?, ?, ?, ?)"
            " ON CONFLICT (run_id, finding_id) DO NOTHING",
            (
                run_id,
                repository_id,
                finding.id,
                finding.analyzer,
                evidence_state.value,
                seen,
            ),
        )
    except sqlite3.Error as exc:
        raise DatabaseError(
            f"cannot store observation of {finding.id} in run {run_id}: {exc}"
        ) from exc
    return Observation(
        run_id=run_id,
        finding_id=finding.id,
        analyzer=finding.analyzer,
        repository_id=repository_id,
        evidence_state=evidence_state,
        observed_at=seen,
    )


def record_analyzer_result(
    conn: sqlite3.Connection, run_id: int, result: AnalyzerResult
) -> int:
    """Store an analyzer execution result; return its row id (stable per run)."""
    try:
        row = conn.execute(
            "INSERT INTO analyzer_results (run_id, analyzer, status, checks_json,"
            " uncovered_checks_json, unavailable_evidence_json, errors_json)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT (run_id, analyzer) DO UPDATE SET status = excluded.status,"
            " checks_json = excluded.checks_json,"
            " uncovered_checks_json = excluded.uncovered_checks_json,"
            " unavailable_evidence_json = excluded.unavailable_evidence_json,"
            " errors_json = excluded.errors_json RETURNING id",
            (
                run_id,
                result.analyzer,
                result.status.value,
                _encode_str_list(result.checks),
                _encode_str_list(result.uncovered_checks),
                _encode_str_list(result.unavailable_evidence),
                _encode_str_list(result.errors),
            ),
        ).fetchone()
    except sqlite3.Error as exc:
        raise DatabaseError(
            f"cannot store result of {result.analyzer} in run {run_id}: {exc}"
        ) from exc
    if row is None:  # pragma: no cover - defensive; RETURNING always yields a row
        raise DatabaseError(
            f"cannot store result of {result.analyzer}: no row returned"
        )
    return int(row[0])


def _row_to_finding(row: sqlite3.Row, context: str) -> Finding:
    try:
        return Finding(
            id=str(row["id"]),
            analyzer=str(row["analyzer"]),
            rule=str(row["rule"]),
            title=str(row["title"]),
            description=str(row["description"]),
            severity=Severity(str(row["severity"])),
            path=str(row["path"]),
            locator=str(row["locator"]),
            fingerprint=str(row["fingerprint"]),
            evidence=str(row["evidence"]),
            recommendation=str(row["recommendation"]),
        )
    except (ValidationError, ValueError) as exc:
        raise DatabaseError(f"stored finding {context} is invalid: {exc}") from exc


def get_findings_for_run(conn: sqlite3.Connection, run_id: int) -> list[Finding]:
    """Return a run's observed findings ordered by finding id.

    The join is scoped to the run's repository, so identical finding ids in
    other repositories never leak into the result.
    """
    try:
        rows = conn.execute(
            "SELECT findings.* FROM findings JOIN observations"
            " ON observations.finding_id = findings.id"
            " AND observations.repository_id = findings.repository_id"
            " WHERE observations.run_id = ? ORDER BY findings.id",
            (run_id,),
        ).fetchall()
    except sqlite3.Error as exc:
        raise DatabaseError(f"cannot read findings for run {run_id}: {exc}") from exc
    return [_row_to_finding(row, str(row["id"])) for row in rows]


def get_observations_for_finding(
    conn: sqlite3.Connection, finding_id: str
) -> list[Observation]:
    """Return a finding's observations ordered by run id (history order).

    History spans repositories: use each observation's ``repository_id``
    (or its run) to attribute entries per repository.
    """
    try:
        rows = conn.execute(
            "SELECT run_id, repository_id, finding_id, analyzer,"
            " evidence_state, observed_at"
            " FROM observations WHERE finding_id = ? ORDER BY run_id",
            (finding_id,),
        ).fetchall()
    except sqlite3.Error as exc:
        raise DatabaseError(
            f"cannot read observations for {finding_id}: {exc}"
        ) from exc
    observations: list[Observation] = []
    for row in rows:
        try:
            observations.append(
                Observation(
                    run_id=int(row["run_id"]),
                    finding_id=str(row["finding_id"]),
                    analyzer=str(row["analyzer"]),
                    repository_id=int(row["repository_id"]),
                    evidence_state=EvidenceState(str(row["evidence_state"])),
                    observed_at=str(row["observed_at"]),
                )
            )
        except (ValidationError, ValueError) as exc:
            raise DatabaseError(
                f"stored observation for {finding_id} is invalid: {exc}"
            ) from exc
    return observations


def get_results_for_run(conn: sqlite3.Connection, run_id: int) -> list[AnalyzerResult]:
    """Return a run's analyzer results ordered by analyzer name.

    Each result's findings are reattached from the run's observations, so a
    stored SUCCESS result round-trips to the value originally recorded.
    """
    try:
        rows = conn.execute(
            "SELECT analyzer, status, checks_json, uncovered_checks_json,"
            " unavailable_evidence_json, errors_json FROM analyzer_results"
            " WHERE run_id = ? ORDER BY analyzer",
            (run_id,),
        ).fetchall()
    except sqlite3.Error as exc:
        raise DatabaseError(
            f"cannot read analyzer results for run {run_id}: {exc}"
        ) from exc
    findings_by_analyzer: dict[str, list[Finding]] = {}
    for finding in get_findings_for_run(conn, run_id):
        findings_by_analyzer.setdefault(finding.analyzer, []).append(finding)
    results: list[AnalyzerResult] = []
    for row in rows:
        analyzer = str(row["analyzer"])
        try:
            results.append(
                AnalyzerResult(
                    analyzer=analyzer,
                    status=AnalyzerStatus(str(row["status"])),
                    findings=tuple(findings_by_analyzer.get(analyzer, ())),
                    checks=_decode_str_list(str(row["checks_json"]), "checks"),
                    uncovered_checks=_decode_str_list(
                        str(row["uncovered_checks_json"]), "uncovered checks"
                    ),
                    unavailable_evidence=_decode_str_list(
                        str(row["unavailable_evidence_json"]), "unavailable evidence"
                    ),
                    errors=_decode_str_list(str(row["errors_json"]), "errors"),
                )
            )
        except (ValidationError, ValueError) as exc:
            raise DatabaseError(
                f"stored result of {analyzer} in run {run_id} is invalid: {exc}"
            ) from exc
    return results
