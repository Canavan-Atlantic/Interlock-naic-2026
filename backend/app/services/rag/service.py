"""Deterministic Module 5A policy corpus inventory and build service.

This module deliberately stops at provenance-aware extraction and deterministic
chunking. It does not call an LLM, create embeddings, search, score, or make a
site recommendation.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any, Iterable

from pydantic import ValidationError

from ..data.registry import sha256_file
from .models import (
    CitationReference,
    CuratedRecordEnvelope,
    DocumentStatus,
    Domain,
    ExtractionStatus,
    Jurisdiction,
    RAGChunk,
    RAGDocument,
    SourceClass,
    Workflow,
)


OUTPUT_DIRNAME = "data/rag_processed"
CHUNK_SIZE_CHARS = 3600
CHUNK_OVERLAP_CHARS = 400


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - installation issue
        raise RuntimeError("PyYAML is required for Module 5A configuration") from exc
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def load_configuration(project_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Load relative source rules and explicit metadata overrides."""

    sources_path = project_root / "config" / "rag_sources.yaml"
    overrides_path = project_root / "config" / "rag_metadata_overrides.yaml"
    if not sources_path.is_file():
        raise FileNotFoundError(f"RAG source configuration not found: {sources_path}")
    sources = _load_yaml(sources_path)
    overrides = _load_yaml(overrides_path) if overrides_path.is_file() else {}
    return sources, overrides.get("documents", {})


def _relative_path(path: Path, project_root: Path) -> str:
    return path.relative_to(project_root).as_posix()


