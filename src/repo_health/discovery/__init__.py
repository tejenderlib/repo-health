"""Repository and file discovery (Stage 3; Tasks 1 and 3 implemented)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from repo_health.discovery.patterns import CompiledPattern, compile_pattern, matches

if TYPE_CHECKING:
    from repo_health.discovery.files import (
        DiscoveryResult,
        SkippedEntry,
        SkipReason,
        discover_files,
    )
    from repo_health.discovery.languages import EXTENSION_MAP, detect_language
    from repo_health.discovery.repository import ResolvedTarget, resolve_target

__all__ = [
    "CompiledPattern",
    "DiscoveryResult",
    "EXTENSION_MAP",
    "ResolvedTarget",
    "SkipReason",
    "SkippedEntry",
    "compile_pattern",
    "detect_language",
    "discover_files",
    "matches",
    "resolve_target",
]

_LAZY_SUBMODULES = {
    "DiscoveryResult": ".files",
    "SkipReason": ".files",
    "SkippedEntry": ".files",
    "discover_files": ".files",
    "EXTENSION_MAP": ".languages",
    "detect_language": ".languages",
    "ResolvedTarget": ".repository",
    "resolve_target": ".repository",
}


def __getattr__(name: str) -> object:
    """Expose submodules lazily to avoid a config/discovery import cycle.

    ``config`` precompiles patterns (importing ``discovery.patterns``),
    while ``discovery.files`` consumes ``DiscoveryConfig``; importing the
    heavier submodules eagerly at package init would close that loop.
    """
    import importlib

    try:
        submodule = _LAZY_SUBMODULES[name]
    except KeyError:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from None
    return getattr(importlib.import_module(submodule, __name__), name)
