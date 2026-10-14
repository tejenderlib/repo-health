# Repo Health — AI Agent Instructions

## 1. Project Mission

Repo Health is a deterministic repository analysis and evidence-comparison
system.

Its purpose is to inspect repository evidence, identify supported findings,
compare observations over time, and explain what changed without inventing
facts or making unsupported causal claims.

Correctness, reproducibility, traceability, and maintainability take priority
over feature count.

## 2. Mandatory Reading

Before implementing a feature or changing architecture, read the relevant
documentation:

- `README.md` — project purpose and usage.
- `docs/architecture.md` — component boundaries and data flow.
- `docs/configuration.md` — supported configuration.
- `docs/rules.md` — analysis and evidence rules.

If documentation is incomplete, identify the missing decisions before
implementing features that depend on them.

Do not assume an undocumented feature already exists.

## 3. Core Engineering Principles

### Deterministic behavior

- The same inputs must produce the same substantive outputs.
- Use explicit, stable ordering for findings, comparisons, and serialized data.
- Avoid dependence on filesystem traversal order, timestamps, or randomness
  unless explicitly required by the contract.
- Do not introduce nondeterministic behavior into the core.

### Evidence before conclusions

- Every finding and reported change must be supported by available evidence.
- Preserve the provenance of evidence wherever applicable.
- Never fabricate findings, repository facts, history, or missing observations.
- Distinguish an absent fact from a fact that has been verified to be absent.
- Represent unavailable or insufficient evidence explicitly.

### Read-only operation

- Repository analysis must not modify the target repository.
- Do not automatically fix files, install dependencies in the target
  repository, or execute destructive commands.
- Any future write operation requires an explicitly designed and documented
  workflow with appropriate user authorization.

### No unsupported conclusions

- Do not infer causality from correlation.
- Do not claim that a change caused a defect without supporting evidence.
- Do not classify a finding as resolved merely because it was not observed.
- Do not treat an analyzer that did not run as an analyzer that found nothing.

## 4. Architecture Boundaries

- Keep core logic independent of external infrastructure.
- Keep Git, filesystem access, persistence, and command-line concerns behind
  explicit boundaries.
- Keep analysis, evidence collection, comparison, and presentation concerns
  separate.
- Prefer small, cohesive modules with explicit inputs and outputs.
- Avoid circular imports and hidden global state.
- Do not reorganize the architecture without documenting the reason and
  updating the relevant tests.

The exact responsibilities of each module must be defined in
`docs/architecture.md` before implementation begins.

## 5. Evidence and Comparison Contract

The system must distinguish:

- KNOWN: sufficient evidence exists to establish a fact.
- UNKNOWN: available evidence does not establish the fact.
- UNAVAILABLE: the required evidence or analysis layer could not be obtained.

These states are not interchangeable.

When comparing observations:

- Use deterministic comparison logic.
- Preserve the distinction between changed, unchanged, and indeterminate facts.
- Missing file evidence must not automatically be interpreted as file deletion.
- Unknown evidence at the baseline must not produce an unsupported lifecycle
  classification.
- Finding transitions require sufficient evidence from the relevant analyzer.
- A finding that was not evaluated must not be classified as resolved.

History must be derived from actual persisted evidence. Never manufacture
historical observations.

## 6. Schema and Compatibility

The previously established evidence and comparison contract uses schema v3.

- Preserve schema v3 compatibility unless an explicit design decision
  authorizes a migration.
- Do not silently rename, remove, or reinterpret existing fields.
- Do not introduce a new schema version merely to simplify implementation.
- Document and test any explicitly approved compatibility changes.

## 7. AI and External Dependencies

- Core analysis and comparison must remain deterministic and independent
  of language models.
- Do not add LLM calls, embeddings, or AI-generated findings to the core.
- Do not introduce risk scores or unsupported causal judgments.
- Keep runtime dependencies minimal.
- Prefer the Python standard library when practical.
- Do not install packages or add dependencies without establishing a concrete
  requirement and documenting the decision.

AI coding assistants may help implement and review code, but their generated
claims are not evidence about the target repository.

## 8. Testing Requirements

- Add or update tests for every behavior change.
- Test normal cases, edge cases, invalid inputs, and missing evidence.
- Test determinism explicitly where ordering or comparison matters.
- Test failure paths, including unavailable analyzers and incomplete evidence.
- Use temporary repositories and fixtures rather than modifying real
  repositories during tests.
- Never weaken or delete a test simply to make the suite pass.
- Run the relevant tests after changes and report the actual result.

Do not claim that tests pass unless they were executed successfully.

## 9. Code Quality

- Use type hints for public interfaces.
- Prefer explicit data models and clear contracts.
- Keep functions focused and avoid unnecessary abstractions.
- Validate inputs at appropriate boundaries.
- Use meaningful names and actionable error messages.
- Follow the project's configured linting and formatting rules.
- Avoid unrelated refactoring.

## 10. Documentation Requirements

Update documentation whenever a change affects:

- Architecture or module responsibilities.
- Evidence semantics or finding lifecycle rules.
- Configuration or command-line behavior.
- Data formats or schema compatibility.
- Dependencies or supported environments.
- User-visible output.

Keep documentation aligned with implemented behavior.

Clearly label planned features as planned. Never describe an unimplemented
feature as operational.

## 11. Required Workflow

For each task:

1. Read the relevant documentation and inspect existing code.
2. Identify the requirements and affected modules.
3. Check for conflicts with established contracts.
4. Propose the smallest appropriate change.
5. Implement the change without unrelated modifications.
6. Add or update tests.
7. Run the relevant tests and checks.
8. Update documentation when needed.
9. Summarize changes, verification results, and remaining limitations.

If requirements conflict with the established architecture or evidence
contract, stop and explain the conflict before making the change.

## 12. Scope Discipline

- Do not implement unrelated features.
- Do not invent requirements to fill documentation gaps.
- Do not change established contracts without explicit approval.
- Do not claim capabilities based solely on filenames or directory structure.
- Prefer a small, correct, tested implementation over a large, incomplete one.
