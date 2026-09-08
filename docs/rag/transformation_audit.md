# Transformation Audit: Source Matrix to RAG Records

**Audit date:** 2026-09-06  
**Source material:** `sources/user_provided_ireland_data_centre_screening_matrix.pdf`  
**Method:** Each statement in the source matrix has been mapped to either a verified production record, a contextual-only record, or a source-quality flag. Only rules with a primary official source appear in the production evidence layer of `rag_records.jsonl`.

## Audit Conclusion

The source PDF identifies the correct areas of enquiry: grid capacity, dispatchable resources, renewable electricity, locational policy and EU energy performance are all material to early feasibility of an Irish data-centre project. The final CRU decision requires more granular screening by MIC and location for new connection applications; projects at or above 10 MVA require associated dispatchable generation and/or storage, while qualifying projects must also meet an additional-Irish-renewables requirement.[1] Several source statements, however, present a policy signal, proposal or project assumption as a certain legal conclusion. Those statements have been removed from the production rules and separately flagged.

| Source topic or claim | Transformation result | Production treatment | Rationale |
|---|---|---|---|
| Data centres consumed 22% of national metered electricity in 2024 | `IE-DC-CONTEXT-001` | Context only | The CRU’s official page confirms that data centres represented 22% of national electricity demand in 2024. That figure cannot replace a site-specific capacity assessment.[2] |
| PR6 prevents uncontracted Dublin projects to 2030; connection probability is near zero | `FLAG-001` | Must not be used as a rule | The current CRU decision requires a constrained/unconstrained assessment of the specific application location and leaves accommodation to the System Operators; it does not support a fixed connection probability.[1] |
| Strategic Green Energy Parks serve projects in the hundreds of MW | `IE-DC-PLAN-001` + `FLAG-007` | Policy-ranking signal | LEAP supports co-location of large energy users with indigenous renewable resources, but the official announcement does not establish the source claim’s project scale or legally protected park status.[3] |
| A CPPA is mandatory to bind new sites to renewable energy | `IE-DC-RENEW-001` + `FLAG-002` | Replace with additionality, location, 80% annual demand and six-year path | The CRU requires additional renewable electricity generated in Ireland but permits direct development or contracting with other parties; it does not make a CPPA the sole route.[1] |
| 5.7 TWh biomethane target | `IE-DC-BIO-001` | Policy context | Ireland’s National Biomethane Strategy commits the Government to support delivery of up to 5.7 TWh of indigenously produced biomethane by 2030; it is not a direct electricity-connection condition for a data centre.[4] |
| The CRU expressly prefers indigenous biomethane for data-centre backup generation | `IE-DC-GAS-001` + `FLAG-003` | Must not be used as a rule | CRU/2025236 states that no new decision on gas-network connections was made in that review. Fuel and gas diligence must be separated from the electricity-connection workstream.[1] |
| The EU Tech Sovereignty Package was formally adopted on 2026-06-03 | `FLAG-004` | Must not be used as a rule | No verifiable legal identifier is provided. Regulation 2024/1364 is a first-phase reporting/KPI regulation and cannot support this unreferenced claim.[5] |
| Mandatory energy-efficiency rating and electronic labels are already generated automatically | `EU-DC-EFF-002` + `FLAG-005` | Legal-status watch item | The Commission’s March 2026 notice describes electronic labels as part of a second-stage draft; a final Official Journal text is needed before it is represented as an in-force obligation.[6] |
| Low-efficiency legacy infrastructure will be phased out | `FLAG-006` | Future-policy monitoring only | The Commission states that a future energy-efficiency package will launch work on minimum performance standards. The reviewed material does not establish an in-force phase-out measure.[7] |
| Technology-sector GVA, employment, global investment and global electricity-use metrics | `FLAG-009` | Require source before contextual use | The source PDF supplies no statistical methodology or link. Such data must never trigger a grid or permitting pass/fail conclusion. |
| A 2026–2027 rating rollout and a 2028+ NEDS/flexibility tariff | `FLAG-008` and related flags | Must not be used in a compliance calendar | The source material supplies no primary source. The reviewed CRU decision and DETE LEAP announcement do not verify the programme name, timetable or tariff arrangement. |

## Evidence Priority in Production Answers

The agent must retrieve production records with legal status `in_force`, `active_policy` or `implemented_procedure` first. For locational capacity, a specific connection configuration and current procedure, the static record identifies the right questions but does not supply the final fact. EirGrid has published a data-centre connection process, technical assessment and constrained-area material aligned to CRU/2025236; the current version must be refreshed for each case screening.[8]

> If a source statement conflicts with a primary source, the agent must cite the primary source and identify the source statement as requiring verification. It must not use the source matrix to support a simpler or more favourable conclusion.

## References

[1] [CRU, Large Energy Users Connection Policy, CRU/2025236](https://cruie-live-96ca64acab2247eca8a850a7e54b-5b34f62.divio-media.com/documents/CRU2025236_Large_Energy_User_connection_policy_decision_paper.pdf)  
[2] [CRU, New Electricity Connection Policy for Data Centres](https://www.cru.ie/about-us/news/the-cru-publishes-its-decision-on-new-electricity-connection-policy-for-data-centres/)  
[3] [DETE, Large Energy User Action Plan announcement](https://enterprise.gov.ie/en/news-and-events/department-news/2026/january/20260113.html)  
[4] [Government of Ireland, National Biomethane Strategy](https://www.gov.ie/en/department-of-climate-energy-and-the-environment/publications/national-biomethane-strategy/)  
[5] [EUR-Lex, Commission Delegated Regulation (EU) 2024/1364](https://eur-lex.europa.eu/eli/reg_del/2024/1364/oj/eng)  
[6] [European Commission, Rating scheme for data centres in the EU](https://energy.ec.europa.eu/news/rating-scheme-data-centres-eu-commission-launches-call-feedback-2026-03-27_en)  
[7] [European Commission, Energy performance of data centres](https://energy.ec.europa.eu/topics/energy-efficiency/energy-efficiency-targets-directive-and-rules/energy-efficiency-directive/energy-performance-data-centres_en)  
[8] [EirGrid, Demand Connections / Data Centre Connection Offer Process and Policy Version 3](https://www.eirgrid.ie/industry/becoming-customer/demand-connections)
