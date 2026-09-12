"""Module 5B authority-aware hybrid retrieval over the Module 5A corpus.

This module reads only the processed Module 5A JSONL outputs. It does not
re-open source PDFs, interpret law, generate answers, score projects, or call
agents. Authority and document status are eligibility and ordering controls,
not embedding text or unexplained semantic boosts.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import Counter, defaultdict
from datetime import datetime, timezone
import argparse
from functools import lru_cache
import hashlib
import json
import logging
import math
import os
from pathlib import Path
import random
import re
import sys
import time
from typing import Any, Iterable, Sequence

import numpy as np

from .models import (
    CuratedRecordEnvelope,
    DocumentStatus,
    Domain,
    Jurisdiction,
    RAGChunk,
    RAGDocument,
    RetrievalRequest,
    SourceClass,
    Workflow,
)


INDEX_DIRNAME = "data/rag_index"
INDEX_SCHEMA_VERSION = 1
RRF_K = 60
BM25_K1 = 1.2
BM25_B = 0.75
CANDIDATE_MULTIPLIER = 5
MOCK_EMBEDDING_DIMENSION = 64
DEFAULT_OPENAI_EMBEDDING_MODEL = "text-embedding-3-small"
MAX_BATCH_TOKENS = 250_000
MAX_BATCH_ITEMS = 256
MAX_RATE_LIMIT_RETRIES = 6
INITIAL_BACKOFF_SECONDS = 2.0
MAX_BACKOFF_SECONDS = 60.0
DEFAULT_BATCH_DELAY_SECONDS = 0.5
TOKEN_PATTERN = re.compile(r"[a-z0-9]+(?:[.-][a-z0-9]+)*", re.IGNORECASE)
PAGE_PATTERN = re.compile(r"\bpp?\.?\s*(\d+)(?:\s*[\u2013\u2014-]\s*(\d+))?\b", re.IGNORECASE)
RETRY_DURATION_PATTERN = re.compile(r"(?P<value>\d+(?:\.\d+)?)(?P<unit>ms|s|m|h)", re.IGNORECASE)


LOGGER = logging.getLogger(__name__)


class RetrievalError(RuntimeError):
    """Base class for controlled retrieval/index errors."""


class IndexNotBuiltError(RetrievalError):
    """Raised when a search is requested before the local index exists."""


class StaleIndexError(RetrievalError):
    """Raised when processed Module 5A inputs changed after indexing."""


class SemanticUnavailableError(RetrievalError):
    """Raised internally when semantic indexing/search cannot be enabled."""


class EmbeddingBatchError(RetrievalError):
    """Raised when an OpenAI embedding batch cannot be completed safely."""


class EmbeddingInputTooLargeError(EmbeddingBatchError):
    """Raised when one embedding input exceeds the conservative batch limit."""


def _non_negative_float_from_env(name: str, default: float) -> float:
    raw_value = os.getenv(name)
    if raw_value is None or not raw_value.strip():
        return default
    try:
        return max(0.0, float(raw_value))
    except ValueError:
        return default


def _parse_retry_interval(value: Any) -> float | None:
    """Parse seconds or compact reset durations such as ``1m30s``."""

    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        seconds = float(text)
    except ValueError:
        seconds = 0.0
        position = 0
        matches = list(RETRY_DURATION_PATTERN.finditer(text))
        if not matches or matches[0].start() != 0:
            return None
        for match in matches:
            if match.start() != position:
                return None
            amount = float(match.group("value"))
            unit = match.group("unit").lower()
            seconds += amount / 1000 if unit == "ms" else amount * {"s": 1, "m": 60, "h": 3600}[unit]
            position = match.end()
        if position != len(text):
            return None
    return seconds if seconds > 0 else None


def _enum_text(value: Any) -> str:
    return str(getattr(value, "value", value))


def _normalise(value: Any) -> str:
    return str(value or "").strip()


def _tokens(text: str) -> list[str]:
    return [match.group(0).lower() for match in TOKEN_PATTERN.finditer(text)]


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _sha256_if_present(path: Path) -> str | None:
    return _sha256_file(path) if path.is_file() else None


def _json_lines(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise FileNotFoundError(f"Required Module 5A output is missing: {path}")
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if line.strip():
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"Expected an object at {path}:{line_number}")
            rows.append(value)
    return rows


def _corpus_hash(project_root: Path) -> str:
    digest = hashlib.sha256()
    for relative in (
        "data/rag_processed/chunks.jsonl",
        "data/rag_processed/curated_records.jsonl",
    ):
        path = project_root / relative
        digest.update(relative.encode("utf-8"))
        digest.update(path.read_bytes() if path.is_file() else b"<missing>")
    return digest.hexdigest()


class EmbeddingProvider(ABC):
    """Provider abstraction used only for embedding text, never authority."""

    provider_name: str
    model_name: str | None
    dimension: int | None

    @abstractmethod
    def embed_documents(self, texts: Sequence[str]) -> np.ndarray:
        """Embed a sequence of texts into a two-dimensional float array."""

    def embed_query(self, text: str) -> np.ndarray:
        vectors = self.embed_documents([text])
        return vectors[0]


class DeterministicMockEmbeddingProvider(EmbeddingProvider):
    """Stable hashed-token vectors for tests and offline development."""

    provider_name = "deterministic_mock"
    model_name = "sha256-token-hash-v1"
    dimension = MOCK_EMBEDDING_DIMENSION

    def embed_documents(self, texts: Sequence[str]) -> np.ndarray:
        vectors = np.zeros((len(texts), self.dimension), dtype=np.float32)
        for row, text in enumerate(texts):
            for token in _tokens(text):
                digest = hashlib.sha256(token.encode("utf-8")).digest()
                index = int.from_bytes(digest[:4], "big") % self.dimension
                sign = 1.0 if digest[4] % 2 else -1.0
                vectors[row, index] += sign
            norm = float(np.linalg.norm(vectors[row]))
            if norm:
                vectors[row] /= norm
        return vectors


class OpenAIEmbeddingProvider(EmbeddingProvider):
    """OpenAI embeddings through OPENAI_API_KEY and the configured model."""

    provider_name = "openai"

    def __init__(self, model_name: str | None = None, api_key: str | None = None) -> None:
        self.model_name = model_name or os.getenv("INTERLOCK_RAG_EMBEDDING_MODEL") or DEFAULT_OPENAI_EMBEDDING_MODEL
        configured_key = api_key or os.getenv("OPENAI_API_KEY")
        if not configured_key:
            raise SemanticUnavailableError("OPENAI_API_KEY is not configured")
        try:
            from openai import OpenAI, RateLimitError
        except ImportError as exc:
            raise SemanticUnavailableError("The openai package is not installed") from exc
        self._client = OpenAI(api_key=configured_key)
        self._rate_limit_error = RateLimitError
        self._encoding = self._load_encoding(self.model_name)
        self._batch_delay_seconds = _non_negative_float_from_env(
            "INTERLOCK_RAG_EMBEDDING_BATCH_DELAY_SECONDS",
            DEFAULT_BATCH_DELAY_SECONDS,
        )
        self.dimension = None

    @staticmethod
    def _load_encoding(model_name: str):
        """Load the model encoding when tiktoken is available, with a safe fallback."""

        try:
            import tiktoken
        except ImportError:
            return None
        try:
            return tiktoken.encoding_for_model(model_name)
        except (KeyError, ValueError):
            return tiktoken.get_encoding("cl100k_base")

    def _estimate_token_count(self, text: str) -> int:
        if self._encoding is not None:
            return max(1, len(self._encoding.encode(text, disallowed_special=())))
        # UTF-8 byte count is a conservative upper bound when no tokenizer is
        # installed: byte-oriented tokenizers cannot produce more tokens than
        # input bytes.
        return max(1, len(text.encode("utf-8")))

    @staticmethod
    def _server_retry_seconds(error: BaseException) -> float | None:
        response = getattr(error, "response", None)
        headers = getattr(response, "headers", None) or getattr(error, "headers", None)
        if headers is None:
            return None
        values: list[float] = []
        for wanted_name in (
            "retry-after",
            "x-ratelimit-reset-tokens",
            "x-ratelimit-reset-requests",
        ):
            value = None
            try:
                value = headers.get(wanted_name)
            except AttributeError:
                value = None
            if value is None:
                for key, candidate in getattr(headers, "items", lambda: [])():
                    if str(key).lower() == wanted_name:
                        value = candidate
                        break
            parsed = _parse_retry_interval(value)
            if parsed is not None:
                values.append(parsed)
        return max(values) if values else None

    @staticmethod
    def _local_retry_seconds(retry_number: int) -> float:
        base = min(
            MAX_BACKOFF_SECONDS,
            INITIAL_BACKOFF_SECONDS * (2 ** max(0, retry_number - 1)),
        )
        jitter = random.uniform(0.0, min(1.0, base * 0.1))
        return min(MAX_BACKOFF_SECONDS, base + jitter)

    def _create_embedding_batch(
        self,
        batch: list[str],
        batch_number: int,
        batch_start: int,
    ) -> Any:
        rate_limit_retries = 0
        rate_limit_error = getattr(self, "_rate_limit_error", ())
        while True:
            try:
                return self._client.embeddings.create(model=self.model_name, input=batch)
            except Exception as exc:
                if not isinstance(exc, rate_limit_error):
                    raise EmbeddingBatchError(
                        f"OpenAI embedding batch {batch_number} failed for input indexes "
                        f"{batch_start}-{batch_start + len(batch) - 1} ({len(batch)} records): "
                        f"{type(exc).__name__}."
                    ) from exc
                if rate_limit_retries >= MAX_RATE_LIMIT_RETRIES:
                    LOGGER.error(
                        "OpenAI embedding batch %s exhausted rate-limit retries (%s records).",
                        batch_number,
                        len(batch),
                    )
                    raise EmbeddingBatchError(
                        f"OpenAI embedding batch {batch_number} exhausted rate-limit retries "
                        f"after {MAX_RATE_LIMIT_RETRIES} retries ({len(batch)} records)."
                    ) from exc
                rate_limit_retries += 1
                local_wait = self._local_retry_seconds(rate_limit_retries)
                server_wait = self._server_retry_seconds(exc)
                wait_seconds = max(local_wait, server_wait or 0.0)
                LOGGER.warning(
                    "OpenAI embedding batch %s rate limited; retrying attempt %s/%s in %.1f "
                    "seconds (%s records).",
                    batch_number,
                    rate_limit_retries,
                    MAX_RATE_LIMIT_RETRIES,
                    wait_seconds,
                    len(batch),
                )
                time.sleep(wait_seconds)

    def _embedding_batches(self, texts: Sequence[str]) -> Iterable[tuple[int, list[str], int]]:
        batch_start = 0
        batch: list[str] = []
        batch_tokens = 0
        for input_index, text in enumerate(texts):
            estimated_tokens = self._estimate_token_count(text)
            if estimated_tokens > MAX_BATCH_TOKENS:
                raise EmbeddingInputTooLargeError(
                    f"Embedding input at index {input_index} is estimated at "
                    f"{estimated_tokens} tokens, above MAX_BATCH_TOKENS={MAX_BATCH_TOKENS}; "
                    "refusing to truncate policy evidence."
                )
            if batch and (
                len(batch) >= MAX_BATCH_ITEMS
                or batch_tokens + estimated_tokens > MAX_BATCH_TOKENS
            ):
                yield batch_start, batch, batch_tokens
                batch_start = input_index
                batch = []
                batch_tokens = 0
            if not batch:
                batch_start = input_index
            batch.append(text)
            batch_tokens += estimated_tokens
        if batch:
            yield batch_start, batch, batch_tokens

    @staticmethod
    def _ordered_batch_vectors(response: Any, expected_count: int, batch_number: int) -> np.ndarray:
        response_data = list(getattr(response, "data", []) or [])
        if len(response_data) != expected_count:
            raise EmbeddingBatchError(
                f"OpenAI embedding batch {batch_number} returned {len(response_data)} "
                f"embeddings for {expected_count} inputs."
            )
        try:
            ordered = sorted(response_data, key=lambda item: int(item.index))
            indexes = [int(item.index) for item in ordered]
        except (AttributeError, TypeError, ValueError) as exc:
            raise EmbeddingBatchError(
                f"OpenAI embedding batch {batch_number} returned invalid response indexes."
            ) from exc
        if indexes != list(range(expected_count)):
            raise EmbeddingBatchError(
                f"OpenAI embedding batch {batch_number} returned non-contiguous response indexes."
            )
        try:
            vectors = np.asarray([item.embedding for item in ordered], dtype=np.float32)
        except (AttributeError, TypeError, ValueError) as exc:
            raise EmbeddingBatchError(
                f"OpenAI embedding batch {batch_number} returned invalid vector data."
            ) from exc
        if vectors.ndim != 2 or vectors.shape[0] != expected_count or vectors.shape[1] == 0:
            raise EmbeddingBatchError(
                f"OpenAI embedding batch {batch_number} returned vectors with an invalid shape."
            )
        return vectors

    def embed_documents(self, texts: Sequence[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, 0), dtype=np.float32)
        vectors_by_batch: list[np.ndarray] = []
        batches = list(self._embedding_batches(texts))
        for batch_number, (batch_start, batch, _estimated_tokens) in enumerate(batches, start=1):
            response = self._create_embedding_batch(batch, batch_number, batch_start)
            batch_vectors = self._ordered_batch_vectors(response, len(batch), batch_number)
            if vectors_by_batch and batch_vectors.shape[1] != vectors_by_batch[0].shape[1]:
                raise EmbeddingBatchError(
                    f"OpenAI embedding batch {batch_number} returned a different vector dimension."
                )
            vectors_by_batch.append(batch_vectors)
            if batch_number < len(batches):
                batch_delay_seconds = getattr(self, "_batch_delay_seconds", 0.0)
                if batch_delay_seconds > 0:
                    time.sleep(batch_delay_seconds)
        vectors = np.vstack(vectors_by_batch)
        if vectors.shape[0] != len(texts):
            raise EmbeddingBatchError(
                f"OpenAI embedding returned {vectors.shape[0]} vectors for {len(texts)} inputs."
            )
        self.dimension = int(vectors.shape[1])
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        return np.divide(vectors, np.where(norms == 0, 1, norms))


def _requested_embedding_provider(provider_name: str | None = None) -> str:
    return (
        provider_name
        or os.getenv("INTERLOCK_RAG_EMBEDDING_PROVIDER")
        or "openai"
    ).strip().lower()


def make_embedding_provider(provider_name: str | None = None) -> EmbeddingProvider:
    configured = _requested_embedding_provider(provider_name)
    if configured in {"mock", "deterministic_mock", "test"}:
        return DeterministicMockEmbeddingProvider()
    if configured in {"none", "lexical", "disabled"}:
        raise SemanticUnavailableError("Semantic embeddings are disabled")
    if configured != "openai":
        raise SemanticUnavailableError(f"Unsupported embedding provider: {configured}")
    return OpenAIEmbeddingProvider()


def _localized_title(value: Any, fallback: str) -> str:
    if isinstance(value, dict):
        return str(value.get("en") or next(iter(value.values()), fallback))
    return str(value or fallback)


def _topic_domains(topic: Any) -> list[str]:
    value = str(topic or "").lower()
    mapping = {
        "grid_connection": ["GRID", "DATA_CENTRE_POLICY"],
        "dispatchable_generation": ["GRID", "ENERGY", "DATA_CENTRE_POLICY"],
        "renewable_energy": ["ENERGY", "DATA_CENTRE_POLICY"],
        "gas_and_biomethane": ["ENERGY", "DATA_CENTRE_POLICY"],
        "site_location": ["GRID", "PLANNING"],
        "grid_connection": ["GRID", "DATA_CENTRE_POLICY"],
        "planning_policy": ["PLANNING", "DATA_CENTRE_POLICY"],
        "energy_efficiency_reporting": ["ENERGY", "EU_REPORTING"],
        "context": ["GENERAL"],
    }
    return mapping.get(value, ["GENERAL"])


def _topic_workflows(domains: Iterable[str]) -> list[str]:
    result: list[str] = []
    for domain in domains:
        if domain in {"PLANNING", "BIODIVERSITY", "ENVIRONMENT", "WATER", "GRID", "ENERGY"}:
            for workflow in ("SITE_DISCOVERY", "SITE_FEASIBILITY", "POLICY_REGULATORY_INTELLIGENCE"):
                if workflow not in result:
                    result.append(workflow)
        elif domain in {"DATA_CENTRE_POLICY", "EU_REPORTING", "INFRASTRUCTURE", "GENERAL"}:
            if "POLICY_REGULATORY_INTELLIGENCE" not in result:
                result.append("POLICY_REGULATORY_INTELLIGENCE")
    return result


def _parse_pages(pinpoint: Any) -> tuple[int | None, int | None]:
    match = PAGE_PATTERN.search(str(pinpoint or ""))
    if not match:
        return None, None
    start = int(match.group(1))
    end = int(match.group(2) or start)
    return start, end


def _format_citation(
    title: str,
    issuer: str | None,
    page_start: int | None,
    page_end: int | None,
    section_heading: str | None = None,
    pinpoint: str | None = None,
) -> str:
    prefix = f"{issuer} — {title}" if issuer else title
    if page_start is not None:
        page = f"p. {page_start}" if page_start == page_end else f"pp. {page_start}–{page_end}"
        return f"{prefix}, {page}"
    if section_heading:
        return f"{prefix}, section {section_heading}"
    if pinpoint:
        return f"{prefix}, {pinpoint}"
    return prefix


def _document_title(document: RAGDocument | None, fallback: str) -> str:
    return document.title if document is not None else fallback


def _base_record(
    *,
    record_id: str,
    text: str,
    embedding_text: str,
    document: RAGDocument | None,
    record_kind: str,
    title: str,
    source_class: str,
    document_status: str,
    jurisdiction: str,
    jurisdiction_detail: str | None,
    issuer: str | None,
    publication_date: str | None,
    effective_date: str | None,
    version: str | None,
    applicable_workflows: list[str],
    applicable_domains: list[str],
    source_path: str,
    page_start: int | None,
    page_end: int | None,
    section_heading: str | None,
    citation: str,
    verification_status: str,
    requires_human_review: bool,
    retrieval_eligible: bool,
    record_legal_status: str | None = None,
    record_topic: str | None = None,
    source_references: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "record_id": record_id,
        "record_kind": record_kind,
        "chunk_id": record_id if record_kind == "chunk" else None,
        "curated_record_id": record_id if record_kind == "curated" else None,
        "document_id": document.document_id if document else None,
        "title": title,
        "text": text,
        "embedding_text": embedding_text,
        "page_start": page_start,
        "page_end": page_end,
        "section_heading": section_heading,
        "source_class": source_class,
        "document_status": document_status,
        "jurisdiction": jurisdiction,
        "jurisdiction_detail": jurisdiction_detail,
        "issuer": issuer,
        "publication_date": publication_date,
        "effective_date": effective_date,
        "version": version,
        "applicable_workflows": applicable_workflows,
        "applicable_domains": applicable_domains,
        "citation": citation,
        "source_path": source_path,
        "verification_status": verification_status,
        "requires_human_review": requires_human_review,
        "retrieval_eligible": retrieval_eligible,
        "record_legal_status": record_legal_status,
        "record_topic": record_topic,
        "source_references": source_references or [],
    }


def _processed_records(project_root: Path) -> list[dict[str, Any]]:
    output_root = project_root / "data" / "rag_processed"
    registry_payload = json.loads((output_root / "document_registry.json").read_text(encoding="utf-8"))
    documents = {
        item.document_id: item
        for item in (RAGDocument.model_validate(row) for row in registry_payload.get("documents", []))
    }
    chunks = [RAGChunk.model_validate(row) for row in _json_lines(output_root / "chunks.jsonl")]
    curated = [CuratedRecordEnvelope.model_validate(row) for row in _json_lines(output_root / "curated_records.jsonl")]
    records: list[dict[str, Any]] = []

    for chunk in chunks:
        document = documents.get(chunk.document_id)
        if document is None:
            continue
        if not chunk.retrieval_eligible or not document.retrieval_eligible:
            continue
        if document.duplicate_of_document_id:
            continue
        if chunk.source_class in {SourceClass.RESTRICTED, SourceClass.ARCHIVE, SourceClass.GOVERNANCE}:
            continue
        title = _document_title(document, chunk.document_id)
        source = chunk.source_reference.model_dump(mode="json")
        citation = _format_citation(
            title,
            chunk.issuer,
            chunk.page_start,
            chunk.page_end,
            chunk.section_heading,
        )
        records.append(
            _base_record(
                record_id=chunk.chunk_id,
                text=chunk.text,
                embedding_text="\n".join(item for item in (title, chunk.section_heading or "", chunk.text) if item),
                document=document,
                record_kind="chunk",
                title=title,
                source_class=_enum_text(chunk.source_class),
                document_status=_enum_text(chunk.document_status),
                jurisdiction=_enum_text(chunk.jurisdiction),
                jurisdiction_detail=document.jurisdiction_detail,
                issuer=chunk.issuer,
                publication_date=chunk.publication_date,
                effective_date=document.effective_date,
                version=chunk.version,
                applicable_workflows=[_enum_text(value) for value in chunk.applicable_workflows],
                applicable_domains=[_enum_text(value) for value in chunk.applicable_domains],
                source_path=chunk.source_path,
                page_start=chunk.page_start,
                page_end=chunk.page_end,
                section_heading=chunk.section_heading,
                citation=citation,
                verification_status=chunk.verification_status,
                requires_human_review=chunk.requires_human_review,
                retrieval_eligible=chunk.retrieval_eligible,
                source_references=[source],
            )
        )

    for envelope in curated:
        record = envelope.record
        quality = record.get("quality", {}) if isinstance(record.get("quality"), dict) else {}
        if not envelope.retrieval_eligible or envelope.review_flags or quality.get("review_required"):
            continue
        topic = str(record.get("topic") or "")
        domains = _topic_domains(topic)
        workflows = _topic_workflows(domains)
        source_references = envelope.source_references
        first_source = source_references[0] if source_references else {}
        title = _localized_title(record.get("title"), envelope.record_id)
        content = record.get("content", {}) if isinstance(record.get("content"), dict) else {}
        retrieval_text = str(content.get("retrieval_text") or content.get("en") or "")
        full_text = str(content.get("en") or retrieval_text)
        page_start, page_end = _parse_pages(first_source.get("pinpoint"))
        issuer = str(record.get("authority") or first_source.get("publisher") or "") or None
        jurisdiction = str(record.get("jurisdiction") or "UNKNOWN").upper().replace(" ", "_")
        if jurisdiction == "EUROPEAN_UNION":
            jurisdiction = Jurisdiction.EU.value
        if jurisdiction not in {item.value for item in Jurisdiction}:
            jurisdiction = Jurisdiction.UNKNOWN.value
        document = documents.get(envelope.document_id)
        records.append(
            _base_record(
                record_id=envelope.record_id,
                text=full_text,
                embedding_text="\n".join(item for item in (title, retrieval_text, full_text) if item),
                document=document,
                record_kind="curated",
                title=title,
                source_class=SourceClass.CURATED.value,
                document_status=_enum_text(document.document_status) if document else DocumentStatus.SUPPORTING.value,
                jurisdiction=jurisdiction,
                jurisdiction_detail=None,
                issuer=issuer,
                publication_date=first_source.get("publication_date"),
                effective_date=record.get("effective_date"),
                version=record.get("version"),
                applicable_workflows=workflows,
                applicable_domains=domains,
                source_path=envelope.source_path,
                page_start=page_start,
                page_end=page_end,
                section_heading=first_source.get("pinpoint"),
                citation=_format_citation(
                    str(first_source.get("title") or title),
                    issuer,
                    page_start,
                    page_end,
                    pinpoint=first_source.get("pinpoint"),
                ),
                verification_status=envelope.verification_status,
                requires_human_review=False,
                retrieval_eligible=envelope.retrieval_eligible,
                record_legal_status=str(record.get("legal_status") or "") or None,
                record_topic=topic or None,
                source_references=source_references,
            )
        )

    return _deduplicate_records(records)


def _authority_sort_key(record: dict[str, Any]) -> tuple[int, int, str]:
    source_class = record["source_class"]
    status = record["document_status"]
    class_rank = {
        SourceClass.PRIMARY.value: 0,
        SourceClass.CURATED.value: 1,
        SourceClass.SUPPORTING_PUBLIC_BODY.value: 2,
        SourceClass.SUPPORTING_INDUSTRY.value: 3,
        SourceClass.SUPPORTING_RESEARCH.value: 4,
    }.get(source_class, 9)
    status_rank = {
        DocumentStatus.CURRENT.value: 0,
        DocumentStatus.SUPPORTING.value: 1,
        DocumentStatus.PROPOSED.value: 2,
        DocumentStatus.HISTORICAL.value: 3,
        DocumentStatus.SUPERSEDED.value: 4,
    }.get(status, 9)
    return class_rank, status_rank, record["record_id"]


def _deduplicate_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_text: dict[str, dict[str, Any]] = {}
    for record in sorted(records, key=_authority_sort_key):
        text_key = hashlib.sha256(_normalise(record["text"]).encode("utf-8")).hexdigest()
        if text_key not in by_text:
            by_text[text_key] = record
    return sorted(by_text.values(), key=lambda item: item["record_id"])


def _lexical_index(records: list[dict[str, Any]]) -> dict[str, Any]:
    postings: dict[str, dict[str, int]] = defaultdict(dict)
    lengths: dict[str, int] = {}
    for record in records:
        counts = Counter(_tokens(record["text"]))
        lengths[record["record_id"]] = sum(counts.values())
        for token, count in counts.items():
            postings[token][record["record_id"]] = count
    return {
        "method": "BM25",
        "k1": BM25_K1,
        "b": BM25_B,
        "document_count": len(records),
        "average_document_length": (sum(lengths.values()) / len(records)) if records else 0.0,
        "lengths": lengths,
        "postings": postings,
    }


def _bm25_scores(records: list[dict[str, Any]], index: dict[str, Any], query: str) -> dict[str, float]:
    query_tokens = set(_tokens(query))
    if not query_tokens:
        return {}
    records_by_id = {record["record_id"]: record for record in records}
    average_length = float(index.get("average_document_length") or 1.0)
    document_count = max(int(index.get("document_count", len(records))), 1)
    scores: dict[str, float] = defaultdict(float)
    for token in query_tokens:
        posting = index.get("postings", {}).get(token, {})
        if not posting:
            continue
        document_frequency = len(posting)
        idf = math.log(1.0 + (document_count - document_frequency + 0.5) / (document_frequency + 0.5))
        for record_id, term_frequency in posting.items():
            length = int(index.get("lengths", {}).get(record_id, len(_tokens(records_by_id[record_id]["text"]))))
            denominator = term_frequency + BM25_K1 * (1.0 - BM25_B + BM25_B * length / average_length)
            scores[record_id] += idf * (term_frequency * (BM25_K1 + 1.0) / denominator)
    return dict(scores)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def build_index(project_root: Path, embedding_provider: str | None = None) -> dict[str, Any]:
    """Build a local BM25 index and optionally a semantic vector sidecar."""

    records = _processed_records(project_root)
    if not records:
        raise ValueError("No trusted active Module 5A records are available for indexing")
    output_root = project_root / INDEX_DIRNAME
    output_root.mkdir(parents=True, exist_ok=True)
    lexical = _lexical_index(records)

    provider: EmbeddingProvider | None = None
    semantic_warning: str | None = None
    requested = _requested_embedding_provider(embedding_provider)
    if requested not in {"none", "lexical", "disabled"}:
        try:
            provider = make_embedding_provider(requested)
            vectors = provider.embed_documents([record["embedding_text"] for record in records])
        except SemanticUnavailableError as exc:
            semantic_warning = str(exc)
            provider = None
    else:
        vectors = None

    # Commit the new corpus artifacts only after any requested semantic build
    # has completed. A failed API batch therefore cannot overwrite a previously
    # valid index or leave a new manifest claiming semantic success.
    _write_jsonl(output_root / "records.jsonl", records)
    _write_json(output_root / "lexical_index.json", lexical)
    if provider is not None:
        np.save(output_root / "embeddings.npy", vectors)
    else:
        (output_root / "embeddings.npy").unlink(missing_ok=True)

    manifest = {
        "schema_version": INDEX_SCHEMA_VERSION,
        "index_created_at": datetime.now(timezone.utc).isoformat(),
        "corpus_hash": _corpus_hash(project_root),
        "source_hashes": {
            "chunks.jsonl": _sha256_file(project_root / "data/rag_processed/chunks.jsonl"),
            "curated_records.jsonl": _sha256_file(project_root / "data/rag_processed/curated_records.jsonl"),
            "document_registry.json": _sha256_if_present(project_root / "data/rag_processed/document_registry.json"),
            "build_report.json": _sha256_if_present(project_root / "data/rag_processed/build_report.json"),
        },
        "indexed_chunks": sum(record["record_kind"] == "chunk" for record in records),
        "indexed_curated_records": sum(record["record_kind"] == "curated" for record in records),
        "indexed_records": len(records),
        "embedding_provider_requested": requested,
        "embedding_provider": provider.provider_name if provider else "none",
        "embedding_model": provider.model_name if provider else None,
        "dimension": provider.dimension if provider else None,
        "semantic_available": provider is not None,
        "semantic_unavailable_reason": semantic_warning,
        "lexical_index": {
            "method": lexical["method"],
            "k1": BM25_K1,
            "b": BM25_B,
            "rrf_k": RRF_K,
            "candidate_multiplier": CANDIDATE_MULTIPLIER,
        },
    }
    _write_json(output_root / "manifest.json", manifest)
    return manifest


def _load_index(project_root: Path) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any], np.ndarray | None]:
    output_root = project_root / INDEX_DIRNAME
    manifest_path = output_root / "manifest.json"
    if not manifest_path.is_file():
        raise IndexNotBuiltError(f"Retrieval index not found: {manifest_path}; run the index command first")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    current_hash = _corpus_hash(project_root)
    if manifest.get("corpus_hash") != current_hash:
        raise StaleIndexError("Retrieval index is stale relative to Module 5A chunks/curated records; rebuild with the index command")
    records = _json_lines(output_root / "records.jsonl")
    lexical = json.loads((output_root / "lexical_index.json").read_text(encoding="utf-8"))
    vectors: np.ndarray | None = None
    if manifest.get("semantic_available"):
        vector_path = output_root / "embeddings.npy"
        if not vector_path.is_file():
            raise StaleIndexError("Semantic index sidecar is missing; rebuild with the index command")
        vectors = np.load(vector_path)
        if len(vectors) != len(records):
            raise StaleIndexError("Semantic index sidecar does not match indexed records; rebuild with the index command")
    return manifest, records, lexical, vectors


class LoadedRetrievalIndex:
    """Validated Module 5B artifacts reused for one deterministic run."""

    def __init__(
        self,
        project_root: Path,
        manifest: dict[str, Any],
        records: list[dict[str, Any]],
        lexical_index: dict[str, Any],
        vectors: np.ndarray | None,
    ) -> None:
        self.project_root = project_root
        self.manifest = manifest
        self.records = records
        self.lexical_index = lexical_index
        self.vectors = vectors
        self._embedding_provider: EmbeddingProvider | None = None
        self._embedding_provider_loaded = False

    def search(self, request: RetrievalRequest | dict[str, Any]) -> dict[str, Any]:
        return _search_loaded_index(self, request)


@lru_cache(maxsize=4)
def _load_retrieval_index_cached(
    root: str,
    manifest_mtime_ns: int,
    manifest_size: int,
    corpus_hash: str,
) -> LoadedRetrievalIndex:
    """Reuse an unchanged validated index without hiding rebuilds.

    The file signature and corpus hash are part of the cache key so a local
    Module 5A/5B rebuild automatically gets a fresh index object.
    """

    resolved_root = Path(root)
    _ = manifest_mtime_ns, manifest_size, corpus_hash
    return LoadedRetrievalIndex(resolved_root, *_load_index(resolved_root))


def load_retrieval_index(project_root: Path) -> LoadedRetrievalIndex:
    """Load and validate Module 5B artifacts, reusing unchanged static data."""

    root = Path(project_root).resolve()
    manifest_path = root / INDEX_DIRNAME / "manifest.json"
    stat = manifest_path.stat()
    return _load_retrieval_index_cached(
        str(root),
        stat.st_mtime_ns,
        stat.st_size,
        _corpus_hash(root),
    )


def _infer_local_authority(query: str, request: RetrievalRequest) -> str | None:
    if request.local_authority or request.jurisdiction_detail:
        return request.local_authority or request.jurisdiction_detail
    lower = query.lower()
    if re.search(r"\b(fingal|blanchardstown|swords|dublin 15)\b", lower):
        return "Fingal"
    if re.search(r"\b(wicklow|arklow|bray|greystones)\b", lower):
        return "Wicklow"
    return None


def _context_value(request: RetrievalRequest, *keys: str) -> str | None:
    for key in keys:
        value = request.project_context.get(key)
        if value:
            return str(value)
    return None


def _resolved_filters(request: RetrievalRequest) -> dict[str, Any]:
    local_authority = _infer_local_authority(request.query, request)
    if local_authority is None:
        local_authority = _context_value(request, "local_authority", "county")
    jurisdiction = _enum_text(request.jurisdiction) if request.jurisdiction else None
    workflow = _enum_text(request.workflow) if request.workflow else None
    domains = [_enum_text(value) for value in request.domains]
    return {
        "workflow": workflow,
        "domains": domains,
        "jurisdiction": jurisdiction,
        "jurisdiction_detail": request.jurisdiction_detail,
        "local_authority": local_authority,
        "legal_status": list(request.legal_status),
        "quality_review_required": request.quality_review_required,
        "include_historical": request.include_historical,
        "include_supporting": request.include_supporting,
        "top_k": request.top_k,
        "primary_limit": request.primary_limit,
        "supporting_limit": request.supporting_limit,
    }


def _is_governance_query(request: RetrievalRequest, filters: dict[str, Any]) -> bool:
    if "RESPONSIBLE_AI" in filters["domains"]:
        return True
    query = request.query.lower()
    return bool(re.search(r"\b(governance|responsible ai|ai act|artificial intelligence)\b", query))


def _jurisdiction_allowed(record: dict[str, Any], requested: str | None) -> bool:
    if not requested:
        return True
    actual = record["jurisdiction"]
    if requested == Jurisdiction.IRELAND.value:
        return actual in {Jurisdiction.IRELAND.value, Jurisdiction.LOCAL_AUTHORITY.value, Jurisdiction.EU.value}
    if requested == Jurisdiction.LOCAL_AUTHORITY.value:
        return actual == Jurisdiction.LOCAL_AUTHORITY.value
    return actual == requested


def _record_allowed(record: dict[str, Any], request: RetrievalRequest, filters: dict[str, Any]) -> bool:
    if not record.get("retrieval_eligible"):
        return False
    source_class = record["source_class"]
    status = record["document_status"]
    if source_class in {SourceClass.RESTRICTED.value, SourceClass.ARCHIVE.value}:
        return False
    if source_class == SourceClass.GOVERNANCE.value and not _is_governance_query(request, filters):
        return False
    if source_class == SourceClass.PRIMARY.value:
        if status == DocumentStatus.CURRENT.value:
            if record.get("requires_human_review"):
                return False
        elif status in {DocumentStatus.PROPOSED.value, DocumentStatus.HISTORICAL.value, DocumentStatus.SUPERSEDED.value}:
            if not request.include_historical:
                return False
        else:
            return False
    elif source_class == SourceClass.CURATED.value:
        if record.get("record_legal_status") in {"proposal_or_consultation", "needs_source_review"}:
            return False
    elif source_class == SourceClass.SUPPORTING_PUBLIC_BODY.value:
        pass
    elif source_class in {SourceClass.SUPPORTING_INDUSTRY.value, SourceClass.SUPPORTING_RESEARCH.value}:
        if not request.include_supporting:
            return False
    elif source_class == SourceClass.GOVERNANCE.value:
        pass
    else:
        return False

    if not _jurisdiction_allowed(record, filters["jurisdiction"]):
        return False
    local_authority = filters["local_authority"]
    if local_authority and record["jurisdiction"] == Jurisdiction.LOCAL_AUTHORITY.value:
        expected = local_authority.casefold()
        actual = str(record.get("jurisdiction_detail") or "").casefold()
        if expected != actual:
            return False
    if filters["workflow"]:
        workflows = set(record.get("applicable_workflows") or [])
        if workflows and filters["workflow"] not in workflows and Workflow.POLICY_REGULATORY_INTELLIGENCE.value not in workflows:
            return False
    if filters["domains"]:
        domains = set(record.get("applicable_domains") or [])
        if domains and not domains.intersection(filters["domains"]):
            return False
    if filters["legal_status"]:
        status = record.get("record_legal_status") or {
            DocumentStatus.CURRENT.value: "in_force",
            DocumentStatus.SUPPORTING.value: "active_policy",
            DocumentStatus.PROPOSED.value: "proposal_or_consultation",
            DocumentStatus.HISTORICAL.value: "historical",
            DocumentStatus.SUPERSEDED.value: "historical",
        }.get(status, status)
        if status not in set(filters["legal_status"]):
            return False
    if filters["quality_review_required"] is False and record.get("requires_human_review"):
        return False
    return True


def _semantic_scores(
    records: list[dict[str, Any]],
    record_ids: set[str],
    vectors: np.ndarray | None,
    query: str,
    manifest: dict[str, Any],
    embedding_provider: EmbeddingProvider | None = None,
    provider_loaded: bool = False,
) -> tuple[dict[str, float], str | None]:
    if vectors is None or not manifest.get("semantic_available"):
        return {}, "Semantic retrieval unavailable; lexical retrieval was used."
    provider_name = manifest.get("embedding_provider")
    try:
        if provider_loaded and embedding_provider is None:
            return {}, "Semantic retrieval unavailable; lexical retrieval was used."
        provider = embedding_provider or make_embedding_provider(provider_name)
        query_vector = provider.embed_query(query)
    except SemanticUnavailableError as exc:
        return {}, str(exc)
    id_to_index = {record["record_id"]: index for index, record in enumerate(records)}
    query_norm = float(np.linalg.norm(query_vector)) or 1.0
    scores: dict[str, float] = {}
    for record_id in record_ids:
        index = id_to_index[record_id]
        scores[record_id] = float(np.dot(vectors[index], query_vector) / query_norm)
    return scores, None


def _ranked(scores: dict[str, float], allowed_ids: set[str], reverse: bool = True) -> list[tuple[str, float]]:
    return sorted(
        ((record_id, score) for record_id, score in scores.items() if record_id in allowed_ids),
        key=lambda item: (-item[1], item[0]) if reverse else (item[1], item[0]),
    )


def _fuse(
    lexical: list[tuple[str, float]],
    semantic: list[tuple[str, float]],
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    lexical_ranks = {record_id: rank for rank, (record_id, _score) in enumerate(lexical, start=1)}
    lexical_scores = dict(lexical)
    semantic_ranks = {record_id: rank for rank, (record_id, _score) in enumerate(semantic, start=1)}
    semantic_scores = dict(semantic)
    for record_id in set(lexical_ranks) | set(semantic_ranks):
        score = 0.0
        if record_id in lexical_ranks:
            score += 1.0 / (RRF_K + lexical_ranks[record_id])
        if record_id in semantic_ranks:
            score += 1.0 / (RRF_K + semantic_ranks[record_id])
        result[record_id] = {
            "lexical_score": lexical_scores.get(record_id),
            "lexical_rank": lexical_ranks.get(record_id),
            "semantic_score": semantic_scores.get(record_id),
            "semantic_rank": semantic_ranks.get(record_id),
            "fusion_score": score,
        }
    return result


def _hit(record: dict[str, Any], fusion: dict[str, Any], rank: int) -> dict[str, Any]:
    result = {
        "rank": rank,
        "chunk_id": record["chunk_id"],
        "curated_record_id": record["curated_record_id"],
        "document_id": record["document_id"],
        "title": record["title"],
        "text": record["text"],
        "page_start": record["page_start"],
        "page_end": record["page_end"],
        "section_heading": record["section_heading"],
        "source_class": record["source_class"],
        "document_status": record["document_status"],
        "jurisdiction": record["jurisdiction"],
        "jurisdiction_detail": record["jurisdiction_detail"],
        "issuer": record["issuer"],
        "publication_date": record["publication_date"],
        "effective_date": record["effective_date"],
        "version": record["version"],
        "applicable_workflows": record["applicable_workflows"],
        "applicable_domains": record["applicable_domains"],
        "citation": record["citation"],
        "lexical_score": fusion.get("lexical_score"),
        "lexical_rank": fusion.get("lexical_rank"),
        "semantic_score": fusion.get("semantic_score"),
        "semantic_rank": fusion.get("semantic_rank"),
        "fusion_score": fusion.get("fusion_score"),
        "requires_human_review": record["requires_human_review"],
        "verification_status": record["verification_status"],
        "source_path": record["source_path"],
        "record_legal_status": record["record_legal_status"],
        "record_topic": record["record_topic"],
    }
    return result


def _comparison_candidates(groups: dict[str, list[dict[str, Any]]], include_historical: bool) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    current = groups.get("authoritative", [])[:3]
    current_document_ids = list(dict.fromkeys(item["document_id"] for item in current if item["document_id"]))
    if len(current_document_ids) > 1:
        candidates.append(
            {
                "document_ids": current_document_ids,
                "reason": "Multiple current authoritative sources retrieved for the same policy question",
                "requires_human_review": True,
                "comparison_type": "CROSS_SOURCE_COMPARISON_CANDIDATE",
            }
        )
    if include_historical:
        historical = groups.get("historical", [])[:3]
        status_values = {item["document_status"] for item in current + historical}
        historical_ids = list(dict.fromkeys(item["document_id"] for item in historical if item["document_id"]))
        if historical_ids and DocumentStatus.CURRENT.value in status_values:
            candidates.append(
                {
                    "document_ids": current_document_ids + historical_ids,
                    "reason": "Current and proposed/historical versions were deliberately retrieved for comparison",
                    "requires_human_review": True,
                    "comparison_type": "POLICY_VERSION_DIFFERENCE",
                }
            )
    return candidates


def _gaps(
    records: list[dict[str, Any]],
    groups: dict[str, list[dict[str, Any]]],
    filters: dict[str, Any],
    request: RetrievalRequest,
) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    local_authority = filters["local_authority"]
    domain = filters["domains"][0] if filters["domains"] else Domain.PLANNING.value
    if local_authority:
        local_match = [
            record
            for record in records
            if record["source_class"] == SourceClass.PRIMARY.value
            and record["document_status"] == DocumentStatus.CURRENT.value
            and record["jurisdiction"] == Jurisdiction.LOCAL_AUTHORITY.value
            and str(record.get("jurisdiction_detail") or "").casefold() == str(local_authority).casefold()
            and (not filters["domains"] or set(record.get("applicable_domains") or []).intersection(filters["domains"]))
        ]
        if not local_match:
            gaps.append(
                {
                    "type": "NO_AUTHORITATIVE_LOCAL_SOURCE",
                    "domain": domain,
                    "jurisdiction_detail": local_authority,
                    "message": f"No active local-authority {domain} source for {local_authority} is present in the current corpus; another county's local policy was not substituted.",
                }
            )
    if filters["domains"] and not groups.get("authoritative"):
        gaps.append(
            {
                "type": "NO_AUTHORITATIVE_SOURCE",
                "domain": ", ".join(filters["domains"]),
                "jurisdiction_detail": local_authority,
                "message": "No current PRIMARY evidence matched the requested scope and filters.",
            }
        )
    return gaps


def _search_loaded_index(
    loaded_index: LoadedRetrievalIndex,
    request: RetrievalRequest | dict[str, Any],
) -> dict[str, Any]:
    """Search already-validated artifacts without changing retrieval rules."""

    retrieval_request = request if isinstance(request, RetrievalRequest) else RetrievalRequest.model_validate(request)
    if not retrieval_request.query.strip():
        raise ValueError("query must contain non-whitespace text")
    manifest = loaded_index.manifest
    records = loaded_index.records
    lexical_index = loaded_index.lexical_index
    vectors = loaded_index.vectors
    filters = _resolved_filters(retrieval_request)
    allowed_records = [record for record in records if _record_allowed(record, retrieval_request, filters)]
    allowed_ids = {record["record_id"] for record in allowed_records}
    lexical_scores = _bm25_scores(records, lexical_index, retrieval_request.query)
    candidate_count = max(retrieval_request.top_k * CANDIDATE_MULTIPLIER, 50)
    lexical_ranked = _ranked(lexical_scores, allowed_ids)[:candidate_count]
    if vectors is not None and manifest.get("semantic_available") and not loaded_index._embedding_provider_loaded:
        try:
            loaded_index._embedding_provider = make_embedding_provider(manifest.get("embedding_provider"))
        except SemanticUnavailableError:
            loaded_index._embedding_provider = None
        loaded_index._embedding_provider_loaded = True
    semantic_scores, semantic_warning = _semantic_scores(
        records,
        allowed_ids,
        vectors,
        retrieval_request.query,
        manifest,
        loaded_index._embedding_provider,
        loaded_index._embedding_provider_loaded,
    )
    semantic_ranked = _ranked(semantic_scores, allowed_ids)[:candidate_count]
    fused = _fuse(lexical_ranked, semantic_ranked)
    by_id = {record["record_id"]: record for record in allowed_records}

    ordered = sorted(
        ((record_id, score) for record_id, score in fused.items()),
        key=lambda item: (-item[1]["fusion_score"], item[0]),
    )
    candidate_records = [(by_id[record_id], score) for record_id, score in ordered if record_id in by_id]
    grouped_records: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record, score in candidate_records:
        if record["source_class"] == SourceClass.PRIMARY.value and record["document_status"] == DocumentStatus.CURRENT.value:
            group = "authoritative"
        elif record["source_class"] == SourceClass.PRIMARY.value:
            group = "historical"
        elif record["source_class"] == SourceClass.CURATED.value:
            group = "curated"
        else:
            group = "supporting"
        grouped_records[group].append({"record": record, "fusion": score})

    limits = {
        "authoritative": retrieval_request.primary_limit or retrieval_request.top_k,
        "curated": retrieval_request.supporting_limit or retrieval_request.top_k,
        "supporting": retrieval_request.supporting_limit or retrieval_request.top_k,
        "historical": retrieval_request.top_k,
    }
    groups: dict[str, list[dict[str, Any]]] = {}
    for group_name, values in grouped_records.items():
        selected = values[: limits.get(group_name, retrieval_request.top_k)]
        groups[group_name] = [_hit(item["record"], item["fusion"], index) for index, item in enumerate(selected, start=1)]

    warnings: list[str] = []
    if semantic_warning:
        warnings.append(semantic_warning)
    if vectors is None:
        warnings.append("Semantic results are disabled for this index; no embeddings were created or available.")
    if filters["local_authority"] and filters["local_authority"].casefold() == "wicklow":
        warnings.append("Fingal local-authority policy is excluded from this Wicklow scope; a local-policy gap is reported when applicable.")
    ordered_results: list[dict[str, Any]] = []
    for group_name in ("authoritative", "curated", "supporting", "historical"):
        for hit in groups.get(group_name, []):
            copy = dict(hit)
            copy["rank"] = len(ordered_results) + 1
            ordered_results.append(copy)
    result = {
        "query": retrieval_request.query,
        "retrieval_mode": "hybrid" if vectors is not None and not semantic_warning else "lexical",
        "semantic_available": vectors is not None and not semantic_warning,
        "filters_applied": {
            **filters,
            "index_corpus_hash": manifest.get("corpus_hash"),
            "rrf_k": RRF_K,
            "lexical_method": lexical_index.get("method", "BM25"),
            "candidate_multiplier": CANDIDATE_MULTIPLIER,
        },
        "authoritative_results": groups.get("authoritative", []),
        "curated_results": groups.get("curated", []),
        "supporting_results": groups.get("supporting", []),
        "historical_results": groups.get("historical", []),
        "ordered_results": ordered_results,
        "comparison_candidates": _comparison_candidates(groups, retrieval_request.include_historical),
        "gaps": _gaps(records, groups, filters, retrieval_request),
        "warnings": warnings,
        "index": {
            "created_at": manifest.get("index_created_at"),
            "embedding_provider": manifest.get("embedding_provider"),
            "embedding_model": manifest.get("embedding_model"),
            "indexed_records": manifest.get("indexed_records"),
        },
    }
    return result


def search_index(project_root: Path, request: RetrievalRequest | dict[str, Any]) -> dict[str, Any]:
    """Search the local index using deterministic lexical/semantic fusion."""

    return load_retrieval_index(project_root).search(request)


def _evaluation_filter(case: dict[str, Any]) -> dict[str, Any]:
    metadata = case.get("metadata_filter", {}) if isinstance(case.get("metadata_filter"), dict) else {}
    request: dict[str, Any] = {}
    if metadata.get("jurisdiction"):
        jurisdiction = str(metadata["jurisdiction"]).upper().replace("EUROPEAN UNION", "EU")
        request["jurisdiction"] = jurisdiction
    if metadata.get("topic"):
        topics = metadata["topic"] if isinstance(metadata["topic"], list) else [metadata["topic"]]
        topic_domains: list[str] = []
        for topic in topics:
            topic_domains.extend(_topic_domains(topic))
        request["domains"] = sorted(set(topic_domains))
    if metadata.get("legal_status"):
        request["legal_status"] = metadata["legal_status"]
    if "quality_review_required" in metadata:
        request["quality_review_required"] = bool(metadata["quality_review_required"])
    return request


def evaluate_index(project_root: Path) -> dict[str, Any]:
    """Evaluate supported gold IDs from the curated evaluation-case file."""

    cases_path = project_root / "data" / "rag" / "curated" / "ireland_datacentre_screening" / "retrieval_eval_cases.jsonl"
    cases = _json_lines(cases_path)
    case_results: list[dict[str, Any]] = []
    recalls_5: list[float] = []
    recalls_10: list[float] = []
    reciprocal_ranks: list[float] = []
    leakage = {"authoritative_source_hit": [], "historical": [], "restricted_archive": [], "jurisdiction": [], "flagged_claim": []}
    unsupported_gold_cases: list[str] = []
    for case in cases:
        request_payload = {"query": case.get("query_en", ""), **_evaluation_filter(case)}
        response = search_index(project_root, request_payload)
        results = response["ordered_results"]
        result_ids = [item.get("curated_record_id") or item.get("chunk_id") for item in results]
        required = [str(item) for item in case.get("required_record_ids", [])]
        optional = [str(item) for item in case.get("optional_record_ids", [])]
        available_gold = set(result_ids) | set(required) | set(optional)
        if not required and not optional:
            unsupported_gold_cases.append(str(case.get("case_id")))
        else:
            for cutoff, target in ((5, recalls_5), (10, recalls_10)):
                target.append(len(set(required).intersection(result_ids[:cutoff])) / len(required) if required else 0.0)
            first_rank = next((index + 1 for index, item in enumerate(result_ids) if item in required), None)
            reciprocal_ranks.append(1.0 / first_rank if first_rank else 0.0)
        leakage["authoritative_source_hit"].append(bool(response["authoritative_results"]))
        leakage["historical"].append(any(item["document_status"] in {"PROPOSED", "HISTORICAL", "SUPERSEDED"} for item in results))
        leakage["restricted_archive"].append(any(item["source_class"] in {"RESTRICTED", "ARCHIVE"} for item in results))
        requested_jurisdiction = request_payload.get("jurisdiction")
        leakage["jurisdiction"].append(
            bool(requested_jurisdiction and any(not _jurisdiction_allowed(item, requested_jurisdiction) for item in results))
        )
        leakage["flagged_claim"].append(any(item["requires_human_review"] or item["verification_status"] == "REVIEW_REQUIRED" for item in results))
        case_results.append(
            {
                "case_id": case.get("case_id"),
                "required_record_ids": required,
                "optional_record_ids": optional,
                "returned_record_ids": result_ids,
                "required_hits_at_10": sorted(set(required).intersection(result_ids[:10])),
                "metadata_filter_applied": request_payload,
                "unsupported_gold_labels": not bool(required or optional),
            }
        )
    total = len(cases) or 1
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "cases": len(cases),
        "cases_without_explicit_gold_labels": unsupported_gold_cases,
        "Recall at 5": sum(recalls_5) / len(recalls_5) if recalls_5 else None,
        "Recall at 10": sum(recalls_10) / len(recalls_10) if recalls_10 else None,
        "MRR": sum(reciprocal_ranks) / len(reciprocal_ranks) if reciprocal_ranks else None,
        "authoritative_source_hit_rate": sum(leakage["authoritative_source_hit"]) / total,
        "historical_leakage_rate": sum(leakage["historical"]) / total,
        "restricted_archive_leakage_rate": sum(leakage["restricted_archive"]) / total,
        "jurisdiction_leakage_rate": sum(leakage["jurisdiction"]) / total,
        "flagged_claim_leakage_rate": sum(leakage["flagged_claim"]) / total,
        "case_results": case_results,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="INTERLOCK Module 5B authority-aware retrieval tools")
    parser.add_argument("command", choices=("index", "search", "eval"))
    parser.add_argument("--project-root", type=Path, default=Path("."))
    parser.add_argument("--query", default=None)
    parser.add_argument("--workflow", choices=[item.value for item in Workflow], default=None)
    parser.add_argument("--domain", action="append", dest="domains", choices=[item.value for item in Domain], default=[])
    parser.add_argument("--jurisdiction", choices=[item.value for item in Jurisdiction], default=None)
    parser.add_argument("--jurisdiction-detail", default=None)
    parser.add_argument("--local-authority", default=None)
    parser.add_argument("--include-historical", action="store_true")
    parser.add_argument("--include-supporting", action="store_true")
    parser.add_argument("--top-k", type=int, default=8)
    parser.add_argument("--embedding-provider", choices=("openai", "mock", "none"), default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    project_root = args.project_root.resolve()
    try:
        if args.command == "index":
            print(json.dumps(build_index(project_root, args.embedding_provider), indent=2))
        elif args.command == "eval":
            print(json.dumps(evaluate_index(project_root), indent=2))
        else:
            if not args.query:
                raise ValueError("--query is required for search")
            request = RetrievalRequest(
                query=args.query,
                workflow=args.workflow,
                domains=args.domains,
                jurisdiction=args.jurisdiction,
                jurisdiction_detail=args.jurisdiction_detail,
                local_authority=args.local_authority,
                include_historical=args.include_historical,
                include_supporting=args.include_supporting,
                top_k=args.top_k,
            )
            print(json.dumps(search_index(project_root, request), indent=2, ensure_ascii=True))
    except (FileNotFoundError, RetrievalError, ValueError) as exc:
        print(f"Module 5B {args.command} failed: {exc}", file=sys.stderr)
        return 1
    return 0


__all__ = [
    "EmbeddingProvider",
    "DeterministicMockEmbeddingProvider",
    "OpenAIEmbeddingProvider",
    "LoadedRetrievalIndex",
    "IndexNotBuiltError",
    "StaleIndexError",
    "build_index",
    "evaluate_index",
    "main",
    "load_retrieval_index",
    "search_index",
]
