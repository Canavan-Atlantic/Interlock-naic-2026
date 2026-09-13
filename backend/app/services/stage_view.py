"""Build the single stage-specific customer view used by UI and PDF."""

from __future__ import annotations

from typing import Any, Iterable

from ..schemas.agents import (
    AgentEvidenceState,
    AssessmentResult,
    EvidenceBundle,
    EvidenceCreatedBy,
    EvidenceSourceTrust,
    StageAssessmentView,
    StageIntelligence,
)
from ..services.rag.models import Domain


_STATUS_PRIORITY = {"CLEAR": 1, "INFORMATIONAL": 2, "UNKNOWN": 3, "CONDITIONAL": 4, "CONSTRAINED": 5}
_FRIENDLY_DOMAINS = {
    "PLANNING": "Planning & Zoning",
    "GRID": "Grid",
    "ENERGY": "Energy",
    "WATER": "Water / Wastewater",
    "BIODIVERSITY": "Biodiversity",
    "ENVIRONMENT": "Environment",
    "DATA_CENTRE_POLICY": "Data Centre Policy",
    "GENERAL": "Project Definition",
}
_DOMAIN_GROUPS = (
    ("planning", "Planning & Zoning", ("PLANNING",)),
    ("grid-energy", "Grid & Energy", ("GRID", "ENERGY")),
    ("water", "Water / Wastewater", ("WATER",)),
    ("biodiversity-environment", "Biodiversity / Environment", ("BIODIVERSITY", "ENVIRONMENT")),
    ("data-centre-policy", "Data Centre Policy", ("DATA_CENTRE_POLICY",)),
    ("general", "Project Definition", ("GENERAL",)),
)
_SITE_DOMAINS = {"PLANNING", "GRID", "BIODIVERSITY", "ENVIRONMENT", "GENERAL"}
_ALL_DOMAINS = {domain.value for domain in Domain if domain != Domain.UNKNOWN}


def _enum(value: object) -> str:
    return str(getattr(value, "value", value) or "")


