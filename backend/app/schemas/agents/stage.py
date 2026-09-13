"""Deterministic customer-stage intelligence contracts."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from .common import ContractModel


class StageRequirementStatus(str):
    """String values used for a stage requirement display."""

    SATISFIED = "SATISFIED"
    REQUIRED_TO_PROGRESS = "REQUIRED_TO_PROGRESS"
    NOT_REQUIRED_AT_STAGE = "NOT_REQUIRED_AT_STAGE"


class StageRequirement(ContractModel):
    requirement_id: str
    label: str
    status: Literal["SATISFIED", "REQUIRED_TO_PROGRESS", "NOT_REQUIRED_AT_STAGE"]
    why_required: str
    next_step: str
    owner: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)


class StageIntelligence(ContractModel):
    stage: str
    purpose: str
    customer_question: str
    evidence_expectations: list[str] = Field(default_factory=list)
    relevant_inputs: list[str] = Field(default_factory=list)
    not_required_at_stage: list[str] = Field(default_factory=list)
    investigation_emphasis: list[str] = Field(default_factory=list)
    missing_evidence_wording: str
    progression_criteria: list[str] = Field(default_factory=list)
    provided_inputs: list[str] = Field(default_factory=list)
    required_to_progress: list[StageRequirement] = Field(default_factory=list)
    evidence_maturity_summary: dict[str, int] = Field(default_factory=dict)


class StageAssessmentView(ContractModel):
    """The bounded customer view shared by the UI and executive report."""

    stage: str
    customer_question: str
    requirement_heading: str
    not_required_at_stage: list[str] = Field(default_factory=list)
    provided_inputs: list[str] = Field(default_factory=list)
    relevant_findings: list[dict[str, Any]] = Field(default_factory=list)
    information_required: list[dict[str, Any]] = Field(default_factory=list)
    professional_reviews: list[dict[str, Any]] = Field(default_factory=list)
    next_actions: list[dict[str, Any]] = Field(default_factory=list)
    domain_states: list[dict[str, Any]] = Field(default_factory=list)
    relevant_evidence_ids: list[str] = Field(default_factory=list)
    relevant_evidence_count: int = 0
    total_evidence_count: int = 0
    counts: dict[str, int] = Field(default_factory=dict)


__all__ = ["StageAssessmentView", "StageIntelligence", "StageRequirement", "StageRequirementStatus"]
