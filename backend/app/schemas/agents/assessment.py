"""Assessment contracts.  These describe findings, not investment decisions."""

from __future__ import annotations

from pydantic import Field

from ...services.rag.models import Domain
from .common import (
    AssessmentStatus,
    ContractModel,
    DependencyRecord,
    HumanReviewRequest,
    ProjectContext,
)
from .evidence import EvidenceBundle


class AssessmentRequest(ContractModel):
    project_context: ProjectContext
    evidence_bundle: EvidenceBundle


class AssessmentFinding(ContractModel):
    finding_id: str
    domain: Domain
    status: AssessmentStatus = AssessmentStatus.UNKNOWN
    constraint: str | None = None
    dependency_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    material_unknowns: list[str] = Field(default_factory=list)
    decision_impact: str | None = None
    evidence_required_next: list[str] = Field(default_factory=list)
    human_review_required: bool = False


class AssessmentResult(ContractModel):
    project_context: ProjectContext
    findings: list[AssessmentFinding] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    dependencies: list[DependencyRecord] = Field(default_factory=list)
    material_unknowns: list[str] = Field(default_factory=list)
    human_reviews: list[HumanReviewRequest] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


__all__ = ["AssessmentFinding", "AssessmentRequest", "AssessmentResult"]
