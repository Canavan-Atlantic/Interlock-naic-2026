"""Focused deterministic Module 7 Assessment Agent tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from backend.app.agents.assessment import DeterministicAssessmentAgent
from backend.app.main import app
from backend.app.schemas.agents import (
    AgentEvidenceState,
    AssessmentRequest,
    AssessmentResult,
    DependencyRecord,
    EvidenceBundle,
    EvidenceCreatedBy,
    EvidenceRecord,
    EvidenceSourceTrust,
    HumanReviewRequest,
    HumanReviewRole,
    ProjectContext,
)
from backend.app.schemas.agents.common import HumanReviewSeverity
from backend.app.schemas.evidence import EvidenceCategory, EvidenceConfidence, EvidenceReviewStatus, EvidenceSourceType
from backend.app.services.rag.models import DocumentStatus, Domain, Jurisdiction, SourceClass


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "agents"


def _context(**overrides: Any) -> ProjectContext:
    values: dict[str, Any] = {
        "project_id": "assessment-test-project",
        "project_name": "Synthetic Assessment Project",
        "project_type": "Data Centre",
        "location": {"country": "Ireland", "jurisdiction": Jurisdiction.IRELAND},
        "project_lifecycle_status": "PRE_PLANNING",
    }
    values.update(overrides)
    return ProjectContext.model_validate(values)


def _record(
    evidence_id: str,
    domain: Domain,
    field_name: str,
    fact: str,
    *,
    value: Any = "supplied",
    state: AgentEvidenceState = AgentEvidenceState.PROVIDED,
    created_by: EvidenceCreatedBy = EvidenceCreatedBy.DEVELOPER_INPUT,
    source_trust: EvidenceSourceTrust = EvidenceSourceTrust.UNVERIFIED_DEVELOPER_INPUT,
    source_class: SourceClass | None = None,
    document_status: DocumentStatus | None = None,
    deterministic: bool = False,
    missing_evidence: list[str] | None = None,
    human_review_required: bool = False,
) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=evidence_id,
        project_id="assessment-test-project",
        domain=domain,
        category=EvidenceCategory.SITE,
        field_name=field_name,
        fact=fact,
        finding=fact,
        value=value,
        source_type=(
            EvidenceSourceType.DETERMINISTIC_CALCULATION
            if deterministic
            else EvidenceSourceType.POLICY_DOCUMENT
            if created_by == EvidenceCreatedBy.RAG_RETRIEVAL
            else EvidenceSourceType.CUSTOMER_DOCUMENT
        ),
        source_name="Synthetic source",
        source_reference=evidence_id,
        evidence_state=state,
        confidence=EvidenceConfidence.HIGH if deterministic else EvidenceConfidence.MEDIUM,
        review_status=EvidenceReviewStatus.UNREVIEWED,
        checked_at="2026-01-01T00:00:00Z",
        source_class=source_class,
        authority_class=source_class,
        document_status=document_status,
        jurisdiction=Jurisdiction.IRELAND,
        created_by=created_by,
        deterministic=deterministic,
        source_trust=source_trust,
        missing_evidence=missing_evidence or [],
        human_review_required=human_review_required,
    )


def _bundle(records: list[EvidenceRecord], **overrides: Any) -> EvidenceBundle:
    values: dict[str, Any] = {
        "project_context": _context(),
        "records": records,
    }
    values.update(overrides)
    return EvidenceBundle.model_validate(values)


def _assess(bundle: EvidenceBundle) -> AssessmentResult:
    return DeterministicAssessmentAgent().run(
        AssessmentRequest(project_context=bundle.project_context, evidence_bundle=bundle)
    )


def _finding(result: AssessmentResult, domain: Domain, status: str | None = None):
    matches = [item for item in result.findings if item.domain == domain]
    if status is not None:
        matches = [item for item in matches if item.status == status]
    assert matches
    return matches[0]


def test_evidence_bundle_produces_valid_serialisable_assessment_result() -> None:
    result = _assess(_bundle([_record("ev-general", Domain.GENERAL, "project_stage", "Stage is unknown", state=AgentEvidenceState.UNKNOWN)]))

    assert AssessmentResult.model_validate_json(result.model_dump_json()) == result
    assert "decision" not in result.model_dump()
    assert "score" not in result.model_dump()
    assert result.project_context.project_id == "assessment-test-project"


def test_missing_mic_remains_unknown() -> None:
    result = _assess(_bundle([_record("ev-mic", Domain.ENERGY, "requested_mic_mva", "MIC is not provided", value=None, state=AgentEvidenceState.NOT_PROVIDED, missing_evidence=["MIC not provided"])]))

    finding = _finding(result, Domain.ENERGY, "UNKNOWN")
    assert finding.material_unknowns
    assert finding.evidence_ids == ["ev-mic"]
    assert "MIC not provided" in result.material_unknowns
    assert any(review.recommended_role == HumanReviewRole.GRID_ENGINEER for review in result.human_reviews)


def test_unknown_zoning_remains_unknown() -> None:
    result = _assess(_bundle([_record("ev-zoning", Domain.PLANNING, "zoning.status", "Zoning is unknown", value=None, state=AgentEvidenceState.UNKNOWN, missing_evidence=["usable site-specific zoning evidence"])]))

    assert _finding(result, Domain.PLANNING, "UNKNOWN").evidence_ids == ["ev-zoning"]
    assert any(review.recommended_role == HumanReviewRole.PLANNING_CONSULTANT for review in result.human_reviews)


def test_harmless_general_unknown_does_not_create_human_review() -> None:
    result = _assess(_bundle([_record("ev-note", Domain.GENERAL, "project_note", "Optional note is unknown.", value=None, state=AgentEvidenceState.UNKNOWN)]))

    assert _finding(result, Domain.GENERAL, "UNKNOWN")
    assert not result.human_reviews


def test_water_feasibility_does_not_equal_secured_connection() -> None:
    result = _assess(_bundle([_record("ev-water", Domain.WATER, "water.connection_feasibility", "Uisce Eireann feasibility correspondence is available.", value="FEASIBILITY_LETTER")]))

    finding = _finding(result, Domain.WATER, "CONDITIONAL")
    assert "does not establish a secured" in (finding.decision_impact or "")
    assert "ev-water" in finding.evidence_ids
    assert result.human_reviews


def test_proposed_grid_infrastructure_does_not_equal_energised() -> None:
    result = _assess(_bundle([_record("ev-substation", Domain.GRID, "grid.substation_status", "Proposed substation is described in project material.", value="PROPOSED")]))

    finding = _finding(result, Domain.GRID, "CONDITIONAL")
    assert "commissioned or operational" in (finding.decision_impact or "")
    assert not result.constraints


def test_explicit_current_authority_constraint_is_not_averaged_away() -> None:
    result = _assess(_bundle([_record(
        "ev-prohibited",
        Domain.PLANNING,
        "planning.policy_constraint",
        "The current policy states that development is not permitted in this zone.",
        created_by=EvidenceCreatedBy.RAG_RETRIEVAL,
        source_trust=EvidenceSourceTrust.AUTHORITATIVE_POLICY,
        source_class=SourceClass.PRIMARY,
        document_status=DocumentStatus.CURRENT,
    )]))

    finding = _finding(result, Domain.PLANNING, "CONSTRAINED")
    assert finding.evidence_ids == ["ev-prohibited"]
    assert result.constraints


def test_planned_renewable_asset_does_not_equal_operational_asset() -> None:
    result = _assess(_bundle([_record("ev-renewable", Domain.ENERGY, "renewable_asset_status", "Renewable asset is planned but not commissioned.", value="PLANNED_NOT_COMMISSIONED")]))

    finding = _finding(result, Domain.ENERGY, "CONDITIONAL")
    assert "commissioned or operational" in (finding.decision_impact or "")


def test_contextual_grid_asset_does_not_become_confirmed_capacity() -> None:
    result = _assess(_bundle([_record("ev-nearest", Domain.GRID, "grid.nearest_connection", "Nearest substation is a contextual asset.", value={"distance_m": 1000}, created_by=EvidenceCreatedBy.DETERMINISTIC_GIS, source_trust=EvidenceSourceTrust.DETERMINISTIC_SOURCE, deterministic=True)]))

    finding = _finding(result, Domain.GRID, "CONDITIONAL")
    assert "do not establish available capacity" in (finding.decision_impact or "")
    assert any(review.severity == HumanReviewSeverity.HIGH_CONSEQUENCE for review in result.human_reviews)


def test_no_spatial_intersection_does_not_become_no_environmental_risk() -> None:
    result = _assess(_bundle([_record("ev-sac", Domain.BIODIVERSITY, "biodiversity.sac_intersection", "No intersection with tested SAC layer.", value={"intersects": False}, created_by=EvidenceCreatedBy.DETERMINISTIC_GIS, source_trust=EvidenceSourceTrust.DETERMINISTIC_SOURCE, deterministic=True)]))

    finding = _finding(result, Domain.BIODIVERSITY, "CONDITIONAL")
    assert "does not establish absence" in (finding.decision_impact or "")
    assert not any("no environmental risk" in item.casefold() for item in result.constraints)


def test_project_document_policy_interpretation_cannot_override_authority() -> None:
    records = [
        _record("ev-project-policy", Domain.GRID, "project.policy_interpretation", "Project policy interpretation says connection is feasible.", created_by=EvidenceCreatedBy.PROJECT_DOCUMENT, source_trust=EvidenceSourceTrust.UNTRUSTED_PROJECT_DOCUMENT),
        _record("ev-authority", Domain.GRID, "policy.grid_requirement", "Current authoritative policy requirement.", created_by=EvidenceCreatedBy.RAG_RETRIEVAL, source_trust=EvidenceSourceTrust.AUTHORITATIVE_POLICY, source_class=SourceClass.PRIMARY, document_status=DocumentStatus.CURRENT),
    ]
    result = _assess(_bundle(records))

    assert any("non-authoritative" in (item.decision_impact or "") for item in result.findings)
    assert any("ev-project-policy" in item.evidence_ids and "ev-authority" in item.evidence_ids for item in result.findings)


def test_material_contradiction_remains_visible_and_requires_review() -> None:
    records = [
        _record("ev-scope-a", Domain.GENERAL, "project_scope", "Original scope is 100 MW.", value="100 MW"),
        _record("ev-scope-b", Domain.GENERAL, "project_scope", "Revised scope is 200 MW.", value="200 MW"),
    ]
    contradiction = {
        "contradiction_id": "contradiction-scope",
        "project_id": "assessment-test-project",
        "domain": Domain.GENERAL,
        "evidence_ids": ["ev-scope-a", "ev-scope-b"],
        "type": "PROJECT_SCOPE_MISMATCH",
        "description": "Distinct project scopes require confirmation.",
        "requires_human_review": True,
    }
    result = _assess(_bundle(records, potential_contradictions=[contradiction]))

    assert any("conflicting evidence" in (item.decision_impact or "") for item in result.findings)
    assert any(set(review.evidence_ids) == {"ev-scope-a", "ev-scope-b"} for review in result.human_reviews)


def test_dependencies_preserve_evidence_ids() -> None:
    dependency = DependencyRecord(
        dependency_id="dependency-water",
        project_id="assessment-test-project",
        from_domain=Domain.WATER,
        to_domain=Domain.WATER,
        description="Water readiness depends on a connection agreement.",
        status="UNRESOLVED",
        evidence_ids=["ev-water"],
        evidence_required_next=["water connection agreement"],
        human_review_required=True,
    )
    result = _assess(_bundle([], dependencies=[dependency]))

    assert result.dependencies[0].evidence_ids == ["ev-water"]
    assert _finding(result, Domain.WATER, "CONDITIONAL").dependency_ids == ["dependency-water"]


def test_related_human_reviews_are_aggregated_without_losing_evidence_ids() -> None:
    records = [
        _record("ev-a", Domain.GRID, "grid.status", "Grid status requires review.", human_review_required=True),
        _record("ev-b", Domain.GRID, "grid.status_detail", "Grid status requires review.", human_review_required=True),
    ]
    review_a = HumanReviewRequest(
        review_id="review-grid-a",
        project_id="assessment-test-project",
        domain=Domain.GRID,
        reason="Confirm grid status.",
        severity=HumanReviewSeverity.MATERIAL,
        recommended_role=HumanReviewRole.GRID_ENGINEER,
        evidence_ids=["ev-a"],
    )
    review_b = review_a.model_copy(update={"review_id": "review-grid-b", "evidence_ids": ["ev-b"]})
    result = _assess(_bundle(records, human_review_requests=[review_a, review_b]))

    matching = [review for review in result.human_reviews if review.domain == Domain.GRID and "grid status" in review.reason.casefold()]
    assert len(matching) == 1
    assert matching[0].evidence_ids == ["ev-a", "ev-b"]


def test_identical_upstream_and_assessment_issue_is_one_review() -> None:
    record = _record("ev-agreement", Domain.GRID, "grid_connection_agreement", "A connection agreement is recorded.")
    upstream = HumanReviewRequest(
        review_id="review-upstream-grid",
        project_id="assessment-test-project",
        domain=Domain.GRID,
        reason="A connection agreement or feasibility statement does not establish energisation or a secured MIC.",
        severity=HumanReviewSeverity.MATERIAL,
        recommended_role=HumanReviewRole.GRID_ENGINEER,
        evidence_ids=["ev-upstream"],
    )
    result = _assess(_bundle([record], human_review_requests=[upstream]))

    matching = [review for review in result.human_reviews if review.recommended_role == HumanReviewRole.GRID_ENGINEER and "energisation" in review.reason]
    assert len(matching) == 1
    assert matching[0].review_id == "review-upstream-grid"
    assert matching[0].evidence_ids == ["ev-upstream", "ev-agreement"]


def test_unrelated_same_domain_issues_remain_separate() -> None:
    reviews = [
        HumanReviewRequest(
            review_id="review-planning-zoning",
            project_id="assessment-test-project",
            domain=Domain.PLANNING,
            reason="Confirm zoning evidence.",
            recommended_role=HumanReviewRole.PLANNING_CONSULTANT,
            evidence_ids=["ev-zoning"],
        ),
        HumanReviewRequest(
            review_id="review-planning-scope",
            project_id="assessment-test-project",
            domain=Domain.PLANNING,
            reason="Confirm the conflicting project scope.",
            severity=HumanReviewSeverity.HIGH_CONSEQUENCE,
            recommended_role=HumanReviewRole.PLANNING_CONSULTANT,
            evidence_ids=["ev-scope"],
        ),
    ]
    result = _assess(_bundle([], human_review_requests=reviews))

    assert {review.review_id for review in result.human_reviews} == {"review-planning-zoning", "review-planning-scope"}


def test_deterministic_gis_provenance_is_not_rewritten() -> None:
    result = _assess(_bundle([_record("ev-gis", Domain.ENVIRONMENT, "flood.intersection", "No intersection with tested flood layer.", value={"intersects": False}, created_by=EvidenceCreatedBy.DETERMINISTIC_GIS, source_trust=EvidenceSourceTrust.DETERMINISTIC_SOURCE, deterministic=True)]))

    assert "ev-gis" in result.findings[0].evidence_ids
    assert not result.constraints


def test_echelon_scope_fixture_keeps_scope_mismatch_and_unknowns() -> None:
    payload = json.loads((FIXTURES / "echelon_scope_change_example.json").read_text(encoding="utf-8"))
    bundle = _bundle(
        [EvidenceRecord.model_validate(record) for record in payload["records"]],
        project_context=ProjectContext.model_validate(payload["project_context"]),
        missing_evidence=payload["missing_evidence"],
        retrieval_gaps=payload["retrieval_gaps"],
        potential_contradictions=payload["potential_contradictions"],
        human_review_requests=payload["human_review_requests"],
    )
    result = _assess(bundle)

    assert any(item.domain == Domain.GENERAL for item in result.findings)
    assert result.material_unknowns
    assert result.human_reviews


def test_assessment_api_uses_shared_request_and_result_contract() -> None:
    bundle = _bundle([_record("ev-api", Domain.GRID, "requested_mic_mva", "MIC is not provided.", value=None, state=AgentEvidenceState.NOT_PROVIDED, missing_evidence=["MIC not provided"])])
    response = TestClient(app).post(
        "/agents/assessment",
        json=AssessmentRequest(project_context=bundle.project_context, evidence_bundle=bundle).model_dump(mode="json"),
    )

    assert response.status_code == 200
    parsed = AssessmentResult.model_validate(response.json())
    assert parsed.findings
    assert "decision" not in response.json()
