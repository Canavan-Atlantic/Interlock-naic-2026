"""Tests for the Module 6.0 shared agent contracts only."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.app.schemas.agents import (
    AGENT_CONTRACT_VERSION,
    AgentEvidenceState,
    AssessmentFinding,
    AssessmentRequest,
    AssessmentResult,
    DependencyRecord,
    EvidenceBundle,
    EvidenceCreatedBy,
    EvidenceRecord,
    ExplanationResult,
    ExplanationRequest,
    InterlockResult,
    ProjectContext,
    ProjectLifecycleStatus,
)
from backend.app.schemas.evidence import EvidenceCategory, EvidenceSourceType
from backend.app.schemas.project import ProjectInput
from backend.app.services.rag.models import (
    CitationReference,
    Domain,
    Jurisdiction,
    Workflow,
)


FIXTURES = Path(__file__).parent / "fixtures" / "agents"


def _record(**overrides: object) -> EvidenceRecord:
    values: dict[str, object] = {
        "evidence_id": "ev-test-001",
        "category": EvidenceCategory.SITE,
        "field_name": "test_field",
        "fact": "A synthetic test fact.",
        "value": "present",
        "source_type": EvidenceSourceType.CUSTOMER_DOCUMENT,
        "source_name": "Synthetic test source",
        "evidence_state": AgentEvidenceState.PROVIDED,
        "confidence": "MEDIUM",
        "review_status": "UNREVIEWED",
        "checked_at": "2026-01-01T00:00:00Z",
        "project_id": "project-test-001",
        "domain": Domain.GENERAL,
        "created_by": EvidenceCreatedBy.PROJECT_DOCUMENT,
    }
    values.update(overrides)
    return EvidenceRecord.model_validate(values)


def test_workflow_and_lifecycle_status_are_separate() -> None:
    context = ProjectContext(
        project_id="project-test-001",
        assessment_workflow=Workflow.SITE_FEASIBILITY,
        project_lifecycle_status=ProjectLifecycleStatus.PRE_PLANNING,
    )

    assert context.assessment_workflow == Workflow.SITE_FEASIBILITY
    assert context.project_lifecycle_status == ProjectLifecycleStatus.PRE_PLANNING
    assert context.assessment_workflow != context.project_lifecycle_status


def test_missing_numeric_values_remain_null_and_are_not_zero_defaults() -> None:
    context = ProjectContext(project_id="project-test-001")

    assert context.planned_power_mw is None
    assert context.requested_mic_mva is None
    assert context.location.latitude is None
    assert context.location.longitude is None
    assert context.site_boundary is None


def test_module_two_input_can_be_adapted_without_inventing_values() -> None:
    input_model = ProjectInput(
        project_name="Synthetic project",
        site_address="Synthetic address",
        project_stage="Unknown",
        power_strategy="Unknown",
    )

    context = ProjectContext.from_project_input(
        input_model,
        project_id="project-test-001",
        assessment_workflow=Workflow.SITE_DISCOVERY,
    )

    assert context.source_project_input == input_model
    assert context.project_name == "Synthetic project"
    assert context.location.address == "Synthetic address"
    assert context.planned_power_mw is None
    assert context.requested_mic_mva is None


def test_provenance_serialises_gis_and_page_aware_rag_citation() -> None:
    record = _record(
        evidence_id="ev-rag-001",
        source_type=EvidenceSourceType.POLICY_DOCUMENT,
        source_document_id="doc-test-001",
        source_class="PRIMARY",
        document_status="CURRENT",
        jurisdiction=Jurisdiction.IRELAND,
        created_by=EvidenceCreatedBy.RAG_RETRIEVAL,
        citation=CitationReference(
            document_id="doc-test-001",
            source_path="synthetic/policy.pdf",
            page_start=12,
            page_end=13,
            locator="page=12-13",
        ),
    )
    payload = record.model_dump(mode="json")

    assert payload["created_by"] == "RAG_RETRIEVAL"
    assert payload["citation"]["page_start"] == 12
    assert payload["citation"]["page_end"] == 13
    assert payload["source_document_id"] == "doc-test-001"


def test_ai_evidence_cannot_masquerade_as_deterministic() -> None:
    with pytest.raises(ValidationError, match="cannot masquerade"):
        _record(
            created_by=EvidenceCreatedBy.AI_EXTRACTION,
            source_type=EvidenceSourceType.DETERMINISTIC_CALCULATION,
            deterministic=True,
        )


def test_evidence_bundle_has_no_final_decision_field() -> None:
    assert "decision" not in EvidenceBundle.model_fields
    bundle = EvidenceBundle(project_context=ProjectContext(project_id="project-test-001"))
    assert "decision" not in bundle.model_dump()


def test_potential_contradiction_requires_human_review() -> None:
    payload = {
        "contradiction_id": "contradiction-test-001",
        "project_id": "project-test-001",
        "domain": Domain.PLANNING,
        "description": "Synthetic source mismatch.",
        "requires_human_review": True,
    }
    bundle = EvidenceBundle(
        project_context=ProjectContext(project_id="project-test-001"),
        potential_contradictions=[payload],
    )

    assert bundle.potential_contradictions[0].requires_human_review is True


def test_assessment_and_explanation_compose_without_investment_decision() -> None:
    context = ProjectContext(project_id="project-test-001")
    finding = AssessmentFinding(
        finding_id="finding-test-001",
        domain=Domain.GRID,
        evidence_ids=["ev-test-001"],
        material_unknowns=["synthetic missing input"],
    )
    assessment = AssessmentResult(
        project_context=context,
        findings=[finding],
        material_unknowns=["synthetic missing input"],
    )
    dependency = DependencyRecord(
        dependency_id="dependency-test-001",
        project_id="project-test-001",
        from_domain=Domain.GRID,
        to_domain=Domain.ENERGY,
        description="Synthetic dependency.",
        impact_description="Synthetic impact description.",
    )
    bundle = EvidenceBundle(
        project_context=context,
        records=[_record()],
        dependencies=[dependency],
    )
    assessment_request = AssessmentRequest(
        project_context=context,
        evidence_bundle=bundle,
    )
    explanation = ExplanationResult(
        executive_summary="Synthetic explanation.",
        material_unknowns=["synthetic missing input"],
    )
    explanation_request = ExplanationRequest(
        project_context=context,
        assessment_result=assessment,
    )
    result = InterlockResult(
        project_context=context,
        evidence_bundle=assessment_request.evidence_bundle,
        assessment_result=assessment,
        explanation_result=explanation,
        schema_version=AGENT_CONTRACT_VERSION,
    )

    assert result.schema_version == "1.0"
    assert "decision" not in result.model_dump()
    assert result.assessment_result.findings[0].status == "UNKNOWN"
    assert explanation_request.assessment_result == assessment
    assert result.evidence_bundle.dependencies[0].impact_description == "Synthetic impact description."
    round_tripped_dependency = DependencyRecord.model_validate_json(
        dependency.model_dump_json()
    )
    assert round_tripped_dependency == dependency
    assert result.assessment_result.findings[0].evidence_ids == ["ev-test-001"]


@pytest.mark.parametrize(
    ("filename", "model"),
    [
        ("project_context_blanchardstown.json", ProjectContext),
        ("evidence_bundle_example.json", EvidenceBundle),
        ("assessment_result_example.json", AssessmentResult),
        ("explanation_result_example.json", ExplanationResult),
        ("interlock_result_example.json", InterlockResult),
        ("echelon_scope_change_example.json", EvidenceBundle),
    ],
)
def test_synthetic_fixtures_validate_and_round_trip(filename: str, model: type) -> None:
    fixture_path = FIXTURES / filename
    payload = fixture_path.read_text(encoding="utf-8")
    parsed = model.model_validate_json(payload)
    reparsed = model.model_validate_json(parsed.model_dump_json())

    assert reparsed == parsed
    assert json.loads(parsed.model_dump_json())
