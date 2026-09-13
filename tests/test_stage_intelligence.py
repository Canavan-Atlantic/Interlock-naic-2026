from backend.app.schemas.agents import (
    AssessmentFinding,
    AssessmentResult,
    EvidenceBundle,
    ExplanationAction,
    ExplanationResult,
    HumanReviewRequest,
    ProjectContext,
)
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
    for item in stage.required_to_progress:
        if item.status == "REQUIRED_TO_PROGRESS":
            assert item.why_required
            assert item.next_step
            assert item.owner


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


def test_stage_view_counts_explicit_constraints_and_preserves_finding_ids() -> None:
    context = _context("Early Feasibility")
    assessment = AssessmentResult(
        project_context=context,
        findings=[
            AssessmentFinding(finding_id="conditional", domain="GRID", status="CONDITIONAL"),
            AssessmentFinding(finding_id="hard", domain="PLANNING", status="CONSTRAINED"),
            AssessmentFinding(finding_id="unknown", domain="WATER", status="UNKNOWN"),
        ],
    )
    view = build_stage_assessment_view(
        context,
        EvidenceBundle(project_context=context),
        assessment,
        build_stage_intelligence(context),
    )

    assert view.counts["constraint_count"] == 1
    assert view.counts["conditional_or_constrained_finding_count"] == 2
    assert {item["finding_ids"][0] for item in view.domain_states} == {"conditional", "hard", "unknown"}


def test_site_discovery_does_not_surface_later_stage_actions_as_immediate_requirements() -> None:
    context = _context("Site Discovery")
    assessment = AssessmentResult(
        project_context=context,
        findings=[
            AssessmentFinding(finding_id="site-grid", domain="GRID", status="UNKNOWN"),
            AssessmentFinding(finding_id="site-planning", domain="PLANNING", status="UNKNOWN"),
        ],
    )
    explanation = ExplanationResult(
        next_action_plan=[
            ExplanationAction(
                action_id="grid-mic",
                title="Confirm MIC and energy strategy",
                rationale="This action addresses the assessment evidence requirements: project-specific grid evidence.",
                finding_ids=["site-grid"],
            ),
            ExplanationAction(
                action_id="water",
                title="Confirm water capacity",
                rationale="This action addresses the assessment evidence requirements: water capacity.",
                finding_ids=["later-water"],
            ),
            ExplanationAction(
                action_id="planning",
                title="Review planning position",
                rationale="This action addresses the assessment evidence requirements: site planning evidence.",
                finding_ids=["site-planning"],
            ),
        ]
    )
    view = build_stage_assessment_view(
        context,
        EvidenceBundle(project_context=context),
        assessment,
        build_stage_intelligence(context),
        explanation,
    )

    action_text = " ".join(item["title"] + " " + item["why_this_action"] for item in view.next_actions)
    assert "water capacity" not in action_text.casefold()
    assert "mic and energy strategy" not in action_text.casefold()
    assert any(item["title"] == "Review nearby grid infrastructure context" for item in view.next_actions)
    grid = next(item for item in view.relevant_findings if item["finding_id"] == "site-grid")
    assert grid["display_status"] == "SCREENING_CONTEXT"
    assert "later-stage question" in grid["headline"]
    assert "site screening" in grid["why_it_matters"]


def test_site_discovery_does_not_route_later_stage_grid_review() -> None:
    context = _context("Site Discovery")
    late_review = HumanReviewRequest(
        review_id="grid-mic-review",
        project_id=context.project_id,
        domain="GRID",
        reason="MIC not provided for the project connection pathway.",
        recommended_role="GRID_ENGINEER",
    )
    assessment = AssessmentResult(project_context=context, human_reviews=[late_review])
    view = build_stage_assessment_view(
        context,
        EvidenceBundle(project_context=context),
        assessment,
        build_stage_intelligence(context),
    )

    assert view.professional_reviews == []


def test_stage_view_deduplicates_professional_reviews_and_keeps_action_reason_distinct() -> None:
    context = _context("Deliverability Validation")
    review = HumanReviewRequest(
        review_id="planning-review",
        project_id=context.project_id,
        domain="PLANNING",
        reason="Confirm the site-specific planning position.",
        recommended_role="PLANNING_CONSULTANT",
        evidence_ids=["planning-evidence"],
    )
    assessment = AssessmentResult(
        project_context=context,
        findings=[AssessmentFinding(finding_id="planning", domain="PLANNING", status="UNKNOWN")],
        human_reviews=[review],
    )
    explanation = ExplanationResult(
        next_action_plan=[
            ExplanationAction(
                action_id="planning-action",
                title="Confirm planning position",
                rationale="This action addresses the assessment evidence requirements: obtain site-specific planning evidence.",
                finding_ids=["planning"],
            )
        ]
    )
    view = build_stage_assessment_view(
        context,
        EvidenceBundle(project_context=context, human_review_requests=[review]),
        assessment,
        build_stage_intelligence(context),
        explanation,
    )

    assert len(view.professional_reviews) == 1
    assert view.professional_reviews[0]["recommended_role"] == "PLANNING_CONSULTANT"
    assert view.next_actions[0]["reason"] != view.next_actions[0]["why_this_action"]


def test_stage_view_fallback_actions_name_the_missing_input() -> None:
    context = _context("Early Feasibility")
    view = build_stage_assessment_view(
        context,
        EvidenceBundle(project_context=context),
        AssessmentResult(project_context=context),
        build_stage_intelligence(context),
    )

    titles = {item["title"] for item in view.next_actions}
    assert "Provide the site area or confirmed site boundary." in titles
    assert "Confirm the current project definition, stage and phasing inputs." not in titles
