# Repo Health — Analysis and Evidence Rules

## 1. Purpose

This document defines how Repo Health interprets evidence, produces findings,
classifies finding severity, and compares repository observations.

These rules are normative: implementations must follow them.

If a rule is not implemented, do not claim that the corresponding capability
is operational.

## 2. Fundamental Principles

### 2.1 Evidence-Based Results

Every finding must be supported by evidence obtained during analysis.

A finding must identify its analyzer and provide enough information to
understand what was detected and where applicable, where it was detected.

Never fabricate evidence or claim that a check succeeded when it did not run.

### 2.2 Determinism

Equivalent evidence and configuration must produce equivalent substantive
results.

Implementations must use stable ordering and explicit comparison rules.

Do not rely on random identifiers, filesystem traversal order, or unstable
environment-specific values for substantive results.

### 2.3 Conservative Interpretation

When evidence is insufficient, preserve uncertainty.

Do not silently interpret missing evidence as proof that an issue does not
exist.

Do not infer causality merely because two events occurred together.

## 3. Evidence States

Evidence-dependent operations must distinguish the following states.

### KNOWN

Sufficient evidence is available to establish the relevant fact.

Examples:

- A file was successfully read and contains a detected secret pattern.
- A supported configuration explicitly forbids a particular dependency.
- A finding was observed by a successfully executed analyzer.

### UNKNOWN

Available information does not establish the relevant fact.

Examples:

- A baseline observation lacks sufficient information to identify a finding.
- A comparison cannot establish whether an issue existed previously.
- A dependency relationship cannot be established from the available files.

UNKNOWN does not mean false.

### UNAVAILABLE

Required evidence could not be obtained or evaluated.

Examples:

- A required file could not be read.
- Git metadata is unavailable for a Git-dependent check.
- An analyzer could not execute because a required capability is missing.

UNAVAILABLE does not mean that the repository is unhealthy or healthy by itself.

### State Handling Rules

- Never treat UNKNOWN as KNOWN.
- Never treat UNAVAILABLE as a successful check.
- Never treat missing evidence as verified absence.
- Preserve the reason evidence is unavailable when possible.
- Propagate uncertainty when downstream conclusions depend on it.

These are semantic states. Their exact Python representation must be defined
in the implementation contract before implementation.

## 4. Finding Contract

A finding represents an issue or observation supported by analysis evidence.

A finding should contain:

- A stable finding identifier.
- A rule or analyzer identifier.
- A human-readable title.
- A clear description.
- A severity classification.
- A file path or location when applicable.
- Evidence supporting the finding.
- A recommendation when a meaningful recommendation exists.

Optional information must remain optional when the analyzer cannot establish it.

### Finding Identity

Finding identity must be stable across equivalent observations.

Identity must not depend on:

- The current wall-clock time.
- A randomly generated identifier.
- The order in which files were discovered.
- An absolute checkout path when that path is irrelevant to the rule.

Identity design must distinguish separate occurrences of the same rule where
necessary.

The exact identity algorithm must be documented and tested before it is
implemented.

### Finding Evidence

Evidence must be traceable to the relevant observation.

Do not include secrets, credentials, or unnecessary sensitive values in
reports.

Secret detection must avoid reproducing the full detected secret in output.

## 5. Severity Levels

The intended severity levels are:

| Severity | Meaning |
|---|---|
| CRITICAL | A verified issue with potentially severe consequences that requires urgent attention. |
| HIGH | A verified, significant issue requiring prompt attention. |
| MEDIUM | A meaningful issue that should be addressed. |
| LOW | A minor issue or maintainability concern. |
| INFO | An informational observation that is not necessarily a defect. |

Severity must follow documented rule-specific criteria.

Do not assign severity based solely on vague intuition or unsupported
assumptions.

Severity describes an established finding; it does not measure uncertainty.

## 6. Analyzer Execution Results

Every analyzer execution must be distinguishable from its findings.

Conceptually, an analyzer result must communicate:

- Which analyzer ran.
- Whether execution succeeded, partially succeeded, or failed.
- Which findings were produced.
- Which checks were performed.
- Which checks could not be completed.
- What relevant evidence was unavailable.

The exact result model must be established before analyzer implementation.

### Successful Execution

A successful analyzer may produce findings or no findings.

Zero findings means only that the executed checks produced no findings within
their documented scope.

It does not establish that the entire repository is free of defects.

### Partial Execution

