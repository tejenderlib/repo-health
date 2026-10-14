"""Observation comparison and lifecycle classification (Phase 6).

Pure, deterministic, read-only comparison of persisted observations for
one repository, plus integration that derives comparison inputs from
stored runs. Callers never invent history: every boolean comes from
actual rows. No schema changes were needed: rule ids already live in
finding rows, and run/repository linkage already exists.

Integration decisions (see docs/rules.md section 16.9):

1. Completeness is per (run, analyzer): the analyzer's result row must
   exist with SUCCESS status and empty unavailable-evidence and
   uncovered-checks lists.
2. Coverage compatibility is per analyzer name on both sides; a missing
   or non-successful analyzer row means incomplete, never success.
3. `previously_resolved` means: the baseline run is complete and absent
   for the finding, with an earlier same-repository observation. Runs
   between baseline and current are out of scope for pairwise
   comparison.
4. Rule compatibility compares rule ids from both sides when both
   observed, else holds (absence of version data is not incompatibility;
   rule versions would need a schema change for zero v1 benefit).

Completeness notes, per section 8: presence is positive evidence, so
RECURRING and RESOLVED do not require the *other* side's coverage to be
complete — but NEW requires a complete baseline (absence must be
established), RESOLVED requires a complete current observation, and
REAPPEARED requires an evidenced intervening resolution.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass

from repo_health.core.exceptions import ValidationError
from repo_health.models.analyzer_result import AnalyzerResult, AnalyzerStatus
from repo_health.models.finding import IDENTITY_RE, validate_identifier
from repo_health.models.lifecycle import FindingLifecycle, Lifecycle
from repo_health.storage.records import (
    get_observations_for_finding,
    get_results_for_run,
    list_runs,
)


@dataclass(frozen=True)
class FindingComparison:
    """One finding's evidence on both sides of a comparison."""

    finding_id: str
    analyzer: str
    current_observed: bool
    baseline_observed: bool
    current_complete: bool
    baseline_complete: bool
    rule_compatible: bool = True
    previously_resolved: bool = False
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
        for kind in (
            "current_observed",
            "baseline_observed",
            "current_complete",
            "baseline_complete",
            "rule_compatible",
            "previously_resolved",
        ):
            if not isinstance(getattr(self, kind), bool):
                raise ValidationError(
                    f"{kind} must be a boolean, got {getattr(self, kind)!r}"
                )
        for kind in ("baseline_run_id", "current_run_id"):
            value = getattr(self, kind)
            if value is not None and (not isinstance(value, int) or value < 1):
                raise ValidationError(f"{kind} must be a positive run id or None")
        if self.previously_resolved and self.baseline_observed:
            raise ValidationError(
                "previously_resolved contradicts baseline_observed: "
                "a resolution requires baseline absence"
            )
        object.__setattr__(self, "finding_id", finding_id)
        object.__setattr__(self, "analyzer", analyzer)


def _run_label(run_id: int | None) -> str:
    return f"run {run_id}" if run_id is not None else "an unrecorded run"


def _lifecycle(
    comparison: FindingComparison,
    lifecycle: Lifecycle,
    reason: str,
) -> FindingLifecycle:
    return FindingLifecycle(
        finding_id=comparison.finding_id,
        analyzer=comparison.analyzer,
        lifecycle=lifecycle,
        reason=reason,
        baseline_run_id=comparison.baseline_run_id,
        current_run_id=comparison.current_run_id,
    )


