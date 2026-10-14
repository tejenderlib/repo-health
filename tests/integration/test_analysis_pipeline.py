"""Stage 4 integration: engine with all analyzers, persisted to storage."""

from __future__ import annotations

import json
import os
from pathlib import Path

from repo_health.analyzers import analyzer_names
from repo_health.config import DiscoveryConfig
from repo_health.core.engine import analyze
from repo_health.discovery.repository import resolve_target
from repo_health.models import RunStatus
from repo_health.models.analyzer_result import AnalyzerStatus
from repo_health.storage import (
    connect,
    create_run,
    get_results_for_run,
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
    (base / "README.md").write_text("# Demo\n")
    (base / "pyproject.toml").write_text("[project]\n")
    return base


def snapshot(base: Path) -> dict[str, tuple[int, bytes]]:
    state: dict[str, tuple[int, bytes]] = {}
    for dirpath, _dirnames, filenames in os.walk(base):
        for name in filenames:
            full = Path(dirpath) / name
            state[str(full)] = (full.stat().st_mtime_ns, full.read_bytes())
    return state


def test_registry_runs_all_documented_analyzers_in_order(tmp_path: Path) -> None:
    assert analyzer_names() == (
        "git",
        "code",
        "tests",
        "dependencies",
        "security",
        "documentation",
        "architecture",
        "configuration",
    )
    root = build_repo(tmp_path / "repo")
    results = analyze(root)
    assert [r.analyzer for r in results] == list(analyzer_names())
    assert all(r.status is AnalyzerStatus.SUCCESS for r in results)
    assert analyze(root) == results


def test_pipeline_persists_and_round_trips(tmp_path: Path) -> None:
    root = build_repo(tmp_path / "repo")
    before = snapshot(root)
    results = analyze(root, config=DiscoveryConfig())
    assert snapshot(root) == before
    db_path = init_db(tmp_path / "memory.db")
    with connect(db_path) as conn:
        repo_id = upsert_repository(conn, resolve_target(root).root)
        run_id = create_run(conn, repo_id, RunStatus.COMPLETED)
        for result in results:
            record_analyzer_result(conn, run_id, result)
            for finding in result.findings:
                record_observation(conn, run_id, finding)
        stored = get_results_for_run(conn, run_id)
    assert [r.analyzer for r in stored] == sorted(r.analyzer for r in results)
    assert {r.analyzer: r for r in stored} == {r.analyzer: r for r in results}
    blob = json.dumps([[f.to_dict() for f in r.findings] for r in stored])
    assert "AKIA" not in blob
