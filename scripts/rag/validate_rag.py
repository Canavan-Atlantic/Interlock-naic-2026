#!/usr/bin/env python3
"""Validate the Ireland data-centre RAG package without external dependencies."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECORDS_PATH = ROOT / "data" / "rag_records.jsonl"
FLAGS_PATH = ROOT / "data" / "review_flags.jsonl"
SOURCES_PATH = ROOT / "sources" / "source_registry.json"

REQUIRED_RECORD_FIELDS = {
    "id", "version", "title", "jurisdiction", "topic", "document_type",
    "legal_status", "authority", "applicability", "screening_logic", "content",
    "sources", "quality", "last_verified",
}
REQUIRED_FLAG_FIELDS = {
    "flag_id", "source_id", "original_claim", "classification", "risk",
    "why_flagged", "production_treatment", "official_sources", "status", "last_reviewed",
}


def load_jsonl(path: Path) -> list[dict]:
    records: list[dict] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path.name}:{line_number}: invalid JSON: {exc.msg}") from exc
        if not isinstance(value, dict):
            raise ValueError(f"{path.name}:{line_number}: each JSONL row must be an object")
        records.append(value)
    return records


def fail(errors: list[str], message: str) -> None:
    errors.append(message)


def main() -> int:
    errors: list[str] = []
    sources = json.loads(SOURCES_PATH.read_text(encoding="utf-8"))
    source_ids = {source["source_id"] for source in sources}
    if len(source_ids) != len(sources):
        fail(errors, "Duplicate source_id in source_registry.json")

    records = load_jsonl(RECORDS_PATH)
    record_ids: set[str] = set()
    for index, record in enumerate(records, start=1):
        missing = REQUIRED_RECORD_FIELDS - record.keys()
        if missing:
            fail(errors, f"rag_records row {index} missing fields: {sorted(missing)}")
        record_id = record.get("id")
        if record_id in record_ids:
            fail(errors, f"Duplicate RAG record id: {record_id}")
        record_ids.add(record_id)
        title = record.get("title", {})
        content = record.get("content", {})
        if not {"en"}.issubset(title):
            fail(errors, f"{record_id}: title must contain English")
        if not {"en", "retrieval_text"}.issubset(content):
            fail(errors, f"{record_id}: content must contain English and retrieval_text")
        if record.get("quality", {}).get("review_required") is False and record.get("quality", {}).get("evidence_level") != "primary_official":
            fail(errors, f"{record_id}: non-review record must use primary_official evidence")
        for source in record.get("sources", []):
            source_id = source.get("source_id")
            if source_id not in source_ids:
                fail(errors, f"{record_id}: unknown source_id {source_id}")
            if source.get("source_tier") != "primary":
                fail(errors, f"{record_id}: production RAG record cites non-primary source {source_id}")

    flags = load_jsonl(FLAGS_PATH)
    flag_ids: set[str] = set()
    for index, flag in enumerate(flags, start=1):
        missing = REQUIRED_FLAG_FIELDS - flag.keys()
        if missing:
            fail(errors, f"review_flags row {index} missing fields: {sorted(missing)}")
        flag_id = flag.get("flag_id")
        if flag_id in flag_ids:
            fail(errors, f"Duplicate review flag id: {flag_id}")
        flag_ids.add(flag_id)
        if flag.get("source_id") not in source_ids:
            fail(errors, f"{flag_id}: unknown originating source {flag.get('source_id')}")
        for source_id in flag.get("official_sources", []):
            if source_id not in source_ids:
                fail(errors, f"{flag_id}: unknown official source {source_id}")

    if errors:
        print("VALIDATION FAILED")
        print("\n".join(f"- {error}" for error in errors))
        return 1

    status_counts: dict[str, int] = {}
    topic_counts: dict[str, int] = {}
    for record in records:
        status_counts[record["legal_status"]] = status_counts.get(record["legal_status"], 0) + 1
        topic_counts[record["topic"]] = topic_counts.get(record["topic"], 0) + 1
    print("VALIDATION PASSED")
    print(f"RAG records: {len(records)}")
    print(f"Review flags: {len(flags)}")
    print(f"Registered sources: {len(sources)}")
    print("Legal-status counts:", json.dumps(status_counts, ensure_ascii=False, sort_keys=True))
    print("Topic counts:", json.dumps(topic_counts, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
