"""Stage 4 tests: git analyzer."""

from __future__ import annotations

from pathlib import Path

from repo_health.analyzers.git import analyze
from repo_health.config import DiscoveryConfig
from repo_health.core.context import AnalysisContext
from repo_health.discovery.files import (
    DiscoveryResult,
    SkippedEntry,
    SkipReason,
    discover_files,
)
from repo_health.discovery.repository import resolve_target
from repo_health.models import Severity
from repo_health.models.analyzer_result import AnalyzerStatus


def make_context(base: Path) -> AnalysisContext:
    base.mkdir(parents=True, exist_ok=True)
    (base / "a.py").write_text("x = 1\n")
    resolved = resolve_target(base)
    discovery = discover_files(resolved, DiscoveryConfig())
    return AnalysisContext(target=resolved, discovery=discovery, config=DiscoveryConfig())


def test_git_present_reports_info(tmp_path: Path) -> None:
    base = tmp_path / "repo"
    base.mkdir(parents=True, exist_ok=True)
    (base / ".git").mkdir(parents=True)
    result = analyze(make_context(base))
    assert result.succeeded() is True
    assert result.checks == ("git-presence",)
    (finding,) = result.findings
    assert finding.rule == "git.repository-present"
    assert finding.severity is Severity.INFO
    assert finding.path == ""


def test_git_absent_is_partial_not_clean(tmp_path: Path) -> None:
    result = analyze(make_context(tmp_path / "plain"))
    assert result.status is AnalyzerStatus.PARTIAL
    assert result.findings == ()
    assert result.checks == ("git-presence",)
    assert result.unavailable_evidence != ()


def test_discovery_skips_do_not_affect_git_presence(tmp_path: Path) -> None:
    base = tmp_path / "repo"
    (base / ".git").mkdir(parents=True)
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
    result = analyze(context)
    assert result.succeeded() is True
