# Repo Health — Architecture

## 1. Purpose

Repo Health is a repository analysis system designed to collect evidence,
identify potential issues, compare observations, and generate actionable
reports.

The architecture prioritizes:

- Deterministic behavior.
- Evidence-backed findings.
- Read-only repository analysis.
- Explicit component boundaries.
- Reproducible results.
- Minimal dependencies.
- Testability and maintainability.

This document defines the intended architecture. A documented component
must not be considered implemented until its code and tests exist.

## 2. Architectural Principles

### 2.1 Deterministic Core

Given equivalent repository evidence and configuration, analysis and
comparison must produce equivalent substantive results.

The core must not depend on language models, network services, randomness,
or implicit global state.

### 2.2 Evidence Before Interpretation

Analyzers collect evidence and produce findings supported by that evidence.

The system must distinguish verified facts from unknown or unavailable
information.

Reports must not invent findings or claim causality without supporting
evidence.

### 2.3 Read-Only Analysis

The target repository must not be modified during analysis.

Repository inspection must not automatically fix files, install packages,
or execute arbitrary project code.

### 2.4 Separation of Responsibilities

Each component has a defined responsibility and communicates through
explicit interfaces and shared data models.

A component must not duplicate another component's responsibilities.

## 3. High-Level Data Flow

The intended analysis pipeline is:

    User
      |
      v
    CLI
      |
      v
    Repository Discovery
      |
      v
    Analysis Engine
      |
      +----> Git Analyzer
      +----> Code Analyzer
      +----> Test Analyzer
      +----> Dependency Analyzer
      +----> Security Analyzer
      +----> Documentation Analyzer
      +----> Architecture Analyzer
      +----> Configuration Analyzer
      |
      v
    Finding Collection
      |
      v
    Report Model
      |
      +----> Markdown Output
      +----> JSON Output

Repository comparison and historical analysis form a separate logical
capability. They must use explicit observations and evidence rather than
guessing from missing data.

This diagram describes the intended design, not a claim that the pipeline
is already implemented.

## 4. Module Responsibilities

### 4.1 CLI — `cli.py` and `__main__.py`

Responsibilities:

- Parse user commands and arguments.
- Validate command-line inputs.
- Invoke the appropriate application workflow.
- Display results and actionable errors.
- Return appropriate process exit codes.

The CLI must not contain analyzer-specific detection logic.

Implemented in Stage 5: `main(argv) -> int` with `analyze` and `db`
subcommands over stdlib `argparse`. Exit codes: 0 success (partial
results included), 1 operational or analysis failure, 2 usage or
configuration error. Query commands arrive with later stages.

### 4.2 Configuration — `config.py`

Responsibilities:

- Define supported configuration options.
- Validate configuration values.
- Provide explicit defaults.
- Represent exclusions and analysis settings.

Configuration must not silently override documented safety constraints.

### 4.3 Core — `core/`

#### `engine.py`

Coordinates repository analysis.

It invokes the appropriate discovery and analysis components, collects
their results, and constructs the analysis output.

It must not implement individual security, Git, or code-detection rules.

Implemented in Stage 4: `analyze()` runs discovery once, invokes the
selected registered analyzers in order with independent failure
isolation, and returns their results. See `docs/rules.md` section 16.7.

#### `context.py`

Contains the explicit context needed during an analysis run.

It must not become an unrestricted container for mutable global state.

Implemented in Stage 4 as the frozen `AnalysisContext` (resolved target,
discovery result, configuration).

#### `exceptions.py`

Defines application-specific exceptions for expected error conditions.

Errors must remain distinguishable from successful analysis with zero
findings.

### 4.4 Discovery — `discovery/`

#### `repository.py`

Identifies and validates the repository being analyzed.

#### `files.py`

Discovers eligible files while respecting exclusions and filesystem
safety requirements.

#### `languages.py`

Identifies supported languages using explicit, documented detection rules.

Discovery must handle unreadable files, symlinks, and unsupported inputs
without silently misrepresenting the results.

### 4.5 Analyzers — `analyzers/`

Each analyzer examines a defined category of repository evidence.

- `git.py`: repository state, history, and Git metadata.
- `code.py`: supported static code checks.
- `tests.py`: test structure and available test evidence.
- `dependencies.py`: dependency manifests and related metadata.
- `security.py`: supported security checks, including secret detection.
- `documentation.py`: documentation presence and consistency checks.
- `architecture.py`: explicitly configured architectural constraints.
- `configuration.py`: project configuration checks.

Analyzers must:

- Have clear inputs and outputs.
- Produce findings using the shared finding model.
- Identify the evidence supporting their findings.
- Handle unsupported or unavailable evidence explicitly.
- Avoid modifying the target repository.
- Avoid silently treating analysis failures as clean results.

Each analyzer must have focused tests.

Implemented in Stage 4 with one documented check per analyzer; the
registry in `analyzers/__init__.py` holds the eight documented analyzers
in run order. See `docs/rules.md` section 16.7 for the v1 check set.

### 4.6 Intelligence — `intelligence/`

This package contains higher-level reasoning over collected evidence.

#### `correlation.py`

Identifies relationships between findings when supported by explicit rules.

#### `hotspots.py`

Identifies areas of elevated maintenance or change activity using
documented metrics.

#### `impact.py`

Describes supported relationships between changes and affected components.

It must not claim causality without sufficient evidence.

#### `regression.py`

Compares observations to identify new, recurring, resolved, and reappearing
findings when the available evidence supports those classifications.

