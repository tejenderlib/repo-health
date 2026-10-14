"""Explicit analysis-run context (Stage 4 contract).

Bundles everything one analysis run needs: the resolved target, the
discovery outcome, and the validated configuration. It carries no mutable
global state and performs no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass

from repo_health.config import DiscoveryConfig
from repo_health.core.exceptions import ValidationError
from repo_health.discovery.files import DiscoveryResult
from repo_health.discovery.repository import ResolvedTarget


@dataclass(frozen=True)
class AnalysisContext:
    """Immutable inputs for a single analysis run."""

    target: ResolvedTarget
    discovery: DiscoveryResult
    config: DiscoveryConfig

    def __post_init__(self) -> None:
        if not isinstance(self.target, ResolvedTarget):
            raise ValidationError(
                f"target must be a ResolvedTarget, got {self.target!r}"
            )
        if not isinstance(self.discovery, DiscoveryResult):
            raise ValidationError(
                f"discovery must be a DiscoveryResult, got {self.discovery!r}"
            )
        if not isinstance(self.config, DiscoveryConfig):
            raise ValidationError(
                f"config must be a DiscoveryConfig, got {self.config!r}"
            )
        if self.discovery.root.key() != self.target.root.key():
            raise ValidationError(
                "discovery root does not match the resolved target root"
            )