def classify(comparison: FindingComparison) -> FindingLifecycle:
    """Classify one finding per the section 8 decision table."""
    current = comparison.current_run_id
    baseline = comparison.baseline_run_id
    if not comparison.rule_compatible:
        return _lifecycle(
            comparison,
            Lifecycle.INDETERMINATE,
            "rule versions are incompatible across observations",
        )
    if comparison.current_observed:
        if comparison.previously_resolved:
            if not comparison.baseline_complete:
                return _lifecycle(
                    comparison,
                    Lifecycle.INDETERMINATE,
                    "reappearance claimed without a complete baseline observation",
                )
            return _lifecycle(
                comparison,
                Lifecycle.REAPPEARED,
                f"observed in {_run_label(current)} after an evidenced occurrence "
                f"and resolution at baseline {_run_label(baseline)}",
            )
        if comparison.baseline_observed:
            return _lifecycle(
                comparison,
                Lifecycle.RECURRING,
                f"observed in {_run_label(current)} and already present "
                f"in baseline {_run_label(baseline)}",
            )
        if not comparison.baseline_complete:
            return _lifecycle(
                comparison,
                Lifecycle.INDETERMINATE,
                "baseline evidence cannot establish prior absence",
            )
        return _lifecycle(
            comparison,
            Lifecycle.NEW,
            f"observed in {_run_label(current)}, absent from complete "
            f"baseline {_run_label(baseline)}",
        )
    if not comparison.current_complete:
        return _lifecycle(
            comparison,
            Lifecycle.INDETERMINATE,
            "current evidence cannot establish absence",
        )
    if comparison.baseline_observed:
        return _lifecycle(
            comparison,
            Lifecycle.RESOLVED,
            f"absent from complete {_run_label(current)}, previously observed "
            f"in baseline {_run_label(baseline)}",
        )
    return _lifecycle(
        comparison,
        Lifecycle.INDETERMINATE,
        "not observed in either observation",
    )


def compare_all(
    comparisons: Iterable[FindingComparison],
) -> tuple[FindingLifecycle, ...]:
    """Classify every comparison, ordered deterministically by finding."""
    return tuple(
        sorted(
            (classify(item) for item in comparisons),
            key=lambda result: result.sort_key(),
        )
    )


def _require_connection(conn: sqlite3.Connection) -> None:
    if not isinstance(conn, sqlite3.Connection):
        raise ValidationError(
            f"conn must be a sqlite3.Connection, got {conn!r}"
        )


def _require_run_id(run_id: int, kind: str) -> None:
    if not isinstance(run_id, int) or isinstance(run_id, bool) or run_id < 1:
        raise ValidationError(f"{kind} run id must be a positive integer")


def _analyzer_complete(
    results: list[AnalyzerResult], analyzer: str
) -> bool:
    """Complete means a SUCCESS row with no unavailable or uncovered items."""
    for result in results:
        if result.analyzer == analyzer:
            return (
                result.status is AnalyzerStatus.SUCCESS
                and not result.unavailable_evidence
                and not result.uncovered_checks
            )
    return False


def _observed_rule(
    results: list[AnalyzerResult], finding_id: str
) -> tuple[str, str] | None:
    """Return (analyzer, rule) for an observed finding, else None."""
    for result in results:
        for finding in result.findings:
            if finding.id == finding_id:
                return (finding.analyzer, finding.rule)
    return None


def _previously_resolved(
    conn: sqlite3.Connection,
    repository_id: int,
    finding_id: str,
    baseline_run_id: int,
    baseline_complete: bool,
    baseline_observed: bool,
) -> bool:
    if not baseline_complete or baseline_observed:
        return False
    for observation in get_observations_for_finding(conn, finding_id):
        if (
            observation.repository_id == repository_id
            and observation.run_id < baseline_run_id
        ):
            return True
    return False


