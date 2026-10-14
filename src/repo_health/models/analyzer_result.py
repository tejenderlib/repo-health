"""Analyzer execution-result model (Stage 1 contract).

An analyzer result is distinct from the findings it produced: it records
which analyzer ran, whether execution succeeded, partially succeeded,
failed, or did not run, which checks were performed, and which evidence
was unavailable. An execution failure must never be converted into a
successful result with zero findings.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from repo_health.core.exceptions import ValidationError
from repo_health.models.finding import Finding, validate_identifier


class AnalyzerStatus(StrEnum):
    """Execution status of a single analyzer run."""

    # The analyzer completed its checks within its documented scope.
    SUCCESS = "success"
    # Some checks or evidence were unavailable; output is not complete.
    PARTIAL = "partial"
    # The analyzer could not execute; failure information is preserved.
    FAILED = "failed"
    # The analyzer was disabled; it did not run (never "zero findings").
    NOT_RUN = "not_run"


@dataclass(frozen=True)
class AnalyzerResult:
    """The outcome of executing one analyzer."""

    analyzer: str = ""
    status: AnalyzerStatus = AnalyzerStatus.NOT_RUN
    findings: tuple[Finding, ...] = ()
    checks: tuple[str, ...] = ()
    uncovered_checks: tuple[str, ...] = ()
    unavailable_evidence: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        analyzer = validate_identifier("analyzer", self.analyzer)
        if not isinstance(self.status, AnalyzerStatus):
            raise ValidationError(
                f"status must be an AnalyzerStatus member, got {self.status!r}"
            )
        findings = tuple(sorted(self.findings, key=lambda item: item.sort_key()))
        if self.status is AnalyzerStatus.FAILED and not self.errors:
            raise ValidationError("a failed analyzer must preserve error information")
        if self.status is AnalyzerStatus.PARTIAL and not (
            self.uncovered_checks or self.unavailable_evidence
        ):
            raise ValidationError(
                "a partial analyzer must identify uncovered checks "
                "or unavailable evidence"
            )
        if self.status is AnalyzerStatus.NOT_RUN and (self.findings or self.checks):
            raise ValidationError(
                "an analyzer that did not run must report no findings"
            )
        object.__setattr__(self, "analyzer", analyzer)
        object.__setattr__(self, "findings", findings)

    def succeeded(self) -> bool:
        """Return True only for fully successful execution."""
        return self.status is AnalyzerStatus.SUCCESS
