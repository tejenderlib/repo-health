"""Shared report-data contract (Phase 8, step 1).

A report binds one stored analysis run to its analyzer results and
lifecycle classifications for rendering. It carries no rendering logic:
both the JSON and Markdown renderers consume this model, so presentation
can never invent findings, alter severity, or reinterpret evidence.

Ordering is deterministic: results sort by analyzer name, lifecycles by
their stable sort key. Relationships are validated: the run must belong
to the repository, and lifecycle records must describe this run against
this baseline.
"""

from __future__ import annotations

from dataclasses import dataclass

from repo_health.core.exceptions import ValidationError
from repo_health.models.analyzer_result import AnalyzerResult
from repo_health.models.lifecycle import FindingLifecycle
from repo_health.models.run import AnalysisRun


@dataclass(frozen=True)
class Report:
    """One stored run plus its results and lifecycles, ready to render."""

    repository_key: str = ""
    repository_name: str = ""
    run: AnalysisRun | None = None
    baseline_run_id: int | None = None
    results: tuple[AnalyzerResult, ...] = ()
    lifecycles: tuple[FindingLifecycle, ...] = ()

    def __post_init__(self) -> None:
        repository_key = self.repository_key.strip()
        if repository_key == "":
            raise ValidationError("repository_key must not be blank")
        repository_name = self.repository_name.strip()
        if repository_name == "":
            raise ValidationError("repository_name must not be blank")
        if not isinstance(self.run, AnalysisRun):
            raise ValidationError(f"run must be an AnalysisRun, got {self.run!r}")
        if self.run.repository_key != repository_key:
            raise ValidationError("run does not belong to the report repository")
        if self.baseline_run_id is not None and self.baseline_run_id < 1:
            raise ValidationError("baseline_run_id must be a positive run id or None")
        for result in self.results:
            if not isinstance(result, AnalyzerResult):
                raise ValidationError(f"results must contain AnalyzerResult items, got {result!r}")
        for item in self.lifecycles:
            if not isinstance(item, FindingLifecycle):
                raise ValidationError(
                    f"lifecycles must contain FindingLifecycle items, got {item!r}"
                )
            if (
                item.current_run_id is not None
                and self.run.id is not None
                and item.current_run_id != self.run.id
            ):
                raise ValidationError("lifecycle record does not describe this run")
            if (
                item.baseline_run_id is not None
                and self.baseline_run_id is not None
                and item.baseline_run_id != self.baseline_run_id
            ):
                raise ValidationError("lifecycle record does not describe this baseline")
        object.__setattr__(self, "repository_key", repository_key)
        object.__setattr__(self, "repository_name", repository_name)
        object.__setattr__(self, "results", tuple(sorted(self.results, key=lambda r: r.analyzer)))
        object.__setattr__(
            self,
            "lifecycles",
            tuple(sorted(self.lifecycles, key=lambda item: item.sort_key())),
        )
