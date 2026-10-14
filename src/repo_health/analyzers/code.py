"""Trailing-whitespace evidence in Python files (Stage 4).

Single check ``trailing-whitespace-scan``: lines ending in a space or tab
(criterion documented here) yield LOW findings with line locators. Only
files detected as Python are scanned. Undecodable or unreadable files,
and skipped paths that could hide Python files, are recorded as
unavailable evidence (PARTIAL), never as clean.
"""

from __future__ import annotations

import os

from repo_health.core.context import AnalysisContext
from repo_health.discovery.files import coverage_gaps
from repo_health.discovery.languages import detect_language
from repo_health.models import Severity
from repo_health.models.analyzer_result import AnalyzerResult, AnalyzerStatus
from repo_health.models.finding import Finding


def analyze(context: AnalysisContext) -> AnalyzerResult:
    """Report trailing whitespace in discovered Python files."""
    root = context.target.root.root
    findings: list[Finding] = []
    unavailable: list[str] = []
    for rel in context.discovery.files:
        if detect_language(rel) != "python":
            continue
        try:
            with open(os.path.join(root, *rel.split("/")), encoding="utf-8") as handle:
                text = handle.read()
        except UnicodeDecodeError:
            unavailable.append(f"{rel}: undecodable as UTF-8")
            continue
        except OSError as exc:
            unavailable.append(f"{rel}: unreadable during scan ({exc.strerror})")
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            if line.rstrip("\r\n").endswith((" ", "\t")):
                findings.append(
                    Finding(
                        analyzer="code",
                        rule="code.trailing-whitespace",
                        title=f"Trailing whitespace in {os.path.basename(rel)}",
                        description="A line ends with a space or tab character.",
                        severity=Severity.LOW,
                        path=rel,
                        locator=f"L{number}",
                        evidence=f"line {number} has trailing whitespace",
                        recommendation="Remove the trailing whitespace.",
                    )
                )
    gaps = coverage_gaps(
        context.discovery.skipped,
        lambda rel: detect_language(rel) == "python",
        "trailing-whitespace scan",
    )
    missing = tuple(sorted(set(unavailable) | set(gaps)))
    if missing:
        # Any unavailable evidence means the scan did not complete.
        return AnalyzerResult(
            analyzer="code",
            status=AnalyzerStatus.PARTIAL,
            findings=tuple(findings),
            checks=("trailing-whitespace-scan",),
            uncovered_checks=("trailing-whitespace-scan",),
            unavailable_evidence=missing,
        )
    return AnalyzerResult(
        analyzer="code",
        status=AnalyzerStatus.SUCCESS,
        findings=tuple(findings),
        checks=("trailing-whitespace-scan",),
    )
