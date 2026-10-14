"""Test-file presence evidence (Stage 4).

Single check ``test-file-presence``: records files whose basename matches
``test_*.py`` or ``*_test.py`` as INFO observations. Absence of test
files yields SUCCESS with zero findings (absence alone is not a defect).
Skipped paths that could hide test files are recorded as unavailable
evidence (PARTIAL). Test content is never executed.
"""

from __future__ import annotations

import os

from repo_health.core.context import AnalysisContext
from repo_health.discovery.files import coverage_gaps
from repo_health.discovery.patterns import compile_pattern, matches
from repo_health.models import Severity
from repo_health.models.analyzer_result import AnalyzerResult, AnalyzerStatus
from repo_health.models.finding import Finding

_TEST_PATTERNS = (compile_pattern("test_*.py"), compile_pattern("*_test.py"))


def _is_test_file(rel: str) -> bool:
    name = os.path.basename(rel)
    return any(matches(pattern, name) for pattern in _TEST_PATTERNS)


def analyze(context: AnalysisContext) -> AnalyzerResult:
    """Record test files found during discovery."""
    findings: list[Finding] = []
    for rel in context.discovery.files:
        if not _is_test_file(rel):
            continue
        name = os.path.basename(rel)
        findings.append(
            Finding(
                analyzer="tests",
                rule="tests.test-file-present",
                title=f"Test file present: {name}",
                description=f"The test file {rel} is present.",
                severity=Severity.INFO,
                path=rel,
                evidence=f"test file {rel} present",
            )
        )
    gaps = coverage_gaps(context.discovery.skipped, _is_test_file, "test-file presence")
    if gaps:
        return AnalyzerResult(
            analyzer="tests",
            status=AnalyzerStatus.PARTIAL,
            findings=tuple(findings),
            checks=("test-file-presence",),
            uncovered_checks=("test-file-presence",),
            unavailable_evidence=gaps,
        )
    return AnalyzerResult(
        analyzer="tests",
        status=AnalyzerStatus.SUCCESS,
        findings=tuple(findings),
        checks=("test-file-presence",),
    )
