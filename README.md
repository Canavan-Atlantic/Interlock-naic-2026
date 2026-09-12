# INTERLOCK - Canavan Atlantic / NAIC 2026

INTERLOCK is an early-stage decision-support platform for data-centre development. Its long-term purpose is to help a developer understand whether a development proposition is credible enough to progress, what could stop or delay it, what remains unknown, and what needs to happen next.

## Current scope: Modules 1–12

Module 1 proves that a Streamlit frontend can communicate with a FastAPI backend and that both services can run with Docker Compose. Module 2 adds the structured developer project-input workflow. Module 3 converts that input into an in-memory evidence ledger. Module 4A adds deterministic raw-data inventory, validation, cleaning, provenance, and spatial standardisation. Module 4B adds deterministic site-level evidence queries over those processed outputs while retaining the Module 3 ledger and explicit limitations. Module 5A creates a deterministic, provenance-aware policy knowledge-base foundation. Module 5B adds authority-aware hybrid retrieval over that processed corpus without answer generation or project decisions.

It includes:

- a FastAPI `GET /health` endpoint;
- a Streamlit landing page that checks backend connectivity;
- a Streamlit project-input form with transparent missing-information display;
- an initial evidence ledger showing provenance, state, confidence, and review status;
- a raw-data registry with stable IDs, file hashes, source metadata, and quality findings;
- deterministic processors for configured CSV, GeoJSON, ZIP shapefile, and Excel sources;
- EPSG:2157 standardisation for processed spatial outputs;
- a deterministic Module 4B site-evidence service using the processed registry;
- SAC, SPA, flood, planning, SMR zone, groundwater, karst, and contextual grid evidence;
- explicit UNKNOWN results for tabular-only zoning and REGISTERED_ONLY water/policy documents;
- a `POST /evidence/site` endpoint and a simple Streamlit public-data evidence preview;
- separate backend and frontend Dockerfiles;
- deterministic Pydantic validation for project input;
- deterministic conversion of project input into evidence records;
- a Module 5A document registry, authority/status metadata model, page-aware extraction, curated-record preservation, and deterministic provenance-aware chunks;
- a Module 5B local BM25/optional-embedding retrieval index with authority/status filtering, exact citations, stale-index detection, and a read-only search endpoint;
- automated health, project-input, evidence-ledger, registry, and processing tests.

Module 6.0 adds a separate deterministic project-evidence pipeline and Evidence
Agent integration. The Herbata benchmark uses a finite official-document
allow-list, keeps source PDFs local, writes project-scoped page/chunk/fact
artifacts outside the policy RAG directories, and marks all project-document
evidence as untrusted and human-review-required. It does not add scoring,
recommendations, answer generation, or Module 11 validation.

Raw source files under `data/raw/` are immutable. Generated manifests and processed outputs are written under `data/processed/`. Modules 4A and 4B do not call external services, make site decisions, score sites, or persist data in a database.

EirGrid policy/technical PDFs and Uisce Éireann capacity-register PDFs remain in their existing `data/raw/` locations and are referenced by Module 5A without duplication. Module 5A does not interpret policy, call OpenAI, create embeddings, perform semantic retrieval, or produce recommendations. Module 4B does not call OpenAI, RAG, agents, or external zoning services, and it produces no site score or recommendation.

## Module 5A — Verified Policy Knowledge Base Foundation

Module 5A builds an auditable policy corpus before retrieval or AI is introduced. It records each configured PDF, DOCX, curated JSONL source, and archive package with its SHA-256, source path, authority classification, status, jurisdiction, issuer where known, dates/version where known, retrieval eligibility, review restrictions, duplicate relationships, extraction status, and limitations. Unknown metadata remains `null` or `UNKNOWN`; it is not guessed.

The authority model is deliberately separate from legal interpretation:

- `PRIMARY` is eligible by default when it is current, relevant source material.
- `CURATED` records remain atomic and preserve their original source references and review flags.
- `SUPPORTING_PUBLIC_BODY`, `SUPPORTING_INDUSTRY`, and `SUPPORTING_RESEARCH` are supporting context; industry submissions are never primary authority.
- `GOVERNANCE` is excluded from normal site-assessment policy corpus processing.
- `RESTRICTED` and `ARCHIVE` sources are registered for audit but are not active retrieval sources or chunks.

