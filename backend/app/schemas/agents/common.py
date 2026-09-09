"""Common, versioned data contracts for the INTERLOCK agent workflow."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ...services.rag.models import Domain, Jurisdiction, StringEnum, Workflow
from ..project import PowerStrategy, ProjectInput, ProjectStage

AGENT_CONTRACT_VERSION = "1.0"


class ProjectLifecycleStatus(StringEnum):
    """Project delivery lifecycle, deliberately separate from assessment workflow."""

    CONCEPT = "CONCEPT"
    PRE_PLANNING = "PRE_PLANNING"
    PLANNING = "PLANNING"
    APPROVED = "APPROVED"
    CONSTRUCTION = "CONSTRUCTION"
    OPERATIONAL = "OPERATIONAL"
    UNKNOWN = "UNKNOWN"


class EvidenceCreatedBy(StringEnum):
    DEVELOPER_INPUT = "DEVELOPER_INPUT"
    DETERMINISTIC_GIS = "DETERMINISTIC_GIS"
    RAG_RETRIEVAL = "RAG_RETRIEVAL"
    PROJECT_DOCUMENT = "PROJECT_DOCUMENT"
    AI_EXTRACTION = "AI_EXTRACTION"
    HUMAN_REVIEW = "HUMAN_REVIEW"
    UNKNOWN = "UNKNOWN"


class EvidenceSourceTrust(StringEnum):
    """Trust boundary for evidence provenance, independent of factual confidence."""

    AUTHORITATIVE_POLICY = "AUTHORITATIVE_POLICY"
    DETERMINISTIC_SOURCE = "DETERMINISTIC_SOURCE"
    UNVERIFIED_DEVELOPER_INPUT = "UNVERIFIED_DEVELOPER_INPUT"
    UNTRUSTED_PROJECT_DOCUMENT = "UNTRUSTED_PROJECT_DOCUMENT"
    SUPPORTING_SOURCE = "SUPPORTING_SOURCE"
    UNKNOWN = "UNKNOWN"


class DependencyStatus(StringEnum):
    CONFIRMED = "CONFIRMED"
    POTENTIAL = "POTENTIAL"
    UNRESOLVED = "UNRESOLVED"
    SATISFIED = "SATISFIED"
    UNKNOWN = "UNKNOWN"


class ContradictionType(StringEnum):
    EVIDENCE_MISMATCH = "EVIDENCE_MISMATCH"
    POLICY_VERSION_DIFFERENCE = "POLICY_VERSION_DIFFERENCE"
    CROSS_SOURCE_COMPARISON = "CROSS_SOURCE_COMPARISON"
    PROJECT_SCOPE_MISMATCH = "PROJECT_SCOPE_MISMATCH"
    UNKNOWN = "UNKNOWN"


class HumanReviewSeverity(StringEnum):
    INFORMATIONAL = "INFORMATIONAL"
    MATERIAL = "MATERIAL"
    HIGH_CONSEQUENCE = "HIGH_CONSEQUENCE"


class HumanReviewRole(StringEnum):
    PLANNING_CONSULTANT = "PLANNING_CONSULTANT"
    ECOLOGIST = "ECOLOGIST"
    GRID_ENGINEER = "GRID_ENGINEER"
    EIA_ENVIRONMENTAL_CONSULTANT = "EIA_ENVIRONMENTAL_CONSULTANT"
    DEVELOPER = "DEVELOPER"
    LEGAL_REGULATORY = "LEGAL_REGULATORY"
    UNKNOWN = "UNKNOWN"


class HumanReviewStatus(StringEnum):
    REQUIRED = "REQUIRED"
    REQUESTED = "REQUESTED"
    COMPLETED = "COMPLETED"
    NOT_REQUIRED = "NOT_REQUIRED"


class AssessmentStatus(StringEnum):
    CLEAR = "CLEAR"
    CONDITIONAL = "CONDITIONAL"
    CONSTRAINED = "CONSTRAINED"
    UNKNOWN = "UNKNOWN"
    NOT_ASSESSED = "NOT_ASSESSED"


class WorkflowStatus(StringEnum):
    NOT_STARTED = "NOT_STARTED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    REQUIRES_HUMAN_REVIEW = "REQUIRES_HUMAN_REVIEW"
    BLOCKED = "BLOCKED"
    UNKNOWN = "UNKNOWN"


class ContractModel(BaseModel):
    """Strict base model used by the shared contracts."""

    model_config = ConfigDict(extra="forbid", use_enum_values=True)


class SiteBoundary(ContractModel):
    """Optional GeoJSON-like site boundary supplied by a trusted source."""

    geometry: dict[str, Any] | None = None
    area_hectares: float | None = Field(default=None, ge=0)
    source_reference: str | None = None


class ProjectLocation(ContractModel):
    address: str | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    local_authority: str | None = None
    country: str | None = None
    jurisdiction: Jurisdiction = Jurisdiction.UNKNOWN


class ProjectContext(ContractModel):
    """Canonical project context shared across future agents."""

    project_id: str
    project_name: str | None = None
    project_type: str | None = None
    assessment_workflow: Workflow | None = None
    project_lifecycle_status: ProjectLifecycleStatus = ProjectLifecycleStatus.UNKNOWN
    location: ProjectLocation = Field(default_factory=ProjectLocation)
    site_boundary: SiteBoundary | None = None
    planned_power_mw: float | None = Field(default=None, ge=0)
    requested_mic_mva: float | None = Field(default=None, ge=0)
    power_strategy: PowerStrategy | None = None
    energy_strategy: str | None = None
    phasing: str | None = None
    project_stage: ProjectStage | None = None
    developer_inputs: dict[str, Any] = Field(default_factory=dict)
    uploaded_document_refs: list[str] = Field(default_factory=list)
    source_project_input: ProjectInput | None = None

    @classmethod
    def from_project_input(
        cls,
        project_input: ProjectInput,
        *,
        project_id: str,
        assessment_workflow: Workflow | None = None,
        project_lifecycle_status: ProjectLifecycleStatus = ProjectLifecycleStatus.UNKNOWN,
        local_authority: str | None = None,
        country: str | None = None,
        jurisdiction: Jurisdiction = Jurisdiction.UNKNOWN,
        uploaded_document_refs: list[str] | None = None,
    ) -> "ProjectContext":
        """Adapt the existing Module 2 input without inventing missing values."""

        return cls(
            project_id=project_id,
            project_name=project_input.project_name,
            project_type=project_input.development_type,
            assessment_workflow=assessment_workflow,
            project_lifecycle_status=project_lifecycle_status,
            location=ProjectLocation(
                address=project_input.site_address,
                latitude=project_input.latitude,
                longitude=project_input.longitude,
                local_authority=local_authority,
                country=country,
                jurisdiction=jurisdiction,
            ),
            planned_power_mw=project_input.planned_power_demand_mw,
            requested_mic_mva=project_input.requested_mic_mva,
            power_strategy=project_input.power_strategy,
            energy_strategy=project_input.energy_strategy,
            phasing=project_input.project_phasing_notes,
            project_stage=project_input.project_stage,
            developer_inputs=project_input.model_dump(mode="json"),
            uploaded_document_refs=uploaded_document_refs or [],
            source_project_input=project_input,
        )


class DependencyRecord(ContractModel):
    dependency_id: str
    project_id: str
    from_domain: Domain
    to_domain: Domain
    description: str
    status: DependencyStatus = DependencyStatus.UNKNOWN
    evidence_ids: list[str] = Field(default_factory=list)
    impact_description: str | None = None
    evidence_required_next: list[str] = Field(default_factory=list)
    human_review_required: bool = False


class PotentialContradiction(ContractModel):
    contradiction_id: str
    project_id: str
    domain: Domain
    evidence_ids: list[str] = Field(default_factory=list)
    source_document_ids: list[str] = Field(default_factory=list)
    type: ContradictionType = ContradictionType.UNKNOWN
    description: str
    requires_human_review: bool = True

    def model_post_init(self, __context: Any) -> None:
        if not self.requires_human_review:
            raise ValueError("Potential contradictions must require human review")


class HumanReviewRequest(ContractModel):
    review_id: str
    project_id: str
    domain: Domain
    reason: str
    severity: HumanReviewSeverity = HumanReviewSeverity.MATERIAL
    recommended_role: HumanReviewRole = HumanReviewRole.UNKNOWN
    evidence_ids: list[str] = Field(default_factory=list)
    status: HumanReviewStatus = HumanReviewStatus.REQUIRED
    requested_at: datetime | None = None
