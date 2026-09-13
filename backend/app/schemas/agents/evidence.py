"""Evidence bundle contracts built on the existing Module 3 evidence record."""

from __future__ import annotations

from typing import Any

from pydantic import Field, model_validator

from ...services.rag.models import (
    CitationReference,
    DocumentStatus,
    Domain,
    Jurisdiction,
    SourceClass,
    StringEnum,
)
from ..evidence import (
    EvidenceCategory,
    EvidenceConfidence,
    EvidenceRecord as Module3EvidenceRecord,
    EvidenceReviewStatus,
    EvidenceSourceType,
)
from .common import (
    ContractModel,
    DependencyRecord,
    EvidenceCreatedBy,
    EvidenceSourceTrust,
    HumanReviewRequest,
    HumanReviewRole,
    PotentialContradiction,
    ProjectContext,
)


class AgentEvidenceState(StringEnum):
    """Agent-facing state, retaining the Module 3 provided/unknown values."""

    FACT = "FACT"
    PROVIDED = "PROVIDED"
    UNKNOWN = "UNKNOWN"
    NOT_PROVIDED = "NOT_PROVIDED"
    DERIVED = "DERIVED"
    CONFLICTED = "CONFLICTED"


class EvidenceRecord(Module3EvidenceRecord):
    """Extended Module 3 record with agent provenance and cross-domain links."""

    project_id: str
    domain: Domain
    finding: str | None = None
    source: str | None = None
    source_date: str | None = None
    source_document_id: str | None = None
    citation: CitationReference | None = None
    source_class: SourceClass | None = None
    authority_class: SourceClass | None = None
    document_status: DocumentStatus | None = None
    jurisdiction: Jurisdiction | None = None
    assumption: str | None = None
    missing_evidence: list[str] = Field(default_factory=list)
    dependency_ids: list[str] = Field(default_factory=list)
    contradiction_ids: list[str] = Field(default_factory=list)
    human_review_required: bool = False
    human_review_role: HumanReviewRole = HumanReviewRole.UNKNOWN
    created_by: EvidenceCreatedBy = EvidenceCreatedBy.UNKNOWN
    deterministic: bool = False
    source_trust: EvidenceSourceTrust = EvidenceSourceTrust.UNKNOWN
    verification_status: str = "UNVERIFIED"
    evidence_state: AgentEvidenceState

    @model_validator(mode="after")
    def reject_ai_as_deterministic(self) -> "EvidenceRecord":
        if self.created_by == EvidenceCreatedBy.AI_EXTRACTION and (
            self.deterministic
            or self.source_type == EvidenceSourceType.DETERMINISTIC_CALCULATION
        ):
            raise ValueError(
                "AI-extracted evidence cannot masquerade as deterministic evidence"
            )
        return self


class EvidenceBundle(ContractModel):
    project_context: ProjectContext
    records: list[EvidenceRecord] = Field(default_factory=list)
    domain_summary: dict[str, Any] = Field(default_factory=dict)
    retrieval_gaps: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    potential_contradictions: list[PotentialContradiction] = Field(default_factory=list)
    dependencies: list[DependencyRecord] = Field(default_factory=list)
    human_review_requests: list[HumanReviewRequest] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    provenance_summary: dict[str, Any] = Field(default_factory=dict)
    # Bounded GeoJSON features from registered deterministic layers.  This is
    # presentation metadata; it never replaces the evidence ledger.
    map_features: list[dict[str, Any]] = Field(default_factory=list)


__all__ = [
    "AgentEvidenceState",
    "EvidenceBundle",
    "EvidenceRecord",
    "EvidenceCategory",
    "EvidenceConfidence",
    "EvidenceReviewStatus",
    "EvidenceSourceType",
    "EvidenceSourceTrust",
]