def _comparisons_for_runs(
    conn: sqlite3.Connection,
    repository_id: int,
    current_results: list[AnalyzerResult],
    baseline_results: list[AnalyzerResult],
    current_run_id: int,
    baseline_run_id: int | None,
) -> list[FindingComparison]:
    current_ids = {
        finding.id for result in current_results for finding in result.findings
    }
    baseline_ids = {
        finding.id for result in baseline_results for finding in result.findings
    }
    comparisons: list[FindingComparison] = []
    for finding_id in sorted(current_ids | baseline_ids):
        current_hit = _observed_rule(current_results, finding_id)
        baseline_hit = _observed_rule(baseline_results, finding_id)
        hit = current_hit if current_hit is not None else baseline_hit
        if hit is None:  # pragma: no cover - union membership guarantees a hit
            raise ValidationError(f"finding {finding_id} observed in neither run")
        analyzer = hit[0]
        current_complete = _analyzer_complete(current_results, analyzer)
        baseline_complete = (
            _analyzer_complete(baseline_results, analyzer)
            if baseline_run_id is not None
            else False
        )
        if current_hit is not None and baseline_hit is not None:
            rule_compatible = current_hit[1] == baseline_hit[1]
        else:
            rule_compatible = True
        previously_resolved = (
            _previously_resolved(
                conn,
                repository_id,
                finding_id,
                baseline_run_id,
                baseline_complete,
                baseline_hit is not None,
            )
            if baseline_run_id is not None
            else False
        )
        comparisons.append(
            FindingComparison(
                finding_id=finding_id,
                analyzer=analyzer,
                current_observed=current_hit is not None,
                baseline_observed=baseline_hit is not None,
                current_complete=current_complete,
                baseline_complete=baseline_complete,
                rule_compatible=rule_compatible,
                previously_resolved=previously_resolved,
                baseline_run_id=baseline_run_id,
                current_run_id=current_run_id,
            )
        )
    return comparisons


def _repository_run_ids(conn: sqlite3.Connection, repository_id: int) -> set[int]:
    if not isinstance(repository_id, int) or repository_id < 1:
        raise ValidationError("repository_id must be a positive integer")
    return {
        run.id
        for run in list_runs(conn, repository_id)
        if run.id is not None
    }


def compare_runs(
    conn: sqlite3.Connection,
    repository_id: int,
    current_run_id: int,
    baseline_run_id: int,
) -> tuple[FindingLifecycle, ...]:
    """Compare two stored runs of one repository, ordered by finding.

    Both runs must belong to the repository; anything else is a caller
    error, never an empty comparison.
    """
    _require_connection(conn)
    _require_run_id(current_run_id, "current")
    _require_run_id(baseline_run_id, "baseline")
    if current_run_id == baseline_run_id:
        raise ValidationError("current and baseline runs must differ")
    if baseline_run_id > current_run_id:
        raise ValidationError(
            f"baseline run {baseline_run_id} must precede run {current_run_id}"
        )
    known = _repository_run_ids(conn, repository_id)
    for run_id, kind in (
        (current_run_id, "current"),
        (baseline_run_id, "baseline"),
    ):
        if run_id not in known:
            raise ValidationError(
                f"{kind} run {run_id} does not belong to repository {repository_id}"
            )
    current_results = get_results_for_run(conn, current_run_id)
    baseline_results = get_results_for_run(conn, baseline_run_id)
    return compare_all(
        _comparisons_for_runs(
            conn,
            repository_id,
            current_results,
            baseline_results,
            current_run_id,
            baseline_run_id,
        )
    )


def compare_to_previous(
    conn: sqlite3.Connection,
    repository_id: int,
    current_run_id: int,
) -> tuple[FindingLifecycle, ...]:
    """Compare a stored run against its latest earlier run, if any.

    With no earlier run, every current finding is INDETERMINATE: missing
    baseline evidence must never produce NEW.
    """
    _require_connection(conn)
    _require_run_id(current_run_id, "current")
    known = _repository_run_ids(conn, repository_id)
    if current_run_id not in known:
        raise ValidationError(
            f"current run {current_run_id} does not belong to "
            f"repository {repository_id}"
        )
    earlier = sorted(run_id for run_id in known if run_id < current_run_id)
    if not earlier:
        current_results = get_results_for_run(conn, current_run_id)
        return compare_all(
            _comparisons_for_runs(
                conn, repository_id, current_results, [], current_run_id, None
            )
        )
    return compare_runs(conn, repository_id, current_run_id, earlier[-1])
