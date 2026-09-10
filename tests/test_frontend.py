"""Headless smoke and rendering tests for the Module 10 Streamlit frontend."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest

from frontend.components import source_label, status_label
from frontend.styles import BRAND_CSS


ROOT = Path(__file__).resolve().parents[1]
APP_PATH = ROOT / "frontend" / "app.py"
FIXTURES = ROOT / "tests" / "fixtures" / "agents"


def test_frontend_home_renders_brand_and_primary_journey_without_backend() -> None:
    app = AppTest.from_file(APP_PATH, default_timeout=10).run()

    assert not app.exception
    assert any("CANAVAN" in item.value and "ATLANTIC" in item.value for item in app.markdown)
    assert any(button.label == "Start a new site assessment" for button in app.button)
    assert any(button.label == "Explore data layers" for button in app.button)
    assert {"Home", "New Assessment", "Projects", "Data Layers", "Insights", "About"}.issubset(app.pills[0].options)
    rendered_text = " ".join(item.value for item in app.markdown)
    assert "6+" not in rendered_text
    assert "100+" not in rendered_text
    assert "FASTER" not in rendered_text


def test_frontend_new_assessment_keeps_validation_and_run_actions() -> None:
    app = AppTest.from_file(APP_PATH, default_timeout=10).run()
    app.session_state["active_page"] = "New Assessment"
    app.run()

    assert not app.exception
    assert any(button.label == "Validate Project Input" for button in app.button)
    assert any(button.label == "Run INTERLOCK Assessment" for button in app.button)
    assert any("Blank numeric fields remain unknown" in item.value for item in app.caption)
    assert all(item.value is None for item in app.number_input)


def test_successful_assessment_queues_safe_navigation_and_persists_result(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    result = json.loads((FIXTURES / "interlock_result_example.json").read_text(encoding="utf-8"))
    result.update(
        {
            "run_id": "frontend-navigation-run",
            "workflow_status": "REQUIRES_HUMAN_REVIEW",
            "requires_human_review": True,
            "stage_status": {"evidence": "COMPLETE", "assessment": "COMPLETE", "explanation": "COMPLETE"},
            "stage_counts": {"evidence": 1, "assessment": 1, "explanation": 1},
            "timings_ms": {"evidence": 3.0, "assessment": 2.0, "explanation": 1.0, "total": 6.0},
            "human_reviews": [],
        }
    )
    result["explanation_result"] = json.loads(
        (FIXTURES / "explanation_result_example.json").read_text(encoding="utf-8")
    )

    class FakeResponse:
        def __init__(self, payload: dict[str, object]) -> None:
            self.payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return self.payload

    def fake_get(url: str, **_: object) -> FakeResponse:
        assert url.endswith("/health")
        return FakeResponse({"status": "ok"})

    def fake_post(url: str, **_: object) -> FakeResponse:
        calls.append(url)
        if url.endswith("/project-input/validate"):
            return FakeResponse({"status": "valid", "project": {}, "missing_or_unknown": []})
        assert url.endswith("/interlock/run")
        return FakeResponse(result)

    monkeypatch.setattr("requests.get", fake_get)
    monkeypatch.setattr("requests.post", fake_post)
    monkeypatch.setenv("INTERLOCK_API_BASE_URL", "http://test-backend")

    app = AppTest.from_file(APP_PATH, default_timeout=10).run()
    app.session_state["active_page"] = "New Assessment"
    app.run()
    assert all(item.value is None for item in app.number_input)
    run_button = next(button for button in app.button if button.label == "Run INTERLOCK Assessment")

    run_button.click().run()

    assert not app.exception
    assert app.session_state["interlock_payload"]["run_id"] == "frontend-navigation-run"
    assert app.session_state["active_page"] == "Decision Pack"
    assert app.pills[0].value == "Projects"
    assert any("INTERLOCK Development Readiness Decision Pack" in item.value for item in app.markdown)
    assert any("Human review required" in item.value for item in app.markdown)
    assert len([url for url in calls if url.endswith("/interlock/run")]) == 1

    app.pills[0].select("Home").run()
    assert not app.exception
    assert app.session_state["active_page"] == "Home"
    app.pills[0].select("Projects").run()
    assert not app.exception
    assert app.session_state["active_page"] == "Decision Pack"
    assert app.session_state["interlock_payload"]["run_id"] == "frontend-navigation-run"
    assert len([url for url in calls if url.endswith("/interlock/run")]) == 1


def test_decision_pack_renders_complete_review_payload_without_missing_keys() -> None:
    payload = json.loads((FIXTURES / "interlock_result_example.json").read_text(encoding="utf-8"))
    explanation = json.loads((FIXTURES / "explanation_result_example.json").read_text(encoding="utf-8"))
    payload.update(
        {
            "run_id": "frontend-test-run",
            "workflow_status": "REQUIRES_HUMAN_REVIEW",
            "requires_human_review": True,
            "stage_status": {"evidence": "COMPLETE", "assessment": "COMPLETE", "explanation": "COMPLETE"},
            "stage_counts": {"evidence": 1, "assessment": 1, "explanation": 1},
            "timings_ms": {"evidence": 3.0, "assessment": 2.0, "explanation": 1.0, "total": 6.0},
            "human_reviews": [
                {
                    "review_id": "review-frontend-001",
                    "project_id": "synthetic-blanchardstown-001",
                    "domain": "GRID",
                    "reason": "Confirm current connection status.",
                    "severity": "MATERIAL",
                    "recommended_role": "GRID_ENGINEER",
                    "evidence_ids": ["ev-synthetic-site-001"],
                    "status": "REQUIRED",
                }
            ],
        }
    )
    explanation.update(
        {
            "executive_summary": "Automated analysis completed; professional review remains required.",
            "key_findings": ["UNKNOWN — GRID: current connection evidence is not supplied. [finding: finding-grid]"],
            "material_unknown_themes": [
                {
                    "theme_id": "grid-readiness",
                    "title": "Grid connection readiness",
                    "summary": "Current grid status remains unknown.",
                    "resolution_actions": ["Confirm current connection evidence."],
                    "finding_ids": ["finding-grid"],
                    "evidence_ids": ["ev-synthetic-site-001"],
                    "citations": [],
                }
            ],
            "next_action_plan": [
                {
                    "action_id": "action-grid",
                    "title": "Confirm grid readiness",
                    "rationale": "Resolve the grid evidence gap.",
                    "source_actions": [],
                    "finding_ids": ["finding-grid"],
                    "dependency_ids": [],
                    "evidence_ids": ["ev-synthetic-site-001"],
                    "specialist_roles": ["GRID_ENGINEER"],
                    "citations": [],
                }
            ],
            "customer_facing_citations": [],
        }
    )
    payload["explanation_result"] = explanation

    app = AppTest.from_file(APP_PATH, default_timeout=10).run()
    app.session_state["active_page"] = "Decision Pack"
    app.session_state["interlock_payload"] = payload
    app.run()

    assert not app.exception
    rendered_text = " ".join(item.value for item in app.markdown)
    assert "INTERLOCK Development Readiness Decision Pack" in rendered_text
    assert "Human review required" in rendered_text
    assert "Grid connection readiness" in rendered_text
    assert "Confirm grid readiness" in rendered_text
    assert "ADVANCE" not in rendered_text
    assert "HOLD" not in rendered_text
    assert "score" not in rendered_text.casefold()


def test_failed_workflow_renders_safe_failure_state_without_raw_details() -> None:
    payload = {
        "project_context": {"project_id": "failure-project", "project_name": "Failure test", "location": {}},
        "evidence_bundle": None,
        "assessment_result": None,
        "explanation_result": None,
        "workflow_status": "FAILED",
        "requires_human_review": False,
        "run_id": "failure-run",
        "stage_status": {"evidence": "FAILED", "assessment": "SKIPPED", "explanation": "SKIPPED"},
        "stage_errors": {"evidence": "evidence stage failed (RuntimeError)"},
        "stage_counts": {},
        "timings_ms": {"evidence": 2.0, "total": 2.0},
        "human_reviews": [],
    }
    app = AppTest.from_file(APP_PATH, default_timeout=10).run()
    app.session_state["active_page"] = "Decision Pack"
    app.session_state["interlock_payload"] = payload
    app.run()

    assert not app.exception
    rendered_text = " ".join(item.value for item in app.markdown)
    assert "Assessment could not be completed" in rendered_text
    assert "Traceback" not in rendered_text
    assert any("could not complete the Evidence stage" in item.value for item in app.error)


def test_evidence_page_keeps_customer_summary_and_debug_inspection_accessible() -> None:
    payload = json.loads((FIXTURES / "interlock_result_example.json").read_text(encoding="utf-8"))
    payload["explanation_result"] = json.loads(
        (FIXTURES / "explanation_result_example.json").read_text(encoding="utf-8")
    )
    app = AppTest.from_file(APP_PATH, default_timeout=10).run()
    app.session_state["active_page"] = "Evidence"
    app.session_state["interlock_payload"] = payload
    app.run()

    assert not app.exception
    rendered_text = " ".join(item.value for item in app.markdown)
    assert "Evidence chain" in rendered_text
    assert any(item.label == "View supporting evidence" for item in app.expander)
    assert any(button.label == "Run retrieval" for button in app.button)
    assert "Project Evidence" in rendered_text or "Public / GIS Evidence" in rendered_text


def test_frontend_status_and_source_labels_are_customer_safe() -> None:
    assert status_label("COMPLETE")[0] == "Analysis complete"
    assert status_label("REQUIRES_HUMAN_REVIEW")[0] == "Human review required"
    assert status_label("FAILED")[0] == "Assessment could not be completed"
    assert source_label({"created_by": "PROJECT_DOCUMENT"}) == "Project Evidence"
    assert source_label({"created_by": "DETERMINISTIC_GIS"}) == "Public / GIS Evidence"
    assert source_label({"created_by": "DEVELOPER_INPUT"}) == "Developer Provided"
    assert source_label({"created_by": "RAG_RETRIEVAL", "source_class": "PRIMARY"}) == "Authoritative Policy"
    assert source_label({"created_by": "RAG_RETRIEVAL", "source_class": "SUPPORTING"}) == "Supporting Policy"


def test_frontend_uses_brand_navigation_and_action_styles() -> None:
    assert 'button[aria-pressed="true"]' in BRAND_CSS
    assert "border-bottom: 2px solid var(--interlock-turquoise)" in BRAND_CSS
    assert "background: var(--interlock-red)" not in BRAND_CSS
    assert "background: var(--interlock-turquoise)" in BRAND_CSS
    assert "interlock-site-header" in BRAND_CSS
