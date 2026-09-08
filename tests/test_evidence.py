"""Tests for the Module 3 evidence ledger."""

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.schemas.evidence import EvidenceSourceType, EvidenceState
from backend.app.schemas.project import ProjectInput
from backend.app.services.evidence import project_input_to_evidence_ledger


client = TestClient(app)


MANUAL_PROJECT = {
    "project_name": "NAIC Test Data Centre",
    "development_type": "Data Centre",
    "project_stage": "Early Feasibility",
    "site_address": "Blanchardstown, Dublin 15",
    "latitude": 53.3879,
    "longitude": -6.3750,
    "planned_power_demand_mw": 50,
    "power_strategy": "Unknown",
    "project_phasing_notes": "Prototype test project for INTERLOCK.",
}


def test_complete_supplied_field_becomes_provided() -> None:
    ledger = project_input_to_evidence_ledger(
        ProjectInput(latitude=53.3879),
        generated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    latitude_entry = next(entry for entry in ledger.entries if entry.field_name == "latitude")
    assert latitude_entry.evidence_state is EvidenceState.PROVIDED
    assert latitude_entry.value == 53.3879
    assert latitude_entry.confidence == "HIGH"


def test_explicit_unknown_becomes_unknown() -> None:
    ledger = project_input_to_evidence_ledger(ProjectInput(power_strategy="Unknown"))

    power_entry = next(entry for entry in ledger.entries if entry.field_name == "power_strategy")
    assert power_entry.evidence_state is EvidenceState.UNKNOWN
    assert power_entry.value == "Unknown"


def test_null_field_becomes_not_provided() -> None:
    ledger = project_input_to_evidence_ledger(ProjectInput(requested_mic_mva=None))

    mic_entry = next(entry for entry in ledger.entries if entry.field_name == "requested_mic_mva")
    assert mic_entry.evidence_state is EvidenceState.NOT_PROVIDED
    assert mic_entry.value is None


def test_customer_provenance_and_limitation_are_recorded() -> None:
    ledger = project_input_to_evidence_ledger(ProjectInput(latitude=53.3879))

    latitude_entry = next(entry for entry in ledger.entries if entry.field_name == "latitude")
    assert latitude_entry.source_type is EvidenceSourceType.CUSTOMER_INPUT
    assert latitude_entry.source_name == "Developer Project Input"
    assert latitude_entry.source_reference == "project-input"
    assert latitude_entry.review_status == "UNREVIEWED"
    assert "customer-provided" in latitude_entry.limitation.lower()
    assert "not independently verified" in latitude_entry.limitation.lower()


def test_ledger_counts_missing_fields_and_ids_are_correct() -> None:
    ledger = project_input_to_evidence_ledger(ProjectInput(**MANUAL_PROJECT))

    assert ledger.provided_count == 8
    assert ledger.unknown_count == 1
    assert ledger.not_provided_count == 3
    assert ledger.missing_or_unknown == [
        "site_area_hectares",
        "requested_mic_mva",
        "power_strategy",
        "energy_strategy",
    ]
    evidence_ids = [entry.evidence_id for entry in ledger.entries]
    assert len(evidence_ids) == len(set(evidence_ids))


def test_evidence_endpoint_returns_200_for_valid_project() -> None:
    response = client.post("/evidence/from-project", json=MANUAL_PROJECT)

    assert response.status_code == 200
    assert response.json()["provided_count"] == 8
    assert response.json()["unknown_count"] == 1
    assert response.json()["not_provided_count"] == 3


def test_evidence_endpoint_rejects_invalid_project_input() -> None:
    response = client.post(
        "/evidence/from-project",
        json={"latitude": 91},
    )

    assert response.status_code == 422
