"""Stage 1 tests: evidence states, finding identity, result model, repository."""

from __future__ import annotations

import json

import pytest

from repo_health.core.exceptions import RepoHealthError, ValidationError
from repo_health.models import (
    AnalyzerResult,
    AnalyzerStatus,
    EvidenceState,
    Finding,
    Repository,
    Severity,
    canonicalize_repo_path,
    compute_finding_id,
    is_established,
    validate_identifier,
)


def make_finding(**overrides: object) -> Finding:
    fields: dict[str, object] = {
        "analyzer": "security",
        "rule": "security.secret-pattern",
        "title": "Possible secret",
        "description": "A secret-like pattern was detected.",
        "severity": Severity.HIGH,
        "path": "src/app.py",
        "locator": "L10",
        "fingerprint": "aws-key",
        "evidence": "line 10 matches a known secret pattern",
        "recommendation": "Rotate the credential.",
    }
    fields.update(overrides)
    return Finding(**fields)  # type: ignore[arg-type]


# Evidence states


def test_evidence_states_are_distinct() -> None:
    assert len(set(EvidenceState)) == 3
    assert {s.value for s in EvidenceState} == {"known", "unknown", "unavailable"}


def test_only_known_is_established() -> None:
    assert is_established(EvidenceState.KNOWN) is True
    assert is_established(EvidenceState.UNKNOWN) is False
    assert is_established(EvidenceState.UNAVAILABLE) is False


# Severity


def test_severity_levels() -> None:
    assert [s.value for s in Severity] == [
        "critical",
        "high",
        "medium",
        "low",
        "info",
    ]


def test_severity_rank_orders_deterministically() -> None:
    ordered = sorted(Severity, key=lambda s: s.rank)
    assert ordered == [
        Severity.INFO,
        Severity.LOW,
        Severity.MEDIUM,
        Severity.HIGH,
        Severity.CRITICAL,
    ]


def test_invalid_severity_rejected() -> None:
    with pytest.raises(ValueError):
        Severity("urgent")


# Finding identity


def test_compute_finding_id_format_and_stability() -> None:
    first = compute_finding_id(
        "security", "security.secret-pattern", "src/a.py", "L1", "k"
    )
    second = compute_finding_id(
        "security", "security.secret-pattern", "src/a.py", "L1", "k"
    )
    assert first == second
    assert first.startswith("rh1-") and len(first) == len("rh1-") + 16


def test_identity_ignores_discovery_order_and_absolute_paths() -> None:
    first = make_finding()
    second = make_finding(path="./src/app.py")
    assert first.id == second.id
    assert "/" not in first.id and "app.py" not in first.id


def test_identity_distinguishes_occurrences() -> None:
    base = make_finding()
    assert make_finding(path="src/other.py").id != base.id
    assert make_finding(locator="L11").id != base.id
    assert make_finding(fingerprint="other-key").id != base.id
    assert make_finding(rule="security.other-rule").id != base.id


def test_explicit_matching_id_accepted() -> None:
    finding = make_finding()
    assert make_finding(id=finding.id).id == finding.id


def test_mismatched_or_malformed_id_rejected() -> None:
    finding = make_finding()
    with pytest.raises(ValidationError):
        make_finding(id="rh1-0000000000000000")
    with pytest.raises(ValidationError):
        make_finding(id="not-an-id")
    with pytest.raises(ValidationError):
        make_finding(id=finding.id, locator="L99")


# Path canonicalization


def test_canonicalize_repo_path() -> None:
    assert canonicalize_repo_path("") == ""
    assert canonicalize_repo_path("./src/app.py") == "src/app.py"
    assert canonicalize_repo_path("src//x/./app.py") == "src/x/app.py"


@pytest.mark.parametrize(
    "bad",
    ["/abs/path.py", "C:\\win\\path.py", "../escape.py", "src/../../escape.py", "."],
)
def test_bad_paths_rejected(bad: str) -> None:
    with pytest.raises(ValidationError):
        canonicalize_repo_path(bad)


def test_locator_requires_path() -> None:
    with pytest.raises(ValidationError):
        make_finding(path="", locator="L1")


# Finding validation


@pytest.mark.parametrize(
    "field", ["analyzer", "rule", "title", "description", "evidence"]
)
def test_blank_required_fields_rejected(field: str) -> None:
    with pytest.raises(ValidationError):
        make_finding(**{field: "   "})


