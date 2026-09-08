# Ireland Data Centre Site-Screening RAG Design

**Version:** 1.0  
**Knowledge verification date:** 2026-09-06  
**Scope:** Preliminary, non-binding legal and policy screening for a proposed data-centre development in Ireland. This package does not replace a formal determination by a System Operator, electricity-network operator, planning authority or professional adviser.

## 1. Design Objective

This package converts broad conclusions in the source research into **atomic, retrievable, source-traceable and updateable records**. Each record expresses one regulatory requirement, procedural fact, policy signal, quantitative threshold or claim requiring verification. This prevents legal duties, policy preferences and sector background from being blended into a single retrieval chunk. At retrieval time, the system should prioritise records supported by primary official sources and marked `in_force`, `active_policy` or `implemented_procedure`.

> A preliminary “pass” means only that the available evidence has not triggered a defined red flag. It is not a grid connection offer, planning consent, environmental permit, land-title opinion or financing feasibility conclusion.

| Layer | Purpose | Included material | Constraint on model output |
|---|---|---|---|
| Hard regulatory gate | Identifies conditions that prevent progression or further diligence on the current route | CRU connection duties, thresholds and System Operator accommodation | If unmet, return `STOP / do not commit further development expenditure` and specify missing evidence |
| Conditional eligibility rule | Identifies project conditions that must be delivered | Dispatchable generation or storage, renewable electricity and application evidence | Return `CONDITIONAL / requirements outstanding`; never state that approval has been received |
| Location and planning signal | Ranks the relative priority of locations | Network-constraint information, LEAP and Green Energy Parks | Return `PREFER`, `DEPRIORITISE` or `VERIFY`; do not describe a policy preference as a statutory prohibition |
| Operational compliance | Identifies obligations during design or operation | EU energy-performance reporting, KPIs and label status | Return a `COMPLIANCE WORKSTREAM` with the applicable threshold |
| Contextual information | Provides market or system context, not an approval decision | 2024 electricity-demand share and sector employment | May explain a result but cannot independently determine a screening outcome |
| Quality warning | Prevents unsupported or outdated claims contaminating the answer | Unverified claims in the source PDF | The model must disclose “requires verification” and must not rely on it as decisive evidence |

## 2. Retrieval Unit and Chunking Rules

The basic vector-indexing unit is one JSON object per line in `rag_records.jsonl`. Each record is English-only and stores an embedding-ready `content.retrieval_text` that contains regulatory terminology, material thresholds and location keywords. Rule records are deliberately compact to preserve conditional and threshold precision; the indicative target size is **250–650 English-word equivalents** per atomic record.

Records must not be split by PDF page, press-release heading or broad topic. Use the rules below.

| Rule | Implementation |
|---|---|
| One record, one conclusion | Keep the ≥10 MVA dispatchable-generation/storage duty separate from the 80% renewable-electricity duty |
| Preserve conditions of application | Each rule must state project type, MIC threshold, location condition, temporal condition and exception where relevant |
| Preserve legal status | Use `in_force`, `active_policy`, `implemented_procedure`, `proposal_or_consultation`, `context_only` or `needs_source_review` |
| Prefer primary sources | CRU, EirGrid, ESB Networks, Irish Government departments, EUR-Lex and the European Commission are primary sources; the user PDF is unverified background only |
| Separate fact from inference | Put the source-based duty in `content`; put the screening-operation rule and red flag in `screening_logic` |
| Make freshness explicit | Every record needs `effective_date` and `last_verified`; refresh status before re-embedding new or changed material |

## 3. Recommended Indexing and Filtering Configuration

In any vector database, such as pgvector, Qdrant, Pinecone, Weaviate or Chroma, use `content.retrieval_text` as the embedding field and retain the other fields as filterable metadata. Retrieval is English-oriented in this edition; the chat layer may translate an answer for an end user without changing the source text.

```text
embedding field: content.retrieval_text
metadata filter: jurisdiction, topic, legal_status, document_type,
                 quality.evidence_level, quality.review_required,
                 applicability.thresholds, last_verified
retrieval: top_k = 8; MMR diversification = on; rerank = on
mandatory filters: quality.review_required = false for final decision rationale
fallback: allow review_required = true only in a separate “research gap” section
```

For a question involving current grid capacity, constraints at a named substation, System Operator application status, permissions or site facts, the agent must request or retrieve current project evidence. A static RAG record cannot infer those facts. The latest EirGrid/ESB Networks location-constraint material should be treated as time-sensitive external evidence rather than permanent knowledge.

## 4. Screening Input Model

To allow a RAG record to trigger an explicit assessment path, the agent should collect the following minimum project facts. The correct result for an unknown field is `INSUFFICIENT_EVIDENCE`, not an estimate based on regional averages.

