"""Repository-root resolution (Stage 3, Task 3).

Resolves repository roots, directory targets, and file targets to a
validated root plus a repository-relative target. A directory containing
a real ``.git`` subdirectory marks a Git repository boundary; any other
``.git`` entry (file, symlink) stops the upward search and marks the
current directory as an unversioned root without consulting worktree or
submodule metadata (documented limitation: worktree and submodule
checkouts are treated as unversioned). Directories without any ``.git``
marker are valid unversioned targets.

Only standard-library calls are used, and targets are only inspected,
never modified.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from repo_health.core.exceptions import ValidationError
from repo_health.models.repository import Repository


@dataclass(frozen=True)
class ResolvedTarget:
    """A validated analysis target: root, relative target, Git status."""

    root: Repository
    rel_target: str
    is_git: bool

    def __post_init__(self) -> None:
        if not isinstance(self.root, Repository):
            raise ValidationError(f"root must be a Repository, got {self.root!r}")
        if not isinstance(self.rel_target, str):
            raise ValidationError(f"rel_target must be a string, got {self.rel_target!r}")
        if not isinstance(self.is_git, bool):
            raise ValidationError(f"is_git must be a boolean, got {self.is_git!r}")


def _git_marker(directory: str) -> str:
    """Classify the ``.git`` entry: ``dir``, ``other``, or ``absent``."""
    marker = os.path.join(directory, ".git")
    if not os.path.lexists(marker):
        return "absent"
    if os.path.isdir(marker) and not os.path.islink(marker):
        return "dir"
    return "other"


def _find_root(start: str) -> tuple[str, bool]:
    """Walk up to the nearest valid ``.git`` directory.

    Any other ``.git`` entry stops the search: the current directory
    becomes an unversioned root. Directories without a marker resolve to
    themselves as unversioned roots.
    """
    current = start
    while True:
        marker = _git_marker(current)
        if marker == "dir":
            return current, True
        if marker == "other":
            return current, False
        parent = os.path.dirname(current)
        if parent == current:
            return start, False
        current = parent


def _resolve_link(absolute: str) -> ResolvedTarget:
    """Resolve a directly passed symlink without following it.

    Only the parent directory is normalized; the link name itself becomes
    the repository-relative target so enumeration records the symlink.
    """
    parent = os.path.realpath(os.path.dirname(absolute))
    root, is_git = _find_root(parent)
    rel_parent = "" if parent == root else _to_posix(os.path.relpath(parent, root))
    name = os.path.basename(absolute)
    rel = name if rel_parent == "" else f"{rel_parent}/{name}"
    return ResolvedTarget(root=Repository(root=root), rel_target=rel, is_git=is_git)


def _to_posix(path: str) -> str:
    return path.replace(os.sep, "/")


def resolve_target(path: str | Path) -> ResolvedTarget:
    """Resolve a repository root, directory, or file target.

    Returns the enclosing root (nearest valid ``.git`` directory, else the
    target directory itself as unversioned) with the target expressed as a
    repository-relative POSIX path (``""`` for whole-root targets).
    Missing, blank, or non-file/non-directory targets raise
    :class:`ValidationError`. A symlink passed directly is never followed:
    it resolves to its own repository-relative path so that enumeration
    records it as a symlink skip — including dangling links, whose
    lexical destination decides inside vs escape classification.
    """
    if isinstance(path, Path):
        raw: object = os.fspath(path)
    else:
        raw = path
    if not isinstance(raw, str):
        raise ValidationError(f"target must be a path string, got {path!r}")
    if raw.strip() == "":
        raise ValidationError("target must not be blank")
    expanded = os.path.expanduser(raw)
    if not os.path.lexists(expanded):
        raise ValidationError(f"target does not exist: {raw!r}")
    if os.path.islink(expanded):
        return _resolve_link(os.path.abspath(expanded))
    absolute = os.path.realpath(expanded)
    if os.path.isfile(absolute):
        start = os.path.dirname(absolute)
        root, is_git = _find_root(start)
        rel = _to_posix(os.path.relpath(absolute, root))
        return ResolvedTarget(root=Repository(root=root), rel_target=rel, is_git=is_git)
    if os.path.isdir(absolute):
        root, is_git = _find_root(absolute)
        rel = "" if absolute == root else _to_posix(os.path.relpath(absolute, root))
        return ResolvedTarget(root=Repository(root=root), rel_target=rel, is_git=is_git)
    raise ValidationError(f"target is not a file or directory: {raw!r}")