def _slug(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return value[:70] or "document"


def stable_document_id(source_path: str) -> str:
    """Create an identifier stable for a relative source path."""

    path_hash = hashlib.sha1(source_path.lower().encode("utf-8")).hexdigest()[:12]
    return f"rag-{_slug(Path(source_path).stem)}-{path_hash}"


def _enum_value(enum_type: type, value: Any, default: Any) -> Any:
    if value is None:
        return default
    try:
        return enum_type(str(value))
    except ValueError:
        return default


def _enum_list(enum_type: type, values: Any) -> list[Any]:
    if not values:
        return []
    result: list[Any] = []
    for value in values:
        try:
            result.append(enum_type(str(value)))
        except ValueError:
            continue
    return result


def _as_notes(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


def _path_rule(source_path: str, source_config: dict[str, Any]) -> dict[str, Any]:
    rules = source_config.get("path_rules", [])
    candidates = [
        rule
        for rule in rules
        if source_path == rule.get("prefix")
        or source_path.startswith(f"{rule.get('prefix', '').rstrip('/')}/")
    ]
    if not candidates:
        return {}
    return max(candidates, key=lambda rule: len(str(rule.get("prefix", ""))))


def _root_for_path(source_path: str, source_config: dict[str, Any]) -> dict[str, Any]:
    roots = source_config.get("roots", [])
    candidates = [
        root
        for root in roots
        if source_path == root.get("path")
        or source_path.startswith(f"{root.get('path', '').rstrip('/')}/")
    ]
    return max(candidates, key=lambda root: len(str(root.get("path", "")))) if candidates else {}


def _infer_jurisdiction(source_path: str, configured: Any) -> Jurisdiction:
    explicit = _enum_value(Jurisdiction, configured, Jurisdiction.UNKNOWN)
    if explicit != Jurisdiction.UNKNOWN:
        return explicit
    lower = source_path.lower()
    if "/local_authority/" in lower:
        return Jurisdiction.LOCAL_AUTHORITY
    if "/primary/eu/" in f"/{lower}/" or "/eu_" in lower:
        return Jurisdiction.EU
    if "/primary/ireland/" in f"/{lower}/" or "/raw/grid/" in f"/{lower}/" or "/raw/water/" in f"/{lower}/":
        return Jurisdiction.IRELAND
    return Jurisdiction.UNKNOWN


def _infer_jurisdiction_detail(source_path: str, jurisdiction: Jurisdiction, configured: Any) -> str | None:
    if configured:
        return str(configured)
    lower = source_path.lower()
    if jurisdiction == Jurisdiction.LOCAL_AUTHORITY and "fingal" in lower:
        return "Fingal"
    if jurisdiction == Jurisdiction.IRELAND:
        return "Ireland"
    if jurisdiction == Jurisdiction.EU:
        return "European Union"
    return None


def _infer_domains(source_path: str, source_config: dict[str, Any]) -> list[Domain]:
    lower = source_path.lower()
    mapping = source_config.get("domain_path_map", {})
    domains: list[Domain] = []
    for segment, values in mapping.items():
        if segment.lower() in lower:
            for domain in _enum_list(Domain, values):
                if domain not in domains:
                    domains.append(domain)
    if "32023l1791" in lower or "energy-efficiency" in lower:
        if Domain.EU_REPORTING not in domains:
            domains.append(Domain.EU_REPORTING)
    return domains or [Domain.UNKNOWN]


def _infer_workflows(domains: list[Domain], source_config: dict[str, Any]) -> list[Workflow]:
    workflows: list[Workflow] = []
    mapping = source_config.get("workflow_domain_map", {})
    for domain in domains:
        for workflow in _enum_list(Workflow, mapping.get(domain.value, [])):
            if workflow not in workflows:
                workflows.append(workflow)
    return workflows


def _default_document_type(source_path: str, suffix: str) -> str:
    lower = source_path.lower()
    if suffix == ".zip":
        return "ARCHIVE_PACKAGE"
    if suffix == ".jsonl":
        if lower.endswith("rag_records.jsonl"):
            return "CURATED_KNOWLEDGE_RECORDS"
        if lower.endswith("review_flags.jsonl"):
            return "CURATED_REVIEW_METADATA"
        if lower.endswith("retrieval_eval_cases.jsonl"):
            return "CURATED_EVALUATION_CASES"
        return "JSONL_SOURCE"
    if suffix == ".json":
        if lower.endswith("source_registry.json"):
            return "CURATED_PROVENANCE_METADATA"
        if lower.endswith("rag_record_schema.json"):
            return "CURATED_SCHEMA"
        return "JSON_SOURCE"
    if "/planning/" in lower:
        return "PLANNING_DOCUMENT"
    if "/grid/" in lower or "eirgrid" in lower:
        return "SYSTEM_OPERATOR_POLICY_OR_TECHNICAL"
    if "/water/" in lower or "uisce" in lower:
        return "CAPACITY_REGISTER"
    return "POLICY_OR_RESEARCH_DOCUMENT"


def _default_title(path: Path) -> str:
    return path.stem.replace("_", " ")


def _source_limitations(source_class: SourceClass) -> list[str]:
    if source_class == SourceClass.ARCHIVE:
        return ["Archive material is retained for audit and is not part of the active corpus."]
    if source_class == SourceClass.RESTRICTED:
        return ["Restricted/confidential material is registered for awareness but excluded from active chunks."]
    if source_class == SourceClass.GOVERNANCE:
        return ["Governance material is excluded from normal site-assessment retrieval."]
    if source_class == SourceClass.SUPPORTING_INDUSTRY:
        return ["Industry material is supporting perspective, not primary regulatory authority."]
    return []


def discover_documents(project_root: Path) -> list[RAGDocument]:
    """Discover configured source files without modifying their directories."""

    source_config, overrides = load_configuration(project_root)
    discovered_at = datetime.now(timezone.utc)
    documents: list[RAGDocument] = []
    seen_paths: set[str] = set()

    for root_config in source_config.get("roots", []):
        root_relative = str(root_config.get("path", "")).replace("\\", "/").strip("/")
        root = project_root / Path(root_relative)
        if not root.is_dir():
            continue
        allowed = {str(ext).lower() if str(ext).startswith(".") else f".{str(ext).lower()}" for ext in root_config.get("allowed_extensions", [])}
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in allowed:
                continue
            source_path = _relative_path(path, project_root)
            if source_path in seen_paths:
                continue
            seen_paths.add(source_path)

            rule = _path_rule(source_path, source_config)
            override = dict(overrides.get(source_path, {}))
            source_class = _enum_value(
                SourceClass,
                override.get("source_class", rule.get("source_class", SourceClass.UNKNOWN.value)),
                SourceClass.UNKNOWN,
            )
            document_status = _enum_value(
                DocumentStatus,
                override.get("document_status", rule.get("document_status", DocumentStatus.UNKNOWN.value)),
                DocumentStatus.UNKNOWN,
            )
            jurisdiction = _infer_jurisdiction(source_path, override.get("jurisdiction", rule.get("jurisdiction")))
            domains = _enum_list(
                Domain,
                override.get("applicable_domains", rule.get("applicable_domains")),
            ) or _infer_domains(source_path, source_config)
            workflows = _enum_list(
                Workflow,
                override.get("applicable_workflows", rule.get("applicable_workflows")),
            ) or _infer_workflows(domains, source_config)
            retrieval_eligible = bool(
                override.get("retrieval_eligible", rule.get("retrieval_eligible", False))
            )
            if source_class in {SourceClass.ARCHIVE, SourceClass.RESTRICTED, SourceClass.GOVERNANCE}:
                retrieval_eligible = False
            restricted = bool(override.get("restricted", rule.get("restricted", False))) or source_class == SourceClass.RESTRICTED
            confidential = bool(override.get("confidential", rule.get("confidential", False))) or source_class == SourceClass.RESTRICTED
            notes = _as_notes(rule.get("notes")) + _as_notes(override.get("notes"))
            limitations = _source_limitations(source_class) + _as_notes(override.get("limitations"))
            document = RAGDocument(
                document_id=stable_document_id(source_path),
                title=str(override.get("title", _default_title(path))),
                filename=path.name,
                source_path=source_path,
                sha256=sha256_file(path),
                source_class=source_class,
                authority_class=source_class,
                document_status=document_status,
                jurisdiction=jurisdiction,
                jurisdiction_detail=_infer_jurisdiction_detail(
                    source_path,
                    jurisdiction,
                    override.get("jurisdiction_detail", rule.get("jurisdiction_detail")),
                ),
                issuer=override.get("issuer", rule.get("issuer")),
                document_type=str(override.get("document_type", rule.get("document_type", _default_document_type(source_path, path.suffix.lower())))),
                publication_date=override.get("publication_date"),
                effective_date=override.get("effective_date"),
                version=override.get("version"),
                retrieval_eligible=retrieval_eligible,
                requires_human_review=bool(override.get("requires_human_review", rule.get("requires_human_review", False))),
                restricted=restricted,
                confidential=confidential,
                applicable_workflows=workflows,
                applicable_domains=domains,
                source_url=override.get("source_url"),
                notes=notes,
                limitations=limitations,
                discovered_at=discovered_at,
            )
            documents.append(document)

    _apply_relationships(documents, overrides)
    return sorted(documents, key=lambda document: document.source_path)


def _apply_relationships(documents: list[RAGDocument], overrides: dict[str, Any]) -> None:
    """Attach duplicate and explicit supersession relationships by source path/hash."""

    by_path = {document.source_path: document for document in documents}
    for document in documents:
        override = overrides.get(document.source_path, {})
        duplicate_path = override.get("duplicate_of_path")
        if duplicate_path and duplicate_path in by_path:
            document.duplicate_of_document_id = by_path[duplicate_path].document_id
        supersedes_path = override.get("supersedes_path")
        if supersedes_path and supersedes_path in by_path:
            target = by_path[supersedes_path]
            document.supersedes_document_id = target.document_id
            target.superseded_by_document_id = document.document_id

    by_hash: dict[str, list[RAGDocument]] = defaultdict(list)
    for document in documents:
        by_hash[document.sha256].append(document)
    for group in by_hash.values():
        if len(group) < 2:
            continue
        explicit_targets = {
            document.duplicate_of_document_id
            for document in group
            if document.duplicate_of_document_id
        }
        if explicit_targets:
            canonical = next(
                (document for document in group if document.document_id in explicit_targets),
                sorted(group, key=lambda item: item.source_path)[0],
            )
        else:
            canonical = sorted(
                group,
                key=lambda item: (
                    item.source_class in {SourceClass.ARCHIVE, SourceClass.RESTRICTED},
                    item.source_path,
                ),
            )[0]
        for document in group:
            if document is canonical:
                continue
            if document.duplicate_of_document_id is None:
                document.duplicate_of_document_id = canonical.document_id
            if document.source_path not in canonical.duplicate_source_paths:
                canonical.duplicate_source_paths.append(document.source_path)


def _normalise_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in text.split("\n")]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines)


