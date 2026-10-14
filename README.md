# Repo Health

**A deterministic, evidence-driven repository health analyzer.**

Repo Health is designed to inspect software repositories, identify potential
issues, evaluate repository evidence, compare observations, and generate
actionable reports.

The project prioritizes correctness, reproducibility, traceability, and
maintainability over the number of checks performed.

> **Development status:** Early development. The architecture and behavioral
> contracts are being established before implementation. The capabilities
> described below are planned unless verified by working code and tests.

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

## Development Status

Repo Health is in early development. Documentation and engineering contracts
are being established before implementation.

The next phases are:

1. Review the architecture and behavioral specifications.
2. Verify compatibility requirements against existing project artifacts.
3. Define data models and component interfaces.
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
