# INTERLOCK Evidence Agent (Module 6)

The Evidence Agent assembles one provenance-preserving `EvidenceBundle` for a
`ProjectContext`. It gathers evidence and records gaps; it does not assess
viability and never produces Advance, Hold, Reconfigure, or Stop decisions.

## Input and output

The service accepts the shared `ProjectContext` contract. It reuses
`source_project_input` when present and otherwise adapts the canonical context
back to the existing Module 2 `ProjectInput` without converting missing values
to zero.

It returns the shared `EvidenceBundle`, containing:

- developer, deterministic GIS, structured project-document, and RAG evidence
  records;
- domain summaries and provenance counts;
- explicit retrieval gaps and missing evidence;
- evidence-supported dependencies;
- safe potential contradictions requiring human review;
- human-review requests, warnings, and structured citations.

The bundle has no final project decision or recommendation field.

## Tools and services called

`DeterministicEvidenceAgent.run()` calls only existing deterministic services:

1. Module 3 `project_input_to_evidence_ledger()` for developer evidence;
2. Module 4B `evaluate_site()` for public/GIS evidence;
3. Module 5B `search_index()` for authority-aware policy retrieval.

Structured project-document evidence may be supplied in
`ProjectContext.developer_inputs` under `evidence_records`,
`project_evidence`, or `uploaded_evidence`. This is already-structured input;
Module 6 performs no document extraction and makes no LLM call.

The API endpoint is:

```text
POST /agents/evidence
```

It accepts a `ProjectContext` JSON object and returns an `EvidenceBundle`.

## Retrieval query planning

The agent uses a small fixed, testable query plan for GRID, ENERGY, PLANNING,
BIODIVERSITY, ENVIRONMENT, WATER, and DATA_CENTRE_POLICY. Queries are
parameterised from the project type, power/MIC values, location, jurisdiction,
and local authority. Supporting sources are kept visible as supporting
evidence. Proposed, historical, superseded, restricted, and governance
material is excluded from normal current-policy evidence.

The existing Module 5B filters are used for jurisdiction and local authority.
For a Wicklow project, a Fingal local-authority result is not accepted. A
missing local source becomes a retrieval gap rather than an inference from
another county.

Identical retrieval results are deduplicated by document, page range,
chunk/curated-record ID, and finding text. Distinct evidence records are never
merged merely because their wording is similar.

## Evidence hierarchy and provenance

The agent preserves the origin of each record:

- `DEVELOPER_INPUT` keeps Module 3 `PROVIDED`, `UNKNOWN`, and
  `NOT_PROVIDED` states;
- `DETERMINISTIC_GIS` records are marked deterministic and preserve Module 4B
  source references and limitations;
- `RAG_RETRIEVAL` records preserve document ID, title, issuer, source class,
  document status, jurisdiction, chunk/record ID, and page-aware
  `CitationReference` data;
- `PROJECT_DOCUMENT` represents only already-structured project evidence;
- AI extraction is not part of this implementation and cannot be marked as
  deterministic by the shared record contract.

Primary current policy and supporting evidence remain distinguishable through
`source_class`, `authority_class`, `document_status`, and limitations.

## Unknown and missing evidence

Unknown, not-provided, and missing evidence are retained explicitly. Examples
include an absent MIC, unavailable coordinates for GIS, no current local
planning source, absent energisation proof, and an unproven renewable-asset
commissioning status. The agent does not interpret those gaps as project
failure and does not infer energisation from a grid agreement or commissioning
from a planned asset.

## Dependencies and contradictions

Dependencies are created only when records support them. Current examples are
the dependency between a grid agreement and separate energisation evidence,
and the dependency between a planned renewable asset and commissioning proof.

Distinct project-scope values remain in their original records. A mismatch
such as 100 MW versus 200 MW becomes a `PROJECT_SCOPE_MISMATCH` with linked
evidence IDs and mandatory human review; the Evidence Agent does not resolve
it.

## Human review

Unresolved high-consequence gaps, evidence records marked for review, and all
potential contradictions produce `HumanReviewRequest` records. Suggested roles
are mapped by domain: planning consultant, ecologist, grid engineer,
EIA/environmental consultant, or legal/regulatory specialist. The request
records a required handoff; it does not claim that a specialist review has
been completed.

## Streamlit demo

After project input validation, the UI exposes **Run Evidence Agent**. It
displays project evidence, public/GIS evidence, policy/regulatory evidence,
unknowns, missing evidence, dependencies, contradictions, human reviews, and
citations. It deliberately does not display a final decision.
