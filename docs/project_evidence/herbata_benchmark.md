# Herbata project-evidence benchmark

Herbata is a deterministic Module 6 project-document benchmark identified by
`benchmark-herbata-naas`. Its evidence is deliberately isolated from the Module 5
policy RAG corpus:

- source PDFs: `data/project_evidence/benchmarks/herbata/source_documents/`
- processed artifacts: `data/project_evidence_processed/herbata/`
- optional project index metadata: `data/project_evidence_index/herbata/`
- policy artifacts remain under `data/rag_processed/` and `data/rag_index/`

The downloader uses a finite allow-list from the official Herbata volume 1 and
volume 2 listing pages. It records source URL, classification, retrieval time,
content hash, and local path. It does not crawl the site. Source PDFs are excluded
from Git; manifests and hashes are safe metadata for audit and reproducibility.

Module 6 uses deterministic PyMuPDF text extraction with no OCR, page-aware chunks,
and conservative candidate facts. A feasibility reference is not treated as a
secured connection; proposed, planned, applied-for, or permitted language is not
treated as commissioned or operational. Project documents are marked
`UNTRUSTED_PROJECT_DOCUMENT`, `trusted_as_policy=false`, and require human review.

The API endpoint remains evidence-only:

```text
POST /agents/evidence?include_project_documents=true&include_benchmark_documents=false
```

The default early mode excludes `benchmark_only` documents. Validation mode opts in
explicitly. No gold answers are stored in the benchmark manifest and no score,
recommendation, or Module 11 validation is produced.
