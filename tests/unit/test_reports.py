"""Phase 8 tests: shared report model and JSON report generation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from repo_health.core.exceptions import ValidationError
from repo_health.models import RunStatus, Severity
from repo_health.models.analyzer_result import AnalyzerResult, AnalyzerStatus
from repo_health.models.finding import Finding
from repo_health.models.lifecycle import FindingLifecycle, Lifecycle
from repo_health.models.report import Report
from repo_health.models.repository import Repository
from repo_health.models.run import AnalysisRun
from repo_health.reports.json_report import (
    REPORT_SCHEMA,
    build_report,
    report_to_json,
)
from repo_health.reports.markdown import render_markdown
from repo_health.reports.summary import render_summary
from repo_health.storage import (
    connect,
    create_run,
    init_db,
    record_analyzer_result,
    record_observation,
    upsert_repository,
)

FINDING_A = "rh1-0000000000000000"
FINDING_B = "rh1-ffffffffffffffff"


def make_run(run_id: int = 2) -> AnalysisRun:
    return AnalysisRun(
        id=run_id,
        repository_key="/tmp/repo",
        created_at="2026-01-03T00:00:00+00:00",
        status=RunStatus.COMPLETED,
    )


def make_result(analyzer: str = "security") -> AnalyzerResult:
    return AnalyzerResult(
        analyzer=analyzer, status=AnalyzerStatus.SUCCESS, checks=(f"{analyzer}-check",)
    )


def make_lifecycle(
    finding_id: str = FINDING_A,
    lifecycle: Lifecycle = Lifecycle.NEW,
    current_run_id: int | None = 2,
    baseline_run_id: int | None = 1,
) -> FindingLifecycle:
    return FindingLifecycle(
        finding_id=finding_id,
        analyzer="security",
        lifecycle=lifecycle,
        reason="test reason",
        baseline_run_id=baseline_run_id,
        current_run_id=current_run_id,
    )


def make_report(**overrides: object) -> Report:
    fields: dict[str, object] = {
        "repository_key": "/tmp/repo",
        "repository_name": "repo",
        "run": make_run(),
        "baseline_run_id": 1,
        "results": (make_result("security"), make_result("git")),
        "lifecycles": (
            make_lifecycle(FINDING_B, Lifecycle.RECURRING),
            make_lifecycle(FINDING_A, Lifecycle.NEW),
        ),
    }
    fields.update(overrides)
    return Report(**fields)  # type: ignore[arg-type]


def test_valid_report_sorts_deterministically() -> None:
    report = make_report()
    assert [r.analyzer for r in report.results] == ["git", "security"]
    assert [item.sort_key() for item in report.lifecycles] == [
        (FINDING_A, "security"),
        (FINDING_B, "security"),
    ]
    assert report == make_report()


def test_required_fields_rejected() -> None:
    with pytest.raises(ValidationError):
        make_report(repository_key="   ")
    with pytest.raises(ValidationError):
        make_report(repository_name="")
    with pytest.raises(ValidationError):
        make_report(run=None)
    with pytest.raises(ValidationError):
        make_report(run="run")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        make_report(baseline_run_id=0)
    with pytest.raises(ValidationError):
        make_report(results=("x",))  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        make_report(lifecycles=("x",))  # type: ignore[arg-type]


def test_run_must_belong_to_repository() -> None:
    other = AnalysisRun(repository_key="/tmp/other", created_at="t")
    with pytest.raises(ValidationError):
        make_report(run=other)


def test_lifecycle_must_describe_this_run_and_baseline() -> None:
    with pytest.raises(ValidationError):
        make_report(lifecycles=(make_lifecycle(current_run_id=99),))
    with pytest.raises(ValidationError):
        make_report(lifecycles=(make_lifecycle(baseline_run_id=99),))
    report = make_report(lifecycles=(make_lifecycle(current_run_id=None, baseline_run_id=None),))
    assert len(report.lifecycles) == 1


def test_unset_ids_skip_relationship_checks() -> None:
    run = AnalysisRun(repository_key="/tmp/repo", created_at="t")
    report = make_report(run=run, baseline_run_id=None)
    assert report.run.id is None
    assert report.baseline_run_id is None


# Phase 8, step 2: JSON report builder and serializer


def seed_json_db(tmp_path: Path) -> tuple[str, int, int, Finding]:
    finding = Finding(
        analyzer="security",
        rule="security.secret-pattern",
        title="Possible secret",
        description="A potential secret pattern was detected.",
        severity=Severity.HIGH,
        path="src/a.py",
        locator="L1",
        fingerprint="k1",
        evidence="line 1 matches",
        recommendation="Rotate it.",
    )
    db_path = init_db(tmp_path / "memory.db")
    with connect(db_path) as conn:
        repo_id = upsert_repository(
            conn, Repository(root="/tmp/repo"), now="2026-01-01T00:00:00+00:00"
        )
        run1 = create_run(conn, repo_id, RunStatus.COMPLETED, now="2026-01-02T00:00:00+00:00")
        record_analyzer_result(
            conn,
            run1,
            AnalyzerResult(
                analyzer="security",
                status=AnalyzerStatus.SUCCESS,
                checks=("secret-pattern-scan",),
            ),
        )
        run2 = create_run(conn, repo_id, RunStatus.COMPLETED, now="2026-01-03T00:00:00+00:00")
        record_analyzer_result(
            conn,
            run2,
            AnalyzerResult(
                analyzer="security",
                status=AnalyzerStatus.SUCCESS,
                findings=(finding,),
                checks=("secret-pattern-scan",),
            ),
        )
        record_observation(conn, run2, finding, now="2026-01-03T00:00:00+00:00")
    return str(db_path), run1, run2, finding


def test_build_report_fields(tmp_path: Path) -> None:
    db_path, run1, run2, finding = seed_json_db(tmp_path)
    with connect(db_path) as conn:
        report = build_report(conn, "/tmp/repo", run2, run1)
    assert report.repository_key == "/tmp/repo"
    assert report.run.id == run2
    assert report.baseline_run_id == run1
    assert [r.analyzer for r in report.results] == ["security"]
    assert [(i.finding_id, i.lifecycle) for i in report.lifecycles] == [(finding.id, Lifecycle.NEW)]


def test_build_report_defaults_to_previous(tmp_path: Path) -> None:
    db_path, run1, run2, _ = seed_json_db(tmp_path)
    with connect(db_path) as conn:
        assert build_report(conn, "/tmp/repo", run2) == build_report(conn, "/tmp/repo", run2, run1)
        single = build_report(conn, "/tmp/repo", run1)
    assert single.baseline_run_id is None
    assert single.lifecycles == ()


def test_build_report_rejections(tmp_path: Path) -> None:
    db_path, run1, run2, _ = seed_json_db(tmp_path)
    with connect(db_path) as conn:
        with pytest.raises(ValidationError):
            build_report(conn, "/tmp/nope", run2)
        with pytest.raises(ValidationError):
            build_report(conn, "/tmp/repo", 999)
        with pytest.raises(ValidationError):
            build_report(conn, "/tmp/repo", run1, run2)
        with pytest.raises(ValidationError):
            build_report(conn, "/tmp/repo", run2, "1")  # type: ignore[arg-type]
        with pytest.raises(ValidationError):
            build_report("db", "/tmp/repo", run2)  # type: ignore[arg-type]


EXPECTED_JSON = """{
  "baseline_run_id": 1,
  "coverage": {
    "analyzers": [
      "security"
    ],
    "complete": true
  },
  "findings": [
    {
      "analyzer": "security",
      "baseline_run_id": 1,
      "description": "A potential secret pattern was detected.",
      "evidence": "line 1 matches",
      "id": "rh1-d94328be205da32e",
      "lifecycle": "new",
      "locator": "L1",
      "path": "src/a.py",
      "reason": "observed in run 2, absent from complete baseline run 1",
      "recommendation": "Rotate it.",
      "rule": "security.secret-pattern",
      "severity": "high",
      "title": "Possible secret"
    }
  ],
  "lifecycle_counts": {
    "indeterminate": 0,
    "new": 1,
    "reappeared": 0,
    "recurring": 0,
    "resolved": 0
  },
  "metadata": {
    "created_at": "2026-01-03T00:00:00+00:00"
  },
  "repository": {
    "key": "/tmp/repo",
    "name": "repo"
  },
  "run": {
    "id": 2,
    "status": "completed"
  },
  "schema": "repo-health-report/v1"
}"""


def test_report_to_json_golden(tmp_path: Path) -> None:
    db_path, _, run2, finding = seed_json_db(tmp_path)
    with connect(db_path) as conn:
        text = report_to_json(build_report(conn, "/tmp/repo", run2))
    assert text == EXPECTED_JSON
    parsed = json.loads(text)
    assert parsed["schema"] == REPORT_SCHEMA
    assert parsed["findings"][0]["evidence"] == "line 1 matches"


def test_report_json_deterministic_and_complete(tmp_path: Path) -> None:
    db_path, _, run2, finding = seed_json_db(tmp_path)
    with connect(db_path) as conn:
        first = report_to_json(build_report(conn, "/tmp/repo", run2))
        second = report_to_json(build_report(conn, "/tmp/repo", run2))
    assert first == second
    parsed = json.loads(first)
    assert parsed["lifecycle_counts"] == {
        "new": 1,
        "recurring": 0,
        "resolved": 0,
        "reappeared": 0,
        "indeterminate": 0,
    }
    assert parsed["coverage"] == {"analyzers": ["security"], "complete": True}
    assert parsed["metadata"] == {"created_at": "2026-01-03T00:00:00+00:00"}
    assert parsed["baseline_run_id"] == 1
    with pytest.raises(ValidationError):
        report_to_json("report")  # type: ignore[arg-type]


# Phase 8, step 3: Markdown and summary rendering


def make_finding_full(
    analyzer: str = "security",
    rule: str = "security.secret-pattern",
    severity: Severity = Severity.HIGH,
    fingerprint: str = "k1",
) -> Finding:
    return Finding(
        analyzer=analyzer,
        rule=rule,
        title="Possible secret",
        description="A potential secret pattern was detected.",
        severity=severity,
        path="src/a.py",
        locator="L1",
        fingerprint=fingerprint,
        evidence="line 1 matches",
        recommendation="Rotate it.",
    )


def make_render_report() -> Report:
    sec_finding = make_finding_full()
    git_finding = Finding(
        analyzer="git",
        rule="git.repository-present",
        title="Git repository detected",
        description="The target resides in a Git repository.",
        severity=Severity.INFO,
        evidence=".git directory present",
    )
    return Report(
        repository_key="/tmp/repo",
        repository_name="repo",
        run=make_run(),
        baseline_run_id=1,
        results=(
            AnalyzerResult(
                analyzer="security",
                status=AnalyzerStatus.SUCCESS,
                findings=(sec_finding,),
                checks=("secret-pattern-scan",),
            ),
            AnalyzerResult(
                analyzer="git",
                status=AnalyzerStatus.SUCCESS,
                findings=(git_finding,),
                checks=("git-presence",),
            ),
        ),
        lifecycles=(
            FindingLifecycle(
                finding_id=git_finding.id,
                analyzer="git",
                lifecycle=Lifecycle.RECURRING,
                reason="seen before",
                baseline_run_id=1,
                current_run_id=2,
            ),
            FindingLifecycle(
                finding_id=sec_finding.id,
                analyzer="security",
                lifecycle=Lifecycle.NEW,
                reason="first seen",
                baseline_run_id=1,
                current_run_id=2,
            ),
        ),
    )


MARKDOWN_GOLDEN = """# Repo Health Report

