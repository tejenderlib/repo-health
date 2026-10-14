"""Git repository-state evidence (Stage 4).

Single check ``git-presence``: whether the target resides in a Git
repository. A non-Git target yields PARTIAL (Git history evidence is
unavailable, so output must not pose as complete); a Git target yields
SUCCESS with one INFO observation of presence. No history is parsed and
no Git subprocess runs in v1. Discovery file skips cannot affect this
check: it reads repository metadata, not file content.
"""

from __future__ import annotations

from repo_health.core.context import AnalysisContext
from repo_health.models import Severity
from repo_health.models.analyzer_result import AnalyzerResult, AnalyzerStatus
from repo_health.models.finding import Finding


def analyze(context: AnalysisContext) -> AnalyzerResult:
    """Evaluate Git presence evidence for the run context."""
    if not context.target.is_git:
        return AnalyzerResult(
            analyzer="git",
            status=AnalyzerStatus.PARTIAL,
            checks=("git-presence",),
            unavailable_evidence=(
                "git history and metadata: target is not a Git repository",
            ),
        )
    return AnalyzerResult(
        analyzer="git",
        status=AnalyzerStatus.SUCCESS,
        findings=(
            Finding(
                analyzer="git",
                rule="git.repository-present",
                title="Git repository detected",
                description="The target resides in a Git repository.",
                severity=Severity.INFO,
                evidence=".git directory present at the repository root",
            ),
        ),
        checks=("git-presence",),
    )
