"""Customer-facing explanation contracts without a decision or recommendation."""

from __future__ import annotations

from pydantic import Field

from ...services.rag.models import CitationReference
from .assessment import AssessmentResult
from .common import ContractModel, ProjectContext


class ExplanationRequest(ContractModel):
    project_context: ProjectContext
    assessment_result: AssessmentResult


class ExplanationResult(ContractModel):
    executive_summary: str | None = None
    why_it_matters: list[str] = Field(default_factory=list)
    known_facts: list[str] = Field(default_factory=list)
    material_unknowns: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    human_handoffs: list[str] = Field(default_factory=list)
    source_citations: list[CitationReference] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


__all__ = ["ExplanationRequest", "ExplanationResult"]