def _heading_for_text(text: str) -> str | None:
    for line in _normalise_text(text).split("\n"):
        candidate = line.strip()
        if not candidate or len(candidate) > 160:
            continue
        if candidate.isupper() or re.match(r"^(?:\d+(?:\.\d+)*|[A-Z])\.?\s+\S+", candidate):
            return candidate
    return None


def _text_windows(text: str) -> Iterable[tuple[int, str]]:
    if not text:
        return
    start = 0
    while start < len(text):
        end = min(len(text), start + CHUNK_SIZE_CHARS)
        segment = text[start:end].strip()
        if segment:
            yield start, segment
        if end >= len(text):
            break
        start = max(end - CHUNK_OVERLAP_CHARS, start + 1)


def _verification_status(document: RAGDocument) -> str:
    if document.requires_human_review:
        return "REVIEW_REQUIRED"
    if document.source_class == SourceClass.SUPPORTING_INDUSTRY:
        return "SUPPORTING_ONLY"
    if document.document_status == DocumentStatus.PROPOSED:
        return "PROPOSED_REVIEW"
    return "REGISTERED_SOURCE"


def _pdf_chunks(document: RAGDocument, page_texts: list[dict[str, Any]]) -> list[RAGChunk]:
    chunks: list[RAGChunk] = []
    for page_record in page_texts:
        page = int(page_record["page"])
        text = _normalise_text(str(page_record.get("text", "")))
        if not text:
            continue
        heading = _heading_for_text(text)
        for index, (_offset, segment) in enumerate(_text_windows(text)):
            locator = f"page {page}" if heading is None else f"page {page}, section {heading}"
            citation = CitationReference(
                document_id=document.document_id,
                source_path=document.source_path,
                page_start=page,
                page_end=page,
                section_heading=heading,
                locator=locator,
            )
            chunks.append(
                RAGChunk(
                    chunk_id=f"{document.document_id}-p{page:04d}-{index:03d}",
                    document_id=document.document_id,
                    text=segment,
                    page_start=page,
                    page_end=page,
                    section_heading=heading,
                    source_class=document.source_class,
                    document_status=document.document_status,
                    jurisdiction=document.jurisdiction,
                    issuer=document.issuer,
                    publication_date=document.publication_date,
                    version=document.version,
                    applicable_workflows=document.applicable_workflows,
                    applicable_domains=document.applicable_domains,
                    source_path=document.source_path,
                    source_reference=citation,
                    retrieval_eligible=document.retrieval_eligible,
                    verification_status=_verification_status(document),
                    requires_human_review=document.requires_human_review,
                )
            )
    return chunks


def _extract_pdf(document: RAGDocument, project_root: Path) -> tuple[dict[str, Any], list[RAGChunk]]:
    try:
        try:
            import pymupdf as fitz
        except ImportError:  # pragma: no cover - compatibility with older PyMuPDF
            import fitz
    except ImportError as exc:  # pragma: no cover - installation issue
        raise RuntimeError("PyMuPDF is required for PDF extraction") from exc

    page_texts: list[dict[str, Any]] = []
    with fitz.open(project_root / document.source_path) as pdf:
        for index, page in enumerate(pdf, start=1):
            raw_text = page.get_text("text") or ""
            page_texts.append(
                {
                    "page": index,
                    "text": raw_text,
                    "has_text": bool(raw_text.strip()),
                    "images": len(page.get_images(full=True)),
                    "drawings": len(page.get_drawings()),
                    "links": len(page.get_links()),
                    "width": page.rect.width,
                    "height": page.rect.height,
                }
            )
    extraction = {
        "document_id": document.document_id,
        "source_path": document.source_path,
        "page_count": len(page_texts),
        "no_text_pages": [item["page"] for item in page_texts if not item["has_text"]],
        "pages": page_texts,
        "ocr_used": False,
    }
    return extraction, _pdf_chunks(document, page_texts)


