"""Stage 4 tests: run context, engine orchestration, failure isolation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from repo_health.config import DiscoveryConfig
from repo_health.core.context import AnalysisContext
from repo_health.core.engine import analyze
from repo_health.core.exceptions import ValidationError
from repo_health.discovery.files import discover_files
from repo_health.discovery.repository import resolve_target
from repo_health.models import Severity
from repo_health.models.analyzer_result import AnalyzerResult, AnalyzerStatus
from repo_health.models.finding import Finding


def make_finding() -> Finding:
    return Finding(
        analyzer="stub",
        rule="stub.rule",
        title="Stub",
        description="A stub finding.",
        severity=Severity.INFO,
        path="a.py",
        locator="L1",
        fingerprint="",
        evidence="stub evidence",
        recommendation="",
    )


def ok_fn(context: AnalysisContext) -> AnalyzerResult:
    return AnalyzerResult(
        analyzer="ok", status=AnalyzerStatus.SUCCESS, checks=("ok-check",)
    )


def findings_fn(context: AnalysisContext) -> AnalyzerResult:
    assert context.discovery.files == ("a.py",)
    return AnalyzerResult(
        analyzer="findings",
        status=AnalyzerStatus.SUCCESS,
        findings=(make_finding(),),
        checks=("findings-check",),
    )


def boom_fn(context: AnalysisContext) -> AnalyzerResult:
    raise RuntimeError("boom")


def wrong_type_fn(context: AnalysisContext) -> AnalyzerResult:
    return "nope"  # type: ignore[return-value]


def wrong_name_fn(context: AnalysisContext) -> AnalyzerResult:
    return AnalyzerResult(analyzer="other", status=AnalyzerStatus.SUCCESS)


STUBS = {
    "ok": ok_fn,
    "findings": findings_fn,
    "boom": boom_fn,
    "wrong_type": wrong_type_fn,
    "wrong_name": wrong_name_fn,
}


def make_repo(base: Path) -> Path:
    base.mkdir(parents=True, exist_ok=True)
    (base / "a.py").write_text("x = 1\n")
    return base


def test_context_validation(tmp_path: Path) -> None:
    root = make_repo(tmp_path / "repo")
    resolved = resolve_target(root)
    discovery = discover_files(resolved, DiscoveryConfig())
    context = AnalysisContext(
        target=resolved, discovery=discovery, config=DiscoveryConfig()
    )
    assert context.target.root.key() == str(root)
    with pytest.raises(ValidationError):
        AnalysisContext(target="x", discovery=discovery, config=DiscoveryConfig())  # type: ignore[arg-type]
    other = resolve_target(make_repo(tmp_path / "other"))
    with pytest.raises(ValidationError):
        AnalysisContext(target=other, discovery=discovery, config=DiscoveryConfig())


def test_engine_runs_selected_analyzers_in_order(tmp_path: Path) -> None:
    root = make_repo(tmp_path / "repo")
    results = analyze(root, analyzers=("findings", "ok"), registry=STUBS)
    # Custom analyzers persist under positional aliases; order is preserved.
    assert [r.analyzer for r in results] == ["custom-analyzer-0", "custom-analyzer-1"]
    assert all(r.succeeded() for r in results)
    assert results[0].findings == (make_finding(),)


def test_engine_empty_registry_yields_no_results(tmp_path: Path) -> None:
    root = make_repo(tmp_path / "repo")
    assert analyze(root, registry={}) == []


def test_engine_rejects_unknown_analyzers(tmp_path: Path) -> None:
    root = make_repo(tmp_path / "repo")
    with pytest.raises(ValidationError) as excinfo:
        analyze(root, analyzers=("nope",), registry=STUBS)
    assert "ok" in str(excinfo.value)
    with pytest.raises(ValidationError):
        analyze(root, analyzers="ok", registry=STUBS)  # type: ignore[arg-type]


def test_engine_isolates_failures(tmp_path: Path) -> None:
    root = make_repo(tmp_path / "repo")
    results = analyze(root, analyzers=("ok", "boom", "findings"), registry=STUBS)
    assert [r.status for r in results] == [
        AnalyzerStatus.SUCCESS,
        AnalyzerStatus.FAILED,
        AnalyzerStatus.SUCCESS,
    ]
    assert results[1].errors == ("RuntimeError in analyzer 'custom-analyzer-1'",)
    assert results[1].analyzer == "custom-analyzer-1"
    assert results[1].findings == ()


def test_engine_failure_errors_exclude_exception_text(tmp_path: Path) -> None:
    secret = "hunter2-live-secret-xyz"

    def leaky(context: AnalysisContext) -> AnalyzerResult:
        raise ValueError(f"could not parse value {secret}")

    root = make_repo(tmp_path / "repo")
    (result,) = analyze(root, analyzers=("leaky",), registry={"leaky": leaky})
    assert result.status is AnalyzerStatus.FAILED
    assert result.analyzer == "custom-analyzer-0"
    assert result.errors == ("ValueError in analyzer 'custom-analyzer-0'",)
    blob = json.dumps(
        {
            "errors": list(result.errors),
            "findings": [f.to_dict() for f in result.findings],
        }
    )
    assert secret not in blob


def test_engine_rejects_invalid_results(tmp_path: Path) -> None:
    root = make_repo(tmp_path / "repo")
    (wrong_type,) = analyze(root, analyzers=("wrong_type",), registry=STUBS)
    assert wrong_type.status is AnalyzerStatus.FAILED
    assert wrong_type.analyzer == "custom-analyzer-0"
    assert wrong_type.errors == ("analyzer 'custom-analyzer-0' returned an invalid result",)
    (wrong_name,) = analyze(root, analyzers=("wrong_name",), registry=STUBS)
    assert wrong_name.status is AnalyzerStatus.FAILED
    assert wrong_name.errors == ("analyzer returned a result with a mismatched identity",)


def test_engine_mismatched_identity_hides_returned_name(tmp_path: Path) -> None:
    secret_name = "token-hunter2-abc"

    def sneaky(context: AnalysisContext) -> AnalyzerResult:
        return AnalyzerResult(analyzer=secret_name, status=AnalyzerStatus.SUCCESS)

    root = make_repo(tmp_path / "repo")
    (result,) = analyze(root, analyzers=("sneaky",), registry={"sneaky": sneaky})
    assert result.status is AnalyzerStatus.FAILED
    assert result.analyzer == "custom-analyzer-0"
    assert result.errors == ("analyzer returned a result with a mismatched identity",)
    blob = json.dumps(
        {
            "analyzer": result.analyzer,
            "errors": list(result.errors),
            "findings": [f.to_dict() for f in result.findings],
        }
    )
    assert secret_name not in blob
    assert "hunter2" not in blob


def test_engine_secret_registry_key_never_persists(tmp_path: Path) -> None:
    secret_key = "hunter2-secret-key"

    def boom(context: AnalysisContext) -> AnalyzerResult:
        raise RuntimeError("boom")

    root = make_repo(tmp_path / "repo")
    (result,) = analyze(root, analyzers=(secret_key,), registry={secret_key: boom})
    assert result.status is AnalyzerStatus.FAILED
    assert result.analyzer == "custom-analyzer-0"
    assert result.errors == ("RuntimeError in analyzer 'custom-analyzer-0'",)
    blob = json.dumps(
        {
            "analyzer": result.analyzer,
            "errors": list(result.errors),
            "findings": [f.to_dict() for f in result.findings],
            "unavailable": list(result.unavailable_evidence),
        }
    )
    assert secret_key not in blob
    assert "hunter2" not in blob


def test_engine_invalid_registry_key_yields_failed_not_crash(
    tmp_path: Path,
) -> None:
    def boom(context: AnalysisContext) -> AnalyzerResult:
        raise RuntimeError("boom")

    root = make_repo(tmp_path / "repo")
    (result,) = analyze(root, analyzers=("my key",), registry={"my key": boom})
    assert result.status is AnalyzerStatus.FAILED
    assert result.analyzer == "custom-analyzer-0"
    assert result.errors == ("RuntimeError in analyzer 'custom-analyzer-0'",)


def test_engine_passes_analyzer_built_findings_through_untouched(
    tmp_path: Path,
) -> None:
    # Trust-boundary lock: finding content is the analyzer's own
    # responsibility. The engine aliases result-level fields but never
    # rewrites findings (doing so would corrupt stable finding
    # identities). A rogue analyzer that embeds sensitive content in its
    # own findings therefore persists it — that is the analyzer's defect,
    # and this test pins the boundary so the behavior cannot drift
    # silently in either direction.
    secret_key = "hunter2-secret-key"
    finding = Finding(
        analyzer=secret_key,
        rule="custom.rule",
        title="Custom",
        description="A rogue finding reusing the registry key.",
        severity=Severity.INFO,
        path="a.py",
        locator="L1",
        fingerprint="",
        evidence="custom evidence",
        recommendation="",
    )

    def good(context: AnalysisContext) -> AnalyzerResult:
        return AnalyzerResult(
            analyzer=secret_key,
            status=AnalyzerStatus.SUCCESS,
            findings=(finding,),
            checks=("custom-check",),
        )

    root = make_repo(tmp_path / "repo")
    (result,) = analyze(root, analyzers=(secret_key,), registry={secret_key: good})
    assert result.status is AnalyzerStatus.SUCCESS
    assert result.analyzer == "custom-analyzer-0"
    assert result.findings == (finding,)
    assert result.findings[0].id == finding.id
    blob = json.dumps(
        {
            "analyzer": result.analyzer,
            "errors": list(result.errors),
            "findings": [f.to_dict() for f in result.findings],
        }
    )
    assert secret_key in blob


def test_engine_success_custom_name_persists_display_alias(
    tmp_path: Path,
) -> None:
    secret_key = "hunter2-secret-key"
    finding = Finding(
        analyzer="custom",
        rule="custom.rule",
        title="Custom",
        description="A custom finding with safe values.",
        severity=Severity.INFO,
        path="a.py",
        locator="L1",
        fingerprint="",
        evidence="custom evidence",
        recommendation="",
    )

    def good(context: AnalysisContext) -> AnalyzerResult:
        return AnalyzerResult(
            analyzer=secret_key,
            status=AnalyzerStatus.SUCCESS,
            findings=(finding,),
            checks=("custom-check",),
        )

    root = make_repo(tmp_path / "repo")
    (result,) = analyze(root, analyzers=(secret_key,), registry={secret_key: good})
    assert result.status is AnalyzerStatus.SUCCESS
    assert result.analyzer == "custom-analyzer-0"
    assert result.findings == (finding,)
    assert result.checks == ("custom-check",)
    blob = json.dumps(
        {
            "analyzer": result.analyzer,
            "status": result.status.value,
            "errors": list(result.errors),
            "checks": list(result.checks),
            "unavailable": list(result.unavailable_evidence),
            "findings": [f.to_dict() for f in result.findings],
        }
    )
    assert secret_key not in blob
    assert "hunter2" not in blob


def test_engine_propagates_target_errors(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        analyze(tmp_path / "missing", registry=STUBS)
    with pytest.raises(ValidationError):
        analyze(tmp_path, config="x", registry=STUBS)  # type: ignore[arg-type]


def test_engine_is_deterministic(tmp_path: Path) -> None:
    root = make_repo(tmp_path / "repo")
    first = analyze(root, analyzers=("ok", "findings"), registry=STUBS)
    second = analyze(root, analyzers=("ok", "findings"), registry=STUBS)
    assert first == second
