"""Project-scoped lexical retrieval, separate from Module 5B policy retrieval."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
import re
from typing import Iterable

from .models import ProjectEvidenceChunk, ProjectEvidenceFact


TOKEN_RE = re.compile(r"[a-z0-9]+")


@lru_cache(maxsize=8)
def _read_jsonl_cached(path_text: str, mtime_ns: int, size: int) -> tuple[dict, ...]:
    """Read an unchanged project-evidence artifact once per process."""

    _ = mtime_ns, size
    path = Path(path_text)
    return tuple(json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


class ProjectEvidenceRetriever:
    """Read project evidence only after an explicit project_id is supplied."""

    def __init__(self, project_root: Path, *, benchmark: str = "herbata") -> None:
        self.project_root = project_root.resolve()
        self.processed_dir = self.project_root / "data" / "project_evidence_processed" / benchmark

    def _require_project_id(self, project_id: str) -> str:
        if not isinstance(project_id, str) or not project_id.strip():
            raise ValueError("project_id is required for project evidence retrieval")
        return project_id.strip()

    def _read_jsonl(self, filename: str) -> list[dict]:
        path = self.processed_dir / filename
        if not path.is_file():
            raise FileNotFoundError("Project evidence artifacts are not built; run the project evidence build first")
        stat = path.stat()
        return list(_read_jsonl_cached(str(path), stat.st_mtime_ns, stat.st_size))

    def _check_registry(self, project_id: str) -> bool:
        path = self.processed_dir / "document_registry.json"
        if not path.is_file():
            raise FileNotFoundError("Project evidence document registry is missing; run the project evidence build first")
        registry = json.loads(path.read_text(encoding="utf-8"))
        return registry.get("project_id") == project_id

    @staticmethod
    def _tokens(value: str) -> set[str]:
        return set(TOKEN_RE.findall(value.casefold()))

    def search(
        self,
        project_id: str,
        query: str,
        *,
        include_benchmark: bool = False,
        top_k: int = 10,
        domain: str | None = None,
    ) -> list[ProjectEvidenceChunk]:
        project_id = self._require_project_id(project_id)
        if not query.strip():
            return []
        if not self._check_registry(project_id):
            return []
        wanted = self._tokens(query)
        rows = [ProjectEvidenceChunk.model_validate(row) for row in self._read_jsonl("chunks.jsonl")]
        domain_value = getattr(domain, "value", domain)
        candidates = [row for row in rows if row.project_id == project_id and (include_benchmark or not row.benchmark_only) and (domain_value is None or getattr(row.domain, "value", row.domain) == domain_value)]
        scored: list[tuple[int, str, ProjectEvidenceChunk]] = []
        for row in candidates:
            overlap = len(wanted & self._tokens(row.text))
            if overlap:
                scored.append((overlap, row.chunk_id, row))
        scored.sort(key=lambda item: (-item[0], item[1]))
        return [item[2] for item in scored[:max(1, top_k)]]

    def facts(self, project_id: str, *, include_benchmark: bool = False) -> list[ProjectEvidenceFact]:
        project_id = self._require_project_id(project_id)
        if not self._check_registry(project_id):
            return []
        rows = [ProjectEvidenceFact.model_validate(row) for row in self._read_jsonl("facts.jsonl")]
        return [row for row in rows if row.project_id == project_id and (include_benchmark or not row.benchmark_only)]


__all__ = ["ProjectEvidenceRetriever"]