def _iter_docx_blocks(document: Any) -> Iterable[dict[str, Any]]:
    from docx.document import Document as DocumentClass
    from docx.oxml.table import CT_Tbl
    from docx.oxml.text.paragraph import CT_P
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    if not isinstance(document, DocumentClass):
        raise TypeError("Expected a python-docx Document")
    paragraph_index = 0
    table_index = 0
    for child in document.element.body.iterchildren():
        if isinstance(child, CT_P):
            paragraph = Paragraph(child, document)
            text = paragraph.text or ""
            style_name = getattr(paragraph.style, "name", "") if paragraph.style else ""
            heading = text.strip() if str(style_name).lower().startswith("heading") and text.strip() else None
            paragraph_index += 1
            yield {
                "kind": "paragraph",
                "index": paragraph_index,
                "text": text,
                "heading": heading,
            }
        elif isinstance(child, CT_Tbl):
            table = Table(child, document)
            rows = [" | ".join(cell.text.strip() for cell in row.cells) for row in table.rows]
            table_index += 1
            yield {
                "kind": "table",
                "index": table_index,
                "text": "\n".join(row for row in rows if row),
                "heading": None,
            }


def _docx_chunks(document: RAGDocument, blocks: list[dict[str, Any]]) -> list[RAGChunk]:
    chunks: list[RAGChunk] = []
    current_heading: str | None = None
    for block in blocks:
        raw_text = str(block.get("text", ""))
        text = _normalise_text(raw_text)
        if not text:
            continue
        if block.get("heading"):
            current_heading = str(block["heading"])
        for index, (_offset, segment) in enumerate(_text_windows(text)):
            locator = f"{block['kind']} {block['index']}"
            if current_heading:
                locator = f"{locator}, section {current_heading}"
            citation = CitationReference(
                document_id=document.document_id,
                source_path=document.source_path,
                section_heading=current_heading,
                paragraph_start=block["index"] if block["kind"] == "paragraph" else None,
                paragraph_end=block["index"] if block["kind"] == "paragraph" else None,
                locator=locator,
            )
            chunks.append(
                RAGChunk(
                    chunk_id=f"{document.document_id}-{str(block['kind'])[0]}{block['index']:04d}-{index:03d}",
                    document_id=document.document_id,
                    text=segment,
                    section_heading=current_heading,
                    source_class=document.source_class,
                    document_status=document.document_status,
                    jurisdiction=document.jurisdiction,
                    issuer=document.issuer,
                    publication_date=document.publication_date,
                    version=document.version,
                    applicable_workflows=document.applicable_workflows,
                    applicable_domains=document.applicable_domains,
                    source_path=document.source_path,
                    source_reference=citation,
                    retrieval_eligible=document.retrieval_eligible,
                    verification_status=_verification_status(document),
                    requires_human_review=document.requires_human_review,
                )
            )
    return chunks


def _extract_docx(document: RAGDocument, project_root: Path) -> tuple[dict[str, Any], list[RAGChunk]]:
    try:
        from docx import Document
    except ImportError as exc:  # pragma: no cover - installation issue
        raise RuntimeError("python-docx is required for DOCX extraction") from exc
    doc = Document(project_root / document.source_path)
    blocks = list(_iter_docx_blocks(doc))
    extraction = {
        "document_id": document.document_id,
        "source_path": document.source_path,
        "page_count": None,
        "no_text_pages": [],
        "blocks": blocks,
        "page_numbers_available": False,
    }
    return extraction, _docx_chunks(document, blocks)


def _read_json_lines(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"Expected an object at {path}:{line_number}")
        records.append(value)
    return records


def _curated_records(document: RAGDocument, project_root: Path) -> list[CuratedRecordEnvelope]:
    path = project_root / document.source_path
    records = _read_json_lines(path)
    flags_path = path.with_name("review_flags.jsonl")
    flags = _read_json_lines(flags_path) if flags_path.is_file() else []
    envelopes: list[CuratedRecordEnvelope] = []
    for record in records:
        record_id = str(record.get("id", f"record-{len(envelopes) + 1:04d}"))
        source_ids = {
            str(source.get("source_id"))
            for source in record.get("sources", [])
            if isinstance(source, dict) and source.get("source_id")
        }
        searchable = json.dumps(record, ensure_ascii=False)
        matched_flags = [
            flag
            for flag in flags
            if flag.get("source_id") in source_ids
            or (flag.get("original_claim") and str(flag["original_claim"]) in searchable)
        ]
        quality = record.get("quality", {}) if isinstance(record.get("quality"), dict) else {}
        review_required = bool(quality.get("review_required")) or bool(matched_flags)
        retrieval_eligible = document.retrieval_eligible and not review_required
        verification_status = "REVIEW_REQUIRED" if review_required else "CURATED_RECORD"
        references = record.get("sources", []) if isinstance(record.get("sources"), list) else []
        envelopes.append(
            CuratedRecordEnvelope(
                record_id=record_id,
                document_id=document.document_id,
                source_path=document.source_path,
                record=record,
                review_flags=matched_flags,
                review_flag_status="MATCHED" if matched_flags else "NO_DIRECT_FLAG_MATCH",
                retrieval_eligible=retrieval_eligible,
                verification_status=verification_status,
                source_references=references,
            )
        )
    return envelopes