A partially completed analyzer must identify the checks or evidence that
were unavailable.

It must not present its output as a complete evaluation.

### Failed Execution

A failed analyzer must preserve the failure information.

An execution failure must never be converted into a successful result with
zero findings.

## 7. Observation Comparison

Comparison evaluates evidence from distinct observations.

A comparison must not assume that every observation is complete.

### Required Distinctions

- Observed: sufficient evidence establishes that the finding exists.
- Not observed: a successfully executed, sufficiently complete check did not
  report the finding.
- Unknown: available evidence cannot establish whether the finding exists.
- Unavailable: the required check or evidence could not be obtained.

Not observed is not universally equivalent to resolved.

### Comparison Requirements

- Compare equivalent rule identities and compatible evidence.
- Account for analyzer execution status and coverage.
- Preserve missing or incomplete evidence.
- Avoid treating incompatible observations as directly comparable.
- Record the reasons for indeterminate comparisons where possible.

## 8. Finding Lifecycle

The intended lifecycle classifications are:

### NEW

A finding is NEW when it is observed in the current observation and sufficient
comparable baseline evidence establishes that it was not present previously.

### RECURRING

A finding is RECURRING when it is observed in the current observation and
compatible historical evidence establishes that it was already present.

### RESOLVED

A finding is RESOLVED only when the current observation provides sufficient
evidence that the previously observed issue is no longer present under the
same applicable rule.

The relevant analyzer must have executed successfully with sufficient
coverage.

### REAPPEARED

A finding is REAPPEARED when compatible historical evidence establishes that
the same finding existed, was subsequently resolved, and is now observed again.

### INDETERMINATE

A lifecycle classification is INDETERMINATE when the available evidence
cannot support another classification.

Examples include:

- Missing baseline observations.
- An unavailable analyzer.
- Incomplete analysis coverage.
- Incompatible rule versions.
- An insufficiently stable finding identity.

### Lifecycle Safety Rules

- Missing baseline evidence must not produce NEW automatically.
- Missing current evidence must not produce RESOLVED.
- An analyzer failure must not produce RESOLVED.
- A finding must not be classified as REAPPEARED without evidence of a
  previous occurrence and an intervening resolution.
- Historical states must be derived from actual observations, never invented.

## 9. Schema Compatibility

The previously established evidence and comparison contract uses schema v3.

- Preserve schema v3 compatibility.
- Do not silently change existing field meanings.
- Do not silently remove or rename existing fields.
- Do not assume that a new schema version is authorized.
- Test compatibility against existing valid schema v3 fixtures when available.
- Document any explicitly approved migration before implementing it.

If the original schema v3 definition or fixtures are unavailable, identify
that gap before implementing persistence or migration behavior.

## 10. Security and Privacy

- Never expose full secrets in findings or reports.
- Avoid unnecessarily collecting environment variables or sensitive files.
- Do not execute repository scripts as part of static analysis by default.
- Do not install dependencies into the target repository automatically.
- Do not modify the target repository during analysis.
- Treat repository content as untrusted input.
- Handle symbolic links and filesystem boundaries explicitly.
- Do not claim a security check is complete if its scope is limited.

## 11. Architecture Rules

Architecture checks must use explicit, documented constraints.

Examples include:

- A module must not import a forbidden package.
- A lower-level package must not depend on a higher-level package.
- A module must not introduce a prohibited dependency direction.

Do not invent architectural constraints based on naming conventions alone
unless those conventions have been explicitly configured as rules.

## 12. Scoring and Aggregation

Any future scoring mechanism must have an explicit, documented formula.

A score must not imply certainty that the underlying evidence does not support.

Do not introduce arbitrary weights, opaque risk scores, or causal claims
without an approved specification and tests.

A score must not conceal analyzer failures or unavailable evidence.

## 13. Testing Requirements

Tests must cover:

- Each supported evidence state.
- Empty and invalid inputs.
- Deterministic finding identity.
- Deterministic ordering and serialization.
- Analyzer failures and partial execution.
- Missing baseline and current observations.
- Every supported lifecycle transition.
- Schema v3 compatibility where applicable.
- Secret redaction.
- Symlink and filesystem-boundary behavior.
- Incompatible observations.
- Unknown and unavailable evidence propagation.

Tests must assert both correct classifications and the prevention of
unsupported classifications.

## 14. Change Control

Before changing a rule:

