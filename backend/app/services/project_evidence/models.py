"""Project-document evidence models kept separate from Module 5 policy models."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ...services.rag.models import CitationReference, Domain


class ProjectDocumentClassification(str, Enum):
    PROJECT_INPUT_BENCHMARK = "PROJECT_INPUT_BENCHMARK"
    BENCHMARK_ONLY = "BENCHMARK_ONLY"


class ProjectRightsStatus(str, Enum):
    UNKNOWN = "UNKNOWN"
    PUBLIC_ACCESS_RESTRICTED_REUSE = "PUBLIC_ACCESS_RESTRICTED_REUSE"
    PERMITTED = "PERMITTED"
    UNKNOWN_REUSE = "UNKNOWN_REUSE"


class ProjectEvidenceSourceTrust(str, Enum):
    UNTRUSTED_PROJECT_DOCUMENT = "UNTRUSTED_PROJECT_DOCUMENT"


class ProjectAssetStatus(str, Enum):
    PROPOSED = "PROPOSED"
    PLANNED = "PLANNED"
    APPLIED_FOR = "APPLIED_FOR"
    PERMITTED = "PERMITTED"
    CONTRACTED = "CONTRACTED"
    UNDER_CONSTRUCTION = "UNDER_CONSTRUCTION"
    COMMISSIONED = "COMMISSIONED"
    OPERATIONAL = "OPERATIONAL"
    UNKNOWN = "UNKNOWN"


class ProjectEvidenceModel(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)


class ProjectDocument(ProjectEvidenceModel):
    project_document_id: str
    project_id: str
    title: str
    filename: str
    source_url: str
    sha256: str
    document_type: str
    classification: ProjectDocumentClassification
    domain: Domain
    issuer: str | None = None
    publication_date: str | None = None
    version: str | None = None
    retrieved_at: datetime
    source_type: str = "PROJECT_DOCUMENT"
    authority_class: str = "NON_AUTHORITATIVE_PROJECT_EVIDENCE"
    trusted_as_policy: bool = False
    project_specific: bool = True
    benchmark_only: bool = False
    requires_human_review: bool = True
    rights_status: ProjectRightsStatus = ProjectRightsStatus.UNKNOWN_REUSE
    source_trust: ProjectEvidenceSourceTrust = ProjectEvidenceSourceTrust.UNTRUSTED_PROJECT_DOCUMENT
    notes: list[str] = Field(default_factory=list)
    page_count: int | None = None
    no_text_pages: list[int] = Field(default_factory=list)
    chunk_count: int = 0
    fact_count: int = 0
    local_path: str


class ProjectEvidenceChunk(ProjectEvidenceModel):
    chunk_id: str
    project_document_id: str
    project_id: str
    document_type: str
    domain: Domain
    page_start: int | None = None
    page_end: int | None = None
    section_heading: str | None = None
    text: str
    source_type: str = "PROJECT_DOCUMENT"
    authority_class: str = "NON_AUTHORITATIVE_PROJECT_EVIDENCE"
    trusted_as_policy: bool = False
    benchmark_only: bool = False
    source_url: str
    citation: CitationReference
    source_trust: ProjectEvidenceSourceTrust = ProjectEvidenceSourceTrust.UNTRUSTED_PROJECT_DOCUMENT


class ProjectEvidenceFact(ProjectEvidenceModel):
    fact_id: str
    project_document_id: str
    project_id: str
    field_name: str
    value: Any | None = None
    status: ProjectAssetStatus = ProjectAssetStatus.UNKNOWN
    evidence_state: str = "UNKNOWN"
    confidence: str = "UNKNOWN"
    verification_status: str = "UNVERIFIED_PROJECT_DOCUMENT"
    page_start: int | None = None
    page_end: int | None = None
    source_url: str
    citation: CitationReference
    benchmark_only: bool = False
    source_trust: ProjectEvidenceSourceTrust = ProjectEvidenceSourceTrust.UNTRUSTED_PROJECT_DOCUMENT
    notes: list[str] = Field(default_factory=list)