def _audit_curated_flags(
    flags: list[dict[str, Any]],
    record_envelopes: list[CuratedRecordEnvelope],
) -> list[dict[str, Any]]:
    """Explain every review flag without forcing unsupported claim matches."""

    audit: list[dict[str, Any]] = []
    for flag in flags:
        flag_id = flag.get("flag_id")
        matched_record_ids = [
            envelope.record_id
            for envelope in record_envelopes
            if any(item.get("flag_id") == flag_id for item in envelope.review_flags)
        ]
        item = dict(flag)
        item["matched_record_ids"] = matched_record_ids
        if matched_record_ids:
            item["assessment"] = "B_ACTIVE_CURATED_RECORD_MATCH"
            item["trust_treatment"] = "REVIEW_REQUIRED_MATCHED"
            item["safe_reason"] = (
                "The flag is attached to an active curated record; that record remains visibly review-required "
                "and retrieval-ineligible until reviewed."
            )
        else:
            item["assessment"] = "A_ORIGINAL_SOURCE_CLAIM_ABSENT_FROM_CLEANED_RECORDS"
            item["trust_treatment"] = "NOT_TRUSTED_UNMATCHED"
            item["safe_reason"] = (
                "The flag source_id is not present in any cleaned record source reference and the original claim "
                "has no exact match in the cleaned record payload; the unsupported claim remains outside the "
                "trusted active curated corpus."
            )
        audit.append(item)
    return audit