Missing or incomplete evidence must not automatically imply resolution.

#### `scoring.py`

Provides only explicitly defined, documented scoring calculations.

No unsupported risk score or opaque heuristic may be introduced without
an approved design and validation strategy.

### 4.7 Models — `models/`

Shared data contracts are defined here.

- `finding.py`: finding identity, severity, description, location, and evidence.
  Implements the v1 identity algorithm and severity levels from `docs/rules.md`
  section 16.
- `evidence.py`: the `EvidenceState` (KNOWN/UNKNOWN/UNAVAILABLE) representation
  from `docs/rules.md` section 16.
- `analyzer_result.py`: the analyzer execution-result model (`AnalyzerStatus`
  plus findings, checks, uncovered checks, unavailable evidence, and errors)
  from `docs/rules.md` section 16.
- `repository.py`: repository identity and metadata (Stage 1: representation
  and validation only; persistence and cross-checkout matching are Stage 2).
- `report.py`: analysis results and report metadata (reserved for Stage 8;
  currently unimplemented).

Models must validate their invariants and avoid depending on the CLI or
presentation layer.

Evidence states and finding lifecycle classifications must follow
`docs/rules.md`.

Any persisted observation must follow the approved schema compatibility
contract.

### 4.8 Reports — `reports/`

#### `markdown.py`

Produces human-readable Markdown reports.

#### `json_report.py`

Produces machine-readable JSON output using a stable, documented structure.

#### `summary.py`

Produces concise summaries derived from actual analysis results.

Presentation code must not invent findings, alter severity, or reinterpret
evidence.

### 4.9 Integrations — `integrations/`

Provides optional integration points for external coding agents such as
Claude, Codex, and OpenCode.

Integrations must remain separate from the deterministic analysis core.

No external AI service may become a mandatory runtime dependency.

### 4.10 Utilities — `utils/`

#### `git_cli.py`

Provides a controlled interface to Git operations.

#### `filesystem.py`

Provides shared filesystem inspection utilities.

#### `logging.py`

Provides consistent application logging.

Utilities must remain focused and must not become a second application
orchestration layer.

### 4.11 Storage — `storage/`

Persists engineering memory in SQLite (standard library only).

- `paths.py`: resolves the database location (explicit argument, then
  `REPO_HEALTH_DB`, then `~/.local/share/repo-health/memory.db`).
- `schema.py`: the versioned memory schema and forward-only migrations.
  The current version is memory schema v1, which makes no schema-v3
  compatibility claim (see `docs/rules.md` section 16).
- `db.py`: connections and idempotent initialization. Only Repo Health's
  own database file may be created or modified.
- `records.py`: persistence of repositories, analysis runs, analyzer
  execution results (including unavailable-evidence records), canonical
  findings, and per-run observations.

Storage must never read or write target repositories, never store entire
source files, and never become an analysis or presentation layer.

Canonical finding rows are scoped per repository via the composite
`(repository_id, finding_id)` key, so identical findings in different
repositories keep independent details and timestamps while sharing the
stable Stage 1 finding id. Observations additionally carry a composite
foreign key against their run's repository, so run/repository mismatches
are rejected by the database itself. See `docs/rules.md` section 16.6.

## 5. Dependency Direction

The intended dependency direction is:

    CLI and Integrations
            |
            v
       Core Services
            |
            v
    Discovery and Analyzers
            |
            v
       Shared Models

Reporting consumes the shared models and analysis results.

Shared models must not import the CLI, analyzers, or reporting modules.

Utilities must not import application-level components.

Dependencies between modules must remain explicit and avoid circular imports.

## 6. Error Handling

The system must distinguish:

- Successful analysis with findings.
- Successful analysis with no findings.
- Partial analysis with unavailable evidence.
- Failed analysis.

Errors must not be converted into empty results merely to keep a pipeline
running.

Where safe, independent analyzers may continue after another analyzer fails.
The final result must preserve the failure information.

## 7. Determinism and Reproducibility

The system must:

- Sort findings and discovered paths deterministically.
- Use stable identifiers where the identity contract permits.
- Serialize data consistently.
- Make configuration-dependent behavior explicit.
- Avoid embedding volatile timestamps into deterministic content.
- Keep environment-specific information out of stable identifiers.

Timestamps may be recorded as metadata, but must not silently change the
substantive analysis result.

## 8. Testing Strategy

Testing is organized into three levels.

### Unit Tests

Verify individual models, utilities, analyzers, and comparison rules.

### Integration Tests

Verify interactions between discovery, analysis, models, and reporting.

### End-to-End Tests

Verify user-facing workflows through the CLI using controlled repository
fixtures.

Tests must cover normal behavior, invalid inputs, unavailable evidence,
partial failures, and deterministic output.

Tests must never modify a real repository as a side effect.

## 9. Scope and Implementation Status

This document describes the intended architecture.

A file or directory existing in the repository does not establish that its
functionality is implemented.

Before implementing a component:

1. Define its contract.
2. Identify the relevant evidence and failure states.
3. Define expected behavior with tests.
4. Implement the smallest complete solution.
5. Verify the tests.
6. Update documentation when the design or behavior changes.

## 10. Related Documents

- `AGENTS.md`: coding-agent instructions and engineering constraints.
- `docs/rules.md`: evidence semantics, finding rules, and comparison behavior.
- `docs/configuration.md`: configuration contract.
- `README.md`: project overview and user documentation.
