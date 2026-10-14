"""Analyzer registry (Stage 4; all eight documented analyzers registered).

``AnalyzerFunction`` maps an explicit :class:`AnalysisContext` to its
:class:`AnalyzerResult`. ``ANALYZERS`` holds the documented analyzers in
deterministic run order; analyzers must never be added or removed
silently.
"""

from __future__ import annotations

from collections.abc import Callable

from repo_health.analyzers import (
    architecture,
    code,
    configuration,
    dependencies,
    documentation,
    git,
    security,
    tests,
)
from repo_health.core.context import AnalysisContext
from repo_health.models.analyzer_result import AnalyzerResult

AnalyzerFunction = Callable[[AnalysisContext], AnalyzerResult]

ANALYZERS: dict[str, AnalyzerFunction] = {
    "git": git.analyze,
    "code": code.analyze,
    "tests": tests.analyze,
    "dependencies": dependencies.analyze,
    "security": security.analyze,
    "documentation": documentation.analyze,
    "architecture": architecture.analyze,
    "configuration": configuration.analyze,
}


def analyzer_names() -> tuple[str, ...]:
    """Return the registered analyzer names in run order."""
    return tuple(ANALYZERS)