def _no_text_page_report(
    documents: list[RAGDocument],
    extraction_by_document: dict[str, dict[str, Any]],
    source_config: dict[str, Any],
) -> list[dict[str, Any]]:
    """Create a deterministic audit list for pages with no extractable text."""

    overrides = source_config.get("no_text_page_overrides", {})
    report: list[dict[str, Any]] = []
    for document in documents:
        extraction = extraction_by_document.get(document.document_id)
        if not extraction:
            continue
        page_overrides = overrides.get(document.source_path, {})
        for page in extraction.get("pages", []):
            if page.get("has_text"):
                continue
            page_number = str(page["page"])
            override = page_overrides.get(page_number, {})
            if override:
                classification = str(override.get("classification", "UNKNOWN"))
                basis = str(override.get("basis", "Configured deterministic classification."))
                manual_review = bool(override.get("manual_review_required", False))
            elif page.get("images") or page.get("drawings"):
                classification = "MAP_FIGURE" if page["page"] > 1 else "COVER_TITLE"
                basis = "Deterministic page structure contains visual objects but no extractable text."
                manual_review = True
            else:
                classification = "UNKNOWN"
                basis = "No extractable text and no deterministic visual classification override."
                manual_review = True
            report.append(
                {
                    "document_id": document.document_id,
                    "title": document.title,
                    "page": page["page"],
                    "source_path": document.source_path,
                    "classification": classification,
                    "manual_review_required": manual_review,
                    "basis": basis,
                    "images": page.get("images", 0),
                    "drawings": page.get("drawings", 0),
                    "links": page.get("links", 0),
                }
            )
    return report


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def _write_jsonl(path: Path, records: Iterable[Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as output:
        for record in records:
            payload = record.model_dump(mode="json") if hasattr(record, "model_dump") else record
            output.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _document_summary(document: RAGDocument) -> dict[str, Any]:
    return document.model_dump(mode="json")


def _report(
    documents: list[RAGDocument],
    chunks: list[RAGChunk],
    curated_records: list[CuratedRecordEnvelope],
    flags_total: int,
    flags_matched: int,
    ambiguous: list[str],
    no_text_pages: list[dict[str, Any]],
    flag_audit: list[dict[str, Any]],
) -> dict[str, Any]:
    active_unique = [document for document in documents if document.retrieval_eligible and not document.duplicate_of_document_id]
    supporting_classes = {
        SourceClass.SUPPORTING_PUBLIC_BODY,
        SourceClass.SUPPORTING_INDUSTRY,
        SourceClass.SUPPORTING_RESEARCH,
    }
    no_text = {
        document.document_id: document.no_text_pages
        for document in documents
        if document.no_text_pages
    }
    unknown_metadata = {
        field: sum(1 for document in documents if getattr(document, field) in (None, Jurisdiction.UNKNOWN, "UNKNOWN", []))
        for field in ("publication_date", "effective_date", "version", "issuer", "jurisdiction")
    }
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": "Module 5A deterministic policy knowledge-base foundation; not legal completeness",
        "counts": {
            "total_registered_documents": len(documents),
            "active_retrieval_documents": len(active_unique),
            "primary_current": sum(1 for document in documents if document.source_class == SourceClass.PRIMARY and document.document_status == DocumentStatus.CURRENT),
            "proposed_or_historical": sum(1 for document in documents if document.document_status in {DocumentStatus.PROPOSED, DocumentStatus.HISTORICAL}),
            "supporting_public_body": sum(1 for document in documents if document.source_class == SourceClass.SUPPORTING_PUBLIC_BODY),
            "supporting_industry": sum(1 for document in documents if document.source_class == SourceClass.SUPPORTING_INDUSTRY),
            "supporting_research": sum(1 for document in documents if document.source_class == SourceClass.SUPPORTING_RESEARCH),
            "supporting_documents": sum(1 for document in documents if document.source_class in supporting_classes),
            "governance": sum(1 for document in documents if document.source_class == SourceClass.GOVERNANCE),
            "restricted": sum(1 for document in documents if document.source_class == SourceClass.RESTRICTED),
            "archive": sum(1 for document in documents if document.source_class == SourceClass.ARCHIVE),
            "duplicates": sum(1 for document in documents if document.duplicate_of_document_id),
            "failed_extraction_documents": sum(1 for document in documents if document.extraction_status == ExtractionStatus.FAILED),
            "total_pages_extracted": sum(document.page_count or 0 for document in documents),
            "total_active_chunks": len(chunks),
            "curated_atomic_records": len(curated_records),
            "pages_with_no_extractable_text": sum(len(pages) for pages in no_text.values()),
        },
        "documents_missing_metadata": unknown_metadata,
        "documents_pages_without_extractable_text": no_text,
        "no_text_page_manual_review_count": sum(1 for item in no_text_pages if item["manual_review_required"]),
        "no_text_page_report": no_text_pages,
        "extraction_failures": [
            {"document_id": document.document_id, "source_path": document.source_path, "error": document.extraction_error}
            for document in documents
            if document.extraction_status == ExtractionStatus.FAILED
        ],
        "duplicate_documents": [
            {"document_id": document.document_id, "source_path": document.source_path, "duplicate_of_document_id": document.duplicate_of_document_id}
            for document in documents
            if document.duplicate_of_document_id
        ],
        "ambiguous_documents": ambiguous,
        "curated_review_flags": {
            "total": flags_total,
            "matched_to_records": flags_matched,
            "unmatched_flags_remain_non_trusted": flags_total - flags_matched,
        },
        "curated_review_flag_audit": [
            {
                "flag_id": item.get("flag_id"),
                "assessment": item.get("assessment"),
                "matched_record_ids": item.get("matched_record_ids", []),
                "trust_treatment": item.get("trust_treatment"),
            }
            for item in flag_audit
        ],
        "ai_or_embedding_calls": 0,
    }


def _primary_quality_report(documents: list[RAGDocument]) -> dict[str, Any]:
    """Return concise audit metadata for every PRIMARY source."""

    primary: list[dict[str, Any]] = []
    for document in documents:
        if document.source_class != SourceClass.PRIMARY:
            continue
        jurisdiction = getattr(document.jurisdiction, "value", document.jurisdiction)
        document_status = getattr(document.document_status, "value", document.document_status)
        missing = [
            field
            for field, value in (
                ("title", document.title),
                ("issuer", document.issuer),
                ("jurisdiction", jurisdiction),
                ("publication_date", document.publication_date),
                ("effective_date", document.effective_date),
                ("version", document.version),
            )
            if value in (None, "", "UNKNOWN") or value == Jurisdiction.UNKNOWN.value
        ]
        primary.append(
            {
                "document_id": document.document_id,
                "title": document.title,
                "issuer": document.issuer,
                "jurisdiction": jurisdiction,
                "publication_date": document.publication_date,
                "effective_date": document.effective_date,
                "version": document.version,
                "document_status": document_status,
                "pages": document.page_count,
                "chunks": document.chunk_count,
                "missing_metadata": missing,
                "pages_without_text": document.no_text_pages,
                "duplicate_of": document.duplicate_of_document_id,
                "supersedes": document.supersedes_document_id,
                "superseded_by": document.superseded_by_document_id,
                "retrieval_eligible": document.retrieval_eligible,
            }
        )
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "documents": primary,
    }


