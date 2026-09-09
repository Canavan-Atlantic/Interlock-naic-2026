"""FastAPI entry point for the INTERLOCK backend."""

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query

from .agents.assessment import DeterministicAssessmentAgent
from .agents.evidence import DeterministicEvidenceAgent, EvidenceAgentOptions
from .schemas.agents import AssessmentRequest, AssessmentResult, EvidenceBundle, ProjectContext
from .schemas.evidence import EvidenceLedger
from .schemas.project import (
    ProjectInput,
    ProjectValidationResponse,
    find_missing_or_unknown,
)
from .schemas.site_evidence import SiteEvidenceResponse
from .services.evidence import project_input_to_evidence_ledger
from .services.site_evidence import SiteEvidenceOptions, evaluate_site
from .services.rag.models import DocumentStatus, RAGDocument, RetrievalRequest, SourceClass
from .services.rag.retrieval import IndexNotBuiltError, StaleIndexError, search_index


app = FastAPI(title="INTERLOCK API", version="0.1.0")
PROJECT_ROOT = Path(__file__).resolve().parents[2]


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
