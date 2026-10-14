"""Phase 6, step 1 tests: lifecycle decision table and model validation."""

from __future__ import annotations

import pytest

from repo_health.core.exceptions import ValidationError
from repo_health.intelligence.regression import (
    FindingComparison,
    classify,
    compare_all,
)
from repo_health.models.lifecycle import FindingLifecycle, Lifecycle

FINDING = "rh1-0000000000000000"


def compare(**overrides: object) -> FindingComparison:
    fields: dict[str, object] = {
        "finding_id": FINDING,
        "analyzer": "security",
        "current_observed": True,
        "baseline_observed": False,
        "current_complete": True,
        "baseline_complete": True,
        "rule_compatible": True,
        "previously_resolved": False,
        "baseline_run_id": 1,
        "current_run_id": 2,
    }
    fields.update(overrides)
    return FindingComparison(**fields)  # type: ignore[arg-type]


def lifecycle_of(comparison: FindingComparison) -> Lifecycle:
    return classify(comparison).lifecycle


# Happy paths


def test_new() -> None:
    result = classify(compare())
    assert result.lifecycle is Lifecycle.NEW
    assert result.baseline_run_id == 1
    assert result.current_run_id == 2
    assert result.reason != ""


def test_recurring() -> None:
    assert lifecycle_of(compare(baseline_observed=True)) is Lifecycle.RECURRING


def test_resolved() -> None:
    result = classify(
        compare(current_observed=False, baseline_observed=True)
    )
    assert result.lifecycle is Lifecycle.RESOLVED


def test_reappeared() -> None:
    result = classify(
        compare(
            baseline_observed=False,
            baseline_complete=True,
            previously_resolved=True,
        )
    )
    assert result.lifecycle is Lifecycle.REAPPEARED


# Safety rules: unsupported classifications are prevented


def test_missing_baseline_is_not_new() -> None:
    assert (
        lifecycle_of(compare(baseline_complete=False)) is Lifecycle.INDETERMINATE
    )


def test_missing_current_is_not_resolved() -> None:
    assert (
        lifecycle_of(
            compare(current_observed=False, baseline_observed=True,
                    current_complete=False)
        )
        is Lifecycle.INDETERMINATE
    )


def test_failed_baseline_is_not_new() -> None:
    assert (
        lifecycle_of(
            compare(baseline_complete=False, baseline_observed=False)
        )
        is Lifecycle.INDETERMINATE
    )


def test_incompatible_rules_are_indeterminate() -> None:
    assert (
        lifecycle_of(compare(rule_compatible=False)) is Lifecycle.INDETERMINATE
    )
    assert (
        lifecycle_of(
            compare(current_observed=False, baseline_observed=True,
                    rule_compatible=False)
        )
        is Lifecycle.INDETERMINATE
    )


def test_absent_on_both_sides_is_indeterminate() -> None:
    assert (
        lifecycle_of(compare(current_observed=False, baseline_observed=False))
        is Lifecycle.INDETERMINATE
    )


def test_reappearance_without_complete_baseline_is_indeterminate() -> None:
    assert (
        lifecycle_of(
            compare(previously_resolved=True, baseline_complete=False)
        )
        is Lifecycle.INDETERMINATE
    )


def test_recurring_does_not_require_baseline_coverage() -> None:
    assert (
        lifecycle_of(compare(baseline_observed=True, baseline_complete=False))
        is Lifecycle.RECURRING
    )


def test_resolved_does_not_require_baseline_coverage() -> None:
    assert (
        lifecycle_of(
            compare(current_observed=False, baseline_observed=True,
                    baseline_complete=False)
        )
        is Lifecycle.RESOLVED
    )


def test_contradictory_history_rejected() -> None:
    with pytest.raises(ValidationError):
        compare(baseline_observed=True, previously_resolved=True)


# Determinism and ordering


def test_classification_is_deterministic() -> None:
    assert classify(compare()) == classify(compare())
    assert classify(compare()).reason == classify(compare()).reason


def test_compare_all_orders_by_finding() -> None:
    other = "rh1-ffffffffffffffff"
    results = compare_all(
        [
            compare(finding_id=other, analyzer="code"),
            compare(finding_id=FINDING, analyzer="security"),
        ]
    )
    assert [r.sort_key() for r in results] == [
        (FINDING, "security"),
        (other, "code"),
    ]
    assert all(r.lifecycle is Lifecycle.NEW for r in results)


# Model and input validation


def test_lifecycle_model_validation() -> None:
    with pytest.raises(ValidationError):
        FindingLifecycle(
            finding_id="bad",
            analyzer="security",
            lifecycle=Lifecycle.NEW,
            reason="x",
        )
    with pytest.raises(ValidationError):
        FindingLifecycle(
            finding_id=FINDING,
            analyzer="security",
            lifecycle="new",  # type: ignore[arg-type]
            reason="x",
        )
    with pytest.raises(ValidationError):
        FindingLifecycle(
            finding_id=FINDING,
            analyzer="security",
            lifecycle=Lifecycle.NEW,
            reason="   ",
        )
    with pytest.raises(ValidationError):
        FindingLifecycle(
            finding_id=FINDING,
            analyzer="security",
            lifecycle=Lifecycle.NEW,
            reason="x",
            baseline_run_id=0,
        )


def test_comparison_input_validation() -> None:
    with pytest.raises(ValidationError):
        compare(finding_id="bad")
    with pytest.raises(ValidationError):
        compare(current_observed="yes")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        compare(current_run_id=-1)
