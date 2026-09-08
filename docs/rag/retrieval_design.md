# Module 5B retrieval design

Module 5B is a read-only retrieval layer over the processed Module 5A corpus. It does not read source PDFs again, generate answers, interpret law, score projects, or call agents.

## Index inputs and safety gates

The index consumes only:

- `data/rag_processed/chunks.jsonl`
- `data/rag_processed/curated_records.jsonl`

Records must be retrieval eligible, must not require human review, and must not come from restricted, archive, governance, or duplicate sources. Flagged curated records are excluded. Exact duplicate active text is indexed once.

## Retrieval sequence

1. Resolve query metadata, including workflow, domains, jurisdiction, and inferred local authority.
2. Apply deterministic source eligibility and metadata filters.
3. Retrieve lexical BM25 candidates.
4. Retrieve semantic candidates when an embedding sidecar and provider are available.
5. Merge candidate lists using Reciprocal Rank Fusion:

   `fusion_score = 1 / (60 + lexical_rank) + 1 / (60 + semantic_rank)`

6. Group and order results by authority/status.
7. Return exact citations, source metadata, evidence gaps, warnings, and comparison candidates.

Current PRIMARY evidence is returned in `authoritative_results`. Trusted curated records are returned separately and cannot outrank PRIMARY evidence. Public-body, industry, and research evidence are returned in `supporting_results` under their inclusion rules. Proposed/historical/superseded PRIMARY evidence is returned only in `historical_results` when requested.

## Local authority safety

National Irish and EU sources may support an Irish query. Local-authority sources are only included when their `jurisdiction_detail` matches the requested or inferred authority. For Wicklow/Arklow queries, Fingal material is excluded and `NO_AUTHORITATIVE_LOCAL_SOURCE` is returned because the current corpus has no Wicklow local-authority source.

## Semantic providers

`EmbeddingProvider` supports OpenAI and a deterministic mock provider. OpenAI reads `OPENAI_API_KEY`, `INTERLOCK_RAG_EMBEDDING_PROVIDER`, and `INTERLOCK_RAG_EMBEDDING_MODEL`; it never receives authority metadata injected into the embedding text. If credentials or the SDK are unavailable, lexical BM25 search remains available and the response states that semantic retrieval is disabled.

## Staleness

`manifest.json` stores hashes for the two Module 5A index inputs. Search compares them before reading the index and returns a controlled stale-index error when either file changes.
