"""Documentation presence evidence (Stage 4).

Single check ``readme-presence``: records a root-level README (known
basenames) as an INFO observation. Absence yields SUCCESS with zero
findings (absence alone is not a defect). Skipped paths that could hide a
root README are recorded as unavailable evidence (PARTIAL). Documentation
content is not judged in v1.
"""

from __future__ import annotations

import os

from repo_health.core.context import AnalysisContext
from repo_health.discovery.files import coverage_gaps
from repo_health.models import Severity
from repo_health.models.analyzer_result import AnalyzerResult, AnalyzerStatus
from repo_health.models.finding import Finding

_READMES = frozenset({"README.md", "README", "README.txt", "README.rst"})


def _is_readme(rel: str) -> bool:
    return "/" not in rel and os.path.basename(rel) in _READMES


def analyze(context: AnalysisContext) -> AnalyzerResult:
    """Record a root-level README found during discovery."""
    findings: list[Finding] = []
    for rel in context.discovery.files:
        if not _is_readme(rel):
            continue
        findings.append(
            Finding(
                analyzer="documentation",
                rule="documentation.readme-present",
                title=f"Documentation present: {rel}",
                description=f"The documentation file {rel} is present.",
                severity=Severity.INFO,
                path=rel,
                evidence=f"documentation file {rel} present",
            )
        )
    gaps = coverage_gaps(context.discovery.skipped, _is_readme, "readme presence")
    if gaps:
        return AnalyzerResult(
            analyzer="documentation",
            status=AnalyzerStatus.PARTIAL,
            findings=tuple(findings),
            checks=("readme-presence",),
            uncovered_checks=("readme-presence",),
            unavailable_evidence=gaps,
        )
    return AnalyzerResult(
        analyzer="documentation",
        status=AnalyzerStatus.SUCCESS,
        findings=tuple(findings),
        checks=("readme-presence",),
    )
