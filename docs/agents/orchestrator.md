# Module 9 — Controlled INTERLOCK Orchestrator

Module 9 composes the existing deterministic agents in one request-scoped,
fixed-order workflow:

```text
ProjectContext
  -> Evidence Agent
  -> EvidenceBundle
  -> Assessment Agent
  -> AssessmentResult
  -> Explanation Agent
  -> ExplanationResult
  -> InterlockResult
```

The implementation is `backend/app/agents/orchestrator.py` and the API entry
point is `POST /interlock/run`. The individual agent endpoints remain
available for debugging and integration compatibility.

## Execution rules

- Evidence, Assessment, and Explanation run exactly once and in that order.
- The orchestrator passes the existing bundle and assessment objects through
  the existing request contracts; it does not duplicate their logic.
- Benchmark project documents are excluded by default and can be enabled
  explicitly with `include_benchmark_documents=true`.
- There is no autonomous loop, web search, RAG query, LLM call, score, or
  `ADVANCE`/`HOLD`/`RECONFIGURE`/`STOP` decision in Module 9.
- State is request-scoped. No mutable workflow state is shared between runs.

## Failure and review handling

The same `InterlockResult` contract is returned for success and controlled
stage failure. A failed Evidence stage returns no fabricated bundle and skips
the downstream stages. Assessment failure preserves the evidence bundle;
Explanation failure preserves both prior outputs. Stage status, bounded error
text, record/finding counts, timings, and `failure_stage` explain what
happened without exposing stack traces or secrets.

Domain-level `UNKNOWN` and partial evidence remain valid pipeline inputs. A
completed run with review requests is marked `REQUIRES_HUMAN_REVIEW` and
exposes the structured requests; the orchestrator never treats review as
approval.

## Example

```powershell
$context = Get-Content .\tests\fixtures\agents\herbata_project_context.json -Raw
Invoke-RestMethod -Method Post `
  -Uri http://localhost:8000/interlock/run `
  -ContentType 'application/json' `
  -Body $context
```

The Streamlit application exposes the same operation through **Run
INTERLOCK**, with benchmark validation opt-in in the existing project-evidence
mode selector.
