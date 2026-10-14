"""Stage 3, Task 2 tests: discovery configuration defaults and validation."""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from repo_health.analyzers.configuration import analyze as analyze_configuration
from repo_health.config import (
    DEFAULT_EXCLUDES,
    DEFAULT_MAX_FILE_SIZE,
    DiscoveryConfig,
)
from repo_health.core.context import AnalysisContext
from repo_health.core.exceptions import ValidationError
from repo_health.discovery import matches
from repo_health.discovery.files import (
    DiscoveryResult,
    SkippedEntry,
    SkipReason,
    discover_files,
)
from repo_health.discovery.repository import resolve_target
from repo_health.models import Severity
from repo_health.models.analyzer_result import AnalyzerStatus


def test_defaults() -> None:
    config = DiscoveryConfig()
    assert config.include == ()
    assert config.exclude == DEFAULT_EXCLUDES
    assert DEFAULT_EXCLUDES == (
        ".git/",
        "__pycache__/",
        "*.pyc",
        "venv/",
        ".venv/",
        "env/",
        ".env/",
        "node_modules/",
    )
    assert config.max_file_size == DEFAULT_MAX_FILE_SIZE == 1_048_576
    assert config.follow_symlinks is False
    assert config.compiled_include == ()
    assert [p.source for p in config.compiled_exclude] == [
        ".git/**",
        "__pycache__/**",
        "*.pyc",
        "venv/**",
        ".venv/**",
        "env/**",
        ".env/**",
        "node_modules/**",
    ]


def test_config_is_frozen_and_deterministic() -> None:
    assert DiscoveryConfig() == DiscoveryConfig()
    with pytest.raises(dataclasses.FrozenInstanceError):
        DiscoveryConfig().max_file_size = 10  # type: ignore[misc]


@pytest.mark.parametrize("size", [0, -1, -1_048_576, True, False, "big", 1.5, None])
def test_invalid_sizes_rejected(size: object) -> None:
    with pytest.raises(ValidationError):
        DiscoveryConfig(max_file_size=size)  # type: ignore[arg-type]


def test_follow_symlinks_true_rejected() -> None:
    with pytest.raises(ValidationError):
        DiscoveryConfig(follow_symlinks=True)


@pytest.mark.parametrize("value", [1, 0, "true", "False", None, 1.0, [], "yes"])
def test_non_boolean_follow_symlinks_rejected(value: object) -> None:
    with pytest.raises(ValidationError):
        DiscoveryConfig(follow_symlinks=value)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "patterns",
    [
        "/abs/*.py",
        ("ok/*.py", "../escape"),
        ("ok/*.py", ""),
        "src/*.py",
        ["src/*.py"],
        ("ok/*.py", 42),
    ],
)
def test_invalid_pattern_collections_rejected(patterns: object) -> None:
    with pytest.raises(ValidationError):
        DiscoveryConfig(include=patterns)  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        DiscoveryConfig(exclude=patterns)  # type: ignore[arg-type]


def test_valid_overrides_compile() -> None:
    config = DiscoveryConfig(include=("src/**",), exclude=("src/gen/**",))
    assert [p.source for p in config.compiled_include] == ["src/**"]
    assert [p.source for p in config.compiled_exclude] == ["src/gen/**"]
    assert matches(config.compiled_include[0], "src/a.py") is True
    assert matches(config.compiled_exclude[0], "src/gen/a.py") is True


def test_directory_pattern_matches_dir_itself_and_tree() -> None:
    # Requirement 8's file-vs-directory distinction (a file named `.env`
    # is not excluded by `.env/`) is enforced in Task 4 by applying
    # trailing-`/` patterns to directories only. At the engine level,
    # `.env/**` matches the directory itself and everything under it,
    # per the approved `a/**` semantics.
    (pattern,) = [p for p in DiscoveryConfig().compiled_exclude if p.source == ".env/**"]
    assert matches(pattern, ".env") is True
    assert matches(pattern, ".env/file") is True
    assert matches(pattern, ".env/nested/file") is True
    assert matches(pattern, "other.env/file") is False


def test_default_excludes_match_expected_paths() -> None:
    by_source = {p.source: p for p in DiscoveryConfig().compiled_exclude}
    assert matches(by_source[".git/**"], ".git/config") is True
    assert matches(by_source[".git/**"], ".git") is True
    assert matches(by_source["__pycache__/**"], "__pycache__/a.pyc") is True
    assert matches(by_source["*.pyc"], "a.pyc") is True
    assert matches(by_source["*.pyc"], "src/a.pyc") is False
    assert matches(by_source["venv/**"], "venv/bin/activate") is True
    assert matches(by_source["node_modules/**"], "node_modules/x/index.js") is True


# Stage 4: configuration analyzer


def make_analyzer_context(base: Path) -> AnalysisContext:
    base.mkdir(parents=True, exist_ok=True)
    resolved = resolve_target(base)
    discovery = discover_files(resolved, DiscoveryConfig())
    return AnalysisContext(target=resolved, discovery=discovery, config=DiscoveryConfig())


def test_configuration_files_reported(tmp_path: Path) -> None:
    base = tmp_path / "repo"
    base.mkdir(parents=True, exist_ok=True)
    (base / "pyproject.toml").write_text("[project]\n")
    (base / "sub").mkdir(parents=True)
    (base / "sub" / "pytest.ini").write_text("[pytest]\n")
    (base / "notes.txt").write_text("hi\n")
    result = analyze_configuration(make_analyzer_context(base))
    assert result.succeeded() is True
    assert [(f.path, f.rule) for f in result.findings] == [
        ("pyproject.toml", "configuration.config-file-present"),
        ("sub/pytest.ini", "configuration.config-file-present"),
    ]
    assert all(f.severity is Severity.INFO for f in result.findings)


def test_no_configuration_files_is_success_empty(tmp_path: Path) -> None:
    base = tmp_path / "repo"
    base.mkdir(parents=True, exist_ok=True)
    (base / "a.py").write_text("x = 1\n")
    result = analyze_configuration(make_analyzer_context(base))
    assert result.succeeded() is True
    assert result.findings == ()


def test_unreadable_dir_forces_partial(tmp_path: Path) -> None:
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
    result = analyze_configuration(context)
    assert result.status is AnalyzerStatus.PARTIAL
    assert result.findings == ()


def test_irrelevant_skips_preserve_success(tmp_path: Path) -> None:
    base = tmp_path / "repo"
    base.mkdir(parents=True, exist_ok=True)
    resolved = resolve_target(base)
    discovery = DiscoveryResult(
        root=resolved.root,
        files=("a.py",),
        skipped=(
            SkippedEntry(".git", SkipReason.EXCLUDED),
            SkippedEntry("notes.txt", SkipReason.TOO_LARGE),
        ),
    )
    context = AnalysisContext(
        target=resolved, discovery=discovery, config=DiscoveryConfig()
    )
    assert analyze_configuration(context).succeeded() is True