Repository: repo (`/tmp/repo`)
Run: 2 (completed) at 2026-01-03T00:00:00+00:00
Baseline: run 1

## Scope and coverage

Analyzers (2): git, security
Coverage: complete
- git: success
- security: success

## Findings (2)

### HIGH (1)

- `src/a.py:L1` Possible secret (security.secret-pattern, high, new)
  Evidence: line 1 matches
  Recommendation: Rotate it.

### INFO (1)

- no file Git repository detected (git.repository-present, info, recurring)
  Evidence: .git directory present

## Lifecycle

1 new, 1 recurring, 0 resolved, 0 reappeared, 0 indeterminate

- rh1-d94328be205da32e (security) - new: first seen

## Limitations

No findings does not prove the repository is free of issues. Results are \
limited to the checks performed, the available evidence, and the configured exclusions.
"""


SUMMARY_GOLDEN = (
    "run 2 (completed), baseline run 1\n"
    "git: success, 1 finding\n"
    "security: success, 1 finding\n"
    "analyzers: 2 (2 success, 0 partial, 0 failed)\n"
    "findings: 2 (critical: 0, high: 1, medium: 0, low: 0, info: 1)\n"
    "lifecycle: 1 new, 1 recurring, 0 resolved, 0 reappeared, 0 indeterminate\n"
)


def test_markdown_exact() -> None:
    assert render_markdown(make_render_report()) == MARKDOWN_GOLDEN


def test_markdown_empty_and_limitations() -> None:
    report = Report(
        repository_key="/tmp/repo",
        repository_name="repo",
        run=make_run(),
        results=(make_result("git"),),
        lifecycles=(),
    )
    text = render_markdown(report)
    assert "## Findings (0)" in text
    assert "No findings recorded." in text
    assert "Baseline: none" in text
    assert "No findings does not prove" in text


def test_markdown_severity_grouping_and_coverage() -> None:
    low = make_finding_full(severity=Severity.LOW, fingerprint="k-low")
    high2 = make_finding_full(fingerprint="k-high-2")
    report = Report(
        repository_key="/tmp/repo",
        repository_name="repo",
        run=make_run(),
        results=(
            AnalyzerResult(
                analyzer="security",
                status=AnalyzerStatus.PARTIAL,
                findings=(low, high2),
                checks=("secret-pattern-scan",),
                uncovered_checks=("secret-pattern-scan",),
                unavailable_evidence=("locked: unreadable",),
            ),
        ),
        lifecycles=(),
    )
    text = render_markdown(report)
    assert text.index("### HIGH (1)") < text.index("### LOW (1)")
    assert "### INFO" not in text
    assert "Coverage: incomplete" in text
    assert "locked: unreadable" in text
    assert "unknown" in text


def test_markdown_rejects_non_report() -> None:
    with pytest.raises(ValidationError):
        render_markdown("report")  # type: ignore[arg-type]


def test_markdown_deterministic() -> None:
    report = make_render_report()
    assert render_markdown(report) == render_markdown(report)


def test_markdown_evidence_verbatim() -> None:
    finding = make_finding_full()
    tricky = Finding(
        analyzer="security",
        rule="security.secret-pattern",
        title="T # title *with* `marks`",
        description="D",
        severity=Severity.INFO,
        path="a.py",
        locator="",
        fingerprint="k9",
        evidence="line 1 has # hash and * star",
        recommendation="",
    )
    report = Report(
        repository_key="/tmp/repo",
        repository_name="repo",
        run=make_run(),
        results=(
            AnalyzerResult(
                analyzer="security",
                status=AnalyzerStatus.SUCCESS,
                findings=(finding, tricky),
                checks=("c",),
            ),
        ),
        lifecycles=(),
    )
    text = render_markdown(report)
    assert "line 1 has # hash and * star" in text
    assert "T # title *with* `marks`" in text


def test_summary_exact() -> None:
    assert render_summary(make_render_report()) == SUMMARY_GOLDEN


def test_summary_empty() -> None:
    report = Report(
        repository_key="/tmp/repo",
        repository_name="repo",
        run=make_run(),
        results=(),
        lifecycles=(),
    )
    assert render_summary(report) == (
        "run 2 (completed), no baseline\n"
        "analyzers: 0 (0 success, 0 partial, 0 failed)\n"
        "findings: 0 (critical: 0, high: 0, medium: 0, low: 0, info: 0)\n"
        "lifecycle: 0 new, 0 recurring, 0 resolved, 0 reappeared, 0 indeterminate\n"
    )


def test_summary_rejects_non_report() -> None:
    with pytest.raises(ValidationError):
        render_summary("report")  # type: ignore[arg-type]


def test_json_missing_lifecycle_coverage_rejected() -> None:
    finding = make_finding_full()
    report = Report(
        repository_key="/tmp/repo",
        repository_name="repo",
        run=make_run(),
        baseline_run_id=1,
        results=(
            AnalyzerResult(
                analyzer="security",
                status=AnalyzerStatus.SUCCESS,
                findings=(finding,),
                checks=("secret-pattern-scan",),
            ),
        ),
        lifecycles=(),
    )
    with pytest.raises(ValidationError) as excinfo:
        report_to_json(report)
    assert finding.id in str(excinfo.value)
