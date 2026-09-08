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
    evidence_bundle: EvidenceBundle
    assessment_result: AssessmentResult
    explanation_result: ExplanationResult | None = None
    workflow_status: WorkflowStatus = WorkflowStatus.UNKNOWN
    human_reviews: list[HumanReviewRequest] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    schema_version: str = AGENT_CONTRACT_VERSION


__all__ = ["InterlockResult"]
