"""Deterministic contextual queries for the ESB Networks heatmap."""

from __future__ import annotations

from typing import Any, Sequence

from ...schemas.evidence import EvidenceState
from .base import (
    DomainResult,
    SiteEvidenceContext,
    dataset_references,
    dedupe_strings,
    entry_sources,
    evidence_record,
    query_references,
    records_from_rows,
    map_features_from_rows,
    source_provenance,
    source_reference_label,
)


GRID_FIELDS = (
    "Station Name",
    "Transformer GroupID",
    "Primary kV",
    "Secondary voltage(s)",
    "Voltage Class",
    "Transformer Configuration",
    "Installed Capacity MVA",
    "Demand FirmCapacity MVA",
    "Demand Available MVA",
    "Parent Available MVA",
    "Demand Parent Constraint",
    "Parent Feeder",
    "Parent Station",
    "TSO Interface Station",
    "Comment",
)


def _policy_documents(context: SiteEvidenceContext) -> list[dict[str, Any]]:
    return [
        {
            "source_name": entry.source_name,
            "source_reference": entry.raw_relative_path,
            "status": entry.status,
            "reason": "Registered-only policy/technical document; no policy interpretation is performed in Module 4B.",
            "limitations": list(entry.limitations),
        }
        for entry in entry_sources(context, "grid")
        if entry.status == "REGISTERED_ONLY" and not entry.processed_output_paths
    ]


def evaluate_grid(
    context: SiteEvidenceContext,
    *,
    radius_m: float = 25_000.0,
    voltage_classes: Sequence[str] | None = None,
    minimum_primary_kv: float | None = None,
    nearby_limit: int = 30,
) -> DomainResult:
    """Return nearby assets with optional deterministic pre-ranking filters."""

    references = [
        reference
        for reference in dataset_references(context, "grid")
        if reference.queryable
    ]
    policies = _policy_documents(context)
    if not references:
        limitation = "Grid asset evidence is UNKNOWN: no PROCESSED heatmap output is available."
        record = evidence_record(
            "site-grid-availability",
            "grid.nearby_assets",
            "Nearby grid asset evidence",
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
                "nearby_assets": [],
                "grouped_by_voltage_class": {},
                "policy_documents": policies,
                "reason": "no PROCESSED heatmap output is available",
                "limitations": [limitation],
                "checked_at": context.checked_at.isoformat().replace("+00:00", "Z"),
            },
            (record,),
        )

    frame = query_references(references, context.point_itm, radius_m)
    filters = {
        "radius_m": float(radius_m),
        "voltage_classes": list(voltage_classes) if voltage_classes else None,
        "minimum_primary_kv": minimum_primary_kv,
    }
    if not frame.empty:
        distances = frame.geometry.distance(context.point_itm)
        frame = frame.copy()
        frame["distance_m"] = distances
        frame = frame.loc[distances <= radius_m]
        if voltage_classes:
            accepted = {value.casefold() for value in voltage_classes}
            frame = frame.loc[
                frame["Voltage Class"].fillna("").astype(str).str.casefold().isin(accepted)
            ]
        if minimum_primary_kv is not None:
            import pandas as pd

            numeric_kv = frame["Primary kV"].astype(str).str.extract(r"([0-9]+(?:\.[0-9]+)?)")[0]
            numeric_kv = pd.to_numeric(numeric_kv, errors="coerce")
            frame = frame.loc[numeric_kv >= minimum_primary_kv]
        frame = frame.sort_values("distance_m", kind="stable").head(nearby_limit)

    assets: list[dict[str, Any]] = []
    if not frame.empty:
        for _, row in frame.iterrows():
            assets.extend(
                records_from_rows(
                    row.to_frame().T,
                    references[0],
                    GRID_FIELDS,
                    context.point_itm,
                )
            )

    grouped: dict[str, dict[str, Any]] = {}
    for asset in assets:
        voltage_class = asset.get("Voltage Class") or "Unknown voltage class"
        primary_kv = asset.get("Primary kV") or "Unknown primary kV"
        group_key = f"{voltage_class} / {primary_kv}"
        grouped.setdefault(group_key, {"count": 0, "assets": []})
        grouped[group_key]["count"] += 1
        grouped[group_key]["assets"].append(asset)

    limitations = dedupe_strings(
        [
            *source_provenance(references[0])["limitations"],
            "The July 2026 public heatmap is indicative and does not prove available connection capacity.",
            "Nearby assets are contextual evidence only; nearest substation is not treated as grid suitability or connection readiness.",
            "Connection relevance requires later grid-policy and domain interpretation; registered-only EirGrid PDFs are not interpreted here.",
        ]
    )
    payload = {
        "status": "SUCCESS",
        "evidence_state": "FACT",
        "filters": filters,
        "nearby_assets": assets,
        "map_features": map_features_from_rows(frame, references[0], context.point_itm, layer="grid", fields=GRID_FIELDS),
        "grouped_by_voltage_class": grouped,
        "policy_documents": policies,
        "source": source_provenance(references[0]),
        "limitations": limitations,
        "checked_at": context.checked_at.isoformat().replace("+00:00", "Z"),
    }
    record = evidence_record(
        "site-grid-nearby-assets",
        "grid.nearby_assets",
        "Nearby grid assets within configured context radius",
        len(assets),
        checked_at=context.checked_at,
        source_name=references[0].entry.source_name,
        source_reference=source_reference_label(references[0]),
        limitation=limitations[1],
    )
    return DomainResult(payload, (record,))
