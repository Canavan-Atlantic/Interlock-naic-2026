# INTERLOCK Explanation Agent (Module 8)

The Explanation Agent converts one existing Module 7 `AssessmentResult` into
a concise, deterministic, evidence-traceable explanation. It is a controlled
presentation layer for developers, planning consultants, energy/infrastructure
consultants, and technical decision-makers.

## Boundaries

Module 8 does not gather evidence, call GIS or RAG, interpret policy
independently, resolve contradictions, calculate a score, make a
recommendation, or produce an `ADVANCE`, `HOLD`, `RECONFIGURE`, or `STOP`
decision. The future Module 9 orchestrator remains outside this module.

The agent preserves the assessment's `UNKNOWN`, `CONDITIONAL`, `CONSTRAINED`,
and `CLEAR` classifications. In particular:

- `UNKNOWN` is explained as insufficient evidence, not as a negative or a
  positive conclusion;
- `CONDITIONAL` remains potentially resolvable subject to further evidence or
  specialist review;
- constraints are copied from the assessment and cannot be invented by the
  explanation layer;
- contradictions remain visible and are not resolved by source preference;
- project documents remain distinguishable from authoritative policy,
  deterministic GIS, supporting evidence, and developer input.

## Input and output

The backend exposes:

```text
POST /agents/explanation
```

The request uses the shared `ExplanationRequest` contract. It always contains
`project_context` and `assessment_result`; an optional `evidence_bundle` lets
the agent resolve referenced evidence IDs to source provenance and structured
citations. The optional field preserves compatibility with callers that only
have the Module 7 result.

`ExplanationResult` contains:

- an executive summary;
- prioritised key findings and conditional issues;
- known facts with source-type labels;
- material unknowns and constraints;
- evidence-linked dependency explanations;
- visible contradiction explanations;
- de-duplicated specialist handoffs;
- next actions copied from assessment evidence requirements;
- referenced evidence IDs and existing structured citations;
- assessment warnings and Module 8 boundary warnings.

## Deterministic prioritisation

Findings are ordered by consequence and unresolvedness:

1. explicit constraints;
2. conditional issues, including material contradictions;
3. material unknowns;
4. unassessed items;
5. clear/supporting findings.

Every finding remains available as one concise summary item; lower-priority
items are not silently discarded. Detailed evidence records remain in the
Module 6 bundle rather than being repeated as a large evidence dump.

## Evidence grounding and citations

The agent only uses text already present in the assessment, its dependencies,
human reviews, and referenced evidence records. It does not infer completion,
capacity, approval, operational status, or absence of risk. When an evidence
bundle is supplied, only referenced non-benchmark records are used for
customer-facing facts, evidence IDs, and citations. Benchmark-only Herbata
records therefore cannot leak into the early-evidence explanation.

Existing `CitationReference` objects are copied without fabricated page,
section, or source locations. Evidence IDs are retained in material summary
items and the result-level evidence list.

## Dependencies, contradictions, and human reviews

Dependencies retain their status, description, evidence IDs, and assessment
evidence required next. Potential contradictions from the evidence bundle and
assessment findings that identify conflicting evidence or scope mismatch are
shown explicitly. Human reviews retain the recommended specialist role,
reason, review ID, and evidence IDs; duplicate role/domain/reason requests are
not repeated in the explanation.

## Streamlit debug flow

The developer UI now runs the functional sequence:

```text
Run Evidence Agent
        ↓
Run Assessment Agent
        ↓
Run Explanation Agent
```

It displays the executive explanation, key findings, constraints, conditional
issues, unknowns, dependencies, contradictions, human reviews, next actions,
and evidence IDs/citations. It remains a debug workflow and is not the final
Decision Pack frontend.
