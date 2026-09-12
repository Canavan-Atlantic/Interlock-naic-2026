"""Module 13 portfolio persistence and historical-reopen coverage."""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError
from streamlit.testing.v1 import AppTest

from backend.app import main
from backend.app.db import configure_database, init_db, session_scope
from backend.app.db.repository import persist_successful_interlock_result
from backend.app.schemas.agents import (
    AssessmentFinding,
    AssessmentResult,
    EvidenceBundle,
    ExplanationResult,
    ExplanationUnknownTheme,
    HumanReviewRequest,
    HumanReviewRole,
    InterlockResult,
    ProjectContext,
    WorkflowStatus,
)
from backend.app.services.rag.models import CitationReference, Domain
from frontend.report import render_assessment_report_pdf


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def portfolio_database() -> Iterator[None]:
    """Give each portfolio test a fresh in-memory database."""

    configure_database("sqlite+pysqlite:///:memory:")
    init_db()
    yield


def _context(project_id: str, *, power_mw: float | None = 50) -> ProjectContext:
    return ProjectContext(
        project_id=project_id,
        project_name=f"Project {project_id}",
        project_type="Data Centre",
        project_lifecycle_status="PRE_PLANNING",
        location={"address": f"{project_id} site", "jurisdiction": "IRELAND"},
        planned_power_mw=power_mw,
        power_strategy="Unknown",
        project_stage="Early Feasibility",
    )


def _result(context: ProjectContext, *, run_id: str, status: WorkflowStatus = WorkflowStatus.COMPLETE) -> InterlockResult:
    review = HumanReviewRequest(
        review_id=f"review-{run_id}",
        project_id=context.project_id,
        domain=Domain.GRID,
        reason="Confirm current connection status.",
        recommended_role=HumanReviewRole.GRID_ENGINEER,
        evidence_ids=[f"evidence-{run_id}"],
    )
    result = InterlockResult(
        project_context=context,
        evidence_bundle=EvidenceBundle(project_context=context),
        assessment_result=AssessmentResult(
            project_context=context,
            findings=[
                AssessmentFinding(
                    finding_id=f"finding-{run_id}",
                    domain=Domain.GRID,
                    status="UNKNOWN",
                    material_unknowns=["Connection information is not supplied."],
                )
            ],
        ),
        explanation_result=ExplanationResult(
            material_unknown_themes=[
                ExplanationUnknownTheme(
                    theme_id=f"theme-{run_id}",
                    title="Grid connection readiness",
                    summary="The current evidence does not resolve the connection position.",
                )
            ],
            source_citations=[
                CitationReference(
                    document_id="eirgrid-plan-001",
                    source_path="data/raw/grid/plan.pdf",
                    locator="p. 12",
                )
            ],
        ),
        workflow_status=status,
        human_reviews=[review],
        requires_human_review=True,
        run_id=run_id,
        timings_ms={"evidence": 10.0, "assessment": 2.0, "explanation": 1.0, "total": 13.0},
    )
    return result


def _persist(context: ProjectContext, result: InterlockResult, *, project_id: str | None = None) -> dict:
    with session_scope() as session:
        response = persist_successful_interlock_result(
            session, context, result, stored_project_id=project_id
        )
        session.commit()
        return response.model_dump(mode="json")


def test_projects_and_runs_preserve_multiple_immutable_snapshots(portfolio_database: None) -> None:
    context = _context("portfolio-project")
    first = _result(context, run_id="run-50")
    first_response = _persist(context, first)
    project_id = first_response["project_id"]

    second_context = _context("portfolio-project", power_mw=100)
    second = _result(second_context, run_id="run-100")
    _persist(second_context, second, project_id=project_id)

    with TestClient(main.app) as client:
        projects = client.get("/projects")
        detail = client.get(f"/projects/{project_id}")
        runs = client.get(f"/projects/{project_id}/runs")
        historical = client.get(f"/runs/{runs.json()[1]['id']}")

    assert projects.status_code == 200
    assert len(projects.json()) == 1
    assert detail.status_code == 200
    assert detail.json()["id"] == project_id
    assert detail.json()["project_context"]["planned_power_mw"] == 100
    assert runs.status_code == 200
    assert len(runs.json()) == 2
    assert runs.json()[0]["planned_power_mw"] == 100
    assert runs.json()[1]["planned_power_mw"] == 50
    assert historical.status_code == 200
    assert historical.json()["interlock_result"]["run_id"] == "run-50"
    assert historical.json()["interlock_result"]["assessment_result"]["findings"][0]["status"] == "UNKNOWN"
    assert historical.json()["interlock_result"]["explanation_result"]["source_citations"][0]["document_id"] == "eirgrid-plan-001"
    assert historical.json()["interlock_result"]["human_reviews"][0]["review_id"] == "review-run-50"