1. Explain why the existing rule is insufficient.
2. Identify affected analyzers, models, reports, and persisted observations.
3. Define expected behavior with tests.
4. Assess schema compatibility.
5. Update this document and related architecture documentation.
6. Obtain approval for changes to established contracts.

Never weaken an evidence rule merely to make an implementation easier.

## 15. Implementation Status

This document specifies intended behavior.

It does not establish that any analyzer, evidence state, lifecycle transition,
or schema compatibility mechanism has already been implemented.

Each capability must be verified through code inspection and automated tests.

## 16. Stage 1 Implementation Contract (Implemented)

This section records the contracts implemented in Stage 1 (core models).
It does not change the normative rules above; it fixes their Python
representation.

### 16.1 Evidence-state representation

Evidence states are represented by `models.evidence.EvidenceState`, a
string enum with values `known`, `unknown`, and `unavailable`.
`models.evidence.is_established()` returns True only for KNOWN.

### 16.2 Stable finding identity algorithm v1

Finding ids use algorithm `rh-finding-id-v1` (see
`models.finding.compute_finding_id`): the SHA-256 hex digest (first 16
characters, prefixed `rh1-`) of
`rh-finding-id-v1|<analyzer>|<rule>|<canonical path>|<locator>|<fingerprint>`,
where the path is canonicalized to a repo-relative POSIX form. The id
depends only on stable rule evidence, never on timestamps, random values,
discovery order, or absolute checkout paths. A supplied id that does not
match the components is rejected. Changing the algorithm requires a new
algorithm name so old and new ids cannot be confused.

### 16.3 Analyzer execution-result model

Analyzer outcomes are represented by `models.analyzer_result.AnalyzerResult`
with status `AnalyzerStatus` (`success`, `partial`, `failed`, `not_run`).
A FAILED result must preserve error information; a PARTIAL result must
identify uncovered checks or unavailable evidence; a NOT_RUN result reports
no findings. Findings are stored sorted by id for deterministic output.

### 16.4 Schema v3 limitation

The previously established schema v3 definition and its fixtures are
currently unavailable. Therefore **no schema-v3 compatibility is claimed**
by this implementation. Persisted formats are defined as a new memory
schema (see section 16.5), and this limitation must be revisited when the
v3 definition becomes available. No finding, report, or database format may
be described as schema-v3 compatible until that happens.

### 16.5 Memory schema v3 (Stage 2, implemented)

Persistent memory uses standard-library `sqlite3` at
`~/.local/share/repo-health/memory.db` by default (explicit path, then
`REPO_HEALTH_DB`, then the default). The schema versions itself
independently as memory schema v3 via a `migrations` table plus the
`user_version` pragma; creation and migration are idempotent. (This
"memory schema" versioning is unrelated to the unavailable legacy
schema v3: no legacy-schema-v3 compatibility is claimed.)

Tables: `repositories` (identity per Stage 1 repository key),
`analysis_runs` (one engine execution, with a unique
`(repository_id, id)` index), `analyzer_results` (status plus
checks, uncovered checks, unavailable evidence, and errors as sorted JSON
arrays), `findings` (canonical finding fields keyed by the composite
`(repository_id, finding_id)`; see section 16.6), and `observations`
(`run_id`, `repository_id`, `finding_id`, analyzer, evidence state).

Integrity beyond single-table keys is enforced by the database itself:
`observations` carries composite foreign keys to both `findings` and
`analysis_runs`, so an observation whose `repository_id` disagrees with
its run's repository is rejected by SQLite. A v1 database with
inconsistent rows would fail migration loudly rather than silently.

The findings table stores finding descriptions and short evidence
summaries only. Entire source files are never stored, and secret values
must never be stored; redaction remains the analyzers' responsibility
(section 10). Cross-checkout repository matching is deferred: the v2
repository key is still the normalized absolute root. Timestamps are UTC
ISO-8601 metadata and never affect finding identity. Each migration runs
in its own transaction and rolls back fully on failure (no partial schema
or migration records remain).

### 16.6 Cross-repository finding isolation (implemented in schema v2,
enforced in schema v3)

Determination: Stage 1 finding ids are intentionally repository-independent
(stable across checkouts, which history comparison needs), so the same
finding content in two different repositories yields the same stable id.
Under memory schema v1 the `findings` table was keyed by that id alone,
so identical findings in different repositories shared one canonical row.
That defect is fixed: since schema v2, canonical findings are keyed by
the composite `(repository_id, finding_id)`, and `observations` carries
`repository_id` with a composite foreign key to it. Schema v3 additionally
constrains `observations` against `analysis_runs`, so a mismatch between
an observation's repository and its run's repository is rejected by the
database. The Stage 1 identity algorithm is unchanged. Per-run
observations (history) were and remain keyed by run.

