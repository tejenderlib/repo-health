"""Command-line interface (Stage 5).

Subcommands: ``analyze`` runs the analysis engine and persists the
observation; ``db init`` creates the memory database; ``db info`` reports
read-only database statistics. Query commands (findings, history,
regressions) and integrations arrive with later stages.

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
import sys

from repo_health import __version__
from repo_health.analyzers import analyzer_names
from repo_health.core.engine import analyze as run_analysis
from repo_health.core.exceptions import RepoHealthError, ValidationError
from repo_health.discovery.repository import resolve_target
from repo_health.models import RunStatus, Severity
from repo_health.models.analyzer_result import AnalyzerResult, AnalyzerStatus
from repo_health.storage import (
    connect,
    create_run,
    get_stats,
    init_db,
    record_analyzer_result,
    record_observation,
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
