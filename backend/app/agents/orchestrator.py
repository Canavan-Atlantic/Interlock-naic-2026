"""Deterministic composition of the INTERLOCK agent pipeline."""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from ..schemas.agents import (
    AssessmentRequest,
    AssessmentResult,
    EvidenceBundle,
    EvidenceAgent,
    ExplanationRequest,
    ExplanationResult,
    InterlockResult,
    HumanReviewRequest,
    HumanReviewStatus,
    ProjectContext,
    WorkflowStatus,
)
from .assessment import DeterministicAssessmentAgent
from .evidence import DeterministicEvidenceAgent, EvidenceAgentOptions
from .explanation import DeterministicExplanationAgent
from .planner import BoundedInvestigationPlanner, InvestigationPlanner, PlannerSettings
from ..services.stage_intelligence import build_stage_intelligence


@dataclass(frozen=True)
class OrchestratorOptions:
    """Request-scoped switches for one fixed pipeline execution."""

    include_project_documents: bool = True
    include_benchmark_documents: bool = False
    run_id: str | None = None


_STAGE_EVIDENCE = "evidence"
_STAGE_ASSESSMENT = "assessment"
_STAGE_EXPLANATION = "explanation"
_STAGES = (_STAGE_EVIDENCE, _STAGE_ASSESSMENT, _STAGE_EXPLANATION)


def _safe_failure(stage: str, error: BaseException) -> str:
    """Return an operational error without copying exception payloads."""

    # Exception strings can contain request bodies, document text, or provider
    # headers.  The stage and exception class are enough for a controlled API
    # result and keep those values out of logs and serialized workflow state.
    return f"{stage} stage failed ({type(error).__name__})"


def _reviews_for(
    evidence_bundle: EvidenceBundle | None,
    assessment_result: AssessmentResult | None,
) -> list[HumanReviewRequest]:
    """Consolidate upstream review state without inventing review IDs."""

    by_id: dict[str, HumanReviewRequest] = {}
    for candidates in (
        evidence_bundle.human_review_requests if evidence_bundle else [],
        assessment_result.human_reviews if assessment_result else [],
    ):
        for review in candidates:
            existing = by_id.get(review.review_id)
            if existing is None:
                by_id[review.review_id] = review.model_copy(deep=True)
                continue

            # Assessment may refine the severity of an evidence-originated
            # request.  Keep the stronger upstream severity, merge all
            # evidence IDs, and never replace a known specialist role with
            # UNKNOWN merely because the duplicate has weaker metadata.
            current = existing
            candidate = review
            selected = (
                candidate
                if _severity_rank(candidate.severity) > _severity_rank(current.severity)
                else current
            ).model_copy(deep=True)
            selected.evidence_ids = list(
                dict.fromkeys([*current.evidence_ids, *candidate.evidence_ids])
            )
            if _role_value(selected.recommended_role) == "UNKNOWN":
                alternate_role = (
                    candidate.recommended_role
                    if _role_value(current.recommended_role) == "UNKNOWN"
                    else current.recommended_role
                )
                if _role_value(alternate_role) != "UNKNOWN":
                    selected.recommended_role = alternate_role
            if _review_is_unresolved(current) or _review_is_unresolved(candidate):
                selected.status = HumanReviewStatus.REQUIRED.value
            by_id[review.review_id] = selected
    return list(by_id.values())


def _severity_rank(value: object) -> int:
    return {
        "INFORMATIONAL": 0,
        "MATERIAL": 1,
        "HIGH_CONSEQUENCE": 2,
    }.get(_enum_value(value), 1)


def _role_value(value: object) -> str:
    return _enum_value(value)


def _review_is_unresolved(review: HumanReviewRequest) -> bool:
    return _enum_value(review.status) not in {
        HumanReviewStatus.COMPLETED.value,
        HumanReviewStatus.NOT_REQUIRED.value,
    }


def _requires_human_review(reviews: list[HumanReviewRequest]) -> bool:
    return any(_review_is_unresolved(review) for review in reviews)


def _enum_value(value: object) -> str:
    return str(getattr(value, "value", value))


