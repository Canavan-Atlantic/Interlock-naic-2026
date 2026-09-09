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
    assert "review-grid-a" in explanation.human_handoffs[0]
    assert "review-grid-b" in explanation.human_handoffs[0]


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
    assert all("ev-benchmark-only" not in item.evidence_ids for item in explanation.material_unknown_themes)
    assert all("ev-benchmark-only" not in item.evidence_ids for item in explanation.next_action_plan)


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


def test_semantically_duplicate_unknowns_form_one_theme_and_preserve_ids() -> None:
    result = AssessmentResult(
        project_context=_context(),
        findings=[
            AssessmentFinding(
                finding_id="finding-mic",
                domain=Domain.GRID,
                status="UNKNOWN",
                evidence_ids=["ev-mic"],
                material_unknowns=["MIC is not provided"],
                evidence_required_next=["Confirm MIC"],
            ),
            AssessmentFinding(
                finding_id="finding-connection",
                domain=Domain.GRID,
                status="UNKNOWN",
                evidence_ids=["ev-connection"],
                material_unknowns=["Confirmed grid connection status is not provided"],
                evidence_required_next=["Confirm connection status"],
            ),
        ],
        material_unknowns=[
            "MIC is not provided",
            "Confirmed grid connection status is not provided",
        ],
    )

    explanation = _run(result)

    grid_themes = [item for item in explanation.material_unknown_themes if item.theme_id.endswith("grid-connection-readiness")]
    assert len(grid_themes) == 1
    assert set(grid_themes[0].underlying_unknowns) == {
        "MIC is not provided",
        "Confirmed grid connection status is not provided",
    }
    assert set(grid_themes[0].finding_ids) == {"finding-mic", "finding-connection"}
    assert explanation.material_unknowns == [
        "MIC is not provided",
        "Confirmed grid connection status is not provided",
    ]


def test_unrelated_unknowns_remain_separate_themes() -> None:
    result = AssessmentResult(
        project_context=_context(),
        findings=[
            AssessmentFinding(
                finding_id="finding-zoning",
                domain=Domain.PLANNING,
                status="UNKNOWN",
                material_unknowns=["Authoritative site-specific zoning evidence is missing"],
            ),
            AssessmentFinding(
                finding_id="finding-water",
                domain=Domain.WATER,
                status="UNKNOWN",
                material_unknowns=["Site-specific wastewater capacity is not confirmed"],
            ),
        ],
    )

    explanation = _run(result)

    titles = {item.title for item in explanation.material_unknown_themes}
    assert "SITE-SPECIFIC PLANNING / ZONING EVIDENCE" in titles
    assert "WATER / WASTEWATER CONNECTION READINESS" in titles
    assert len(explanation.material_unknown_themes) == 2


def test_duplicate_next_actions_consolidate_and_keep_supporting_ids() -> None:
    result = AssessmentResult(
        project_context=_context(),
        findings=[
            AssessmentFinding(
                finding_id="finding-mic-action",
                domain=Domain.GRID,
                status="UNKNOWN",
                evidence_ids=["ev-mic"],
                evidence_required_next=["Confirm MIC"],
            ),
            AssessmentFinding(
                finding_id="finding-status-action",
                domain=Domain.GRID,
                status="UNKNOWN",
                evidence_ids=["ev-status"],
                evidence_required_next=["Confirm grid connection status"],
            ),
            AssessmentFinding(
                finding_id="finding-energisation-action",
                domain=Domain.GRID,
                status="UNKNOWN",
                evidence_ids=["ev-energisation"],
                evidence_required_next=["Confirm energisation evidence"],
            ),
        ],
    )

    explanation = _run(result)

    grid_actions = [item for item in explanation.next_action_plan if item.action_id == "action-grid-connection-readiness"]
    assert len(grid_actions) == 1
    assert grid_actions[0].title.startswith("Confirm project-specific grid connection readiness")
    assert set(grid_actions[0].source_actions) == {
        "Confirm MIC",
        "Confirm grid connection status",
        "Confirm energisation evidence",
    }
    assert set(grid_actions[0].finding_ids) == {
        "finding-mic-action",
        "finding-status-action",
        "finding-energisation-action",
    }
    assert set(grid_actions[0].evidence_ids) == {"ev-mic", "ev-status", "ev-energisation"}


