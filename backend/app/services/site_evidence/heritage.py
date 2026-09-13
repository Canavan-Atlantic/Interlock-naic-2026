"""Deterministic SMR heritage-zone evidence queries."""

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
    nearest_row,
    query_references,
    records_from_rows,
    source_provenance,
    source_reference_label,
    map_features_from_rows,
)


HERITAGE_FIELDS = ("ZONE_ID",)


def evaluate_heritage(context: SiteEvidenceContext) -> DomainResult:
    """Use the current SMR zone-polygon source without inventing monument fields."""

    references = [
        reference
        for reference in dataset_references(context, "heritage")
        if reference.queryable
    ]
    if not references:
        limitation = "Heritage evidence is UNKNOWN: no PROCESSED SMR zone output is available."
        record = evidence_record(
            "site-heritage-availability",
            "heritage.smr_zone",
            "SMR zone evidence",
            None,
            checked_at=context.checked_at,
            source_name="INTERLOCK Module 4B",
            source_reference=None,
            evidence_state=EvidenceState.UNKNOWN,
            limitation=limitation,
        )
        return DomainResult(
            {
                "status": "UNKNOWN",
                "evidence_state": "UNKNOWN",
                "intersects": None,
                "intersecting_zone_ids": [],
                "nearest_zone": None,
                "reason": "no PROCESSED SMR zone output is available",
                "limitations": [limitation],
                "checked_at": context.checked_at.isoformat().replace("+00:00", "Z"),
            },
            (record,),
        )

    intersections: list[dict[str, Any]] = []
    for reference in references:
        local = query_references([reference], context.point_itm, 1.0)
        intersections.extend(
            records_from_rows(
                intersecting_rows(local, context.point_itm),
                reference,
                HERITAGE_FIELDS,
                context.point_itm,
            )
        )

    candidates = expanding_candidates(references, context.point_itm)
    nearest = nearest_row(candidates, context.point_itm)
    nearest_zone = None
    if nearest is not None:
        nearest_zone = records_from_rows(
            nearest.to_frame().T,
            references[0],
            HERITAGE_FIELDS,
            context.point_itm,
        )[0]

    limitations = dedupe_strings(
        [
            *source_provenance(references[0])["limitations"],
            "This is zone-level heritage evidence, not a complete monument-specific archaeological assessment.",
            "Nearest distance is a deterministic straight-line distance in EPSG:2157; no heritage threshold is applied.",
        ]
    )
    payload = {
        "status": "SUCCESS",
        "evidence_state": "FACT",
        "intersects": bool(intersections),
        "intersecting_zone_ids": [item.get("ZONE_ID") for item in intersections],
        "intersecting_zones": intersections,
        "nearest_zone": nearest_zone,
        "map_features": [
            feature
            for reference in references
            for feature in map_features_from_rows(
                query_references([reference], context.point_itm, 1.0),
                reference,
                context.point_itm,
                layer="heritage",
                fields=HERITAGE_FIELDS,
                limit=10,
            )
        ],
        "source": source_provenance(references[0]),
        "limitations": limitations,
        "checked_at": context.checked_at.isoformat().replace("+00:00", "Z"),
    }
    record = evidence_record(
        "site-heritage-zone-intersection",
        "heritage.smr_zone.intersects",
        "SMR zone intersection",
        bool(intersections),
        checked_at=context.checked_at,
        source_name=references[0].entry.source_name,
        source_reference=source_reference_label(references[0]),
        limitation=limitations[0] if limitations else None,
    )
    return DomainResult(payload, (record,))
