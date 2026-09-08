"""Tests for the Module 2 project-input validation endpoint."""

from fastapi.testclient import TestClient

from backend.app.main import app


client = TestClient(app)


def test_valid_project_input_returns_200() -> None:
    response = client.post(
        "/project-input/validate",
        json={
            "project_name": "NAIC Test Data Centre",
            "project_stage": "Early Feasibility",
            "latitude": 53.3879,
            "longitude": -6.3750,
            "planned_power_demand_mw": 50,
            "power_strategy": "Unknown",
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "valid"
    assert response.json()["project"]["development_type"] == "Data Centre"


def test_manual_naic_example_preserves_known_values_and_unknowns() -> None:
    response = client.post(
        "/project-input/validate",
        json={
            "project_name": "NAIC Test Data Centre",
            "development_type": "Data Centre",
            "project_stage": "Early Feasibility",
            "site_address": "Blanchardstown, Dublin 15",
            "latitude": 53.3879,
            "longitude": -6.3750,
            "planned_power_demand_mw": 50,
            "power_strategy": "Unknown",
            "project_phasing_notes": "Prototype test project for INTERLOCK.",
        },
    )

    assert response.status_code == 200
    body = response.json()
    project = body["project"]

    assert project["latitude"] == 53.3879
    assert project["longitude"] == -6.375
    assert project["planned_power_demand_mw"] == 50
    assert project["site_area_hectares"] is None
    assert project["requested_mic_mva"] is None
    assert project["power_strategy"] == "Unknown"
    assert project["energy_strategy"] is None
    assert body["missing_or_unknown"] == [
        "site_area_hectares",
        "requested_mic_mva",
        "power_strategy",
        "energy_strategy",
    ]


def test_missing_optional_fields_are_accepted_and_reported() -> None:
    response = client.post("/project-input/validate", json={})

    assert response.status_code == 200
    missing = response.json()["missing_or_unknown"]
    assert "requested_mic_mva" in missing
    assert "energy_strategy" in missing
    assert response.json()["project"]["requested_mic_mva"] is None


def test_invalid_latitude_is_rejected() -> None:
    response = client.post(
        "/project-input/validate",
        json={"latitude": 90.1},
    )

    assert response.status_code == 422


def test_invalid_longitude_is_rejected() -> None:
    response = client.post(
        "/project-input/validate",
        json={"longitude": -180.1},
    )

    assert response.status_code == 422


def test_negative_planned_power_demand_is_rejected() -> None:
    response = client.post(
        "/project-input/validate",
        json={"planned_power_demand_mw": -1},
    )

    assert response.status_code == 422


def test_negative_mic_is_rejected() -> None:
    response = client.post(
        "/project-input/validate",
        json={"requested_mic_mva": -1},
    )

    assert response.status_code == 422