The source library is under `data/rag/`. Official EirGrid and Uisce Éireann PDFs remain referenced from `data/raw/grid/` and `data/raw/water/`. Generated Module 5A outputs are written separately under `data/rag_processed/`, including `document_registry.json`, `chunks.jsonl`, `curated_records.jsonl`, `curated_review_flags.jsonl`, `no_text_pages.json`, `review_flag_audit.json`, `primary_source_quality.json`, `build_report.json`, and per-document extraction provenance. These permitted project datasets and generated artifacts are included in the private GitHub baseline and remain excluded from the Docker build context. The local `data/rag/restricted/` directory is intentionally withheld pending owner permission.

PDF chunks retain exact page ranges and structured citation metadata. DOCX chunks use heading/paragraph or table provenance and do not fabricate page numbers. No OCR is performed in Module 5A. Archive, restricted, governance, metadata-only curated files, and duplicate active sources do not create active chunks.

Run the Module 5A commands from the project root:

```powershell
& '.\.venv\Scripts\python.exe' -m backend.app.services.rag inventory --project-root .
& '.\.venv\Scripts\python.exe' -m backend.app.services.rag build --project-root .
& '.\.venv\Scripts\python.exe' -m backend.app.services.rag validate --project-root .
```

These commands perform deterministic file inspection and extraction only. Module 5A makes no model, OpenAI, embedding, semantic-search, agent, scoring, PASS/FAIL/HOLD, or recommendation calls. Module 5B consumes these outputs and does not re-read source PDFs.

## Module 5B — Authority-aware hybrid retrieval

Module 5B retrieves evidence for a policy or regulatory question; it does not generate a natural-language answer, make a legal conclusion, score a project, or produce PASS/FAIL/HOLD decisions. The index reads only `data/rag_processed/chunks.jsonl` and `data/rag_processed/curated_records.jsonl`.

The local index stores `records.jsonl`, a deterministic BM25 lexical index, an optional `embeddings.npy` sidecar, and `manifest.json` under `data/rag_index/`. Exact duplicate active text is indexed once. The manifest records the corpus hash, indexed counts, lexical constants, embedding provider/model/dimension, and whether semantic retrieval is available. Searches refuse to run against a stale index.

Retrieval uses lexical candidates plus optional semantic candidates and merges them with documented Reciprocal Rank Fusion (`RRF_K=60`, candidate multiplier `5`). Authority is applied as an eligibility and ordering layer after candidate retrieval: current PRIMARY evidence is returned first, trusted CURATED records are separate, SUPPORTING_PUBLIC_BODY evidence is secondary, and industry/research evidence requires `include_supporting=true`. Proposed, historical, and superseded PRIMARY material requires `include_historical=true`. GOVERNANCE is limited to Responsible AI/governance queries; RESTRICTED and ARCHIVE are never returned.

Jurisdiction and local-authority filters are deterministic. Ireland queries may include EU sources where applicable. A Wicklow/local-planning query excludes Fingal local-authority material and returns an explicit local-policy corpus gap when no Wicklow source is present. Workflow and domain filters use Module 5A metadata; records with unknown applicability are retained unless another safety rule excludes them.

Embedding configuration is environment-based:

```powershell
$env:INTERLOCK_RAG_EMBEDDING_PROVIDER = "openai"
$env:INTERLOCK_RAG_EMBEDDING_MODEL = "text-embedding-3-small"
$env:OPENAI_API_KEY = "..."
```

If `OPENAI_API_KEY` or the OpenAI SDK is unavailable, the index still builds and searches lexically, and the response reports semantic retrieval as unavailable. Tests use the deterministic mock provider and never call OpenAI. Secrets are not logged.

Build, search, and evaluate the index from the project root:

