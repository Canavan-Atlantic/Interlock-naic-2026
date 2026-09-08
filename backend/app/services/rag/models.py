"""Controlled Module 5A metadata and provenance models."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StringEnum(str, Enum):
    """String-valued enum that serialises cleanly in JSON."""


class SourceClass(StringEnum):
    PRIMARY = "PRIMARY"
    CURATED = "CURATED"
    SUPPORTING_PUBLIC_BODY = "SUPPORTING_PUBLIC_BODY"
    SUPPORTING_INDUSTRY = "SUPPORTING_INDUSTRY"
    SUPPORTING_RESEARCH = "SUPPORTING_RESEARCH"
    GOVERNANCE = "GOVERNANCE"
    RESTRICTED = "RESTRICTED"
    ARCHIVE = "ARCHIVE"
    UNKNOWN = "UNKNOWN"


AuthorityClass = SourceClass


class DocumentStatus(StringEnum):
    CURRENT = "CURRENT"
    PROPOSED = "PROPOSED"
    HISTORICAL = "HISTORICAL"
    SUPERSEDED = "SUPERSEDED"
    SUPPORTING = "SUPPORTING"
    UNKNOWN = "UNKNOWN"


class Jurisdiction(StringEnum):
    EU = "EU"
    IRELAND = "IRELAND"
    REGIONAL = "REGIONAL"
    LOCAL_AUTHORITY = "LOCAL_AUTHORITY"
    UNKNOWN = "UNKNOWN"


class Workflow(StringEnum):
    SITE_DISCOVERY = "SITE_DISCOVERY"
    SITE_FEASIBILITY = "SITE_FEASIBILITY"
    POLICY_REGULATORY_INTELLIGENCE = "POLICY_REGULATORY_INTELLIGENCE"


class Domain(StringEnum):
    GRID = "GRID"
    ENERGY = "ENERGY"
    PLANNING = "PLANNING"
    BIODIVERSITY = "BIODIVERSITY"
    ENVIRONMENT = "ENVIRONMENT"
    WATER = "WATER"
    DATA_CENTRE_POLICY = "DATA_CENTRE_POLICY"
    INFRASTRUCTURE = "INFRASTRUCTURE"
    EU_REPORTING = "EU_REPORTING"
    RESPONSIBLE_AI = "RESPONSIBLE_AI"
    GENERAL = "GENERAL"
    UNKNOWN = "UNKNOWN"


class ExtractionStatus(StringEnum):
    NOT_RUN = "NOT_RUN"
    EXTRACTED = "EXTRACTED"
    CURATED_ATOMIC = "CURATED_ATOMIC"
    SKIPPED_ARCHIVE = "SKIPPED_ARCHIVE"
    SKIPPED_RESTRICTED = "SKIPPED_RESTRICTED"
    SKIPPED_GOVERNANCE = "SKIPPED_GOVERNANCE"
    SKIPPED_METADATA = "SKIPPED_METADATA"
    DUPLICATE_SKIPPED = "DUPLICATE_SKIPPED"
    FAILED = "FAILED"


class CitationReference(BaseModel):
    """Structured citation/provenance for a chunk or curated record."""

    model_config = ConfigDict(use_enum_values=True)

    document_id: str
    source_path: str
    page_start: int | None = None
    page_end: int | None = None
    section_heading: str | None = None
    paragraph_start: int | None = None
    paragraph_end: int | None = None
    locator: str


class RAGDocument(BaseModel):
    """Canonical metadata record for one discovered source document."""

    model_config = ConfigDict(use_enum_values=True)

    document_id: str
    title: str
    filename: str
    source_path: str
    sha256: str
    source_class: SourceClass
    authority_class: AuthorityClass
    document_status: DocumentStatus
    jurisdiction: Jurisdiction
    jurisdiction_detail: str | None = None
    issuer: str | None = None
    document_type: str
    publication_date: str | None = None
    effective_date: str | None = None
    version: str | None = None
    retrieval_eligible: bool = False
    requires_human_review: bool = False
    restricted: bool = False
    confidential: bool = False
    supersedes_document_id: str | None = None
    superseded_by_document_id: str | None = None
    applicable_workflows: list[Workflow] = Field(default_factory=list)
    applicable_domains: list[Domain] = Field(default_factory=list)
    source_url: str | None = None
    notes: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    discovered_at: datetime
    processed_at: datetime | None = None
    extraction_status: ExtractionStatus = ExtractionStatus.NOT_RUN
    extraction_error: str | None = None
    page_count: int | None = None
    no_text_pages: list[int] = Field(default_factory=list)
    chunk_count: int = 0
    curated_record_count: int = 0
    duplicate_of_document_id: str | None = None
    duplicate_source_paths: list[str] = Field(default_factory=list)


class RAGChunk(BaseModel):
    """Deterministic page-aware active corpus chunk without embeddings."""

    model_config = ConfigDict(use_enum_values=True)

    chunk_id: str
    document_id: str
    text: str
    page_start: int | None = None
    page_end: int | None = None
    section_heading: str | None = None
    source_class: SourceClass
    document_status: DocumentStatus
    jurisdiction: Jurisdiction
    issuer: str | None = None
    publication_date: str | None = None
    version: str | None = None
    applicable_workflows: list[Workflow] = Field(default_factory=list)
    applicable_domains: list[Domain] = Field(default_factory=list)
    source_path: str
    source_reference: CitationReference
    retrieval_eligible: bool
    verification_status: str
    requires_human_review: bool


class CuratedRecordEnvelope(BaseModel):
    """Atomic wrapper preserving a curated record and its review context."""

    model_config = ConfigDict(use_enum_values=True)

    record_id: str
    document_id: str
    source_path: str
    record: dict[str, Any]
    review_flags: list[dict[str, Any]] = Field(default_factory=list)
    review_flag_status: str
    retrieval_eligible: bool
    verification_status: str
    source_references: list[dict[str, Any]] = Field(default_factory=list)


class RetrievalRequest(BaseModel):
    """Canonical, read-only Module 5B retrieval request."""

    model_config = ConfigDict(use_enum_values=True)

    query: str = Field(min_length=1, max_length=4000)
    workflow: Workflow | None = None
    domains: list[Domain] = Field(default_factory=list)
    jurisdiction: Jurisdiction | None = None
    jurisdiction_detail: str | None = None
    local_authority: str | None = None
    legal_status: list[str] = Field(default_factory=list)
    quality_review_required: bool | None = None
    include_historical: bool = False
    include_supporting: bool = False
    top_k: int = Field(default=8, ge=1, le=50)
    primary_limit: int | None = Field(default=None, ge=1, le=50)
    supporting_limit: int | None = Field(default=None, ge=1, le=50)
    project_context: dict[str, Any] = Field(default_factory=dict)