def test_successful_interlock_endpoint_persists_without_changing_result_contract(
    portfolio_database: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = _context("endpoint-project")
    expected = _result(context, run_id="endpoint-run", status=WorkflowStatus.COMPLETE)

    class FakeOrchestrator:
        def __init__(self, *_: object) -> None:
            pass

        def run(self, *_: object, **__: object) -> InterlockResult:
            return expected

    monkeypatch.setattr(main, "DeterministicInterlockOrchestrator", FakeOrchestrator)
    with TestClient(main.app) as client:
        response = client.post("/interlock/run", json=context.model_dump(mode="json"))
        projects = client.get("/projects")

    assert response.status_code == 200
    assert response.json()["run_id"] == "endpoint-run"
    assert len(projects.json()) == 1
    assert projects.json()[0]["latest_assessment"]["interlock_run_id"] == "endpoint-run"


def test_failed_interlock_result_is_not_saved(portfolio_database: None, monkeypatch: pytest.MonkeyPatch) -> None:
    context = _context("failed-project")
    failed = _result(context, run_id="failed-run", status=WorkflowStatus.FAILED)

    class FakeOrchestrator:
        def __init__(self, *_: object) -> None:
            pass

        def run(self, *_: object, **__: object) -> InterlockResult:
            return failed

    monkeypatch.setattr(main, "DeterministicInterlockOrchestrator", FakeOrchestrator)
    with TestClient(main.app) as client:
        response = client.post("/interlock/run", json=context.model_dump(mode="json"))
        projects = client.get("/projects")

    assert response.status_code == 200
    assert response.json()["workflow_status"] == "FAILED"
    assert projects.json() == []


def test_second_project_has_independent_history(portfolio_database: None) -> None:
    first = _persist(_context("project-a"), _result(_context("project-a"), run_id="a-run"))
    second = _persist(_context("project-b"), _result(_context("project-b"), run_id="b-run"))

    with TestClient(main.app) as client:
        first_runs = client.get(f"/projects/{first['project_id']}/runs")
        second_runs = client.get(f"/projects/{second['project_id']}/runs")

    assert len(first_runs.json()) == 1
    assert len(second_runs.json()) == 1
    assert first_runs.json()[0]["interlock_run_id"] == "a-run"
    assert second_runs.json()[0]["interlock_run_id"] == "b-run"


def test_database_failure_returns_controlled_error_and_keeps_previous_run(
    portfolio_database: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = _context("db-failure-project")
    first = _persist(context, _result(context, run_id="saved-run"))
    expected = _result(context, run_id="unsaved-run")

    class FakeOrchestrator:
        def __init__(self, *_: object) -> None:
            pass

        def run(self, *_: object, **__: object) -> InterlockResult:
            return expected

    def fail_persist(*_: object, **__: object) -> None:
        raise SQLAlchemyError("database unavailable; password=must-not-escape")

    monkeypatch.setattr(main, "DeterministicInterlockOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(main, "persist_successful_interlock_result", fail_persist)
    with TestClient(main.app) as client:
        response = client.post(
            "/interlock/run",
            params={"project_id": first["project_id"]},
            json=context.model_dump(mode="json"),
        )
        runs = client.get(f"/projects/{first['project_id']}/runs")

    assert response.status_code == 503
    assert response.json()["detail"] == "Assessment completed but could not be persisted; no historical run was saved."
    assert len(runs.json()) == 1
    assert runs.json()[0]["interlock_run_id"] == "saved-run"
    assert "password" not in response.text.casefold()


def test_historical_result_can_render_a_report_without_rerunning(portfolio_database: None) -> None:
    context = _context("report-project")
    stored = _persist(context, _result(context, run_id="report-run"))
    pdf = render_assessment_report_pdf(stored["interlock_result"])

    assert pdf.startswith(b"%PDF")


def test_streamlit_opens_stored_assessment_without_posting_a_new_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context("frontend-project")
    result = _result(context, run_id="frontend-stored-run")
    stored = {
        "id": "stored-run-id",
        "project_id": "stored-project-id",
        "interlock_run_id": result.run_id,
        "workflow_status": "COMPLETE",
        "planned_power_mw": 50,
        "findings_count": 1,
        "unknown_theme_count": 1,
        "human_review_count": 1,
        "citation_count": 1,
        "total_runtime_ms": 13.0,
        "created_at": "2026-09-12T10:00:00Z",
        "schema_version": "1.0",
        "report_version": "1.0",
        "submitted_project_context": context.model_dump(mode="json"),
        "interlock_result": result.model_dump(mode="json"),
        "report_available": True,
    }
    detail = {
        "id": "stored-project-id",
        "project_name": "Frontend Project",
        "project_type": "Data Centre",
        "address": "Frontend site",
        "project_context": context.model_dump(mode="json"),
        "latest_run_id": "stored-run-id",
        "latest_assessment": {
            key: stored[key]
            for key in (
                "id",
                "project_id",
                "interlock_run_id",
                "workflow_status",
                "planned_power_mw",
                "findings_count",
                "unknown_theme_count",
                "human_review_count",
                "citation_count",
                "total_runtime_ms",
                "created_at",
                "schema_version",
                "report_version",
            )
        },
        "run_count": 1,
    }

    class FakeResponse:
        def __init__(self, payload: object) -> None:
            self.payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> object:
            return self.payload

    def fake_get(url: str, **_: object) -> FakeResponse:
        if url.endswith("/projects/stored-project-id"):
            return FakeResponse(detail)
        if url.endswith("/projects/stored-project-id/runs"):
            return FakeResponse([detail["latest_assessment"]])
        if url.endswith("/runs/stored-run-id"):
            return FakeResponse(stored)
        raise AssertionError(f"unexpected portfolio GET: {url}")

    def fail_post(*_: object, **__: object) -> None:
        raise AssertionError("opening a stored assessment must not run the backend")

    monkeypatch.setattr("requests.get", fake_get)
    monkeypatch.setattr("requests.post", fail_post)
    monkeypatch.setenv("INTERLOCK_API_BASE_URL", "http://test-backend")

    app = AppTest.from_file(
        ROOT / "frontend" / "app.py", default_timeout=10
    ).run()
    app.session_state["active_page"] = "Projects"
    app.session_state["active_project_id"] = "stored-project-id"
    app.session_state["project_portfolio_view"] = True
    app.run()

    assert not app.exception
    next(button for button in app.button if button.label == "Open latest assessment").click().run()
    assert not app.exception
    assert app.session_state["interlock_payload"]["run_id"] == "frontend-stored-run"
    assert app.session_state["active_page"] == "Decision Pack"
