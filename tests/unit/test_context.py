"""Phase 7, step 1 tests: context bounds and package assembly."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from repo_health.context import (
    CONTEXT_SCHEMA,
    ContextBounds,
    build_package,
    package_to_json,
)
from repo_health.context.bounds import truncate_text
from repo_health.core.exceptions import ValidationError
from repo_health.models import RunStatus, Severity
from repo_health.models.analyzer_result import AnalyzerResult, AnalyzerStatus
from repo_health.models.finding import Finding
from repo_health.models.repository import Repository
from repo_health.storage import (
    connect,
    create_run,
    init_db,
    record_analyzer_result,
    record_observation,
    upsert_repository,
)


def make_finding(
    severity: Severity = Severity.INFO,
    fingerprint: str = "k1",
    evidence: str = "some evidence",
) -> Finding:
    return Finding(
        analyzer="security",
        rule="security.secret-pattern",
        title="Possible secret",
        description="A potential secret pattern was detected.",
        severity=severity,
        path="src/a.py",
        locator="L1",
        fingerprint=fingerprint,
        evidence=evidence,
        recommendation="Rotate it.",
    )


def make_result(findings: tuple[Finding, ...] = ()) -> AnalyzerResult:
    return AnalyzerResult(
        analyzer="security",
        status=AnalyzerStatus.SUCCESS,
        findings=findings,
        checks=("secret-pattern-scan",),
    )


def seed_db(path: Path) -> tuple[str, int, int]:
    db_path = init_db(path / "memory.db")
    with connect(db_path) as conn:
        repo_id = upsert_repository(
            conn,
            Repository(root="/tmp/repo", remote="https://example.com/r.git"),
            now="2026-01-01T00:00:00+00:00",
        )
        run1 = create_run(conn, repo_id, RunStatus.COMPLETED, now="2026-01-02T00:00:00+00:00")
        run2 = create_run(conn, repo_id, RunStatus.COMPLETED, now="2026-01-03T00:00:00+00:00")
        for run_id, stamp in (
            (run1, "2026-01-02T00:00:00+00:00"),
            (run2, "2026-01-03T00:00:00+00:00"),
        ):
            result = make_result()
            record_analyzer_result(conn, run_id, result)
            for finding in result.findings:
                record_observation(conn, run_id, finding, now=stamp)
    return str(db_path), repo_id, run2


def build(
    tmp_path: Path, findings: tuple[Finding, ...] = (make_finding(),)
) -> tuple[dict[str, Any], str]:
    db_path, _, run_id = seed_db(tmp_path)
    with connect(db_path) as conn:
        result = make_result(findings=findings)
        record_analyzer_result(conn, run_id, result)
        for finding in findings:
            record_observation(conn, run_id, finding, now="2026-01-03T00:00:00+00:00")
        package = build_package(conn, "/tmp/repo", run_id, ContextBounds())
    return package, db_path


def test_exact_package_fields(tmp_path: Path) -> None:
    package, _ = build(tmp_path)
    assert package["schema"] == CONTEXT_SCHEMA == "repo-health-context/v1"
    assert package["repository"] == {
        "key": "/tmp/repo",
        "name": "repo",
        "remote": "https://example.com/r.git",
    }
    assert package["run"]["id"] == 2
    assert package["run"]["status"] == "completed"
    assert package["scope"] == {"analyzers": ["security"], "complete": True}
    assert package["baseline_run_id"] == 1
    assert len(package["findings"]) == 1
    finding = package["findings"][0]
    assert finding["severity"] == "info"
    assert finding["lifecycle"] == "new"
    assert finding["baseline_run_id"] == 1
    assert finding["evidence"] == "some evidence"
    assert package["truncated"] == {"findings_omitted": 0, "evidence_chars_omitted": 0}
    assert package["provenance"]["producer"] == "repo-health 0.1.0"
    assert package["provenance"]["source_db"] == "memory.db"
    json.dumps(package)


def test_ordering_by_severity_then_id(tmp_path: Path) -> None:
    findings = (
        make_finding(Severity.INFO, "k-info"),
        make_finding(Severity.CRITICAL, "k-crit"),
        make_finding(Severity.HIGH, "k-high"),
        make_finding(Severity.HIGH, "k-high-2"),
    )
    package, _ = build(tmp_path, findings)
    ordered = package["findings"]
    assert [f["severity"] for f in ordered] == ["critical", "high", "high", "info"]
    high_ids = [f["id"] for f in ordered[1:3]]
    assert high_ids == sorted(high_ids)


def test_truncation_counts_and_markers(tmp_path: Path) -> None:
    long_evidence = "word " * 100
    package, _ = build(tmp_path, (make_finding(evidence=long_evidence.strip()),))
    (finding,) = package["findings"]
    assert finding["evidence"].endswith("...[truncated]")
    assert package["truncated"]["evidence_chars_omitted"] > 0
    short, omitted = truncate_text("abc", 200)
    assert (short, omitted) == ("abc", 0)


def test_max_findings_cut_is_deterministic(tmp_path: Path) -> None:
    findings = tuple(make_finding(fingerprint=f"k{i}") for i in range(5))
    db_path, _, run_id = seed_db(tmp_path)
    with connect(db_path) as conn:
        result = make_result(findings=findings)
        record_analyzer_result(conn, run_id, result)
        for finding in findings:
            record_observation(conn, run_id, finding, now="2026-01-03T00:00:00+00:00")
        first = build_package(conn, "/tmp/repo", run_id, ContextBounds(max_findings=2))
        second = build_package(conn, "/tmp/repo", run_id, ContextBounds(max_findings=2))
    assert first == second
    assert len(first["findings"]) == 2
    assert first["truncated"] == {"findings_omitted": 3, "evidence_chars_omitted": 0}


def test_bounds_validation() -> None:
    with pytest.raises(ValidationError):
        ContextBounds(max_findings=0)
    with pytest.raises(ValidationError):
        ContextBounds(max_findings=-1)
    with pytest.raises(ValidationError):
        ContextBounds(max_evidence_chars=0)
    with pytest.raises(ValidationError):
        ContextBounds(max_evidence_chars=True)
    with pytest.raises(ValidationError):
        ContextBounds(max_findings="50")  # type: ignore[arg-type]


def test_lifecycle_uncertainty_on_first_run(tmp_path: Path) -> None:
    db_path = init_db(tmp_path / "memory.db")
    with connect(db_path) as conn:
        repo_id = upsert_repository(conn, Repository(root="/tmp/repo"))
        run_id = create_run(conn, repo_id, RunStatus.COMPLETED)
        result = make_result(findings=(make_finding(),))
        record_analyzer_result(conn, run_id, result)
        for finding in result.findings:
            record_observation(conn, run_id, finding)
        package = build_package(conn, "/tmp/repo", run_id, ContextBounds())
    (finding,) = package["findings"]
    assert finding["lifecycle"] == "indeterminate"
    assert package["baseline_run_id"] is None


def test_unknown_repository_and_run_rejected(tmp_path: Path) -> None:
    db_path = init_db(tmp_path / "memory.db")
    with connect(db_path) as conn:
        with pytest.raises(ValidationError):
            build_package(conn, "/tmp/nope", 1, ContextBounds())
        upsert_repository(conn, Repository(root="/tmp/repo"))
        with pytest.raises(ValidationError):
            build_package(conn, "/tmp/repo", 999, ContextBounds())
        with pytest.raises(ValidationError):
            build_package(conn, "/tmp/repo", 1, "bounds")  # type: ignore[arg-type]


def test_export_leaves_database_untouched(tmp_path: Path) -> None:
    package, db_path = build(tmp_path)
    before = (Path(db_path).stat().st_mtime_ns, Path(db_path).read_bytes())
    with connect(db_path) as conn:
        again = build_package(conn, "/tmp/repo", 2, ContextBounds())
        assert again == package
    assert (Path(db_path).stat().st_mtime_ns, Path(db_path).read_bytes()) == before


def test_package_json_is_deterministic(tmp_path: Path) -> None:
    package, _ = build(tmp_path)
    assert package_to_json(package) == package_to_json(package)
