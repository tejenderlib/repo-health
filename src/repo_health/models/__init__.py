"""Shared data contracts (Stages 1, 2, and 6: models and lifecycle)."""

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
from repo_health.models.lifecycle import FindingLifecycle, Lifecycle
from repo_health.models.observation import Observation
from repo_health.models.repository import Repository
from repo_health.models.run import AnalysisRun, RunStatus

__all__ = [
    "AnalysisRun",
    "AnalyzerResult",
    "AnalyzerStatus",
    "EvidenceState",
    "Finding",
    "FindingLifecycle",
    "Lifecycle",
    "Observation",
    "Repository",
    "RunStatus",
    "Severity",
    "canonicalize_repo_path",
    "compute_finding_id",
    "is_established",
    "validate_identifier",
]