def test_unrelated_next_actions_remain_separate_and_non_prescriptive() -> None:
    result = AssessmentResult(
        project_context=_context(),
        findings=[
            AssessmentFinding(
                finding_id="finding-grid-action",
                domain=Domain.GRID,
                status="UNKNOWN",
                evidence_required_next=["Obtain project-specific connection status"],
            ),
            AssessmentFinding(
                finding_id="finding-planning-action",
                domain=Domain.PLANNING,
                status="UNKNOWN",
                evidence_required_next=["Confirm site-specific zoning with the relevant planning authority"],
            ),
        ],
    )

    explanation = _run(result)

    assert len(explanation.next_action_plan) == 2
    titles = " ".join(item.title.casefold() for item in explanation.next_action_plan)
    assert "build" not in titles
    assert "submit" not in titles


def test_customer_citations_are_bounded_while_full_provenance_remains() -> None:
    bundle = _load_bundle("evidence_bundle_example.json")
    result = AssessmentResult(
        project_context=bundle.project_context,
        findings=[
            AssessmentFinding(
                finding_id="finding-cited-policy",
                domain=Domain.PLANNING,
                status="CONDITIONAL",
                evidence_ids=["ev-synthetic-policy-001"],
                evidence_required_next=["Confirm site-specific zoning evidence"],
                decision_impact="Policy evidence remains subject to human interpretation.",
            )
        ],
    )

    explanation = _run(result, bundle)

    assert explanation.source_citations
    assert explanation.customer_facing_citations
    assert len(explanation.customer_facing_citations) <= len(explanation.source_citations)
    assert explanation.evidence_ids == ["ev-synthetic-policy-001"]
    assert explanation.next_action_plan[0].evidence_ids == ["ev-synthetic-policy-001"]
    assert explanation.model_dump_json()


def test_old_explanation_request_and_result_payloads_remain_compatible() -> None:
    legacy_result_payload = json.loads(
        (FIXTURES / "explanation_result_example.json").read_text(encoding="utf-8")
    )
    legacy_result = ExplanationResult.model_validate(legacy_result_payload)
    context = ProjectContext.model_validate(
        json.loads((FIXTURES / "project_context_blanchardstown.json").read_text(encoding="utf-8"))
    )
    legacy_request = ExplanationRequest(
        project_context=context,
        assessment_result=AssessmentResult(project_context=context),
    )

    assert legacy_result.executive_summary
    assert legacy_result.material_unknown_themes == []
    assert legacy_result.next_action_plan == []
    assert legacy_result.customer_facing_citations == []
    assert ExplanationRequest.model_validate(legacy_request.model_dump(mode="json")) == legacy_request


def test_echelon_status_distinctions_and_unknown_language_are_preserved() -> None:
    result = AssessmentResult(
        project_context=_context(),
        findings=[
            AssessmentFinding(
                finding_id="finding-planning-scope",
                domain=Domain.PLANNING,
                status="CONDITIONAL",
                decision_impact="Planning approval does not establish the current project scope.",
            ),
            AssessmentFinding(
                finding_id="finding-grid-energisation",
                domain=Domain.GRID,
                status="CONDITIONAL",
                decision_impact="A grid connection agreement does not establish energisation.",
            ),
            AssessmentFinding(
                finding_id="finding-launch-operation",
                domain=Domain.GENERAL,
                status="CONDITIONAL",
                decision_impact="A public launch does not establish operational status.",
            ),
            AssessmentFinding(
                finding_id="finding-renewable-commissioning",
                domain=Domain.ENERGY,
                status="CONDITIONAL",
                decision_impact="A planned renewable asset is not evidence of commissioning.",
            ),
            AssessmentFinding(
                finding_id="finding-unknown",
                domain=Domain.WATER,
                status="UNKNOWN",
                material_unknowns=["Site-specific water capacity is not confirmed"],
            ),
        ],
    )

    explanation = _run(result)
    rendered = " ".join(explanation.key_findings).casefold()

    assert "planning approval does not establish" in rendered
    assert "connection agreement does not establish energisation" in rendered
    assert "public launch does not establish operational" in rendered
    assert "planned renewable asset is not evidence of commissioning" in rendered
    assert "not found sufficient evidence to confirm" in rendered
    assert "not viable" not in rendered
    assert "failed" not in rendered
