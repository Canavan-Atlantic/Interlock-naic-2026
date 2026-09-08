"""Deterministic groundwater, karst-landform, and traced-connection queries."""

from __future__ import annotations

from typing import Any, Sequence

from ...schemas.evidence import EvidenceState
from .base import (
    DEFAULT_RADII_METRES,
    DomainResult,
    SiteEvidenceContext,
    dataset_references,
    dedupe_strings,
    evidence_record,
    expanding_candidates,
    intersecting_rows,
    nearest_row,
    query_references,
    records_from_rows,
    source_provenance,
    source_reference_label,
)


GROUNDWATER_FIELDS = ("VUL40KID", "VUL_CAT", "VUL_DESC")
KARST_LANDFORM_FIELDS = (
    "KARST40KID",
    "KARST_TYPE",
    "KARST_NAME",
    "XYACCURACY",
    "COUNTY",
    "DATASOURCE",
)
KARST_CONNECTION_FIELDS = (
    "INPUT_SITE",
    "OUTPUTSITE",
    "RESULT",
    "COUNTY",
    "LENGTH_M",
    "GWFLOWRATE",
    "DIRECTION",
)


def _section_unknown(
    context: SiteEvidenceContext,
    section: str,
    reason: str,
) -> tuple[dict[str, Any], Any]:
    limitation = f"{section} evidence is UNKNOWN: {reason}."
    record = evidence_record(
        f"site-ground-{section.replace('_', '-')}",
        f"ground.{section}",
        f"{section.replace('_', ' ').title()} evidence",
        None,
        checked_at=context.checked_at,
        source_name="INTERLOCK Module 4B",
        source_reference=None,
        evidence_state=EvidenceState.UNKNOWN,
        limitation=limitation,
    )
    return (
        {
            "status": "UNKNOWN",
            "evidence_state": "UNKNOWN",
            "reason": reason,
            "limitations": [limitation],
            "checked_at": context.checked_at.isoformat().replace("+00:00", "Z"),
        },
        record,
    )


def _refs(context: SiteEvidenceContext, *markers: str) -> list[Any]:
    return [
        reference
        for reference in dataset_references(context, "ground")
        if reference.queryable
        and any(marker in reference.layer_name.lower() for marker in markers)
    ]


def _groundwater(context: SiteEvidenceContext) -> tuple[dict[str, Any], Any]:
    references = _refs(context, "vulnerability", "groundwater")
    if not references:
        return _section_unknown(context, "groundwater", "no PROCESSED vulnerability output is available")
    intersections: list[dict[str, Any]] = []
    for reference in references:
        local = query_references([reference], context.point_itm, 1.0)
        intersections.extend(
            records_from_rows(
                intersecting_rows(local, context.point_itm),
                reference,
                GROUNDWATER_FIELDS,
                context.point_itm,
            )
        )
    limitations = dedupe_strings(
        [
            *source_provenance(references[0])["limitations"],
            "All intersecting vulnerability polygons are returned when source topology produces more than one result.",
            "Vulnerability category is evidence only; no automatic project rejection is produced.",
        ]
    )
    payload = {
        "status": "SUCCESS",
        "evidence_state": "FACT",
        "intersects": bool(intersections),
        "intersections": intersections,
        "multiple_intersections": len(intersections) > 1,
        "source": source_provenance(references[0]),
        "limitations": limitations,
        "checked_at": context.checked_at.isoformat().replace("+00:00", "Z"),
    }
    record = evidence_record(
        "site-ground-groundwater-intersection",
        "ground.groundwater.intersects",
        "Groundwater vulnerability intersection",
        bool(intersections),
        checked_at=context.checked_at,
        source_name=references[0].entry.source_name,
        source_reference=source_reference_label(references[0]),
        limitation=limitations[-1],
    )
    return payload, record


