"""Deterministic file enumeration (Stage 3, Task 3).

Walks a resolved target with ``os.scandir`` and explicit sorting, producing
repository-relative POSIX paths. Includes restrict, exclusions override,
and every skipped path is recorded with a reason so downstream stages can
never mistake partial coverage for complete coverage.

Safety rules: symlinks are never followed (every symlink is recorded,
with boundary escapes distinguished); files larger than the configured
maximum are skipped without being read; binary detection reads at most
the first 8192 bytes; unreadable files and directories are recorded
rather than aborting the walk. Targets are only inspected, never modified.

Trailing-``/`` configuration patterns apply to directories only: a file
that merely shares a directory's name is not excluded by that pattern.
An explicitly requested scope root is evaluated by the normal rules, but
its ancestors' exclusions are never consulted.
"""

from __future__ import annotations

import os
import stat
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from repo_health.config import DiscoveryConfig
from repo_health.core.exceptions import ValidationError
from repo_health.discovery.patterns import matches
from repo_health.discovery.repository import ResolvedTarget
from repo_health.models.repository import Repository

_BINARY_PROBE_SIZE = 8192


class SkipReason(StrEnum):
    """Why a path was excluded from discovery."""

    EXCLUDED = "excluded"
    TOO_LARGE = "too_large"
    UNREADABLE = "unreadable"
    SYMLINK = "symlink"
    SYMLINK_ESCAPE = "symlink_escape"
    BINARY = "binary"
    OUTSIDE_BOUNDARY = "outside_boundary"


@dataclass(frozen=True)
class SkippedEntry:
    """A path omitted from discovery and the reason why."""

    path: str
    reason: SkipReason

    def __post_init__(self) -> None:
        if not isinstance(self.path, str) or self.path == "":
            raise ValidationError(f"skipped path must be non-empty, got {self.path!r}")
        if not isinstance(self.reason, SkipReason):
            raise ValidationError(f"reason must be a SkipReason member, got {self.reason!r}")


@dataclass(frozen=True)
class DiscoveryResult:
    """The outcome of enumerating one resolved target."""

    root: Repository
    files: tuple[str, ...] = ()
    skipped: tuple[SkippedEntry, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.root, Repository):
            raise ValidationError(f"root must be a Repository, got {self.root!r}")
        for path in self.files:
            if not isinstance(path, str) or path == "":
                raise ValidationError(f"file path must be non-empty, got {path!r}")
        for entry in self.skipped:
            if not isinstance(entry, SkippedEntry):
                raise ValidationError(f"skipped must contain SkippedEntry items, got {entry!r}")
        object.__setattr__(self, "files", tuple(sorted(self.files)))
        object.__setattr__(
            self,
            "skipped",
            tuple(sorted(self.skipped, key=lambda e: (e.path, e.reason.value))),
        )

    @property
    def is_complete(self) -> bool:
        """True only when nothing was skipped."""
        return len(self.skipped) == 0

    def coverage_summary(self) -> str:
        """Deterministic human-readable coverage accounting."""
        counts: dict[str, int] = {}
        for entry in self.skipped:
            counts[entry.reason.value] = counts.get(entry.reason.value, 0) + 1
        file_word = "file" if len(self.files) == 1 else "files"
        if not counts:
            return f"{len(self.files)} {file_word}, no skips"
        breakdown = ", ".join(f"{counts[reason]} {reason}" for reason in sorted(counts))
        return f"{len(self.files)} {file_word}, {len(self.skipped)} skipped ({breakdown})"


def _is_dir_only_pattern(raw: str) -> bool:
    """Mirror the Task 1 trailing-slash directory-pattern rule."""
    cleaned = raw.strip().replace("\\", "/")
    return cleaned.endswith("/") and cleaned.rstrip("/") not in ("", ".")


def _is_within(path: str, root: str) -> bool:
    """Return True when absolute ``path`` stays inside absolute ``root``."""
    try:
        return os.path.commonpath((root, path)) == root
    except ValueError:
        return False


def coverage_gaps(
    skipped: tuple[SkippedEntry, ...],
    file_matches: Callable[[str], bool],
    check: str,
) -> tuple[str, ...]:
    """Describe skipped paths that could hide evidence for one check.

    Excluded paths are never relevant: the user explicitly removed them
    from coverage (see docs/configuration.md section 5). Oversized and
    binary skips are files with known paths, so only matching paths count.
    All other skips (unreadable, symlinks, boundary escapes) may hide
    whole directories, so they always count — erring toward uncertainty
    per docs/rules.md section 2.3. Descriptions name paths and reasons
    only, never file content.
    """
    gaps: list[str] = []
    for entry in skipped:
        if entry.reason is SkipReason.EXCLUDED:
            continue
        if entry.reason in (SkipReason.TOO_LARGE, SkipReason.BINARY):
            if not file_matches(entry.path):
                continue
        gaps.append(f"{entry.path}: {entry.reason.value}; {check} unevaluated")
    return tuple(sorted(gaps))


