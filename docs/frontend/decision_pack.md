# Module 10 — INTERLOCK Decision Pack frontend

Module 10 keeps the existing Streamlit frontend and gives it a customer-facing
journey around the real `POST /interlock/run` response:

```text
Home -> New Assessment -> Run INTERLOCK -> Decision Pack
                                      \-> Evidence / Methodology
```

## Page structure

- **Home** introduces INTERLOCK and Canavan Atlantic, with a rights-safe CSS
  landscape/topographic hero treatment and two real navigation CTAs.
- **New Assessment** groups the existing project fields into Project,
  Location, Power & energy, and Project information. Blank numeric values remain
  `None` and are never converted to zero.
- **Decision Pack** maps `InterlockResult` to an executive summary, key
  findings, material unknown themes, dependencies, contradictions, human
  review, next action plan, evidence sources, and technical details.
- **Evidence** presents source classes and customer-facing citations, with
  Module 4B, Module 5B, and individual Module 6–8 endpoint tools in a
  Developer / debug expander.
- **Methodology** explains the evidence, uncertainty, provenance, and review
  boundaries without making a project decision.

## Visual language

The local stylesheet uses deep navy (`#062C3D`), brand teal (`#167A74`),
turquoise (`#00A89D`), white, and restrained pale blue/teal surfaces. It uses
system sans-serif fallbacks with Montserrat preferred when already available;
no font binaries or remote images are committed. Rights-cleared hero artwork
can be added under `frontend/assets/` later.

## InterlockResult mapping

The result page consumes only fields returned by the backend:

- `project_context`, `generated_at`, and `run_id` identify the assessment;
- `workflow_status`, `requires_human_review`, `stage_status`, and safe failure
  fields drive status presentation;
- `explanation_result` supplies the executive summary, findings, unknown themes,
  next actions, and customer-facing citations;
- `assessment_result` supplies structured dependencies;
- top-level `human_reviews` supplies grouped specialist review requests;
- `evidence_bundle` supports source labels and expandable traceability.

`REQUIRES_HUMAN_REVIEW` is presented as a completed automated workflow that
still needs accountable professional review. `FAILED` and `PARTIAL` are shown
as technical workflow problems. `UNKNOWN` is displayed as uncertainty, never as
a failure or a negative conclusion.

## Review, provenance, and drill-down

Human reviews are grouped for presentation by specialist role and domain while
retaining every review ID and evidence ID in the expanded content. Source
labels translate internal provenance into customer-safe labels: Developer
provided, Public / GIS evidence, Project evidence, Authoritative policy, and
Supporting evidence. Customer-facing citations are shown first; full record
IDs and source classes remain in supporting evidence and Technical details.

## Failure and loading states

The assessment form uses a Streamlit status block with descriptive, non-
percentage progress messages while the backend runs. It never claims an exact
percentage. Backend failures show a short controlled message and do not expose
stack traces, filesystem paths, environment values, API keys, or exception
objects.

## Manual acceptance

1. Run `docker compose up --build` or start FastAPI and Streamlit locally.
2. Open <http://localhost:8501> and verify Home branding and the primary CTA.
3. Open New Assessment, leave optional numeric fields blank, and verify the
   unknown-preserving message.
4. Run a normal or Herbata Early assessment and verify the Decision Pack,
   human-review state, six unknown themes where present, action plan, and
   source labels.
5. Open Evidence and verify customer-facing citations plus the debug expander.
6. Exercise a mocked failure and confirm only the controlled failure panel is
   shown.
