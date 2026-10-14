"""Stage 3, Task 1 tests: glob-pattern engine semantics."""

from __future__ import annotations

import pytest

from repo_health.core.exceptions import ValidationError
from repo_health.discovery import CompiledPattern, compile_pattern, matches


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
