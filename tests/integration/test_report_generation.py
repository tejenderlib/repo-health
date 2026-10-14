"""Phase 8, step 4 tests: report command."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from pytest import CaptureFixture, MonkeyPatch

from repo_health.cli import main
from repo_health.models import RunStatus, Severity
from repo_health.models.analyzer_result import AnalyzerResult, AnalyzerStatus
from repo_health.models.finding import Finding
from repo_health.models.repository import Repository
from repo_health.storage import (
    connect,
    create_run,
    init_db,
    record_analyzer_result,
    record_observation,
    upsert_repository,
)


def build_repo(base: Path) -> Path:
    base.mkdir(parents=True, exist_ok=True)
    (base / ".git").mkdir(exist_ok=True)
    (base / "a.py").write_text("x = 1\n")
    (base / "test_a.py").write_text("def test_x(): pass\n")
    return base


def use_db(tmp_path: Path, monkeypatch: MonkeyPatch) -> Path:
    db_path = tmp_path / "memory.db"
    monkeypatch.setenv("REPO_HEALTH_DB", str(db_path))
    return db_path


def analyze_twice(
    tmp_path: Path, monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> tuple[Path, Path]:
    db_path = use_db(tmp_path, monkeypatch)
    root = build_repo(tmp_path / "repo")
    assert main(["analyze", str(root)]) == 0
    capsys.readouterr()
    (root / "key.txt").write_text("key = AKIAIOSFODNN7EXAMPLE\n")
    assert main(["analyze", str(root)]) == 0
    capsys.readouterr()
    return db_path, root


def test_report_help(tmp_path: Path, capsys: CaptureFixture[str]) -> None:
    assert main(["report", "--help"]) == 0
    assert "markdown" in capsys.readouterr().out


def test_report_markdown_default(
    tmp_path: Path, monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
    _, root = analyze_twice(tmp_path, monkeypatch, capsys)
    assert main(["report", "--repo", str(root)]) == 0
    out = capsys.readouterr().out
    assert out.startswith("# Repo Health Report\n")
    assert "Baseline: run 1" in out
    assert "### HIGH (1)" in out
    assert "No findings does not prove" in out


def test_report_json_and_summary(
    tmp_path: Path, monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
    _, root = analyze_twice(tmp_path, monkeypatch, capsys)
    assert main(["report", "--repo", str(root), "--format", "json"]) == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["schema"] == "repo-health-report/v1"
    assert parsed["run"]["id"] == 2
    assert parsed["baseline_run_id"] == 1
    assert parsed["lifecycle_counts"]["new"] == 1
    assert main(["report", "--repo", str(root), "--format", "summary"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("run 2 (completed), baseline run 1\n")
    assert main(["report", "--repo", str(root), "--format", "bogus"]) == 2


def test_report_explicit_baseline_and_run(
    tmp_path: Path, monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
    _, root = analyze_twice(tmp_path, monkeypatch, capsys)
    assert main(["report", "--repo", str(root), "--run", "2", "--baseline", "1"]) == 0
    out = capsys.readouterr().out
    assert "Baseline: run 1" in out
    assert main(["report", "--repo", str(root), "--run", "1"]) == 0
    out = capsys.readouterr().out
    assert "Baseline: none" in out


def test_report_output_file_matches_stdout(
    tmp_path: Path, monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
    _, root = analyze_twice(tmp_path, monkeypatch, capsys)
    assert main(["report", "--repo", str(root), "--format", "json"]) == 0
    stdout_bytes = capsys.readouterr().out
    target = tmp_path / "nested" / "report.json"
    assert main(["report", "--repo", str(root), "--format", "json", "--output", str(target)]) == 0
    assert target.read_bytes() == stdout_bytes.encode("utf-8")
    assert main(["report", "--repo", str(root), "--format", "markdown"]) == 0
    stdout_md = capsys.readouterr().out
    target_md = tmp_path / "nested" / "report.md"
    assert (
        main(["report", "--repo", str(root), "--format", "markdown", "--output", str(target_md)])
        == 0
    )
    assert target_md.read_bytes() == stdout_md.encode("utf-8")


def seed_seeded_db(db_path: Path) -> None:
    init_db(db_path)
    with connect(db_path) as conn:
        repo_id = upsert_repository(
            conn, Repository(root="/tmp/repo"), now="2026-01-01T00:00:00+00:00"
        )
        run1 = create_run(conn, repo_id, RunStatus.COMPLETED, now="2026-01-02T00:00:00+00:00")
        record_analyzer_result(
            conn, run1, AnalyzerResult(analyzer="git", status=AnalyzerStatus.SUCCESS, checks=("c",))
        )
        run2 = create_run(conn, repo_id, RunStatus.COMPLETED, now="2026-01-03T00:00:00+00:00")
        findings = tuple(
            Finding(
                analyzer="security",
                rule="security.secret-pattern",
                title="T",
                description="D",
                severity=severity,
                path="a.py",
                locator="L1",
                fingerprint=f"k{i}",
                evidence="e",
                recommendation="R",
            )
            for i, severity in enumerate((Severity.LOW, Severity.CRITICAL, Severity.INFO))
        )
        result = AnalyzerResult(
            analyzer="security",
            status=AnalyzerStatus.SUCCESS,
            findings=findings,
            checks=("c",),
        )
        record_analyzer_result(conn, run2, result)
        for finding in findings:
            record_observation(conn, run2, finding, now="2026-01-03T00:00:00+00:00")


_RENDER_SCRIPT = "\n".join(
    [
        "import sys",
        "sys.path.insert(0, sys.argv[2])",
        "from repo_health.reports.json_report import build_report, report_to_json",
        "from repo_health.reports.markdown import render_markdown",
        "from repo_health.storage import connect",
        "with connect(sys.argv[1]) as conn:",
        "    report = build_report(conn, '/tmp/repo', 2, 1)",
        "    sys.stdout.write(report_to_json(report))",
        "    sys.stdout.write(render_markdown(report))",
    ]
)


def run_render(db_path: Path, seed: str) -> str:
    root = Path(__file__).resolve().parents[2]
    env = dict(os.environ)
    env["PYTHONHASHSEED"] = seed
    completed = subprocess.run(
        [sys.executable, "-c", _RENDER_SCRIPT, str(db_path), str(root / "src")],
        capture_output=True,
        text=True,
        env=env,
        cwd=root,
    )
    assert completed.returncode == 0, completed.stderr
    return completed.stdout


def test_reports_stable_across_hash_seeds(tmp_path: Path) -> None:
    db_path = tmp_path / "memory.db"
    seed_seeded_db(db_path)
    assert run_render(db_path, "5") == run_render(db_path, "99")


def test_report_unknown_and_invalid(
    tmp_path: Path, monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
    db_path = use_db(tmp_path, monkeypatch)
    root = build_repo(tmp_path / "repo")
    assert main(["db", "init"]) == 0
    capsys.readouterr()
    assert main(["report", "--repo", str(root)]) == 2
    assert "no history" in capsys.readouterr().err
    with connect(db_path) as conn:
        upsert_repository(conn, Repository(root=str(root)))
    assert main(["report", "--repo", str(root)]) == 0
    assert "no runs" in capsys.readouterr().out
    assert main(["analyze", str(root)]) == 0
    capsys.readouterr()
    assert main(["report", "--repo", str(root), "--run", "99"]) == 2
    assert main(["report", "--repo", str(root), "--run", "1", "--baseline", "1"]) == 2


def test_report_is_read_only(
    tmp_path: Path, monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
    db_path, root = analyze_twice(tmp_path, monkeypatch, capsys)
    before = (db_path.stat().st_mtime_ns, db_path.read_bytes())
    assert main(["report", "--repo", str(root)]) == 0
    capsys.readouterr()
    assert main(["report", "--repo", str(root), "--format", "summary"]) == 0
    capsys.readouterr()
    assert (db_path.stat().st_mtime_ns, db_path.read_bytes()) == before
