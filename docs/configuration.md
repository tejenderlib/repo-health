# Repo Health — Configuration Specification

## 1. Purpose

This document defines the intended configuration contract for Repo Health.

Configuration controls which supported checks run, which files are examined,
and how analysis results are presented.

Configuration must not weaken the project's fundamental requirements:
deterministic analysis, evidence-based findings, read-only operation, and
explicit handling of unavailable evidence.

This document describes intended behavior. A configuration option is not
implemented merely because it is documented here.

## 2. Configuration Principles

### 2.1 Explicit Defaults

Every supported option must have a documented default.

Defaults must be predictable and must not depend on the user's shell,
working directory, or unrelated environment variables.

### 2.2 Validation

Configuration must be validated before analysis begins.

Invalid values must produce actionable errors rather than being silently
ignored or interpreted differently.

### 2.3 Minimal Configuration

A user must be able to analyze a repository without creating a configuration
file.

Configuration should be introduced only when it provides meaningful control
over analysis behavior.

### 2.4 Safety Invariants

Configuration must never authorize the analyzer to:

- Modify files in the target repository.
- Automatically fix detected problems.
- Install dependencies into the target repository.
- Execute arbitrary repository scripts as part of static analysis by default.
- Reveal detected secrets in reports.
- Convert unavailable evidence into a successful check.

These constraints cannot be disabled through ordinary configuration.

## 3. Configuration Sources

The intended configuration sources are:

1. Built-in defaults.
2. An optional project configuration file.
3. Explicit command-line options.

When the same supported option is provided by multiple sources, the
precedence must be:

    Command-line option
            |
            v
    Project configuration
            |
            v
    Built-in default

Higher-precedence sources override lower-precedence sources only for the
specific option they define.

The exact configuration filename and supported file format must be
established before implementation.

Do not introduce multiple competing configuration formats without an
approved design decision.

## 4. Configuration Categories

The following categories describe intended configuration capabilities.

They are not a commitment to implement every possible option immediately.

### 4.1 General Options

Potential options include:

- Target repository path.
- Output directory.
- Output formats.
- Verbosity.
- Whether optional analysis categories are enabled.

Defaults must be suitable for ordinary local repository analysis.

### 4.2 File Discovery

Potential options include:

- Included file patterns.
- Excluded file patterns.
- Maximum file size.
- Supported language selection.

File discovery must remain deterministic.

Exclusions must not silently cause the system to report complete analysis
when relevant files were intentionally skipped.

### 4.3 Analyzer Selection

Users may eventually be able to enable or disable supported analyzers.

Examples include:

- Git analysis.
- Code analysis.
- Test analysis.
- Dependency analysis.
- Security analysis.
- Documentation analysis.
- Architecture analysis.
- Configuration analysis.

An analyzer that is disabled must be reported as not run, not as a successful
analysis with zero findings.

Analyzer names must be validated against the supported analyzer registry.

### 4.4 Architecture Rules

Architecture configuration may define explicit constraints, such as:

- Forbidden imports.
- Allowed dependency directions.
- Prohibited module dependencies.

Architecture rules must be documented and validated.

The analyzer must not invent project-specific constraints that were not
configured or otherwise established by an explicit, documented rule.

### 4.5 Output Options

Potential output options include:

- Markdown reports.
- JSON reports.
- Console summaries.
- Output file paths.

Output serialization must be stable for equivalent substantive results.

Volatile metadata, such as generation timestamps, must not unnecessarily
change deterministic content or finding identities.

## 5. Exclusions

Exclusion rules determine which files or directories are considered by
applicable analyzers.

Exclusions must have documented matching behavior.

### 5.1 Exclusion Requirements

- Matching must be deterministic.
- Patterns must be validated.
- Exclusion behavior must be covered by tests.
- Symlinks and filesystem boundaries must be handled explicitly.
- Exclusions must not be confused with verified absence of issues.

### 5.2 Reporting Exclusions

Where exclusions materially limit analysis coverage, the resulting report
must make that limitation clear.

For example, excluding dependency manifests means dependency analysis cannot
claim to have evaluated those manifests.

An exclusion must not silently turn an incomplete check into a successful
complete check.

### 5.3 Defaults

Default exclusions must be conservative and documented.

Do not automatically exclude a file merely because its contents appear
unusual or because an analyzer would otherwise report an issue.

The exact default patterns must be defined before implementation.

## 6. Paths and Filesystem Safety

Paths must be handled consistently across supported operating systems.

The implementation must distinguish:

- The repository root.
- Paths relative to the repository root.
- Absolute filesystem paths.
- Paths that resolve outside the intended analysis boundary.

Reports should prefer repository-relative paths when practical.

Symlink handling must follow the documented filesystem safety contract.

Configuration must not silently expand the analysis scope beyond the
user-selected repository.

## 7. Determinism

Equivalent repository evidence and effective configuration must produce
equivalent substantive analysis results.

Configuration must not introduce hidden nondeterminism through:

- Unordered collections.
- Unstable filesystem traversal.
- Random identifiers.
- Implicit environment-dependent defaults.
- Unspecified pattern precedence.

Where configuration affects analysis coverage, that configuration must be
available in the report metadata or associated observation.

## 8. Error Handling

Configuration errors must be distinguishable from analysis findings.

Examples include:

- Invalid option names.
- Invalid severity values.
- Malformed patterns.
- Unsupported output formats.
- Unknown analyzer names.
- Invalid filesystem paths.
- Unreadable configuration files.

Error messages should identify the relevant option and explain how to fix it.

The application must not silently discard invalid configuration.

## 9. Configuration and Evidence Semantics

Configuration determines which checks are requested and how they operate.

It does not establish that a check succeeded.

The analysis result must distinguish:

- A check that ran successfully.
- A check that ran partially.
- A check that failed.
- A check that was disabled.
- A check that could not obtain required evidence.

These states must follow the rules in `docs/rules.md`.

An excluded file or disabled analyzer must never be treated as proof that
the repository contains no relevant issues.

## 10. Compatibility

Configuration changes must be evaluated for compatibility.

- Do not silently reinterpret existing option values.
- Do not remove supported options without an explicit decision.
- Document defaults and precedence.
- Add tests for new options.
- Update the README when user-facing behavior changes.

The schema v3 compatibility requirements in `AGENTS.md` and `docs/rules.md`
must not be changed through configuration.

## 11. Testing Requirements

Configuration tests must cover:

- Built-in defaults.
- Valid project configuration.
- Command-line precedence.
- Invalid values.
- Unknown options.
- Invalid paths.
- Exclusion matching.
- Analyzer selection.
- Stable effective configuration.
- Safety invariants.
- Unavailable and partial evidence.
- Platform-sensitive path behavior where applicable.

Tests must use temporary directories and must not modify real target
repositories.

## 12. Implementation Workflow

Before implementing configuration:

1. Define the exact configuration filename and format.
2. Define the supported options and their types.
3. Establish defaults and precedence.
4. Define exclusion matching semantics.
5. Define validation errors.
6. Add tests for the configuration contract.
7. Implement configuration parsing and validation.
8. Update the README and relevant documentation.

Do not implement speculative options simply because they appear in this
document.

## 13. Implementation Status

This document describes intended configuration behavior.

It does not establish that configuration parsing, exclusions, analyzer
selection, or output options are already implemented.

Every supported option must be verified through code and automated tests.

## 14. Related Documents

- `AGENTS.md`: instructions for AI coding agents.
- `docs/architecture.md`: system architecture and component boundaries.
- `docs/rules.md`: evidence semantics and analysis rules.
- `README.md`: project overview and usage instructions.

