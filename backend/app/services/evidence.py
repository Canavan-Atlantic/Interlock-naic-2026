"""Deterministic conversion of project input into an evidence ledger."""

from datetime import datetime, timezone
from typing import Any

from ..schemas.evidence import (
    EvidenceCategory,
    EvidenceConfidence,
    EvidenceLedger,
    EvidenceRecord,
    EvidenceReviewStatus,
    EvidenceSourceType,
    EvidenceState,
)
from ..schemas.project import ProjectInput


CUSTOMER_LIMITATION = "Customer-provided value; not independently verified."
MISSING_LIMITATION = "No value provided by the customer."


_FIELD_DEFINITIONS: tuple[tuple[str, EvidenceCategory, str, str | None], ...] = (
    ("project_name", EvidenceCategory.PROJECT, "Project name", None),
    ("development_type", EvidenceCategory.PROJECT, "Development type", None),
    ("project_stage", EvidenceCategory.PROJECT, "Project stage", None),
    ("site_address", EvidenceCategory.SITE, "Proposed site address", None),
    ("latitude", EvidenceCategory.SITE, "Proposed site latitude", "degrees"),
    ("longitude", EvidenceCategory.SITE, "Proposed site longitude", "degrees"),
    ("site_area_hectares", EvidenceCategory.SITE, "Site area", "hectares"),
    (
        "planned_power_demand_mw",
        EvidenceCategory.POWER_AND_ENERGY,
        "Planned power demand",
        "MW",
    ),
    (
        "requested_mic_mva",
        EvidenceCategory.POWER_AND_ENERGY,
        "Requested Maximum Import Capacity",
        "MVA",
    ),
    ("power_strategy", EvidenceCategory.POWER_AND_ENERGY, "Power strategy", None),
    ("energy_strategy", EvidenceCategory.POWER_AND_ENERGY, "Energy strategy", None),
    (
        "project_phasing_notes",
        EvidenceCategory.OTHER,
        "Project phasing and notes",
        None,
    ),
)


def _classify_value(value: Any) -> tuple[EvidenceState, EvidenceConfidence, str]:
    """Classify only what was supplied; do not infer missing project facts."""

    if value is None or (isinstance(value, str) and not value.strip()):
        return EvidenceState.NOT_PROVIDED, EvidenceConfidence.UNKNOWN, MISSING_LIMITATION

    if value == "Unknown":
        # HIGH means the system captured the customer's explicit Unknown value.
        # It does not mean that the underlying technical fact is verified.
        return EvidenceState.UNKNOWN, EvidenceConfidence.HIGH, CUSTOMER_LIMITATION

    # HIGH here means the system confidently captured what the customer entered,
    # not that the customer-provided value has been independently verified.
    return EvidenceState.PROVIDED, EvidenceConfidence.HIGH, CUSTOMER_LIMITATION


def project_input_to_evidence_ledger(
    project: ProjectInput,
    generated_at: datetime | None = None,
) -> EvidenceLedger:
    """Convert a ProjectInput into an in-memory evidence ledger."""

    ledger_timestamp = generated_at or datetime.now(timezone.utc)
    project_values = project.model_dump()
    entries: list[EvidenceRecord] = []

    for field_name, category, fact, unit in _FIELD_DEFINITIONS:
        value = project_values[field_name]
        evidence_state, confidence, limitation = _classify_value(value)
        entries.append(
            EvidenceRecord(
                evidence_id=f"project-input-{field_name}",
                category=category,
                field_name=field_name,
                fact=fact,
                value=value,
                unit=unit,
                source_type=EvidenceSourceType.CUSTOMER_INPUT,
                source_name="Developer Project Input",
                source_reference="project-input",
                evidence_state=evidence_state,
                confidence=confidence,
                limitation=limitation,
                review_status=EvidenceReviewStatus.UNREVIEWED,
                checked_at=ledger_timestamp,
            )
        )

    return EvidenceLedger(
        project_name=project.project_name,
        generated_at=ledger_timestamp,
        entries=entries,
        provided_count=sum(
            entry.evidence_state is EvidenceState.PROVIDED for entry in entries
        ),
        unknown_count=sum(
            entry.evidence_state is EvidenceState.UNKNOWN for entry in entries
        ),
        not_provided_count=sum(
            entry.evidence_state is EvidenceState.NOT_PROVIDED for entry in entries
        ),
        missing_or_unknown=[
            entry.field_name
            for entry in entries
            if entry.evidence_state
            in {EvidenceState.UNKNOWN, EvidenceState.NOT_PROVIDED}
        ],
    )
