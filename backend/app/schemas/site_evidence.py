"""API schema for deterministic Module 4B site evidence."""

from typing import Any

from pydantic import BaseModel, Field

from .evidence import EvidenceLedger


class SiteEvidenceResponse(BaseModel):
    """Structured site evidence with the original Module 3 ledger retained."""

    project_location: dict[str, Any]
    biodiversity: dict[str, Any]
    flood: dict[str, Any]
    planning: dict[str, Any]
    heritage: dict[str, Any]
    ground: dict[str, Any]
    grid: dict[str, Any]
    zoning: dict[str, Any]
    water: dict[str, Any]
    evidence_ledger: EvidenceLedger
    limitations: list[str]
    timings_ms: dict[str, float]
    map_features: list[dict[str, Any]] = Field(default_factory=list)
