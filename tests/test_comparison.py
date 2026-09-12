"""Module 14 deterministic comparison tests."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError
from streamlit.testing.v1 import AppTest

from backend.app import main
from backend.app.db import configure_database, init_db, session_scope
from backend.app.db.models import AssessmentRun, Project
from frontend.report import build_comparison_report_view_model, render_comparison_report_pdf


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def comparison_database() -> None:
    configure_database("sqlite+pysqlite:///:memory:")
    init_db()


def _context(power: float, *, mic: float | None = None, energy: str | None = None) -> dict:
    return {
        "project_id": "blanchardstown",
        "project_name": "Blanchardstown Data Centre",
        "project_type": "Data Centre",
        "assessment_workflow": "SITE_FEASIBILITY",
        "project_lifecycle_status": "PRE_PLANNING",
        "location": {
            "address": "Blanchardstown, Dublin 15",
            "latitude": 53.3879,
            "longitude": -6.375,
            "local_authority": "Fingal County Council",
            "country": "Ireland",
            "jurisdiction": "IRELAND",
        },
        "site_boundary": None,
        "planned_power_mw": power,
        "requested_mic_mva": mic,
        "power_strategy": "Unknown",
        "energy_strategy": energy,
        "phasing": None,
        "project_stage": "Early Feasibility",
        "developer_inputs": {"planned_power_demand_mw": power, "requested_mic_mva": mic},
        "uploaded_document_refs": [],
        "source_project_input": None,
    }


def _result(power: float, *, run_id: str, compared: bool) -> dict:
    findings = [
        {"finding_id": "grid-unchanged", "domain": "GRID", "status": "UNKNOWN", "evidence_ids": ["ev-grid"]},
        {
            "finding_id": "water-changed",
            "domain": "WATER",
            "status": "CONDITIONAL" if compared else "UNKNOWN",
            "constraint": "Water capacity requires confirmation." if compared else None,
            "evidence_ids": ["ev-water"],
        },
    ]
    if not compared:
        findings.append({"finding_id": "planning-removed", "domain": "PLANNING", "status": "CLEAR", "evidence_ids": ["ev-old"]})
    else:
        findings.append({"finding_id": "energy-new", "domain": "ENERGY", "status": "CONSTRAINED", "evidence_ids": ["ev-new"]})

    unknown_themes = [
        {
            "theme_id": "unknown-stable",
            "title": "Stable unknown",
            "summary": "This remains unresolved.",
            "evidence_ids": ["ev-grid"],
        },
        {
            "theme_id": "unknown-changed",
            "title": "Changed unknown",
            "summary": "Updated wording." if compared else "Original wording.",
        },
    ]
    if not compared:
        unknown_themes.append({"theme_id": "unknown-resolved", "title": "Former unknown", "summary": "Previously unresolved."})
    else:
        unknown_themes.append({"theme_id": "unknown-new", "title": "New unknown", "summary": "New evidence is required."})

    dependencies = [
        {"dependency_id": "dep-grid", "project_id": "blanchardstown", "from_domain": "GRID", "to_domain": "ENERGY", "description": "Confirm grid evidence.", "status": "UNRESOLVED", "evidence_ids": ["ev-grid"]},
    ]
    if not compared:
        dependencies.append({"dependency_id": "dep-old", "project_id": "blanchardstown", "from_domain": "PLANNING", "to_domain": "WATER", "description": "Old dependency.", "status": "UNKNOWN", "evidence_ids": []})
    else:
        dependencies.append({"dependency_id": "dep-new", "project_id": "blanchardstown", "from_domain": "WATER", "to_domain": "ENERGY", "description": "New dependency.", "status": "POTENTIAL", "evidence_ids": ["ev-new"]})

    reviews = [
        {"review_id": "review-grid", "project_id": "blanchardstown", "domain": "GRID", "reason": "Confirm current connection status.", "recommended_role": "GRID_ENGINEER", "evidence_ids": ["ev-grid"], "status": "REQUIRED"},
    ]
    if not compared:
        reviews.append({"review_id": "review-removed", "project_id": "blanchardstown", "domain": "PLANNING", "reason": "Review old planning evidence.", "recommended_role": "PLANNING_CONSULTANT", "evidence_ids": [], "status": "REQUIRED"})
    else:
        reviews.append({"review_id": "review-new", "project_id": "blanchardstown", "domain": "WATER", "reason": "Confirm water capacity.", "recommended_role": "EIA_ENVIRONMENTAL_CONSULTANT", "evidence_ids": ["ev-new"], "status": "REQUIRED"})

    actions = [
        {"action_id": "action-grid", "title": "Confirm grid readiness", "rationale": "Resolve the grid evidence gap.", "finding_ids": ["grid-unchanged"], "evidence_ids": ["ev-grid"]},
    ]
    if not compared:
        actions.append({"action_id": "action-removed", "title": "Old action", "rationale": "Old follow-up.", "finding_ids": [], "evidence_ids": []})
    else:
        actions.append({"action_id": "action-new", "title": "Confirm water capacity", "rationale": "Resolve the water evidence gap.", "finding_ids": ["water-changed"], "evidence_ids": ["ev-new"]})

    records = [
        {"evidence_id": "ev-grid", "source_document_id": "doc-grid", "source_path": "data/grid.pdf", "domain": "GRID"},
    ]
    citations = [
        {"document_id": "doc-grid", "source_path": "data/grid.pdf", "locator": "p. 2" if compared else "p. 1"},
    ]
    if not compared:
        records.append({"evidence_id": "ev-old", "source_document_id": "doc-old", "source_path": "data/old.pdf", "domain": "PLANNING"})
        citations.append({"document_id": "doc-old", "source_path": "data/old.pdf", "locator": "p. 4"})
    else:
        records.append({"evidence_id": "ev-new", "source_document_id": "doc-new", "source_path": "data/new.pdf", "domain": "ENERGY"})
        citations.append({"document_id": "doc-new", "source_path": "data/new.pdf", "locator": "p. 8"})

    context = _context(power, mic=80 if compared else None, energy="On-site generation" if compared else None)
    return {
        "project_context": context,
        "evidence_bundle": {"project_context": context, "records": records, "dependencies": dependencies},
        "assessment_result": {
            "project_context": context,
            "findings": findings,
            "dependencies": dependencies,
            "material_unknowns": [],
            "human_reviews": reviews,
        },
        "explanation_result": {
            "material_unknown_themes": unknown_themes,
            "next_action_plan": actions,
            "customer_facing_citations": citations,
            "source_citations": citations,
            "dependencies": [],
            "next_actions": [],
        },
        "workflow_status": "REQUIRES_HUMAN_REVIEW",
        "human_reviews": reviews,
        "requires_human_review": True,
        "run_id": run_id,
        "generated_at": f"2026-09-12T10:{10 if not compared else 20}:00Z",
        "schema_version": "1.0",
        "stage_status": {"evidence": "COMPLETE", "assessment": "COMPLETE", "explanation": "COMPLETE"},
        "stage_counts": {"evidence": len(records), "assessment": len(findings), "explanation": len(unknown_themes)},
        "timings_ms": {"total": 13.0},
    }


def _seed_project(*, project_key: str = "blanchardstown") -> tuple[str, str, str]:
    project_uuid = str(uuid4())
    baseline_id = str(uuid4())
    comparison_id = str(uuid4())
    baseline_context = _context(50)
    comparison_context = _context(100, mic=80, energy="On-site generation")
    baseline_result = _result(50, run_id="interlock-50", compared=False)
    comparison_result = _result(100, run_id="interlock-100", compared=True)
    now = datetime(2026, 9, 12, 10, 0, tzinfo=timezone.utc)
    with session_scope() as session:
        project = Project(
            id=project_uuid,
            external_project_id=project_key,
            project_name="Blanchardstown Data Centre",
            project_type="Data Centre",
            address="Blanchardstown, Dublin 15",
            latitude=53.3879,
            longitude=-6.375,
            lifecycle_status="PRE_PLANNING",
            project_stage="Early Feasibility",
            project_context=baseline_context,
            created_at=now,
            updated_at=now,
        )
        session.add(project)
        session.flush()
        for index, (run_id, context, result, created) in enumerate(
            (
                (baseline_id, baseline_context, baseline_result, now),
                (comparison_id, comparison_context, comparison_result, now.replace(minute=20)),
            )
        ):
            session.add(
                AssessmentRun(
                    id=run_id,
                    project_id=project_uuid,
                    interlock_run_id=result["run_id"],
                    created_at=created,
                    workflow_status="REQUIRES_HUMAN_REVIEW",
                    planned_power_mw=context["planned_power_mw"],
                    submitted_project_context=context,
                    interlock_result=result,
                    total_runtime_ms=13.0,
                    evidence_count=len(result["evidence_bundle"]["records"]),
                    findings_count=len(result["assessment_result"]["findings"]),
                    unknown_theme_count=len(result["explanation_result"]["material_unknown_themes"]),
                    human_review_count=len(result["human_reviews"]),
                    citation_count=len(result["explanation_result"]["customer_facing_citations"]),
                    schema_version="1.0",
                    report_version="1.0",
                )
            )
            if index == 1:
                project.latest_run_id = run_id
        session.commit()
    return project_uuid, baseline_id, comparison_id


def test_comparison_endpoint_detects_changes_and_preserves_snapshots(comparison_database: None) -> None:
    project_id, baseline_id, comparison_id = _seed_project()
    with TestClient(main.app) as client:
        before = client.get(f"/runs/{baseline_id}").json()
        response = client.get(
            f"/projects/{project_id}/compare",
            params={"baseline_run_id": baseline_id, "comparison_run_id": comparison_id},
        )
        after = client.get(f"/runs/{baseline_id}").json()

    assert response.status_code == 200
    payload = response.json()
    assert payload["baseline_run_id"] == baseline_id
    assert payload["comparison_run_id"] == comparison_id
    assert payload["baseline_planned_power_mw"] == 50
    assert payload["comparison_planned_power_mw"] == 100
    assert payload["summary"]["input_changes"] == 3
    assert {item["field_path"] for item in payload["input_changes"]["changed"]} == {
        "energy_strategy", "requested_mic_mva", "planned_power_mw"
    }
    assert "project_name" not in {item["field_path"] for item in payload["input_changes"]["changed"]}
    assert payload["input_changes"]["changed"][0]["previous_display"] != "0"
    assert before == after


def test_comparison_sections_match_ids_conservatively(comparison_database: None) -> None:
    project_id, baseline_id, comparison_id = _seed_project()
    with TestClient(main.app) as client:
        payload = client.get(
            f"/projects/{project_id}/compare",
            params={"baseline_run_id": baseline_id, "comparison_run_id": comparison_id},
        ).json()

    assert payload["domain_changes"]
    domain_states = {item["domain"]: item for item in payload["domain_changes"]}
    assert domain_states["grid-energy"]["baseline_state"] == "UNKNOWN"
    assert domain_states["grid-energy"]["comparison_state"] == "CONSTRAINED"
    assert domain_states["grid-energy"]["changed"] is True
    assert domain_states["water"]["change_kind"] == "CHANGED"
    assert domain_states["planning"]["change_kind"] == "NO_LONGER_PRESENT"

    findings = payload["finding_changes"]
    assert {item["identity"] for item in findings["added"]} == {"energy-new"}
    assert {item["identity"] for item in findings["removed"]} == {"planning-removed"}
    assert {item["identity"] for item in findings["changed"]} == {"water-changed"}
    assert {item["identity"] for item in findings["unchanged"]} == {"grid-unchanged"}

    unknowns = payload["unknown_changes"]
    assert {item["identity"] for item in unknowns["added"]} == {"unknown-new"}
    assert {item["identity"] for item in unknowns["removed"]} == {"unknown-resolved"}
    assert {item["identity"] for item in unknowns["changed"]} == {"unknown-changed"}
    assert {item["identity"] for item in unknowns["unchanged"]} == {"unknown-stable"}

    assert {item["identity"] for item in payload["dependency_changes"]["added"]} == {"dep-new"}
    assert {item["identity"] for item in payload["dependency_changes"]["removed"]} == {"dep-old"}
    assert {item["identity"] for item in payload["human_review_changes"]["added"]} == {"review-new"}
    assert {item["identity"] for item in payload["human_review_changes"]["removed"]} == {"review-removed"}
    assert {item["identity"] for item in payload["next_action_changes"]["added"]} == {"action-new"}
    assert {item["identity"] for item in payload["next_action_changes"]["removed"]} == {"action-removed"}
    assert {item["identity"] for item in payload["evidence_changes"]["added"]} == {"ev-new"}
    assert {item["identity"] for item in payload["evidence_changes"]["removed"]} == {"ev-old"}
    assert {item["identity"] for item in payload["citation_changes"]["added"]} == {"doc-new"}
    assert {item["identity"] for item in payload["citation_changes"]["removed"]} == {"doc-old"}
    assert {item["identity"] for item in payload["citation_changes"]["changed"]} == {"doc-grid"}


def test_comparison_rejects_invalid_or_cross_project_runs(comparison_database: None) -> None:
    project_id, baseline_id, comparison_id = _seed_project()
    other_project_id, other_baseline_id, _ = _seed_project(project_key="lucan")
    with TestClient(main.app) as client:
        invalid = client.get(f"/projects/{project_id}/compare", params={"baseline_run_id": "missing", "comparison_run_id": comparison_id})
        cross_project = client.get(f"/projects/{project_id}/compare", params={"baseline_run_id": baseline_id, "comparison_run_id": other_baseline_id})
        same = client.get(f"/projects/{project_id}/compare", params={"baseline_run_id": baseline_id, "comparison_run_id": baseline_id})

    assert invalid.status_code == 404
    assert cross_project.status_code == 404
    assert same.status_code == 400
    assert other_project_id != project_id


def test_comparison_does_not_invoke_interlock_run(comparison_database: None, monkeypatch: pytest.MonkeyPatch) -> None:
    project_id, baseline_id, comparison_id = _seed_project()

    class MustNotRun:
        def __init__(self, *_: object) -> None:
            raise AssertionError("comparison must not construct the assessment orchestrator")

    monkeypatch.setattr(main, "DeterministicInterlockOrchestrator", MustNotRun)
    with TestClient(main.app) as client:
        response = client.get(
            f"/projects/{project_id}/compare",
            params={"baseline_run_id": baseline_id, "comparison_run_id": comparison_id},
        )
    assert response.status_code == 200


def test_comparison_report_contains_both_runs_without_score_or_decision(comparison_database: None) -> None:
    project_id, baseline_id, comparison_id = _seed_project()
    with TestClient(main.app) as client:
        comparison = client.get(
            f"/projects/{project_id}/compare",
            params={"baseline_run_id": baseline_id, "comparison_run_id": comparison_id},
        ).json()
    model = build_comparison_report_view_model(comparison)
    pdf = render_comparison_report_pdf(comparison)
    assert model["baseline_run_id"] == baseline_id
    assert model["comparison_run_id"] == comparison_id
    assert pdf.startswith(b"%PDF")
    import fitz

    document = fitz.open(stream=pdf, filetype="pdf")
    text = "\n".join(page.get_text() for page in document)
    document.close()
    assert baseline_id in text
    assert comparison_id in text
    assert "50.0 MW" in text
    assert "100.0 MW" in text
    assert "score" not in text.casefold()
    assert "advance" not in text.casefold()
    assert "hold" not in text.casefold()


def test_streamlit_comparison_page_uses_stored_payload_without_posting(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "project_id": "project-1",
        "project_name": "Blanchardstown Data Centre",
        "baseline_run_id": "run-50",
        "comparison_run_id": "run-100",
        "baseline_timestamp": "2026-09-12T10:00:00Z",
        "comparison_timestamp": "2026-09-12T10:20:00Z",
        "baseline_workflow_status": "REQUIRES_HUMAN_REVIEW",
        "comparison_workflow_status": "REQUIRES_HUMAN_REVIEW",
        "baseline_planned_power_mw": 50,
        "comparison_planned_power_mw": 100,
        "generated_at": "2026-09-12T10:30:00Z",
        "summary": {"input_changes": 1, "domain_changes": 1, "new_findings": 0, "resolved_unknowns": 0, "new_reviews": 0, "new_actions": 0},
        "input_changes": {"changed": [{"label": "Planned power", "previous_display": "50 MW", "comparison_display": "100 MW"}], "unchanged": [], "unchanged_count": 0},
        "domain_changes": [{"label": "Grid & Energy", "baseline_state": "UNKNOWN", "comparison_state": "CONDITIONAL", "change_kind": "CHANGED"}],
        **{
            key: {"added": [], "removed": [], "changed": [], "unchanged": [], "unchanged_count": 0}
            for key in ("finding_changes", "unknown_changes", "dependency_changes", "human_review_changes", "next_action_changes", "evidence_changes", "citation_changes")
        },
    }

    def fail_post(*_: object, **__: object) -> None:
        raise AssertionError("comparison page must not run an assessment")

    monkeypatch.setattr("requests.post", fail_post)
    monkeypatch.setenv("INTERLOCK_API_BASE_URL", "http://test-backend")
    app = AppTest.from_file(ROOT / "frontend" / "app.py", default_timeout=10).run()
    app.session_state["active_page"] = "Assessment Comparison"
    app.session_state["comparison_view"] = True
    app.session_state["comparison_payload"] = payload
    app.run()

    assert not app.exception
    rendered = " ".join(item.value for item in [*app.markdown, *app.caption])
    assert "What changed?" in rendered
    assert "50 MW" in rendered
    assert "100 MW" in rendered
    assert "no new assessment has been run" in rendered.casefold()
