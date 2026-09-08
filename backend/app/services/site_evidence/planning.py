"""Deterministic proximity counts for National Planning Applications."""

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
    query_references,
    records_from_rows,
    source_provenance,
    source_reference_label,
)


PLANNING_FIELDS = (
    "ApplicationNumber",
    "PlanningAuthority",
    "DevelopmentDescription",
    "DevelopmentAddress",
    "ApplicationStatus",
    "ApplicationType",
    "Decision",
    "ReceivedDate",
    "WithdrawnDate",
    "DecisionDate",
    "DecisionDueDate",
    "GrantDate",
    "ExpiryDate",
    "AppealRefNumber",
    "AppealStatus",
    "AppealDecision",
    "AppealDecisionDate",
    "AppealSubmittedDate",
    "LinkAppDetails",
)


def _unknown(context: SiteEvidenceContext, reason: str) -> DomainResult:
    limitation = f"Planning evidence is UNKNOWN: {reason}."
    record = evidence_record(
        "site-planning-availability",
        "planning.applications",
        "Nearby planning application evidence",
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
            "counts_within_radii": {},
            "nearby_records": [],
            "reason": reason,
            "limitations": [limitation],
            "checked_at": context.checked_at.isoformat().replace("+00:00", "Z"),
        },
        (record,),
    )


def evaluate_planning(
    context: SiteEvidenceContext,
    radii_m: Sequence[float] = DEFAULT_RADII_METRES,
    nearby_limit: int = 10,
) -> DomainResult:
    """Count and list nearby records using projected straight-line distance."""

    references = [
        reference
        for reference in dataset_references(context, "planning")
        if reference.queryable
    ]
    if not references:
        return _unknown(context, "no PROCESSED planning output is available")

    maximum_radius = max(radii_m) if radii_m else 5_000.0
    frame = query_references(references, context.point_itm, maximum_radius)
    if frame.empty:
        counts = {f"{int(radius / 1000)}_km": 0 for radius in radii_m}
        nearby_records: list[dict[str, Any]] = []
    else:
        distances = frame.geometry.distance(context.point_itm)
        frame = frame.copy()
        frame["distance_m"] = distances
        counts = {
            f"{int(radius / 1000)}_km": int((distances <= radius).sum())
            for radius in radii_m
        }
        nearby = frame.loc[distances <= maximum_radius].sort_values(
            "distance_m", kind="stable"
        ).head(nearby_limit)
        nearby_records = []
        for _, row in nearby.iterrows():
            item = {
                field_name: row[field_name]
                for field_name in PLANNING_FIELDS
                if field_name in row.index
            }
            # Reuse the common scalar conversion and provenance path without exposing
            # the geometry or any applicant fields.
            reference = references[0]
            item = records_from_rows(
                row.to_frame().T,
                reference,
                PLANNING_FIELDS,
                context.point_itm,
            )[0]
            nearby_records.append(item)

    limitations = [
        *source_provenance(references[0])["limitations"],
        "Counts and distances use deterministic straight-line distance in EPSG:2157.",
        "Nearby records are descriptive only; no planning similarity, approval, or PASS/FAIL conclusion is produced.",
        "Applicant personal information is excluded from the processed dataset and response.",
    ]
    payload = {
        "status": "SUCCESS",
        "evidence_state": "FACT",
        "radii_m": [float(radius) for radius in radii_m],
        "counts_within_radii": counts,
        "nearby_records": nearby_records,
        "source": source_provenance(references[0]),
        "limitations": dedupe_strings(limitations),
        "checked_at": context.checked_at.isoformat().replace("+00:00", "Z"),
    }
    record = evidence_record(
        "site-planning-counts",
        "planning.applications.within_radii",
        "Planning applications within configured radii",
        counts,
        checked_at=context.checked_at,
        source_name=references[0].entry.source_name,
        source_reference=source_reference_label(references[0]),
        limitation=payload["limitations"][1],
    )
    return DomainResult(payload, (record,))
