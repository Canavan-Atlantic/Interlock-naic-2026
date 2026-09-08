"""Lightweight deterministic validation for raw data sources."""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path
import re
import zipfile
from typing import Any

from .registry import SourceSpec


@dataclass
class ValidationResult:
    """Validation findings that can be copied into registry quality metadata."""

    row_count: int | None = None
    feature_count: int | None = None
    geometry_type: str | None = None
    missing_required_columns: list[str] = field(default_factory=list)
    validation_errors: list[str] = field(default_factory=list)
    quality: dict[str, Any] = field(default_factory=dict)

    @property
    def valid(self) -> bool:
        return not self.validation_errors and not self.missing_required_columns


def _column_findings(
    columns: list[str],
    spec: SourceSpec,
) -> tuple[list[str], list[str]]:
    """Return missing required and missing expected columns."""

    available = set(columns)
    missing_required = [column for column in spec.required_columns if column not in available]
    missing_expected = [column for column in spec.expected_columns if column not in available]
    return missing_required, missing_expected


def validate_csv(path: Path, spec: SourceSpec) -> ValidationResult:
    """Validate CSV headers and count rows without changing the file."""

    with path.open("r", encoding="utf-8-sig", newline="") as source:
        reader = csv.reader(source)
        try:
            headers = next(reader)
        except StopIteration:
            return ValidationResult(validation_errors=["CSV file is empty."])

        row_count = sum(1 for _ in reader)

    missing_required, missing_expected = _column_findings(headers, spec)
    errors = []
    if missing_required:
        errors.append(f"Missing required columns: {', '.join(missing_required)}")

    return ValidationResult(
        row_count=row_count,
        missing_required_columns=missing_required,
        validation_errors=errors,
        quality={
            "columns": headers,
            "missing_expected_columns": missing_expected,
            "duplicate_headers": sorted({header for header in headers if headers.count(header) > 1}),
        },
    )


def validate_geojson(path: Path, spec: SourceSpec) -> ValidationResult:
    """Validate GeoJSON framing without loading a large source twice."""

    try:
        with path.open("r", encoding="utf-8") as source:
            prefix = source.read(2 * 1024 * 1024)
    except OSError as exc:
        return ValidationResult(validation_errors=[f"GeoJSON could not be read: {exc}"])

    if not re.search(r'"type"\s*:\s*"FeatureCollection"', prefix):
        return ValidationResult(validation_errors=["GeoJSON is not a FeatureCollection."])

    return ValidationResult(
        validation_errors=[],
        quality={
            "validation_deferred_to_processing": True,
            "source_size_bytes": path.stat().st_size,
        },
    )


def validate_zip(path: Path, spec: SourceSpec) -> ValidationResult:
    """Validate ZIP readability and shapefile companion availability."""

    try:
        with zipfile.ZipFile(path) as archive:
            members = [member.filename for member in archive.infolist()]
    except (OSError, zipfile.BadZipFile) as exc:
        return ValidationResult(validation_errors=[f"ZIP could not be read: {exc}"])

    shapefile_stems = {
        Path(member).with_suffix("").as_posix().lower()
        for member in members
        if Path(member).suffix.lower() == ".shp"
    }
    missing_companions: list[str] = []
    for stem in sorted(shapefile_stems):
        for extension in (".dbf", ".shx", ".prj"):
            expected = f"{stem}{extension}"
            if expected not in {member.lower() for member in members}:
                missing_companions.append(expected)

    errors = []
    if not shapefile_stems:
        errors.append("ZIP contains no shapefile geometry layer.")
    if missing_companions:
        errors.append(
            "Shapefile companions missing: " + ", ".join(missing_companions[:10])
        )

    return ValidationResult(
        validation_errors=errors,
        quality={
            "zip_member_count": len(members),
            "shapefile_layer_count": len(shapefile_stems),
            "shapefile_layers": sorted(shapefile_stems),
            "missing_shapefile_companions": missing_companions,
        },
    )


def validate_source(path: Path, spec: SourceSpec) -> ValidationResult:
    """Dispatch validation based on configured processing mode."""

    if not path.is_file():
        return ValidationResult(validation_errors=["Raw source file does not exist."])

    if spec.mode == "zoning_csv":
        return validate_csv(path, spec)
    if spec.mode == "planning_geojson":
        return validate_geojson(path, spec)
    if spec.mode == "spatial_zip":
        return validate_zip(path, spec)
    if spec.mode in {"grid_excel", "register_only"}:
        return ValidationResult(
            quality={"validation_deferred_to_processing": spec.mode == "grid_excel"}
        )

    return ValidationResult(
        quality={"validation_note": "No specialised validator configured."}
    )
