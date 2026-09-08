"""Raw data inventory and registry metadata."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import fnmatch
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from pydantic import BaseModel, Field


class SourceSpec(BaseModel):
    """Configuration for one source family in a raw-data domain."""

    domain: str
    source_name: str
    patterns: list[str] = Field(default_factory=list)
    mode: str = "register_only"
    source_crs: str | None = None
    header_row: int = 0
    expected_columns: list[str] = Field(default_factory=list)
    required_columns: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class RegistryEntry(BaseModel):
    """Traceable metadata for one immutable raw source file."""

    dataset_id: str
    domain: str
    source_name: str
    processing_mode: str
    raw_relative_path: str
    file_type: str
    file_size: int
    sha256: str
    discovered_at: datetime
    processed_at: datetime | None = None
    source_crs: str | None = None
    output_crs: str | None = None
    row_count: int | None = None
    feature_count: int | None = None
    geometry_type: str | None = None
    processed_output_path: str | None = None
    processed_output_paths: list[str] = Field(default_factory=list)
    status: str = "DISCOVERED"
    limitations: list[str] = Field(default_factory=list)
    validation_errors: list[str] = Field(default_factory=list)
    processing_errors: list[str] = Field(default_factory=list)
    quality: dict[str, Any] = Field(default_factory=dict)


@dataclass(frozen=True)
class DataSourceConfig:
    """Loaded registry configuration."""

    target_crs: str
    specs: tuple[SourceSpec, ...]

    def find_spec(self, domain: str, filename: str) -> SourceSpec:
        """Find the most specific configured source for a raw filename."""

        filename_lower = filename.lower()
        matching = [
            spec
            for spec in self.specs
            if spec.domain == domain
            and any(fnmatch.fnmatch(filename_lower, pattern.lower()) for pattern in spec.patterns)
        ]
        if matching:
            return matching[0]

        return SourceSpec(
            domain=domain,
            source_name=f"Unclassified {domain} raw source",
            mode="register_only",
            limitations=["No configured Module 4A processor matched this file."],
        )


def load_data_source_config(config_path: Path) -> DataSourceConfig:
    """Load the YAML registry configuration."""

    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - dependency installation issue
        raise RuntimeError("PyYAML is required to load config/data_sources.yaml") from exc

    config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    specs: list[SourceSpec] = []
    for domain, domain_config in config.get("domains", {}).items():
        for source in domain_config.get("sources", []):
            specs.append(SourceSpec(domain=domain, **source))

    return DataSourceConfig(
        target_crs=config.get("target_crs", "EPSG:2157"),
        specs=tuple(specs),
    )


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    """Calculate a streaming SHA-256 hash without modifying the source."""

    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def stable_dataset_id(raw_relative_path: str, domain: str) -> str:
    """Create a stable identifier from the normalised relative source path."""

    normalised = raw_relative_path.replace("\\", "/").lower()
    stem = Path(normalised).stem
    slug = re.sub(r"[^a-z0-9]+", "-", stem).strip("-") or "dataset"
    path_hash = hashlib.sha1(normalised.encode("utf-8")).hexdigest()[:12]
    return f"{domain}-{slug}-{path_hash}"


def discover_raw_files(
    project_root: Path,
    config: DataSourceConfig,
    raw_root: Path | None = None,
) -> list[RegistryEntry]:
    """Recursively inventory raw files without writing into the raw tree."""

    raw_root = raw_root or project_root / "data" / "raw"
    discovered_at = datetime.now(timezone.utc)
    entries: list[RegistryEntry] = []

    for path in sorted(raw_root.rglob("*")):
        if not path.is_file() or path.name == ".gitkeep":
            continue

        relative_to_raw = path.relative_to(raw_root)
        domain = relative_to_raw.parts[0].lower() if relative_to_raw.parts else "other"
        spec = config.find_spec(domain, path.name)
        raw_relative_path = path.relative_to(project_root).as_posix()
        entries.append(
            RegistryEntry(
                dataset_id=stable_dataset_id(raw_relative_path, domain),
                domain=domain,
                source_name=spec.source_name,
                processing_mode=spec.mode,
                raw_relative_path=raw_relative_path,
                file_type=path.suffix.lower().lstrip(".") or "unknown",
                file_size=path.stat().st_size,
                sha256=sha256_file(path),
                discovered_at=discovered_at,
                status="REGISTERED_ONLY" if spec.mode == "register_only" else "DISCOVERED",
                source_crs=spec.source_crs,
                limitations=list(spec.limitations),
                quality={"raw_file_exists": True, "raw_file_immutable": True},
            )
        )

    return entries


def write_registry_manifest(entries: list[RegistryEntry], manifest_path: Path) -> None:
    """Write registry metadata as JSON under the processed-output tree."""

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    payload = [entry.model_dump(mode="json") for entry in entries]
    manifest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