def build_corpus(project_root: Path) -> dict[str, Any]:
    """Build the registry, extraction provenance, deterministic chunks and report."""

    source_config, _overrides = load_configuration(project_root)
    documents = discover_documents(project_root)
    output_root = project_root / OUTPUT_DIRNAME
    extraction_root = output_root / "extraction"
    output_root.mkdir(parents=True, exist_ok=True)
    extraction_root.mkdir(parents=True, exist_ok=True)
    chunks: list[RAGChunk] = []
    curated_records: list[CuratedRecordEnvelope] = []
    curated_flag_records: list[dict[str, Any]] = []
    flag_audit: list[dict[str, Any]] = []
    extraction_by_document: dict[str, dict[str, Any]] = {}
    now = datetime.now(timezone.utc)
    flags_total = 0
    flags_matched = 0
    ambiguous: list[str] = [document.source_path for document in documents if document.source_class == SourceClass.UNKNOWN]

    for document in documents:
        document.processed_at = now
        if document.duplicate_of_document_id and document.retrieval_eligible:
            document.extraction_status = ExtractionStatus.DUPLICATE_SKIPPED
            continue
        if document.source_class == SourceClass.ARCHIVE:
            document.extraction_status = ExtractionStatus.SKIPPED_ARCHIVE
            continue
        if document.source_class == SourceClass.RESTRICTED:
            document.extraction_status = ExtractionStatus.SKIPPED_RESTRICTED
            continue
        if document.source_class == SourceClass.GOVERNANCE:
            document.extraction_status = ExtractionStatus.SKIPPED_GOVERNANCE
            continue
        if document.source_class == SourceClass.CURATED:
            if document.filename == "rag_records.jsonl":
                try:
                    record_envelopes = _curated_records(document, project_root)
                    curated_records.extend(record_envelopes)
                    document.curated_record_count = len(record_envelopes)
                    document.extraction_status = ExtractionStatus.CURATED_ATOMIC
                    flags_path = project_root / document.source_path.replace("rag_records.jsonl", "review_flags.jsonl")
                    if flags_path.is_file():
                        source_flags = _read_json_lines(flags_path)
                        flags_total = len(source_flags)
                        flag_audit = _audit_curated_flags(source_flags, record_envelopes)
                        curated_flag_records.extend(flag_audit)
                        flags_matched = sum(1 for item in flag_audit if item.get("matched_record_ids"))
                except Exception as exc:  # noqa: BLE001 - one bad curated file must not stop the corpus
                    document.extraction_status = ExtractionStatus.FAILED
                    document.extraction_error = str(exc)
            else:
                document.extraction_status = ExtractionStatus.SKIPPED_METADATA
            continue
        if not document.retrieval_eligible or Path(document.filename).suffix.lower() not in {".pdf", ".docx"}:
            document.extraction_status = ExtractionStatus.SKIPPED_METADATA
            continue
        try:
            if document.filename.lower().endswith(".pdf"):
                extraction, document_chunks = _extract_pdf(document, project_root)
                document.page_count = extraction["page_count"]
                document.no_text_pages = extraction["no_text_pages"]
            else:
                extraction, document_chunks = _extract_docx(document, project_root)
            document.chunk_count = len(document_chunks)
            document.extraction_status = ExtractionStatus.EXTRACTED
            chunks.extend(document_chunks)
            extraction_by_document[document.document_id] = extraction
            _write_json(extraction_root / f"{document.document_id}.json", extraction)
        except Exception as exc:  # noqa: BLE001 - corpus build should report, not hide, one bad source
            document.extraction_status = ExtractionStatus.FAILED
            document.extraction_error = str(exc)

    registry_payload = {
        "schema_version": 1,
        "generated_at": now.isoformat(),
        "documents": [_document_summary(document) for document in documents],
    }
    _write_json(output_root / "document_registry.json", registry_payload)
    _write_jsonl(output_root / "chunks.jsonl", chunks)
    _write_jsonl(output_root / "curated_records.jsonl", curated_records)
    _write_jsonl(output_root / "curated_review_flags.jsonl", curated_flag_records)
    no_text_pages = _no_text_page_report(documents, extraction_by_document, source_config)
    report = _report(documents, chunks, curated_records, flags_total, flags_matched, ambiguous, no_text_pages, flag_audit)
    _write_json(
        output_root / "no_text_pages.json",
        {"generated_at": now.isoformat(), "pages": no_text_pages},
    )
    _write_json(
        output_root / "review_flag_audit.json",
        {
            "generated_at": now.isoformat(),
            "flags": flag_audit,
            "summary": {
                "total": len(flag_audit),
                "matched": sum(1 for item in flag_audit if item.get("matched_record_ids")),
                "not_trusted_unmatched": sum(1 for item in flag_audit if item.get("trust_treatment") == "NOT_TRUSTED_UNMATCHED"),
            },
        },
    )
    _write_json(output_root / "primary_source_quality.json", _primary_quality_report(documents))
    _write_json(output_root / "build_report.json", report)
    return report


