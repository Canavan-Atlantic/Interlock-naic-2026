"""Explicit UNKNOWN result for the tabular-only GZT source."""

from __future__ import annotations

from typing import Any

from ...schemas.evidence import EvidenceState
from .base import (
    DomainResult,
    SiteEvidenceContext,
    dataset_references,
    entry_sources,
    evidence_record,
)


def evaluate_zoning(context: SiteEvidenceContext) -> DomainResult:
    """Do not infer site zoning from tabular GZT metadata."""

    entries = entry_sources(context, "zoning")
    source_reference = entries[0].raw_relative_path if entries else None
    limitation = "Current tabular GZT source contains zoning metadata but no usable site polygon geometry."
    record = evidence_record(
        "site-zoning-state",
        "zoning.state",
        "Site zoning evidence state",
        "UNKNOWN",
        checked_at=context.checked_at,
        source_name=entries[0].source_name if entries else "INTERLOCK Module 4B",
        source_reference=source_reference,
        evidence_state=EvidenceState.UNKNOWN,
        limitation=limitation,
    )
    return DomainResult(
        {
            "status": "UNKNOWN",
            "evidence_state": "UNKNOWN",
            "state": "UNKNOWN",
            "reason": limitation,
            "next_data_dependency": "Official MyPlan spatial zoning service / geometry connector required.",
            "source": {
                "source_name": entries[0].source_name if entries else "GZT registry",
                "source_reference": source_reference,
                "registry_status": entries[0].status if entries else None,
            },
            "limitations": [limitation, "Module 4B does not call the external MyPlan service."],
            "checked_at": context.checked_at.isoformat().replace("+00:00", "Z"),
        },
        (record,),
    )
