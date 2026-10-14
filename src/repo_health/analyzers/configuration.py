"""Project configuration-file presence evidence (Stage 4).

Single check ``config-file-presence``: records known project
configuration files by basename at any depth as INFO observations.
Absence yields SUCCESS with zero findings (absence alone is not a
defect). Skipped paths that could hide configuration files are recorded
as unavailable evidence (PARTIAL). Configuration values are not judged
in v1.
"""

from __future__ import annotations

import os

from repo_health.core.context import AnalysisContext
from repo_health.discovery.files import coverage_gaps
from repo_health.models import Severity
from repo_health.models.analyzer_result import AnalyzerResult, AnalyzerStatus
from repo_health.models.finding import Finding

_CONFIG_FILES = frozenset(
    {
        "pyproject.toml",
        "setup.py",
        "setup.cfg",
        "pytest.ini",
        "tox.ini",
        "package.json",
    }
)


def _is_config_file(rel: str) -> bool:
    return os.path.basename(rel) in _CONFIG_FILES


def analyze(context: AnalysisContext) -> AnalyzerResult:
    """Record known configuration files found during discovery."""
    findings: list[Finding] = []
    for rel in context.discovery.files:
        name = os.path.basename(rel)
        if name not in _CONFIG_FILES:
            continue
        findings.append(
            Finding(
                analyzer="configuration",
                rule="configuration.config-file-present",
                title=f"Configuration file present: {name}",
                description=f"The configuration file {rel} is present.",
                severity=Severity.INFO,
                path=rel,
                fingerprint=name,
                evidence=f"configuration file {rel} present",
            )
        )
    gaps = coverage_gaps(
        context.discovery.skipped, _is_config_file, "config-file presence"
    )
    if gaps:
        return AnalyzerResult(
            analyzer="configuration",
            status=AnalyzerStatus.PARTIAL,
            findings=tuple(findings),
            checks=("config-file-presence",),
            uncovered_checks=("config-file-presence",),
            unavailable_evidence=gaps,
        )
    return AnalyzerResult(
        analyzer="configuration",
        status=AnalyzerStatus.SUCCESS,
        findings=tuple(findings),
        checks=("config-file-presence",),
    )
