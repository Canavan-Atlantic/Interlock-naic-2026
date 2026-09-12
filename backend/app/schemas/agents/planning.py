"""Strict contracts for bounded INTERLOCK evidence planning.

The planning contract is deliberately narrower than an agent tool protocol. It
describes evidence to acquire and never contains a score, recommendation,
decision, policy override, or executable instruction.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import ConfigDict, Field

from ...services.rag.models import Domain
from .common import ContractModel


class PlanningMode(str, Enum):
    """How the investigation plan was produced."""

    BOUNDED_LLM = "BOUNDED_LLM"
    DETERMINISTIC_FALLBACK = "DETERMINISTIC_FALLBACK"


class ApprovedToolName(str, Enum):
    """The only evidence capabilities a planner may request."""

    POLICY_RAG_SEARCH = "POLICY_RAG_SEARCH"
    GIS_SITE_EVIDENCE = "GIS_SITE_EVIDENCE"
    PROJECT_DOCUMENT_SEARCH = "PROJECT_DOCUMENT_SEARCH"
    DEVELOPER_INPUT_EVIDENCE = "DEVELOPER_INPUT_EVIDENCE"


class InvestigationPriority(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class PlannerTokenUsage(ContractModel):
    """Optional provider telemetry; never a prompt or reasoning transcript."""

    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)


class PlanRejection(ContractModel):
    """Safe rejection audit entry without copying untrusted generated text."""

    request_index: int | None = Field(default=None, ge=0)
    field: str
    reason_code: str


class ToolRequest(ContractModel):
    """One validated request for an existing deterministic evidence capability."""

    tool: ApprovedToolName
    domain: Domain
    query: str = Field(min_length=1, max_length=500)
    priority: InvestigationPriority = InvestigationPriority.MEDIUM
    required: bool = False


class InvestigationItem(ContractModel):
    """Human-readable scope for one bounded investigation question."""

    domain: Domain
    question: str = Field(min_length=1, max_length=500)
    reason: str = Field(min_length=1, max_length=300)
    tool: ApprovedToolName
    priority: InvestigationPriority = InvestigationPriority.MEDIUM


class InvestigationPlan(ContractModel):
    """Complete, strict, serialisable planning provenance for one run."""

    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    plan_id: str = Field(min_length=1, max_length=100)
    project_id: str = Field(min_length=1, max_length=200)
    planning_mode: PlanningMode
    llm_used: bool = False
    model: str | None = Field(default=None, max_length=100)
    selected_domains: list[Domain] = Field(min_length=1, max_length=12)
    investigation_items: list[InvestigationItem] = Field(min_length=1, max_length=16)
    tool_requests: list[ToolRequest] = Field(min_length=1, max_length=24)
    unresolved_input_gaps: list[str] = Field(default_factory=list, max_length=16)
    rejected_requests: list[PlanRejection] = Field(default_factory=list, max_length=24)
    fallback_reason: str | None = Field(default=None, max_length=80)
    planner_duration_ms: float = Field(default=0.0, ge=0)
    validation_duration_ms: float = Field(default=0.0, ge=0)
    total_duration_ms: float = Field(default=0.0, ge=0)
    token_usage: PlannerTokenUsage | None = None
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    schema_version: str = "1.0"


__all__ = [
    "ApprovedToolName",
    "InvestigationItem",
    "InvestigationPlan",
    "InvestigationPriority",
    "PlanRejection",
    "PlannerTokenUsage",
    "PlanningMode",
    "ToolRequest",
]
