# INTERLOCK shared agent contracts (Module 6.0)

Module 6.0 defines the versioned data contracts and lightweight interfaces that
future INTERLOCK agents may use. It does not implement agents, model calls,
investment decisions, scoring, or recommendations.

## Contract boundary

The canonical workflow is:

```text
ProjectContext
      |
      v
EvidenceAgent.run(ProjectContext)
      |
      v
EvidenceBundle -----> human review requests / provenance / gaps
      |
      v
AssessmentAgent.run(AssessmentRequest)
      |
      v
AssessmentResult ----> findings / constraints / dependencies / unknowns
      |
      v
ExplanationAgent.run(ExplanationRequest)
      |
      v
ExplanationResult --> facts / limits / dependencies / next actions / handoffs
      |
      v
InterlockResult (composition only; no final investment decision)
```

`backend/app/schemas/agents/` contains the contracts. `ProjectContext` adapts
the existing Module 2 `ProjectInput`; the agent-facing `EvidenceRecord`
extends the existing Module 3 record rather than replacing it. RAG citations
reuse Module 5A `CitationReference`, `Domain`, `Jurisdiction`, source class,
and document status models.

## Ownership and boundaries

- Module 2 owns developer-input validation and the original `ProjectInput`.
- Module 3 owns deterministic evidence capture and the base evidence record.
- Module 4B owns deterministic domain evidence calculations.
- Module 5A/5B own corpus provenance and retrieval citations.
- Module 6.0 owns the shared shapes that let the agents exchange those
  results without losing provenance.
- The Evidence, Assessment, and Explanation implementations use their
  existing contracts directly. Module 9 composes them through
  `InterlockResult` without changing lower-level evidence or assessment
  meaning.
- Future concrete agents own orchestration and interpretation only within
  these boundaries. They must not overwrite deterministic facts.
- Human specialists remain the authority for material, high-consequence, or
  contradictory matters. `PotentialContradiction` always requires human
  review, and `HumanReviewRequest` records the intended specialist role.

Missing numeric values are represented as `null`; no contract invents a zero.
Assessment workflow (`SITE_DISCOVERY`, `SITE_FEASIBILITY`, or
`POLICY_REGULATORY_INTELLIGENCE`) is separate from project lifecycle status
(`PRE_PLANNING`, `PLANNING`, `CONSTRUCTION`, and so on).

## Deterministic versus AI-derived evidence

Every agent-facing evidence record carries `created_by`, `deterministic`,
`verification_status`, and source metadata. Deterministic GIS records can be
identified as `DETERMINISTIC_GIS` with a deterministic-calculation source.
RAG records retain a structured `CitationReference`, including page and
section locators when available. AI-extracted records are explicitly marked
`AI_EXTRACTION` and are rejected if they attempt to claim deterministic
provenance.

The contracts contain facts, findings, constraints, unknowns, and explanations;
they deliberately contain no `decision`, score, recommendation, or investment
outcome field.

## Versioning

`AGENT_CONTRACT_VERSION` is currently `1.0`, and `InterlockResult.schema_version`
exposes that value. Additive changes should preserve the existing meaning of
fields. Breaking changes require a new contract version and fixture migration.

## Branch and implementation guide

Shared contract work belongs on `feature/shared-agent-contracts`. A future
agent implementation should:

1. depend on the protocols in `schemas.agents.interfaces`,
2. return the corresponding Pydantic contract models,
3. preserve evidence IDs and structured citations,
4. surface unknowns, gaps, contradictions, and human handoffs, and
5. keep model/provider code outside this contract package.

Recommended implementation branches are:

```text
feature/module6-evidence-agent
feature/module7-assessment-agent
feature/module8-explanation-agent
feature/module9-orchestrator
```

Each developer should start from an up-to-date main branch, create the named
feature branch, implement against the shared contracts, run the tests, push
the branch, and open a pull request. For example:

```text
git checkout main
git pull
git checkout -b feature/<branch>
```

No developer should make direct changes to `main`.

The synthetic fixtures in `tests/fixtures/agents/` are contract examples only;
they are not real policy evidence or project advice.
