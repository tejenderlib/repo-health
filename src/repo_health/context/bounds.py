"""Context-package size bounds (Phase 7, step 1)."""

from __future__ import annotations

from dataclasses import dataclass

from repo_health.core.exceptions import ValidationError

DEFAULT_MAX_FINDINGS = 50
DEFAULT_MAX_EVIDENCE_CHARS = 200
TRUNCATION_MARKER = "...[truncated]"


@dataclass(frozen=True)
class ContextBounds:
    """Validated limits for one context export."""

    max_findings: int = DEFAULT_MAX_FINDINGS
    max_evidence_chars: int = DEFAULT_MAX_EVIDENCE_CHARS

    def __post_init__(self) -> None:
        for kind in ("max_findings", "max_evidence_chars"):
            value = getattr(self, kind)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValidationError(f"{kind} must be a positive integer, got {value!r}")


def truncate_text(text: str, limit: int) -> tuple[str, int]:
    """Truncate to ``limit`` chars at a word boundary.

    Returns the (possibly truncated) text and the omitted character count,
    excluding the appended marker. Short inputs pass through untouched.
    """
    if len(text) <= limit:
        return text, 0
    cut = text[:limit]
    boundary = cut.rfind(" ")
    kept = cut[:boundary] if boundary > 0 else cut
    return kept + TRUNCATION_MARKER, len(text) - len(kept)
