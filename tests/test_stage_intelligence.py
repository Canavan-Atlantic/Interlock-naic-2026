from backend.app.schemas.agents import AssessmentFinding, AssessmentResult, EvidenceBundle, ProjectContext
from backend.app.services.stage_intelligence import build_stage_intelligence
from backend.app.services.stage_view import build_stage_assessment_view


def _context(stage: str, **values: object) -> ProjectContext:
    return ProjectContext(
        project_id="stage-test",
        project_name="Stage test",
        project_stage=stage,
        location={"address": "Blanchardstown, Dublin 15", "latitude": 53.3879, "longitude": -6.375},
        **values,
    )


def test_site_discovery_does_not_require_later_stage_mic_or_energy() -> None:
    stage = build_stage_intelligence(_context("Site Discovery"))
    assert "Confirmed MIC or project-specific grid pathway" in stage.not_required_at_stage
    assert not any(item.requirement_id == "grid-readiness" for item in stage.required_to_progress)


def test_early_feasibility_requires_grid_and_energy_inputs() -> None:
    stage = build_stage_intelligence(_context("Early Feasibility", planned_power_mw=50))
    required = {item.requirement_id for item in stage.required_to_progress if item.status == "REQUIRED_TO_PROGRESS"}
    assert {"grid-readiness", "energy-strategy", "site-extent", "planning-position", "water-pathway"}.issubset(required)
    assert stage.missing_evidence_wording == "Required to progress"


def test_deliverability_is_stronger_and_requires_project_specific_pathway() -> None:
    stage = build_stage_intelligence(_context("Deliverability Validation", planned_power_mw=50, phasing="Phase 1"))
    required = {item.requirement_id for item in stage.required_to_progress}
    assert "grid-pathway" in required
    assert "energy-pathway" in required
    assert stage.missing_evidence_wording == "Delivery-critical evidence missing"
    assert stage.customer_question != build_stage_intelligence(_context("Site Discovery")).customer_question


def test_deliverability_inputs_are_not_delivery_evidence() -> None:
    stage = build_stage_intelligence(_context(
        "Deliverability Validation",
        planned_power_mw=50,
        requested_mic_mva=60,
        power_strategy="New Grid Connection",
        energy_strategy="On-site renewable and storage",
        phasing="Phase 1",
    ))
    required = {item.requirement_id for item in stage.required_to_progress if item.status == "REQUIRED_TO_PROGRESS"}
    assert {"grid-pathway", "energy-pathway", "planning-position", "water-pathway"}.issubset(required)
    assert stage.provided_inputs


def test_stage_layer_does_not_add_assessment_or_score_fields() -> None:
    result = build_stage_intelligence(_context("Early Feasibility"))
    payload = result.model_dump()
    assert "score" not in payload
    assert "decision" not in payload


def test_stage_assessment_view_is_relevant_and_reportable() -> None:
    context = _context("Site Discovery")
    assessment = AssessmentResult(
        project_context=context,
        findings=[
            AssessmentFinding(finding_id="site-planning", domain="PLANNING", status="UNKNOWN"),
            AssessmentFinding(finding_id="later-energy", domain="ENERGY", status="UNKNOWN"),
        ],
    )
    intelligence = build_stage_intelligence(context)
    view = build_stage_assessment_view(context, EvidenceBundle(project_context=context), assessment, intelligence)

    assert view.requirement_heading == "Further Investigation"
    assert [item["finding_id"] for item in view.relevant_findings] == ["site-planning"]
    assert view.relevant_evidence_count == 0
    assert view.total_evidence_count == 0
    assert "score" not in view.model_dump()
    assert "decision" not in view.model_dump()
