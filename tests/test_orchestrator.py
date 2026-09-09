from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.agents.assessment import DeterministicAssessmentAgent
from backend.app.agents.explanation import DeterministicExplanationAgent
from backend.app.agents.orchestrator import (
    DeterministicInterlockOrchestrator,
    OrchestratorOptions,
)
from backend.app.schemas.agents import (
    AssessmentRequest,
    AssessmentResult,
    EvidenceBundle,
    ExplanationRequest,
    ExplanationResult,
    HumanReviewRequest,
    HumanReviewRole,
    HumanReviewSeverity,
    HumanReviewStatus,
    InterlockResult,
    ProjectContext,
    WorkflowStatus,
)
from backend.app.services.rag.models import Domain


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "agents"


def _context(project_id: str = "orchestrator-test-project") -> ProjectContext:
    return ProjectContext(
        project_id=project_id,
        project_name=f"Project {project_id}",
        project_type="Data Centre",
        location={"country": "Ireland"},
    )


def _bundle(context: ProjectContext, *, review: HumanReviewRequest | None = None) -> EvidenceBundle:
    template = EvidenceBundle.model_validate_json(
        (FIXTURES / "evidence_bundle_example.json").read_text(encoding="utf-8")
    )
    return template.model_copy(
        deep=True,
        update={
            "project_context": context,
            "human_review_requests": [review] if review else [],
        },
    )


class RecordingEvidenceAgent:
    def __init__(self, bundle: EvidenceBundle | None = None, error: Exception | None = None) -> None:
        self.bundle = bundle
        self.error = error
        self.calls: list[tuple[ProjectContext, object]] = []

    def run(self, context: ProjectContext, options: object = None) -> EvidenceBundle:
        self.calls.append((context, options))
        if self.error:
            raise self.error
        assert self.bundle is not None
        return self.bundle


