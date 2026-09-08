# Herbata project evidence

This is a separate Module 6 project-evidence layer for the `benchmark-herbata-naas`
project. It is not part of the Module 5 policy corpus. Source PDFs are downloaded
only from the finite allow-list in `backend/app/services/project_evidence/catalog.py`
and remain local under `source_documents/`; they are not committed to Git.

Use the downloader and processor from the repository root:

```powershell
& '.venv\Scripts\python.exe' scripts/project_evidence/download_herbata.py --project-root .
& '.venv\Scripts\python.exe' -m backend.app.services.project_evidence.processing --project-root .
```

Generated registry, pages, chunks, candidate facts, extraction report, and benchmark
theme manifest are written below `data/project_evidence_processed/herbata/`. Rights
remain `UNKNOWN_REUSE` and every project-document record requires human review.

The early Evidence Agent mode includes project-input benchmark documents but excludes
the `benchmark_only` validation set. Validation mode explicitly opts into the latter.
