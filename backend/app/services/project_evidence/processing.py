"""Deterministic extraction and artifact build for project-document evidence.

This module intentionally does not import or write the Module 5 policy index.
Project documents are source material supplied for a named project, not policy
authority.  PDF text extraction is page-aware, does not use OCR, and writes
the complete artifact set only after all documents have been processed.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any

from ...services.rag.models import CitationReference, Domain
from ..rag.service import _heading_for_text, _normalise_text, _text_windows
from .catalog import HERBATA_PROJECT_ID
from .models import (
    ProjectAssetStatus,
    ProjectDocument,
    ProjectDocumentClassification,
    ProjectEvidenceChunk,
    ProjectEvidenceFact,
    ProjectRightsStatus,
)


PROCESSED_ROOT = Path("data/project_evidence_processed")
INDEX_ROOT = Path("data/project_evidence_index")
_NUMBER = r"(?:\d[\d,]*(?:\.\d+)?)"


def _json_write(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")


def _jsonl_write(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(row, ensure_ascii=False, default=str) + "\n" for row in rows), encoding="utf-8")


def _parse_number(value: str) -> float:
    return float(value.replace(",", ""))


def _status_for_text(text: str) -> ProjectAssetStatus:
    lower = text.casefold()
    if any(marker in lower for marker in ("not commissioned", "not yet commissioned", "not operational", "not secured")):
        return ProjectAssetStatus.UNKNOWN
    ordered = (
        ("under construction", ProjectAssetStatus.UNDER_CONSTRUCTION),
        ("commissioned", ProjectAssetStatus.COMMISSIONED),
        ("operational", ProjectAssetStatus.OPERATIONAL),
        ("permitted", ProjectAssetStatus.PERMITTED),
        ("contracted", ProjectAssetStatus.CONTRACTED),
        ("applied for", ProjectAssetStatus.APPLIED_FOR),
        ("planning application", ProjectAssetStatus.APPLIED_FOR),
        ("planned", ProjectAssetStatus.PLANNED),
        ("proposed", ProjectAssetStatus.PROPOSED),
    )
    for marker, status in ordered:
        if marker in lower:
            return status
    return ProjectAssetStatus.UNKNOWN


def _fact(
    *,
    document: ProjectDocument,
    field_name: str,
    value: Any,
    page: int,
    text: str,
    ordinal: int,
    notes: list[str] | None = None,
) -> ProjectEvidenceFact:
    citation = CitationReference(
        document_id=document.project_document_id,
        source_path=document.local_path,
        page_start=page,
        page_end=page,
        section_heading=_heading_for_text(text),
        locator=f"page {page}",
    )
    return ProjectEvidenceFact(
        fact_id=f"{document.project_document_id}-fact-{ordinal:04d}",
        project_document_id=document.project_document_id,
        project_id=document.project_id,
        field_name=field_name,
        value=value,
        status=_status_for_text(text),
        evidence_state="PROVIDED" if value is not None else "UNKNOWN",
        confidence="UNKNOWN",
        verification_status="UNVERIFIED_PROJECT_DOCUMENT",
        page_start=page,
        page_end=page,
        source_url=document.source_url,
        citation=citation,
        benchmark_only=document.benchmark_only,
        notes=notes or ["Deterministic candidate extracted from project document text; human verification required."],
    )


def extract_project_facts(document: ProjectDocument, pages: list[dict[str, Any]]) -> list[ProjectEvidenceFact]:
    """Extract only explicit numeric/status candidates; never infer completion."""

    facts: list[ProjectEvidenceFact] = []
    ordinal = 1
    for page_record in pages:
        page = int(page_record["page"])
        text = _normalise_text(str(page_record.get("text") or ""))
        if not text:
            continue
        for match in re.finditer(rf"({_NUMBER})\s*(?:hectares?|ha)\b", text, re.IGNORECASE):
            facts.append(_fact(document=document, field_name="site_area_hectares", value=_parse_number(match.group(1)), page=page, text=text, ordinal=ordinal))
            ordinal += 1
        for match in re.finditer(rf"({_NUMBER})\s*(MW|MVA)\b", text, re.IGNORECASE):
            unit = match.group(2).upper()
            field = "planned_power_mw" if unit == "MW" else "requested_mic_mva"
            facts.append(_fact(document=document, field_name=field, value={"value": _parse_number(match.group(1)), "unit": unit}, page=page, text=text, ordinal=ordinal))
            ordinal += 1
        lower = text.casefold()
        if any(marker in lower for marker in ("renewable", "solar", "wind", "battery", "energy storage")):
            status = _status_for_text(text)
            facts.append(_fact(document=document, field_name="renewable_asset_status", value={"mentioned": True, "status": status.value}, page=page, text=text, ordinal=ordinal, notes=["Renewable/energy asset language is preserved as a candidate; mention is not evidence of commissioning or operation."]))
            ordinal += 1
        if any(marker in lower for marker in ("connection agreement", "connection offer", "grid connection", "energisation")):
            facts.append(_fact(document=document, field_name="grid_connection_status", value={"status": _status_for_text(text).value}, page=page, text=text, ordinal=ordinal, notes=["Grid language is preserved as a candidate; feasibility, agreement, energisation and operation are not conflated."]))
            ordinal += 1
        if any(marker in lower for marker in ("water", "uisce", "wastewater", "feasibility")):
            facts.append(_fact(document=document, field_name="utility_or_feasibility_reference", value={"mentioned": True}, page=page, text=text, ordinal=ordinal, notes=["Reference detected in project text; this is not a verified utility connection or secured capacity."]))
            ordinal += 1
    return facts


def _pdf_pages(path: Path) -> list[dict[str, Any]]:
    try:
        try:
            import pymupdf as fitz
        except ImportError:  # pragma: no cover - compatibility path
            import fitz
    except ImportError as exc:  # pragma: no cover - installation issue
        raise RuntimeError("PyMuPDF is required for project evidence extraction") from exc

    pages: list[dict[str, Any]] = []
    with fitz.open(path) as pdf:
        for index, page in enumerate(pdf, start=1):
            raw_text = page.get_text("text") or ""
            pages.append(
                {
                    "page": index,
                    "text": _normalise_text(raw_text),
                    "has_text": bool(raw_text.strip()),
                    "images": len(page.get_images(full=True)),
                    "drawings": len(page.get_drawings()),
                    "links": len(page.get_links()),
                }
            )
    return pages


def _chunks(document: ProjectDocument, pages: list[dict[str, Any]]) -> list[ProjectEvidenceChunk]:
    chunks: list[ProjectEvidenceChunk] = []
    for page_record in pages:
        page = int(page_record["page"])
        text = _normalise_text(str(page_record.get("text") or ""))
        if not text:
            continue
        heading = _heading_for_text(text)
        for index, (_offset, segment) in enumerate(_text_windows(text)):
            citation = CitationReference(
                document_id=document.project_document_id,
                source_path=document.local_path,
                page_start=page,
                page_end=page,
                section_heading=heading,
                locator=f"page {page}" if heading is None else f"page {page}, section {heading}",
            )
            chunks.append(
                ProjectEvidenceChunk(
                    chunk_id=f"{document.project_document_id}-p{page:04d}-{index:03d}",
                    project_document_id=document.project_document_id,
                    project_id=document.project_id,
                    document_type=document.document_type,
                    domain=document.domain,
                    page_start=page,
                    page_end=page,
                    section_heading=heading,
                    text=segment,
                    benchmark_only=document.benchmark_only,
                    source_url=document.source_url,
                    citation=citation,
                )
            )
    return chunks


def _document_id(key: str) -> str:
    return "project-herbata-" + re.sub(r"[^a-z0-9]+", "-", key.casefold()).strip("-")


def _load_manifest(project_root: Path, manifest_path: Path | None) -> dict[str, Any]:
    path = manifest_path or project_root / "data" / "project_evidence" / "benchmarks" / "herbata" / "metadata" / "download_manifest.json"
    if not path.is_file():
        raise FileNotFoundError("Herbata download manifest is missing; run download_herbata.py first")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("project_id") != HERBATA_PROJECT_ID:
        raise ValueError("Herbata download manifest has an unexpected project_id")
    if manifest.get("failures"):
        raise ValueError("Herbata download manifest contains failed allow-list downloads")
    return manifest


def _write_staged_artifacts(
    staging: Path,
    *,
    project_id: str,
    documents: list[ProjectDocument],
    pages: list[dict[str, Any]],
    chunks: list[ProjectEvidenceChunk],
    facts: list[ProjectEvidenceFact],
    extraction_report: dict[str, Any],
    benchmark_manifest: dict[str, Any],
) -> None:
    _json_write(staging / "document_registry.json", {"schema_version": 1, "project_id": project_id, "documents": [item.model_dump(mode="json") for item in documents]})
    _jsonl_write(staging / "pages.jsonl", pages)
    pages_dir = staging / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)
    for document_id in sorted({str(item["project_document_id"]) for item in pages}):
        _json_write(
            pages_dir / f"{document_id}.json",
            {
                "project_id": project_id,
                "project_document_id": document_id,
                "pages": [item for item in pages if item["project_document_id"] == document_id],
            },
        )
    _jsonl_write(staging / "chunks.jsonl", [item.model_dump(mode="json") for item in chunks])
    _jsonl_write(staging / "facts.jsonl", [item.model_dump(mode="json") for item in facts])
    _json_write(staging / "extraction_report.json", extraction_report)
    _json_write(staging / "benchmark_manifest.json", benchmark_manifest)


def build_project_evidence(project_root: Path, *, manifest_path: Path | None = None) -> dict[str, Any]:
    """Build the Herbata project-evidence artifacts with a final registry commit."""

    project_root = project_root.resolve()
    manifest = _load_manifest(project_root, manifest_path)
    processed_dir = project_root / PROCESSED_ROOT / "herbata"
    index_dir = project_root / INDEX_ROOT / "herbata"
    parent = processed_dir.parent
    parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix="herbata-project-evidence-", dir=parent))
    documents: list[ProjectDocument] = []
    pages_output: list[dict[str, Any]] = []
    chunks: list[ProjectEvidenceChunk] = []
    facts: list[ProjectEvidenceFact] = []
    report_documents: list[dict[str, Any]] = []
    try:
        for item in sorted(manifest["documents"], key=lambda row: str(row["key"])):
            source = project_root / Path(str(item["local_path"]))
            if not source.is_file():
                raise FileNotFoundError(f"Project evidence source is missing: {item['local_path']}")
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            if digest != item["sha256"]:
                raise ValueError(f"Project evidence source hash changed: {item['local_path']}")
            doc = ProjectDocument(
                project_document_id=_document_id(str(item["key"])),
                project_id=HERBATA_PROJECT_ID,
                title=str(item["title"]),
                filename=str(item["filename"]),
                source_url=str(item["source_url"]),
                sha256=digest,
                document_type=str(item["document_type"]),
                classification=ProjectDocumentClassification(str(item["classification"])),
                domain=Domain(str(item["domain"])),
                retrieved_at=datetime.fromisoformat(str(item["retrieved_at"])),
                benchmark_only=bool(item["benchmark_only"]),
                rights_status=ProjectRightsStatus.UNKNOWN_REUSE,
                notes=["Downloaded from the official Herbata environmental-document listing or known document endpoint.", "Not authoritative policy; not eligible for Module 5 policy retrieval."],
                local_path=str(item["local_path"]),
            )
            page_records = _pdf_pages(source)
            doc = doc.model_copy(update={"page_count": len(page_records), "no_text_pages": [int(page["page"]) for page in page_records if not page["has_text"]]})
            doc_chunks = _chunks(doc, page_records)
            doc_facts = extract_project_facts(doc, page_records)
            doc = doc.model_copy(update={"chunk_count": len(doc_chunks), "fact_count": len(doc_facts)})
            documents.append(doc)
            chunks.extend(doc_chunks)
            facts.extend(doc_facts)
            pages_output.extend({"project_document_id": doc.project_document_id, "project_id": doc.project_id, **page} for page in page_records)
            report_documents.append({"project_document_id": doc.project_document_id, "title": doc.title, "page_count": doc.page_count, "no_text_pages": doc.no_text_pages, "chunk_count": doc.chunk_count, "fact_count": doc.fact_count, "ocr_used": False})

        by_key = {item["key"]: _document_id(item["key"]) for item in manifest["documents"]}
        benchmark_manifest = {
            "schema_version": 1,
            "project_id": HERBATA_PROJECT_ID,
            "themes": {
                "environment": [by_key["appropriate_assessment"]],
                "biodiversity": [by_key["biodiversity_eiar"]],
                "water": [by_key["water_hydrology_eiar"]],
                "energy": [],
                "grid": [],
                "planning": [],
                "infrastructure": [by_key["material_assets_built_services"]],
            },
        }
        extraction_report = {
            "schema_version": 1,
            "project_id": HERBATA_PROJECT_ID,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "ocr_used": False,
            "documents": report_documents,
            "counts": {"documents": len(documents), "pages": len(pages_output), "chunks": len(chunks), "facts": len(facts)},
        }
        _write_staged_artifacts(staging, project_id=HERBATA_PROJECT_ID, documents=documents, pages=pages_output, chunks=chunks, facts=facts, extraction_report=extraction_report, benchmark_manifest=benchmark_manifest)
        # Registry is the final processed artifact. A failure before this point
        # leaves the previous valid registry untouched.
        processed_dir.mkdir(parents=True, exist_ok=True)
        for name in ("pages.jsonl", "chunks.jsonl", "facts.jsonl", "extraction_report.json", "benchmark_manifest.json"):
            shutil.copy2(staging / name, processed_dir / name)
        pages_dir = processed_dir / "pages"
        if pages_dir.exists():
            shutil.rmtree(pages_dir)
        shutil.copytree(staging / "pages", pages_dir)
        shutil.copy2(staging / "document_registry.json", processed_dir / "document_registry.json")
        index_dir.mkdir(parents=True, exist_ok=True)
        _json_write(index_dir / "manifest.json", {"schema_version": 1, "project_id": HERBATA_PROJECT_ID, "processed_path": PROCESSED_ROOT.joinpath("herbata").as_posix(), "documents": len(documents), "chunks": len(chunks), "facts": len(facts), "semantic_available": False, "retrieval_mode": "project_evidence_lexical"})
        return extraction_report
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Build separate Herbata project-evidence artifacts")
    parser.add_argument("--project-root", type=Path, default=Path("."))
    args = parser.parse_args(argv)
    print(json.dumps(build_project_evidence(args.project_root), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
