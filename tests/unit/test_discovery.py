"""Stage 3 tests: glob-pattern engine, resolution, enumeration, languages."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from repo_health.config import DiscoveryConfig
from repo_health.core.exceptions import ValidationError
from repo_health.discovery import (
    CompiledPattern,
    DiscoveryResult,
    ResolvedTarget,
    SkippedEntry,
    SkipReason,
    compile_pattern,
    detect_language,
    discover_files,
    matches,
    resolve_target,
)
from repo_health.models.repository import Repository


def assert_matches(pattern: str, path: str) -> None:
    assert matches(compile_pattern(pattern), path) is True


def assert_no_match(pattern: str, path: str) -> None:
    assert matches(compile_pattern(pattern), path) is False


# Compilation and normalization


def test_normalization() -> None:
    assert compile_pattern("./src/*.py").source == "src/*.py"
    assert compile_pattern("src\\*.py").source == "src/*.py"
    assert compile_pattern("src//*.py").source == "src/*.py"
    assert compile_pattern("build/").source == "build/**"
    assert compile_pattern("**").source == "**"
    assert compile_pattern("**/").source == "**"


@pytest.mark.parametrize(
    "bad", ["", "   ", ".", "./", "/abs/*.py", "C:/x/*.py", "../x/*.py", "a/../b"]
)
def test_invalid_patterns_rejected(bad: str) -> None:
    with pytest.raises(ValidationError):
        compile_pattern(bad)


def test_non_string_pattern_rejected() -> None:
    with pytest.raises(ValidationError):
        compile_pattern(None)  # type: ignore[arg-type]


def test_compiled_patterns_compare_by_source() -> None:
    first = compile_pattern("src/*.py")
    second = compile_pattern("./src/*.py")
    assert isinstance(first, CompiledPattern)
    assert first == second
    assert hash(first) == hash(second)


# Star semantics


@pytest.mark.parametrize(
    ("pattern", "path"),
    [("*.py", "a.py"), ("src/*.py", "src/a.py"), ("a*b", "ab"), ("a*b", "axxb")],
)
def test_star_matches(pattern: str, path: str) -> None:
    assert_matches(pattern, path)


@pytest.mark.parametrize(
    ("pattern", "path"),
    [
        ("*.py", "d/a.py"),
        ("src/*.py", "a.py"),
        ("src/*.py", "src/d/a.py"),
        ("*", "a/b"),
        ("a*b", "a/b"),
    ],
)
def test_star_does_not_cross_separator(pattern: str, path: str) -> None:
    assert_no_match(pattern, path)


# Question-mark semantics


@pytest.mark.parametrize(("pattern", "path"), [("a?.py", "ab.py"), ("?", "a")])
def test_question_mark_matches(pattern: str, path: str) -> None:
    assert_matches(pattern, path)


@pytest.mark.parametrize(
    ("pattern", "path"),
    [
        ("a?.py", "a.py"),
        ("a?.py", "abc.py"),
        ("a?.py", "a/b.py"),
        ("?", ""),
        ("?", "ab"),
    ],
)
def test_question_mark_is_exactly_one_non_separator(pattern: str, path: str) -> None:
    assert_no_match(pattern, path)


# Double-star semantics


@pytest.mark.parametrize(
    ("pattern", "path"),
    [
        ("**", "a"),
        ("**", "a/b/c"),
        ("**/*.py", "a.py"),
        ("**/*.py", "d/a.py"),
        ("**/*.py", "d/e/a.py"),
        ("src/**", "src"),
        ("src/**", "src/a.py"),
        ("src/**", "src/a/b/c"),
        ("a/**/b", "a/b"),
        ("a/**/b", "a/x/b"),
        ("a/**/b", "a/x/y/b"),
        ("a/**/b/**/c", "a/b/c"),
        ("a/**/b/**/c", "a/x/b/y/c"),
        ("**/**", "a/b"),
    ],
)
def test_double_star_matches(pattern: str, path: str) -> None:
    assert_matches(pattern, path)


@pytest.mark.parametrize(
    ("pattern", "path"),
    [
        ("**/*.py", "a.txt"),
        ("src/**", "other"),
        ("src/**", "srcx/a.py"),
        ("a/**/b", "a/x/c"),
        ("a/**/b", "a/b/c"),
        ("a/**/b", "x/a/b"),
    ],
)
def test_double_star_limits(pattern: str, path: str) -> None:
    assert_no_match(pattern, path)


# Literal characters and case


@pytest.mark.parametrize(
    ("pattern", "path"),
    [
        ("a.py", "a.py"),
        ("a+b.py", "a+b.py"),
        ("a[0].py", "a[0].py"),
        ("(x).py", "(x).py"),
        ("*.tar.gz", "a.tar.gz"),
    ],
)
def test_special_chars_are_literal(pattern: str, path: str) -> None:
    assert_matches(pattern, path)


@pytest.mark.parametrize(
    ("pattern", "path"),
    [("a.py", "aXpy"), ("a[0].py", "a0.py"), ("*.PY", "a.py"), ("*.py", "A.PY")],
)
def test_matching_is_case_sensitive(pattern: str, path: str) -> None:
    assert_no_match(pattern, path)


# Candidates and determinism


@pytest.mark.parametrize("path", ["/abs/a.py", "C:\\win\\a.py", ""])
def test_absolute_or_empty_candidates_never_match(path: str) -> None:
    assert matches(compile_pattern("**"), path) is False


@pytest.mark.parametrize("path", [".", "..", "../a.py", "a/../b.py", "a/b/../../c.py"])
def test_dot_segments_never_match(path: str) -> None:
    assert matches(compile_pattern("**"), path) is False
    assert matches(compile_pattern("a/*.py"), path) is False


@pytest.mark.parametrize(
    ("pattern", "path"),
    [("*", " a.py"), ("*", "a.py "), ("?.py", " .py"), ("**", " dir/file.py ")],
)
def test_whitespace_in_filenames_is_preserved(pattern: str, path: str) -> None:
    assert_matches(pattern, path)


def test_non_string_candidate_rejected() -> None:
    with pytest.raises(ValidationError):
        matches(compile_pattern("**"), None)  # type: ignore[arg-type]


def test_matching_is_deterministic() -> None:
    compiled = compile_pattern("src/**/*.py")
    expected = (("src/a.py", True), ("src/x/b.py", True), ("other/c.py", False))
    forward = [(path, matches(compiled, path)) for path, _ in expected]
    backward = [(path, matches(compiled, path)) for path, _ in reversed(expected)]
    assert forward == list(expected)
    assert backward == list(reversed(expected))


# Task 3: repository resolution, enumeration, languages


def make_git_repo(root: Path) -> Path:
    (root / ".git").mkdir(parents=True, exist_ok=True)
    (root / ".git" / "config").write_text("[core]\n")
    return root


def build_fixture(base: Path) -> dict[str, Path]:
    make_git_repo(base)
    (base / "src" / "nested").mkdir(parents=True)
    (base / "src" / "a.py").write_text("print('a')\n")
    (base / "src" / "nested" / "b.py").write_text("print('b')\n")
    (base / "README.md").write_text("# Demo\n")
    (base / "empty.txt").write_text("")
    (base / "big.bin").write_text("01234567890123456789")
    (base / ".env").write_text("K=V\n")
    (base / "data.bin").write_bytes(b"\x00\x01binary")
    outside = base.parent / "outside-secret.txt"
    outside.write_text("outside\n")
    os.symlink(base / "src" / "a.py", base / "link_inside")
    os.symlink(outside, base / "link_escape")
    os.symlink(base / "missing", base / "dangling")
    return {"root": base, "outside": outside}


def snapshot(base: Path) -> dict[str, tuple[int, bytes]]:
    state: dict[str, tuple[int, bytes]] = {}
    for dirpath, _dirnames, filenames in os.walk(base):
        for name in filenames:
            full = Path(dirpath) / name
            if full.is_symlink():
                continue
            state[str(full)] = (full.stat().st_mtime_ns, full.read_bytes())
    return state


def test_resolve_repository_root(tmp_path: Path) -> None:
    root = make_git_repo(tmp_path / "repo")
    resolved = resolve_target(root)
    assert resolved.root.key() == str(root)
    assert resolved.rel_target == ""
    assert resolved.is_git is True


def test_resolve_file_and_subdir_targets(tmp_path: Path) -> None:
    paths = build_fixture(tmp_path / "repo")
    root = paths["root"]
    file_target = resolve_target(root / "src" / "nested" / "b.py")
    assert file_target.root.key() == str(root)
    assert file_target.rel_target == "src/nested/b.py"
    assert file_target.is_git is True
    dir_target = resolve_target(root / "src")
    assert dir_target.rel_target == "src"
    assert dir_target.is_git is True


def test_resolve_unversioned_directory(tmp_path: Path) -> None:
    plain = tmp_path / "plain" / "sub"
    plain.mkdir(parents=True)
    (plain / "a.py").write_text("x = 1\n")
    resolved = resolve_target(plain)
    assert resolved.root.key() == str(plain)
    assert resolved.rel_target == ""
    assert resolved.is_git is False


def test_resolve_nearest_git_root(tmp_path: Path) -> None:
    outer = make_git_repo(tmp_path / "outer")
    inner = make_git_repo(outer / "inner")
    (inner / "a.py").write_text("x = 1\n")
    resolved = resolve_target(inner / "a.py")
    assert resolved.root.key() == str(inner)
    assert resolved.rel_target == "a.py"


def test_resolve_git_file_stops_as_unversioned(tmp_path: Path) -> None:
    outer = make_git_repo(tmp_path / "outer")
    sub = outer / "sub"
    sub.mkdir()
    (sub / ".git").write_text("gitdir: ../.git/worktrees/x\n")
    resolved = resolve_target(sub)
    assert resolved.root.key() == str(sub)
    assert resolved.is_git is False


@pytest.mark.parametrize("bad", ["", "   "])
def test_resolve_blank_target_rejected(bad: str) -> None:
    with pytest.raises(ValidationError):
        resolve_target(bad)


def test_resolve_missing_and_bad_targets_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        resolve_target(tmp_path / "nope")
    with pytest.raises(ValidationError):
        resolve_target(42)  # type: ignore[arg-type]


def test_direct_dangling_symlink_target_is_recorded(tmp_path: Path) -> None:
    paths = build_fixture(tmp_path / "repo")
    resolved = resolve_target(paths["root"] / "dangling")
    assert resolved.rel_target == "dangling"
    assert resolved.root.key() == str(paths["root"])
    result = discover_files(resolved, DiscoveryConfig())
    assert result.files == ()
    assert result.skipped == (SkippedEntry("dangling", SkipReason.SYMLINK),)


def test_direct_dangling_symlink_escaping_root_is_recorded(tmp_path: Path) -> None:
    paths = build_fixture(tmp_path / "repo")
    escape = paths["root"] / "dangling_escape"
    os.symlink(paths["root"].parent / "nowhere", escape)
    resolved = resolve_target(escape)
    assert resolved.rel_target == "dangling_escape"
    result = discover_files(resolved, DiscoveryConfig())
    assert result.files == ()
    assert result.skipped == (SkippedEntry("dangling_escape", SkipReason.SYMLINK_ESCAPE),)


def test_resolved_target_validation() -> None:
    repo = Repository(root="/tmp/repo")
    with pytest.raises(ValidationError):
        ResolvedTarget(root="x", rel_target="", is_git=True)  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        ResolvedTarget(root=repo, rel_target=None, is_git=True)  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        ResolvedTarget(root=repo, rel_target="", is_git="yes")  # type: ignore[arg-type]


def test_discover_default_config(tmp_path: Path) -> None:
    paths = build_fixture(tmp_path / "repo")
    before = snapshot(paths["root"])
    resolved = resolve_target(paths["root"])
    result = discover_files(resolved, DiscoveryConfig())
    assert result.root.key() == str(paths["root"])
    assert result.files == (
        ".env",
        "README.md",
        "big.bin",
        "empty.txt",
        "src/a.py",
        "src/nested/b.py",
    )
    assert result.skipped == (
        SkippedEntry(".git", SkipReason.EXCLUDED),
        SkippedEntry("dangling", SkipReason.SYMLINK),
        SkippedEntry("data.bin", SkipReason.BINARY),
        SkippedEntry("link_escape", SkipReason.SYMLINK_ESCAPE),
        SkippedEntry("link_inside", SkipReason.SYMLINK),
    )
    assert result.is_complete is False
    assert result.coverage_summary() == (
        "6 files, 5 skipped (1 binary, 1 excluded, 2 symlink, 1 symlink_escape)"
    )
    assert snapshot(paths["root"]) == before


def test_discover_file_target_yields_only_that_file(tmp_path: Path) -> None:
    paths = build_fixture(tmp_path / "repo")
    resolved = resolve_target(paths["root"] / "src" / "a.py")
    result = discover_files(resolved, DiscoveryConfig())
    assert result.files == ("src/a.py",)
    assert result.is_complete is True
    assert result.coverage_summary() == "1 file, no skips"


def test_discover_subdir_target_is_scoped(tmp_path: Path) -> None:
    paths = build_fixture(tmp_path / "repo")
    resolved = resolve_target(paths["root"] / "src")
    result = discover_files(resolved, DiscoveryConfig())
    assert result.files == ("src/a.py", "src/nested/b.py")
    assert result.skipped == ()


def test_discover_excluded_dir_target_records_single_entry(tmp_path: Path) -> None:
    paths = build_fixture(tmp_path / "repo")
    resolved = resolve_target(paths["root"] / ".git")
    result = discover_files(resolved, DiscoveryConfig())
    assert result.files == ()
    assert result.skipped == (SkippedEntry(".git", SkipReason.EXCLUDED),)


def test_discover_custom_size_limit(tmp_path: Path) -> None:
    base = tmp_path / "repo"
    base.mkdir()
    (base / "small.txt").write_text("0123456789abcdef")
    (base / "large.txt").write_text("0123456789abcdefg")
    resolved = resolve_target(base)
    result = discover_files(resolved, DiscoveryConfig(exclude=(), max_file_size=16))
    assert result.files == ("small.txt",)
    assert result.skipped == (SkippedEntry("large.txt", SkipReason.TOO_LARGE),)


def test_discover_include_allowlist(tmp_path: Path) -> None:
    paths = build_fixture(tmp_path / "repo")
    resolved = resolve_target(paths["root"])
    config = DiscoveryConfig(include=("src/**",), exclude=())
    result = discover_files(resolved, config)
    assert result.files == ("src/a.py", "src/nested/b.py")
    assert SkippedEntry("README.md", SkipReason.EXCLUDED) in result.skipped


@pytest.mark.skipif(
    os.name != "posix" or (hasattr(os, "geteuid") and os.geteuid() == 0),
    reason="requires POSIX non-root permission semantics",
)
def test_discover_unreadable_paths_are_skipped(tmp_path: Path) -> None:
    base = tmp_path / "repo"
    (base / "sub").mkdir(parents=True)
    (base / "ok.py").write_text("x = 1\n")
    (base / "locked.py").write_text("y = 2\n")
    (base / "sub" / "c.py").write_text("z = 3\n")
    os.chmod(base / "locked.py", 0o000)
    os.chmod(base / "sub", 0o000)
    try:
        result = discover_files(resolve_target(base), DiscoveryConfig(exclude=()))
    finally:
        os.chmod(base / "locked.py", 0o644)
        os.chmod(base / "sub", 0o755)
    assert result.files == ("ok.py",)
    assert SkippedEntry("locked.py", SkipReason.UNREADABLE) in result.skipped
    assert SkippedEntry("sub", SkipReason.UNREADABLE) in result.skipped


def test_discover_empty_directory_is_complete(tmp_path: Path) -> None:
    base = tmp_path / "repo"
    base.mkdir()
    result = discover_files(resolve_target(base), DiscoveryConfig())
    assert result.files == ()
    assert result.is_complete is True
    assert result.coverage_summary() == "0 files, no skips"


def test_discover_rejects_bad_inputs(tmp_path: Path) -> None:
    paths = build_fixture(tmp_path / "repo")
    resolved = resolve_target(paths["root"])
    with pytest.raises(ValidationError):
        discover_files("x", DiscoveryConfig())  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        discover_files(resolved, "x")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        DiscoveryResult(root="x")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        SkippedEntry("", SkipReason.BINARY)
    with pytest.raises(ValidationError):
        SkippedEntry("a.py", "binary")  # type: ignore[arg-type]


def test_discovery_result_sorts_deterministically(tmp_path: Path) -> None:
    repo = Repository(root=str(tmp_path))
    result = DiscoveryResult(
        root=repo,
        files=("b.py", "a.py"),
        skipped=(
            SkippedEntry("z.py", SkipReason.BINARY),
            SkippedEntry("a.py", SkipReason.EXCLUDED),
        ),
    )
    assert result.files == ("a.py", "b.py")
    assert [e.path for e in result.skipped] == ["a.py", "z.py"]


def _populate_ordered_repo(base: Path, order: list[str]) -> None:
    (base / "sub").mkdir(parents=True, exist_ok=True)
    (base / "gen").mkdir(exist_ok=True)
    for name in order:
        if name == "link":
            os.symlink(base / "a.py", base / "link")
        else:
            (base / name).write_text(f"{name}\n")


def test_discovery_is_independent_of_creation_order(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    names = ["b.py", "a.py", "sub/z.py", "sub/a.py", "m.txt", "link", "gen/skip.py"]
    _populate_ordered_repo(first, names)
    _populate_ordered_repo(second, list(reversed(names)))
    config = DiscoveryConfig(exclude=("gen/",))
    first_result = discover_files(resolve_target(first), config)
    second_result = discover_files(resolve_target(second), config)
    assert first_result.files == second_result.files
    assert first_result.skipped == second_result.skipped
    assert first_result.files == ("a.py", "b.py", "m.txt", "sub/a.py", "sub/z.py")
    assert list(first_result.files) == sorted(first_result.files)
    assert [(e.path, e.reason.value) for e in first_result.skipped] == sorted(
        (e.path, e.reason.value) for e in first_result.skipped
    )
    assert first_result.skipped == (
        SkippedEntry("gen", SkipReason.EXCLUDED),
        SkippedEntry("link", SkipReason.SYMLINK),
    )


@pytest.mark.parametrize(
    ("path", "language"),
    [
        ("a.py", "python"),
        ("A.PY", "python"),
        ("a.pyi", "python"),
        ("a.js", "javascript"),
        ("a.tsx", "typescript"),
        ("a.go", "go"),
        ("a.rs", "rust"),
        ("a.md", "markdown"),
        ("a.yml", "yaml"),
        ("src/deep/a.TOML", "toml"),
    ],
)
def test_detect_known_languages(path: str, language: str) -> None:
    assert detect_language(path) == language


@pytest.mark.parametrize("path", ["a.xyz", "Makefile", ".gitignore", "a", "archive.tar.gz", ""])
def test_detect_unknown_languages(path: str) -> None:
    assert detect_language(path) is None


def test_detect_language_rejects_non_string() -> None:
    with pytest.raises(ValidationError):
        detect_language(None)  # type: ignore[arg-type]


def test_direct_file_symlink_target_is_recorded_not_followed(tmp_path: Path) -> None:
    paths = build_fixture(tmp_path / "repo")
    resolved = resolve_target(paths["root"] / "link_inside")
    assert resolved.rel_target == "link_inside"
    assert resolved.root.key() == str(paths["root"])
    result = discover_files(resolved, DiscoveryConfig())
    assert result.files == ()
    assert result.skipped == (SkippedEntry("link_inside", SkipReason.SYMLINK),)


def test_direct_escaping_file_symlink_target_is_recorded(tmp_path: Path) -> None:
    paths = build_fixture(tmp_path / "repo")
    resolved = resolve_target(paths["root"] / "link_escape")
    assert resolved.rel_target == "link_escape"
    result = discover_files(resolved, DiscoveryConfig())
    assert result.files == ()
    assert result.skipped == (SkippedEntry("link_escape", SkipReason.SYMLINK_ESCAPE),)


def test_direct_directory_symlink_targets_are_recorded(tmp_path: Path) -> None:
    paths = build_fixture(tmp_path / "repo")
    inner = paths["root"] / "inner"
    inner.mkdir()
    (inner / "deep.py").write_text("x = 1\n")
    outside_dir = tmp_path / "outer"
    outside_dir.mkdir()
    (outside_dir / "o.py").write_text("y = 2\n")
    os.symlink(inner, paths["root"] / "dir_inside")
    os.symlink(outside_dir, paths["root"] / "dir_escape")
    for name, reason in (
        ("dir_inside", SkipReason.SYMLINK),
        ("dir_escape", SkipReason.SYMLINK_ESCAPE),
    ):
        resolved = resolve_target(paths["root"] / name)
        assert resolved.rel_target == name
        result = discover_files(resolved, DiscoveryConfig())
        assert result.files == ()
        assert result.skipped == (SkippedEntry(name, reason),)