```powershell
& '.\.venv\Scripts\python.exe' -m backend.app.services.rag index --project-root .
& '.\.venv\Scripts\python.exe' -m backend.app.services.rag search --project-root . --query "What connection requirements apply to a large data centre in Ireland?"
& '.\.venv\Scripts\python.exe' -m backend.app.services.rag eval --project-root .
```

The read-only API endpoint is `POST /rag/search`. It accepts the canonical query, workflow, domains, jurisdiction/local-authority scope, historical/supporting switches, and result limits. It returns separate `authoritative_results`, `curated_results`, `supporting_results`, and `historical_results`, together with citation/provenance metadata, retrieval ranks, comparison candidates, warnings, and evidence gaps. The Streamlit developer section exposes the same retrieval controls without adding answer generation.

## Module 6.0 — Isolated project evidence

Herbata project documents are deliberately separate from Module 5 policy evidence:

- source PDFs: `data/project_evidence/benchmarks/herbata/source_documents/` (local and git-ignored);
- processed registry/pages/chunks/facts/reports: `data/project_evidence_processed/herbata/`;
- optional project index metadata: `data/project_evidence_index/herbata/`;
- authoritative policy artifacts remain under `data/rag_processed/` and `data/rag_index/`.

Run the finite download and deterministic extraction from the project root:

```powershell
& '.\.venv\Scripts\python.exe' scripts/project_evidence/download_herbata.py --project-root .
& '.\.venv\Scripts\python.exe' scripts/project_evidence/build_herbata.py --project-root .
```

The Evidence Agent endpoint accepts `include_project_documents=true` and
`include_benchmark_documents=false` (the early-evidence default). The Streamlit
Evidence Agent panel exposes Normal project, Herbata Early Evidence, and Herbata
Validation modes. Project-document records retain source URLs/page citations and
cannot masquerade as authoritative policy.

## Module 7 — Deterministic constraint assessment

Module 7 consumes an existing Evidence Agent bundle through the shared
`AssessmentRequest` contract and returns an `AssessmentResult`. It preserves
unknowns, lifecycle distinctions, source authority, dependencies,
contradictions, and selective human review. It does not gather new evidence,
call GIS/RAG, use an LLM, calculate an equal-weight score, or produce an
Advance/Hold/Reconfigure/Stop decision.

The backend endpoint is `POST /agents/assessment`. The Streamlit developer
flow runs it only after the Evidence Agent and displays findings grouped by
domain, with supporting evidence IDs and citations retained in the input
bundle.

## Module 8 — Deterministic explanation

Module 8 consumes an existing `AssessmentResult` and produces a concise,
evidence-grounded `ExplanationResult`. It preserves `UNKNOWN`, `CONDITIONAL`,
and `CONSTRAINED` status, source distinctions, dependencies, contradictions,
specialist reviews, evidence IDs, and existing citations. It does not gather
evidence, reinterpret policy, calculate a score, make a recommendation, or
produce an `ADVANCE`, `HOLD`, `RECONFIGURE`, or `STOP` decision.

The backend endpoint is `POST /agents/explanation`. The Streamlit developer
flow now runs Evidence Agent → Assessment Agent → Explanation Agent and shows
the executive explanation, prioritised findings, consolidated material-unknown
themes, dependencies, contradictions, human reviews, consolidated next
actions, and customer-facing citations. Detailed unknowns, actions, evidence
IDs, and complete citations remain available through the provenance
drill-down. The additive explanation fields preserve old valid contract
payloads.

## Module 9 — Controlled INTERLOCK Orchestrator

Module 9 provides the fixed, deterministic `Evidence → Assessment →
Explanation` workflow through `POST /interlock/run`. It returns the existing
`InterlockResult` composition with stage status, timings, operational counts,
preserved provenance, and human-review requests. Stage failures preserve
successful upstream outputs and never fabricate missing evidence. Benchmark
project documents remain excluded by default; enable them explicitly for the
existing Herbata validation mode. The Streamlit application exposes the same
workflow through **Run INTERLOCK**. Module 9 adds no RAG calls, LLM calls,
scoring, recommendations, or final project decision.

## Module 10 — Decision Pack frontend

