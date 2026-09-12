"""Deterministic, presentation-safe views of an InterlockResult."""

from __future__ import annotations

from collections import Counter
from typing import Any


_STATUS_PRIORITY = {
    "NOT_ASSESSED": 0,
    "CLEAR": 1,
    "INFORMATIONAL": 2,
    "UNKNOWN": 3,
    "CONDITIONAL": 4,
    "CONSTRAINED": 5,
}

# These are display groupings of domains that already exist in the shared
# assessment contract.  A group is rendered only when its source domain is
# present in the returned assessment findings.
DOMAIN_GROUPS = (
    ("planning", "Planning & Zoning", ("PLANNING",)),
    ("grid-energy", "Grid & Energy", ("GRID", "ENERGY")),
    ("water", "Water / Wastewater", ("WATER",)),
    ("biodiversity-environment", "Biodiversity / Environment", ("BIODIVERSITY", "ENVIRONMENT")),
    ("infrastructure", "Infrastructure", ("INFRASTRUCTURE",)),
    ("data-centre-policy", "Data Centre Policy", ("DATA_CENTRE_POLICY",)),
    ("general", "General Project Evidence", ("GENERAL",)),
    ("eu-reporting", "EU Reporting", ("EU_REPORTING",)),
    ("responsible-ai", "Responsible AI", ("RESPONSIBLE_AI",)),
    ("unknown", "Unclassified", ("UNKNOWN",)),
)


def assessment_domain_state_summary(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Map structured assessment findings into truthful visual domain groups."""

    assessment = _as_dict(payload.get("assessment_result"))
    findings = [_as_dict(item) for item in _as_list(assessment.get("findings"))]
    result: list[dict[str, Any]] = []
    assigned: set[int] = set()

    for key, label, source_domains in DOMAIN_GROUPS:
        matches = [
            (index, finding)
            for index, finding in enumerate(findings)
            if _enum_text(finding.get("domain")) in source_domains
        ]
        if not matches:
            continue
        assigned.update(index for index, _ in matches)
        result.append(_group_summary(key, label, source_domains, [finding for _, finding in matches]))

    # Preserve any future/unknown domain returned by the backend instead of
    # silently dropping it from the customer-facing summary.
    for index, finding in enumerate(findings):
        if index in assigned:
            continue
        domain = _enum_text(finding.get("domain")) or "UNKNOWN"
        result.append(_group_summary(domain.casefold(), domain.replace("_", " ").title(), (domain,), [finding]))
    return result


def summarize_interlock_result(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a small summary using only fields present in an InterlockResult."""

    context = _as_dict(payload.get("project_context"))
    location = _as_dict(context.get("location"))
    evidence = _as_dict(payload.get("evidence_bundle"))
    assessment = _as_dict(payload.get("assessment_result"))
    explanation = _as_dict(payload.get("explanation_result"))
    records = _as_list(evidence.get("records"))
    findings = _as_list(assessment.get("findings"))
    dependencies = _as_list(assessment.get("dependencies")) or _as_list(explanation.get("dependencies"))
    citations = _as_list(explanation.get("customer_facing_citations"))

    status_counts = Counter(
        _enum_text(_as_dict(finding).get("status")) or "UNKNOWN"
        for finding in findings
    )
    source_counts = Counter(
        _enum_text(_as_dict(record).get("created_by")) or "UNKNOWN"
        for record in records
    )

    return {
        "project_id": context.get("project_id"),
        "project_name": context.get("project_name"),
        "location": location.get("address") or location.get("local_authority"),
        "run_id": payload.get("run_id"),
        "generated_at": payload.get("generated_at"),
        "workflow_status": payload.get("workflow_status"),
        "evidence_record_count": len(records),
        "finding_count": len(findings),
        "finding_status_counts": dict(sorted(status_counts.items())),
        "conditional_or_constrained_finding_count": sum(
            status_counts.get(status, 0) for status in ("CONDITIONAL", "CONSTRAINED")
        ),
        "material_unknown_count": len(_as_list(assessment.get("material_unknowns"))),
        "unknown_theme_count": len(_as_list(explanation.get("material_unknown_themes"))),
        "dependency_count": len(dependencies),
        "contradiction_count": len(_as_list(explanation.get("contradictions"))),
        "human_review_count": len(_as_list(payload.get("human_reviews"))),
        "customer_facing_citation_count": len(citations),
        "source_counts": dict(sorted(source_counts.items())),
        "stage_counts": dict(_as_dict(payload.get("stage_counts"))),
        "timings_ms": dict(_as_dict(payload.get("timings_ms"))),
    }


def _group_summary(
    key: str,
    label: str,
    source_domains: tuple[str, ...],
    findings: list[dict[str, Any]],
) -> dict[str, Any]:
    statuses = [_enum_text(item.get("status")) or "UNKNOWN" for item in findings]
    state = max(statuses, key=lambda item: _STATUS_PRIORITY.get(item, _STATUS_PRIORITY["UNKNOWN"]))
    evidence_ids = _unique(
        evidence_id
        for finding in findings
        for evidence_id in _as_list(finding.get("evidence_ids"))
    )
    finding_ids = _unique(
        finding_id
        for finding in findings
        for finding_id in [finding.get("finding_id")]
        if finding_id
    )
    return {
        "key": key,
        "label": label,
        "source_domains": list(source_domains),
        "state": state,
        "finding_ids": finding_ids,
        "evidence_ids": evidence_ids,
    }


def _enum_text(value: object) -> str:
    return str(getattr(value, "value", value) or "")


def _unique(values: Any) -> list[Any]:
    output: list[Any] = []
    for value in values:
        if value not in output:
            output.append(value)
    return output


def _as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


__all__ = ["DOMAIN_GROUPS", "assessment_domain_state_summary", "summarize_interlock_result"]
