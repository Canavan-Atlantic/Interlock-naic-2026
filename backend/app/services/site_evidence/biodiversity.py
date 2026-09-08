"""Deterministic SAC and SPA site-evidence queries."""

from __future__ import annotations

from typing import Any

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
)
from ...schemas.evidence import EvidenceState


SITE_FIELDS = ("SITECODE", "SITE_NAME")


def _kind_references(context: SiteEvidenceContext, kind: str) -> list[Any]:
    references = [
        reference
        for reference in dataset_references(context, "biodiversity")
        if kind.lower() in reference.entry.raw_relative_path.lower()
    ]
    if not references:
        return []

    onshore = [
        reference
        for reference in references
        if not any(
            marker in reference.layer_name.lower()
            for marker in ("marine", "offshore")
        )
    ]
    return onshore or references


def _unknown(kind: str, context: SiteEvidenceContext, reason: str) -> DomainResult:
    limitation = (
        f"{kind.upper()} site evidence is UNKNOWN: {reason}. "
        "No protected-area conclusion is inferred."
    )
    record = evidence_record(
        f"site-biodiversity-{kind.lower()}",
        f"biodiversity.{kind.lower()}",
        f"{kind.upper()} protected-area evidence",
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
            "intersecting_sites": [],
            "nearest_protected_site": None,
            "reason": reason,
            "limitations": [limitation],
            "checked_at": context.checked_at.isoformat().replace("+00:00", "Z"),
        },
        (record,),
    )


def evaluate_biodiversity(context: SiteEvidenceContext) -> DomainResult:
    """Query onshore SAC and SPA layers independently."""

    sections: dict[str, Any] = {}
    records = []
    limitations: list[str] = []
    for kind in ("SAC", "SPA"):
        references = _kind_references(context, kind)
        if not references:
            result = _unknown(kind, context, "no PROCESSED onshore output is available")
            sections[kind.lower()] = result.payload
            records.extend(result.records)
            limitations.extend(result.payload["limitations"])
            continue

        intersections: list[dict[str, Any]] = []
        for reference in references:
            local = query_references([reference], context.point_itm, 1.0)
            hits = intersecting_rows(local, context.point_itm)
            intersections.extend(
                records_from_rows(hits, reference, SITE_FIELDS, context.point_itm)
            )

        candidates = expanding_candidates(references, context.point_itm)
        nearest = nearest_row(candidates, context.point_itm)
        nearest_record = None
        if nearest is not None:
            nearest_reference = references[0]
            source_layer = str(nearest.get("SOURCE_LAYER", ""))
            for reference in references:
                if reference.layer_name.casefold() == source_layer.casefold():
                    nearest_reference = reference
                    break
            nearest_record = records_from_rows(
                candidates.loc[[nearest.name]],
                nearest_reference,
                SITE_FIELDS,
                context.point_itm,
            )[0]

        source_limitations = dedupe_strings(
            limitation
            for reference in references
            for limitation in source_provenance(reference)["limitations"]
        )
        source_limitations.append(
            "Distance is a deterministic straight-line distance in metres after EPSG:2157 transformation; no distance threshold is applied."
        )
        source_limitations.append(
            "Irish onshore layers are preferred when the registry contains both onshore and marine/offshore helper layers."
        )
        payload = {
            "status": "SUCCESS",
            "evidence_state": "FACT",
            "intersects": bool(intersections),
            "intersecting_sites": intersections,
            "nearest_protected_site": nearest_record,
            "source_datasets": [source_reference_label(reference) for reference in references],
            "limitations": dedupe_strings(source_limitations),
            "checked_at": context.checked_at.isoformat().replace("+00:00", "Z"),
        }
        sections[kind.lower()] = payload
        limitations.extend(payload["limitations"])
        records.append(
            evidence_record(
                f"site-biodiversity-{kind.lower()}",
                f"biodiversity.{kind.lower()}.intersects",
                f"{kind.upper()} protected-area intersection",
                bool(intersections),
                checked_at=context.checked_at,
                source_name=references[0].entry.source_name,
                source_reference=payload["source_datasets"][0],
                limitation=payload["limitations"][0] if payload["limitations"] else None,
            )
        )

    return DomainResult(
        {
            "status": "SUCCESS",
            "evidence_state": "FACT",
            **sections,
            "limitations": dedupe_strings(limitations),
        },
        tuple(records),
    )