Module 10 adds the polished Streamlit journey: Home, New Assessment, Decision
Pack, Evidence, and Methodology. The primary assessment action calls
`POST /interlock/run` and renders the real `InterlockResult` as an evidence-led
development readiness pack. It keeps `UNKNOWN` distinct from failure, presents
human review as an accountable workflow state, distinguishes project evidence
from authoritative policy, and does not add scores, fabricated metrics, or
unsupported `ADVANCE`/`HOLD`/`RECONFIGURE`/`STOP` decisions.

The frontend uses a Canavan Atlantic-style white header, web navigation, dark
teal landscape hero, capability and approach sections, truthful capability
statements, and a compact footer. It uses the approved local hero asset at
`frontend/assets/interlock_hero.png` and the extracted Canavan Atlantic logos in
`frontend/assets/`. The supplied UI screenshot remains design reference only
and is never rendered as application content or a background.

Completed assessments can also be downloaded as a deterministic PDF report
from the stored `InterlockResult`; generating the report does not rerun the
backend assessment.

## Module 12 — Visual Decision Pack and assessment report

The Decision Pack now opens with a compact, result-driven domain-state visual
and truthful summary metrics for findings, unknown themes, dependencies,
contradictions, and professional reviews. A completed result can be downloaded
as a branded PDF containing the stored inputs, domain states, findings,
unknowns, traceability, citations, methodology, limitations, and provenance.
`UNKNOWN` remains explicit and non-alarmist, and no score or final project
decision is created by the frontend.

Run the frontend directly with:

```powershell
$env:INTERLOCK_API_BASE_URL = "http://localhost:8000"
py -m streamlit run frontend/app.py
```

The existing Module 4B and Module 5B developer tools remain available under
the Evidence page's Developer / debug tools expander.

## Prerequisites

- Docker Desktop with Docker Compose support;
- Python 3.10 or newer if running tests outside Docker.

## Private GitHub baseline and data setup

The private repository includes the permitted raw and processed project datasets, policy/RAG corpus, generated Module 5A outputs, and Module 5B index artifacts. Large files are stored with Git LFS. The restricted research PDF under `data/rag/restricted/` is intentionally not uploaded because owner permission has not been confirmed.

Clone the project and retrieve its LFS objects:

```powershell
git lfs install
git clone https://github.com/Canavan-Atlantic/Interlock-naic-2026.git
cd Interlock-naic-2026
git lfs pull
```

Create a Python environment and install dependencies:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -r requirements.txt
```

`.env.example` is included as a template, but `.env` files and API keys are never stored in GitHub. Provide `OPENAI_API_KEY` and the optional retrieval settings through each user's local environment when semantic retrieval is required:

```powershell
$env:OPENAI_API_KEY = "<your-key>"
$env:INTERLOCK_RAG_EMBEDDING_PROVIDER = "openai"
$env:INTERLOCK_RAG_EMBEDDING_MODEL = "text-embedding-3-small"
```

## Run with Docker

From the project directory in PowerShell:

```powershell
docker compose up --build
```

Open:

- Streamlit: <http://localhost:8501>
- FastAPI: <http://localhost:8000>
- FastAPI docs: <http://localhost:8000/docs>

The project-input endpoint is available at `POST http://localhost:8000/project-input/validate`.

The evidence-ledger endpoint is available at `POST http://localhost:8000/evidence/from-project`.

The deterministic site-evidence endpoint is available at `POST http://localhost:8000/evidence/site`. It accepts the validated project-input shape and requires latitude and longitude.

The frontend uses `INTERLOCK_API_BASE_URL=http://backend:8000` inside Docker so it can reach the backend service by its Compose service name.

During Docker Compose runs, the repository's local `./data` directory is mounted read-only into the backend container at `/data`. This keeps the raw and processed datasets out of the Docker image while allowing Module 4B to read `/data/processed/data_registry.json`.

Stop the services with:

```powershell
docker compose down
```

## Run tests

