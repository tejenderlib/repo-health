"""Phase 6, step 2 tests: historical comparison over stored runs."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from repo_health.core.exceptions import ValidationError
from repo_health.intelligence.regression import compare_runs, compare_to_previous
from repo_health.models import RunStatus, Severity
from repo_health.models.analyzer_result import AnalyzerResult, AnalyzerStatus
from repo_health.models.finding import Finding
from repo_health.models.lifecycle import Lifecycle
from repo_health.models.repository import Repository
from repo_health.storage import (
    connect,
    create_run,
    init_db,
    record_analyzer_result,
    record_observation,
    upsert_repository,
)


def make_finding(fingerprint: str = "k1") -> Finding:
    return Finding(
        analyzer="security",
        rule="security.secret-pattern",
        title="Possible secret",
        description="A secret-like pattern was detected.",
        severity=Severity.HIGH,
        path="src/a.py",
        locator="L1",
        fingerprint=fingerprint,
        evidence="line 1 matches a known secret pattern",
        recommendation="Rotate the credential.",
    )


def make_result(
    analyzer: str = "security",
    status: AnalyzerStatus = AnalyzerStatus.SUCCESS,
    findings: tuple[Finding, ...] = (),
    unavailable: tuple[str, ...] = (),
    uncovered: tuple[str, ...] = (),
    errors: tuple[str, ...] = (),
) -> AnalyzerResult:
    return AnalyzerResult(
        analyzer=analyzer,
        status=status,
        findings=findings,
        checks=(f"{analyzer}-check",),
        uncovered_checks=uncovered,
        unavailable_evidence=unavailable,
        errors=errors,
    )


def seed_run(
    conn: sqlite3.Connection,
    repo_id: int,
    status: RunStatus,
    results: list[AnalyzerResult],
    stamp: str,
) -> int:
    run_id = create_run(conn, repo_id, status, notes="", now=stamp)
    for result in results:
        record_analyzer_result(conn, run_id, result)
        for finding in result.findings:
            record_observation(conn, run_id, finding, now=stamp)
    return run_id


def seed_repo(conn: sqlite3.Connection, root: str) -> int:
    return upsert_repository(conn, Repository(root=root), now="2026-01-01T00:00:00+00:00")


def lifecycles(
    conn: sqlite3.Connection, repo_id: int, current: int, baseline: int
) -> dict[str, Lifecycle]:
    return {
        item.finding_id: item.lifecycle
        for item in compare_runs(conn, repo_id, current, baseline)
    }


def test_new_recurring_resolved_sequence(tmp_path: Path) -> None:
    path = init_db(tmp_path / "memory.db")
    with connect(path) as conn:
        repo = seed_repo(conn, "/tmp/repo")
        finding = make_finding()
        run1 = seed_run(
            conn, repo, RunStatus.COMPLETED,
            [make_result(findings=(finding,))], "2026-01-02T00:00:00+00:00",
        )
        run2 = seed_run(
            conn, repo, RunStatus.COMPLETED,
            [make_result(findings=(finding,))], "2026-01-03T00:00:00+00:00",
        )
        run3 = seed_run(
            conn, repo, RunStatus.COMPLETED,
            [make_result()], "2026-01-04T00:00:00+00:00",
        )
        assert lifecycles(conn, repo, run2, run1) == {finding.id: Lifecycle.RECURRING}
        assert lifecycles(conn, repo, run3, run2) == {finding.id: Lifecycle.RESOLVED}


def test_reappeared(tmp_path: Path) -> None:
    path = init_db(tmp_path / "memory.db")
    with connect(path) as conn:
        repo = seed_repo(conn, "/tmp/repo")
        finding = make_finding()
        seed_run(
            conn, repo, RunStatus.COMPLETED,
            [make_result(findings=(finding,))], "2026-01-02T00:00:00+00:00",
        )
        run2 = seed_run(
            conn, repo, RunStatus.COMPLETED,
            [make_result()], "2026-01-03T00:00:00+00:00",
        )
        run3 = seed_run(
            conn, repo, RunStatus.COMPLETED,
            [make_result(findings=(finding,))], "2026-01-04T00:00:00+00:00",
        )
        assert lifecycles(conn, repo, run3, run2) == {finding.id: Lifecycle.REAPPEARED}


def test_no_baseline_is_indeterminate(tmp_path: Path) -> None:
    path = init_db(tmp_path / "memory.db")
    with connect(path) as conn:
        repo = seed_repo(conn, "/tmp/repo")
        finding = make_finding()
        run1 = seed_run(
            conn, repo, RunStatus.COMPLETED,
            [make_result(findings=(finding,))], "2026-01-02T00:00:00+00:00",
        )
        (item,) = compare_to_previous(conn, repo, run1)
        assert item.finding_id == finding.id
        assert item.lifecycle is Lifecycle.INDETERMINATE


def test_partial_baseline_is_not_new(tmp_path: Path) -> None:
    path = init_db(tmp_path / "memory.db")
    with connect(path) as conn:
        repo = seed_repo(conn, "/tmp/repo")
        finding = make_finding()
        run1 = seed_run(
            conn, repo, RunStatus.PARTIAL,
            [make_result(status=AnalyzerStatus.PARTIAL, unavailable=("scan cut",))],
            "2026-01-02T00:00:00+00:00",
        )
        run2 = seed_run(
            conn, repo, RunStatus.COMPLETED,
            [make_result(findings=(finding,))], "2026-01-03T00:00:00+00:00",
        )
        assert lifecycles(conn, repo, run2, run1) == {finding.id: Lifecycle.INDETERMINATE}


def test_failed_current_is_not_resolved(tmp_path: Path) -> None:
    path = init_db(tmp_path / "memory.db")
    with connect(path) as conn:
        repo = seed_repo(conn, "/tmp/repo")
        finding = make_finding()
        run1 = seed_run(
            conn, repo, RunStatus.COMPLETED,
            [make_result(findings=(finding,))], "2026-01-02T00:00:00+00:00",
        )
        run2 = seed_run(
            conn, repo, RunStatus.FAILED,
            [make_result(status=AnalyzerStatus.FAILED, errors=("boom",))],
            "2026-01-03T00:00:00+00:00",
        )
        assert lifecycles(conn, repo, run2, run1) == {finding.id: Lifecycle.INDETERMINATE}


def test_missing_analyzer_in_baseline_is_indeterminate(tmp_path: Path) -> None:
    path = init_db(tmp_path / "memory.db")
    with connect(path) as conn:
        repo = seed_repo(conn, "/tmp/repo")
        finding = make_finding()
        run1 = seed_run(
            conn, repo, RunStatus.COMPLETED,
            [make_result(analyzer="git")], "2026-01-02T00:00:00+00:00",
        )
        run2 = seed_run(
            conn, repo, RunStatus.COMPLETED,
            [make_result(findings=(finding,))], "2026-01-03T00:00:00+00:00",
        )
        assert lifecycles(conn, repo, run2, run1) == {finding.id: Lifecycle.INDETERMINATE}


def test_success_with_uncovered_checks_counts_as_incomplete(tmp_path: Path) -> None:
    path = init_db(tmp_path / "memory.db")
    with connect(path) as conn:
        repo = seed_repo(conn, "/tmp/repo")
        finding = make_finding()
        run1 = seed_run(
            conn, repo, RunStatus.COMPLETED,
            [make_result(uncovered=("manifest-presence",))],
            "2026-01-02T00:00:00+00:00",
        )
        run2 = seed_run(
            conn, repo, RunStatus.COMPLETED,
            [make_result(findings=(finding,))], "2026-01-03T00:00:00+00:00",
        )
        assert lifecycles(conn, repo, run2, run1) == {finding.id: Lifecycle.INDETERMINATE}


def test_cross_repo_history_does_not_leak(tmp_path: Path) -> None:
    path = init_db(tmp_path / "memory.db")
    with connect(path) as conn:
        repo_a = seed_repo(conn, "/tmp/a")
        repo_b = seed_repo(conn, "/tmp/b")
        finding = make_finding()
        seed_run(
            conn, repo_a, RunStatus.COMPLETED,
            [make_result(findings=(finding,))], "2026-01-02T00:00:00+00:00",
        )
        run_b1 = seed_run(
            conn, repo_b, RunStatus.COMPLETED,
            [make_result()], "2026-01-03T00:00:00+00:00",
        )
        run_b2 = seed_run(
            conn, repo_b, RunStatus.COMPLETED,
            [make_result(findings=(finding,))], "2026-01-04T00:00:00+00:00",
        )
        assert lifecycles(conn, repo_b, run_b2, run_b1) == {finding.id: Lifecycle.NEW}


def test_compare_to_previous_picks_latest_run(tmp_path: Path) -> None:
    path = init_db(tmp_path / "memory.db")
    with connect(path) as conn:
        repo = seed_repo(conn, "/tmp/repo")
        finding = make_finding()
        seed_run(conn, repo, RunStatus.COMPLETED, [make_result()],
                 "2026-01-02T00:00:00+00:00")
        seed_run(conn, repo, RunStatus.COMPLETED,
                 [make_result(findings=(finding,))], "2026-01-03T00:00:00+00:00")
        run3 = seed_run(conn, repo, RunStatus.COMPLETED,
                        [make_result(findings=(finding,))], "2026-01-04T00:00:00+00:00")
        (item,) = compare_to_previous(conn, repo, run3)
        assert item.lifecycle is Lifecycle.RECURRING


def test_empty_union_compares_to_nothing(tmp_path: Path) -> None:
    path = init_db(tmp_path / "memory.db")
    with connect(path) as conn:
        repo = seed_repo(conn, "/tmp/repo")
        run1 = seed_run(conn, repo, RunStatus.COMPLETED, [make_result()],
                        "2026-01-02T00:00:00+00:00")
        run2 = seed_run(conn, repo, RunStatus.COMPLETED, [make_result()],
                        "2026-01-03T00:00:00+00:00")
        assert compare_runs(conn, repo, run2, run1) == ()


def test_invalid_run_selection_rejected(tmp_path: Path) -> None:
    path = init_db(tmp_path / "memory.db")
    with connect(path) as conn:
        repo = seed_repo(conn, "/tmp/repo")
        other = seed_repo(conn, "/tmp/other")
        run1 = seed_run(conn, repo, RunStatus.COMPLETED, [make_result()],
                        "2026-01-02T00:00:00+00:00")
        foreign = seed_run(conn, other, RunStatus.COMPLETED, [make_result()],
                           "2026-01-03T00:00:00+00:00")
        with pytest.raises(ValidationError):
            compare_runs(conn, repo, 999, run1)
        with pytest.raises(ValidationError):
            compare_runs(conn, repo, run1, foreign)
        with pytest.raises(ValidationError):
            compare_runs(conn, repo, run1, run1)
        with pytest.raises(ValidationError):
            compare_to_previous(conn, repo, 999)
        with pytest.raises(ValidationError):
            compare_runs(conn, repo, run1, 0)
        with pytest.raises(ValidationError):
            compare_runs("db", repo, run1, run1)  # type: ignore[arg-type]


def test_inverted_run_order_rejected(tmp_path: Path) -> None:
    path = init_db(tmp_path / "memory.db")
    with connect(path) as conn:
        repo = seed_repo(conn, "/tmp/repo")
        run1 = seed_run(conn, repo, RunStatus.COMPLETED, [make_result()],
                        "2026-01-02T00:00:00+00:00")
        run2 = seed_run(conn, repo, RunStatus.COMPLETED, [make_result()],
                        "2026-01-03T00:00:00+00:00")
        with pytest.raises(ValidationError):
            compare_runs(conn, repo, run1, run2)
        assert compare_runs(conn, repo, run2, run1) == ()
