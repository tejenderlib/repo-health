"""Stage 2 tests: paths, init, migrations, persistence round-trips, errors."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest

from repo_health.core.exceptions import DatabaseError, ValidationError
from repo_health.models import (
    AnalysisRun,
    AnalyzerResult,
    AnalyzerStatus,
    EvidenceState,
    Finding,
    Observation,
    Repository,
    RunStatus,
    Severity,
)
from repo_health.storage import (
    DEFAULT_DB_PATH,
    MEMORY_SCHEMA_VERSION,
    connect,
    connect_readonly,
    create_run,
    get_findings_for_run,
    get_observations_for_finding,
    get_repository,
    get_results_for_run,
    get_run,
    init_db,
    list_runs,
    migrate,
    record_analyzer_result,
    record_observation,
    resolve_db_path,
    upsert_repository,
)
from repo_health.storage import schema as schema_module


def make_finding(
    fingerprint: str = "key-a",
    evidence: str = "line 10 matches a known secret pattern",
) -> Finding:
    return Finding(
        analyzer="security",
        rule="security.secret-pattern",
        title="Possible secret",
        description="A secret-like pattern was detected.",
        severity=Severity.HIGH,
        path="src/app.py",
        locator="L10",
        fingerprint=fingerprint,
        evidence=evidence,
        recommendation="Rotate the credential.",
    )


def make_repo(root: str = "/tmp/demo-repo") -> Repository:
    return Repository(root=root, name="demo-repo")


def seed_run(conn: sqlite3.Connection) -> int:
    repo_id = upsert_repository(conn, make_repo(), now="2026-01-01T00:00:00+00:00")
    return create_run(
        conn, repo_id, RunStatus.COMPLETED, now="2026-01-02T00:00:00+00:00"
    )


# Path resolution


def test_default_db_path() -> None:
    assert (
        DEFAULT_DB_PATH
        == Path.home() / ".local" / "share" / "repo-health" / "memory.db"
    )
    assert resolve_db_path() == DEFAULT_DB_PATH


def test_explicit_path_overrides_default(tmp_path: Path) -> None:
    custom = tmp_path / "custom.db"
    assert resolve_db_path(custom) == custom
    assert resolve_db_path("~/alt.db") == Path.home() / "alt.db"


def test_env_var_overrides_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    custom = tmp_path / "env.db"
    monkeypatch.setenv("REPO_HEALTH_DB", str(custom))
    assert resolve_db_path() == custom
    assert resolve_db_path(tmp_path / "explicit.db") == tmp_path / "explicit.db"


def test_resolving_paths_creates_nothing(tmp_path: Path) -> None:
    target = tmp_path / "nope" / "memory.db"
    resolve_db_path(target)
    assert not target.parent.exists()


# Initialization and migrations


def test_init_db_creates_and_migrates(tmp_path: Path) -> None:
    path = init_db(tmp_path / "memory.db")
    assert path.exists()
    with connect(path) as conn:
        assert migrate(conn) == MEMORY_SCHEMA_VERSION
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
    assert {
        "migrations",
        "repositories",
        "analysis_runs",
        "analyzer_results",
        "findings",
        "observations",
    } <= tables


def test_init_db_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "memory.db"
    assert init_db(path) == init_db(path)
    with connect(path) as conn:
        repo_id = upsert_repository(conn, make_repo())
    assert init_db(path) == path
    with connect(path) as conn:
        assert get_repository(conn, make_repo().key()) is not None
        assert upsert_repository(conn, make_repo()) == repo_id


def test_migrate_is_idempotent_on_open_connection(tmp_path: Path) -> None:
    path = init_db(tmp_path / "memory.db")
    with connect(path) as conn:
        assert migrate(conn) == migrate(conn) == MEMORY_SCHEMA_VERSION


def test_failed_migration_leaves_no_partial_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        schema_module,
        "MIGRATIONS",
        (
            (
                1,
                "deliberately failing migration",
                "CREATE TABLE partial_ok (id INTEGER); THIS IS NOT SQL;",
            ),
        ),
    )
    path = tmp_path / "memory.db"
    with pytest.raises(DatabaseError):
        with connect(path) as conn:
            migrate(conn)
    with connect(path) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        assert "partial_ok" not in tables
        assert schema_module.applied_versions(conn) == ()


def test_database_recovers_after_failed_migration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_migrations = schema_module.MIGRATIONS
    monkeypatch.setattr(
        schema_module,
        "MIGRATIONS",
        ((1, "deliberately failing migration", "THIS IS NOT SQL;"),),
    )
    monkeypatch.setattr(schema_module, "MEMORY_SCHEMA_VERSION", 1)
    path = tmp_path / "memory.db"
    with pytest.raises(DatabaseError):
        init_db(path)
    monkeypatch.setattr(schema_module, "MIGRATIONS", real_migrations)
    monkeypatch.setattr(schema_module, "MEMORY_SCHEMA_VERSION", len(real_migrations))
    with connect(path) as conn:
        assert migrate(conn) == MEMORY_SCHEMA_VERSION
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        assert {"repositories", "findings", "observations"} <= tables


def test_migrate_refuses_open_transaction(tmp_path: Path) -> None:
    path = init_db(tmp_path / "memory.db")
    with connect(path) as conn:
        conn.execute(
            "INSERT INTO repositories (key, root, name, first_seen,"
            " last_seen) VALUES ('k', '/r', 'r', 't', 't')"
        )
        with pytest.raises(DatabaseError):
            migrate(conn)


def test_findings_table_stores_no_file_contents(tmp_path: Path) -> None:
    path = init_db(tmp_path / "memory.db")
    with connect(path) as conn:
        columns = {
            row[1] for row in conn.execute("PRAGMA table_info(findings)").fetchall()
        }
    assert columns == {
        "repository_id",
        "id",
        "analyzer",
        "rule",
        "title",
        "description",
        "severity",
        "path",
        "locator",
        "fingerprint",
        "evidence",
        "recommendation",
        "first_seen",
        "last_seen",
    }


def test_findings_key_is_repository_scoped(tmp_path: Path) -> None:
    path = init_db(tmp_path / "memory.db")
    with connect(path) as conn:
        info = conn.execute("PRAGMA table_info(findings)").fetchall()
        key = {row["name"] for row in info if row["pk"] > 0}
        assert key == {"repository_id", "id"}


# Repository round-trips


def test_repository_round_trip(tmp_path: Path) -> None:
    path = init_db(tmp_path / "memory.db")
    with connect(path) as conn:
        assert get_repository(conn, "missing") is None
        repo_id = upsert_repository(conn, make_repo())
        stored = get_repository(conn, make_repo().key())
    assert stored == make_repo()
    assert isinstance(repo_id, int)


def test_repository_upsert_is_stable_per_key(tmp_path: Path) -> None:
    path = init_db(tmp_path / "memory.db")
    with connect(path) as conn:
        first = upsert_repository(conn, make_repo(), now="2026-01-01T00:00:00+00:00")
        second = upsert_repository(
            conn,
            Repository(root="/tmp/demo-repo", name="renamed"),
            now="2026-02-01T00:00:00+00:00",
        )
        assert first == second
        stored = get_repository(conn, make_repo().key())
        assert stored is not None and stored.name == "renamed"
        row = conn.execute(
            "SELECT first_seen, last_seen FROM repositories WHERE id = ?", (first,)
        ).fetchone()
        assert row["first_seen"] == "2026-01-01T00:00:00+00:00"
        assert row["last_seen"] == "2026-02-01T00:00:00+00:00"


# Run round-trips


def test_run_round_trip_and_listing(tmp_path: Path) -> None:
    path = init_db(tmp_path / "memory.db")
    with connect(path) as conn:
        assert get_run(conn, 999) is None
        repo_id = upsert_repository(conn, make_repo())
        first = create_run(conn, repo_id, RunStatus.COMPLETED, notes="first")
        second = create_run(conn, repo_id, RunStatus.PARTIAL)
        runs = list_runs(conn, repo_id)
        missing = get_run(conn, 999)
        reread = get_run(conn, first)
    assert [run.id for run in runs] == [first, second]
    assert missing is None
    assert reread == runs[0]
    assert runs[0].status is RunStatus.COMPLETED
    assert runs[0].notes == "first"
    assert runs[0].repository_key == make_repo().key()
    assert runs[1].status is RunStatus.PARTIAL
    assert reread == runs[0]
    assert isinstance(runs[0], AnalysisRun)


def test_create_run_rejects_bad_status(tmp_path: Path) -> None:
    path = init_db(tmp_path / "memory.db")
    with connect(path) as conn:
        repo_id = upsert_repository(conn, make_repo())
        with pytest.raises(ValidationError):
            create_run(conn, repo_id, "done")  # type: ignore[arg-type]


def test_create_run_for_missing_repository_fails(tmp_path: Path) -> None:
    path = init_db(tmp_path / "memory.db")
    with connect(path) as conn:
        with pytest.raises(DatabaseError):
            create_run(conn, 999, RunStatus.COMPLETED)


# Results, findings, observations


def test_full_observation_pipeline_round_trip(tmp_path: Path) -> None:
    path = init_db(tmp_path / "memory.db")
    with connect(path) as conn:
        run_id = seed_run(conn)
        result = AnalyzerResult(
            analyzer="security",
            status=AnalyzerStatus.SUCCESS,
            findings=(make_finding("key-b"), make_finding("key-a")),
            checks=("secret-scan",),
        )
        record_analyzer_result(conn, run_id, result)
        for finding in result.findings:
            record_observation(conn, run_id, finding)
        stored_results = get_results_for_run(conn, run_id)
        stored_findings = get_findings_for_run(conn, run_id)
        no_findings = get_findings_for_run(conn, 999)
        no_results = get_results_for_run(conn, 999)
    assert stored_results == [result]
    assert [f.id for f in stored_findings] == sorted(f.id for f in result.findings)
    assert no_findings == []
    assert no_results == []


def test_failed_and_partial_results_round_trip(tmp_path: Path) -> None:
    path = init_db(tmp_path / "memory.db")
    with connect(path) as conn:
        run_id = seed_run(conn)
        failed = AnalyzerResult(
            analyzer="git", status=AnalyzerStatus.FAILED, errors=("no git",)
        )
        partial = AnalyzerResult(
            analyzer="tests",
            status=AnalyzerStatus.PARTIAL,
            unavailable_evidence=("manifest unreadable",),
        )
        record_analyzer_result(conn, run_id, failed)
        record_analyzer_result(conn, run_id, partial)
        stored = get_results_for_run(conn, run_id)
    assert stored == [failed, partial]  # ordered by analyzer name


def test_observation_history_order(tmp_path: Path) -> None:
    path = init_db(tmp_path / "memory.db")
    with connect(path) as conn:
        repo_id = upsert_repository(conn, make_repo())
        run_a = create_run(conn, repo_id, RunStatus.COMPLETED)
        run_b = create_run(conn, repo_id, RunStatus.COMPLETED)
        finding = make_finding()
        record_observation(conn, run_a, finding)
        record_observation(
            conn, run_b, finding, EvidenceState.UNKNOWN, now="2026-03-01T00:00:00+00:00"
        )
        history = get_observations_for_finding(conn, finding.id)
        missing_history = get_observations_for_finding(conn, "rh1-0000000000000000")
    assert [(obs.run_id, obs.evidence_state) for obs in history] == [
        (run_a, EvidenceState.KNOWN),
        (run_b, EvidenceState.UNKNOWN),
    ]
    assert all(isinstance(obs, Observation) for obs in history)
    assert missing_history == []


def test_reobservation_is_idempotent(tmp_path: Path) -> None:
    path = init_db(tmp_path / "memory.db")
    with connect(path) as conn:
        run_id = seed_run(conn)
        finding = make_finding()
        record_observation(conn, run_id, finding)
        record_observation(conn, run_id, finding)
        assert len(get_findings_for_run(conn, run_id)) == 1
        assert len(get_observations_for_finding(conn, finding.id)) == 1


def test_finding_upsert_refreshes_last_seen(tmp_path: Path) -> None:
    path = init_db(tmp_path / "memory.db")
    with connect(path) as conn:
        repo_id = upsert_repository(conn, make_repo())
        run_id = create_run(conn, repo_id, RunStatus.COMPLETED)
        finding = make_finding()
        record_observation(conn, run_id, finding, now="2026-01-01T00:00:00+00:00")
        record_observation(conn, run_id, finding, now="2026-02-01T00:00:00+00:00")
        row = conn.execute(
            "SELECT first_seen, last_seen FROM findings WHERE id = ?", (finding.id,)
        ).fetchone()
        assert row["first_seen"] == "2026-01-01T00:00:00+00:00"
        assert row["last_seen"] == "2026-02-01T00:00:00+00:00"


def test_record_result_for_missing_run_fails(tmp_path: Path) -> None:
    path = init_db(tmp_path / "memory.db")
    with connect(path) as conn:
        result = AnalyzerResult(analyzer="code", status=AnalyzerStatus.SUCCESS)
        with pytest.raises(DatabaseError):
            record_analyzer_result(conn, 999, result)


def test_record_observation_rejects_bad_state(tmp_path: Path) -> None:
    path = init_db(tmp_path / "memory.db")
    with connect(path) as conn:
        run_id = seed_run(conn)
        with pytest.raises(ValidationError):
            record_observation(conn, run_id, make_finding(), "known")  # type: ignore[arg-type]


# Error handling


def test_corrupt_database_file_rejected(tmp_path: Path) -> None:
    path = tmp_path / "memory.db"
    path.write_text("not a database")
    with pytest.raises(DatabaseError):
        init_db(path)


def test_directory_as_database_rejected(tmp_path: Path) -> None:
    with pytest.raises(DatabaseError):
        init_db(tmp_path)


def test_readonly_connection(tmp_path: Path) -> None:
    path = init_db(tmp_path / "memory.db")
    with connect(path) as conn:
        run_id = seed_run(conn)
    with connect_readonly(path) as conn:
        assert get_run(conn, run_id) is not None
        with pytest.raises(DatabaseError):
            upsert_repository(conn, make_repo())
    with pytest.raises(DatabaseError):
        with connect_readonly(tmp_path / "missing.db"):
            pass


def test_storage_leaves_target_repositories_untouched(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    victim = target / "code.py"
    victim.write_text("print('hello')\n")
    before = (victim.stat().st_mtime_ns, victim.read_text())
    db_path = tmp_path / "db" / "memory.db"
    init_db(db_path)
    with connect(db_path) as conn:
        upsert_repository(conn, Repository(root=str(target)))
        run_id = create_run(conn, 1, RunStatus.COMPLETED)
        record_observation(conn, run_id, make_finding())
    assert (victim.stat().st_mtime_ns, victim.read_text()) == before
    assert list(target.iterdir()) == [victim]


def test_unusable_parent_directory_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("REPO_HEALTH_DB", "")
    blocker = tmp_path / "blocker"
    blocker.write_text("x")
    with pytest.raises(DatabaseError):
        init_db(blocker / "memory.db")
    assert os.environ.get("REPO_HEALTH_DB") == ""


# Cross-repository finding isolation (see docs/rules.md 16.6)


def test_same_finding_in_two_repositories_keeps_separate_details(
    tmp_path: Path,
) -> None:
    path = init_db(tmp_path / "memory.db")
    with connect(path) as conn:
        repo_a = upsert_repository(conn, Repository(root="/tmp/repo-a"))
        repo_b = upsert_repository(conn, Repository(root="/tmp/repo-b"))
        run_a = create_run(conn, repo_a, RunStatus.COMPLETED)
        run_b = create_run(conn, repo_b, RunStatus.COMPLETED)
        in_a = make_finding(evidence="evidence seen in repo A")
        in_b = make_finding(evidence="different evidence in repo B")
        assert in_a.id == in_b.id
        obs_a = record_observation(conn, run_a, in_a, now="2026-01-01T00:00:00+00:00")
        obs_b = record_observation(conn, run_b, in_b, now="2026-02-01T00:00:00+00:00")
        assert (obs_a.repository_id, obs_b.repository_id) == (repo_a, repo_b)
        seen_from_a = get_findings_for_run(conn, run_a)
        seen_from_b = get_findings_for_run(conn, run_b)
        history = get_observations_for_finding(conn, in_a.id)
        resolution_a = conn.execute(
            "SELECT evidence, first_seen, last_seen FROM findings"
            " WHERE repository_id = ? AND id = ?",
            (repo_a, in_a.id),
        ).fetchone()
        resolution_b = conn.execute(
            "SELECT evidence, first_seen, last_seen FROM findings"
            " WHERE repository_id = ? AND id = ?",
            (repo_b, in_a.id),
        ).fetchone()
    assert [finding.id for finding in seen_from_a] == [in_a.id]
    assert seen_from_a[0].evidence == "evidence seen in repo A"
    assert seen_from_b[0].evidence == "different evidence in repo B"
    assert resolution_a["evidence"] == "evidence seen in repo A"
    assert resolution_b["evidence"] == "different evidence in repo B"
    assert (
        resolution_a["first_seen"]
        == resolution_a["last_seen"]
        == ("2026-01-01T00:00:00+00:00")
    )
    assert (
        resolution_b["first_seen"]
        == resolution_b["last_seen"]
        == ("2026-02-01T00:00:00+00:00")
    )
    assert [(obs.run_id, obs.repository_id) for obs in history] == [
        (run_a, repo_a),
        (run_b, repo_b),
    ]


def test_migrate_v1_to_v2_scopes_shared_findings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        schema_module,
        "MIGRATIONS",
        ((1, "initial memory schema", schema_module._MIGRATION_1_SQL),),
    )
    monkeypatch.setattr(schema_module, "MEMORY_SCHEMA_VERSION", 1)
    path = init_db(tmp_path / "memory.db")
    finding_id = make_finding().id
    with connect(path) as conn:
        conn.execute(
            "INSERT INTO repositories (key, root, name, first_seen, last_seen)"
            " VALUES ('/tmp/repo-a', '/tmp/repo-a', 'repo-a',"
            " '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00'),"
            " ('/tmp/repo-b', '/tmp/repo-b', 'repo-b',"
            " '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')"
        )
        conn.execute(
            "INSERT INTO analysis_runs (repository_id, created_at, status)"
            " VALUES (1, '2026-01-01T00:00:00+00:00', 'completed'),"
            " (2, '2026-02-01T00:00:00+00:00', 'completed')"
        )
        conn.execute(
            "INSERT INTO findings (id, analyzer, rule, title, description,"
            " severity, path, locator, fingerprint, evidence, recommendation,"
            " first_seen, last_seen) VALUES (?, 'security',"
            " 'security.secret-pattern', 'Possible secret', 'Detected.', 'high',"
            " 'src/app.py', 'L10', 'key-a', 'shared evidence', '',"
            " '2026-01-01T00:00:00+00:00', '2026-02-01T00:00:00+00:00')",
            (finding_id,),
        )
        conn.execute(
            "INSERT INTO observations (run_id, finding_id, analyzer,"
            " evidence_state, observed_at) VALUES (1, ?, 'security', 'known',"
            " '2026-01-01T00:00:00+00:00'), (2, ?, 'security', 'known',"
            " '2026-02-01T00:00:00+00:00')",
            (finding_id, finding_id),
        )
    monkeypatch.undo()
    with connect(path) as conn:
        assert migrate(conn) == MEMORY_SCHEMA_VERSION
        rows = conn.execute(
            "SELECT repository_id, first_seen, last_seen FROM findings"
            " WHERE id = ? ORDER BY repository_id",
            (finding_id,),
        ).fetchall()
        assert [
            (row["repository_id"], row["first_seen"], row["last_seen"]) for row in rows
        ] == [
            (1, "2026-01-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00"),
            (2, "2026-02-01T00:00:00+00:00", "2026-02-01T00:00:00+00:00"),
        ]
        history = get_observations_for_finding(conn, finding_id)
        assert [(obs.run_id, obs.repository_id) for obs in history] == [(1, 1), (2, 2)]
        assert [f.id for f in get_findings_for_run(conn, 1)] == [finding_id]
        assert [f.id for f in get_findings_for_run(conn, 2)] == [finding_id]


def test_mismatched_observation_repository_rejected(tmp_path: Path) -> None:
    path = init_db(tmp_path / "memory.db")
    with connect(path) as conn:
        repo_a = upsert_repository(conn, Repository(root="/tmp/repo-a"))
        repo_b = upsert_repository(conn, Repository(root="/tmp/repo-b"))
        run_a = create_run(conn, repo_a, RunStatus.COMPLETED)
        finding = make_finding()
        record_observation(conn, run_a, finding)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO observations (run_id, repository_id, finding_id,"
                " analyzer, evidence_state, observed_at)"
                " VALUES (?, ?, ?, 'security', 'known', '2026-03-01T00:00:00+00:00')",
                (run_a, repo_b, finding.id),
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "UPDATE observations SET repository_id = ? WHERE run_id = ?",
                (repo_b, run_a),
            )
    with connect(path) as conn:
        assert len(get_observations_for_finding(conn, finding.id)) == 1
