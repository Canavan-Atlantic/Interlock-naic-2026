"""Canonical, data-backed demo inputs and run-summary helpers for Module 11."""

from __future__ import annotations

from collections import Counter
from typing import Any


DEMO_PROJECT_ID = "naic-demo-blanchardstown"
DEMO_PROJECT_PRESET_NAME = "NAIC Demo Project"
DEMO_PROJECT_EVIDENCE_MODE = "Normal project"

# These values are the existing Blanchardstown project-input scenario used by
# the repository's deterministic tests and README command.  Missing values are
# intentionally None/Unknown so the demo exercises the same evidence behavior
# as an ordinary incomplete project input.
DEMO_PROJECT_PRESET: dict[str, object] = {
    "project_name": "NAIC Test Data Centre",
    "development_type": "Data Centre",
    "project_stage": "Early Feasibility",
    "site_address": "Blanchardstown, Dublin 15",
    "local_authority": None,
    "latitude": 53.3879,
    "longitude": -6.3750,
    "site_area_hectares": None,
    "planned_power_demand_mw": 50,
    "requested_mic_mva": None,
    "power_strategy": "Unknown",
    "energy_strategy": None,
    "project_phasing_notes": "Prototype test project for INTERLOCK.",
}

DEMO_PROJECT_METADATA: dict[str, object] = {
    "preset_name": DEMO_PROJECT_PRESET_NAME,
    "scenario": "Blanchardstown",
    "kind": "demo_benchmark_preset",
}


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
        str(_as_dict(finding).get("status") or "UNKNOWN")
        for finding in findings
    )
    source_counts = Counter(
        str(_as_dict(record).get("created_by") or "UNKNOWN")
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


def _as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


__all__ = [
    "DEMO_PROJECT_ID",
    "DEMO_PROJECT_EVIDENCE_MODE",
    "DEMO_PROJECT_METADATA",
    "DEMO_PROJECT_PRESET",
    "DEMO_PROJECT_PRESET_NAME",
    "summarize_interlock_result",
]