| Input field | Data type | Purpose |
|---|---|---|
| `site_location` | Eircode, coordinates, county/locality and proposed connection point | Determines System Operator jurisdiction, network constraints and planning context |
| `requested_mic_mva` | Number | Determines the 1 MVA and 10 MVA CRU thresholds |
| `application_type` | `new`, `additional_capacity` or `existing` | Determines the rule set and application route |
| `energisation_target_date` | Date | Calculates the six-year renewable-electricity path and matches the rule in force at that date |
| `dispatchable_asset_plan` | Technology, MW/MVA, location, connection and market-participation plan | Tests the dispatchable-generation/storage requirement |
| `renewable_project_plan` | Project location, annual output, commissioning date, support status and contract | Tests additional Irish renewable electricity and the 80% threshold |
| `network_evidence_date` | Date and source | Prevents decisions based on stale capacity information |
| `land_and_planning_status` | Zoning, permissions, land control and environmental constraints | Supports the planning workstream; this package does not yet provide a complete planning-law analysis |
| `water_and_heat_plan` | Source, cooling and heat-reuse pathway | Supports EU energy-performance and sustainability reporting design |

## 5. Decision-Output Contract

Every answer must distinguish between the applicable rule, provided project facts and the agent’s preliminary inference. The recommended response format is:

```json
{
  "overall_status": "STOP | CONDITIONAL | VERIFY | INSUFFICIENT_EVIDENCE",
  "hard_gates": [
    {
      "record_id": "IE-DC-GRID-001",
      "status": "pass | fail | unknown | not_applicable",
      "evidence_used": ["..."],
      "reason": "...",
      "next_step": "..."
    }
  ],
  "conditions": [],
  "policy_signals": [],
  "compliance_workstreams": [],
  "research_gaps": [],
  "citations": []
}
```

## 6. Currency, Conflicts and Legal-Safety Controls

Irish data-centre connection policy and EU sustainability rules are time-sensitive. Resolve conflicts in the following order: **current legislation/regulatory decision > current System Operator procedure > government policy > official contextual statistic > unverified user-provided material > secondary commentary**. Every conflict must be reported as a `research_gap`; the agent must not silently choose the more favourable version.

The source PDF provides no underlying legal links. Its claims have been retained for traceability but this package replaces imprecise statements with verified official records. In particular, the production model must not present any of the following as certain conclusions: a “near-zero” connection probability for Dublin sites lacking existing contracts; a CPPA as the sole compulsory mechanism; an explicit CRU preference for biomethane; or a final EU electronic-label regime arising from a generic “Tech Sovereignty Package”. See `data/review_flags.jsonl`.

## 7. Source Hierarchy

| Source tier | Permitted in a final conclusion | Example |
|---|---|---|
| `primary` | Yes | CRU decision, EirGrid procedure, EUR-Lex regulation or formal Government policy |
| `user_provided` | No, unless verified against a primary source | The uploaded research matrix |
| `secondary` | Generally no; use only to discover leads | Law-firm or industry commentary |

## 8. Current Coverage and Gaps

This package covers the topics contained in the source research: **grid connection, renewable electricity, dispatchable assets, locational constraints, national large-energy-user policy, EU data-centre energy-performance reporting and rating status**. It is not a complete development-permitting checklist. It does not yet systematically cover planning consent, environmental impact assessment, water abstraction/discharge, building regulations, fire safety, noise, ecology, data protection, taxation or construction contracts. These should be added as separate RAG modules supported by primary materials from the relevant competent authorities before deployment as a full development-screening agent.

## 9. References

[1] [CRU, Large Energy Users Connection Policy, CRU/2025236, 12 December 2025](https://cruie-live-96ca64acab2247eca8a850a7e54b-5b34f62.divio-media.com/documents/CRU2025236_Large_Energy_User_connection_policy_decision_paper.pdf)  
[2] [CRU, New Electricity Connection Policy for Data Centres, 12 December 2025](https://www.cru.ie/about-us/news/the-cru-publishes-its-decision-on-new-electricity-connection-policy-for-data-centres/)  
[3] [EirGrid, Demand Connections and Data Centre Connection Offer Process and Policy Version 3](https://www.eirgrid.ie/industry/becoming-customer/demand-connections)  
[4] [Department of Enterprise, Tourism and Employment, Large Energy User Action Plan announcement, 13 January 2026](https://enterprise.gov.ie/en/news-and-events/department-news/2026/january/20260113.html)  
[5] [Commission Delegated Regulation (EU) 2024/1364, EUR-Lex](https://eur-lex.europa.eu/eli/reg_del/2024/1364/oj/eng)  
[6] [European Commission, Energy performance of data centres](https://energy.ec.europa.eu/topics/energy-efficiency/energy-efficiency-targets-directive-and-rules/energy-efficiency-directive/energy-performance-data-centres_en)  
[7] [European Commission, Rating scheme for data centres in the EU, 27 March 2026](https://energy.ec.europa.eu/news/rating-scheme-data-centres-eu-commission-launches-call-feedback-2026-03-27_en)
