"""Glob-pattern engine for file discovery (Stage 3, Task 1).

Patterns match repository-relative POSIX paths with explicitly defined,
standard-library-only semantics:

* ``*`` matches any sequence of characters except ``/``.
* ``?`` matches exactly one character except ``/``.
* ``**`` as a full path segment matches zero or more path segments, so
  ``a/**`` matches ``a`` itself and everything below it, and ``**/x``
  matches ``x`` at any depth including the root.
* All other characters (including ``.``, ``[``, ``]``, ``+``) are literal.
* Matching is case-sensitive.

Normalization applied at compile time: surrounding whitespace is stripped,
backslashes become ``/``, a leading ``./`` is removed, duplicate ``/``
separators collapse, adjacent ``**`` segments merge, and a trailing ``/``
marks a directory pattern equivalent to appending ``/**``.

Rejected with :class:`ValidationError`: blank patterns, absolute patterns
(leading ``/`` or drive-qualified), and patterns containing ``..`` segments.
Matching a candidate is a pure predicate: absolute candidates never match.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from repo_health.core.exceptions import ValidationError

_ABSOLUTE_DRIVE_RE = re.compile(r"^[A-Za-z]:")


def _translate_segment(segment: str) -> str:
    """Translate one non-``**`` segment to a regex fragment."""
    parts: list[str] = []
    for char in segment:
        if char == "*":
            parts.append("[^/]*")
        elif char == "?":
            parts.append("[^/]")
        else:
            parts.append(re.escape(char))
    return "".join(parts)


def _to_regex_body(parts: list[str]) -> str:
    """Join translated segments, giving ``**`` its multi-segment meaning."""
    out: list[str] = []
    separator = "/"
    total = len(parts)
    for index, part in enumerate(parts):
        first = index == 0
        last = index == total - 1
        if part == "**":
            if first and last:
                out.append(".*")
            elif first:
                out.append("(?:.*/)?")
                separator = ""
            elif last:
                out.append("(?:/.*)?")
            else:
                out.append("(?:/.*)?")
                separator = "/"
        else:
            if out:
                out.append(separator)
            out.append(_translate_segment(part))
            separator = "/"
    return "".join(out)


def _normalize(raw: str) -> str:
    cleaned = raw.strip().replace("\\", "/")
    while cleaned.startswith("./"):
        cleaned = cleaned[2:]
    while "//" in cleaned:
        cleaned = cleaned.replace("//", "/")
    is_dir = cleaned.endswith("/") and len(cleaned) > 1
    cleaned = cleaned.rstrip("/")
    if cleaned == "" or cleaned == ".":
        raise ValidationError(f"pattern must not be blank: {raw!r}")
    if cleaned.startswith("/") or _ABSOLUTE_DRIVE_RE.match(cleaned) is not None:
        raise ValidationError(f"pattern must be repo-relative: {raw!r}")
    segments = [segment for segment in cleaned.split("/") if segment != ""]
    if any(segment == ".." for segment in segments):
        raise ValidationError(f"pattern must not escape the root: {raw!r}")
    if is_dir:
        segments.append("**")
    squeezed: list[str] = []
    for segment in segments:
        if segment == "**" and squeezed and squeezed[-1] == "**":
            continue
        squeezed.append(segment)
    return "/".join(squeezed)


@dataclass(frozen=True)
class CompiledPattern:
    """A validated, normalized glob pattern ready for matching."""

    source: str
    regex: re.Pattern[str] = field(compare=False, repr=False)


def compile_pattern(raw: str) -> CompiledPattern:
    """Validate and compile ``raw``; raise ValidationError if invalid."""
    if not isinstance(raw, str):
        raise ValidationError(f"pattern must be a string, got {raw!r}")
    normalized = _normalize(raw)
    return CompiledPattern(
        source=normalized, regex=re.compile(_to_regex_body(normalized.split("/")))
    )


def _normalize_candidate(path: str) -> str | None:
    """Normalize a candidate path; return None when it can never match.

    Surrounding whitespace is preserved: filenames may legitimately begin
    or end with spaces. Candidates containing a complete ``..`` segment or
    equal to ``.`` are rejected because repository-relative discovery paths
    never take those forms.
    """
    if not isinstance(path, str):
        raise ValidationError(f"path must be a string, got {path!r}")
    cleaned = path.replace("\\", "/")
    while cleaned.startswith("./"):
        cleaned = cleaned[2:]
    while "//" in cleaned:
        cleaned = cleaned.replace("//", "/")
    if (
        cleaned == ""
        or cleaned == "."
        or cleaned.startswith("/")
        or _ABSOLUTE_DRIVE_RE.match(cleaned) is not None
        or any(segment == ".." for segment in cleaned.split("/"))
    ):
        return None
    return cleaned


def matches(compiled: CompiledPattern, rel_posix_path: str) -> bool:
    """Return True when the repo-relative path matches the pattern."""
    candidate = _normalize_candidate(rel_posix_path)
    if candidate is None:
        return False
    return compiled.regex.fullmatch(candidate) is not None
