"""Headless smoke and rendering tests for the Module 10 Streamlit frontend."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest

from frontend.components import source_label, status_label


ROOT = Path(__file__).resolve().parents[1]
APP_PATH = ROOT / "frontend" / "app.py"
FIXTURES = ROOT / "tests" / "fixtures" / "agents"


def test_frontend_home_renders_brand_and_primary_journey_without_backend() -> None:
    app = AppTest.from_file(APP_PATH, default_timeout=10).run()

    assert not app.exception
    assert app.title[0].value == "INTERLOCK"
    assert any(button.label == "Start a new site assessment" for button in app.button)
    assert any(button.label == "Explore how INTERLOCK works" for button in app.button)
    assert "Decision Pack" in app.pills[0].options


def test_frontend_new_assessment_keeps_validation_and_run_actions() -> None:
    app = AppTest.from_file(APP_PATH, default_timeout=10).run()
    app.session_state["active_page"] = "New Assessment"
    app.run()

    assert not app.exception
    assert any(button.label == "Validate Project Input" for button in app.button)
    assert any(button.label == "Run INTERLOCK assessment" for button in app.button)
    assert any("Blank numeric fields remain unknown" in item.value for item in app.caption)
    assert all(item.value is None for item in app.number_input)


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


def test_frontend_status_and_source_labels_are_customer_safe() -> None:
    assert status_label("COMPLETE")[0] == "Analysis complete"
    assert status_label("REQUIRES_HUMAN_REVIEW")[0] == "Human review required"
    assert status_label("FAILED")[0] == "Assessment could not be completed"
    assert source_label({"created_by": "PROJECT_DOCUMENT"}) == "Project evidence"
    assert source_label({"created_by": "DETERMINISTIC_GIS"}) == "Public / GIS evidence"
    assert source_label({"created_by": "RAG_RETRIEVAL", "source_class": "PRIMARY"}) == "Authoritative policy"
