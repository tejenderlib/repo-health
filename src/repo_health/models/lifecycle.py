"""Finding lifecycle classification contract (Phase 6, step 1).

Lifecycle states follow docs/rules.md section 8. A classification always
carries its evidence basis (the compared run ids and a deterministic
reason), so history is traceable to actual observations and never
invented.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from repo_health.core.exceptions import ValidationError
from repo_health.models.finding import IDENTITY_RE, validate_identifier


class Lifecycle(StrEnum):
    """Lifecycle classification of one finding across two observations."""

    # Observed now; comparable baseline evidence shows prior absence.
    NEW = "new"
    # Observed now and already present in compatible history.
    RECURRING = "recurring"
    # Previously observed; current evidence establishes absence.
    RESOLVED = "resolved"
    # Observed again after an evidenced occurrence and resolution.
    REAPPEARED = "reappeared"
    # Available evidence cannot support another classification.
    INDETERMINATE = "indeterminate"


@dataclass(frozen=True)
class FindingLifecycle:
    """The lifecycle classification of one finding."""

    finding_id: str
    analyzer: str
    lifecycle: Lifecycle
    reason: str
    baseline_run_id: int | None = None
    current_run_id: int | None = None

    def __post_init__(self) -> None:
        finding_id = self.finding_id.strip()
        if IDENTITY_RE.fullmatch(finding_id) is None:
            raise ValidationError(
                f"finding_id must match {IDENTITY_RE.pattern}, "
                f"got {self.finding_id!r}"
            )
        analyzer = validate_identifier("analyzer", self.analyzer)
        if not isinstance(self.lifecycle, Lifecycle):
            raise ValidationError(
                "lifecycle must be a Lifecycle member, "
                f"got {self.lifecycle!r}"
            )
        if self.reason.strip() == "":
            raise ValidationError("reason must not be blank")
        for kind, value in (
            ("baseline_run_id", self.baseline_run_id),
            ("current_run_id", self.current_run_id),
        ):
            if value is not None and (not isinstance(value, int) or value < 1):
                raise ValidationError(f"{kind} must be a positive run id or None")
        object.__setattr__(self, "finding_id", finding_id)
        object.__setattr__(self, "analyzer", analyzer)

    def sort_key(self) -> tuple[str, str]:
        """Stable deterministic ordering key."""
        return (self.finding_id, self.analyzer)
