"""Observation model (Stage 2 contract).

An observation records that a finding was observed in a specific analysis
run, with the evidence state that applied at the time. Absence of an
observation row means "not observed"; it must never be read as "resolved"
without the comparison rules in docs/rules.md section 8.
"""

from __future__ import annotations

from dataclasses import dataclass

from repo_health.core.exceptions import ValidationError
from repo_health.models.evidence import EvidenceState
from repo_health.models.finding import IDENTITY_RE, validate_identifier


@dataclass(frozen=True)
class Observation:
    """A finding observed in a run. ``observed_at`` is set on storage."""

    run_id: int
    finding_id: str
    analyzer: str
    repository_id: int
    evidence_state: EvidenceState = EvidenceState.KNOWN
    observed_at: str = ""

    def __post_init__(self) -> None:
        if self.run_id < 1:
            raise ValidationError(f"run_id must be positive, got {self.run_id!r}")
        if self.repository_id < 1:
            raise ValidationError(
                f"repository_id must be positive, got {self.repository_id!r}"
            )
        finding_id = self.finding_id.strip()
        if IDENTITY_RE.fullmatch(finding_id) is None:
            raise ValidationError(
                f"finding_id must match {IDENTITY_RE.pattern}, got {self.finding_id!r}"
            )
        analyzer = validate_identifier("analyzer", self.analyzer)
        if not isinstance(self.evidence_state, EvidenceState):
            raise ValidationError(
                "evidence_state must be an EvidenceState member,"
                f" got {self.evidence_state!r}"
            )
        object.__setattr__(self, "finding_id", finding_id)
        object.__setattr__(self, "analyzer", analyzer)
