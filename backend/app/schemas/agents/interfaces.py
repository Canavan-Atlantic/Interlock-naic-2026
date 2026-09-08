"""Lightweight protocols for future agent implementations."""

from __future__ import annotations

from typing import Protocol

from .assessment import AssessmentRequest, AssessmentResult
from .common import ProjectContext
from .evidence import EvidenceBundle
from .explanation import ExplanationRequest, ExplanationResult


class EvidenceAgent(Protocol):
    def run(self, project_context: ProjectContext) -> EvidenceBundle:
        """Collect and provenance evidence; make no final decision."""


class AssessmentAgent(Protocol):
    def run(self, request: AssessmentRequest) -> AssessmentResult:
        """Assess evidence and constraints; make no investment decision."""


class ExplanationAgent(Protocol):
    def run(self, request: ExplanationRequest) -> ExplanationResult:
        """Explain results and handoffs; make no recommendation."""


__all__ = ["AssessmentAgent", "EvidenceAgent", "ExplanationAgent"]
