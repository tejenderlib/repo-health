# Repo Health — Output Format Specification

This document defines the report outputs produced from the shared report
model (`models/report.py`). All renderers are pure formatting functions:
they never invent findings, alter severity, or reinterpret evidence.

## 1. JSON report — `repo-health-report/v1`

`reports/json_report.py` builds the shared model from stored runs and
serializes it with sorted keys and two-space indentation. Top-level keys:

| Key | Content |
|---|---|
| `schema` | Always `"repo-health-report/v1"`. Unrelated to legacy schema v3. |
| `repository` | `key` (normalized absolute root) and `name`. |
| `run` | `id` and `status` (`completed`, `partial`, or `failed`). |
| `baseline_run_id` | Compared baseline run id, or `null` for first runs. |
| `metadata` | `created_at` timestamp. Volatile generation timestamps never appear; only this stored value. |
| `coverage` | `analyzers`: sorted analyzer names evaluated in the run. `complete`: true only when every analyzer row reports SUCCESS with empty unavailable-evidence and uncovered-checks lists. |
| `findings` | One entry per observed finding, ordered by severity rank (critical first) then finding id. Fields: `id`, `analyzer`, `rule`, `severity`, `path`, `locator`, `title`, `description`, `evidence`, `recommendation`, `lifecycle`, `reason`, `baseline_run_id`. Content passes through from storage, preserving analyzer-level redaction. |
| `lifecycle_counts` | All five statuses (`new`, `recurring`, `resolved`, `reappeared`, `indeterminate`), including zero counts. |

### Example

The following is actual output for a run with one new HIGH finding
(verified against `tests/unit/test_reports.py`):

```json
{
  "baseline_run_id": 1,
  "coverage": {
    "analyzers": [
      "security"
    ],
    "complete": true
  },
  "findings": [
    {
      "analyzer": "security",
      "baseline_run_id": 1,
      "description": "A potential secret pattern was detected.",
      "evidence": "line 1 matches",
      "id": "rh1-d94328be205da32e",
      "lifecycle": "new",
      "locator": "L1",
      "path": "src/a.py",
      "reason": "observed in run 2, absent from complete baseline run 1",
      "recommendation": "Rotate it.",
      "rule": "security.secret-pattern",
      "severity": "high",
      "title": "Possible secret"
    }
  ],
  "lifecycle_counts": {
    "indeterminate": 0,
    "new": 1,
    "reappeared": 0,
    "recurring": 0,
    "resolved": 0
  },
  "metadata": {
    "created_at": "2026-01-03T00:00:00+00:00"
  },
  "repository": {
    "key": "/tmp/repo",
    "name": "repo"
  },
  "run": {
    "id": 2,
    "status": "completed"
  },
  "schema": "repo-health-report/v1"
}
```

## 2. Markdown report

`reports/markdown.py` renders the same model with this fixed layout:

1. `# Repo Health Report` title, repository name and key, run id/status/timestamp, baseline (`Baseline: run N` or `Baseline: none`).
2. `## Scope and coverage`: analyzer count and names, `Coverage: complete|incomplete`, per-analyzer statuses, and each unavailable-evidence item.
3. `## Findings (N)`: groups for severities present, ordered CRITICAL, HIGH, MEDIUM, LOW, INFO; findings ordered by id within a group. Each entry shows location, title, rule, severity, lifecycle, evidence, and recommendation (when present). Empty runs render `No findings recorded.`
4. `## Lifecycle`: counts for all five statuses, then one line per new, reappeared, or resolved finding. Findings without lifecycle data render as `unknown` rather than inventing a classification.
5. `## Limitations`: states that no findings does not prove the repository is free of issues.

### Example

Actual output for a run with one new HIGH and one recurring INFO finding
(verified against `tests/unit/test_reports.py`):

```markdown
# Repo Health Report

Repository: repo (`/tmp/repo`)
Run: 2 (completed) at 2026-01-03T00:00:00+00:00
Baseline: run 1

## Scope and coverage

Analyzers (2): git, security
Coverage: complete
- git: success
- security: success

## Findings (2)

### HIGH (1)

- `src/a.py:L1` Possible secret (security.secret-pattern, high, new)
  Evidence: line 1 matches
  Recommendation: Rotate it.

### INFO (1)

- no file Git repository detected (git.repository-present, info, recurring)
  Evidence: .git directory present

## Lifecycle

1 new, 1 recurring, 0 resolved, 0 reappeared, 0 indeterminate

- rh1-d94328be205da32e (security) - new: first seen

## Limitations

No findings does not prove the repository is free of issues. Results are limited to the checks performed, the available evidence, and the configured exclusions.
```

## 3. Summary format

`reports/summary.py` renders one line for the run (`run 2 (completed),
baseline run 1`, or `no baseline`), one `analyzer: status, N finding(s)`
line per analyzer, then analyzer totals, finding totals with all five
severity counts, and lifecycle counts. Example:

```text
run 2 (completed), baseline run 1
git: success, 1 finding
security: success, 1 finding
analyzers: 2 (2 success, 0 partial, 0 failed)
findings: 2 (critical: 0, high: 1, medium: 0, low: 0, info: 1)
lifecycle: 1 new, 1 recurring, 0 resolved, 0 reappeared, 0 indeterminate
```

## 4. Determinism and output behavior

- Identical report models render byte-identical output: findings ordered
  by severity rank then id, lifecycles by `(finding_id, analyzer)`,
  JSON keys sorted, no timestamps beyond stored `created_at`.
- The `report` command prints to stdout by default; `--output FILE`
  writes byte-identical content to the explicitly requested file only.
- Unknown repositories, runs, baselines, and formats follow the CLI exit
  contract (exit 2); queries never modify the database.

## 5. Related documents

- `docs/architecture.md` section 4.8: module responsibilities.
- `docs/rules.md` section 16: evidence and lifecycle contracts.
- `README.md`: usage examples.
