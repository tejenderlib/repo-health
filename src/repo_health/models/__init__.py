"""Shared data contracts (Stage 1: evidence, finding, result, repository)."""

from __future__ import annotations

from repo_health.models.analyzer_result import AnalyzerResult, AnalyzerStatus
from repo_health.models.evidence import EvidenceState, is_established
from repo_health.models.finding import (
    Finding,
    Severity,
    canonicalize_repo_path,
    compute_finding_id,
    validate_identifier,
)
from repo_health.models.repository import Repository

__all__ = [
    "AnalyzerResult",
    "AnalyzerStatus",
    "EvidenceState",
    "Finding",
    "Repository",
    "Severity",
    "canonicalize_repo_path",
    "compute_finding_id",
    "is_established",
    "validate_identifier",
]
