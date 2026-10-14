"""Concise summary rendering (Phase 8, step 3).

Pure formatting over the shared report model: run identity, per-analyzer
statuses, finding totals with severity counts, and lifecycle counts.
Mirrors the `analyze` console shape so summaries stay consistent.
"""

from __future__ import annotations

from repo_health.core.exceptions import ValidationError
from repo_health.models import Severity
from repo_health.models.analyzer_result import AnalyzerStatus
from repo_health.models.lifecycle import Lifecycle
from repo_health.models.report import Report


def render_summary(report: Report) -> str:
    """Render a report as a deterministic plain-text summary."""
    if not isinstance(report, Report):
        raise ValidationError(f"report must be a Report, got {report!r}")
    run = report.run
    if run is None:  # pragma: no cover - Report validation forbids this
        raise ValidationError("report has no run")
    findings = [f for r in report.results for f in r.findings]
    severities = {severity: 0 for severity in Severity}
    for finding in findings:
        severities[finding.severity] += 1
    counts = {lifecycle: 0 for lifecycle in Lifecycle}
    for item in report.lifecycles:
        counts[item.lifecycle] += 1
    lines = [
        f"run {run.id} ({run.status.value}), "
        + (
            f"baseline run {report.baseline_run_id}"
            if report.baseline_run_id is not None
            else "no baseline"
        ),
    ]
    for result in report.results:
        word = "finding" if len(result.findings) == 1 else "findings"
        lines.append(f"{result.analyzer}: {result.status.value}, {len(result.findings)} {word}")
    lines.append(
        f"analyzers: {len(report.results)} "
        f"({sum(1 for r in report.results if r.status is AnalyzerStatus.SUCCESS)} success, "
        f"{sum(1 for r in report.results if r.status is AnalyzerStatus.PARTIAL)} partial, "
        f"{sum(1 for r in report.results if r.status is AnalyzerStatus.FAILED)} failed)"
    )
    lines.append(
        f"findings: {len(findings)} ("
        + ", ".join(f"{severity.value}: {severities[severity]}" for severity in Severity)
        + ")"
    )
    lines.append(
        f"lifecycle: {counts[Lifecycle.NEW]} new, "
        f"{counts[Lifecycle.RECURRING]} recurring, "
        f"{counts[Lifecycle.RESOLVED]} resolved, "
        f"{counts[Lifecycle.REAPPEARED]} reappeared, "
        f"{counts[Lifecycle.INDETERMINATE]} indeterminate"
    )
    return "\n".join(lines) + "\n"
