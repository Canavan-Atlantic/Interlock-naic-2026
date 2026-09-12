"""API contracts for durable project portfolio and assessment history."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .agents import ProjectContext


PORTFOLIO_SCHEMA_VERSION = "1.0"
REPORT_VERSION = "1.0"


class ProjectCreate(ProjectContext):
    """Canonical project context accepted when creating a portfolio record."""


class AssessmentRunSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    interlock_run_id: str | None = None
    project_id: str
    created_at: datetime
    workflow_status: str
    planned_power_mw: float | None = None
    evidence_count: int = 0
    findings_count: int = 0
    unknown_theme_count: int = 0
    human_review_count: int = 0
    citation_count: int = 0
    total_runtime_ms: float | None = None
    schema_version: str = PORTFOLIO_SCHEMA_VERSION
    report_version: str = REPORT_VERSION


class ProjectSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    external_project_id: str | None = None
    project_name: str | None = None
    project_type: str | None = None
    address: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    lifecycle_status: str | None = None
    project_stage: str | None = None
    created_at: datetime
    updated_at: datetime
    latest_run_id: str | None = None
    latest_assessment: AssessmentRunSummary | None = None
    run_count: int = 0


class ProjectDetail(ProjectSummary):
    project_context: dict[str, Any] = Field(default_factory=dict)


class AssessmentRunResponse(AssessmentRunSummary):
    submitted_project_context: dict[str, Any] = Field(default_factory=dict)
    interlock_result: dict[str, Any] = Field(default_factory=dict)
    report_available: bool = True


__all__ = [
    "AssessmentRunResponse",
    "AssessmentRunSummary",
    "PORTFOLIO_SCHEMA_VERSION",
    "ProjectCreate",
    "ProjectDetail",
    "ProjectSummary",
    "REPORT_VERSION",
]
