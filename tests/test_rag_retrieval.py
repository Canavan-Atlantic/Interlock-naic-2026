"""Synthetic Module 5B retrieval safety and ranking tests."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from backend.app import main as api_main
from backend.app.services.rag.models import RetrievalRequest
from backend.app.services.rag import retrieval as retrieval_module
from backend.app.services.rag.retrieval import (
    EmbeddingBatchError,
    EmbeddingInputTooLargeError,
    OpenAIEmbeddingProvider,
    StaleIndexError,
    build_index,
    evaluate_index,
    search_index,
)


def _document(
    document_id: str,
    source_path: str,
    title: str,
    source_class: str,
    status: str,
    jurisdiction: str,
    *,
    jurisdiction_detail: str | None = None,
    eligible: bool = True,
    domains: list[str] | None = None,
    workflows: list[str] | None = None,
    duplicate_of: str | None = None,
) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "document_id": document_id,
        "title": title,
        "filename": Path(source_path).name,
        "source_path": source_path,
        "sha256": document_id,
        "source_class": source_class,
        "authority_class": source_class,
        "document_status": status,
        "jurisdiction": jurisdiction,
        "jurisdiction_detail": jurisdiction_detail,
        "issuer": title.split(" ")[0],
        "document_type": "TEST_POLICY",
        "publication_date": "2026-01-01",
        "effective_date": "2026-01-01" if status == "CURRENT" else None,
        "version": "v1",
        "retrieval_eligible": eligible,
        "requires_human_review": False,
        "restricted": source_class == "RESTRICTED",
        "confidential": source_class == "RESTRICTED",
        "supersedes_document_id": None,
        "superseded_by_document_id": None,
        "applicable_workflows": workflows or ["SITE_FEASIBILITY", "POLICY_REGULATORY_INTELLIGENCE"],
        "applicable_domains": domains or ["GENERAL"],
        "source_url": None,
        "notes": [],
        "limitations": [],
        "discovered_at": now,
        "processed_at": now,
        "extraction_status": "EXTRACTED",
        "extraction_error": None,
        "page_count": 10,
        "no_text_pages": [],
        "chunk_count": 1,
        "curated_record_count": 0,
        "duplicate_of_document_id": duplicate_of,
        "duplicate_source_paths": [],
    }


def _chunk(chunk_id: str, document: dict, text: str, page: int | None, *, section: str | None = None) -> dict:
    return {
        "chunk_id": chunk_id,
        "document_id": document["document_id"],
        "text": text,
        "page_start": page,
        "page_end": page,
        "section_heading": section,
        "source_class": document["source_class"],
        "document_status": document["document_status"],
        "jurisdiction": document["jurisdiction"],
        "issuer": document["issuer"],
        "publication_date": document["publication_date"],
        "version": document["version"],
        "applicable_workflows": document["applicable_workflows"],
        "applicable_domains": document["applicable_domains"],
        "source_path": document["source_path"],
        "source_reference": {
            "document_id": document["document_id"],
            "source_path": document["source_path"],
            "page_start": page,
            "page_end": page,
            "section_heading": section,
            "paragraph_start": 3 if page is None else None,
            "paragraph_end": 3 if page is None else None,
            "locator": section or (f"page {page}" if page is not None else "paragraph 3"),
        },
        "retrieval_eligible": document["retrieval_eligible"],
        "verification_status": "REGISTERED_SOURCE",
        "requires_human_review": False,
    }


def _curated(record_id: str, document_id: str, *, flagged: bool = False) -> dict:
    flags = [{"flag_id": "FLAG-SYNTHETIC", "source_id": "SRC-FLAGGED", "original_claim": "unsupported claim"}] if flagged else []
    return {
        "record_id": record_id,
        "document_id": document_id,
        "source_path": "data/rag/curated/test/rag_records.jsonl",
        "record": {
            "id": record_id,
            "version": "v1",
            "title": {"en": "Trusted dispatchable policy record" if not flagged else "Flagged unsupported claim"},
            "jurisdiction": "Ireland",
            "topic": "dispatchable_generation",
            "document_type": "regulatory_decision",
            "legal_status": "in_force",
            "authority": "CRU",
            "effective_date": "2026-01-01",
            "content": {
                "en": "Trusted dispatchable storage evidence for a data centre.",
                "retrieval_text": "data centre dispatchable storage 10 MVA CRU requirement",
            },
            "sources": [{
                "source_id": "SRC-FLAGGED" if flagged else "SRC-TRUSTED",
                "publisher": "CRU",
                "title": "CRU decision",
                "publication_date": "2026-01-01",
                "pinpoint": "p. 4",
                "source_tier": "primary",
            }],
            "quality": {"review_required": False, "evidence_level": "primary_official", "confidence": "high"},
        },
        "review_flags": flags,
        "review_flag_status": "MATCHED" if flagged else "NO_DIRECT_FLAG_MATCH",
        "retrieval_eligible": not flagged,
        "verification_status": "REVIEW_REQUIRED" if flagged else "CURATED_RECORD",
        "source_references": [{
            "source_id": "SRC-FLAGGED" if flagged else "SRC-TRUSTED",
            "publisher": "CRU",
            "title": "CRU decision",
            "publication_date": "2026-01-01",
            "pinpoint": "p. 4",
            "source_tier": "primary",
        }],
    }


def _make_project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    output = root / "data/rag_processed"
    output.mkdir(parents=True)
    docs = [
        _document("doc-cru", "data/rag/primary/ireland/cru/current.pdf", "CRU current policy", "PRIMARY", "CURRENT", "IRELAND", domains=["GRID", "ENERGY", "DATA_CENTRE_POLICY"]),
        _document("doc-eirgrid", "data/raw/grid/eirgrid.pdf", "EirGrid current process", "PRIMARY", "CURRENT", "IRELAND", domains=["GRID"]),
        _document("doc-fingal", "data/rag/primary/ireland/planning/local_authority/fingal/plan.pdf", "Fingal local plan", "PRIMARY", "CURRENT", "LOCAL_AUTHORITY", jurisdiction_detail="Fingal", domains=["PLANNING"]),
        _document("doc-eu", "data/rag/primary/eu/energy/directive.pdf", "EU energy directive", "PRIMARY", "CURRENT", "EU", domains=["ENERGY", "EU_REPORTING"]),
        _document("doc-proposed", "data/rag/primary/ireland/cru/historical_proposed/proposed.pdf", "CRU proposed policy", "PRIMARY", "PROPOSED", "IRELAND", domains=["GRID"]),
        _document("doc-public", "data/rag/supporting/public_bodies/grid.pdf", "Public body grid note", "SUPPORTING_PUBLIC_BODY", "SUPPORTING", "IRELAND", domains=["GRID"]),
        _document("doc-industry", "data/rag/supporting/industry/submission.pdf", "Industry submission", "SUPPORTING_INDUSTRY", "SUPPORTING", "IRELAND", domains=["GRID"]),
        _document("doc-research", "data/rag/supporting/research/report.pdf", "Research report", "SUPPORTING_RESEARCH", "SUPPORTING", "IRELAND", domains=["ENERGY"]),
        _document("doc-governance", "data/rag/governance/ai.pdf", "Governance note", "GOVERNANCE", "SUPPORTING", "IRELAND", eligible=False, domains=["RESPONSIBLE_AI"]),
        _document("doc-restricted", "data/rag/restricted/secret.pdf", "Restricted source", "RESTRICTED", "UNKNOWN", "UNKNOWN", eligible=False),
        _document("doc-archive", "data/rag/archive/old.zip", "Archive source", "ARCHIVE", "UNKNOWN", "UNKNOWN", eligible=False),
        _document("doc-curated", "data/rag/curated/test/rag_records.jsonl", "Curated records", "CURATED", "SUPPORTING", "IRELAND", domains=["GRID"]),
    ]
    chunks = [
        _chunk("chunk-cru", docs[0], "Current CRU connection requirement: dispatchable storage must match 10 MVA MIC in Ireland.", 12, section="Current requirement"),
        _chunk("chunk-cru-duplicate", docs[0], "Current CRU connection requirement: dispatchable storage must match 10 MVA MIC in Ireland.", 13),
        _chunk("chunk-eirgrid", docs[1], "EirGrid current connection process and grid capacity assessment for Ireland.", 3),
        _chunk("chunk-fingal", docs[2], "Fingal local planning policy for a data centre in Blanchardstown.", 22),
        _chunk("chunk-eu", docs[3], "EU energy efficiency reporting for data centres above 500 kW.", 4),
        _chunk("chunk-proposed", docs[4], "Proposed CRU connection policy for dispatchable capacity.", 2),
        _chunk("chunk-public", docs[5], "Public body grid capacity context.", 7),
        _chunk("chunk-industry", docs[6], "Industry submission claims about grid connection.", 8),
        _chunk("chunk-research", docs[7], "Research discussion of energy demand.", 9),
        _chunk("chunk-governance", docs[8], "Responsible AI governance material.", 1),
        _chunk("chunk-restricted", docs[9], "Restricted claim that must never be returned.", 1),
        _chunk("chunk-archive", docs[10], "Archived claim that must never be returned.", 1),
        _chunk("chunk-docx", docs[0], "Paragraph provenance without fabricated page number.", None, section="DOCX heading"),
    ]
    (output / "document_registry.json").write_text(json.dumps({"documents": docs}), encoding="utf-8")
    (output / "chunks.jsonl").write_text("\n".join(json.dumps(item) for item in chunks) + "\n", encoding="utf-8")
    curated = [_curated("IE-TRUSTED", "doc-curated"), _curated("IE-FLAGGED", "doc-curated", flagged=True)]
    (output / "curated_records.jsonl").write_text("\n".join(json.dumps(item) for item in curated) + "\n", encoding="utf-8")
    cases = [{
        "case_id": "CASE-1",
        "required_record_ids": ["IE-TRUSTED"],
        "optional_record_ids": [],
        "metadata_filter": {"jurisdiction": "Ireland", "legal_status": ["in_force"]},
        "query_en": "dispatchable storage requirement",
    }]
    eval_path = root / "data/rag/curated/ireland_datacentre_screening"
    eval_path.mkdir(parents=True)
    (eval_path / "retrieval_eval_cases.jsonl").write_text("\n".join(json.dumps(item) for item in cases) + "\n", encoding="utf-8")
    return root


@pytest.fixture()
def indexed_project(tmp_path: Path) -> Path:
    root = _make_project(tmp_path)
    build_index(root, embedding_provider="mock")
    return root


def test_lexical_retrieval_and_exact_pdf_citation(tmp_path: Path) -> None:
    root = _make_project(tmp_path)
    manifest = build_index(root, embedding_provider="none")
    result = search_index(root, {"query": "current CRU dispatchable storage 10 MVA"})
    assert manifest["semantic_available"] is False
    assert result["retrieval_mode"] == "lexical"
    assert result["authoritative_results"][0]["document_id"] == "doc-cru"
    assert result["authoritative_results"][0]["citation"].endswith("p. 12")


def test_semantic_mock_provider_and_hybrid_fusion(indexed_project: Path) -> None:
    result = search_index(indexed_project, {"query": "dispatchable storage"})
    assert result["retrieval_mode"] == "hybrid"
    assert result["semantic_available"] is True
    assert result["ordered_results"][0]["fusion_score"] is not None
    assert result["ordered_results"][0]["semantic_rank"] is not None


def test_openai_unavailable_keeps_lexical_retrieval(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _make_project(tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("INTERLOCK_RAG_EMBEDDING_PROVIDER", raising=False)
    manifest = build_index(root)
    result = search_index(root, {"query": "current CRU connection"})
    assert manifest["embedding_provider"] == "none"
    assert result["semantic_available"] is False
    assert result["authoritative_results"]


def test_current_primary_precedes_curated_and_supporting(indexed_project: Path) -> None:
    result = search_index(indexed_project, {"query": "dispatchable storage"})
    assert result["ordered_results"][0]["source_class"] == "PRIMARY"
    assert all(item["source_class"] != "SUPPORTING_INDUSTRY" for item in result["ordered_results"])


def test_proposed_is_excluded_by_default_and_separated_when_enabled(indexed_project: Path) -> None:
    default = search_index(indexed_project, {"query": "proposed CRU connection policy"})
    historical = search_index(indexed_project, {"query": "proposed CRU connection policy", "include_historical": True})
    assert all(item["document_status"] != "PROPOSED" for item in default["ordered_results"])
    assert any(item["document_status"] == "PROPOSED" for item in historical["historical_results"])
    assert all(item["document_status"] != "PROPOSED" for item in historical["authoritative_results"])


def test_supporting_switch_controls_industry_and_research(indexed_project: Path) -> None:
    default = search_index(indexed_project, {"query": "grid energy"})
    enabled = search_index(indexed_project, {"query": "grid energy", "include_supporting": True})
    assert all(item["source_class"] not in {"SUPPORTING_INDUSTRY", "SUPPORTING_RESEARCH"} for item in default["supporting_results"])
    assert any(item["source_class"] == "SUPPORTING_INDUSTRY" for item in enabled["supporting_results"])


def test_restricted_archive_and_governance_are_not_normal_results(indexed_project: Path) -> None:
    normal = search_index(indexed_project, {"query": "claim governance restricted archive"})
    governance = search_index(indexed_project, {"query": "responsible AI governance", "domains": ["RESPONSIBLE_AI"]})
    assert all(item["source_class"] not in {"RESTRICTED", "ARCHIVE", "GOVERNANCE"} for item in normal["ordered_results"])
    assert all(item["source_class"] != "RESTRICTED" for item in governance["ordered_results"])


def test_flagged_curated_claim_never_leaks(indexed_project: Path) -> None:
    result = search_index(indexed_project, {"query": "unsupported claim"})
    assert all(item.get("curated_record_id") != "IE-FLAGGED" for item in result["ordered_results"])


def test_exact_duplicate_content_is_indexed_once(indexed_project: Path) -> None:
    manifest = json.loads((indexed_project / "data/rag_index/manifest.json").read_text(encoding="utf-8"))
    result = search_index(indexed_project, {"query": "current CRU dispatchable storage"})
    matching = [item for item in result["ordered_results"] if item["text"].startswith("Current CRU connection requirement")]
    assert manifest["indexed_chunks"] == 9
    assert len(matching) == 1


def test_docx_provenance_does_not_fabricate_page_number(indexed_project: Path) -> None:
    result = search_index(indexed_project, {"query": "paragraph provenance"})
    hit = next(item for item in result["ordered_results"] if "DOCX heading" in (item["section_heading"] or ""))
    assert hit["page_start"] is None
    assert "section DOCX heading" in hit["citation"]


def test_jurisdiction_and_eu_relevance_filters(indexed_project: Path) -> None:
    eu = search_index(indexed_project, {"query": "EU energy efficiency", "jurisdiction": "EU"})
    ireland = search_index(indexed_project, {"query": "EU energy efficiency", "jurisdiction": "IRELAND"})
    assert any(item["document_id"] == "doc-eu" for item in eu["authoritative_results"])
    assert any(item["document_id"] == "doc-eu" for item in ireland["authoritative_results"])
    assert all(item["jurisdiction"] == "EU" for item in eu["ordered_results"])


def test_fingal_does_not_leak_into_wicklow_and_gap_is_reported(indexed_project: Path) -> None:
    wicklow = search_index(indexed_project, {"query": "What planning policies apply in Arklow, County Wicklow?", "domains": ["PLANNING"]})
    fingal = search_index(indexed_project, {"query": "What planning policies apply in Blanchardstown, Fingal?", "domains": ["PLANNING"]})
    assert all(item["document_id"] != "doc-fingal" for item in wicklow["ordered_results"])
    assert any(gap["type"] == "NO_AUTHORITATIVE_LOCAL_SOURCE" for gap in wicklow["gaps"])
    assert any(item["document_id"] == "doc-fingal" for item in fingal["authoritative_results"])


def test_workflow_and_domain_filters(indexed_project: Path) -> None:
    result = search_index(indexed_project, RetrievalRequest(query="energy reporting", workflow="SITE_FEASIBILITY", domains=["EU_REPORTING"]))
    assert all("EU_REPORTING" in item["applicable_domains"] for item in result["ordered_results"])
    assert all("SITE_FEASIBILITY" in item["applicable_workflows"] for item in result["ordered_results"])


def test_no_authoritative_source_gap(indexed_project: Path) -> None:
    result = search_index(indexed_project, {"query": "water abstraction policy", "domains": ["WATER"]})
    assert any(gap["type"] == "NO_AUTHORITATIVE_SOURCE" for gap in result["gaps"])


def test_stale_index_detection(indexed_project: Path) -> None:
    chunks = indexed_project / "data/rag_processed/chunks.jsonl"
    chunks.write_text(chunks.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(StaleIndexError):
        search_index(indexed_project, {"query": "grid"})


def test_deterministic_ordering_and_controlled_empty_query(indexed_project: Path) -> None:
    first = search_index(indexed_project, {"query": "grid connection"})
    second = search_index(indexed_project, {"query": "grid connection"})
    assert first["ordered_results"] == second["ordered_results"]
    with pytest.raises(ValueError, match="query must contain"):
        search_index(indexed_project, {"query": "   "})


def test_evaluation_metrics_use_actual_gold_schema(tmp_path: Path) -> None:
    root = _make_project(tmp_path)
    build_index(root, embedding_provider="none")
    evaluation = evaluate_index(root)
    assert evaluation["cases"] == 1
    assert "Recall at 5" in evaluation
    assert "Recall at 10" in evaluation
    assert "MRR" in evaluation
    assert evaluation["flagged_claim_leakage_rate"] == 0.0


def test_read_only_search_api_uses_canonical_request(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _make_project(tmp_path)
    build_index(root, embedding_provider="none")
    monkeypatch.setattr(api_main, "PROJECT_ROOT", root)
    response = api_main.rag_search(RetrievalRequest(query="current CRU connection"))
    assert response["authoritative_results"]
    assert response["authoritative_results"][0]["citation"].endswith("p. 12")


class _MockRateLimitError(RuntimeError):
    def __init__(self, message: str = "simulated rate limit", headers: dict[str, str] | None = None) -> None:
        super().__init__(message)
        self.response = SimpleNamespace(headers=headers or {})


class _MockOpenAIEmbeddingClient:
    def __init__(
        self,
        *,
        fail_on_call: int | None = None,
        failure_secret: str = "",
        rate_limit_calls: set[int] | None = None,
        rate_limit_headers: dict[str, str] | None = None,
    ) -> None:
        self.calls: list[dict[str, object]] = []
        self.fail_on_call = fail_on_call
        self.failure_secret = failure_secret
        self.rate_limit_calls = rate_limit_calls or set()
        self.rate_limit_headers = rate_limit_headers or {}
        self.embeddings = self

    def create(self, *, model: str, input: list[str]) -> SimpleNamespace:
        self.calls.append({"model": model, "input": list(input)})
        if self.fail_on_call == len(self.calls):
            raise RuntimeError(self.failure_secret or "simulated API failure")
        if len(self.calls) in self.rate_limit_calls:
            raise _MockRateLimitError(headers=self.rate_limit_headers)
        data = []
        for index, text in enumerate(input):
            try:
                value = float(int(text.rsplit("-", 1)[1]) + 1)
            except ValueError:
                value = float(index + 1)
            data.append(SimpleNamespace(index=index, embedding=[value, 1.0]))
        return SimpleNamespace(data=list(reversed(data)))


def _mock_openai_provider(client: _MockOpenAIEmbeddingClient) -> OpenAIEmbeddingProvider:
    provider = object.__new__(OpenAIEmbeddingProvider)
    provider.model_name = "text-embedding-3-small"
    provider._client = client
    provider._rate_limit_error = _MockRateLimitError
    provider._encoding = None
    provider._batch_delay_seconds = 0.0
    provider.dimension = None
    return provider


def test_openai_embedding_documents_batches_by_tokens_and_items(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _MockOpenAIEmbeddingClient()
    provider = _mock_openai_provider(client)
    monkeypatch.setattr(retrieval_module, "MAX_BATCH_TOKENS", 12)
    monkeypatch.setattr(retrieval_module, "MAX_BATCH_ITEMS", 2)
    monkeypatch.setattr(provider, "_estimate_token_count", lambda text: len(text))
    texts = ["item-0", "item-1", "item-2", "item-3", "item-4"]

    vectors = provider.embed_documents(texts)

    assert len(client.calls) == 3
    assert all(len(call["input"]) <= 2 for call in client.calls)
    assert all(sum(len(text) for text in call["input"]) <= 12 for call in client.calls)
    assert vectors.shape == (len(texts), 2)
    expected = np.asarray(
        [[float(index + 1), 1.0] for index in range(len(texts))],
        dtype=np.float32,
    )
    expected /= np.linalg.norm(expected, axis=1, keepdims=True)
    assert np.allclose(vectors, expected)


def test_openai_embedding_documents_rejects_one_oversized_input(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = _mock_openai_provider(_MockOpenAIEmbeddingClient())
    monkeypatch.setattr(retrieval_module, "MAX_BATCH_TOKENS", 5)
    monkeypatch.setattr(provider, "_estimate_token_count", lambda text: len(text))

    with pytest.raises(EmbeddingInputTooLargeError, match=r"index 0"):
        provider.embed_documents(["item-000"])


def test_openai_embedding_batch_failure_is_controlled_and_does_not_leak_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    secret = "sk-test-secret-that-must-not-appear"
    client = _MockOpenAIEmbeddingClient(fail_on_call=2, failure_secret=secret)
    provider = _mock_openai_provider(client)
    monkeypatch.setattr(retrieval_module, "MAX_BATCH_TOKENS", 10)
    monkeypatch.setattr(retrieval_module, "MAX_BATCH_ITEMS", 2)
    monkeypatch.setattr(provider, "_estimate_token_count", lambda text: len(text))

    with pytest.raises(EmbeddingBatchError) as error:
        provider.embed_documents(["item-0", "item-1", "item-2", "item-3"])

    captured = capsys.readouterr()
    assert "batch 2" in str(error.value)
    assert secret not in str(error.value)
    assert secret not in captured.out + captured.err

    root = _make_project(tmp_path)
    client.calls.clear()
    monkeypatch.setattr(retrieval_module, "make_embedding_provider", lambda _name: provider)
    with pytest.raises(EmbeddingBatchError):
        build_index(root, embedding_provider="openai")
    assert not (root / "data/rag_index/manifest.json").exists()


def test_openai_rate_limit_retries_same_batch_and_preserves_order(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    client = _MockOpenAIEmbeddingClient(
        rate_limit_calls={1},
        rate_limit_headers={"retry-after": "9"},
    )
    provider = _mock_openai_provider(client)
    waits: list[float] = []
    monkeypatch.setattr(retrieval_module, "MAX_RATE_LIMIT_RETRIES", 3)
    monkeypatch.setattr(retrieval_module, "INITIAL_BACKOFF_SECONDS", 2.0)
    monkeypatch.setattr(retrieval_module, "MAX_BACKOFF_SECONDS", 60.0)
    monkeypatch.setattr(retrieval_module.random, "uniform", lambda _start, _end: 0.0)
    monkeypatch.setattr(retrieval_module.time, "sleep", waits.append)
    caplog.set_level(logging.WARNING, logger=retrieval_module.__name__)

    texts = ["item-0", "item-1", "item-2"]
    vectors = provider.embed_documents(texts)

    assert len(client.calls) == 2
    assert client.calls[0]["input"] == client.calls[1]["input"]
    assert waits == [9.0]
    assert vectors.shape == (3, 2)
    expected = np.asarray([[1.0, 1.0], [2.0, 1.0], [3.0, 1.0]], dtype=np.float32)
    expected /= np.linalg.norm(expected, axis=1, keepdims=True)
    assert np.allclose(vectors, expected)
    assert "batch 1" in caplog.text
    assert "attempt 1/3" in caplog.text
    assert "9.0 seconds" in caplog.text
    assert "item-0" not in caplog.text
    assert "OPENAI_API_KEY" not in caplog.text


def test_openai_rate_limit_retries_stop_after_configured_maximum(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _MockOpenAIEmbeddingClient(rate_limit_calls={1, 2, 3, 4})
    provider = _mock_openai_provider(client)
    waits: list[float] = []
    monkeypatch.setattr(retrieval_module, "MAX_RATE_LIMIT_RETRIES", 3)
    monkeypatch.setattr(retrieval_module, "INITIAL_BACKOFF_SECONDS", 2.0)
    monkeypatch.setattr(retrieval_module.random, "uniform", lambda _start, _end: 0.0)
    monkeypatch.setattr(retrieval_module.time, "sleep", waits.append)

    with pytest.raises(EmbeddingBatchError, match="exhausted rate-limit retries after 3 retries"):
        provider.embed_documents(["item-0", "item-1"])

    assert len(client.calls) == 4
    assert waits == [2.0, 4.0, 8.0]


def test_openai_permanent_error_fails_without_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _MockOpenAIEmbeddingClient(fail_on_call=1, failure_secret="permanent-secret")
    provider = _mock_openai_provider(client)
    waits: list[float] = []
    monkeypatch.setattr(retrieval_module.time, "sleep", waits.append)

    with pytest.raises(EmbeddingBatchError, match="RuntimeError"):
        provider.embed_documents(["item-0", "item-1"])

    assert len(client.calls) == 1
    assert waits == []


def test_rate_limit_exhaustion_preserves_previous_valid_index(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _make_project(tmp_path)
    build_index(root, embedding_provider="mock")
    index_paths = [
        root / "data/rag_index/records.jsonl",
        root / "data/rag_index/lexical_index.json",
        root / "data/rag_index/embeddings.npy",
        root / "data/rag_index/manifest.json",
    ]
    previous_bytes = {path: path.read_bytes() for path in index_paths}

    client = _MockOpenAIEmbeddingClient(rate_limit_calls={1, 2})
    provider = _mock_openai_provider(client)
    monkeypatch.setattr(retrieval_module, "MAX_RATE_LIMIT_RETRIES", 1)
    monkeypatch.setattr(retrieval_module.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(retrieval_module, "make_embedding_provider", lambda _name: provider)

    with pytest.raises(EmbeddingBatchError):
        build_index(root, embedding_provider="openai")

    assert all(path.read_bytes() == previous_bytes[path] for path in index_paths)
