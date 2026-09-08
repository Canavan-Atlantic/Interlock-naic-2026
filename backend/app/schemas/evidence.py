"""Reusable evidence and evidence-ledger schemas."""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel


class EvidenceCategory(str, Enum):
    """High-level grouping for an evidence record."""

    PROJECT = "Project"
    SITE = "Site"
    POWER_AND_ENERGY = "Power & Energy"
    OTHER = "Other"


class EvidenceSourceType(str, Enum):
    """Source types supported by the evidence model."""

    CUSTOMER_INPUT = "customer_input"
    PUBLIC_DATASET = "public_dataset"
    CUSTOMER_DOCUMENT = "customer_document"
    POLICY_DOCUMENT = "policy_document"
    DETERMINISTIC_CALCULATION = "deterministic_calculation"
    HUMAN_REVIEW = "human_review"


class EvidenceState(str, Enum):
    """Capture state, not an assessment outcome such as pass or fail."""

    PROVIDED = "PROVIDED"
    UNKNOWN = "UNKNOWN"
    NOT_PROVIDED = "NOT_PROVIDED"


class EvidenceConfidence(str, Enum):
    """Confidence in capture of the value, not technical correctness."""

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNKNOWN = "UNKNOWN"


class EvidenceReviewStatus(str, Enum):
    """Whether a record has received a later review."""

    UNREVIEWED = "UNREVIEWED"
    REVIEWED = "REVIEWED"


class EvidenceRecord(BaseModel):
    """One captured fact and its provenance metadata."""

    evidence_id: str
    category: EvidenceCategory
    field_name: str
    fact: str
    value: Any | None = None
    unit: str | None = None
    source_type: EvidenceSourceType
    source_name: str
    source_reference: str | None = None
    evidence_state: EvidenceState
    confidence: EvidenceConfidence
    limitation: str | None = None
    review_status: EvidenceReviewStatus
    checked_at: datetime


class EvidenceLedger(BaseModel):
    """The in-memory evidence records generated for one project input."""

    project_name: str | None = None
    generated_at: datetime
    entries: list[EvidenceRecord]
    provided_count: int
    unknown_count: int
    not_provided_count: int
    missing_or_unknown: list[str]
