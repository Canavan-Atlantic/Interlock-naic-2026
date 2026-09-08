#!/usr/bin/env python3
"""Convert RAG JSONL payloads from bilingual delivery format to English-only format."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

EVAL_QUERIES = {
    "EVAL-001": "We plan to build a 12 MVA data centre in Ireland. We have no associated battery or generation asset. Can we proceed with a grid connection application?",
    "EVAL-002": "Our data centre has a 5 MVA MIC and has procured a corporate PPA from a UK wind project. Does this meet the renewable electricity requirement?",
    "EVAL-003": "This Dublin site was previously considered grid-constrained. Should we abandon the project immediately?",
    "EVAL-004": "Can we use indigenous Irish biomethane as backup fuel to meet CRU electricity-connection requirements?",
    "EVAL-005": "What EU energy-performance compliance workstreams apply to an operating or planned data centre with 800 kW of installed IT load?",
    "EVAL-006": "If a site is not in a Green Energy Park, is a hyperscale data centre prohibited after 2030?",
}


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, records: list[dict]) -> None:
    path.write_text(
        "\n".join(json.dumps(record, ensure_ascii=False, separators=(",", ":")) for record in records) + "\n",
        encoding="utf-8",
    )


def convert_records() -> None:
    path = ROOT / "data" / "rag_records.jsonl"
    records = load_jsonl(path)
    for record in records:
        record["title"] = {"en": record["title"]["en"]}
        record["content"] = {
            "en": record["content"]["en"],
            "retrieval_text": record["content"]["retrieval_text"].split(". Chinese:")[0].rstrip(".") + ".",
        }
    write_jsonl(path, records)


def convert_eval_cases() -> None:
    path = ROOT / "data" / "retrieval_eval_cases.jsonl"
    cases = load_jsonl(path)
    for case in cases:
        case["query_en"] = EVAL_QUERIES[case["case_id"]]
        case.pop("query_zh", None)
    write_jsonl(path, cases)


if __name__ == "__main__":
    convert_records()
    convert_eval_cases()
    print("Converted RAG records and evaluation queries to English-only format.")