def _karst_landforms(
    context: SiteEvidenceContext,
    radii_m: Sequence[float],
) -> tuple[dict[str, Any], Any]:
    references = _refs(context, "landform")
    if not references:
        return _section_unknown(context, "karst_landforms", "no PROCESSED karst landform output is available")
    maximum_radius = max(radii_m) if radii_m else 5_000.0
    local = query_references(references, context.point_itm, maximum_radius)
    if local.empty:
        counts = {f"{int(radius / 1000)}_km": 0 for radius in radii_m}
    else:
        distances = local.geometry.distance(context.point_itm)
        counts = {
            f"{int(radius / 1000)}_km": int((distances <= radius).sum())
            for radius in radii_m
        }
    nearest = nearest_row(expanding_candidates(references, context.point_itm), context.point_itm)
    nearest_landform = None
    if nearest is not None:
        nearest_landform = records_from_rows(
            nearest.to_frame().T,
            references[0],
            KARST_LANDFORM_FIELDS,
            context.point_itm,
        )[0]
    limitations = dedupe_strings(
        [
            *source_provenance(references[0])["limitations"],
            "Karst proximity is contextual evidence only; no automatic site rejection is produced.",
        ]
    )
    payload = {
        "status": "SUCCESS",
        "evidence_state": "FACT",
        "counts_within_radii": counts,
        "nearest_landform": nearest_landform,
        "source": source_provenance(references[0]),
        "limitations": limitations,
        "checked_at": context.checked_at.isoformat().replace("+00:00", "Z"),
    }
    record = evidence_record(
        "site-ground-karst-landforms",
        "ground.karst_landforms.nearest",
        "Nearest karst landform distance",
        None if nearest_landform is None else nearest_landform.get("distance_m"),
        checked_at=context.checked_at,
        source_name=references[0].entry.source_name,
        source_reference=source_reference_label(references[0]),
        limitation=limitations[-1],
    )
    return payload, record


def _karst_connections(context: SiteEvidenceContext) -> tuple[dict[str, Any], Any]:
    references = _refs(context, "traced", "connection")
    if not references:
        return _section_unknown(context, "karst_connections", "no PROCESSED traced-connection output is available")
    intersections: list[dict[str, Any]] = []
    for reference in references:
        local = query_references([reference], context.point_itm, 1.0)
        intersections.extend(
            records_from_rows(
                intersecting_rows(local, context.point_itm),
                reference,
                KARST_CONNECTION_FIELDS,
                context.point_itm,
            )
        )
    nearest = nearest_row(expanding_candidates(references, context.point_itm), context.point_itm)
    nearest_connection = None
    if nearest is not None:
        nearest_connection = records_from_rows(
            nearest.to_frame().T,
            references[0],
            KARST_CONNECTION_FIELDS,
            context.point_itm,
        )[0]
    limitations = dedupe_strings(
        [
            *source_provenance(references[0])["limitations"],
            "Traced-connection proximity is contextual evidence only; no automatic site rejection is produced.",
        ]
    )
    payload = {
        "status": "SUCCESS",
        "evidence_state": "FACT",
        "intersects": bool(intersections),
        "intersecting_connections": intersections,
        "nearest_connection": nearest_connection,
        "source": source_provenance(references[0]),
        "limitations": limitations,
        "checked_at": context.checked_at.isoformat().replace("+00:00", "Z"),
    }
    record = evidence_record(
        "site-ground-karst-connections",
        "ground.karst_connections.intersects",
        "Traced underground connection intersection",
        bool(intersections),
        checked_at=context.checked_at,
        source_name=references[0].entry.source_name,
        source_reference=source_reference_label(references[0]),
        limitation=limitations[-1],
    )
    return payload, record


def evaluate_ground(
    context: SiteEvidenceContext,
    radii_m: Sequence[float] = DEFAULT_RADII_METRES,
) -> DomainResult:
    """Return independent groundwater and karst evidence sections."""

    sections: dict[str, Any] = {}
    records = []
    limitations: list[str] = []
    for key, evaluator in (
        ("groundwater", _groundwater),
        ("karst_landforms", lambda current: _karst_landforms(current, radii_m)),
        ("karst_connections", _karst_connections),
    ):
        payload, record = evaluator(context)
        sections[key] = payload
        records.append(record)
        limitations.extend(payload.get("limitations", []))
    successful = any(section.get("status") == "SUCCESS" for section in sections.values())
    return DomainResult(
        {
            "status": "SUCCESS" if successful else "UNKNOWN",
            "evidence_state": "FACT" if successful else "UNKNOWN",
            **sections,
            "limitations": dedupe_strings(limitations),
        },
        tuple(records),
    )
