# Repo Health

**A deterministic, evidence-driven repository health analyzer.**

Repo Health is designed to inspect software repositories, identify potential
issues, evaluate repository evidence, compare observations, and generate
actionable reports.

The project prioritizes correctness, reproducibility, traceability, and
maintainability over the number of checks performed.

> **Development status:** Early development. Only the capabilities listed
> under [Implemented to date](#implemented-to-date) are implemented and
> verified by code and tests. Everything else described below is planned.

## Project Goals

- Detect supported code quality and maintainability issues.
- Inspect Git metadata and repository structure.
- Analyze dependency manifests and configuration files.
- Identify supported security issues, including potential secrets.
- Evaluate documentation and architectural constraints.
- Compare repository observations using explicit evidence.
- Generate human-readable and machine-readable reports.
- Help developers understand findings and decide what to address.

## Core Principles

### Deterministic Analysis

Equivalent repository evidence and configuration should produce equivalent
substantive results.

### Evidence-Based Findings

Every finding must be supported by evidence. Unknown information must not be
treated as false, and unavailable evidence must not be treated as a successful
check.

### Read-Only by Default

Analysis must not modify the target repository, automatically fix files,
or execute arbitrary project scripts by default.

### Explicit Uncertainty

The system must distinguish successful analysis, partial analysis, failed
analysis, and checks that were not performed.

### Minimal Dependencies

Prefer the Python standard library where practical. External dependencies
must have a clear justification.

### Testability

Behavior must be verified through automated tests. A documented capability
is not considered implemented until its behavior is verified.

## Planned Architecture

The intended architecture separates repository discovery, analysis,
evidence comparison, data models, and reporting.

```text
Repository
    |
    v
Discovery
    |
    v
Analysis Engine
    |
    +--> Git Analyzer
    +--> Code Analyzer
    +--> Test Analyzer
    +--> Dependency Analyzer
    +--> Security Analyzer
    +--> Documentation Analyzer
    +--> Architecture Analyzer
    +--> Configuration Analyzer
    |
    v
Finding Collection
    |
    v
Report Generation
    |
    +--> Markdown
    +--> JSON
```

Historical comparison is a separate logical capability requiring explicit
observation and evidence contracts.

This diagram describes the intended design, not implemented functionality.

## Project Structure

See the repository tree for the current layout. The intended Python package
uses a `src/repo_health/` structure with separate modules for analyzers,
core services, discovery, intelligence, integrations, models, reports, and
utilities.

## Documentation

Read the project specifications before implementing new functionality.

| Document | Purpose |
|---|---|
| [AGENTS.md](AGENTS.md) | Instructions for AI coding agents |
| [Architecture](docs/architecture.md) | Component responsibilities and boundaries |
| [Analysis Rules](docs/rules.md) | Evidence semantics and finding lifecycle |
| [Configuration](docs/configuration.md) | Intended configuration contract |

## Technology

- **Language:** Python 3.12 or newer
- **Package layout:** `src/`-based Python package
- **Testing:** pytest
- **Code quality:** Ruff and mypy
- **Runtime dependencies:** None currently declared

Development tools are defined as optional dependencies in `pyproject.toml`.

## Usage

```bash
repo-health analyze /path/to/repo
repo-health analyze /path/to/repo --analyzers git security --no-persist
repo-health db init
repo-health db info
repo-health history --repo /path/to/repo
repo-health history --repo /path/to/repo --run 2 --baseline 1
repo-health regressions --repo /path/to/repo
```

`analyze` runs the engine and persists the observation to the memory
database (`REPO_HEALTH_DB` or `~/.local/share/repo-health/memory.db`
unless `--db-path` is given). Exit codes: `0` success (partial results
included), `1` analysis or operational failure, `2` usage or
configuration error. Every command supports `--help`.

## Implemented to date

Verified in code and tests; see `docs/rules.md` section 16 for the contracts.

- **Stage 1 — Core models and evidence contracts** (`src/repo_health/models/`):
  evidence states (`EvidenceState`: known / unknown / unavailable),
  stable finding identity algorithm v1 (`rh-finding-id-v1`), analyzer
  execution-result model (`AnalyzerResult` with
  success / partial / failed / not_run), and repository identity
  (representation and validation only).
- **Stage 2 — Persistent SQLite storage and migrations**
  (`src/repo_health/storage/`): versioned memory schema with idempotent,
  forward-only migrations over standard-library `sqlite3`; persists
  repositories, analysis runs, analyzer results, canonical findings keyed by
  `(repository_id, finding_id)`, and per-run observations with database-level
  integrity checks. No legacy schema-v3 compatibility is claimed
  (see `docs/rules.md` section 16.4).

- **Stage 3 — Repository and file discovery** (`src/repo_health/discovery/`,
  `src/repo_health/config.py`): deterministic glob engine, validated
  discovery configuration, repository-root resolution, read-only file
  enumeration with skip accounting, and extension-based language detection.
- **Stage 4 — Analysis engine and analyzers** (`src/repo_health/core/`,
  `src/repo_health/analyzers/`): explicit run context, deterministic
  engine with failure isolation, registry of the eight documented
  analyzers, and one documented check per analyzer
  (see `docs/rules.md` section 16.7).
- **Stage 5 — Command-line interface** (`src/repo_health/cli.py`):
  `analyze` and `db` commands over stdlib `argparse`, with documented
  exit codes (0 success, 1 failure, 2 usage error).

## Planned (not implemented)

The following are not implemented. The corresponding modules exist only as
empty placeholders; a directory or empty module does not establish that a
capability works.

- Analysis engine consumers: finding queries, comparison/regression
  logic, and report generation (Markdown, JSON, summaries).

## Development Status

Repo Health is in early development. Documentation and engineering contracts
are being established before implementation.

The next phases are:

1. Review the architecture and behavioral specifications.
2. Verify compatibility requirements against existing project artifacts.
   (Note: the legacy schema v3 definition is currently unavailable, so no
   schema-v3 compatibility is claimed; see `docs/rules.md` section 16.4.)
3. Define data models and component interfaces. (Stage 1 and Stage 2 complete;
   see [Implemented to date](#implemented-to-date).)
4. Implement the core and analyzers incrementally.
5. Add tests and verify behavior.
6. Implement reporting and user-facing workflows.

A directory or empty module does not establish that a capability works.

## Development Workflow

1. Read the relevant documentation.
2. Inspect existing implementation and tests.
3. Define expected behavior and failure cases.
4. Add or update tests.
5. Implement the smallest complete change.
6. Run relevant tests and quality checks.
7. Update documentation when behavior changes.

Never claim a test passed unless it was executed successfully.

## Safety and Limitations

Repo Health supports engineering review; it does not replace it.

A clean report does not prove that a repository is free of defects or security
vulnerabilities. Findings are limited by the checks performed, available
evidence, configured exclusions, and supported languages.

Repository content must be treated as untrusted input.

## License

The project is licensed under the [MIT License](LICENSE).
