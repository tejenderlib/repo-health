"""Analysis-run model (Stage 2 contract).

An analysis run records one execution of the analysis engine against a
repository. Detailed results live in the analyzer-result and observation
records; the run itself carries identity, timing metadata, and overall
status. Timestamps are metadata only and never affect finding identity.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from repo_health.core.exceptions import ValidationError


class RunStatus(StrEnum):
    """Overall status of an analysis run."""

    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"


@dataclass(frozen=True)
class AnalysisRun:
    """One persisted analysis execution. ``id`` is None until stored."""

    repository_key: str = ""
    created_at: str = ""
    status: RunStatus = RunStatus.COMPLETED
    notes: str = ""
    id: int | None = None

    def __post_init__(self) -> None:
        if self.repository_key.strip() == "":
            raise ValidationError("repository_key must not be blank")
        if not isinstance(self.status, RunStatus):
            raise ValidationError(
                f"status must be a RunStatus member, got {self.status!r}"
            )
        if self.id is not None and self.id < 1:
            raise ValidationError(f"run id must be positive, got {self.id!r}")
        object.__setattr__(self, "repository_key", self.repository_key.strip())
        object.__setattr__(self, "notes", self.notes.strip())

    def to_dict(self) -> dict[str, str]:
        """Serialize with fixed key order for stable output."""
        return {
            "id": "" if self.id is None else str(self.id),
            "repository_key": self.repository_key,
            "created_at": self.created_at,
            "status": self.status.value,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, str]) -> AnalysisRun:
        """Deserialize, raising ValidationError on missing or invalid fields."""
        try:
            raw_id = str(data["id"]).strip()
            return cls(
                id=None if raw_id == "" else int(raw_id),
                repository_key=str(data["repository_key"]),
                created_at=str(data["created_at"]),
                status=RunStatus(str(data["status"])),
                notes=str(data["notes"]),
            )
        except KeyError as exc:
            raise ValidationError(f"run field missing: {exc}") from exc
        except ValueError as exc:
            raise ValidationError(f"invalid run data: {exc}") from exc
