"""Headless smoke and rendering tests for the Module 10 Streamlit frontend."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest

from backend.app.schemas.agents.common import ProjectContext, Workflow
from backend.app.schemas.project import ProjectInput, find_missing_or_unknown
from frontend.components import (
    HERO_ASSET_PATH,
    LOGO_ASSET_PATH,
    WHITE_LOGO_ASSET_PATH,
    hero_background_css,
    hero_asset_style,
    source_label,
    status_label,
)
from frontend.demo import (
    DEMO_PROJECT_ID,
    DEMO_PROJECT_METADATA,
    DEMO_PROJECT_PRESET,
    DEMO_PROJECT_PRESET_NAME,
    summarize_interlock_result,
)
from frontend.report import build_assessment_report_view_model, render_assessment_report_pdf, safe_report_filename
from frontend.result_summary import assessment_domain_state_summary
from frontend.styles import BRAND_CSS


ROOT = Path(__file__).resolve().parents[1]
APP_PATH = ROOT / "frontend" / "app.py"
FIXTURES = ROOT / "tests" / "fixtures" / "agents"


def _module_12_report_payload() -> dict[str, object]:
    """Small result-shaped payload containing every report branch we need to verify."""

    return {
        "project_context": {
            "project_id": "report-project-001",
            "project_name": "Report Test Data Centre",
            "project_type": "Data Centre",
            "assessment_workflow": "SITE_FEASIBILITY",
            "project_lifecycle_status": "PRE_PLANNING",
            "project_stage": "Early Feasibility",
            "location": {"address": "Blanchardstown, Dublin 15", "jurisdiction": "IRELAND"},
            "planned_power_mw": 50,
            "requested_mic_mva": None,
            "power_strategy": "Unknown",
            "energy_strategy": None,
            "phasing": None,
        },
        "evidence_bundle": {
            "records": [
                {
                    "evidence_id": "ev-grid-001",
                    "created_by": "RAG_RETRIEVAL",
                    "source_document_id": "eirgrid-plan-001",
                    "source_path": "data/rag/grid/eirgrid-plan.pdf",
                    "domain": "GRID",
                }
            ],
            "warnings": [],
        },
        "assessment_result": {
            "findings": [
                {
                    "finding_id": "finding-grid",
                    "domain": "GRID",
                    "status": "CONDITIONAL",
                    "decision_impact": "Connection evidence needs confirmation.",
                    "evidence_ids": ["ev-grid-001"],
                    "material_unknowns": ["Current connection position"],
                    "human_review_required": True,
                },
                {
                    "finding_id": "finding-water",
                    "domain": "WATER",
                    "status": "UNKNOWN",
                    "evidence_ids": [],
                },
                {
                    "finding_id": "finding-biodiversity",
                    "domain": "BIODIVERSITY",
                    "status": "CONSTRAINED",
                    "constraint": "Ecology baseline remains incomplete.",
                    "evidence_ids": [],
                },
            ],
            "constraints": ["Ecology baseline remains incomplete."],
            "dependencies": [{"dependency_id": "dep-grid", "status": "OPEN", "description": "Confirm connection evidence.", "evidence_ids": ["ev-grid-001"]}],
            "material_unknowns": ["Requested MIC is not provided."],
            "human_reviews": [],
        },
        "explanation_result": {
            "executive_summary": "Evidence is available for review, with material gaps remaining.",
            "known_facts": ["The project context identifies a Blanchardstown site."],
            "why_it_matters": ["Connection and ecology evidence affect the next feasibility step."],
            "key_findings": ["CONDITIONAL — GRID: confirm connection evidence. [finding: finding-grid]"],
            "material_unknown_themes": [
                {
                    "theme_id": "unknown-grid",
                    "title": "Grid connection readiness",
                    "summary": "Current grid status remains unknown.",
                    "resolution_actions": ["Confirm current connection evidence."],
                    "finding_ids": ["finding-grid"],
                    "evidence_ids": ["ev-grid-001"],
                }
            ],
            "dependencies": [],
            "contradictions": ["A potential source discrepancy needs review."],
            "next_action_plan": [
                {
                    "action_id": "action-grid",
                    "title": "Confirm grid readiness",
                    "rationale": "Resolve the grid evidence gap.",
                    "finding_ids": ["finding-grid"],
                    "evidence_ids": ["ev-grid-001"],
                    "specialist_roles": ["GRID_ENGINEER"],
                }
            ],
            "customer_facing_citations": [
                {
                    "document_id": "eirgrid-plan-001",
                    "source_path": "data/rag/grid/eirgrid-plan.pdf",
                    "page_start": 12,
                    "page_end": 13,
                    "locator": "p. 12–13",
                    "section_heading": "Network planning",
                }
            ],
            "warnings": ["Evidence requires professional validation before reliance."],
        },
        "workflow_status": "REQUIRES_HUMAN_REVIEW",
        "requires_human_review": True,
        "human_reviews": [
            {
                "review_id": "review-grid-001",
                "domain": "GRID",
                "reason": "Confirm current connection status.",
                "severity": "MATERIAL",
                "recommended_role": "GRID_ENGINEER",
                "evidence_ids": ["ev-grid-001"],
            }
        ],
        "run_id": "module-12-report-run",
        "generated_at": "2026-09-12T10:30:00Z",
        "schema_version": "1.0",
        "stage_status": {"evidence": "COMPLETE", "assessment": "COMPLETE", "explanation": "COMPLETE"},
        "stage_counts": {"evidence": 1, "assessment": 3, "explanation": 1},
        "timings_ms": {"evidence": 10.0, "assessment": 2.0, "explanation": 1.0, "total": 13.0},
    }


def test_frontend_home_renders_brand_and_primary_journey_without_backend() -> None:
    app = AppTest.from_file(APP_PATH, default_timeout=10).run()

    assert not app.exception
    assert any("CANAVAN" in item.value and "ATLANTIC" in item.value for item in app.markdown)
    assert any(button.label == "Start a new site assessment" for button in app.button)
    assert any(button.label == "Explore data layers" for button in app.button)
    assert {"Home", "New Assessment", "Projects", "Data Layers", "Insights", "About"}.issubset(app.pills[0].options)
    rendered_text = " ".join(
        re.sub(r"data:image/[^;]+;base64,[A-Za-z0-9+/=]+", "", item.value)
        for item in app.markdown
    )
    assert "6+" not in rendered_text
    assert "100+" not in rendered_text
    assert "FASTER" not in rendered_text


def test_frontend_uses_supplied_hero_and_extracted_brand_assets() -> None:
    assert HERO_ASSET_PATH.is_file()
    assert LOGO_ASSET_PATH.is_file()
    assert WHITE_LOGO_ASSET_PATH.is_file()
    assert "data:image/png;base64," in hero_asset_style()
    assert 'background-image: linear-gradient' in hero_background_css()
    assert 'url("data:image/png;base64,' in hero_background_css()

    app = AppTest.from_file(APP_PATH, default_timeout=10).run()

    assert not app.exception
    assert any("interlock-ca-logo" in item.value for item in app.markdown)
    assert any("interlock-footer-logo" in item.value for item in app.markdown)
    assert any("interlock-hero-image" in item.value for item in app.markdown)


def test_frontend_new_assessment_keeps_validation_and_run_actions() -> None:
    app = AppTest.from_file(APP_PATH, default_timeout=10).run()
    app.session_state["active_page"] = "New Assessment"
    app.run()

    assert not app.exception
    assert any(button.label == "Validate Project Input" for button in app.button)
    assert any(button.label == "Run INTERLOCK Assessment" for button in app.button)
    assert any("Blank numeric fields remain unknown" in item.value for item in app.caption)
    assert all(item.value is None for item in app.number_input)


def test_demo_preset_validates_as_project_context_and_preserves_unknowns() -> None:
    project_input = ProjectInput.model_validate(DEMO_PROJECT_PRESET)
    context = ProjectContext.from_project_input(
        project_input,
        project_id=DEMO_PROJECT_ID,
        assessment_workflow=Workflow.SITE_FEASIBILITY,
    )

    assert project_input.project_name == "NAIC Test Data Centre"
    assert context.project_id == DEMO_PROJECT_ID
    assert context.location.latitude == 53.3879
    assert context.location.longitude == -6.375
    assert context.planned_power_mw == 50
    assert context.requested_mic_mva is None
    assert context.power_strategy == "Unknown"
    assert context.site_boundary is None
    assert "requested_mic_mva" in find_missing_or_unknown(project_input)
    assert "site_area_hectares" in find_missing_or_unknown(project_input)


def test_load_demo_project_populates_editable_inputs_without_running_assessment() -> None:
    app = AppTest.from_file(APP_PATH, default_timeout=10).run()
    app.session_state["active_page"] = "New Assessment"
    app.run()

    load_button = next(button for button in app.button if button.label == "Load Demo Project")
    load_button.click().run()

    assert not app.exception
    assert any(DEMO_PROJECT_PRESET_NAME in item.value for item in app.info)
    assert next(item for item in app.text_input if item.label == "Project name (optional)").value == "NAIC Test Data Centre"
    assert next(item for item in app.text_input if item.label == "Address (optional)").value == "Blanchardstown, Dublin 15"
    assert next(item for item in app.number_input if item.label == "Latitude (optional)").value == 53.3879
    assert next(item for item in app.number_input if item.label == "Requested MIC (MVA, optional)").value is None
    assert app.session_state["interlock_payload"] is None


def test_demo_run_uses_normal_validation_and_interlock_path_and_stores_real_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, dict[str, object]]] = []
    result = json.loads((FIXTURES / "interlock_result_example.json").read_text(encoding="utf-8"))
    result.update(
        {
            "run_id": "frontend-demo-run",
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
        def __init__(self, url: str, payload: dict[str, object]) -> None:
            self.url = url
            self.payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return self.payload

    def fake_post(url: str, **kwargs: object) -> FakeResponse:
        calls.append((url, kwargs.get("json", {})))
        if url.endswith("/project-input/validate"):
            return FakeResponse(url, {"status": "valid", "project": {}, "missing_or_unknown": []})
        return FakeResponse(url, result)

    monkeypatch.setattr("requests.post", fake_post)
    monkeypatch.setenv("INTERLOCK_API_BASE_URL", "http://test-backend")

    app = AppTest.from_file(APP_PATH, default_timeout=10).run()
    app.session_state["active_page"] = "New Assessment"
    app.run()
    next(button for button in app.button if button.label == "Load Demo Project").click().run()
    next(button for button in app.button if button.label == "Run INTERLOCK Assessment").click().run()

    assert not app.exception
    assert [url.rsplit("/", 1)[-1] for url, _ in calls] == ["validate", "run"]
    context_payload = calls[1][1]
    assert context_payload["project_id"] == DEMO_PROJECT_ID
    assert context_payload["developer_inputs"]["preset_metadata"] == DEMO_PROJECT_METADATA
    assert context_payload["developer_inputs"]["project_evidence_mode"] == "Normal project"
    assert app.session_state["demo_run_summary"]["run_id"] == "frontend-demo-run"
    assert app.session_state["demo_run_summary"]["workflow_status"] == "REQUIRES_HUMAN_REVIEW"
    assert any("Demo run summary" in item.value for item in app.markdown)


def test_demo_summary_uses_only_actual_interlock_result_fields() -> None:
    payload = json.loads((FIXTURES / "interlock_result_example.json").read_text(encoding="utf-8"))
    payload["evidence_bundle"]["records"] = [
        {"created_by": "DETERMINISTIC_GIS"},
        {"created_by": "DEVELOPER_INPUT"},
    ]
    payload["assessment_result"]["findings"] = [
        {"status": "CONDITIONAL"},
        {"status": "UNKNOWN"},
    ]
    payload["explanation_result"] = {
        "material_unknown_themes": [{"theme_id": "unknown-1"}],
        "contradictions": ["review this"],
        "customer_facing_citations": [{"citation_id": "citation-1"}],
    }
    payload["human_reviews"] = [{"review_id": "review-1"}]
    payload["stage_counts"] = {"evidence": 2, "assessment": 2, "explanation": 1}
    payload["timings_ms"] = {"total": 12.5}

    summary = summarize_interlock_result(payload)

    assert summary["evidence_record_count"] == 2
    assert summary["finding_count"] == 2
    assert summary["conditional_or_constrained_finding_count"] == 1
    assert summary["unknown_theme_count"] == 1
    assert summary["contradiction_count"] == 1
    assert summary["human_review_count"] == 1
    assert summary["customer_facing_citation_count"] == 1
    assert summary["source_counts"] == {"DETERMINISTIC_GIS": 1, "DEVELOPER_INPUT": 1}
    assert summary["stage_counts"] == {"evidence": 2, "assessment": 2, "explanation": 1}
    assert summary["timings_ms"] == {"total": 12.5}
    assert "score" not in summary
    assert "decision" not in summary
    assert "recommendation" not in summary


def test_module_12_domain_visual_maps_only_actual_assessment_domains() -> None:
    payload = _module_12_report_payload()

    domains = assessment_domain_state_summary(payload)
    states = {item["label"]: item["state"] for item in domains}

    assert states["Grid & Energy"] == "CONDITIONAL"
    assert states["Water / Wastewater"] == "UNKNOWN"
    assert states["Biodiversity / Environment"] == "CONSTRAINED"
    assert "Flood" not in states
    assert "Heritage" not in states
    assert all("score" not in item for item in states)

    all_states = assessment_domain_state_summary(
        {
            "assessment_result": {
                "findings": [
                    {"finding_id": "clear", "domain": "PLANNING", "status": "CLEAR"},
                    {"finding_id": "informational", "domain": "GRID", "status": "INFORMATIONAL"},
                    {"finding_id": "conditional", "domain": "INFRASTRUCTURE", "status": "CONDITIONAL"},
                    {"finding_id": "constrained", "domain": "BIODIVERSITY", "status": "CONSTRAINED"},
                    {"finding_id": "unknown", "domain": "WATER", "status": "UNKNOWN"},
                ]
            }
        }
    )
    assert {item["state"] for item in all_states} == {
        "CLEAR",
        "INFORMATIONAL",
        "CONDITIONAL",
        "CONSTRAINED",
        "UNKNOWN",
    }


def test_module_12_decision_pack_renders_real_visual_states_without_outcomes() -> None:
    app = AppTest.from_file(APP_PATH, default_timeout=10).run()
    app.session_state["active_page"] = "Decision Pack"
    app.session_state["interlock_payload"] = _module_12_report_payload()
    app.run()

    assert not app.exception
    rendered_text = " ".join(
        [item.value for item in app.markdown] + [item.value for item in app.caption]
    ).casefold()
    assert "decision summary" in rendered_text
    assert "grid & energy" in rendered_text
    assert "conditional" in rendered_text
    assert "water / wastewater" in rendered_text
    assert "unknown" in rendered_text
    assert "score" not in rendered_text
    assert not re.search(r"\b(?:ADVANCE|HOLD|RECONFIGURE|STOP)\b", rendered_text.upper())


def test_module_12_report_contains_actual_result_fields_and_unknowns() -> None:
    payload = _module_12_report_payload()

    view_model = build_assessment_report_view_model(payload)
    assert view_model["project"]["requested_mic_mva"] == "Not provided"
    assert view_model["project"]["power_strategy"] == "Unknown"
    assert view_model["findings"][0]["finding_id"] == "finding-grid"
    assert view_model["unknowns"][0]["title"] == "Grid connection readiness"
    assert view_model["reviews"][0]["review_id"] == "review-grid-001"
    assert view_model["citations"][0]["document_id"] == "eirgrid-plan-001"

    pdf_bytes = render_assessment_report_pdf(payload)
    assert pdf_bytes.startswith(b"%PDF")
    import fitz

    document = fitz.open(stream=pdf_bytes, filetype="pdf")
    report_text = "\n".join(page.get_text() for page in document)
    document.close()

    assert "Report Test Data Centre" in report_text
    assert "module-12-report-run" in report_text
    assert "REQUIRES_HUMAN_REVIEW" in report_text
    assert "finding-grid" in report_text
    assert "CONDITIONAL" in report_text
    assert "Grid connection readiness" in report_text
    assert "GRID_ENGINEER" in report_text
    assert "eirgrid-plan-001" in report_text
    assert "p. 12" in report_text
    assert "Not provided" in report_text
    assert "readiness score" not in report_text.casefold()
    assert "ADVANCE" not in report_text
    assert "HOLD" not in report_text
    assert safe_report_filename(payload) == "INTERLOCK_Report_Test_Data_Centre_2026-09-12.pdf"


def test_module_12_report_download_uses_stored_result_without_backend_rerun(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def fail_post(*_: object, **__: object) -> None:
        calls.append("post")
        raise AssertionError("stored report rendering must not call the backend")

    monkeypatch.setattr("requests.post", fail_post)
    app = AppTest.from_file(APP_PATH, default_timeout=10).run()
    app.session_state["active_page"] = "Decision Pack"
    app.session_state["interlock_payload"] = _module_12_report_payload()
    app.run()

    assert not app.exception
    assert any(item.label == "Download Assessment Report" for item in app.download_button)
    assert calls == []


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
    assert "border-bottom: 3px solid var(--interlock-turquoise)" in BRAND_CSS
    assert "background: var(--interlock-red)" not in BRAND_CSS
    assert "background: var(--interlock-turquoise)" in BRAND_CSS
    assert "interlock-site-header" in BRAND_CSS
    assert "max-height: 52px" in BRAND_CSS
    assert "max-height: 55px" in BRAND_CSS
    assert "background-position: center 55%" in BRAND_CSS
    assert "margin: -8.6rem" not in BRAND_CSS
