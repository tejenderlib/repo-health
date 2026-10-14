"""Stage 4 tests: architecture analyzer (no invented constraints)."""

from __future__ import annotations

from pathlib import Path

from repo_health.analyzers.architecture import analyze as analyze_architecture
from repo_health.config import DiscoveryConfig
from repo_health.core.context import AnalysisContext
from repo_health.discovery.files import (
    DiscoveryResult,
    SkippedEntry,
    SkipReason,
    discover_files,
)
from repo_health.discovery.repository import resolve_target


def make_context(base: Path) -> AnalysisContext:
    base.mkdir(parents=True, exist_ok=True)
    resolved = resolve_target(base)
    discovery = discover_files(resolved, DiscoveryConfig())
    return AnalysisContext(target=resolved, discovery=discovery, config=DiscoveryConfig())


def test_architecture_reports_success_empty_without_invented_rules(
    tmp_path: Path,
) -> None:
    base = tmp_path / "repo"
    base.mkdir(parents=True, exist_ok=True)
    (base / "a.py").write_text("x = 1\n")
    result = analyze_architecture(make_context(base))
    assert result.succeeded() is True
    assert result.findings == ()
    assert result.checks == ("architecture-constraints",)


def test_discovery_skips_do_not_affect_empty_constraint_set(
    tmp_path: Path,
) -> None:
    base = tmp_path / "repo"
    base.mkdir(parents=True, exist_ok=True)
    resolved = resolve_target(base)
    discovery = DiscoveryResult(
        root=resolved.root,
        files=("a.py",),
        skipped=(SkippedEntry("locked", SkipReason.UNREADABLE),),
    )
    context = AnalysisContext(
        target=resolved, discovery=discovery, config=DiscoveryConfig()
    )
    result = analyze_architecture(context)
    assert result.succeeded() is True