class DeterministicInterlockOrchestrator:
    """Run Evidence -> Assessment -> Explanation in a fixed order."""

    def __init__(
        self,
        project_root: Path,
        *,
        evidence_agent: EvidenceAgent | None = None,
        assessment_agent: object | None = None,
        explanation_agent: object | None = None,
        planner: InvestigationPlanner | None = None,
    ) -> None:
        self.evidence_agent = evidence_agent or DeterministicEvidenceAgent(project_root)
        self.assessment_agent = assessment_agent or DeterministicAssessmentAgent()
        self.explanation_agent = explanation_agent or DeterministicExplanationAgent()
        self.planner = planner or BoundedInvestigationPlanner()

    @staticmethod
    def _call_evidence_agent(
        agent: object,
        context: ProjectContext,
        options: OrchestratorOptions,
        investigation_plan: object,
    ) -> EvidenceBundle:
        """Support both the original one-argument protocol and concrete options."""

        runner = agent.run
        evidence_options = EvidenceAgentOptions(
            include_project_documents=options.include_project_documents,
            include_benchmark_documents=options.include_benchmark_documents,
            investigation_plan=investigation_plan,
        )
        try:
            inspect.signature(runner).bind(context, evidence_options)
        except (TypeError, ValueError):
            return runner(context)
        return runner(context, evidence_options)

    @staticmethod
    def _result(
        context: ProjectContext,
        *,
        run_id: str,
        evidence_bundle: EvidenceBundle | None,
        assessment_result: AssessmentResult | None,
        explanation_result: ExplanationResult | None,
        workflow_status: WorkflowStatus,
        stage_status: dict[str, str],
        stage_errors: dict[str, str],
        stage_counts: dict[str, int],
        timings_ms: dict[str, float],
        investigation_plan: object | None = None,
        failure_stage: str | None = None,
        failure_message: str | None = None,
    ) -> InterlockResult:
        reviews = _reviews_for(evidence_bundle, assessment_result)
        return InterlockResult(
            project_context=context,
            evidence_bundle=evidence_bundle,
            assessment_result=assessment_result,
            explanation_result=explanation_result,
            investigation_plan=investigation_plan,
            stage_intelligence=build_stage_intelligence(context, evidence_bundle, assessment_result),
            workflow_status=workflow_status,
            human_reviews=reviews,
            requires_human_review=_requires_human_review(reviews),
            run_id=run_id,
            stage_status=stage_status,
            stage_errors=stage_errors,
            stage_counts=stage_counts,
            timings_ms=timings_ms,
            failure_stage=failure_stage,
            failure_message=failure_message,
        )

    def run(
        self,
        project_context: ProjectContext,
        options: OrchestratorOptions | None = None,
    ) -> InterlockResult:
        """Execute the fixed pipeline with isolated, stage-aware failure handling."""

        options = options or OrchestratorOptions()
        run_id = options.run_id or f"{project_context.project_id}-{uuid4().hex[:12]}"
        started = perf_counter()
        stage_status = {stage: "NOT_STARTED" for stage in _STAGES}
        stage_errors: dict[str, str] = {}
        stage_counts: dict[str, int] = {}
        timings_ms: dict[str, float] = {}

        # Planning is a bounded scope step.  It is deliberately outside the
        # Evidence/Assessment/Explanation stage status contract so existing
        # consumers retain the same three deterministic stages.  The plan
        # carries planner and validation timings as provenance.
        try:
            investigation_plan = self.planner.plan(
                project_context,
                include_project_documents=options.include_project_documents,
            )
        except Exception:
            # A custom planner cannot make the deterministic pipeline fail.
            investigation_plan = BoundedInvestigationPlanner(
                settings=PlannerSettings(mode="deterministic_fallback")
            ).plan(
                project_context,
                include_project_documents=options.include_project_documents,
            )

        stage_status[_STAGE_EVIDENCE] = WorkflowStatus.IN_PROGRESS.value
        stage_started = perf_counter()
        try:
            evidence_bundle = self._call_evidence_agent(
                self.evidence_agent,
                project_context,
                options,
                investigation_plan,
            )
        except Exception as error:
            elapsed = round((perf_counter() - stage_started) * 1000, 3)
            timings_ms[_STAGE_EVIDENCE] = elapsed
            timings_ms["total"] = round((perf_counter() - started) * 1000, 3)
            stage_status[_STAGE_EVIDENCE] = WorkflowStatus.FAILED.value
            stage_status[_STAGE_ASSESSMENT] = "SKIPPED"
            stage_status[_STAGE_EXPLANATION] = "SKIPPED"
            failure = _safe_failure(_STAGE_EVIDENCE, error)
            stage_errors[_STAGE_EVIDENCE] = failure
            return self._result(
                project_context,
                run_id=run_id,
                evidence_bundle=None,
                assessment_result=None,
                explanation_result=None,
                workflow_status=WorkflowStatus.FAILED,
                stage_status=stage_status,
                stage_errors=stage_errors,
                stage_counts=stage_counts,
                timings_ms=timings_ms,
                investigation_plan=investigation_plan,
                failure_stage=_STAGE_EVIDENCE,
                failure_message=failure,
            )

        timings_ms[_STAGE_EVIDENCE] = round((perf_counter() - stage_started) * 1000, 3)
        stage_status[_STAGE_EVIDENCE] = WorkflowStatus.COMPLETE.value
        stage_counts[_STAGE_EVIDENCE] = len(evidence_bundle.records)

        stage_status[_STAGE_ASSESSMENT] = WorkflowStatus.IN_PROGRESS.value
        stage_started = perf_counter()
        try:
            assessment_result = self.assessment_agent.run(
                AssessmentRequest(
                    project_context=project_context,
                    evidence_bundle=evidence_bundle,
                )
            )
        except Exception as error:
            timings_ms[_STAGE_ASSESSMENT] = round((perf_counter() - stage_started) * 1000, 3)
            timings_ms["total"] = round((perf_counter() - started) * 1000, 3)
            stage_status[_STAGE_ASSESSMENT] = WorkflowStatus.FAILED.value
            stage_status[_STAGE_EXPLANATION] = "SKIPPED"
            failure = _safe_failure(_STAGE_ASSESSMENT, error)
            stage_errors[_STAGE_ASSESSMENT] = failure
            return self._result(
                project_context,
                run_id=run_id,
                evidence_bundle=evidence_bundle,
                assessment_result=None,
                explanation_result=None,
                workflow_status=WorkflowStatus.PARTIAL,
                stage_status=stage_status,
                stage_errors=stage_errors,
                stage_counts=stage_counts,
                timings_ms=timings_ms,
                investigation_plan=investigation_plan,
                failure_stage=_STAGE_ASSESSMENT,
                failure_message=failure,
            )

        timings_ms[_STAGE_ASSESSMENT] = round((perf_counter() - stage_started) * 1000, 3)
        stage_status[_STAGE_ASSESSMENT] = WorkflowStatus.COMPLETE.value
        stage_counts[_STAGE_ASSESSMENT] = len(assessment_result.findings)

        stage_status[_STAGE_EXPLANATION] = WorkflowStatus.IN_PROGRESS.value
        stage_started = perf_counter()
        try:
            explanation_result = self.explanation_agent.run(
                ExplanationRequest(
                    project_context=project_context,
                    assessment_result=assessment_result,
                    evidence_bundle=evidence_bundle,
                )
            )
        except Exception as error:
            timings_ms[_STAGE_EXPLANATION] = round((perf_counter() - stage_started) * 1000, 3)
            timings_ms["total"] = round((perf_counter() - started) * 1000, 3)
            stage_status[_STAGE_EXPLANATION] = WorkflowStatus.FAILED.value
            failure = _safe_failure(_STAGE_EXPLANATION, error)
            stage_errors[_STAGE_EXPLANATION] = failure
            return self._result(
                project_context,
                run_id=run_id,
                evidence_bundle=evidence_bundle,
                assessment_result=assessment_result,
                explanation_result=None,
                workflow_status=WorkflowStatus.PARTIAL,
                stage_status=stage_status,
                stage_errors=stage_errors,
                stage_counts=stage_counts,
                timings_ms=timings_ms,
                investigation_plan=investigation_plan,
                failure_stage=_STAGE_EXPLANATION,
                failure_message=failure,
            )

        timings_ms[_STAGE_EXPLANATION] = round((perf_counter() - stage_started) * 1000, 3)
        stage_status[_STAGE_EXPLANATION] = WorkflowStatus.COMPLETE.value
        stage_counts[_STAGE_EXPLANATION] = len(explanation_result.key_findings)
        timings_ms["total"] = round((perf_counter() - started) * 1000, 3)
        reviews = _reviews_for(evidence_bundle, assessment_result)
        workflow_status = (
            WorkflowStatus.REQUIRES_HUMAN_REVIEW
            if _requires_human_review(reviews)
            else WorkflowStatus.COMPLETE
        )
        return self._result(
            project_context,
            run_id=run_id,
            evidence_bundle=evidence_bundle,
            assessment_result=assessment_result,
            explanation_result=explanation_result,
            workflow_status=workflow_status,
            stage_status=stage_status,
            stage_errors=stage_errors,
            stage_counts=stage_counts,
            timings_ms=timings_ms,
            investigation_plan=investigation_plan,
        )


InterlockOrchestrator = DeterministicInterlockOrchestrator


__all__ = [
    "DeterministicInterlockOrchestrator",
    "InterlockOrchestrator",
    "OrchestratorOptions",
]
