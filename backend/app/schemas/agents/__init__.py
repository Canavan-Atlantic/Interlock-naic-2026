"""Shared contracts for the future INTERLOCK agent workflow.

This package contains data contracts and typing protocols only.  It does not
implement agents, model calls, decisions, scoring, or recommendations.
"""

from .assessment import AssessmentFinding, AssessmentRequest, AssessmentResult
from .common import (
    AGENT_CONTRACT_VERSION,
    AssessmentStatus,
    ContradictionType,
    DependencyRecord,
    DependencyStatus,
    EvidenceCreatedBy,
    EvidenceSourceTrust,
    HumanReviewRequest,
    HumanReviewRole,
    HumanReviewSeverity,
    HumanReviewStatus,
    PotentialContradiction,
    ProjectContext,
    ProjectLifecycleStatus,
    ProjectLocation,
    SiteBoundary,
    WorkflowStatus,
)
from .evidence import AgentEvidenceState, EvidenceBundle, EvidenceRecord
from .explanation import (
    ExplanationAction,
    ExplanationRequest,
    ExplanationResult,
    ExplanationUnknownTheme,
)
from .interfaces import AssessmentAgent, EvidenceAgent, ExplanationAgent
from .result import InterlockResult

__all__ = [
    "AGENT_CONTRACT_VERSION",
    "AgentEvidenceState",
    "AssessmentAgent",
    "AssessmentFinding",
    "AssessmentRequest",
    "AssessmentResult",
    "AssessmentStatus",
    "ContradictionType",
    "DependencyRecord",
    "DependencyStatus",
    "EvidenceAgent",
    "EvidenceBundle",
    "EvidenceCreatedBy",
    "EvidenceSourceTrust",
    "EvidenceRecord",
    "ExplanationAgent",
    "ExplanationAction",
    "ExplanationRequest",
    "ExplanationResult",
    "ExplanationUnknownTheme",
    "HumanReviewRequest",
    "HumanReviewRole",
    "HumanReviewSeverity",
    "HumanReviewStatus",
    "InterlockResult",
    "PotentialContradiction",
    "ProjectContext",
    "ProjectLifecycleStatus",
    "ProjectLocation",
    "SiteBoundary",
    "WorkflowStatus",
]
