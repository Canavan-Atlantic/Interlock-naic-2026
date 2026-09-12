"""FastAPI entry point for the INTERLOCK backend."""

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from sqlalchemy.exc import SQLAlchemyError

from .agents.assessment import DeterministicAssessmentAgent
from .agents.evidence import DeterministicEvidenceAgent, EvidenceAgentOptions
from .agents.explanation import DeterministicExplanationAgent, ExplanationAgentError
from .agents.orchestrator import DeterministicInterlockOrchestrator, OrchestratorOptions
from .schemas.agents import (
    AssessmentRequest,
    AssessmentResult,
    EvidenceBundle,
    ExplanationRequest,
    ExplanationResult,
    InterlockResult,
    ProjectContext,
)
from .schemas.evidence import EvidenceLedger
from .schemas.project import (
    ProjectInput,
    ProjectValidationResponse,
    find_missing_or_unknown,
)
from .schemas.site_evidence import SiteEvidenceResponse
from .schemas.portfolio import (
    AssessmentRunResponse,
    AssessmentRunSummary,
    ProjectCreate,
    ProjectDetail,
    ProjectSummary,
)
from .db import init_db, session_scope
from .db.repository import (
    create_or_get_project,
    list_projects,
    persist_successful_interlock_result,
    project_by_reference,
    project_detail,
    project_runs,
    run_by_id,
    run_response,
)
from .services.evidence import project_input_to_evidence_ledger
from .services.site_evidence import SiteEvidenceOptions, evaluate_site
from .services.rag.models import DocumentStatus, RAGDocument, RetrievalRequest, SourceClass
from .services.rag.retrieval import IndexNotBuiltError, StaleIndexError, search_index


app = FastAPI(title="INTERLOCK API", version="0.1.0")
PROJECT_ROOT = Path(__file__).resolve().parents[2]


@app.on_event("startup")
def initialize_database() -> None:
    """Prepare the portfolio schema before the API accepts requests."""

    try:
        init_db()
    except SQLAlchemyError as exc:
        raise RuntimeError("Application database initialization failed") from exc


@app.get("/health")
def health() -> dict[str, str]:
    """Return the backend health status."""

    return {
        "status": "ok",
        "service": "interlock-api",
        "version": "0.1.0",
    }


@app.post("/project-input/validate", response_model=ProjectValidationResponse)
def validate_project_input(project: ProjectInput) -> ProjectValidationResponse:
    """Validate and return structured project input without assessing viability."""

    return ProjectValidationResponse(
        status="valid",
        project=project,
        missing_or_unknown=find_missing_or_unknown(project),
    )


@app.post("/evidence/from-project", response_model=EvidenceLedger)
def evidence_from_project(project: ProjectInput) -> EvidenceLedger:
    """Create an in-memory evidence ledger from supplied project input."""

    return project_input_to_evidence_ledger(project)


@app.post("/evidence/site", response_model=SiteEvidenceResponse)
def site_evidence(
    project: ProjectInput,
    grid_min_primary_kv: float | None = Query(default=None, ge=0),
    grid_voltage_class: list[str] | None = Query(default=None),
) -> SiteEvidenceResponse:
    """Calculate deterministic public-data evidence for a validated site location."""

    if project.latitude is None or project.longitude is None:
        raise HTTPException(
            status_code=422,
            detail="latitude and longitude are required for a site evidence check",
        )
    return evaluate_site(
        project,
        PROJECT_ROOT,
        SiteEvidenceOptions(
            grid_voltage_classes=tuple(grid_voltage_class) if grid_voltage_class else None,
            grid_min_primary_kv=grid_min_primary_kv,
        ),
    )


@app.post("/agents/evidence", response_model=EvidenceBundle)
def evidence_agent(
    project_context: ProjectContext,
    include_project_documents: bool = Query(default=True),
    include_benchmark_documents: bool = Query(default=False),
) -> EvidenceBundle:
    """Assemble provenance-preserving evidence without producing a decision."""

    options = EvidenceAgentOptions(
        include_project_documents=include_project_documents,
        include_benchmark_documents=include_benchmark_documents,
    )
    agent = DeterministicEvidenceAgent(PROJECT_ROOT)
    # Preserve the original one-argument seam for existing integrations and
    # tests; the concrete agent's defaults are the early project-evidence mode.
    if include_project_documents and not include_benchmark_documents:
        return agent.run(project_context)
    return agent.run(project_context, options)


@app.post("/agents/assessment", response_model=AssessmentResult)
def assessment_agent(request: AssessmentRequest) -> AssessmentResult:
    """Assess an existing EvidenceBundle without gathering new evidence."""

    return DeterministicAssessmentAgent().run(request)


@app.post("/agents/explanation", response_model=ExplanationResult)
def explanation_agent(request: ExplanationRequest) -> ExplanationResult:
    """Explain an existing assessment without gathering evidence or deciding."""

    try:
        return DeterministicExplanationAgent().run(request)
    except ExplanationAgentError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/interlock/run", response_model=InterlockResult)
