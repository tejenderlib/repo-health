"""Secret-pattern evidence (Stage 4).

Single check ``secret-pattern-scan`` over discovered files. Severity
criteria: HIGH for credential-material patterns (cloud access keys,
private key blocks) that are almost certainly sensitive; MEDIUM for
assignment-shaped hints (``key = ...``) that require human review.

Findings never reproduce secret values: assignment patterns match only
the key name and delimiter, evidence cites the pattern name and line,
and fingerprints contain pattern names only. Undecodable or unreadable
files, and skipped paths that could hide scannable files, are recorded
as unavailable evidence (PARTIAL).
"""

from __future__ import annotations

import os
import re

from repo_health.core.context import AnalysisContext
from repo_health.discovery.files import coverage_gaps
from repo_health.models import Severity
from repo_health.models.analyzer_result import AnalyzerResult, AnalyzerStatus
from repo_health.models.finding import Finding

_PATTERNS: tuple[tuple[str, Severity, re.Pattern[str]], ...] = (
    ("aws-access-key", Severity.HIGH, re.compile(r"AKIA[0-9A-Z]{16}")),
    (
        "private-key-block",
        Severity.HIGH,
        re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----"),
    ),
    (
        "secret-assignment",
        Severity.MEDIUM,
        re.compile(
            r"(?i)\b(api[_-]?key|secret|passwd|password|token)\b\s*[:=]"
        ),
    ),
)


def analyze(context: AnalysisContext) -> AnalyzerResult:
    """Scan discovered files for secret patterns without storing secrets."""
    root = context.target.root.root
    findings: list[Finding] = []
    unavailable: list[str] = []
    for rel in context.discovery.files:
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
            for name, severity, pattern in _PATTERNS:
                if pattern.search(line) is None:
                    continue
                findings.append(
                    Finding(
                        analyzer="security",
                        rule=f"security.{name}",
                        title=f"Possible {name} in {os.path.basename(rel)}",
                        description=(
                            "A potential secret pattern was detected; "
                            "verify and rotate it if genuine."
                        ),
                        severity=severity,
                        path=rel,
                        locator=f"L{number}",
                        fingerprint=name,
                        evidence=f"line {number} matches the {name} pattern",
                        recommendation=(
                            "Remove the secret from the repository, rotate "
                            "it, and use a secret manager."
                        ),
                    )
                )
    gaps = coverage_gaps(
        context.discovery.skipped, lambda rel: True, "secret-pattern scan"
    )
    missing = tuple(sorted(set(unavailable) | set(gaps)))
    if missing:
        # Any unavailable evidence means the scan did not complete.
        return AnalyzerResult(
            analyzer="security",
            status=AnalyzerStatus.PARTIAL,
            findings=tuple(findings),
            checks=("secret-pattern-scan",),
            uncovered_checks=("secret-pattern-scan",),
            unavailable_evidence=missing,
        )
    return AnalyzerResult(
        analyzer="security",
        status=AnalyzerStatus.SUCCESS,
        findings=tuple(findings),
        checks=("secret-pattern-scan",),
    )