Create and activate a virtual environment if needed, then install the dependencies:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -r requirements.txt
py -m pytest
```

Module 4A tests use small temporary fixtures and do not depend on the large raw datasets.

## Run the Module 4A data registry

From the project root, create a raw-data inventory and JSON registry manifest without processing source files:

```powershell
py -m backend.app.services.data inventory --project-root .
```

To validate and process the configured local sources into `data/processed/`:

```powershell
py -m backend.app.services.data process --project-root .
```

The process command writes `data/processed/data_registry.json` plus Parquet/GeoParquet outputs where processing succeeds. Validation or processing failures remain visible in the registry and do not produce misleading output files. Large spatial sources may require substantial disk space and runtime.

## Run a Module 4B site evidence check

From the project root in PowerShell:

```powershell
& '.\.venv\Scripts\python.exe' -m backend.app.services.site_evidence check --project-root . --project-name "NAIC Test Data Centre" --project-stage "Early Feasibility" --site-address "Blanchardstown, Dublin 15" --latitude 53.3879 --longitude -6.3750
```

The command transforms the input from EPSG:4326 to EPSG:2157, resolves only `PROCESSED` outputs through `data/processed/data_registry.json`, and prints structured evidence, provenance, limitations, and per-domain timings. Optional deterministic grid filters are available with repeated `--grid-voltage-class` and `--grid-min-primary-kv` arguments.

Module 4B uses cached GeoParquet reads with projected bounding-box filtering for large sources. The reported timings are diagnostic only. Zoning is UNKNOWN until an official MyPlan geometry source is available; water/wastewater and EirGrid PDFs remain REGISTERED_ONLY and produce no site-specific claims. Grid results are contextual assets only, and public capacity is not treated as connection capacity. No AI, RAG, policy interpretation, score, suitability threshold, or recommendation is produced.

To run the Streamlit app and backend directly without Docker, start the backend in one PowerShell window:

```powershell
py -m uvicorn backend.app.main:app --reload --port 8000
```

Then start the frontend in another:

```powershell
$env:INTERLOCK_API_BASE_URL = "http://localhost:8000"
py -m streamlit run frontend/app.py
```

On the New Assessment page, **Load Demo Project** populates the verified
Blanchardstown NAIC demonstration inputs without starting a run. The inputs
remain editable and are submitted through the same validation and
`/interlock/run` path as a normal assessment.

## Directory structure

```text
Interlock-naic-2026/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py
│   │   └── schemas/
│   │       ├── __init__.py
│   │       ├── evidence.py
│   │       ├── project.py
│   │       └── site_evidence.py
│   │   └── services/
│   │       ├── __init__.py
│   │       ├── evidence.py
│   │       ├── site_evidence/
│   │       │   ├── __init__.py
│   │       │   ├── __main__.py
│   │       │   ├── base.py
│   │       │   ├── biodiversity.py
│   │       │   ├── flood.py
│   │       │   ├── grid.py
│   │       │   ├── ground.py
│   │       │   ├── heritage.py
│   │       │   ├── planning.py
│   │       │   ├── service.py
│   │       │   ├── water.py
│   │       │   └── zoning.py
│   │       └── data/
│   │           ├── __init__.py
│   │           ├── __main__.py
│   │           ├── processing.py
│   │           ├── registry.py
│   │           └── validation.py
│   └── Dockerfile
├── frontend/
│   ├── app.py
│   └── Dockerfile
├── tests/
│   ├── test_health.py
│   ├── test_evidence.py
│   ├── test_project_input.py
│   ├── test_data_registry.py
│   ├── test_data_processing.py
│   └── test_site_evidence.py
├── config/
│   └── data_sources.yaml
├── data/
│   ├── raw/
│   ├── processed/
│   ├── rag/
│   ├── rag_processed/
│   ├── rag_index/
│   └── demo/
├── docs/
├── .env.example
├── .gitignore
├── docker-compose.yml
├── requirements.txt
└── README.md
```

Permitted raw and generated data directories are included in this private baseline so teammates can reproduce Modules 1–5B. `data/rag/restricted/` remains local and is not committed. Docker continues to exclude raw, processed, and RAG data from image builds; Compose mounts the local `./data` directory read-only into the backend at `/data`.
