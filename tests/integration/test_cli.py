"""Stage 5 tests: CLI framework, analyze, and db commands."""

from __future__ import annotations

import json
import os
from pathlib import Path

from pytest import CaptureFixture, MonkeyPatch

from repo_health.cli import main
from repo_health.models import RunStatus
from repo_health.models.analyzer_result import AnalyzerResult, AnalyzerStatus
from repo_health.models.repository import Repository
from repo_health.storage import (
    connect,
    get_results_for_run,
    list_runs,
    upsert_repository,
)


def build_repo(base: Path) -> Path:
    base.mkdir(parents=True, exist_ok=True)
    (base / ".git").mkdir(exist_ok=True)
    (base / "a.py").write_text("x = 1\n")
    (base / "test_a.py").write_text("def test_x(): pass\n")
    return base


def snapshot(base: Path) -> dict[str, tuple[int, bytes]]:
    state: dict[str, tuple[int, bytes]] = {}
    for dirpath, _dirnames, filenames in os.walk(base):
        for name in filenames:
            full = Path(dirpath) / name
            state[str(full)] = (full.stat().st_mtime_ns, full.read_bytes())
    return state


def test_help_exits_zero(capsys: CaptureFixture[str]) -> None:
    assert main(["--help"]) == 0
    assert main(["--version"]) == 0
    assert main(["analyze", "--help"]) == 0
    assert main(["db", "--help"]) == 0
    assert main(["db", "init", "--help"]) == 0
    assert main(["db", "info", "--help"]) == 0


def test_help_lists_subcommands(capsys: CaptureFixture[str]) -> None:
    assert main(["--help"]) == 0
    out = capsys.readouterr().out
    assert "analyze" in out and "db" in out


def test_unknown_command_and_analyzer_exit_two(tmp_path: Path) -> None:
    assert main(["nope"]) == 2
    root = build_repo(tmp_path / "repo")
    assert main(["analyze", str(root), "--analyzers", "nope"]) == 2


def test_analyze_missing_target_exits_two(capsys: CaptureFixture[str], tmp_path: Path) -> None:
    assert main(["analyze", str(tmp_path / "missing")]) == 2
    err = capsys.readouterr().err
    assert "does not exist" in err


