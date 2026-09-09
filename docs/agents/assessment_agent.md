# INTERLOCK Assessment Agent (Module 7)

The Assessment Agent converts one existing `EvidenceBundle` into the shared
`AssessmentResult` contract. It is a deterministic-first constraint
assessment layer. It does not collect evidence, call Module 4B, call Module
5B, use an LLM, search the web, or make a final project decision.

## Input and output

The agent accepts `AssessmentRequest`, containing a `ProjectContext` and the
already assembled `EvidenceBundle`. It returns `AssessmentResult` with:

- domain findings using the shared `AssessmentStatus` values;
- explicit constraints only where authoritative or deterministic evidence
  clearly supports them;
- material unknowns and evidence required next;
- evidence-supported dependencies copied from the bundle;
- human-review requests with preserved evidence IDs;
- warnings explaining the assessment boundary.

The contract intentionally has no score, recommendation, or
`ADVANCE`/`HOLD`/`RECONFIGURE`/`STOP` field.

## Deterministic assessment logic

The implementation groups existing records by the shared `Domain` enum and
keeps `UNKNOWN` and `NOT_PROVIDED` states unchanged. It creates conditional
findings for unresolved dependencies, lifecycle limitations, contextual GIS
assets, project-document-only evidence, and tested spatial layers whose
non-intersection does not establish absence of wider environmental risk.

An explicit `CONSTRAINED` finding requires a clear constraint phrase in
current authoritative policy or deterministic evidence. Missing evidence,
nearby assets, generic policy text, or a project-document assertion cannot
create a hard constraint.

## Authority and lifecycle boundaries

Current PRIMARY/CURATED policy evidence is authoritative policy context.
Deterministic GIS is authoritative only for the spatial test it actually
performed. Developer input and project documents retain their provenance and
cannot override authoritative policy. Project documents remain untrusted and
human-reviewable.

The agent preserves distinctions such as:

- connection agreement versus energisation;
- feasibility correspondence versus secured water connection;
- proposed/planned infrastructure versus commissioned/operational assets;
- planned renewable assets versus commissioned renewable assets;
- planning permission versus development readiness.

## Human review and contradictions

Existing bundle reviews are carried forward and related assessment escalations
are aggregated by normalized domain/reason. Evidence IDs are merged rather
than discarded, and high-consequence severity is preserved. Existing
`PotentialContradiction` records become conditional findings with their source
evidence IDs and remain human-review material; no contradiction is silently
resolved.

## API and developer UI

The backend exposes:

```text
POST /agents/assessment
```

The minimal Streamlit developer flow is sequential: run the Evidence Agent,
then run the Assessment Agent. Findings are grouped by domain and the UI
shows constraints, unknowns, dependencies, conditional contradiction
findings, human reviews, and evidence IDs. It does not display a final
customer decision.

## Boundary to later modules

Module 7 stops at structured assessment. Module 8 consumes these findings
through `ExplanationRequest` and turns them into controlled, evidence-traceable
explanations without changing their status. A future Orchestrator may compose
the workflow results. No equal-weight 0-100 score is used because a material
constraint must not be averaged away by unrelated positive evidence.
