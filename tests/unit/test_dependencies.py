"""Stage 4 tests: dependencies analyzer."""

from __future__ import annotations

from pathlib import Path

from repo_health.analyzers.dependencies import analyze
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
    resolved = resolve_target(base)
    discovery = discover_files(resolved, DiscoveryConfig())
    return AnalysisContext(target=resolved, discovery=discovery, config=DiscoveryConfig())


def test_manifests_reported(tmp_path: Path) -> None:
    base = tmp_path / "repo"
    base.mkdir(parents=True, exist_ok=True)
    (base / "requirements.txt").write_text("pytest\n")
    (base / "sub").mkdir(parents=True)
    (base / "sub" / "package.json").write_text("{}\n")
    (base / "a.py").write_text("x = 1\n")
    result = analyze(make_context(base))
    assert result.succeeded() is True
    assert [(f.path, f.rule) for f in result.findings] == [
        ("requirements.txt", "dependencies.manifest-present"),
        ("sub/package.json", "dependencies.manifest-present"),
    ]
    assert all(f.severity is Severity.INFO for f in result.findings)


def test_no_manifests_is_success_empty(tmp_path: Path) -> None:
    base = tmp_path / "repo"
    base.mkdir(parents=True, exist_ok=True)
    (base / "a.py").write_text("x = 1\n")
    result = analyze(make_context(base))
    assert result.succeeded() is True
    assert result.findings == ()


def context_with_skips(
    base: Path, files: tuple[str, ...], skipped: tuple[SkippedEntry, ...]
) -> AnalysisContext:
    base.mkdir(parents=True, exist_ok=True)
    resolved = resolve_target(base)
    discovery = DiscoveryResult(root=resolved.root, files=files, skipped=skipped)
    return AnalysisContext(target=resolved, discovery=discovery, config=DiscoveryConfig())


def test_unreadable_dir_forces_partial(tmp_path: Path) -> None:
    base = tmp_path / "repo"
    context = context_with_skips(
        base, ("a.py",), (SkippedEntry("locked", SkipReason.UNREADABLE),)
    )
    result = analyze(context)
    assert result.status is AnalyzerStatus.PARTIAL
    assert result.findings == ()
    assert result.uncovered_checks == ("manifest-presence",)
    assert any("locked" in item for item in result.unavailable_evidence)


def test_irrelevant_skips_preserve_success(tmp_path: Path) -> None:
    base = tmp_path / "repo"
    context = context_with_skips(
        base,
        ("a.py",),
        (
            SkippedEntry(".git", SkipReason.EXCLUDED),
            SkippedEntry("big.txt", SkipReason.TOO_LARGE),
        ),
    )
    result = analyze(context)
    assert result.succeeded() is True
