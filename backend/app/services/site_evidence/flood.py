"""Deterministic flood-layer evidence queries."""

from __future__ import annotations

from typing import Any

from ...schemas.evidence import EvidenceState
from .base import (
    DomainResult,
    SiteEvidenceContext,
    dataset_references,
    dedupe_strings,
    evidence_record,
    expanding_candidates,
    intersecting_rows,
    layer_return_period,
    nearest_row,
    query_references,
    records_from_rows,
    source_provenance,
    source_reference_label,
)


FLOOD_FIELDS = ("UUID", "PPPP", "PROJ_NAME", "PROJ_TYPE")


def _flood_type(reference: Any) -> str:
    source = reference.entry.raw_relative_path.lower()
    if "ext_c" in source:
        return "coastal"
    if "ext_f" in source:
        return "fluvial"
    return "unknown"


def _layer_unknown(
    context: SiteEvidenceContext,
    reference: Any,
    flood_type: str,
) -> dict[str, Any]:
    limitation = dedupe_strings(
        [
            *source_provenance(reference)["limitations"],
            f"Registry status is {reference.entry.status}; only PROCESSED datasets are queried as deterministic evidence.",
        ]
    )
    return {
        "status": "UNKNOWN",
        "evidence_state": "UNKNOWN",
        "flood_type": flood_type,
        "source_layer": reference.layer_name,
        "return_period": layer_return_period(reference.layer_name),
        "project_point_intersects": None,
        "nearest_extent": None,
        "source": source_provenance(reference),
        "reason": "This generated output is not eligible for deterministic querying.",
        "limitations": limitation,
        "checked_at": context.checked_at.isoformat().replace("+00:00", "Z"),
    }


def _layer_result(context: SiteEvidenceContext, reference: Any) -> dict[str, Any]:
    flood_type = _flood_type(reference)
    if not reference.queryable:
        return _layer_unknown(context, reference, flood_type)

    local = query_references([reference], context.point_itm, 1.0)
    hits = intersecting_rows(local, context.point_itm)
    intersecting_records = records_from_rows(
        hits,
        reference,
        FLOOD_FIELDS,
        context.point_itm,
    )

    nearest = nearest_row(expanding_candidates([reference], context.point_itm), context.point_itm)
    nearest_extent = None
    if nearest is not None:
        nearest_extent = records_from_rows(
            nearest.to_frame().T,
            reference,
            FLOOD_FIELDS,
            context.point_itm,
        )[0]

    limitations = dedupe_strings(
        [
            *source_provenance(reference)["limitations"],
            "Flood extent intersection and distance are evidence only; no planning, certification, or PASS/FAIL conclusion is produced.",
        ]
    )
    return {
        "status": "SUCCESS",
        "evidence_state": "FACT",
        "flood_type": flood_type,
        "source_layer": reference.layer_name,
        "return_period": layer_return_period(reference.layer_name),
        "project_point_intersects": bool(intersecting_records),
        "intersecting_extents": intersecting_records,
        "nearest_extent": None if intersecting_records else nearest_extent,
        "source": source_provenance(reference),
        "limitations": limitations,
        "checked_at": context.checked_at.isoformat().replace("+00:00", "Z"),
    }


def evaluate_flood(context: SiteEvidenceContext) -> DomainResult:
    """Return separate coastal/fluvial, return-period-specific evidence."""

    references = dataset_references(context, "flood", include_ineligible=True)
    sections: dict[str, list[dict[str, Any]]] = {"coastal": [], "fluvial": []}
    records = []
    limitations: list[str] = []
    for reference in references:
        flood_type = _flood_type(reference)
        if flood_type not in sections:
            continue
        result = _layer_result(context, reference)
        sections[flood_type].append(result)
        limitations.extend(result["limitations"])
        records.append(
            evidence_record(
                f"site-flood-{flood_type}-{reference.layer_name.lower()}",
                f"flood.{flood_type}.{reference.layer_name}.intersects",
                f"{flood_type.title()} flood layer intersection",
                result["project_point_intersects"],
                checked_at=context.checked_at,
                source_name=reference.entry.source_name,
                source_reference=source_reference_label(reference),
                evidence_state=(
                    EvidenceState.PROVIDED
                    if result["status"] == "SUCCESS"
                    else EvidenceState.UNKNOWN
                ),
                limitation=(result["limitations"][0] if result["limitations"] else None),
            )
        )

    for flood_type in sections:
        if not sections[flood_type]:
            limitation = f"No {flood_type} flood output is available in the processed registry."
            limitations.append(limitation)
            records.append(
                evidence_record(
                    f"site-flood-{flood_type}-availability",
                    f"flood.{flood_type}",
                    f"{flood_type.title()} flood evidence availability",
                    None,
                    checked_at=context.checked_at,
                    source_name="INTERLOCK Module 4B",
                    source_reference=None,
                    evidence_state=EvidenceState.UNKNOWN,
                    limitation=limitation,
                )
            )

    return DomainResult(
        {
            "status": "SUCCESS" if references else "UNKNOWN",
            "evidence_state": "FACT" if references else "UNKNOWN",
            "coastal": sections["coastal"],
            "fluvial": sections["fluvial"],
            "limitations": dedupe_strings(limitations),
        },
        tuple(records),
    )
