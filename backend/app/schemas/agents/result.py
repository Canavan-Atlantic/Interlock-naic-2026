"""Top-level composition contract for the shared INTERLOCK workflow."""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import Field

from .assessment import AssessmentResult
from .common import (
    AGENT_CONTRACT_VERSION,
    ContractModel,
    HumanReviewRequest,
    ProjectContext,
    WorkflowStatus,
)
from .evidence import EvidenceBundle
from .explanation import ExplanationResult


class InterlockResult(ContractModel):
    project_context: ProjectContext
    # These are optional only so a failed stage cannot be represented by a
    # fabricated empty payload.  Successful runs still contain all three
    # stage outputs.
    evidence_bundle: EvidenceBundle | None = None
    assessment_result: AssessmentResult | None = None
    explanation_result: ExplanationResult | None = None
    workflow_status: WorkflowStatus = WorkflowStatus.UNKNOWN
    human_reviews: list[HumanReviewRequest] = Field(default_factory=list)
    requires_human_review: bool = False
    run_id: str | None = None
    stage_status: dict[str, str] = Field(default_factory=dict)
    stage_errors: dict[str, str] = Field(default_factory=dict)
    stage_counts: dict[str, int] = Field(default_factory=dict)
    timings_ms: dict[str, float] = Field(default_factory=dict)
    failure_stage: str | None = None
    failure_message: str | None = None
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    schema_version: str = AGENT_CONTRACT_VERSION


__all__ = ["InterlockResult"]
