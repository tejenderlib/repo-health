"""Stage 4 tests: tests analyzer."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from repo_health.analyzers.tests import analyze
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


def test_test_files_reported(tmp_path: Path) -> None:
    base = tmp_path / "repo"
    base.mkdir(parents=True, exist_ok=True)
    (base / "test_a.py").write_text("def test_x(): pass\n")
    (base / "sub").mkdir(parents=True)
    (base / "sub" / "b_test.py").write_text("def test_y(): pass\n")
    (base / "a.py").write_text("x = 1\n")
    (base / "attest.py").write_text("x = 1\n")
    result = analyze(make_context(base))
    assert result.succeeded() is True
    assert sorted(f.path for f in result.findings) == ["sub/b_test.py", "test_a.py"]
    assert all(f.rule == "tests.test-file-present" for f in result.findings)
    assert all(f.severity is Severity.INFO for f in result.findings)


def test_no_tests_is_success_empty(tmp_path: Path) -> None:
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
    assert result.uncovered_checks == ("test-file-presence",)
    assert any(
        "locked" in item and "unreadable" in item
        for item in result.unavailable_evidence
    )


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


@pytest.mark.skipif(
    os.name != "posix" or (hasattr(os, "geteuid") and os.geteuid() == 0),
    reason="requires POSIX non-root permission semantics",
)
def test_hidden_tests_behind_unreadable_dir(tmp_path: Path) -> None:
    base = tmp_path / "repo"
    (base / "locked").mkdir(parents=True)
    (base / "locked" / "test_hidden.py").write_text("def test_x(): pass\n")
    (base / "a.py").write_text("x = 1\n")
    os.chmod(base / "locked", 0o000)
    try:
        resolved = resolve_target(base)
        discovery = discover_files(resolved, DiscoveryConfig(exclude=()))
        context = AnalysisContext(
            target=resolved, discovery=discovery, config=DiscoveryConfig(exclude=())
        )
    finally:
        os.chmod(base / "locked", 0o755)
    assert discovery.is_complete is False
    result = analyze(context)
    assert result.status is AnalyzerStatus.PARTIAL
    assert result.findings == ()
    assert any("locked" in item for item in result.unavailable_evidence)
