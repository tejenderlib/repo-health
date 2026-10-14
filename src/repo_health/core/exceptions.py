"""Application-specific exceptions.

Errors must remain distinguishable from successful analysis with zero
findings (see docs/architecture.md section 4.3).
"""

from __future__ import annotations


class RepoHealthError(Exception):
    """Base class for all expected Repo Health errors."""


class ValidationError(RepoHealthError, ValueError):
    """Raised when a model invariant or input contract is violated."""
