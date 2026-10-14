"""Stage 4 tests: security analyzer, including secret redaction."""

from __future__ import annotations

import json
from pathlib import Path

from repo_health.analyzers.security import analyze
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

AWS_EXAMPLE_KEY = "AKIAIOSFODNN7EXAMPLE"
ASSIGNMENT_SECRET = "hunter2-super-secret-value"


def make_context(base: Path) -> AnalysisContext:
    base.mkdir(parents=True, exist_ok=True)
    resolved = resolve_target(base)
    discovery = discover_files(resolved, DiscoveryConfig())
    return AnalysisContext(target=resolved, discovery=discovery, config=DiscoveryConfig())


def test_detects_each_pattern_class(tmp_path: Path) -> None:
    base = tmp_path / "repo"
    base.mkdir(parents=True, exist_ok=True)
    (base / "config.py").write_text(
        f'api_key = "{ASSIGNMENT_SECRET}"\nkey = "{AWS_EXAMPLE_KEY}"\n'
    )
    (base / "key.pem").write_text("-----BEGIN RSA PRIVATE KEY-----\ndata\n")
    result = analyze(make_context(base))
    assert result.succeeded() is True
    assert result.checks == ("secret-pattern-scan",)
    by_rule = {finding.rule: finding for finding in result.findings}
    assert set(by_rule) == {
        "security.secret-assignment",
        "security.aws-access-key",
        "security.private-key-block",
    }
    assert by_rule["security.aws-access-key"].severity is Severity.HIGH
    assert by_rule["security.private-key-block"].severity is Severity.HIGH
    assert by_rule["security.secret-assignment"].severity is Severity.MEDIUM
    assert by_rule["security.aws-access-key"].locator == "L2"
    assert len({finding.id for finding in result.findings}) == 3


def test_no_secret_values_leak(tmp_path: Path) -> None:
    base = tmp_path / "repo"
    base.mkdir(parents=True, exist_ok=True)
    (base / "config.py").write_text(
        f'api_key = "{ASSIGNMENT_SECRET}"\nkey = "{AWS_EXAMPLE_KEY}"\n'
    )
    (base / "key.pem").write_text("-----BEGIN RSA PRIVATE KEY-----\ndata\n")
    result = analyze(make_context(base))
    blob = json.dumps([finding.to_dict() for finding in result.findings])
    assert ASSIGNMENT_SECRET not in blob
    assert AWS_EXAMPLE_KEY not in blob
    assert "PRIVATE KEY-----\ndata" not in blob


def test_clean_tree_is_success_empty(tmp_path: Path) -> None:
    base = tmp_path / "repo"
    base.mkdir(parents=True, exist_ok=True)
    (base / "a.py").write_text('key = "value"\n')
    result = analyze(make_context(base))
    assert result.succeeded() is True
    assert result.findings == ()


def test_undecodable_file_is_partial(tmp_path: Path) -> None:
    base = tmp_path / "repo"
    base.mkdir(parents=True, exist_ok=True)
    (base / "odd.txt").write_bytes(b"\xff\xfe Latin-1 text \xe9\n")
    result = analyze(make_context(base))
    assert result.status is AnalyzerStatus.PARTIAL
    assert result.uncovered_checks == ("secret-pattern-scan",)
    assert any("odd.txt" in item for item in result.unavailable_evidence)


def test_file_vanished_after_discovery_is_partial(tmp_path: Path) -> None:
    base = tmp_path / "repo"
    base.mkdir(parents=True, exist_ok=True)
    resolved = resolve_target(base)
    discovery = DiscoveryResult(
        root=resolved.root, files=("gone.txt",), skipped=()
    )
    context = AnalysisContext(
        target=resolved, discovery=discovery, config=DiscoveryConfig()
    )
    result = analyze(context)
    assert result.status is AnalyzerStatus.PARTIAL
    assert result.uncovered_checks == ("secret-pattern-scan",)
    assert any("gone.txt" in item for item in result.unavailable_evidence)


def test_results_are_deterministic(tmp_path: Path) -> None:
    base = tmp_path / "repo"
    base.mkdir(parents=True, exist_ok=True)
    (base / "config.py").write_text(f'token = "{ASSIGNMENT_SECRET}"\n')
    assert analyze(make_context(base)) == analyze(make_context(base))


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


def test_any_skipped_file_content_forces_partial(tmp_path: Path) -> None:
    base = tmp_path / "repo"
    context = context_with_skips(
        base,
        ("a.py",),
        (
            SkippedEntry("big.txt", SkipReason.TOO_LARGE),
            SkippedEntry("img.bin", SkipReason.BINARY),
        ),
    )
    result = analyze(context)
    assert result.status is AnalyzerStatus.PARTIAL


def test_excluded_paths_preserve_success(tmp_path: Path) -> None:
    base = tmp_path / "repo"
    context = context_with_skips(
        base, ("a.py",), (SkippedEntry(".git", SkipReason.EXCLUDED),)
    )
    result = analyze(context)
    assert result.succeeded() is True
