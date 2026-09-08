"""Explicit UNKNOWN water and wastewater capacity evidence."""

from __future__ import annotations

from typing import Any

from ...schemas.evidence import EvidenceState
from .base import DomainResult, SiteEvidenceContext, entry_sources, evidence_record


def evaluate_water(context: SiteEvidenceContext) -> DomainResult:
    """Expose registered-only documents without extracting site capacity claims."""

    entries = entry_sources(context, "water")
    documents = [
        {
            "source_name": entry.source_name,
            "source_reference": entry.raw_relative_path,
            "exists": (context.project_root / entry.raw_relative_path).is_file(),
            "registry_status": entry.status,
            "site_specific_structured_capacity_available": False,
            "limitations": list(entry.limitations),
        }
        for entry in entries
    ]
    limitation = (
        "Water and wastewater sources are REGISTERED_ONLY PDFs; site-specific structured capacity "
        "evidence is unavailable and document retrieval/interpretation is deferred to Module 5 / RAG."
    )
    record = evidence_record(
        "site-water-capacity",
        "water.site_specific_capacity",
        "Site-specific water and wastewater capacity evidence",
        None,
        checked_at=context.checked_at,
        source_name="Uisce Éireann capacity-register documents",
        source_reference=documents[0]["source_reference"] if documents else None,
        evidence_state=EvidenceState.UNKNOWN,
        limitation=limitation,
    )
    return DomainResult(
        {
            "status": "UNKNOWN",
            "evidence_state": "UNKNOWN",
            "documents": documents,
            "site_specific_structured_capacity_available": False,
            "capacity_treated_as_guaranteed": False,
            "reason": "REGISTERED_ONLY documents are not queried as structured site evidence.",
            "deferred_to": "Module 5 / RAG",
            "limitations": [limitation, "No capacity conclusion is inferred from the PDFs."],
            "checked_at": context.checked_at.isoformat().replace("+00:00", "Z"),
        },
        (record,),
    )