Migration v1 to v2 splits any previously shared canonical row into one
row per observing repository, recovering per-repository `first_seen` and
`last_seen` from that repository's observation timestamps. Canonical
detail text already conflated across repositories cannot be unmixed and
is carried into each split row as-is; this is recorded here rather than
hidden. A passing regression test locks the isolated behavior.

### 16.7 Analysis engine and analyzer checks v1 (Stage 4, implemented)

The engine (`core/engine.py`) runs discovery once, then invokes each
selected analyzer independently against an explicit `AnalysisContext`
(target, discovery result, configuration). Analyzers run in the requested
order (registry order by default); an analyzer that raises, returns a
non-result, or returns another analyzer's result becomes a FAILED result
with preserved failure information. Target and configuration errors raise
`ValidationError` before any analyzer runs.

Analyzer checks v1 (one documented check each; criteria in each module):

- `git` (`git-presence`): INFO presence observation, or PARTIAL when the
  target is not a Git repository. No history parsing, no subprocess.
  Discovery file skips cannot affect this check.
- `security` (`secret-pattern-scan`): HIGH for cloud access keys and
  private key blocks, MEDIUM for secret-assignment hints. Findings never
  reproduce secret values. Undecodable/unreadable files → PARTIAL.
- `dependencies` (`manifest-presence`), `tests` (`test-file-presence`),
  `documentation` (`readme-presence`), `configuration`
  (`config-file-presence`): INFO presence observations; absence yields
  SUCCESS with zero findings.
- `code` (`trailing-whitespace-scan`): LOW findings per offending line in
  Python files; undecodable/unreadable files → PARTIAL.
- `architecture` (`architecture-constraints`): SUCCESS with zero findings
  — no constraints are configured in v1, and none are invented.

Coverage gaps (Stage 4 fix): file-consuming analyzers (`tests`,
`dependencies`, `documentation`, `configuration`, `code`, `security`)
inspect `discovery.skipped` via the shared `coverage_gaps` rule. Excluded
paths never count (explicitly out of coverage); oversized and binary
skips count only when the known path matches the check's file criteria;
all other skips (unreadable, symlinks, boundary escapes) always count,
erring toward uncertainty. Relevant gaps are recorded in
`unavailable_evidence` (and the check in `uncovered_checks`) with PARTIAL
status; no findings are invented for skipped paths. `git` and
`architecture` consume no file content, so skips cannot affect them.

Failure information (Stage 4 fix): an analyzer that raises, returns a
non-result, or returns another analyzer's result becomes FAILED with the
analyzer's display name and the exception type only
(e.g. `ValueError in analyzer 'custom-analyzer-0'`). Exception messages
are untrusted input that may reproduce repository content, including
secrets, so they are never stored — this narrows "preserved failure
information" to identity plus exception type, documented here rather than
changed silently. Display names are the documented registry names
verbatim; any other requested name (custom registries are not bound by
the identifier rules) is persisted as the positional alias
`custom-analyzer-N` in engine-built fields, which are therefore always
constructible. The
wrong-analyzer branch stores a fixed mismatched-identity message for the
same reason.

Trust boundary (adopted): the engine guarantees result-level fields it
builds itself — display aliases instead of arbitrary registry keys, and
type-only failure errors. It does not inspect, sanitize, or rewrite
analyzer-built content: findings (including `finding.analyzer`), and the
checks/errors/unavailable strings of successful results, pass through
under the analyzer's own no-secrets contract. Rewriting finding values
would corrupt stable finding identities, and no reliable secret detector
exists for arbitrary text — so a custom analyzer that embeds sensitive
content in its own findings can persist it, and that is the analyzer's
defect, not the engine's. The built-in analyzers are redaction-tested
against this contract. The engine therefore does not claim that
arbitrary registry keys can never reach persisted output in any form;
it claims exactly the result-level guarantee above.

Whenever a file-consuming analyzer returns PARTIAL over file evidence,
it names its check in `uncovered_checks`: any unavailable evidence means
the scan did not complete.

No scoring, correlation, LLM calls, fixes, or repository-code execution
exist in v1.
