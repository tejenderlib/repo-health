"""Dependency-manifest presence evidence (Stage 4).

Single check ``manifest-presence``: records known dependency manifests by
basename at any depth as INFO observations. Absence of manifests yields
SUCCESS with zero findings (absence alone is not a defect). Skipped paths
that could hide manifests are recorded as unavailable evidence (PARTIAL).
Manifests are not parsed in v1.
"""

from __future__ import annotations

import os

from repo_health.core.context import AnalysisContext
from repo_health.discovery.files import coverage_gaps
from repo_health.models import Severity
from repo_health.models.analyzer_result import AnalyzerResult, AnalyzerStatus
from repo_health.models.finding import Finding

_MANIFESTS = frozenset({"requirements.txt", "pyproject.toml", "package.json"})


def _is_manifest(rel: str) -> bool:
    return os.path.basename(rel) in _MANIFESTS


def analyze(context: AnalysisContext) -> AnalyzerResult:
    """Record known dependency manifests found during discovery."""
    findings: list[Finding] = []
    for rel in context.discovery.files:
        name = os.path.basename(rel)
        if name not in _MANIFESTS:
            continue
        findings.append(
            Finding(
                analyzer="dependencies",
                rule="dependencies.manifest-present",
                title=f"Dependency manifest present: {name}",
                description=f"The dependency manifest {rel} is present.",
                severity=Severity.INFO,
                path=rel,
                fingerprint=name,
                evidence=f"manifest file {rel} present",
            )
        )
    gaps = coverage_gaps(context.discovery.skipped, _is_manifest, "manifest presence")
    if gaps:
        return AnalyzerResult(
            analyzer="dependencies",
            status=AnalyzerStatus.PARTIAL,
            findings=tuple(findings),
            checks=("manifest-presence",),
            uncovered_checks=("manifest-presence",),
            unavailable_evidence=gaps,
        )
    return AnalyzerResult(
        analyzer="dependencies",
        status=AnalyzerStatus.SUCCESS,
        findings=tuple(findings),
        checks=("manifest-presence",),
    )
