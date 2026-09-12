"""API contracts for deterministic comparisons of stored assessment runs."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


COMPARISON_SCHEMA_VERSION = "1.0"
COMPARISON_REPORT_VERSION = "1.0"


class ComparisonValueChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field_path: str
    label: str
    previous_value: Any = None
    comparison_value: Any = None
    previous_display: str
    comparison_display: str


class InputComparison(BaseModel):
    model_config = ConfigDict(extra="forbid")

    changed: list[ComparisonValueChange] = Field(default_factory=list)
    unchanged: list[ComparisonValueChange] = Field(default_factory=list)
    changed_count: int = 0
    unchanged_count: int = 0


class ComparisonItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    identity: str
    label: str
    matchable: bool = True
    baseline: dict[str, Any] | None = None
    comparison: dict[str, Any] | None = None
    changed_fields: list[str] = Field(default_factory=list)


class ComparisonSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    added: list[ComparisonItem] = Field(default_factory=list)
    removed: list[ComparisonItem] = Field(default_factory=list)
    changed: list[ComparisonItem] = Field(default_factory=list)
    unchanged: list[ComparisonItem] = Field(default_factory=list)
    added_count: int = 0
    removed_count: int = 0
    changed_count: int = 0
    unchanged_count: int = 0


class DomainComparison(BaseModel):
    model_config = ConfigDict(extra="forbid")

    domain: str
    label: str
    source_domains: list[str] = Field(default_factory=list)
    baseline_state: str
    comparison_state: str
    changed: bool
    change_kind: str
    baseline_finding_ids: list[str] = Field(default_factory=list)
    comparison_finding_ids: list[str] = Field(default_factory=list)


class AssessmentComparison(BaseModel):
    """A read-only comparison generated from two immutable run snapshots."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = COMPARISON_SCHEMA_VERSION
    report_version: str = COMPARISON_REPORT_VERSION
    project_id: str
    project_name: str | None = None
    baseline_run_id: str
    comparison_run_id: str
    baseline_interlock_run_id: str | None = None
    comparison_interlock_run_id: str | None = None
    baseline_timestamp: datetime
    comparison_timestamp: datetime
    baseline_workflow_status: str
    comparison_workflow_status: str
    baseline_planned_power_mw: float | None = None
    comparison_planned_power_mw: float | None = None
    generated_at: datetime
    summary: dict[str, int] = Field(default_factory=dict)
    input_changes: InputComparison
    domain_changes: list[DomainComparison] = Field(default_factory=list)
    finding_changes: ComparisonSection
    unknown_changes: ComparisonSection
    dependency_changes: ComparisonSection
    human_review_changes: ComparisonSection
    next_action_changes: ComparisonSection
    evidence_changes: ComparisonSection
    citation_changes: ComparisonSection


__all__ = [
    "AssessmentComparison",
    "COMPARISON_REPORT_VERSION",
    "COMPARISON_SCHEMA_VERSION",
    "ComparisonItem",
    "ComparisonSection",
    "ComparisonValueChange",
    "DomainComparison",
    "InputComparison",
]
