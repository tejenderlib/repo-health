"""Deterministic analysis engine (Stage 4 contract).

Runs discovery, then invokes each selected analyzer independently against
the shared context. Analyzers run in the requested order (registry order
by default). An analyzer that raises, returns a non-result, or returns a
result for the wrong analyzer becomes a FAILED result with preserved
failure information — never an empty success, and never a skipped peer.
Target and configuration errors surface as :class:`ValidationError`
before any analyzer runs.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from repo_health.analyzers import ANALYZERS, AnalyzerFunction
from repo_health.config import DiscoveryConfig
from repo_health.core.context import AnalysisContext
from repo_health.core.exceptions import ValidationError
from repo_health.discovery.files import discover_files
from repo_health.discovery.repository import resolve_target
from repo_health.models.analyzer_result import AnalyzerResult, AnalyzerStatus


def _resolve_table(
    registry: Mapping[str, AnalyzerFunction] | None,
) -> dict[str, AnalyzerFunction]:
    if registry is None:
        return dict(ANALYZERS)
    return dict(registry)


def _resolve_names(
    analyzers: tuple[str, ...] | None, table: Mapping[str, AnalyzerFunction]
) -> tuple[str, ...]:
    if analyzers is None:
        return tuple(table)
    if isinstance(analyzers, str) or not isinstance(analyzers, tuple):
        raise ValidationError(
            f"analyzers must be a tuple of names, got {analyzers!r}"
        )
    valid = sorted(table)
    for name in analyzers:
        if not isinstance(name, str) or name not in table:
            raise ValidationError(
                f"unknown analyzer {name!r}; valid names: {', '.join(valid)}"
            )
    return analyzers


def _display_name(name: str, index: int) -> str:
    """Return the persisted name for a requested analyzer.

    Documented registry names are safe to persist. Anything else is
    untrusted caller input that may carry arbitrary content, so custom
    analyzers get a positional alias. The alias is always a valid
    identifier, which additionally keeps engine-built results
    constructible for keys the model would reject.
    """
    if name in ANALYZERS:
        return name
    return f"custom-analyzer-{index}"


def _run_one(
    name: str, display: str, func: AnalyzerFunction, context: AnalysisContext
) -> AnalyzerResult:
    # Failure information preserves the analyzer's display name and the
    # exception type only. Exception messages and untrusted names are
    # never stored: they may reproduce repository content, including
    # secrets. See docs/rules.md section 16.7.
    try:
        result = func(context)
    except Exception as exc:
        return AnalyzerResult(
            analyzer=display,
            status=AnalyzerStatus.FAILED,
            errors=(f"{type(exc).__name__} in analyzer {display!r}",),
        )
    if not isinstance(result, AnalyzerResult):
        return AnalyzerResult(
            analyzer=display,
            status=AnalyzerStatus.FAILED,
            errors=(f"analyzer {display!r} returned an invalid result",),
        )
    if result.analyzer != name:
        # The returned name is untrusted (custom registries may return
        # arbitrary strings), so it is never stored. Analyzer identity is
        # already carried by this result's own analyzer field.
        return AnalyzerResult(
            analyzer=display,
            status=AnalyzerStatus.FAILED,
            errors=("analyzer returned a result with a mismatched identity",),
        )
    if display != name:
        # Custom analyzers keep their requested name for validation, but
        # only the safe display alias is persisted. Every other field is
        # preserved untouched. Finding-level analyzer values are NOT
        # rewritten: they feed stable finding identities, so altering them
        # would corrupt history linkage. Finding content is the analyzer's
        # own contractual responsibility (see docs/rules.md section 16.7).
        return AnalyzerResult(
            analyzer=display,
            status=result.status,
            findings=result.findings,
            checks=result.checks,
            uncovered_checks=result.uncovered_checks,
            errors=result.errors,
            unavailable_evidence=result.unavailable_evidence,
        )
    return result


def analyze(
    target: str | Path,
    config: DiscoveryConfig | None = None,
    analyzers: tuple[str, ...] | None = None,
    registry: Mapping[str, AnalyzerFunction] | None = None,
) -> list[AnalyzerResult]:
    """Discover the target and run the selected analyzers in order.

    ``analyzers`` defaults to every registered analyzer in registry order.
    ``registry`` overrides the analyzer table (used by tests); production
    callers omit it. Results built by the engine (failures) identify
    custom analyzers by positional alias (``custom-analyzer-N``); only
    documented registry names are persisted verbatim.
    """
    if config is not None and not isinstance(config, DiscoveryConfig):
        raise ValidationError(f"config must be a DiscoveryConfig, got {config!r}")
    table = _resolve_table(registry)
    names = _resolve_names(analyzers, table)
    cfg = config if config is not None else DiscoveryConfig()
    resolved = resolve_target(target)
    discovery = discover_files(resolved, cfg)
    context = AnalysisContext(target=resolved, discovery=discovery, config=cfg)
    return [
        _run_one(name, _display_name(name, index), table[name], context)
        for index, name in enumerate(names)
    ]
