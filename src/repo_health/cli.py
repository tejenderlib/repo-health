"""Command-line interface (Stages 5 and 6).

Subcommands: ``analyze`` runs the analysis engine and persists the
observation; ``db init`` creates the memory database; ``db info`` reports
read-only database statistics; ``history`` shows runs and per-finding
lifecycle against a baseline; ``regressions`` reports new and reappeared
findings. Query commands exit 0 whenever the query succeeds, even when
regressions are found: their output is a report, not a verdict. Findings
queries and integrations arrive with later stages.

Exit codes:

* ``0`` — success. A run whose analyzers report PARTIAL still succeeds;
  partial analysis is not a failure.
* ``1`` — operational failure: at least one analyzer FAILED, the
  observation could not be persisted, or a database command failed.
* ``2`` — usage or configuration error: unknown commands, invalid
  options, unknown analyzer names, invalid targets, or unreadable paths.

Only Repo Health's own database may be created or modified, and only by
``analyze`` (without ``--no-persist``) and ``db init``. The target
repository is never modified.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys

from repo_health import __version__
from repo_health.analyzers import analyzer_names
from repo_health.core.engine import analyze as run_analysis
from repo_health.core.exceptions import RepoHealthError, ValidationError
from repo_health.discovery.repository import resolve_target
from repo_health.intelligence.regression import compare_runs, compare_to_previous
from repo_health.models import RunStatus, Severity
from repo_health.models.analyzer_result import AnalyzerResult, AnalyzerStatus
from repo_health.models.lifecycle import Lifecycle
from repo_health.storage import (
    connect,
    connect_readonly,
    create_run,
    get_repository_id,
    get_stats,
    init_db,
    list_runs,
    record_analyzer_result,
    record_observation,
    resolve_db_path,
    upsert_repository,
)

EXIT_OK = 0
EXIT_FAILURE = 1
EXIT_USAGE = 2


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level argument parser."""
    parser = argparse.ArgumentParser(
        prog="repo-health",
        description="Deterministic, evidence-driven repository health analyzer.",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    subparsers = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    analyze_parser = subparsers.add_parser(
        "analyze",
        help="analyze a repository and persist the observation",
        description="Run discovery and the analysis engine over a target, "
        "then persist the observation to the memory database.",
    )
    analyze_parser.add_argument(
        "target",
        nargs="?",
        default=".",
        help="repository root, directory, or file to analyze (default: .)",
    )
    analyze_parser.add_argument(
        "--analyzers",
        nargs="+",
        choices=analyzer_names(),
        metavar="ANALYZER",
        default=None,
        help="subset of analyzers to run (default: all)",
    )
    analyze_parser.add_argument(
        "--db-path",
        default=None,
        help="memory database path (default: REPO_HEALTH_DB or ~/.local/share/...)",
    )
    analyze_parser.add_argument(
        "--no-persist",
        action="store_true",
        help="run analysis without writing to the memory database",
    )
    analyze_parser.set_defaults(func=_cmd_analyze)

    db_parser = subparsers.add_parser(
        "db",
        help="manage the memory database",
        description="Initialize or inspect Repo Health's own SQLite database.",
    )
    db_subparsers = db_parser.add_subparsers(
        dest="db_command", required=True, metavar="DB_COMMAND"
    )
    db_init_parser = db_subparsers.add_parser(
        "init",
        help="create the memory database (repeatable)",
        description="Create parent directories, create tables, and apply "
        "pending migrations. Safe to run repeatedly.",
    )
    db_init_parser.add_argument("--db-path", default=None, help="database path")
    db_init_parser.set_defaults(func=_cmd_db_init)
    db_info_parser = db_subparsers.add_parser(
        "info",
        help="show read-only database statistics",
        description="Report the database path, schema version, and stored "
        "record counts without modifying anything.",
    )
    db_info_parser.add_argument("--db-path", default=None, help="database path")
    db_info_parser.set_defaults(func=_cmd_db_info)

    history_parser = subparsers.add_parser(
        "history",
        help="show analysis history for a repository",
        description="List stored runs, or classify one run's findings "
        "against a baseline run. Read-only.",
    )
    history_parser.add_argument(
        "--repo",
        default=".",
        help="repository path to inspect (default: .)",
    )
    history_parser.add_argument(
        "--run",
        type=int,
        default=None,
        help="run id to inspect (default: list runs)",
    )
    history_parser.add_argument(
        "--baseline",
        type=int,
        default=None,
        help="baseline run id (default: previous run)",
    )
    history_parser.add_argument("--db-path", default=None, help="database path")
    history_parser.set_defaults(func=_cmd_history)

    regressions_parser = subparsers.add_parser(
        "regressions",
        help="report new and reappeared findings",
        description="Compare a run against a baseline run and report findings "
        "classified NEW or REAPPEARED, with a full status summary. "
        "Read-only; exits 0 even when regressions are found.",
    )
    regressions_parser.add_argument(
        "--repo",
        default=".",
        help="repository path to inspect (default: .)",
    )
    regressions_parser.add_argument(
        "--run",
        type=int,
        default=None,
        help="current run id (default: latest run)",
    )
    regressions_parser.add_argument(
        "--baseline",
        type=int,
        default=None,
        help="baseline run id (default: previous run)",
    )
    regressions_parser.add_argument("--db-path", default=None, help="database path")
    regressions_parser.set_defaults(func=_cmd_regressions)
    return parser


def _run_status(results: list[AnalyzerResult]) -> RunStatus:
    if any(result.status is AnalyzerStatus.FAILED for result in results):
        return RunStatus.FAILED
    if any(result.status is AnalyzerStatus.PARTIAL for result in results):
        return RunStatus.PARTIAL
    return RunStatus.COMPLETED


def _finding_word(count: int) -> str:
    return "finding" if count == 1 else "findings"


def _cmd_analyze(args: argparse.Namespace) -> int:
    analyzers = tuple(args.analyzers) if args.analyzers is not None else None
    results = run_analysis(str(args.target), analyzers=analyzers)
    resolved = resolve_target(str(args.target))
    counts = {status: 0 for status in AnalyzerStatus}
    finding_total = 0
    severity_counts = {severity: 0 for severity in Severity}
    for result in results:
        counts[result.status] += 1
        finding_total += len(result.findings)
        for finding in result.findings:
            severity_counts[finding.severity] += 1
    status = _run_status(results)
    run_line: str | None = None
    db_path = ""
    if not args.no_persist:
        db_path = str(init_db(args.db_path))
        with connect(db_path) as conn:
            repo_id = upsert_repository(conn, resolved.root)
            run_id = create_run(conn, repo_id, status)
            for result in results:
                record_analyzer_result(conn, run_id, result)
                for finding in result.findings:
                    record_observation(conn, run_id, finding)
        run_line = f"run {run_id} ({status.value}) [db: {db_path}]"
    lines = [f"target: {args.target}"]
    for result in results:
        lines.append(
            f"  {result.analyzer}: {result.status.value}, "
            f"{len(result.findings)} {_finding_word(len(result.findings))}"
        )
    severity_breakdown = ", ".join(
        f"{severity.value}: {severity_counts[severity]}" for severity in Severity
    )
    lines.append(
        f"analyzers: {counts[AnalyzerStatus.SUCCESS]} success, "
        f"{counts[AnalyzerStatus.PARTIAL]} partial, "
        f"{counts[AnalyzerStatus.FAILED]} failed; "
        f"findings: {finding_total} ({severity_breakdown})"
    )
    lines.append(run_line if run_line is not None else "run not persisted")
    print("\n".join(lines))
    if status is RunStatus.FAILED:
        return EXIT_FAILURE
    return EXIT_OK


def _cmd_db_init(args: argparse.Namespace) -> int:
    path = init_db(args.db_path)
    print(f"initialized: {path}")
    return EXIT_OK


def _cmd_db_info(args: argparse.Namespace) -> int:
    stats = get_stats(args.db_path)
    print(f"path: {stats.path}")
    print(f"schema_version: {stats.schema_version}")
    print(f"repositories: {stats.repositories}")
    print(f"runs: {stats.runs}")
    print(f"analyzer_results: {stats.analyzer_results}")
    print(f"findings: {stats.findings}")
    print(f"observations: {stats.observations}")
    return EXIT_OK


def _resolve_history_repo(conn: sqlite3.Connection, repo: str) -> int:
    resolved = resolve_target(repo)
    repo_id = get_repository_id(conn, resolved.root.key())
    if repo_id is None:
        raise ValidationError(f"no history for {repo!r}: run analyze first")
    return repo_id


def _select_runs(
    run_ids: list[int], run: int | None, baseline: int | None
) -> tuple[int, int | None]:
    current = run if run is not None else run_ids[-1]
    if current not in run_ids:
        raise ValidationError(f"unknown run {current}")
    if baseline is not None:
        if baseline not in run_ids:
            raise ValidationError(f"unknown run {baseline}")
        if baseline >= current:
            raise ValidationError(
                f"baseline run {baseline} must precede run {current}"
            )
    return current, baseline


def _run_rows(conn: sqlite3.Connection, repo_id: int) -> list[tuple[int, str, str]]:
    return [
        (run.id, run.status.value, run.created_at)
        for run in list_runs(conn, repo_id)
        if run.id is not None
    ]


def _cmd_history(args: argparse.Namespace) -> int:
    with connect_readonly(resolve_db_path(args.db_path)) as conn:
        repo_id = _resolve_history_repo(conn, str(args.repo))
        rows = _run_rows(conn, repo_id)
        lines = [f"repo: {args.repo}"]
        if not rows:
            lines.append("no runs")
            print("\n".join(lines))
            return EXIT_OK
        if args.run is None and args.baseline is None:
            for run_id, status, created in rows:
                lines.append(f"run {run_id} ({status}) {created}")
            print("\n".join(lines))
            return EXIT_OK
        current, baseline = _select_runs(
            [run_id for run_id, _, _ in rows], args.run, args.baseline
        )
        if baseline is None:
            lifecycles = compare_to_previous(conn, repo_id, current)
            lines.append(f"run {current} vs previous run")
        else:
            lifecycles = compare_runs(conn, repo_id, current, baseline)
            lines.append(f"run {current} vs baseline run {baseline}")
        for item in lifecycles:
            lines.append(
                f"{item.finding_id} {item.analyzer} "
                f"{item.lifecycle.value}: {item.reason}"
            )
        print("\n".join(lines))
        return EXIT_OK


def _cmd_regressions(args: argparse.Namespace) -> int:
    order = (
        Lifecycle.NEW,
        Lifecycle.RECURRING,
        Lifecycle.RESOLVED,
        Lifecycle.REAPPEARED,
        Lifecycle.INDETERMINATE,
    )
    with connect_readonly(resolve_db_path(args.db_path)) as conn:
        repo_id = _resolve_history_repo(conn, str(args.repo))
        rows = _run_rows(conn, repo_id)
        lines = [f"repo: {args.repo}"]
        if not rows:
            lines.append("no runs")
            print("\n".join(lines))
            return EXIT_OK
        current, baseline = _select_runs(
            [run_id for run_id, _, _ in rows], args.run, args.baseline
        )
        if baseline is None:
            lifecycles = compare_to_previous(conn, repo_id, current)
            label = "previous run"
        else:
            lifecycles = compare_runs(conn, repo_id, current, baseline)
            label = f"baseline run {baseline}"
        counts = {lifecycle: 0 for lifecycle in order}
        for item in lifecycles:
            counts[item.lifecycle] += 1
        lines.append(
            f"run {current} vs {label}: {counts[Lifecycle.NEW]} new, "
            f"{counts[Lifecycle.REAPPEARED]} reappeared "
            f"({counts[Lifecycle.RECURRING]} recurring, "
            f"{counts[Lifecycle.RESOLVED]} resolved, "
            f"{counts[Lifecycle.INDETERMINATE]} indeterminate)"
        )
        shown = [
            item
            for item in lifecycles
            if item.lifecycle in (Lifecycle.NEW, Lifecycle.REAPPEARED)
        ]
        if not shown:
            lines.append("no regressions")
        for item in shown:
            lines.append(
                f"{item.finding_id} {item.analyzer} "
                f"{item.lifecycle.value}: {item.reason}"
            )
        print("\n".join(lines))
        return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    """Run the CLI; return the process exit code (never raises SystemExit)."""
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        if isinstance(exc.code, int):
            return exc.code
        return EXIT_USAGE
    try:
        code = args.func(args)
    except ValidationError as exc:
        print(f"repo-health: error: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except RepoHealthError as exc:
        print(f"repo-health: error: {exc}", file=sys.stderr)
        return EXIT_FAILURE
    return int(code)


if __name__ == "__main__":  # pragma: no cover - exercised via main()
    raise SystemExit(main())
