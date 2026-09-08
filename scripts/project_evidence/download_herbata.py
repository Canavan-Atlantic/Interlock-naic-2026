"""Download the finite Herbata project-evidence allow-list.

This script discovers only the named documents from the two official listing
pages. It does not crawl the Herbata site and never writes into the Module 5
policy corpus.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
import time
from typing import Any
from urllib.parse import unquote, urljoin, urlparse

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.services.project_evidence.catalog import (  # noqa: E402
    HERBATA_DOCUMENT_ALLOWLIST,
    HERBATA_PROJECT_ID,
)


class LinkParser(HTMLParser):
    """Small HTML parser retaining visible anchor text and hrefs only."""

    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        self._href = dict(attrs).get("href")
        self._text = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._href:
            self.links.append((" ".join(self._text), self._href))
            self._href = None
            self._text = []


def normalise_title(value: str) -> str:
    return " ".join(value.replace("\xa0", " ").split()).casefold()


def discover_document_link(html: str, listing_url: str, title: str) -> str | None:
    """Resolve a named listing anchor without broad site crawling."""

    parser = LinkParser()
    parser.feed(html)
    wanted = normalise_title(title)
    exact = [href for text, href in parser.links if normalise_title(text) == wanted]
    if not exact:
        exact = [
            href
            for text, href in parser.links
            if wanted in normalise_title(text) or normalise_title(text) in wanted
        ]
    return urljoin(listing_url, exact[0]) if exact else None


def _validate_official_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in {"herbatagdc.ie", "www.herbatagdc.ie"}:
        raise RuntimeError("Refusing a non-official Herbata document URL")
    return url


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def safe_filename(title: str, url: str, content_disposition: str | None) -> str:
    if content_disposition:
        match = re.search(r"filename\*?=(?:UTF-8''|\")?([^\";]+)", content_disposition, re.IGNORECASE)
        if match:
            candidate = Path(unquote(match.group(1).strip().strip('"'))).name
            if candidate and candidate.lower().endswith(".pdf"):
                return candidate
    path_name = Path(unquote(urlparse(url).path)).name
    if path_name.lower().endswith(".pdf"):
        return path_name
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", title).strip("-").lower()
    return f"{slug[:100] or 'project-document'}.pdf"


def _request_with_retry(session: requests.Session, url: str, retries: int, sleep_seconds: float) -> requests.Response:
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            response = session.get(url, timeout=60)
            if response.status_code == 200:
                return response
            if response.status_code not in {429, 500, 502, 503, 504}:
                response.raise_for_status()
            last_error = requests.HTTPError(f"HTTP {response.status_code} for {url}")
        except requests.RequestException as exc:
            last_error = exc
        if attempt < retries:
            time.sleep(min(30.0, sleep_seconds * (2**attempt)))
    raise RuntimeError(f"Download failed after {retries + 1} attempts: {url}") from last_error


def download_allowlist(
    project_root: Path,
    *,
    session: requests.Session | None = None,
    sleep_seconds: float = 0.5,
    retries: int = 3,
) -> dict[str, Any]:
    """Discover and download the curated allow-list with safe hash handling."""

    session = session or requests.Session()
    session.headers.update({"User-Agent": "INTERLOCK-project-evidence-downloader/1.0"})
    source_root = project_root / "data" / "project_evidence" / "benchmarks" / "herbata" / "source_documents"
    metadata_root = project_root / "data" / "project_evidence" / "benchmarks" / "herbata" / "metadata"
    source_root.mkdir(parents=True, exist_ok=True)
    metadata_root.mkdir(parents=True, exist_ok=True)
    listing_cache: dict[str, str] = {}
    results: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []

    for spec in HERBATA_DOCUMENT_ALLOWLIST:
        try:
            if spec.listing_url not in listing_cache:
                listing_cache[spec.listing_url] = _request_with_retry(
                    session, spec.listing_url, retries, sleep_seconds
                ).text
            url = discover_document_link(listing_cache[spec.listing_url], spec.listing_url, spec.title)
            discovery_method = "listing_anchor"
            if url is None and spec.direct_url:
                url = spec.direct_url
                discovery_method = "known_official_fallback"
            if url is None:
                raise RuntimeError(f"Required document title was not found on listing page: {spec.title}")
            url = _validate_official_url(url)

            response = _request_with_retry(session, url, retries, sleep_seconds)
            content_type = response.headers.get("content-type", "").split(";", 1)[0].casefold()
            if content_type and content_type not in {"application/pdf", "application/octet-stream"}:
                raise RuntimeError(f"Unexpected content type {content_type!r} for {spec.title}")
            payload = response.content
            digest = sha256_bytes(payload)
            filename = safe_filename(spec.title, url, response.headers.get("content-disposition"))
            relative_dir = "benchmark_only" if spec.benchmark_only else "project_input"
            destination = source_root / relative_dir / filename
            destination.parent.mkdir(parents=True, exist_ok=True)
            action = "downloaded"
            if destination.is_file():
                existing_hash = hashlib.sha256(destination.read_bytes()).hexdigest()
                if existing_hash != digest:
                    raise RuntimeError(f"Refusing to overwrite different existing file: {destination}")
                action = "skipped_identical"
            else:
                destination.write_bytes(payload)
            record = {
                "key": spec.key,
                "project_id": HERBATA_PROJECT_ID,
                "title": spec.title,
                "filename": filename,
                "local_path": destination.relative_to(project_root).as_posix(),
                "source_url": url,
                "listing_url": spec.listing_url,
                "discovery_method": discovery_method,
                "sha256": digest,
                "size_bytes": len(payload),
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
                "classification": spec.classification.value,
                "document_type": spec.document_type,
                "domain": spec.domain.value,
                "benchmark_only": spec.benchmark_only,
                "action": action,
            }
            results.append(record)
            time.sleep(max(0.0, sleep_seconds))
        except Exception as exc:  # noqa: BLE001 - manifest reports each allow-list failure
            failures.append({"key": spec.key, "title": spec.title, "error": str(exc)})

    manifest = {
        "schema_version": 1,
        "project_id": HERBATA_PROJECT_ID,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_listing_pages": sorted(listing_cache),
        "documents": results,
        "failures": failures,
    }
    manifest_path = metadata_root / "download_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if failures:
        raise RuntimeError(f"Herbata download completed with {len(failures)} required-document failure(s): {manifest_path}")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Download the curated Herbata project-evidence allow-list")
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--sleep-seconds", type=float, default=0.5)
    parser.add_argument("--retries", type=int, default=3)
    args = parser.parse_args()
    manifest = download_allowlist(args.project_root.resolve(), sleep_seconds=args.sleep_seconds, retries=args.retries)
    print(json.dumps({"documents": len(manifest["documents"]), "failures": len(manifest["failures"])}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
