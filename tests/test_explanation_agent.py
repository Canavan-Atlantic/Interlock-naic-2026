"""Focused deterministic Module 8 Explanation Agent tests."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.agents.assessment import DeterministicAssessmentAgent
from backend.app.agents.explanation import DeterministicExplanationAgent
from backend.app.main import app
from backend.app.schemas.agents import (
    AssessmentFinding,
    AssessmentRequest,
    AssessmentResult,
    DependencyRecord,
    EvidenceBundle,
    ExplanationRequest,
    ExplanationResult,
    HumanReviewRequest,
    ProjectContext,
)
from backend.app.services.rag.models import Domain


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "agents"


def _context(project_id: str = "explanation-test-project") -> ProjectContext:
    return ProjectContext(
        project_id=project_id,
        project_name="Synthetic Explanation Project",
        project_type="Data Centre",
        location={"address": "Synthetic site", "country": "Ireland"},
    )


def _request(
    result: AssessmentResult,
    bundle: EvidenceBundle | None = None,
) -> ExplanationRequest:
    return ExplanationRequest(
        project_context=result.project_context,
        assessment_result=result,
        evidence_bundle=bundle,
    )


def _run(result: AssessmentResult, bundle: EvidenceBundle | None = None) -> ExplanationResult:
    return DeterministicExplanationAgent().run(_request(result, bundle))


def _load_bundle(name: str) -> EvidenceBundle:
    payload = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return EvidenceBundle.model_validate(payload)


def test_assessment_result_produces_valid_serialisable_explanation() -> None:
    result = AssessmentResult(
        project_context=_context(),
        findings=[
            AssessmentFinding(
                finding_id="finding-unknown-grid",
                domain=Domain.GRID,
                status="UNKNOWN",
                material_unknowns=["connection information"],
                evidence_required_next=["current connection evidence"],
                human_review_required=True,
            )
        ],
        material_unknowns=["connection information"],
    )

    explanation = _run(result)

    assert ExplanationResult.model_validate_json(explanation.model_dump_json()) == explanation
    assert explanation.executive_summary
    assert explanation.key_findings
    assert "decision" not in explanation.model_dump()
    assert "score" not in explanation.model_dump()


def test_unknown_and_conditional_stay_explicitly_uncertain() -> None:
    result = AssessmentResult(
        project_context=_context(),
        findings=[
            AssessmentFinding(
                finding_id="finding-unknown",
                domain=Domain.PLANNING,
                status="UNKNOWN",
                material_unknowns=["site-specific zoning evidence"],
            ),
            AssessmentFinding(
                finding_id="finding-conditional",
                domain=Domain.WATER,
                status="CONDITIONAL",
                decision_impact="A feasibility response does not establish a secured connection.",
            ),
        ],
        material_unknowns=["site-specific zoning evidence"],
    )

    explanation = _run(result)

    assert any(item.startswith("UNKNOWN") for item in explanation.key_findings)
    assert any("not found sufficient evidence" in item for item in explanation.key_findings)
    assert any(item.startswith("CONDITIONAL") for item in explanation.conditional_issues)
    assert all("approved" not in item.casefold() for item in explanation.key_findings)


def test_explanation_cannot_invent_a_hard_constraint() -> None:
    result = AssessmentResult(
        project_context=_context(),
        findings=[
            AssessmentFinding(
                finding_id="finding-clear",
                domain=Domain.ENERGY,
                status="CLEAR",
                decision_impact="No explicit hard constraint was identified in the supplied evidence.",
            )
        ],
    )

    explanation = _run(result)

    assert explanation.constraints == []
    assert not any(item.startswith("CONSTRAINED") for item in explanation.key_findings)


def test_dependencies_and_next_actions_preserve_evidence_ids() -> None:
    dependency = DependencyRecord(
        dependency_id="dependency-grid",
        project_id="explanation-test-project",
        from_domain=Domain.GRID,
        to_domain=Domain.ENERGY,
        description="Energy strategy depends on grid connection confirmation.",
        status="UNRESOLVED",
        evidence_ids=["ev-grid"],
        evidence_required_next=["current connection evidence"],
    )
    result = AssessmentResult(
        project_context=_context(),
        dependencies=[dependency],
        findings=[
            AssessmentFinding(
                finding_id="finding-grid",
                domain=Domain.GRID,
                status="CONDITIONAL",
                dependency_ids=[dependency.dependency_id],
                evidence_ids=["ev-grid"],
                evidence_required_next=["current connection evidence"],
            )
        ],
    )

    explanation = _run(result)

    assert "ev-grid" in explanation.dependencies[0]
    assert explanation.evidence_ids == ["ev-grid"]
    assert explanation.next_actions == ["current connection evidence"]


def test_human_review_role_is_preserved_and_duplicate_reviews_are_not_repeated() -> None:
    reviews = [
        HumanReviewRequest(
            review_id="review-grid-a",
            project_id="explanation-test-project",
            domain=Domain.GRID,
            reason="Confirm connection status.",
            recommended_role="GRID_ENGINEER",
            evidence_ids=["ev-grid"],
        ),
        HumanReviewRequest(
            review_id="review-grid-b",
            project_id="explanation-test-project",
            domain=Domain.GRID,
            reason="Confirm connection status.",
            recommended_role="GRID_ENGINEER",
            evidence_ids=["ev-grid-2"],
        ),
    ]
    result = AssessmentResult(project_context=_context(), human_reviews=reviews)

    explanation = _run(result)

    assert len(explanation.human_handoffs) == 1
    assert "GRID_ENGINEER" in explanation.human_handoffs[0]
    assert "ev-grid" in explanation.human_handoffs[0]


def test_source_types_citations_and_evidence_ids_remain_traceable() -> None:
    bundle = _load_bundle("evidence_bundle_example.json")
    result = AssessmentResult(
        project_context=bundle.project_context,
        findings=[
            AssessmentFinding(
                finding_id="finding-policy",
                domain=Domain.PLANNING,
                status="CONDITIONAL",
                evidence_ids=["ev-synthetic-policy-001"],
                decision_impact="Policy evidence remains subject to human interpretation.",
            )
        ],
    )

    explanation = _run(result, bundle)

    assert explanation.evidence_ids == ["ev-synthetic-policy-001"]
    assert any("AUTHORITATIVE POLICY" in item for item in explanation.known_facts)
    assert [item.document_id for item in explanation.source_citations] == ["synthetic-policy-doc-001"]
    assert "synthetic/policy.pdf" in explanation.source_citations[0].source_path


def test_benchmark_only_evidence_does_not_leak_into_explanation() -> None:
    bundle = _load_bundle("evidence_bundle_example.json")
    record = bundle.records[0].model_copy(
        update={
            "evidence_id": "ev-benchmark-only",
            "value": {"benchmark_only": True},
            "fact": "Benchmark-only evidence must not appear.",
            "finding": "Benchmark-only evidence must not appear.",
        }
    )
    bundle = bundle.model_copy(update={"records": [record]})
    result = AssessmentResult(
        project_context=bundle.project_context,
        findings=[
            AssessmentFinding(
                finding_id="finding-benchmark",
                domain=Domain.PLANNING,
                status="CONDITIONAL",
                evidence_ids=["ev-benchmark-only"],
                decision_impact="Benchmark-only item.",
            )
        ],
    )

    explanation = _run(result, bundle)

    assert "ev-benchmark-only" not in explanation.evidence_ids
    assert all("benchmark" not in item.casefold() for item in explanation.known_facts)
    assert not explanation.source_citations


def test_echelon_scope_mismatch_remains_visible() -> None:
    bundle = _load_bundle("echelon_scope_change_example.json")
    assessment = DeterministicAssessmentAgent().run(
        AssessmentRequest(project_context=bundle.project_context, evidence_bundle=bundle)
    )

    explanation = _run(assessment, bundle)

    assert explanation.contradictions
    assert any("scope" in item.casefold() or "conflicting" in item.casefold() for item in explanation.contradictions)
    assert any("ev-synthetic-grid-agreement-001" in item for item in explanation.contradictions)


def test_explanation_api_uses_shared_request_and_has_no_decision_or_score() -> None:
    result = AssessmentResult(
        project_context=_context(),
        findings=[
            AssessmentFinding(
                finding_id="finding-api",
                domain=Domain.GRID,
                status="UNKNOWN",
                material_unknowns=["connection information"],
            )
        ],
    )

    response = TestClient(app).post(
        "/agents/explanation",
        json=ExplanationRequest(
            project_context=result.project_context,
            assessment_result=result,
        ).model_dump(mode="json"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert ExplanationResult.model_validate(payload).key_findings
    assert "decision" not in payload
    assert "score" not in payload
    serialized = json.dumps(payload).upper()
    assert all(term not in serialized for term in ("ADVANCE", "HOLD", "RECONFIGURE", "STOP"))