def write_inventory(project_root: Path) -> dict[str, Any]:
    """Write a metadata-only registry without extracting or chunking source text."""

    documents = discover_documents(project_root)
    output_root = project_root / OUTPUT_DIRNAME
    output_root.mkdir(parents=True, exist_ok=True)
    _write_json(
        output_root / "document_registry.json",
        {
            "schema_version": 1,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "documents": [_document_summary(document) for document in documents],
        },
    )
    summary = {"total_registered_documents": len(documents), "output": str(output_root / "document_registry.json")}
    print(json.dumps(summary, indent=2))
    return summary


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_corpus(project_root: Path) -> dict[str, Any]:
    """Validate generated registry/chunk invariants and source immutability hashes."""

    output_root = project_root / OUTPUT_DIRNAME
    registry_path = output_root / "document_registry.json"
    chunks_path = output_root / "chunks.jsonl"
    curated_path = output_root / "curated_records.jsonl"
    curated_flags_path = output_root / "curated_review_flags.jsonl"
    flag_audit_path = output_root / "review_flag_audit.json"
    no_text_path = output_root / "no_text_pages.json"
    primary_quality_path = output_root / "primary_source_quality.json"
    report_path = output_root / "build_report.json"
    missing = [
        str(path)
        for path in (
            registry_path,
            chunks_path,
            curated_path,
            curated_flags_path,
            flag_audit_path,
            no_text_path,
            primary_quality_path,
            report_path,
        )
        if not path.is_file()
    ]
    if missing:
        raise FileNotFoundError("Generated Module 5A output is missing: " + ", ".join(missing))

    registry = _load_json(registry_path)
    documents = [RAGDocument.model_validate(item) for item in registry.get("documents", [])]
    document_by_id = {document.document_id: document for document in documents}
    chunks = [RAGChunk.model_validate(json.loads(line)) for line in chunks_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    curated = [CuratedRecordEnvelope.model_validate(json.loads(line)) for line in curated_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    flag_audit = _load_json(flag_audit_path).get("flags", [])
    no_text_report = _load_json(no_text_path).get("pages", [])
    primary_quality = _load_json(primary_quality_path).get("documents", [])
    errors: list[str] = []
    if len({chunk.chunk_id for chunk in chunks}) != len(chunks):
        errors.append("Duplicate chunk_id values found")
    for chunk in chunks:
        document = document_by_id.get(chunk.document_id)
        if document is None:
            errors.append(f"Chunk references missing document: {chunk.chunk_id}")
        elif not document.retrieval_eligible:
            errors.append(f"Excluded document has an active chunk: {document.source_path}")
        if chunk.page_start is not None and chunk.page_end is not None and chunk.page_start > chunk.page_end:
            errors.append(f"Invalid page range: {chunk.chunk_id}")
    for document in documents:
        source = project_root / document.source_path
        if not source.is_file():
            errors.append(f"Source file missing: {document.source_path}")
        elif sha256_file(source) != document.sha256:
            errors.append(f"Source hash changed: {document.source_path}")
        if document.source_class in {SourceClass.ARCHIVE, SourceClass.RESTRICTED, SourceClass.GOVERNANCE} and document.chunk_count:
            errors.append(f"Excluded document reports active chunks: {document.source_path}")
        if document.source_class in {SourceClass.ARCHIVE, SourceClass.RESTRICTED} and document.retrieval_eligible:
            errors.append(f"Archive/restricted document is retrieval eligible: {document.source_path}")
        if document.source_class == SourceClass.SUPPORTING_INDUSTRY and document.authority_class == SourceClass.PRIMARY:
            errors.append(f"Industry source masquerades as primary authority: {document.source_path}")
        if document.duplicate_of_document_id and document.chunk_count:
            errors.append(f"Duplicate source produced active chunks: {document.source_path}")

    cru_documents = [document for document in documents if "/cru/" in f"/{document.source_path.lower()}/"]
    current_cru = [document for document in cru_documents if document.document_status == DocumentStatus.CURRENT]
    proposed_cru = [
        document
        for document in cru_documents
        if document.document_status in {DocumentStatus.PROPOSED, DocumentStatus.HISTORICAL}
    ]
    if current_cru and proposed_cru and any("proposed" in document.title.lower() for document in current_cru):
        errors.append("A CRU document with proposed status is labelled CURRENT")
    if current_cru and proposed_cru and not {document.document_id for document in current_cru}.isdisjoint(
        document.document_id for document in proposed_cru
    ):
        errors.append("Current and proposed CRU document IDs are not distinct")

    curated_by_id = {record.record_id: record for record in curated}
    for record in curated:
        if record.review_flags and record.retrieval_eligible:
            errors.append(f"Flagged curated record is still trusted/retrieval eligible: {record.record_id}")
    for flag in flag_audit:
        if flag.get("trust_treatment") == "NOT_TRUSTED_UNMATCHED" and flag.get("matched_record_ids"):
            errors.append(f"Unmatched review flag has record matches: {flag.get('flag_id')}")
        for record_id in flag.get("matched_record_ids", []):
            record = curated_by_id.get(record_id)
            if record is None:
                errors.append(f"Review flag references missing curated record: {record_id}")
            elif not record.review_flags or record.retrieval_eligible:
                errors.append(f"Flagged curated record lacks visible exclusion: {record_id}")

    expected_no_text = {
        (document.document_id, page)
        for document in documents
        for page in document.no_text_pages
    }
    reported_no_text = {(item.get("document_id"), item.get("page")) for item in no_text_report}
    if expected_no_text != reported_no_text:
        errors.append("No-text page report does not match registry page metadata")
    primary_ids = {document.document_id for document in documents if document.source_class == SourceClass.PRIMARY}
    if {item.get("document_id") for item in primary_quality} != primary_ids:
        errors.append("Primary source quality report does not cover every PRIMARY document")
    report = _load_json(report_path)
    result = {
        "valid": not errors,
        "documents": len(documents),
        "chunks": len(chunks),
        "curated_records": len(curated),
        "errors": errors,
        "report_counts": report.get("counts", {}),
    }
    print(json.dumps(result, indent=2))
    if errors:
        raise ValueError("Module 5A validation failed")
    return result


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="INTERLOCK Module 5A deterministic policy corpus tools")
    parser.add_argument("command", choices=("inventory", "build", "validate"))
    parser.add_argument("--project-root", type=Path, default=Path("."))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    project_root = args.project_root.resolve()
    try:
        if args.command == "inventory":
            write_inventory(project_root)
        elif args.command == "build":
            print(json.dumps(build_corpus(project_root), indent=2))
        else:
            validate_corpus(project_root)
    except (FileNotFoundError, RuntimeError, ValueError, ValidationError) as exc:
        print(f"Module 5A {args.command} failed: {exc}", file=sys.stderr)
        return 1
    return 0
