"""Customer-facing explanation contracts without a decision or recommendation."""

from __future__ import annotations

from pydantic import Field

from ...services.rag.models import CitationReference
from .assessment import AssessmentResult
from .common import ContractModel, ProjectContext
from .evidence import EvidenceBundle


class ExplanationRequest(ContractModel):
    project_context: ProjectContext
    assessment_result: AssessmentResult
    # Optional for compatibility with the original Module 6/7 hand-off.  When
    # supplied, the Explanation Agent can resolve evidence IDs to provenance
    # and citations without changing the AssessmentResult contract.
    evidence_bundle: EvidenceBundle | None = None


class ExplanationResult(ContractModel):
    executive_summary: str | None = None
    key_findings: list[str] = Field(default_factory=list)
    conditional_issues: list[str] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    why_it_matters: list[str] = Field(default_factory=list)
    known_facts: list[str] = Field(default_factory=list)
    material_unknowns: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    human_handoffs: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    source_citations: list[CitationReference] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


__all__ = ["ExplanationRequest", "ExplanationResult"]