def interlock_run(
    project_context: ProjectContext,
    include_project_documents: bool = Query(default=True),
    include_benchmark_documents: bool = Query(default=False),
    run_id: str | None = Query(default=None, min_length=1),
    project_id: str | None = Query(default=None, min_length=1),
) -> InterlockResult:
    """Run the fixed Evidence -> Assessment -> Explanation workflow."""

    orchestrator = DeterministicInterlockOrchestrator(PROJECT_ROOT)
    result = orchestrator.run(
        project_context,
        OrchestratorOptions(
            include_project_documents=include_project_documents,
            include_benchmark_documents=include_benchmark_documents,
            run_id=run_id,
        ),
    )
    if str(getattr(result.workflow_status, "value", result.workflow_status)) in {
        "COMPLETE",
        "REQUIRES_HUMAN_REVIEW",
    }:
        try:
            with session_scope() as session:
                persist_successful_interlock_result(
                    session,
                    project_context,
                    result,
                    stored_project_id=project_id,
                )
                session.commit()
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (SQLAlchemyError, TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=503,
                detail="Assessment completed but could not be persisted; no historical run was saved.",
            ) from exc
    return result


@app.post("/projects", response_model=ProjectDetail, status_code=201)
def create_project(project_context: ProjectCreate) -> ProjectDetail:
    """Create or refresh a durable portfolio project without running an assessment."""

    try:
        with session_scope() as session:
            project = create_or_get_project(session, project_context)
            session.commit()
            return project_detail(session, project)
    except (SQLAlchemyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=503, detail="Project portfolio database is unavailable.") from exc


@app.get("/projects", response_model=list[ProjectSummary])
def get_projects() -> list[ProjectSummary]:
    """List projects with latest assessment metadata only."""

    try:
        with session_scope() as session:
            return list_projects(session)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Project portfolio database is unavailable.") from exc


@app.get("/projects/{project_id}/runs", response_model=list[AssessmentRunSummary])
def get_project_runs(project_id: str) -> list[AssessmentRunSummary]:
    """List immutable assessment-run summaries in reverse chronological order."""

    try:
        with session_scope() as session:
            project = project_by_reference(session, project_id)
            if project is None:
                raise HTTPException(status_code=404, detail="Project not found")
            return project_runs(session, project.id)
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Project portfolio database is unavailable.") from exc


@app.get("/projects/{project_id}", response_model=ProjectDetail)
def get_project(project_id: str) -> ProjectDetail:
    """Return one project and its current submitted context."""

    try:
        with session_scope() as session:
            project = project_by_reference(session, project_id)
            if project is None:
                raise HTTPException(status_code=404, detail="Project not found")
            return project_detail(session, project)
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Project portfolio database is unavailable.") from exc


@app.get("/runs/{run_id}", response_model=AssessmentRunResponse)
def get_run(run_id: str) -> AssessmentRunResponse:
    """Return one stored InterlockResult snapshot for historical reopening/reporting."""

    try:
        with session_scope() as session:
            run = run_by_id(session, run_id)
            if run is None:
                raise HTTPException(status_code=404, detail="Assessment run not found")
            return run_response(run)
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Project portfolio database is unavailable.") from exc


def _rag_registry_path() -> Path:
    return PROJECT_ROOT / "data" / "rag_processed" / "document_registry.json"


def _load_rag_documents() -> list[RAGDocument]:
    registry_path = _rag_registry_path()
    if not registry_path.is_file():
        raise HTTPException(
            status_code=404,
            detail="Module 5A policy corpus has not been built; run the RAG build command first",
        )
    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    return [RAGDocument.model_validate(item) for item in payload.get("documents", [])]


@app.get("/rag/status")
def rag_status() -> dict:
    """Return read-only Module 5A corpus metadata, if it has been built."""

    report_path = PROJECT_ROOT / "data" / "rag_processed" / "build_report.json"
    if not report_path.is_file():
        return {"status": "not_built", "module": "5A"}
    return json.loads(report_path.read_text(encoding="utf-8"))


@app.get("/rag/documents")
def rag_documents(
    source_class: SourceClass | None = Query(default=None),
    document_status: DocumentStatus | None = Query(default=None),
    retrieval_eligible: bool | None = Query(default=None),
) -> dict:
    """List Module 5A document metadata without exposing corpus text."""

    documents = _load_rag_documents()
    if source_class is not None:
        documents = [document for document in documents if document.source_class == source_class]
    if document_status is not None:
        documents = [document for document in documents if document.document_status == document_status]
    if retrieval_eligible is not None:
        documents = [document for document in documents if document.retrieval_eligible == retrieval_eligible]
    return {"count": len(documents), "documents": [document.model_dump(mode="json") for document in documents]}


@app.get("/rag/documents/{document_id}")
def rag_document(document_id: str) -> dict:
    """Return one Module 5A document metadata record."""

    document = next((item for item in _load_rag_documents() if item.document_id == document_id), None)
    if document is None:
        raise HTTPException(status_code=404, detail="RAG document not found")
    return document.model_dump(mode="json")


@app.post("/rag/search")
def rag_search(request: RetrievalRequest) -> dict:
    """Run read-only Module 5B retrieval without generating an answer."""

    try:
        return search_index(PROJECT_ROOT, request)
    except IndexNotBuiltError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except StaleIndexError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