class RecordingAssessmentAgent:
    def __init__(self, result: AssessmentResult | None = None, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.calls: list[AssessmentRequest] = []

    def run(self, request: AssessmentRequest) -> AssessmentResult:
        self.calls.append(request)
        if self.error:
            raise self.error
        assert self.result is not None
        return self.result.model_copy(update={"project_context": request.project_context})


class RecordingExplanationAgent:
    def __init__(self, result: ExplanationResult | None = None, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.calls: list[ExplanationRequest] = []

    def run(self, request: ExplanationRequest) -> ExplanationResult:
        self.calls.append(request)
        if self.error:
            raise self.error
        assert self.result is not None
        return self.result


def _agents(
    context: ProjectContext,
    *,
    review: HumanReviewRequest | None = None,
    evidence_error: Exception | None = None,
    assessment_error: Exception | None = None,
    explanation_error: Exception | None = None,
) -> tuple[RecordingEvidenceAgent, RecordingAssessmentAgent, RecordingExplanationAgent]:
    evidence = RecordingEvidenceAgent(_bundle(context, review=review), evidence_error)
    assessment = RecordingAssessmentAgent(AssessmentResult(project_context=context), assessment_error)
    explanation = RecordingExplanationAgent(ExplanationResult(executive_summary="Synthetic explanation."), explanation_error)
    return evidence, assessment, explanation


def _orchestrator(
    evidence: RecordingEvidenceAgent,
    assessment: RecordingAssessmentAgent,
    explanation: RecordingExplanationAgent,
) -> DeterministicInterlockOrchestrator:
    return DeterministicInterlockOrchestrator(
        ROOT,
        evidence_agent=evidence,
        assessment_agent=assessment,
        explanation_agent=explanation,
    )


def test_pipeline_order_and_exact_contract_objects_are_preserved() -> None:
    context = _context()
    evidence, assessment, explanation = _agents(context)
    result = _orchestrator(evidence, assessment, explanation).run(context, OrchestratorOptions(run_id="run-001"))

    assert result.workflow_status == WorkflowStatus.COMPLETE
    assert result.evidence_bundle is evidence.bundle
    assert result.assessment_result is not None
    assert assessment.calls[0].evidence_bundle is evidence.bundle
    assert explanation.calls[0].evidence_bundle is evidence.bundle
    assert explanation.calls[0].assessment_result is result.assessment_result
    assert ["evidence", "assessment", "explanation"] == list(result.stage_status)
    assert result.stage_status == {
        "evidence": "COMPLETE",
        "assessment": "COMPLETE",
        "explanation": "COMPLETE",
    }


def test_evidence_failure_does_not_fabricate_payload_or_run_downstream() -> None:
    context = _context()
    evidence, assessment, explanation = _agents(context, evidence_error=RuntimeError("source unavailable"))
    result = _orchestrator(evidence, assessment, explanation).run(context)

    assert result.workflow_status == WorkflowStatus.FAILED
    assert result.evidence_bundle is None
    assert result.assessment_result is None
    assert result.explanation_result is None
    assert result.failure_stage == "evidence"
    assert result.stage_status["assessment"] == "SKIPPED"
    assert result.stage_status["explanation"] == "SKIPPED"
    assert not assessment.calls
    assert not explanation.calls


def test_assessment_failure_preserves_evidence_and_skips_explanation() -> None:
    context = _context()
    evidence, assessment, explanation = _agents(context, assessment_error=RuntimeError("assessment unavailable"))
    result = _orchestrator(evidence, assessment, explanation).run(context)

    assert result.workflow_status == WorkflowStatus.PARTIAL
    assert result.evidence_bundle is evidence.bundle
    assert result.assessment_result is None
    assert result.explanation_result is None
    assert result.failure_stage == "assessment"
    assert result.stage_status["explanation"] == "SKIPPED"
    assert not explanation.calls


def test_explanation_failure_preserves_evidence_and_assessment() -> None:
    context = _context()
    evidence, assessment, explanation = _agents(context, explanation_error=RuntimeError("explanation unavailable"))
    result = _orchestrator(evidence, assessment, explanation).run(context)

    assert result.workflow_status == WorkflowStatus.PARTIAL
    assert result.evidence_bundle is evidence.bundle
    assert result.assessment_result is not None
    assert result.explanation_result is None
    assert result.failure_stage == "explanation"


def test_unknown_domain_payload_can_complete_without_being_upgraded() -> None:
    context = _context()
    evidence, assessment, explanation = _agents(context)
    evidence.bundle = evidence.bundle.model_copy(
        update={"domain_summary": {"GRID": {"states": {"UNKNOWN": 1}}}, "missing_evidence": ["Grid evidence unknown"]}
    )
    result = _orchestrator(evidence, assessment, explanation).run(context)

    assert result.workflow_status == WorkflowStatus.COMPLETE
    assert result.evidence_bundle is not None
    assert result.evidence_bundle.domain_summary["GRID"]["states"]["UNKNOWN"] == 1


def test_human_review_requests_propagate_without_implying_approval() -> None:
    context = _context()
    review = HumanReviewRequest(
        review_id="review-grid-001",
        project_id=context.project_id,
        domain=Domain.GRID,
        reason="Confirm current connection status.",
    )
    evidence, assessment, explanation = _agents(context, review=review)
    result = _orchestrator(evidence, assessment, explanation).run(context)

    assert result.workflow_status == WorkflowStatus.REQUIRES_HUMAN_REVIEW
    assert result.requires_human_review is True
    assert [item.review_id for item in result.human_reviews] == ["review-grid-001"]
    assert "decision" not in result.model_dump()


def test_benchmark_documents_are_excluded_by_default_and_explicitly_opt_in() -> None:
    context = _context("herbata-test")
    evidence, assessment, explanation = _agents(context)
    orchestrator = _orchestrator(evidence, assessment, explanation)

    orchestrator.run(context)
    default_options = evidence.calls[-1][1]
    assert default_options.include_project_documents is True
    assert default_options.include_benchmark_documents is False

    orchestrator.run(
        context,
        OrchestratorOptions(include_benchmark_documents=True, run_id="validation-run"),
    )
    validation_options = evidence.calls[-1][1]
    assert validation_options.include_benchmark_documents is True


def test_request_scoped_runs_do_not_leak_between_projects() -> None:
    first = _context("project-a")
    second = _context("project-b")
    evidence, assessment, explanation = _agents(first)
    orchestrator = _orchestrator(evidence, assessment, explanation)

    first_result = orchestrator.run(first)
    evidence.bundle = _bundle(second)
    second_result = orchestrator.run(second)

    assert first_result.project_context.project_id == "project-a"
    assert second_result.project_context.project_id == "project-b"
    assert first_result.run_id != second_result.run_id
    assert first_result.evidence_bundle.project_context.project_id == "project-a"
    assert second_result.evidence_bundle.project_context.project_id == "project-b"


def test_two_projects_isolate_records_findings_reviews_citations_and_documents() -> None:
    from backend.app.services.rag.models import CitationReference
    from backend.app.schemas.agents import AssessmentFinding

    first_context = _context("isolated-a")
    second_context = _context("isolated-b")
    first_review = HumanReviewRequest(
        review_id="review-isolated-a",
        project_id=first_context.project_id,
        domain=Domain.GRID,
        reason="A-only review.",
        evidence_ids=["evidence-a"],
    )
    second_review = HumanReviewRequest(
        review_id="review-isolated-b",
        project_id=second_context.project_id,
        domain=Domain.WATER,
        reason="B-only review.",
        evidence_ids=["evidence-b"],
    )
    first_evidence, first_assessment, first_explanation = _agents(first_context, review=first_review)
    second_evidence, second_assessment, second_explanation = _agents(second_context, review=second_review)
    first_record = first_evidence.bundle.records[0].model_copy(
        update={"project_id": first_context.project_id, "evidence_id": "evidence-a"}
    )
    second_record = second_evidence.bundle.records[0].model_copy(
        update={"project_id": second_context.project_id, "evidence_id": "evidence-b"}
    )
    first_evidence.bundle = first_evidence.bundle.model_copy(update={"records": [first_record]})
    second_evidence.bundle = second_evidence.bundle.model_copy(update={"records": [second_record]})
    first_assessment.result = AssessmentResult(
        project_context=first_context,
        findings=[AssessmentFinding(finding_id="finding-a", domain=Domain.GRID)],
    )
    second_assessment.result = AssessmentResult(
        project_context=second_context,
        findings=[AssessmentFinding(finding_id="finding-b", domain=Domain.WATER)],
    )
    first_explanation.result = ExplanationResult(
        evidence_ids=["evidence-a"],
        source_citations=[CitationReference(document_id="doc-a", source_path="a", locator="p.1")],
    )
    second_explanation.result = ExplanationResult(
        evidence_ids=["evidence-b"],
        source_citations=[CitationReference(document_id="doc-b", source_path="b", locator="p.1")],
    )

    first = _orchestrator(first_evidence, first_assessment, first_explanation).run(first_context)
    second = _orchestrator(second_evidence, second_assessment, second_explanation).run(second_context)

    assert first.evidence_bundle.records[0].evidence_id == "evidence-a"
    assert second.evidence_bundle.records[0].evidence_id == "evidence-b"
    assert first.assessment_result.findings[0].finding_id == "finding-a"
    assert second.assessment_result.findings[0].finding_id == "finding-b"
    assert [review.review_id for review in first.human_reviews] == ["review-isolated-a"]
    assert [review.review_id for review in second.human_reviews] == ["review-isolated-b"]
    assert first.explanation_result.evidence_ids == ["evidence-a"]
    assert second.explanation_result.evidence_ids == ["evidence-b"]
    assert first.explanation_result.source_citations[0].document_id == "doc-a"
    assert second.explanation_result.source_citations[0].document_id == "doc-b"
    assert first.timings_ms is not second.timings_ms
    assert first.run_id != second.run_id


def test_timings_counts_and_serialisation_are_present_without_decision_fields() -> None:
    context = _context()
    evidence, assessment, explanation = _agents(context)
    result = _orchestrator(evidence, assessment, explanation).run(context, OrchestratorOptions(run_id="timed-run"))
    payload = result.model_dump(mode="json")

    assert result.run_id == "timed-run"
    assert set(result.timings_ms) == {"evidence", "assessment", "explanation", "total"}
    assert all(value >= 0 for value in result.timings_ms.values())
    assert result.stage_counts["evidence"] == len(result.evidence_bundle.records)
    assert result.stage_counts["assessment"] == 0
    assert "score" not in payload
    assert "recommendation" not in payload
    assert "decision" not in payload
    assert json.loads(result.model_dump_json())["workflow_status"] == "COMPLETE"


def test_echelon_scope_change_stays_uncertain_and_does_not_create_a_decision() -> None:
    bundle = EvidenceBundle.model_validate_json(
        (FIXTURES / "echelon_scope_change_example.json").read_text(encoding="utf-8")
    )
    evidence = RecordingEvidenceAgent(bundle)
    orchestrator = DeterministicInterlockOrchestrator(
        ROOT,
        evidence_agent=evidence,
        assessment_agent=DeterministicAssessmentAgent(),
        explanation_agent=DeterministicExplanationAgent(),
    )

    result = orchestrator.run(bundle.project_context)
    assert result.assessment_result is not None
    assert result.explanation_result is not None
    combined = " ".join(
        result.explanation_result.key_findings
        + result.explanation_result.conditional_issues
        + result.explanation_result.material_unknowns
    ).casefold()
    assert "energisation" in combined
    assert "renewable" in combined
    assert "decision" not in result.model_dump()


def test_interlock_endpoint_serialises_the_existing_result_contract(monkeypatch) -> None:
    from backend.app import main as main_module

    context = _context("api-project")
    evidence, assessment, explanation = _agents(context)
    orchestrator = _orchestrator(evidence, assessment, explanation)
    monkeypatch.setattr(main_module, "DeterministicInterlockOrchestrator", lambda _root: orchestrator)

    response = TestClient(main_module.app).post(
        "/interlock/run?run_id=api-run",
        json=context.model_dump(mode="json"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["run_id"] == "api-run"
    assert payload["stage_status"]["evidence"] == "COMPLETE"
    assert payload["explanation_result"]["executive_summary"] == "Synthetic explanation."


def test_failure_metadata_does_not_copy_secrets_or_document_text() -> None:
    context = _context()
    evidence, assessment, explanation = _agents(
        context,
        evidence_error=RuntimeError("OPENAI_API_KEY=sk-secret complete policy text must not escape"),
    )
    result = _orchestrator(evidence, assessment, explanation).run(context)

    serialized = result.model_dump_json()
    assert "sk-secret" not in serialized
    assert "complete policy text" not in serialized
    assert "RuntimeError" in result.failure_message
    assert "traceback" not in serialized.casefold()


def test_assessment_context_and_explanation_context_are_the_original_request_context() -> None:
    context = _context("identity-project")
    evidence, assessment, explanation = _agents(context)
    _orchestrator(evidence, assessment, explanation).run(context)

    assert assessment.calls[0].project_context is context
    assert explanation.calls[0].project_context is context


def test_assessment_review_is_propagated_when_evidence_has_no_review() -> None:
    context = _context()
    review = HumanReviewRequest(
        review_id="review-assessment-001",
        project_id=context.project_id,
        domain=Domain.PLANNING,
        reason="Confirm planning position.",
    )
    evidence, assessment, explanation = _agents(context)
    assessment.result = AssessmentResult(project_context=context, human_reviews=[review])
    result = _orchestrator(evidence, assessment, explanation).run(context)

    assert result.requires_human_review is True
    assert result.workflow_status == WorkflowStatus.REQUIRES_HUMAN_REVIEW
    assert [item.review_id for item in result.human_reviews] == ["review-assessment-001"]


def test_duplicate_review_ids_are_not_multiplied_in_composed_result() -> None:
    context = _context()
    review = HumanReviewRequest(
        review_id="review-shared-001",
        project_id=context.project_id,
        domain=Domain.GRID,
        reason="Same review referenced by both stages.",
    )
    evidence, assessment, explanation = _agents(context, review=review)
    assessment.result = AssessmentResult(project_context=context, human_reviews=[review])
    result = _orchestrator(evidence, assessment, explanation).run(context)

    assert [item.review_id for item in result.human_reviews] == ["review-shared-001"]


def test_project_documents_can_be_disabled_without_enabling_benchmarks() -> None:
    context = _context()
    evidence, assessment, explanation = _agents(context)
    _orchestrator(evidence, assessment, explanation).run(
        context,
        OrchestratorOptions(include_project_documents=False),
    )

    options = evidence.calls[-1][1]
    assert options.include_project_documents is False
    assert options.include_benchmark_documents is False


def test_run_id_is_request_scoped_and_has_no_shared_mutable_workflow_state() -> None:
    first_context = _context("first")
    second_context = _context("second")
    first_agents = _agents(first_context)
    second_agents = _agents(second_context)
    first = _orchestrator(*first_agents).run(first_context)
    second = _orchestrator(*second_agents).run(second_context)

    assert first.run_id.startswith("first-")
    assert second.run_id.startswith("second-")
    assert first.run_id != second.run_id
    assert first.stage_status is not second.stage_status


def test_partial_failure_retains_completed_stage_counts_and_timings() -> None:
    context = _context()
    evidence, assessment, explanation = _agents(context, explanation_error=RuntimeError("failed"))
    result = _orchestrator(evidence, assessment, explanation).run(context)

    assert result.stage_counts["evidence"] == len(evidence.bundle.records)
    assert result.stage_counts["assessment"] == 0
    assert "evidence" in result.timings_ms
    assert "assessment" in result.timings_ms
    assert "explanation" in result.timings_ms
    assert result.timings_ms["total"] >= result.timings_ms["explanation"]


def test_failed_result_round_trips_with_missing_downstream_payloads() -> None:
    context = _context()
    evidence, assessment, explanation = _agents(context, assessment_error=RuntimeError("failed"))
    result = _orchestrator(evidence, assessment, explanation).run(context)
    round_tripped = type(result).model_validate_json(result.model_dump_json())

    assert round_tripped.evidence_bundle is not None
    assert round_tripped.assessment_result is None
    assert round_tripped.explanation_result is None
    assert round_tripped.workflow_status == WorkflowStatus.PARTIAL


def test_each_stage_runs_at_most_once_per_request() -> None:
    context = _context()
    evidence, assessment, explanation = _agents(context)
    _orchestrator(evidence, assessment, explanation).run(context)

    assert len(evidence.calls) == 1
    assert len(assessment.calls) == 1
    assert len(explanation.calls) == 1


def test_successful_result_contains_all_three_stage_outputs() -> None:
    context = _context()
    evidence, assessment, explanation = _agents(context)
    result = _orchestrator(evidence, assessment, explanation).run(context)

    assert result.evidence_bundle is not None
    assert result.assessment_result is not None
    assert result.explanation_result is not None
    assert result.failure_stage is None
    assert result.stage_errors == {}


def test_endpoint_defaults_to_non_benchmark_evidence_mode(monkeypatch) -> None:
    from backend.app import main as main_module

    context = _context("default-api-project")
    evidence, assessment, explanation = _agents(context)
    orchestrator = _orchestrator(evidence, assessment, explanation)
    monkeypatch.setattr(main_module, "DeterministicInterlockOrchestrator", lambda _root: orchestrator)

    response = TestClient(main_module.app).post(
        "/interlock/run",
        json=context.model_dump(mode="json"),
    )

    assert response.status_code == 200
    options = evidence.calls[-1][1]
    assert options.include_benchmark_documents is False


def test_final_review_ids_are_exactly_the_unique_upstream_union() -> None:
    context = _context()
    evidence_review = HumanReviewRequest(
        review_id="upstream-evidence-review",
        project_id=context.project_id,
        domain=Domain.GRID,
        reason="Evidence review.",
        evidence_ids=["evidence-a"],
    )
    assessment_review = HumanReviewRequest(
        review_id="upstream-assessment-review",
        project_id=context.project_id,
        domain=Domain.PLANNING,
        reason="Assessment review.",
        evidence_ids=["evidence-b"],
    )
    evidence, assessment, explanation = _agents(context, review=evidence_review)
    assessment.result = AssessmentResult(
        project_context=context,
        human_reviews=[evidence_review, assessment_review],
    )
    result = _orchestrator(evidence, assessment, explanation).run(context)

    assert {item.review_id for item in result.human_reviews} == {
        "upstream-evidence-review",
        "upstream-assessment-review",
    }
    assert len(result.human_reviews) == 2


def test_duplicate_reviews_keep_highest_severity_role_and_all_evidence_ids() -> None:
    context = _context()
    evidence_review = HumanReviewRequest(
        review_id="review-merge-001",
        project_id=context.project_id,
        domain=Domain.GRID,
        reason="Connection review.",
        severity=HumanReviewSeverity.MATERIAL,
        recommended_role=HumanReviewRole.GRID_ENGINEER,
        evidence_ids=["evidence-a"],
    )
    assessment_review = evidence_review.model_copy(
        update={
            "severity": HumanReviewSeverity.HIGH_CONSEQUENCE,
            "recommended_role": HumanReviewRole.UNKNOWN,
            "evidence_ids": ["evidence-b"],
        }
    )
    evidence, assessment, explanation = _agents(context, review=evidence_review)
    assessment.result = AssessmentResult(project_context=context, human_reviews=[assessment_review])
    result = _orchestrator(evidence, assessment, explanation).run(context)

    merged = result.human_reviews[0]
    assert merged.severity == HumanReviewSeverity.HIGH_CONSEQUENCE.value
    assert merged.recommended_role == HumanReviewRole.GRID_ENGINEER.value
    assert merged.evidence_ids == ["evidence-a", "evidence-b"]


def test_completed_review_is_preserved_but_does_not_trigger_review_gate() -> None:
    context = _context()
    completed_review = HumanReviewRequest(
        review_id="review-completed-001",
        project_id=context.project_id,
        domain=Domain.GRID,
        reason="Already resolved upstream.",
        status=HumanReviewStatus.COMPLETED,
    )
    evidence, assessment, explanation = _agents(context, review=completed_review)
    result = _orchestrator(evidence, assessment, explanation).run(context)

    assert result.human_reviews[0].review_id == "review-completed-001"
    assert result.requires_human_review is False
    assert result.workflow_status == WorkflowStatus.COMPLETE


def test_review_required_overall_status_is_not_a_technical_failure() -> None:
    context = _context()
    review = HumanReviewRequest(
        review_id="review-required-001",
        project_id=context.project_id,
        domain=Domain.GRID,
        reason="Unresolved grid question.",
    )
    evidence, assessment, explanation = _agents(context, review=review)
    result = _orchestrator(evidence, assessment, explanation).run(context)

    assert result.stage_status == {
        "evidence": "COMPLETE",
        "assessment": "COMPLETE",
        "explanation": "COMPLETE",
    }
    assert result.workflow_status == WorkflowStatus.REQUIRES_HUMAN_REVIEW
    assert result.workflow_status not in {WorkflowStatus.FAILED, WorkflowStatus.PARTIAL}


def test_legacy_shared_contract_payloads_still_deserialise() -> None:
    legacy = json.loads(
        (FIXTURES / "interlock_result_example.json").read_text(encoding="utf-8")
    )
    result = InterlockResult.model_validate(legacy)
    evidence = EvidenceBundle.model_validate_json(
        (FIXTURES / "evidence_bundle_example.json").read_text(encoding="utf-8")
    )
    assessment = AssessmentResult.model_validate_json(
        (FIXTURES / "assessment_result_example.json").read_text(encoding="utf-8")
    )
    explanation = ExplanationResult.model_validate_json(
        (FIXTURES / "explanation_result_example.json").read_text(encoding="utf-8")
    )

    assert result.workflow_status == WorkflowStatus.COMPLETE
    assert result.evidence_bundle.project_context.project_id == evidence.project_context.project_id
    assert result.assessment_result.project_context.project_id == assessment.project_context.project_id
    assert explanation.model_dump(mode="json")
    assert result.run_id is None
    assert result.stage_status == {}


def test_api_failure_result_is_structured_without_internal_details(monkeypatch) -> None:
    from backend.app import main as main_module

    context = _context("safe-api-project")
    evidence, assessment, explanation = _agents(
        context,
        evidence_error=RuntimeError(
            "Traceback: C:\\private\\project\\secret.py OPENAI_API_KEY=sk-test-secret"
        ),
    )
    orchestrator = _orchestrator(evidence, assessment, explanation)
    monkeypatch.setattr(main_module, "DeterministicInterlockOrchestrator", lambda _root: orchestrator)

    response = TestClient(main_module.app).post(
        "/interlock/run",
        json=context.model_dump(mode="json"),
    )

    assert response.status_code == 200
    payload = response.json()
    serialized = response.text
    assert payload["workflow_status"] == "FAILED"
    assert payload["stage_status"]["evidence"] == "FAILED"
    assert payload["stage_status"]["assessment"] == "SKIPPED"
    assert payload["evidence_bundle"] is None
    assert "Traceback" not in serialized
    assert "private\\project" not in serialized
    assert "sk-test-secret" not in serialized


def test_individual_agent_routes_remain_registered_alongside_orchestrator() -> None:
    from backend.app.main import app

    routes = {
        (method, route.path)
        for route in app.routes
        for method in getattr(route, "methods", set())
    }
    assert ("POST", "/agents/evidence") in routes
    assert ("POST", "/agents/assessment") in routes
    assert ("POST", "/agents/explanation") in routes
    assert ("POST", "/interlock/run") in routes