def test_bad_identifiers_rejected() -> None:
    with pytest.raises(ValidationError):
        make_finding(analyzer="Security tool!")
    with pytest.raises(ValidationError):
        make_finding(rule="")
    assert validate_identifier("analyzer", " git ") == "git"


def test_findings_sort_deterministically() -> None:
    findings = [make_finding(fingerprint="b"), make_finding(fingerprint="a")]
    assert [
        f.sort_key() for f in sorted(findings, key=lambda f: f.sort_key())
    ] == sorted(f.id for f in findings)


def test_finding_serialization_round_trip_is_stable() -> None:
    finding = make_finding()
    text = json.dumps(finding.to_dict(), sort_keys=True)
    restored = Finding.from_dict(json.loads(text))
    assert restored == finding
    assert json.dumps(restored.to_dict(), sort_keys=True) == text


def test_finding_from_dict_rejects_bad_data() -> None:
    finding = make_finding()
    data = finding.to_dict()
    del data["evidence"]
    with pytest.raises(ValidationError):
        Finding.from_dict(data)
    with pytest.raises(ValidationError):
        Finding.from_dict({**finding.to_dict(), "severity": "urgent"})


# Analyzer results


def test_success_with_zero_findings_is_valid() -> None:
    result = AnalyzerResult(
        analyzer="code", status=AnalyzerStatus.SUCCESS, checks=("c1",)
    )
    assert result.succeeded() is True
    assert result.findings == ()


def test_success_with_findings_sorts_by_id() -> None:
    result = AnalyzerResult(
        analyzer="code",
        status=AnalyzerStatus.SUCCESS,
        findings=(make_finding(fingerprint="b"), make_finding(fingerprint="a")),
    )
    assert [f.id for f in result.findings] == sorted(f.id for f in result.findings)


def test_failed_result_requires_errors_and_preserves_them() -> None:
    with pytest.raises(ValidationError):
        AnalyzerResult(analyzer="git", status=AnalyzerStatus.FAILED)
    result = AnalyzerResult(
        analyzer="git", status=AnalyzerStatus.FAILED, errors=("git not available",)
    )
    assert result.succeeded() is False
    assert result.errors == ("git not available",)
    assert result.findings == ()


def test_failed_result_is_never_coerced_to_empty_success() -> None:
    result = AnalyzerResult(
        analyzer="git", status=AnalyzerStatus.FAILED, errors=("boom",)
    )
    assert result.status is not AnalyzerStatus.SUCCESS


def test_partial_result_requires_unavailable_info() -> None:
    with pytest.raises(ValidationError):
        AnalyzerResult(analyzer="tests", status=AnalyzerStatus.PARTIAL)
    result = AnalyzerResult(
        analyzer="tests",
        status=AnalyzerStatus.PARTIAL,
        unavailable_evidence=("test manifest unreadable",),
    )
    assert result.succeeded() is False


def test_not_run_reports_no_findings() -> None:
    assert AnalyzerResult(analyzer="code").status is AnalyzerStatus.NOT_RUN
    with pytest.raises(ValidationError):
        AnalyzerResult(
            analyzer="code",
            status=AnalyzerStatus.NOT_RUN,
            findings=(make_finding(fingerprint="x"),),
        )


def test_bad_analyzer_name_and_status_rejected() -> None:
    with pytest.raises(ValidationError):
        AnalyzerResult(analyzer="Bad Name!", status=AnalyzerStatus.SUCCESS)
    with pytest.raises(ValidationError):
        AnalyzerResult(analyzer="code", status="done")  # type: ignore[arg-type]


# Repository


def test_repository_identity() -> None:
    repo = Repository(root="/tmp/my-repo", remote="https://example.com/r.git")
    assert repo.key() == "/tmp/my-repo"
    assert repo.name == "my-repo"
    assert repo.remote == "https://example.com/r.git"


def test_repository_root_validation() -> None:
    with pytest.raises(ValidationError):
        Repository(root="")
    with pytest.raises(ValidationError):
        Repository(root="relative/path")
    assert Repository(root="/tmp/repo/").root == "/tmp/repo"


def test_validation_error_is_distinguishable() -> None:
    assert issubclass(ValidationError, RepoHealthError)
    assert issubclass(ValidationError, ValueError)
