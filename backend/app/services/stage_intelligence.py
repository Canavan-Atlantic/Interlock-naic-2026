"""Deterministic stage requirements for the customer workflow.

This module is deliberately presentation/closure metadata.  It does not
change evidence, assessment states, scoring, or project decisions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from ..schemas.agents import (
    AgentEvidenceState,
    AssessmentResult,
    EvidenceBundle,
    EvidenceCreatedBy,
    EvidenceSourceTrust,
    ProjectContext,
    StageIntelligence,
    StageRequirement,
)


@dataclass(frozen=True)
class _StageProfile:
    purpose: str
    question: str
    evidence_expectations: tuple[str, ...]
    relevant_inputs: tuple[str, ...]
    not_required: tuple[str, ...]
    emphasis: tuple[str, ...]
    missing_wording: str
    progression: tuple[str, ...]


_PROFILES: dict[str, _StageProfile] = {
    "Site Discovery": _StageProfile(
        purpose="Screen whether the site merits deeper investigation.",
        question="Is this site worth investigating further?",
        evidence_expectations=(
            "Location and site context",
            "Planning and zoning context where available",
            "Flood, protected-site and biodiversity context",
            "Major environmental and grid-infrastructure context",
        ),
        relevant_inputs=("Site address or coordinates", "Development type"),
        not_required=(
            "Confirmed MIC or project-specific grid pathway",
            "Detailed energy strategy",
            "Final water or wastewater capacity confirmation",
        ),
        emphasis=("Early constraints", "Evidence gaps worth resolving", "Further-investigation triggers"),
        missing_wording="Further Investigation",
        progression=(
            "Confirm the site location and development type",
            "Review any early high-consequence spatial constraints",
            "Decide whether to commission deeper feasibility evidence",
        ),
    ),
    "Early Feasibility": _StageProfile(
        purpose="Identify what could stop or delay the project before deeper investment.",
        question="What could stop or delay this project, and what information is required before progressing?",
        evidence_expectations=(
            "Planned power, site boundary or area and project definition",
            "Grid/MIC, energy, planning/zoning and water evidence",
            "Environmental evidence and project documents where available",
        ),
        relevant_inputs=(
            "Planned power demand",
            "Site area or boundary",
            "Power strategy and energy strategy",
            "Phasing and project evidence",
        ),
        not_required=("Secured connection or final construction evidence",),
        emphasis=("Potential constraints", "Information needed before progression", "Specialist confirmation"),
        missing_wording="Required to progress",
        progression=(
            "Resolve material evidence gaps",
            "Confirm the grid, planning, water and environmental pathways",
            "Carry forward only items with an accountable closure path",
        ),
    ),
    "Deliverability Validation": _StageProfile(
        purpose="Check which delivery-critical requirements are evidenced and which remain unresolved.",
        question="Which delivery-critical requirements are confirmed, and what remains unresolved?",
        evidence_expectations=(
            "Confirmed project definition and phasing",
            "Project-specific grid/MIC pathway and connection status where available",
            "Planning position, water/wastewater pathway and environmental evidence",
            "Supporting technical or project documents",
        ),
        relevant_inputs=(
            "Planned power and requested MIC",
            "Power and energy strategy",
            "Site area or boundary",
            "Confirmed phasing and project documents",
        ),
        not_required=("None identified for this validation stage",),
        emphasis=("Delivery-critical evidence", "Unresolved confirmations", "Professional sign-off"),
        missing_wording="Delivery-critical evidence missing",
        progression=(
            "Obtain project-specific confirmations",
            "Close high-consequence professional reviews",
            "Do not treat deliverability as established while critical items remain unresolved",
        ),
    ),
}


def _stage(context: ProjectContext) -> str:
    return str(context.project_stage or "Unknown")


def _profile(context: ProjectContext) -> _StageProfile:
    return _PROFILES.get(_stage(context), _StageProfile(
        purpose="The assessment stage has not been selected.",
        question="What evidence is available for this project?",
        evidence_expectations=("Select a customer assessment stage",),
        relevant_inputs=("Project stage",),
        not_required=("No stage-specific requirement is applied",),
        emphasis=("Clarify the intended assessment stage",),
        missing_wording="Stage selection required",
        progression=("Select Site Discovery, Early Feasibility or Deliverability Validation",),
    ))


def _records(bundle: EvidenceBundle | None) -> list[Any]:
    return list(bundle.records) if bundle else []


def _enum(value: object) -> str:
    return str(getattr(value, "value", value) or "")


def _has_input(context: ProjectContext, key: str) -> bool:
    if key == "planned_power":
        return context.planned_power_mw is not None
    if key == "site_extent":
        return context.site_boundary is not None or context.developer_inputs.get("site_area_hectares") is not None
    if key == "power_strategy":
        return context.power_strategy not in (None, "Unknown")
    if key == "energy_strategy":
        return bool(context.energy_strategy)
    if key == "mic":
        return context.requested_mic_mva is not None
    if key == "phasing":
        return bool(context.phasing)
    if key == "project_documents":
        return bool(context.uploaded_document_refs)
    return False


def _has_verified_domain(records: list[Any], domains: set[str]) -> tuple[bool, list[str]]:
    ids: list[str] = []
    for record in records:
        if _enum(getattr(record, "domain", None)) not in domains:
            continue
        state = _enum(getattr(record, "evidence_state", None))
        creator = _enum(getattr(record, "created_by", None))
        if state not in {AgentEvidenceState.UNKNOWN.value, AgentEvidenceState.NOT_PROVIDED.value} and creator != EvidenceCreatedBy.DEVELOPER_INPUT.value:
            ids.append(str(getattr(record, "evidence_id", "")))
    return bool(ids), ids


def _has_site_specific_evidence(records: list[Any], domain: str) -> tuple[bool, list[str]]:
    """Return non-policy site evidence suitable for an early site position."""

    ids: list[str] = []
    for record in records:
        if _enum(getattr(record, "domain", None)) != domain:
            continue
        state = _enum(getattr(record, "evidence_state", None))
        creator = _enum(getattr(record, "created_by", None))
        field = str(getattr(record, "field_name", "")).casefold()
        if state in {AgentEvidenceState.UNKNOWN.value, AgentEvidenceState.NOT_PROVIDED.value}:
            continue
        if creator in {EvidenceCreatedBy.DEVELOPER_INPUT.value, EvidenceCreatedBy.RAG_RETRIEVAL.value}:
            continue
        if field == "zoning.state":
            continue
        ids.append(str(getattr(record, "evidence_id", "")))
    return bool(ids), ids


def _has_delivery_evidence(records: list[Any], domain: str) -> tuple[bool, list[str]]:
    """Find project-specific delivery confirmation, not contextual policy/GIS."""

    terms = {
        "GRID": ("connection offer", "connection agreement", "energisation", "energization", "mic allocation", "capacity confirmed"),
        "ENERGY": ("commissioned", "operational capacity", "energy delivery confirmation"),
        "PLANNING": ("planning permission", "planning decision", "planning approval", "site-specific planning position"),
        "WATER": ("water connection agreement", "wastewater connection", "water capacity confirmed", "utility capacity confirmation"),
    }.get(domain, ())
    ids: list[str] = []
    for record in records:
        if _enum(getattr(record, "domain", None)) != domain:
            continue
        state = _enum(getattr(record, "evidence_state", None))
        if state in {AgentEvidenceState.UNKNOWN.value, AgentEvidenceState.NOT_PROVIDED.value}:
            continue
        creator = _enum(getattr(record, "created_by", None))
        if creator in {EvidenceCreatedBy.DEVELOPER_INPUT.value, EvidenceCreatedBy.RAG_RETRIEVAL.value, EvidenceCreatedBy.DETERMINISTIC_GIS.value}:
            continue
        text = " ".join(str(getattr(record, key, "") or "") for key in ("field_name", "fact", "finding", "value")).casefold()
        if any(term in text for term in terms):
            ids.append(str(getattr(record, "evidence_id", "")))
    return bool(ids), ids


def _requirement(
    requirement_id: str,
    label: str,
    satisfied: bool,
    why_required: str,
    next_step: str,
    owner: str | None = None,
    evidence_ids: list[str] | None = None,
) -> StageRequirement:
    return StageRequirement(
        requirement_id=requirement_id,
        label=label,
        status="SATISFIED" if satisfied else "REQUIRED_TO_PROGRESS",
        why_required=why_required,
        next_step=next_step,
        owner=owner,
        evidence_ids=list(evidence_ids or []),
    )


def _maturity_summary(records: list[Any]) -> dict[str, int]:
    summary = {
        "Developer Input": 0,
        "Observed / Authoritative Evidence": 0,
        "Deterministic Derived Evidence": 0,
        "Assumption / Contextual Evidence": 0,
        "Confirmation Required": 0,
    }
    for record in records:
        creator = _enum(getattr(record, "created_by", None))
        trust = _enum(getattr(record, "source_trust", None))
        state = _enum(getattr(record, "evidence_state", None))
        if creator == EvidenceCreatedBy.DEVELOPER_INPUT.value:
            key = "Developer Input"
        elif creator == EvidenceCreatedBy.DETERMINISTIC_GIS.value:
            key = "Deterministic Derived Evidence"
        elif trust == EvidenceSourceTrust.AUTHORITATIVE_POLICY.value:
            key = "Observed / Authoritative Evidence"
        elif state in {AgentEvidenceState.UNKNOWN.value, AgentEvidenceState.NOT_PROVIDED.value} or getattr(record, "human_review_required", False):
            key = "Confirmation Required"
        else:
            key = "Assumption / Contextual Evidence"
        summary[key] += 1
    return summary


def build_stage_intelligence(
    context: ProjectContext,
    evidence_bundle: EvidenceBundle | None = None,
    assessment_result: AssessmentResult | None = None,
) -> StageIntelligence:
    """Build stage-specific closure guidance from actual stored evidence."""

    profile = _profile(context)
    records = _records(evidence_bundle)
    requirements: list[StageRequirement] = []
    provided_inputs: list[str] = []
    stage = _stage(context)

    if stage == "Site Discovery":
        has_location = context.location.latitude is not None and context.location.longitude is not None or bool(context.location.address)
        has_screening = any(_enum(getattr(item, "created_by", None)) == EvidenceCreatedBy.DETERMINISTIC_GIS.value for item in records)
        if not has_location:
            requirements.append(_requirement(
                "site-location", "Site location", False,
                "A site cannot be screened without a usable location.",
                "Provide an address or coordinates for deterministic spatial screening.",
                "Developer",
            ))
        if not has_screening:
            requirements.append(_requirement(
                "site-screening-evidence", "Early spatial screening", False,
                "Flood, biodiversity, planning and grid context are needed to judge whether deeper investigation is worthwhile.",
                "Run or review the available deterministic site evidence.",
                "Planning / environmental review",
            ))
    elif stage == "Early Feasibility":
        requirements.extend([
            _requirement("planned-power", "Planned power demand", _has_input(context, "planned_power"), "Power demand frames grid, energy and infrastructure questions.", "Confirm the current design demand and units.", "Developer"),
            _requirement("site-extent", "Site area or boundary", _has_input(context, "site_extent"), "Site extent is needed for spatial and planning interpretation.", "Provide a boundary or site area.", "Developer"),
            _requirement("grid-readiness", "MIC or equivalent grid-readiness evidence", _has_input(context, "mic") or _has_input(context, "power_strategy"), "Grid pathway information is required to understand a potential delivery constraint.", "Confirm MIC, connection strategy or the current operator evidence.", "Grid engineer"),
            _requirement("energy-strategy", "Energy strategy", _has_input(context, "energy_strategy"), "Energy strategy affects the evidence needed for power and environmental review.", "Record the current energy strategy or explicitly mark it unknown.", "Developer / energy specialist"),
        ])
        planning_ok, planning_ids = _has_site_specific_evidence(records, "PLANNING")
        requirements.append(_requirement(
            "planning-position", "Planning / zoning position", planning_ok,
            "A site-specific planning or zoning position is needed before feasibility can progress.",
            "Obtain current site-specific planning or zoning evidence.",
            "Planning consultant", planning_ids,
        ))
        water_ok, water_ids = _has_verified_domain(records, {"WATER"})
        requirements.append(_requirement("water-pathway", "Water / wastewater pathway", water_ok, "Site-specific capacity or connection evidence is needed before progressing feasibility.", "Obtain a site-specific utility or capacity confirmation.", "Water / wastewater specialist", water_ids))
    elif stage == "Deliverability Validation":
        if _has_input(context, "mic"):
            provided_inputs.append("MIC input supplied — delivery confirmation remains separate")
        if _has_input(context, "power_strategy"):
            provided_inputs.append("Power strategy input supplied — connection pathway remains separate")
        grid_ok, grid_ids = _has_delivery_evidence(records, "GRID")
        energy_ok, energy_ids = _has_delivery_evidence(records, "ENERGY")
        requirements.extend([
            _requirement("planned-power", "Confirmed planned power", _has_input(context, "planned_power"), "Delivery validation needs a defined demand envelope.", "Confirm the current project demand.", "Developer"),
            _requirement("grid-pathway", "Project-specific grid / MIC pathway", grid_ok, "Nearby infrastructure and developer inputs do not prove capacity, connection or energisation.", "Obtain project-specific grid pathway, MIC allocation and energisation evidence.", "Grid engineer", grid_ids),
            _requirement("energy-pathway", "Confirmed energy delivery pathway", energy_ok, "An energy input or strategy is not delivery confirmation.", "Obtain project-specific energy delivery and commissioning evidence.", "Energy specialist", energy_ids),
            _requirement("project-definition", "Confirmed phasing and project definition", _has_input(context, "phasing"), "Delivery-critical sequencing must be explicit before deliverability can be established.", "Confirm phasing and key delivery assumptions.", "Developer / delivery lead"),
            _requirement("project-documents", "Supporting technical project documents", _has_input(context, "project_documents"), "Supporting documents provide the project-specific confirmation needed at this stage.", "Upload or reference the current technical documents.", "Developer"),
        ])
        planning_ok, planning_ids = _has_delivery_evidence(records, "PLANNING")
        requirements.append(_requirement("planning-position", "Authoritative planning position", planning_ok, "Planning status is delivery-critical at validation.", "Obtain site-specific planning confirmation.", "Planning consultant", planning_ids))
        water_ok, water_ids = _has_delivery_evidence(records, "WATER")
        requirements.append(_requirement("water-pathway", "Water / wastewater pathway", water_ok, "Utility pathway evidence is delivery-critical at validation.", "Obtain site-specific capacity or connection confirmation.", "Water / wastewater specialist", water_ids))

    # Assessment is intentionally read but not used to alter raw finding
    # states.  This keeps the stage layer downstream of deterministic truth.
    _ = assessment_result
    return StageIntelligence(
        stage=stage,
        purpose=profile.purpose,
        customer_question=profile.question,
        evidence_expectations=list(profile.evidence_expectations),
        relevant_inputs=list(profile.relevant_inputs),
        not_required_at_stage=list(profile.not_required),
        investigation_emphasis=list(profile.emphasis),
        missing_evidence_wording=profile.missing_wording,
        progression_criteria=list(profile.progression),
        provided_inputs=provided_inputs,
        required_to_progress=requirements,
        evidence_maturity_summary=_maturity_summary(records),
    )


__all__ = ["build_stage_intelligence"]