class _Walker:
    """Single discovery walk accumulating files and skips."""

    def __init__(
        self,
        root: str,
        config: DiscoveryConfig,
        dir_only_excludes: set[str],
    ) -> None:
        self._root = root
        self._config = config
        self._dir_only_excludes = dir_only_excludes
        self.files: list[str] = []
        self.skipped: list[SkippedEntry] = []

    def _excluded_file(self, rel: str) -> bool:
        return any(
            pattern.source not in self._dir_only_excludes and matches(pattern, rel)
            for pattern in self._config.compiled_exclude
        )

    def _dir_pruned(self, rel: str) -> bool:
        return any(
            pattern.source in self._dir_only_excludes and matches(pattern, rel)
            for pattern in self._config.compiled_exclude
        )

    def _included_file(self, rel: str) -> bool:
        if not self._config.compiled_include:
            return True
        return any(matches(pattern, rel) for pattern in self._config.compiled_include)

    def add_file(self, absolute: str, rel: str) -> None:
        """Evaluate one regular file against the file rules."""
        if self._excluded_file(rel):
            self.skipped.append(SkippedEntry(rel, SkipReason.EXCLUDED))
            return
        if not self._included_file(rel):
            self.skipped.append(SkippedEntry(rel, SkipReason.EXCLUDED))
            return
        try:
            size = os.lstat(absolute).st_size
        except OSError:
            self.skipped.append(SkippedEntry(rel, SkipReason.UNREADABLE))
            return
        if size > self._config.max_file_size:
            self.skipped.append(SkippedEntry(rel, SkipReason.TOO_LARGE))
            return
        try:
            with open(absolute, "rb") as handle:
                probe = handle.read(_BINARY_PROBE_SIZE)
        except OSError:
            self.skipped.append(SkippedEntry(rel, SkipReason.UNREADABLE))
            return
        if b"\x00" in probe:
            self.skipped.append(SkippedEntry(rel, SkipReason.BINARY))
            return
        self.files.append(rel)

    def add_symlink(self, absolute: str, rel: str) -> None:
        """Record a symlink without following it."""
        if _is_within(os.path.realpath(absolute), self._root):
            reason = SkipReason.SYMLINK
        else:
            reason = SkipReason.SYMLINK_ESCAPE
        self.skipped.append(SkippedEntry(rel, reason))

    def walk(self, dir_abs: str, rel_dir: str) -> None:
        """Recursively enumerate one directory; unreadable dirs are skipped."""
        try:
            with os.scandir(dir_abs) as iterator:
                entries = sorted(iterator, key=lambda entry: entry.name)
        except OSError:
            self.skipped.append(SkippedEntry(rel_dir if rel_dir else ".", SkipReason.UNREADABLE))
            return
        for entry in entries:
            rel = f"{rel_dir}/{entry.name}" if rel_dir else entry.name
            try:
                is_link = entry.is_symlink()
            except OSError:
                self.skipped.append(SkippedEntry(rel, SkipReason.UNREADABLE))
                continue
            if is_link:
                self.add_symlink(entry.path, rel)
                continue
            try:
                is_dir = entry.is_dir(follow_symlinks=False)
            except OSError:
                self.skipped.append(SkippedEntry(rel, SkipReason.UNREADABLE))
                continue
            if is_dir:
                if self._dir_pruned(rel):
                    self.skipped.append(SkippedEntry(rel, SkipReason.EXCLUDED))
                else:
                    self.walk(entry.path, rel)
                continue
            try:
                is_file = entry.is_file(follow_symlinks=False)
            except OSError:
                self.skipped.append(SkippedEntry(rel, SkipReason.UNREADABLE))
                continue
            if is_file:
                self.add_file(entry.path, rel)
            else:
                # Fifos, sockets, and devices are never opened.
                self.skipped.append(SkippedEntry(rel, SkipReason.UNREADABLE))


def discover_files(resolved: ResolvedTarget, config: DiscoveryConfig) -> DiscoveryResult:
    """Enumerate the resolved target's files per ``config``.

    A file target yields only that file; a directory target yields only
    that directory and its descendants. The scope root itself follows the
    normal rules, but its ancestors' exclusions are never consulted.
    """
    if not isinstance(resolved, ResolvedTarget):
        raise ValidationError(f"resolved must be a ResolvedTarget, got {resolved!r}")
    if not isinstance(config, DiscoveryConfig):
        raise ValidationError(f"config must be a DiscoveryConfig, got {config!r}")
    root = resolved.root.root
    dir_only_excludes = {
        compiled.source
        for compiled, raw in zip(config.compiled_exclude, config.exclude, strict=True)
        if _is_dir_only_pattern(raw)
    }
    walker = _Walker(root, config, dir_only_excludes)
    if resolved.rel_target == "":
        walker.walk(root, "")
        return DiscoveryResult(
            root=resolved.root, files=tuple(walker.files), skipped=tuple(walker.skipped)
        )
    target_abs = os.path.join(root, *resolved.rel_target.split("/"))
    try:
        mode = os.lstat(target_abs).st_mode
    except OSError as exc:
        raise ValidationError(
            f"target is no longer available: {resolved.rel_target!r} ({exc})"
        ) from exc
    if stat.S_ISLNK(mode):
        walker.add_symlink(target_abs, resolved.rel_target)
    elif not _is_within(os.path.realpath(target_abs), root):
        walker.skipped.append(SkippedEntry(resolved.rel_target, SkipReason.OUTSIDE_BOUNDARY))
    elif stat.S_ISDIR(mode):
        if walker._dir_pruned(resolved.rel_target):
            walker.skipped.append(SkippedEntry(resolved.rel_target, SkipReason.EXCLUDED))
        else:
            walker.walk(target_abs, resolved.rel_target)
    elif stat.S_ISREG(mode):
        walker.add_file(target_abs, resolved.rel_target)
    else:
        # Fifos, sockets, and devices are never opened.
        walker.skipped.append(SkippedEntry(resolved.rel_target, SkipReason.UNREADABLE))
    return DiscoveryResult(
        root=resolved.root, files=tuple(walker.files), skipped=tuple(walker.skipped)
    )