def _as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _short(value: object, fallback: str, limit: int = 180) -> str:
    text = " ".join(str(value or fallback).split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _stage_domains(stage: str) -> set[str]:
    return _SITE_DOMAINS if stage == "Site Discovery" else _ALL_DOMAINS


def _headline(domain: str, status: str, stage: str) -> str:
    if domain == "GRID":
        if stage == "Deliverability Validation":
            return "Project-specific grid connection pathway and energisation evidence remains outstanding."
        if status == "CONDITIONAL":
            return "Nearby grid infrastructure is visible, but project-specific connection readiness is not confirmed."
        return "Project-specific grid connection and MIC evidence remains unconfirmed."
    if domain == "ENERGY":
        if stage == "Deliverability Validation":
            return "Power inputs are supplied, but the delivery pathway is not confirmed."
        return "MIC, power strategy and energy strategy are required to progress the energy assessment."
    if domain == "PLANNING":
        if status == "CONSTRAINED":
            return "A planning or zoning constraint is recorded and requires professional review."
        return "Authoritative site-specific planning and zoning evidence is still required."
    if domain == "WATER":
        return "Site-specific water and wastewater capacity remains unconfirmed."
    if domain == "BIODIVERSITY":
        if status == "CONSTRAINED":
            return "A protected-site intersection is recorded and requires ecological review."
        return "No tested protected-site intersection was recorded; wider ecological review may still be required."
    if domain == "ENVIRONMENT":
        return "Flood, ground or heritage context is recorded; specialist interpretation may still be required."
    if domain == "DATA_CENTRE_POLICY":
        return "Current data-centre policy evidence was retrieved for this stage."
    return "Project definition and phasing information remains incomplete."


def _why(domain: str, status: str) -> str:
    if status == "CONSTRAINED":
        return "A material constraint is recorded in the evidence chain and needs accountable specialist review."
    if status == "CONDITIONAL":
        return "The evidence is useful context but does not establish a complete project position."
    if status == "UNKNOWN":
        return f"{_FRIENDLY_DOMAINS.get(domain, 'This domain')} cannot be treated as resolved from the available evidence."
    return "The available evidence does not identify an explicit hard constraint."


def _owner(domain: str) -> str:
    return {
        "GRID": "Grid engineer",
        "ENERGY": "Energy specialist",
        "PLANNING": "Planning consultant",
        "BIODIVERSITY": "Ecologist",
        "ENVIRONMENT": "Environmental / EIA specialist",
        "WATER": "Water / wastewater specialist",
        "GENERAL": "Developer / project team",
    }.get(domain, "Project team")


def _finding_view(finding: dict[str, Any], stage: str) -> dict[str, Any]:
    domain = _enum(finding.get("domain")) or "GENERAL"
    status = _enum(finding.get("status")) or "UNKNOWN"
    ids = [str(item) for item in _as_list(finding.get("evidence_ids")) if item]
    return {
        "finding_id": str(finding.get("finding_id") or "finding"),
        "domain": domain,
        "domain_label": _FRIENDLY_DOMAINS.get(domain, domain.replace("_", " ").title()),
        "status": status,
        "headline": _headline(domain, status, stage),
        "why_it_matters": _why(domain, status),
        "evidence_ids": ids,
        "next_action": _short(
            (_as_list(finding.get("evidence_required_next")) or ["Confirm the related evidence."])[0],
            "Confirm the related evidence.",
            150,
        ),
        "owner": _owner(domain),
    }


def _domain_states(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    states: list[dict[str, Any]] = []
    for key, label, domains in _DOMAIN_GROUPS:
        matching = [item for item in findings if item["domain"] in domains]
        if not matching:
            continue
        state = max((item["status"] for item in matching), key=lambda value: _STATUS_PRIORITY.get(value, 3))
        states.append({
            "key": key,
            "label": label,
            "state": state,
            "finding_count": len(matching),
            "evidence_ids": list(dict.fromkeys(id for item in matching for id in item["evidence_ids"])),
        })
    return states


def _action_view(action: dict[str, Any], finding_by_id: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    ids = [str(item) for item in _as_list(action.get("finding_ids")) if item]
    linked = next((finding_by_id[item] for item in ids if item in finding_by_id), None)
    domain = linked["domain"] if linked else "GENERAL"
    title = _short(action.get("title"), "Confirm related evidence.", 100)
    roles = [_short(item, "Project team", 60) for item in _as_list(action.get("specialist_roles")) if item]
    owner = roles[0] if roles else _owner(domain)
    return {
        "action_id": str(action.get("action_id") or f"action-{domain.casefold()}"),
        "title": title,
        "domain": domain,
        "domain_label": _FRIENDLY_DOMAINS.get(domain, domain.replace("_", " ").title()),
        "owner": owner,
        "reason": _short(action.get("rationale"), "Resolve the related evidence gap.", 150),
        "why_this_action": _short(action.get("rationale"), "Resolve the related evidence gap.", 500),
        "finding_ids": ids,
        "evidence_ids": [str(item) for item in _as_list(action.get("evidence_ids")) if item],
    }


def build_stage_assessment_view(
    context: Any,
    evidence_bundle: EvidenceBundle | None,
    assessment_result: AssessmentResult | None,
    stage_intelligence: StageIntelligence,
    explanation_result: Any | None = None,
) -> StageAssessmentView:
    """Build a bounded, stage-relevant projection without mutating raw outputs."""

    stage = stage_intelligence.stage
    domains = _stage_domains(stage)
    raw_findings = [
        _as_dict(item.model_dump(mode="python") if hasattr(item, "model_dump") else item)
        for item in (assessment_result.findings if assessment_result else [])
    ]
    findings = [_finding_view(item, stage) for item in raw_findings if _enum(item.get("domain")) in domains]
    evidence_records = list(evidence_bundle.records) if evidence_bundle else []
    relevant_ids = [
        str(record.evidence_id)
        for record in evidence_records
        if _enum(record.domain) in domains
    ]
    requirements = [
        _as_dict(item.model_dump(mode="python") if hasattr(item, "model_dump") else item)
        for item in stage_intelligence.required_to_progress
        if _enum(item.get("status")) == "REQUIRED_TO_PROGRESS"
    ]
    reviews: list[dict[str, Any]] = []
    for review in [
        *(evidence_bundle.human_review_requests if evidence_bundle else []),
        *(assessment_result.human_reviews if assessment_result else []),
    ]:
        item = _as_dict(review.model_dump(mode="python") if hasattr(review, "model_dump") else review)
        review_domains = {_enum(item.get("domain"))}
        review_ids = {str(value) for value in _as_list(item.get("evidence_ids"))}
        if review_domains & domains or review_ids & set(relevant_ids):
            reviews.append(item)
    finding_by_id = {item["finding_id"]: item for item in findings}
    actions: list[dict[str, Any]] = []
    explanation = explanation_result
    if explanation is not None:
        for raw in _as_list(getattr(explanation, "next_action_plan", None)):
            item = _action_view(_as_dict(raw.model_dump(mode="python") if hasattr(raw, "model_dump") else raw), finding_by_id)
            if item and (item["domain"] in domains or not item["finding_ids"]):
                actions.append(item)
    if not actions:
        for requirement in requirements:
            domain = _enum(requirement.get("owner")) or "GENERAL"
            actions.append({
                "action_id": f"action-{requirement.get('requirement_id', 'evidence')}",
                "title": _short(requirement.get("label"), "Confirm related evidence.", 100),
                "domain": "GENERAL",
                "domain_label": "Project Definition",
                "owner": requirement.get("owner") or "Project team",
                "reason": "Close the stage-specific information gap.",
                "why_this_action": requirement.get("next_step") or "Confirm the related evidence.",
                "finding_ids": [],
                "evidence_ids": list(_as_list(requirement.get("evidence_ids"))),
            })
    actions = list(dict((item["action_id"], item) for item in actions).values())
    return StageAssessmentView(
        stage=stage,
        customer_question=stage_intelligence.customer_question,
        requirement_heading=stage_intelligence.missing_evidence_wording,
        not_required_at_stage=list(stage_intelligence.not_required_at_stage),
        provided_inputs=list(stage_intelligence.provided_inputs),
        relevant_findings=findings,
        information_required=requirements,
        professional_reviews=reviews,
        next_actions=actions,
        domain_states=_domain_states(findings),
        relevant_evidence_ids=list(dict.fromkeys(relevant_ids)),
        relevant_evidence_count=len(set(relevant_ids)),
        total_evidence_count=len(evidence_records),
        counts={
            "finding_count": len(findings),
            "constraint_count": sum(item["status"] in {"CONSTRAINED", "CONDITIONAL"} for item in findings),
            "information_required_count": len(requirements),
            "professional_review_count": len(reviews),
            "action_count": len(actions),
            "relevant_evidence_count": len(set(relevant_ids)),
            "total_evidence_count": len(evidence_records),
        },
    )


__all__ = ["build_stage_assessment_view"]
