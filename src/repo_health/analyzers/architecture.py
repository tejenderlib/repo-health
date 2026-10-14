"""Architectural-constraint evidence (Stage 4).

Single check ``architecture-constraints``: evaluates explicitly configured
architectural constraints. No constraints are configured in v1, so this
analyzer honestly reports SUCCESS with zero findings within its (empty)
documented scope. Constraints must never be invented from naming
conventions (see docs/rules.md section 11).
"""

from __future__ import annotations

from repo_health.core.context import AnalysisContext
from repo_health.models.analyzer_result import AnalyzerResult, AnalyzerStatus


def analyze(context: AnalysisContext) -> AnalyzerResult:
    """Evaluate configured constraints (none in v1)."""
    _ = context
    return AnalyzerResult(
        analyzer="architecture",
        status=AnalyzerStatus.SUCCESS,
        checks=("architecture-constraints",),
    )
