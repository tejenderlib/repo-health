"""Stage 4 tests: code analyzer (trailing whitespace)."""

from __future__ import annotations

from pathlib import Path

from repo_health.analyzers.code import analyze
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


def test_trailing_whitespace_found(tmp_path: Path) -> None:
    base = tmp_path / "repo"
    base.mkdir(parents=True, exist_ok=True)
    (base / "a.py").write_text("x = 1  \ny = 2\t\nz = 3\n")
    (base / "b.js").write_text("var x = 1;  \n")
    result = analyze(make_context(base))
    assert result.succeeded() is True
    assert sorted((f.path, f.locator) for f in result.findings) == [
        ("a.py", "L1"),
        ("a.py", "L2"),
    ]
    assert all(f.severity is Severity.LOW for f in result.findings)
    assert all(f.rule == "code.trailing-whitespace" for f in result.findings)


def test_clean_python_is_success_empty(tmp_path: Path) -> None:
    base = tmp_path / "repo"
    base.mkdir(parents=True, exist_ok=True)
    (base / "a.py").write_text("x = 1\n")
    result = analyze(make_context(base))
    assert result.succeeded() is True
    assert result.findings == ()
    assert result.checks == ("trailing-whitespace-scan",)


def test_undecodable_python_is_partial(tmp_path: Path) -> None:
    base = tmp_path / "repo"
    base.mkdir(parents=True, exist_ok=True)
    (base / "a.py").write_bytes(b"x = '\xe9'\n")
    result = analyze(make_context(base))
    assert result.status is AnalyzerStatus.PARTIAL
    assert result.uncovered_checks == ("trailing-whitespace-scan",)
    assert any("a.py" in item for item in result.unavailable_evidence)


def test_file_vanished_after_discovery_is_partial(tmp_path: Path) -> None:
    base = tmp_path / "repo"
    base.mkdir(parents=True, exist_ok=True)
    resolved = resolve_target(base)
    discovery = DiscoveryResult(
        root=resolved.root, files=("gone.py",), skipped=()
    )
    context = AnalysisContext(
        target=resolved, discovery=discovery, config=DiscoveryConfig()
    )
    result = analyze(context)
    assert result.status is AnalyzerStatus.PARTIAL
    assert result.uncovered_checks == ("trailing-whitespace-scan",)
    assert any("gone.py" in item for item in result.unavailable_evidence)


def context_with_skips(
    base: Path, files: tuple[str, ...], skipped: tuple[SkippedEntry, ...]
) -> AnalysisContext:
    base.mkdir(parents=True, exist_ok=True)
    for name in files:
        target = base / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("x = 1\n")
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
    assert any("locked" in item for item in result.unavailable_evidence)


def test_matching_oversized_python_forces_partial(tmp_path: Path) -> None:
    base = tmp_path / "repo"
    context = context_with_skips(
        base, ("a.py",), (SkippedEntry("big.py", SkipReason.TOO_LARGE),)
    )
    result = analyze(context)
    assert result.status is AnalyzerStatus.PARTIAL
    assert any("big.py" in item for item in result.unavailable_evidence)


def test_irrelevant_skips_preserve_success(tmp_path: Path) -> None:
    base = tmp_path / "repo"
    context = context_with_skips(
        base,
        ("a.py",),
        (
            SkippedEntry(".git", SkipReason.EXCLUDED),
            SkippedEntry("big.txt", SkipReason.TOO_LARGE),
            SkippedEntry("img.bin", SkipReason.BINARY),
        ),
    )
    result = analyze(context)
    assert result.succeeded() is True
