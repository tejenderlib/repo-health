"""JSON report generation (Phase 8, step 2).

Builds the shared report model from stored runs and serializes it to
deterministic JSON under schema ``repo-health-report/v1``. All database
access is read-only; lifecycle comes from the existing Phase 6
comparison logic. Finding content passes through untouched, preserving
the analyzer-level redaction behavior without a second redaction system.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from repo_health.core.exceptions import DatabaseError, ValidationError
from repo_health.intelligence.regression import compare_runs, compare_to_previous
from repo_health.models.analyzer_result import AnalyzerResult, AnalyzerStatus
from repo_health.models.lifecycle import Lifecycle
from repo_health.models.report import Report
from repo_health.storage.records import (
    get_repository,
    get_repository_id,
    get_results_for_run,
    get_run,
    list_runs,
)

REPORT_SCHEMA = "repo-health-report/v1"


def _complete(results: list[AnalyzerResult]) -> bool:
    """Per-analyzer completeness, same rule as regression comparison."""
    return all(
        result.status is AnalyzerStatus.SUCCESS
        and not result.unavailable_evidence
        and not result.uncovered_checks
        for result in results
    )


def _resolve_baseline(
    conn: sqlite3.Connection,
    repository_id: int,
    run_id: int,
    baseline_run_id: int | None,
) -> int | None:
    if baseline_run_id is not None:
        if (
            not isinstance(baseline_run_id, int)
            or isinstance(baseline_run_id, bool)
            or baseline_run_id < 1
        ):
            raise ValidationError("baseline run id must be a positive integer or None")
        return baseline_run_id
    ids = sorted(run.id for run in list_runs(conn, repository_id) if run.id is not None)
    earlier = [i for i in ids if i < run_id]
    return earlier[-1] if earlier else None


def build_report(
    conn: sqlite3.Connection,
    repository_key: str,
    run_id: int,
    baseline_run_id: int | None = None,
) -> Report:
    """Assemble the shared report for one stored run (read-only)."""
    if not isinstance(conn, sqlite3.Connection):
        raise ValidationError(f"conn must be a sqlite3.Connection, got {conn!r}")
    if not isinstance(repository_key, str) or repository_key.strip() == "":
        raise ValidationError("repository_key must be a non-blank string")
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
    baseline = _resolve_baseline(conn, repo_id, run_id, baseline_run_id)
    results = get_results_for_run(conn, run_id)
    if baseline is None:
        lifecycles = compare_to_previous(conn, repo_id, run_id)
    else:
        lifecycles = compare_runs(conn, repo_id, run_id, baseline)
    return Report(
        repository_key=repository_key,
        repository_name=repo.name,
        run=run,
        baseline_run_id=baseline,
        results=tuple(results),
        lifecycles=lifecycles,
    )


def report_to_json(report: Report) -> str:
    """Serialize a report to deterministic JSON."""
    if not isinstance(report, Report):
        raise ValidationError(f"report must be a Report, got {report!r}")
    if report.run is None:  # pragma: no cover - Report validation forbids this
        raise ValidationError("report has no run")
    run = report.run
    counts = {lifecycle: 0 for lifecycle in Lifecycle}
    finding_entries: list[dict[str, Any]] = []
    lifecycles = {item.finding_id: item for item in report.lifecycles}
    ordered = sorted(
        {finding.id: finding for r in report.results for finding in r.findings}.values(),
        key=lambda f: (-f.severity.rank, f.id),
    )
    for finding in ordered:
        # Present for build_report output: comparison covers the union of
        # both runs. Anything else is a caller error, not silent data loss.
        try:
            lifecycle = lifecycles[finding.id]
        except KeyError:
            raise ValidationError(f"no lifecycle data for finding {finding.id!r}") from None
        counts[lifecycle.lifecycle] += 1
        finding_entries.append(
            {
                "id": finding.id,
                "analyzer": finding.analyzer,
                "rule": finding.rule,
                "severity": finding.severity.value,
                "path": finding.path,
                "locator": finding.locator,
                "title": finding.title,
                "description": finding.description,
                "evidence": finding.evidence,
                "recommendation": finding.recommendation,
                "lifecycle": lifecycle.lifecycle.value,
                "reason": lifecycle.reason,
                "baseline_run_id": lifecycle.baseline_run_id,
            }
        )
    data: dict[str, Any] = {
        "schema": REPORT_SCHEMA,
        "repository": {"key": report.repository_key, "name": report.repository_name},
        "run": {"id": run.id, "status": run.status.value},
        "baseline_run_id": report.baseline_run_id,
        "metadata": {"created_at": run.created_at},
        "coverage": {
            "analyzers": sorted({r.analyzer for r in report.results}),
            "complete": _complete(list(report.results)),
        },
        "findings": finding_entries,
        "lifecycle_counts": {lifecycle.value: counts[lifecycle] for lifecycle in Lifecycle},
    }
    return json.dumps(data, sort_keys=True, indent=2)
