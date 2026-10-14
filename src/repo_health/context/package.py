"""Context-package assembly (Phase 7, step 1).

Builds a bounded, evidence-backed package from persisted rows only: no
target access, no re-analysis, no synthesis. Lifecycle values are derived
at export time via the existing comparison API, never read from storage
(the schema stores no lifecycle table). Every finding traces to a stored
observation; selection and truncation are deterministic.
"""

from __future__ import annotations

import json
import os
import sqlite3
from typing import Any

from repo_health import __version__
from repo_health.context.bounds import ContextBounds, truncate_text
from repo_health.core.exceptions import DatabaseError, ValidationError
from repo_health.intelligence.regression import compare_to_previous
from repo_health.models.analyzer_result import AnalyzerResult, AnalyzerStatus
from repo_health.storage.records import (
    get_repository,
    get_repository_id,
    get_results_for_run,
    get_run,
)

CONTEXT_SCHEMA = "repo-health-context/v1"


def package_to_json(package: dict[str, Any]) -> str:
    """Serialize a package deterministically (JSON transport only)."""
    return json.dumps(package, sort_keys=True, indent=2)


def _complete(results: list[AnalyzerResult]) -> bool:
    """Per-analyzer completeness, same rule as regression comparison."""
    return all(
        result.status is AnalyzerStatus.SUCCESS
        and not result.unavailable_evidence
        and not result.uncovered_checks
        for result in results
    )


def _source_db_name(conn: sqlite3.Connection) -> str:
    try:
        rows = conn.execute("PRAGMA database_list").fetchall()
    except sqlite3.Error as exc:
        raise DatabaseError(f"cannot identify database: {exc}") from exc
    for row in rows:
        if row[1] == "main":
            return str(os.path.basename(row[2]))
    return ""


def build_package(
    conn: sqlite3.Connection,
    repository_key: str,
    run_id: int,
    bounds: ContextBounds,
) -> dict[str, Any]:
    """Assemble the context package for one stored run (read-only)."""
    if not isinstance(conn, sqlite3.Connection):
        raise ValidationError(f"conn must be a sqlite3.Connection, got {conn!r}")
    if not isinstance(bounds, ContextBounds):
        raise ValidationError(f"bounds must be ContextBounds, got {bounds!r}")
    if not isinstance(run_id, int) or isinstance(run_id, bool) or run_id < 1:
        raise ValidationError(f"run id must be a positive integer, got {run_id!r}")
    repo = get_repository(conn, repository_key)
    if repo is None:
        raise ValidationError(f"unknown repository {repository_key!r}")
    repo_id = get_repository_id(conn, repository_key)
    if repo_id is None:  # pragma: no cover - defensive; row was just read
        raise DatabaseError(f"repository {repository_key!r} vanished")
    run = get_run(conn, run_id)
    if run is None or run.repository_key != repository_key:
        raise ValidationError(f"unknown run {run_id} for repository {repository_key!r}")
    results = get_results_for_run(conn, run_id)
    lifecycles = {item.finding_id: item for item in compare_to_previous(conn, repo_id, run_id)}
    findings = [f for r in results for f in r.findings]
    ordered = sorted(findings, key=lambda f: (-f.severity.rank, f.id))
    kept, omitted = ordered[: bounds.max_findings], ordered[bounds.max_findings :]
    entries: list[dict[str, Any]] = []
    omitted_chars = 0
    for finding in kept:
        lifecycle = lifecycles[finding.id]
        description, description_omitted = truncate_text(
            finding.description, bounds.max_evidence_chars
        )
        evidence, evidence_omitted = truncate_text(finding.evidence, bounds.max_evidence_chars)
        omitted_chars += description_omitted + evidence_omitted
        entries.append(
            {
                "id": finding.id,
                "analyzer": finding.analyzer,
                "rule": finding.rule,
                "severity": finding.severity.value,
                "path": finding.path,
                "locator": finding.locator,
                "title": finding.title,
                "description": description,
                "evidence": evidence,
                "recommendation": finding.recommendation,
                "lifecycle": lifecycle.lifecycle.value,
                "baseline_run_id": lifecycle.baseline_run_id,
            }
        )
    first_lifecycle = next(iter(lifecycles.values()), None)
    return {
        "schema": CONTEXT_SCHEMA,
        "repository": {
            "key": repo.key(),
            "name": repo.name,
            "remote": repo.remote,
        },
        "run": {"id": run.id, "created_at": run.created_at, "status": run.status.value},
        "scope": {
            "analyzers": sorted({r.analyzer for r in results}),
            "complete": _complete(results),
        },
        "baseline_run_id": (
            first_lifecycle.baseline_run_id if first_lifecycle is not None else None
        ),
        "findings": entries,
        "truncated": {
            "findings_omitted": len(omitted),
            "evidence_chars_omitted": omitted_chars,
        },
        "provenance": {
            "producer": f"repo-health {__version__}",
            "source_db": _source_db_name(conn),
        },
    }
