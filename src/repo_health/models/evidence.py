"""Evidence-state representation (Stage 1 contract).

This module defines the Python representation of the KNOWN / UNKNOWN /
UNAVAILABLE semantic states required by docs/rules.md section 3.

Schema-v3 note: the previously established schema v3 definition is
currently unavailable, so no schema-v3 compatibility is claimed.
Persisted formats will be defined as a new memory schema in Stage 2.
"""

from __future__ import annotations

from enum import StrEnum


class EvidenceState(StrEnum):
    """Machine representation of an evidence state.

    Members serialize to their lowercase value for stable JSON output.
    """

    # Sufficient evidence is available to establish the relevant fact.
    KNOWN = "known"
    # Available information does not establish the relevant fact.
    UNKNOWN = "unknown"
    # Required evidence could not be obtained or evaluated.
    UNAVAILABLE = "unavailable"


def is_established(state: EvidenceState) -> bool:
    """Return True only when the fact is established (KNOWN).

    UNKNOWN and UNAVAILABLE must never be treated as KNOWN.
    """
    return state is EvidenceState.KNOWN