def test_analyze_persists_observation(
    tmp_path: Path, monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
    db_path = tmp_path / "memory.db"
    monkeypatch.setenv("REPO_HEALTH_DB", str(db_path))
    root = build_repo(tmp_path / "repo")
    before = snapshot(root)
    assert main(["analyze", str(root)]) == 0
    out = capsys.readouterr().out
    assert "run 1 (completed)" in out
    assert "8 success" in out
    assert snapshot(root) == before
    with connect(db_path) as conn:
        repo = upsert_repository(conn, Repository(root=str(root)))
        runs = list_runs(conn, repo)
        assert len(runs) == 1
        assert runs[0].status is RunStatus.COMPLETED
        assert len(get_results_for_run(conn, runs[0].id or 0)) == 8


def test_analyze_no_persist_writes_nothing(
    tmp_path: Path, monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
    db_path = tmp_path / "memory.db"
    monkeypatch.setenv("REPO_HEALTH_DB", str(db_path))
    root = build_repo(tmp_path / "repo")
    assert main(["analyze", str(root), "--no-persist"]) == 0
    out = capsys.readouterr().out
    assert "run not persisted" in out
    assert not db_path.exists()


def test_analyze_partial_still_exits_zero(
    tmp_path: Path, monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
    db_path = tmp_path / "memory.db"
    monkeypatch.setenv("REPO_HEALTH_DB", str(db_path))
    root = tmp_path / "plain"
    root.mkdir()
    (root / "a.py").write_text("x = 1\n")
    assert main(["analyze", str(root)]) == 0
    out = capsys.readouterr().out
    assert "1 partial" in out


def test_analyze_summary_reports_severity_counts(
    tmp_path: Path, monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
    db_path = tmp_path / "memory.db"
    monkeypatch.setenv("REPO_HEALTH_DB", str(db_path))
    root = build_repo(tmp_path / "repo")
    (root / "sloppy.py").write_text("x = 1  \n")
    (root / "key.txt").write_text("key = AKIAIOSFODNN7EXAMPLE\n")
    assert main(["analyze", str(root)]) == 0
    out = capsys.readouterr().out
    assert "findings: 4 (critical: 0, high: 1, medium: 0, low: 1, info: 2)" in out


def test_analyze_summary_empty_result_reports_zero_counts(
    tmp_path: Path, monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
    db_path = tmp_path / "memory.db"
    monkeypatch.setenv("REPO_HEALTH_DB", str(db_path))
    root = build_repo(tmp_path / "repo")
    assert main(["analyze", str(root), "--analyzers", "architecture"]) == 0
    out = capsys.readouterr().out
    assert "findings: 0 (critical: 0, high: 0, medium: 0, low: 0, info: 0)" in out


def test_analyze_subset_and_determinism(
    tmp_path: Path, monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
    db_path = tmp_path / "memory.db"
    monkeypatch.setenv("REPO_HEALTH_DB", str(db_path))
    root = build_repo(tmp_path / "repo")

    def run() -> list[str]:
        assert main(["analyze", str(root), "--analyzers", "git", "code"]) == 0
        out = capsys.readouterr().out
        return [line for line in out.splitlines() if not line.startswith("run ")]

    assert run() == run()


def test_analyze_failure_exits_one_and_persists(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    db_path = tmp_path / "memory.db"
    monkeypatch.setenv("REPO_HEALTH_DB", str(db_path))
    root = build_repo(tmp_path / "repo")
    failed = AnalyzerResult(
        analyzer="boom", status=AnalyzerStatus.FAILED, errors=("boom",)
    )
    monkeypatch.setattr(
        "repo_health.cli.run_analysis", lambda *a, **k: [failed]
    )
    assert main(["analyze", str(root)]) == 1
    with connect(db_path) as conn:
        repo = upsert_repository(conn, Repository(root=str(root)))
        (run,) = list_runs(conn, repo)
        assert run.status is RunStatus.FAILED
        assert get_results_for_run(conn, run.id or 0) == [failed]


def test_db_init_is_repeatable_and_info_is_read_only(
    tmp_path: Path, capsys: CaptureFixture[str]
) -> None:
    db_path = tmp_path / "sub" / "memory.db"
    assert main(["db", "init", "--db-path", str(db_path)]) == 0
    assert main(["db", "init", "--db-path", str(db_path)]) == 0
    before = (db_path.stat().st_mtime_ns, db_path.read_bytes())
    assert main(["db", "info", "--db-path", str(db_path)]) == 0
    out = capsys.readouterr().out
    assert "schema_version: 3" in out
    assert "repositories: 0" in out
    assert "runs: 0" in out
    assert (db_path.stat().st_mtime_ns, db_path.read_bytes()) == before


def test_db_info_missing_database_exits_one(tmp_path: Path) -> None:
    assert main(["db", "info", "--db-path", str(tmp_path / "missing.db")]) == 1


def test_db_path_flag_overrides_env(
    tmp_path: Path, monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
    env_db = tmp_path / "env.db"
    flag_db = tmp_path / "flag.db"
    monkeypatch.setenv("REPO_HEALTH_DB", str(env_db))
    assert main(["db", "init", "--db-path", str(flag_db)]) == 0
    assert flag_db.exists()
    assert not env_db.exists()
    assert main(["db", "info", "--db-path", str(flag_db)]) == 0
    out = capsys.readouterr().out
    assert str(flag_db) in out
    assert main(["db", "info"]) == 1


def use_db(tmp_path: Path, monkeypatch: MonkeyPatch) -> Path:
    db_path = tmp_path / "memory.db"
    monkeypatch.setenv("REPO_HEALTH_DB", str(db_path))
    return db_path


def test_history_help_and_unknown_repo(
    tmp_path: Path, monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
    assert main(["history", "--help"]) == 0
    assert main(["regressions", "--help"]) == 0
    use_db(tmp_path, monkeypatch)
    root = build_repo(tmp_path / "repo")
    assert main(["db", "init"]) == 0
    capsys.readouterr()
    assert main(["history", "--repo", str(root)]) == 2
    err = capsys.readouterr().err
    assert "no history" in err


def test_history_lists_runs_and_empty_history(
    tmp_path: Path, monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
    use_db(tmp_path, monkeypatch)
    root = build_repo(tmp_path / "repo")
    assert main(["analyze", str(root)]) == 0
    capsys.readouterr()
    assert main(["history", "--repo", str(root)]) == 0
    out = capsys.readouterr().out
    assert "run 1 (completed)" in out
    assert main(["analyze", str(root)]) == 0
    capsys.readouterr()
    assert main(["history", "--repo", str(root)]) == 0
    out = capsys.readouterr().out
    assert "run 1 (completed)" in out
    assert "run 2 (completed)" in out


def test_history_run_classifies_against_previous(
    tmp_path: Path, monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
    use_db(tmp_path, monkeypatch)
    root = build_repo(tmp_path / "repo")
    assert main(["analyze", str(root)]) == 0
    capsys.readouterr()
    (root / "key.txt").write_text("key = AKIAIOSFODNN7EXAMPLE\n")
    assert main(["analyze", str(root)]) == 0
    capsys.readouterr()
    assert main(["history", "--repo", str(root), "--run", "2"]) == 0
    out = capsys.readouterr().out
    assert "run 2 vs previous run" in out
    assert "new:" in out
    assert "recurring" in out


def test_history_explicit_baseline_and_first_run_indeterminate(
    tmp_path: Path, monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
    use_db(tmp_path, monkeypatch)
    root = build_repo(tmp_path / "repo")
    assert main(["analyze", str(root)]) == 0
    capsys.readouterr()
    assert main(["history", "--repo", str(root), "--run", "1"]) == 0
    out = capsys.readouterr().out
    assert "indeterminate" in out
    assert main(["analyze", str(root)]) == 0
    capsys.readouterr()
    assert main(["history", "--repo", str(root), "--run", "2", "--baseline", "1"]) == 0
    out = capsys.readouterr().out
    assert "run 2 vs baseline run 1" in out


def test_history_invalid_runs_rejected(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    use_db(tmp_path, monkeypatch)
    root = build_repo(tmp_path / "repo")
    assert main(["analyze", str(root)]) == 0
    assert main(["history", "--repo", str(root), "--run", "99"]) == 2
    assert main(["history", "--repo", str(root), "--run", "1", "--baseline", "1"]) == 2
    assert main(["history", "--repo", str(root), "--run", "1", "--baseline", "99"]) == 2
    assert main(["history", "--repo", str(root), "--run", "abc"]) == 2


def test_regressions_reports_new_and_summary(
    tmp_path: Path, monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
    use_db(tmp_path, monkeypatch)
    root = build_repo(tmp_path / "repo")
    assert main(["analyze", str(root)]) == 0
    capsys.readouterr()
    (root / "key.txt").write_text("key = AKIAIOSFODNN7EXAMPLE\n")
    assert main(["analyze", str(root)]) == 0
    capsys.readouterr()
    assert main(["regressions", "--repo", str(root)]) == 0
    out = capsys.readouterr().out
    assert "1 new, 0 reappeared" in out
    assert "new:" in out
    assert "recurring" in out


def test_regressions_empty_and_read_only(
    tmp_path: Path, monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
    db_path = use_db(tmp_path, monkeypatch)
    root = build_repo(tmp_path / "repo")
    assert main(["analyze", str(root)]) == 0
    capsys.readouterr()
    assert main(["analyze", str(root)]) == 0
    capsys.readouterr()
    assert main(["regressions", "--repo", str(root), "--run", "2"]) == 0
    out = capsys.readouterr().out
    assert "0 new, 0 reappeared" in out
    assert "no regressions" in out
    before = (db_path.stat().st_mtime_ns, db_path.read_bytes())
    assert main(["history", "--repo", str(root), "--run", "2"]) == 0
    capsys.readouterr()
    assert main(["regressions", "--repo", str(root), "--run", "2"]) == 0
    capsys.readouterr()
    assert (db_path.stat().st_mtime_ns, db_path.read_bytes()) == before


def test_context_help_unknown_and_empty(
    tmp_path: Path, monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
    assert main(["context", "--help"]) == 0
    db_path = use_db(tmp_path, monkeypatch)
    root = build_repo(tmp_path / "repo")
    assert main(["db", "init"]) == 0
    capsys.readouterr()
    assert main(["context", "--repo", str(root)]) == 2
    assert "no history" in capsys.readouterr().err
    assert main(["analyze", str(root)]) == 0
    capsys.readouterr()
    assert main(["context", "--repo", str(root)]) == 0
    package = json.loads(capsys.readouterr().out)
    assert package["schema"] == "repo-health-context/v1"
    assert package["repository"]["key"] == str(root)
    assert package["run"]["id"] == 1
    assert package["truncated"] == {"findings_omitted": 0, "evidence_chars_omitted": 0}
    before = (db_path.stat().st_mtime_ns, db_path.read_bytes())
    assert main(["context", "--repo", str(root), "--run", "1"]) == 0
    capsys.readouterr()
    assert (db_path.stat().st_mtime_ns, db_path.read_bytes()) == before


def test_context_limits_and_invalid(
    tmp_path: Path, monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
    use_db(tmp_path, monkeypatch)
    root = build_repo(tmp_path / "repo")
    assert main(["analyze", str(root)]) == 0
    capsys.readouterr()
    assert main(["context", "--repo", str(root), "--max-findings", "1"]) == 0
    package = json.loads(capsys.readouterr().out)
    assert len(package["findings"]) == 1
    assert package["truncated"]["findings_omitted"] == 1
    assert main(["context", "--repo", str(root), "--run", "99"]) == 2
    assert main(["context", "--repo", str(root), "--max-findings", "0"]) == 2
    assert main(["context", "--repo", str(root), "--max-evidence-chars", "-5"]) == 2
    assert main(["context", "--repo", str(root), "--max-findings", "abc"]) == 2
