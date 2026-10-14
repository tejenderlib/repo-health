"""Discovery configuration (Stage 3, Task 2).

Defines the validated, explicit defaults controlling which files file
discovery examines. No configuration-file parser is implemented: only
built-in defaults and explicit in-code overrides exist (see
`docs/configuration.md`).

Pattern semantics come from the Task 1 engine
(`discovery.patterns`): matching is case-sensitive against
repository-relative POSIX paths. A directory pattern ending in ``/``
(e.g. ``.env/``) compiles to ``<dir>/**`` and therefore excludes the
directory and everything under it — but never a file that merely shares
the name (a file named ``.env`` is not excluded by ``.env/``). Patterns
without ``**`` match at a single level only: ``*.pyc`` excludes
root-level ``*.pyc`` files, not nested ones.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from repo_health.core.exceptions import ValidationError
from repo_health.discovery.patterns import CompiledPattern, compile_pattern

DEFAULT_EXCLUDES: tuple[str, ...] = (
    ".git/",
    "__pycache__/",
    "*.pyc",
    "venv/",
    ".venv/",
    "env/",
    ".env/",
    "node_modules/",
)

DEFAULT_MAX_FILE_SIZE = 1_048_576


def _require_pattern_tuple(kind: str, value: tuple[str, ...]) -> tuple[str, ...]:
    if isinstance(value, str) or not isinstance(value, tuple):
        raise ValidationError(
            f"{kind} must be a tuple of pattern strings, got {value!r}"
        )
    for item in value:
        if not isinstance(item, str):
            raise ValidationError(
                f"{kind} must contain only pattern strings, got {item!r}"
            )
    return value


def _require_size(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValidationError(
            "max_file_size must be a positive integer of bytes, "
            f"got {value!r}"
        )
    return value


@dataclass(frozen=True)
class DiscoveryConfig:
    """Validated file-discovery settings.

    ``include`` restricts eligible files when non-empty (empty means all
    eligible files); ``exclude`` overrides ``include``. Both are compiled
    with the Task 1 pattern engine at construction, so invalid patterns
    fail here rather than during discovery.
    """

    include: tuple[str, ...] = ()
    exclude: tuple[str, ...] = DEFAULT_EXCLUDES
    max_file_size: int = DEFAULT_MAX_FILE_SIZE
    follow_symlinks: bool = False
    compiled_include: tuple[CompiledPattern, ...] = field(default=(), repr=False)
    compiled_exclude: tuple[CompiledPattern, ...] = field(default=(), repr=False)

    def __post_init__(self) -> None:
        include = _require_pattern_tuple("include", self.include)
        exclude = _require_pattern_tuple("exclude", self.exclude)
        max_file_size = _require_size(self.max_file_size)
        if not isinstance(self.follow_symlinks, bool):
            raise ValidationError(
                "follow_symlinks must be a boolean, "
                f"got {self.follow_symlinks!r}"
            )
        if self.follow_symlinks:
            raise ValidationError(
                "follow_symlinks=True is unsupported in v1: "
                "symlinks are never followed"
            )
        object.__setattr__(self, "include", include)
        object.__setattr__(self, "exclude", exclude)
        object.__setattr__(self, "max_file_size", max_file_size)
        object.__setattr__(
            self, "compiled_include", tuple(compile_pattern(p) for p in include)
        )
        object.__setattr__(
            self, "compiled_exclude", tuple(compile_pattern(p) for p in exclude)
        )
