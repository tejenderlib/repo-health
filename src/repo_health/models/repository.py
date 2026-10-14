"""Repository identity and metadata (Stage 1 contract).

Stage 1 scope: identity representation and validation only. Persistence
and cross-checkout repository matching are Stage 2 concerns. The v1
repository key is the normalized absolute root; whether checkouts of the
same remote share one record is unresolved and will be decided in Stage 2.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from repo_health.core.exceptions import ValidationError


@dataclass(frozen=True)
class Repository:
    """Identifies the repository under analysis."""

    root: str = ""
    name: str = ""
    remote: str | None = None
    revision: str | None = None

    def __post_init__(self) -> None:
        if self.root.strip() == "":
            raise ValidationError("repository root must not be blank")
        normalized = os.path.normpath(os.path.expanduser(self.root.strip()))
        if not os.path.isabs(normalized):
            raise ValidationError(
                f"repository root must be absolute, got {self.root!r}"
            )
        name = self.name.strip() or os.path.basename(normalized) or "repository"
        object.__setattr__(self, "root", normalized)
        object.__setattr__(self, "name", name)
        if self.remote is not None:
            object.__setattr__(self, "remote", self.remote.strip() or None)
        if self.revision is not None:
            object.__setattr__(self, "revision", self.revision.strip() or None)

    def key(self) -> str:
        """Stable v1 repository key: the normalized absolute root."""
        return self.root
