"""Shared registry, coordinate, Parquet-query, and provenance helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from functools import lru_cache
import json
import math
from pathlib import Path
import re
from typing import Any, Iterable, Sequence

from shapely.geometry import Point, mapping

from ...schemas.evidence import (
    EvidenceCategory,
    EvidenceConfidence,
    EvidenceRecord,
    EvidenceReviewStatus,
    EvidenceSourceType,
    EvidenceState,
)
from ...schemas.project import ProjectInput
from ..data.registry import RegistryEntry, load_data_source_config


DEFAULT_RADII_METRES = (1_000.0, 3_000.0, 5_000.0)
NEAREST_SEARCH_RADII_METRES = (5_000.0, 25_000.0, 100_000.0, 500_000.0)


class SiteEvidenceError(RuntimeError):
    """Controlled error raised for an invalid site-evidence request."""


@dataclass(frozen=True)
class DatasetReference:
    """A registry-described generated output, without hardcoded filenames."""

    entry: RegistryEntry
    path: Path
    layer_name: str
    layer_quality: dict[str, Any] = field(default_factory=dict)

    @property
    def queryable(self) -> bool:
        """Only a successfully processed registry entry is evidence-queryable."""

        return self.entry.status == "PROCESSED"


@dataclass(frozen=True)
class SiteEvidenceContext:
    """Immutable inputs shared by every independent evidence domain."""

    project: ProjectInput
    project_root: Path
    point_wgs84: Point
    point_itm: Point
    checked_at: datetime
    target_crs: str
    registry_entries: tuple[RegistryEntry, ...]
    registry_error: str | None = None


@dataclass(frozen=True)
class DomainResult:
    """JSON-safe domain payload plus records to append to Module 3's ledger."""

    payload: dict[str, Any]
    records: tuple[EvidenceRecord, ...] = ()


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp for a single site check."""

    return datetime.now(timezone.utc)


def iso_timestamp(value: datetime) -> str:
    """Serialise timestamps consistently in API payloads."""

    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _load_registry(project_root: Path) -> tuple[tuple[RegistryEntry, ...], str | None]:
    manifest = project_root / "data" / "processed" / "data_registry.json"
    if not manifest.is_file():
        return (), f"Processed dataset registry is unavailable: {manifest}"
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
        return tuple(RegistryEntry.model_validate(item) for item in data), None
    except (OSError, ValueError, TypeError) as exc:
        return (), f"Processed dataset registry could not be read: {exc}"


def _target_crs(project_root: Path) -> str:
    config_path = project_root / "config" / "data_sources.yaml"
    if config_path.is_file():
        try:
            return load_data_source_config(config_path).target_crs
        except (OSError, RuntimeError, ValueError):
            pass
    return "EPSG:2157"


def build_context(project: ProjectInput, project_root: Path | None = None) -> SiteEvidenceContext:
    """Validate the site coordinates and transform them deterministically."""

    if project.latitude is None or project.longitude is None:
        raise SiteEvidenceError("latitude and longitude are required for a site evidence check")
    if not math.isfinite(project.latitude) or not math.isfinite(project.longitude):
        raise SiteEvidenceError("latitude and longitude must be finite numbers")
    if not -90 <= project.latitude <= 90:
        raise SiteEvidenceError("latitude must be between -90 and 90 degrees")
    if not -180 <= project.longitude <= 180:
        raise SiteEvidenceError("longitude must be between -180 and 180 degrees")

    root = (project_root or Path.cwd()).resolve()
    target_crs = _target_crs(root)
    try:
        from pyproj import Transformer

        transformer = Transformer.from_crs("EPSG:4326", target_crs, always_xy=True)
        easting, northing = transformer.transform(project.longitude, project.latitude)
    except (ImportError, RuntimeError, ValueError) as exc:
        raise SiteEvidenceError(f"coordinate transformation to {target_crs} failed: {exc}") from exc

    registry_entries, registry_error = _load_registry(root)
    return SiteEvidenceContext(
        project=project,
        project_root=root,
        point_wgs84=Point(project.longitude, project.latitude),
        point_itm=Point(easting, northing),
        checked_at=utc_now(),
        target_crs=target_crs,
        registry_entries=registry_entries,
        registry_error=registry_error,
    )


def _layer_quality(entry: RegistryEntry, layer_name: str) -> dict[str, Any]:
    layers = entry.quality.get("layers", [])
    for layer in layers:
        if str(layer.get("layer", "")).lower() == layer_name.lower():
            return dict(layer)
    return {}


def dataset_references(
    context: SiteEvidenceContext,
    domain: str,
    *,
    include_ineligible: bool = False,
) -> list[DatasetReference]:
    """Resolve generated outputs from the registry rather than guessed paths."""

    references: list[DatasetReference] = []
    for entry in context.registry_entries:
        if entry.domain != domain:
            continue
        for relative_path in entry.processed_output_paths:
            path = context.project_root / relative_path
            reference = DatasetReference(
                entry=entry,
                path=path,
                layer_name=path.stem,
                layer_quality=_layer_quality(entry, path.stem),
            )
            if include_ineligible or reference.queryable:
                references.append(reference)
    return references


def entry_sources(context: SiteEvidenceContext, domain: str) -> list[RegistryEntry]:
    """Return all registry entries for a domain, including REGISTERED_ONLY files."""

    return [entry for entry in context.registry_entries if entry.domain == domain]


@lru_cache(maxsize=64)
def _read_full_parquet(path_string: str) -> Any:
    import geopandas as gpd

    return gpd.read_parquet(path_string)


@lru_cache(maxsize=96)
def _read_bbox_parquet(path_string: str, bbox: tuple[float, float, float, float]) -> Any:
    import geopandas as gpd

    return gpd.read_parquet(path_string, bbox=bbox)


def _bbox(point: Point, radius_m: float) -> tuple[float, float, float, float]:
    radius = max(float(radius_m), 1.0)
    return (point.x - radius, point.y - radius, point.x + radius, point.y + radius)


def read_candidates(reference: DatasetReference, point: Point, radius_m: float) -> Any:
    """Read only a projected bounding box, falling back safely if unsupported."""

    if not reference.queryable:
        raise SiteEvidenceError(
            f"Dataset is not queryable because registry status is {reference.entry.status}: "
            f"{reference.entry.raw_relative_path}"
        )
    if not reference.path.is_file():
        raise SiteEvidenceError(
            f"Processed registry output is missing: {reference.path}"
        )
    bbox = _bbox(point, radius_m)
    try:
        return _read_bbox_parquet(str(reference.path), bbox)
    except (OSError, RuntimeError, ValueError, TypeError):
        return _read_full_parquet(str(reference.path))


def query_references(
    references: Iterable[DatasetReference],
    point: Point,
    radius_m: float,
) -> Any:
    """Combine local bounding-box candidates from several processed layers."""

    import geopandas as gpd
    import pandas as pd

    frames = [read_candidates(reference, point, radius_m) for reference in references]
    if not frames:
        return pd.DataFrame()
    if len(frames) == 1:
        return frames[0]
    combined = pd.concat(frames, ignore_index=True)
    return gpd.GeoDataFrame(
        combined,
        geometry=frames[0].geometry.name,
        crs=frames[0].crs,
    )


def expanding_candidates(
    references: Sequence[DatasetReference],
    point: Point,
    radii_m: Sequence[float] = NEAREST_SEARCH_RADII_METRES,
) -> Any:
    """Find a bounded local candidate set for nearest-distance evidence."""

    for radius in radii_m:
        candidates = query_references(references, point, radius)
        if len(candidates):
            return candidates
    return query_references(references, point, radii_m[-1]) if radii_m else query_references(references, point, 1)


def _json_value(value: Any) -> Any:
    """Convert pandas/numpy scalar values to JSON-safe values without inventing data."""

    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    try:
        import pandas as pd

        missing = pd.isna(value)
        if isinstance(missing, bool) and missing:
            return None
    except (ImportError, TypeError, ValueError):
        pass
    if hasattr(value, "item"):
        try:
            return _json_value(value.item())
        except (TypeError, ValueError):
            pass
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def row_values(row: Any, fields: Sequence[str]) -> dict[str, Any]:
    """Select only known, non-geometry source fields from a result row."""

    return {
        field_name: _json_value(row[field_name])
        for field_name in fields
        if field_name in row.index
    }


def _distance_frame(frame: Any, point: Point) -> Any:
    if frame.empty:
        return frame.copy()
    result = frame.copy()
    result["distance_m"] = result.geometry.distance(point)
    return result.sort_values("distance_m", kind="stable")


def intersecting_rows(frame: Any, point: Point) -> Any:
    """Return rows whose valid geometry intersects the projected site point."""

    if frame.empty:
        return frame.copy()
    mask = frame.geometry.notna() & ~frame.geometry.is_empty & frame.geometry.intersects(point)
    return frame.loc[mask].copy()


def nearest_row(frame: Any, point: Point) -> Any | None:
    """Return the closest valid geometry row, or None when no candidate exists."""

    ranked = _distance_frame(frame, point)
    if ranked.empty:
        return None
    return ranked.iloc[0]


def records_from_rows(
    rows: Any,
    reference: DatasetReference,
    fields: Sequence[str],
    point: Point,
) -> list[dict[str, Any]]:
    """Attach deterministic distance and source provenance to row values."""

    if rows.empty:
        return []
    ranked = rows.copy()
    if "distance_m" not in ranked.columns:
        ranked = _distance_frame(ranked, point)
    result: list[dict[str, Any]] = []
    for _, row in ranked.iterrows():
        item = row_values(row, fields)
        item["distance_m"] = round(float(row["distance_m"]), 3)
        item.update(source_provenance(reference))
        result.append(item)
    return result


def map_features_from_rows(
    rows: Any,
    reference: DatasetReference,
    point: Point,
    *,
    layer: str,
    fields: Sequence[str] = (),
    limit: int = 30,
) -> list[dict[str, Any]]:
    """Serialize bounded registered geometries to WGS84 GeoJSON features."""

    if rows is None or rows.empty:
        return []
    import geopandas as gpd

    ranked = rows.copy()
    if "distance_m" not in ranked.columns:
        ranked = _distance_frame(ranked, point)
    ranked = ranked.head(max(1, limit))
    source_crs = str(
        getattr(ranked, "crs", None)
        or getattr(getattr(ranked, "geometry", None), "crs", None)
        or "EPSG:2157"
    )
    if not source_crs:
        return []
    geometries = gpd.GeoSeries(ranked.geometry, index=ranked.index, crs=source_crs).to_crs("EPSG:4326")
    provenance = source_provenance(reference)
    features: list[dict[str, Any]] = []
    for index, geometry in geometries.items():
        if geometry is None or geometry.is_empty or not geometry.is_valid:
            continue
        row = ranked.loc[index]
        properties = row_values(row, fields)
        properties.update({
            "layer": layer,
            "distance_m": round(float(row.get("distance_m")), 3) if row.get("distance_m") is not None else None,
            "evidence_maturity": "Deterministic Derived Evidence",
            "source_dataset": provenance.get("source_dataset"),
            "source_reference": provenance.get("source_reference"),
            "source_crs": source_crs,
            "display_note": "Spatial context only; no suitability or capacity conclusion.",
        })
        features.append({
            "type": "Feature",
            "geometry": mapping(geometry),
            "properties": properties,
        })
    return features


def source_provenance(reference: DatasetReference) -> dict[str, Any]:
    """Return source and processing provenance for one generated output."""

    limitations = list(reference.entry.limitations)
    for key in ("warning", "error"):
        value = reference.layer_quality.get(key)
        if value and value not in limitations:
            limitations.append(str(value))
    return {
        "source_dataset": reference.entry.source_name,
        "source_reference": f"{reference.entry.raw_relative_path}::{reference.layer_name}",
        "source_status": reference.entry.status,
        "limitations": list(dict.fromkeys(limitations)),
    }


def source_reference_label(reference: DatasetReference) -> str:
    return f"{reference.entry.raw_relative_path}::{reference.layer_name}"


def layer_return_period(layer_name: str) -> str | None:
    match = re.search(r"_(\d{4})$", layer_name)
    return match.group(1) if match else None


def dedupe_strings(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def evidence_record(
    evidence_id: str,
    field_name: str,
    fact: str,
    value: Any,
    *,
    checked_at: datetime,
    source_name: str,
    source_reference: str | None,
    evidence_state: EvidenceState = EvidenceState.PROVIDED,
    limitation: str | None = None,
    confidence: EvidenceConfidence = EvidenceConfidence.MEDIUM,
) -> EvidenceRecord:
    """Create a Module 3-compatible deterministic evidence record."""

    return EvidenceRecord(
        evidence_id=evidence_id,
        category=EvidenceCategory.SITE,
        field_name=field_name,
        fact=fact,
        value=value,
        unit=None,
        source_type=EvidenceSourceType.DETERMINISTIC_CALCULATION,
        source_name=source_name,
        source_reference=source_reference,
        evidence_state=evidence_state,
        confidence=confidence,
        limitation=limitation,
        review_status=EvidenceReviewStatus.UNREVIEWED,
        checked_at=checked_at,
    )
