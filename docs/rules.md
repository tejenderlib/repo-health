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
