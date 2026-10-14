"""Markdown report rendering (Phase 8, step 3).

Pure formatting over the shared report model: title and run metadata,
scope and analyzer coverage, findings grouped by severity, a lifecycle
section, and a limitations footer. No database access, no analysis, no
invented content — every line derives from the report.
"""

from __future__ import annotations

from repo_health.core.exceptions import ValidationError
from repo_health.models import Severity
from repo_health.models.finding import Finding
from repo_health.models.lifecycle import Lifecycle
from repo_health.models.report import Report

_SEVERITIES = (
    Severity.CRITICAL,
    Severity.HIGH,
    Severity.MEDIUM,
    Severity.LOW,
    Severity.INFO,
)


def _location(finding: Finding) -> str:
    if finding.path == "":
        return "no file"
    if finding.locator == "":
        return f"`{finding.path}`"
    return f"`{finding.path}:{finding.locator}`"


def _finding_block(finding: Finding, lifecycle: str) -> list[str]:
    lines = [
        f"- {_location(finding)} {finding.title} "
        f"({finding.rule}, {finding.severity.value}, {lifecycle})",
        f"  Evidence: {finding.evidence}",
    ]
    if finding.recommendation.strip() != "":
        lines.append(f"  Recommendation: {finding.recommendation}")
    return lines


def render_markdown(report: Report) -> str:
    """Render a report as deterministic Markdown."""
    if not isinstance(report, Report):
        raise ValidationError(f"report must be a Report, got {report!r}")
    run = report.run
    if run is None:  # pragma: no cover - Report validation forbids this
        raise ValidationError("report has no run")
    lifecycles = {item.finding_id: item for item in report.lifecycles}
    findings = [f for r in report.results for f in r.findings]
    lines = [
        "# Repo Health Report",
        "",
        f"Repository: {report.repository_name} (`{report.repository_key}`)",
        f"Run: {run.id} ({run.status.value}) at {run.created_at}",
        (
            f"Baseline: run {report.baseline_run_id}"
            if report.baseline_run_id is not None
            else "Baseline: none"
        ),
        "",
        "## Scope and coverage",
        "",
        f"Analyzers ({len(report.results)}): " + ", ".join(r.analyzer for r in report.results),
        "Coverage: "
        + (
            "complete"
            if all(not r.unavailable_evidence and not r.uncovered_checks for r in report.results)
            else "incomplete"
        ),
    ]
    for result in report.results:
        lines.append(f"- {result.analyzer}: {result.status.value}")
        for note in sorted(result.unavailable_evidence):
            lines.append(f"  - unavailable: {note}")
    lines += ["", f"## Findings ({len(findings)})", ""]
    if not findings:
        lines.append("No findings recorded.")
    for severity in _SEVERITIES:
        group = sorted(
            (f for f in findings if f.severity is severity),
            key=lambda f: f.id,
        )
        if not group:
            continue
        lines.append(f"### {severity.value.upper()} ({len(group)})")
        lines.append("")
        for finding in group:
            entry = lifecycles.get(finding.id)
            lines.extend(
                _finding_block(
                    finding,
                    entry.lifecycle.value if entry is not None else "unknown",
                )
            )
        lines.append("")
    counts = {lifecycle: 0 for lifecycle in Lifecycle}
    for item in report.lifecycles:
        counts[item.lifecycle] += 1
    lines += ["## Lifecycle", ""]
    lines.append(
        f"{counts[Lifecycle.NEW]} new, {counts[Lifecycle.RECURRING]} recurring, "
        f"{counts[Lifecycle.RESOLVED]} resolved, "
        f"{counts[Lifecycle.REAPPEARED]} reappeared, "
        f"{counts[Lifecycle.INDETERMINATE]} indeterminate"
    )
    lines.append("")
    for item in report.lifecycles:
        if item.lifecycle in (
            Lifecycle.NEW,
            Lifecycle.REAPPEARED,
            Lifecycle.RESOLVED,
        ):
            lines.append(
                f"- {item.finding_id} ({item.analyzer}) - {item.lifecycle.value}: {item.reason}"
            )
    lines += [
        "",
        "## Limitations",
        "",
        "No findings does not prove the repository is free of issues. "
        "Results are limited to the checks performed, the available "
        "evidence, and the configured exclusions.",
        "",
    ]
    return "\n".join(lines)
