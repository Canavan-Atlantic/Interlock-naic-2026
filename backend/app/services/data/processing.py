"""Deterministic raw-data cleaning and spatial standardisation."""

from __future__ import annotations

from datetime import datetime, timezone
import re
from pathlib import Path
import shutil
import tempfile
from typing import Any
import zipfile

from .registry import DataSourceConfig, RegistryEntry
from .validation import ValidationResult, validate_source


class ProcessingError(RuntimeError):
    """A visible, source-specific processing failure."""

    def __init__(self, message: str, quality: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.quality = quality or {}


ZONING_KEEP_COLUMNS = [
    "OBJECTID",
    "GZT Zone",
    "Zone Original",
    "Zone Description",
    "Zone Link",
    "Plan From",
    "Plan To",
    "Plan Name",
    "Color",
    "Local Authority",
    "GZT Description",
    "Link to GZT",
    "Upload Date",
    "Current Plan",
    "Plan Level",
    "Standardised Zoning Objective",
    "Plan ID",
    "LA Name",
]

PLANNING_KEEP_COLUMNS = [
    "OBJECTID",
    "PlanningAuthority",
    "ApplicationNumber",
    "DevelopmentDescription",
    "DevelopmentAddress",
    "DevelopmentPostcode",
    "ApplicationStatus",
    "ApplicationType",
    "Decision",
    "AreaofSite",
    "FloorArea",
    "ReceivedDate",
    "WithdrawnDate",
    "DecisionDate",
    "DecisionDueDate",
    "GrantDate",
    "ExpiryDate",
    "AppealRefNumber",
    "AppealStatus",
    "AppealDecision",
    "AppealDecisionDate",
    "AppealSubmittedDate",
    "FIRequestDate",
    "FIRecDate",
    "LinkAppDetails",
    "ETL_DATE",
]

GRID_KEEP_COLUMNS = [
    "Station Name",
    "Transformer GroupID",
    "Primary kV",
    "Secondary voltage(s)",
    "Voltage Class",
    "Transformer Configuration",
    "Installed Capacity MVA",
    "Demand FirmCapacity MVA",
    "Demand Available MVA",
    "Parent Available MVA",
    "Demand Parent Constraint",
    "Parent Feeder",
    "Parent Station",
    "TSO Interface Station",
    "Comment",
    "Latitude",
    "Longitude",
]

BIODIVERSITY_KEEP_COLUMNS = ["SITECODE", "SITE_NAME", "COUNTY", "HA", "VERSION", "URL"]
FLOOD_KEEP_COLUMNS = ["UUID", "PPPP", "PROJ_NAME", "PROJ_TYPE", "UPLOADED", "VERSION"]
HERITAGE_KEEP_COLUMNS = [
    "ZONE_ID",
    "Shape_Leng",
    "Shape_Area",
    "SMRS",
    "COUNTY",
    "TOWNLAND",
    "MONUMENT_CLASS",
    "ZONE_ID_1",
    "ITM_E",
    "ITM_N",
    "WEBSITE_LINK",
    "ENTITY_ID",
    "CLASS_CODE",
]


def _require_pandas() -> Any:
    try:
        import pandas as pd
    except ImportError as exc:  # pragma: no cover - dependency installation issue
        raise ProcessingError("pandas is required for Module 4A tabular processing") from exc
    return pd


def _require_geopandas() -> Any:
    try:
        import geopandas as gpd
    except ImportError as exc:  # pragma: no cover - dependency installation issue
        raise ProcessingError(
            "geopandas is required for Module 4A spatial processing"
        ) from exc
    return gpd


def _resolve_columns(columns: Any, requested: list[str]) -> tuple[list[str], list[str]]:
    """Resolve requested names case-insensitively without renaming raw fields."""

    available = {str(column).lower(): str(column) for column in columns}
    selected: list[str] = []
    missing: list[str] = []
    for name in requested:
        actual = available.get(name.lower())
        if actual is None:
            missing.append(name)
        elif actual not in selected:
            selected.append(actual)
    return selected, missing


def _crs_label(crs: Any) -> str:
    if crs is None:
        raise ProcessingError("Spatial source CRS could not be determined safely.")
    epsg = crs.to_epsg()
    return f"EPSG:{epsg}" if epsg else str(crs)


def _safe_output_path(output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    return output


def _write_parquet(frame: Any, output: Path) -> None:
    try:
        frame.to_parquet(_safe_output_path(output), index=False)
    except ImportError as exc:  # pragma: no cover - dependency installation issue
        raise ProcessingError(
            "Parquet output requires pyarrow; install Module 4A requirements first."
        ) from exc


def _validate_geometry(gdf: Any) -> dict[str, Any]:
    if gdf.geometry is None:
        raise ProcessingError("Spatial dataset has no geometry column.")

    non_null = gdf.geometry.notna()
    empty_count = int(gdf.geometry.is_empty.fillna(False).sum())
    invalid_count = int((non_null & ~gdf.geometry.is_valid).sum())
    quality = {
        "empty_geometry_count": empty_count,
        "invalid_geometry_count": invalid_count,
    }
    if empty_count or invalid_count:
        raise ProcessingError(
            f"Spatial geometry validation failed: {empty_count} empty and "
            f"{invalid_count} invalid geometries.",
            quality=quality,
        )
    return quality


def _geometry_counts(gdf: Any) -> dict[str, Any]:
    """Collect geometry-quality counts without changing the source frame."""

    non_null = gdf.geometry.notna()
    empty = gdf.geometry.is_empty.fillna(False)
    invalid = non_null & ~empty & ~gdf.geometry.is_valid
    return {
        "feature_count": int(len(gdf)),
        "empty_geometry_count": int(empty.sum()),
        "invalid_geometry_count": int(invalid.sum()),
        "geometry_type": ", ".join(
            sorted({str(value) for value in gdf.geom_type.dropna().unique()})
        ),
    }


def _make_valid(geometry: Any) -> Any:
    """Use the installed Shapely make-valid implementation."""

    try:
        from shapely import make_valid
    except ImportError:
        try:
            from shapely.validation import make_valid
        except ImportError as exc:  # pragma: no cover - dependency installation issue
            raise ProcessingError(
                "Shapely make_valid is required to repair invalid polygon geometry."
            ) from exc
    return make_valid(geometry)


def _polygon_parts(geometry: Any) -> list[Any]:
    """Extract only Polygon/MultiPolygon components from repaired output."""

    from shapely.geometry import GeometryCollection, MultiPolygon, Polygon

    if isinstance(geometry, Polygon):
        return [geometry]
    if isinstance(geometry, MultiPolygon):
        return list(geometry.geoms)
    if isinstance(geometry, GeometryCollection):
        parts: list[Any] = []
        for child in geometry.geoms:
            parts.extend(_polygon_parts(child))
        return parts
    return []


def _polygonal_component(geometry: Any) -> Any | None:
    """Return a usable polygonal component and discard unrelated fragments."""

    from shapely.geometry import MultiPolygon, Polygon
    from shapely.ops import unary_union

    parts = [part for part in _polygon_parts(geometry) if not part.is_empty]
    if not parts:
        return None
    merged = unary_union(parts) if len(parts) > 1 else parts[0]
    if isinstance(merged, (Polygon, MultiPolygon)) and not merged.is_empty:
        return merged
    return None


def _buffer_zero_repair(geometry: Any) -> Any:
    """Deterministic polygon-only fallback for a collapsed make_valid result."""

    return geometry.buffer(0)


def _repair_polygon_geometries(
    gdf: Any,
    *,
    drop_unusable: bool = False,
) -> tuple[Any, dict[str, Any]]:
    """Repair invalid polygon features while keeping only polygonal components."""

    from shapely.geometry import MultiPolygon, Polygon

    before = _geometry_counts(gdf)
    repaired = gdf.copy()
    repaired_geometries = repaired.geometry.copy()
    repaired_geometry_count = 0
    unusable_after_repair_count = 0
    geometry_collection_repair_count = 0
    buffer_zero_fallback_count = 0

    for index, geometry in repaired.geometry.items():
        if geometry is None or geometry.is_empty:
            unusable_after_repair_count += 1
            continue

        if not geometry.is_valid:
            candidate = _make_valid(geometry)
            if candidate.geom_type == "GeometryCollection":
                geometry_collection_repair_count += 1
            polygonal = _polygonal_component(candidate)
            if polygonal is None:
                fallback = _buffer_zero_repair(geometry)
                polygonal = _polygonal_component(fallback)
                if polygonal is not None:
                    buffer_zero_fallback_count += 1
            if polygonal is None:
                unusable_after_repair_count += 1
                repaired_geometries.loc[index] = None
            else:
                repaired_geometries.loc[index] = polygonal
                repaired_geometry_count += 1
        elif not isinstance(geometry, (Polygon, MultiPolygon)):
            # Count valid non-polygon source fragments below with the other
            # post-repair non-polygon results.
            pass

    repaired = repaired.set_geometry(repaired_geometries)
    after = _geometry_counts(repaired)
    non_polygon_count = int(
        sum(
            1
            for geometry in repaired.geometry
            if geometry is not None
            and not geometry.is_empty
            and not isinstance(geometry, (Polygon, MultiPolygon))
        )
    )
    unusable_after_repair_count += non_polygon_count
    usable = repaired.geometry.notna() & ~repaired.geometry.is_empty & repaired.geometry.is_valid
    usable &= repaired.geom_type.isin(["Polygon", "MultiPolygon"])
    dropped_unusable_feature_count = 0
    if drop_unusable and unusable_after_repair_count:
        dropped_unusable_feature_count = int((~usable).sum())
        repaired = repaired.loc[usable].copy()
    output_after = _geometry_counts(repaired)
    quality = {
        "feature_count": before["feature_count"],
        "empty_geometry_count_before": before["empty_geometry_count"],
        "invalid_geometry_count_before": before["invalid_geometry_count"],
        "repair_attempted": before["invalid_geometry_count"] > 0,
        "repaired_geometry_count": repaired_geometry_count,
        "unusable_after_repair_count": unusable_after_repair_count,
        "invalid_geometry_count_after_repair": after["invalid_geometry_count"],
        "empty_geometry_count_after_repair": after["empty_geometry_count"],
        "geometry_collection_repair_count": geometry_collection_repair_count,
        "buffer_zero_fallback_count": buffer_zero_fallback_count,
        "output_geometry_type_after_repair": output_after["geometry_type"],
        "output_feature_count_after_repair": output_after["feature_count"],
        "dropped_unusable_feature_count": dropped_unusable_feature_count,
    }
    if (
        after["invalid_geometry_count"]
        or after["empty_geometry_count"]
        or unusable_after_repair_count
    ) and not drop_unusable:
        raise ProcessingError(
            "Polygon geometry validation failed after deterministic repair.",
            quality=quality,
        )
    if not len(repaired):
        raise ProcessingError(
            "Polygon geometry repair produced no usable polygon features.",
            quality=quality,
        )
    return repaired, quality


def _standardise_geodataframe(
    gdf: Any,
    keep_columns: list[str],
    required_columns: list[str],
    output: Path,
    target_crs: str,
    extra_columns: list[str] | None = None,
    repair_polygon_geometry: bool = False,
) -> dict[str, Any]:
    """Select safe fields, validate geometry, and write EPSG:2157 output."""

    selected, missing = _resolve_columns(gdf.columns, keep_columns)
    _, missing_required = _resolve_columns(gdf.columns, required_columns)
    if missing_required:
        raise ProcessingError(
            f"Missing required spatial columns: {', '.join(missing_required)}",
            quality={"missing_required_columns": missing_required},
        )

    if extra_columns:
        for column in extra_columns:
            if column in gdf.columns and column not in selected:
                selected.append(column)

    source_feature_count = int(len(gdf))
    if repair_polygon_geometry:
        gdf, geometry_quality = _repair_polygon_geometries(gdf, drop_unusable=True)
    else:
        geometry_quality = _validate_geometry(gdf)
    source_crs = _crs_label(gdf.crs)
    selected_frame = gdf[selected + [gdf.geometry.name]].copy()
    selected_frame = selected_frame.to_crs(target_crs)
    transformed_counts = _geometry_counts(selected_frame)
    post_transform_quality: dict[str, Any] = {
        "post_transform_repair_attempted": False,
        "repaired_geometry_count_after_transform": 0,
    }
    if repair_polygon_geometry and transformed_counts["invalid_geometry_count"]:
        try:
            selected_frame, post_repair = _repair_polygon_geometries(
                selected_frame,
                drop_unusable=True,
            )
        except ProcessingError as exc:
            raise ProcessingError(
                str(exc),
                quality={
                    **geometry_quality,
                    "invalid_geometry_count_after_transform": transformed_counts[
                        "invalid_geometry_count"
                    ],
                    "empty_geometry_count_after_transform": transformed_counts[
                        "empty_geometry_count"
                    ],
                    **exc.quality,
                },
            ) from exc
        post_transform_quality = {
            "post_transform_repair_attempted": post_repair["repair_attempted"],
            "repaired_geometry_count_after_transform": post_repair[
                "repaired_geometry_count"
            ],
            "unusable_after_post_transform_repair_count": post_repair[
                "unusable_after_repair_count"
            ],
            "dropped_unusable_feature_count_after_transform": post_repair[
                "dropped_unusable_feature_count"
            ],
            "invalid_geometry_count_after_post_transform_repair": post_repair[
                "invalid_geometry_count_after_repair"
            ],
            "empty_geometry_count_after_post_transform_repair": post_repair[
                "empty_geometry_count_after_repair"
            ],
        }

    final_counts = _geometry_counts(selected_frame)
    if final_counts["empty_geometry_count"] or final_counts["invalid_geometry_count"]:
        raise ProcessingError(
            "Spatial geometry validation failed after CRS transformation and repair.",
            quality={
                **geometry_quality,
                "invalid_geometry_count_after_transform": transformed_counts[
                    "invalid_geometry_count"
                ],
                "empty_geometry_count_after_transform": transformed_counts[
                    "empty_geometry_count"
                ],
                **post_transform_quality,
            },
        )
    _write_parquet(selected_frame, output)

    geometry_types = sorted(
        {str(value) for value in selected_frame.geom_type.dropna().unique()}
    )
    quality = {
        **geometry_quality,
        "feature_count": source_feature_count,
        "output_feature_count": int(len(selected_frame)),
        "invalid_geometry_count_after_transform": transformed_counts[
            "invalid_geometry_count"
        ],
        "empty_geometry_count_after_transform": transformed_counts[
            "empty_geometry_count"
        ],
        "output_geometry_type": ", ".join(geometry_types),
        **post_transform_quality,
        "missing_optional_columns": missing,
        "valid_spatial_bounds": [float(value) for value in selected_frame.total_bounds],
    }
    return {
        "source_crs": source_crs,
        "output_crs": target_crs,
        "row_count": int(len(selected_frame)),
        "feature_count": int(len(selected_frame)),
        "geometry_type": ", ".join(geometry_types),
        "quality": quality,
    }


def _process_zoning_csv(raw_path: Path, output: Path, spec: Any) -> dict[str, Any]:
    pd = _require_pandas()
    frame = pd.read_csv(raw_path, low_memory=False)
    selected, missing_required = _resolve_columns(frame.columns, spec.required_columns)
    if missing_required:
        raise ProcessingError(
            f"Missing required zoning columns: {', '.join(missing_required)}",
            quality={"missing_required_columns": missing_required},
        )

    keep, _ = _resolve_columns(frame.columns, ZONING_KEEP_COLUMNS)
    cleaned = frame[keep].copy()
    _write_parquet(cleaned, output)
    duplicate_plan_ids = 0
    if "Plan ID" in cleaned.columns:
        duplicate_plan_ids = int(cleaned["Plan ID"].duplicated(keep=False).sum())

    return {
        "row_count": int(len(cleaned)),
        "quality": {
            "columns_written": keep,
            "missing_expected_columns": [
                column for column in spec.expected_columns if column not in frame.columns
            ],
            "duplicate_plan_id_values": duplicate_plan_ids,
            "geometry_available": False,
        },
        "limitations": [
            "No polygon geometry was generated from Shape__Area or Shape__Length.",
            "Official MyPlan spatial service retrieval is deferred beyond Module 4A.",
        ],
    }


def _process_planning_geojson(raw_path: Path, output: Path, spec: Any, target_crs: str) -> dict[str, Any]:
    gpd = _require_geopandas()
    gdf = gpd.read_file(raw_path)
    result = _standardise_geodataframe(
        gdf,
        PLANNING_KEEP_COLUMNS,
        spec.required_columns,
        output,
        target_crs,
    )
    result["quality"]["excluded_personal_columns"] = [
        "ApplicantForename",
        "ApplicantSurname",
        "ApplicantAddress",
    ]
    return result


def _process_grid_excel(raw_path: Path, output: Path, spec: Any, target_crs: str) -> dict[str, Any]:
    pd = _require_pandas()
    gpd = _require_geopandas()
    frame = pd.read_excel(raw_path, header=spec.header_row)
    _, missing_required = _resolve_columns(frame.columns, spec.required_columns)
    if missing_required:
        raise ProcessingError(
            f"Missing required grid columns: {', '.join(missing_required)}",
            quality={"missing_required_columns": missing_required},
        )

    latitude_column, _ = _resolve_columns(frame.columns, ["Latitude"])
    longitude_column, _ = _resolve_columns(frame.columns, ["Longitude"])
    lat = pd.to_numeric(frame[latitude_column[0]], errors="coerce")
    lon = pd.to_numeric(frame[longitude_column[0]], errors="coerce")
    valid = lat.between(-90, 90) & lon.between(-180, 180)
    invalid_coordinate_count = int((~valid).sum())
    if not valid.any():
        raise ProcessingError(
            "Grid workbook contains no valid latitude/longitude pairs.",
            quality={"invalid_coordinate_count": invalid_coordinate_count},
        )

    keep, _ = _resolve_columns(frame.columns, GRID_KEEP_COLUMNS)
    cleaned = frame.loc[valid, keep].copy()
    cleaned["Latitude"] = lat.loc[valid].to_numpy()
    cleaned["Longitude"] = lon.loc[valid].to_numpy()
    geometry = gpd.points_from_xy(cleaned["Longitude"], cleaned["Latitude"])
    gdf = gpd.GeoDataFrame(cleaned, geometry=geometry, crs=spec.source_crs)
    result = _standardise_geodataframe(
        gdf,
        keep,
        spec.required_columns,
        output,
        target_crs,
    )
    result["quality"]["invalid_coordinate_count"] = invalid_coordinate_count
    result["processed_output_paths"] = [output]
    return result


def _safe_extract_zip(zip_path: Path, target_dir: Path) -> None:
    """Extract ZIP members only beneath a temporary directory."""

    target_root = target_dir.resolve()
    with zipfile.ZipFile(zip_path) as archive:
        for member in archive.infolist():
            destination = (target_root / member.filename).resolve()
            if target_root not in destination.parents and destination != target_root:
                raise ProcessingError(
                    f"Unsafe ZIP member path rejected: {member.filename}"
                )
            if member.is_dir():
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source, destination.open("wb") as target:
                shutil.copyfileobj(source, target)


def _layer_profile(domain: str, layer_name: str, spec: Any) -> tuple[list[str], list[str]]:
    lower_name = layer_name.lower()
    if domain == "biodiversity":
        return BIODIVERSITY_KEEP_COLUMNS, spec.required_columns
    if domain == "flood":
        return FLOOD_KEEP_COLUMNS, spec.required_columns
    if domain == "heritage":
        return HERITAGE_KEEP_COLUMNS, spec.required_columns
    if domain == "ground":
        if "groundwater" in lower_name or "vulnerability" in lower_name:
            return ["VUL40KID", "VUL_CAT", "VUL_DESC"], ["VUL40KID", "VUL_CAT"]
        if "landform" in lower_name:
            return [
                "KARST40KID",
                "KARST_TYPE",
                "KARST_NAME",
                "XYACCURACY",
                "COUNTY",
                "X_ITM",
                "Y_ITM",
                "DATASOURCE",
            ], ["KARST40KID", "KARST_TYPE"]
        if "traced" in lower_name or "connection" in lower_name:
            return [
                "TLINE40KID",
                "INPUT_SITE",
                "OUTPUTSITE",
                "RESULT",
                "COUNTY",
                "LENGTH_M",
                "GWFLOWRATE",
                "DIRECTION",
            ], ["TLINE40KID"]
    return [], spec.required_columns


def _is_polygon_source(domain: str, layer_name: str) -> bool:
    """Identify ZIP layers whose source geometry is expected to be polygonal."""

    lower_name = layer_name.lower()
    if domain in {"biodiversity", "flood", "heritage"}:
        return True
    if domain == "ground":
        return "groundwater" in lower_name or "vulnerability" in lower_name
    return False


def _flood_identity(layer_name: str, zip_name: str) -> tuple[str, str | None]:
    lower = zip_name.lower()
    flood_type = "coastal" if "ext_c" in lower else "fluvial" if "ext_f" in lower else "unknown"
    match = re.search(r"_(\d{4})$", layer_name)
    return flood_type, match.group(1) if match else None


def _process_spatial_zip(
    raw_path: Path,
    output_dir: Path,
    entry: RegistryEntry,
    spec: Any,
    target_crs: str,
) -> dict[str, Any]:
    gpd = _require_geopandas()
    validation = validate_source(raw_path, spec)
    if not validation.valid:
        raise ProcessingError(
            "; ".join(validation.validation_errors),
            quality=validation.quality,
        )

    output_paths: list[Path] = []
    source_crs_values: set[str] = set()
    geometry_types: set[str] = set()
    total_features = 0
    layer_findings: list[dict[str, Any]] = []

    with tempfile.TemporaryDirectory(prefix="interlock-data-") as temporary:
        extracted = Path(temporary)
        _safe_extract_zip(raw_path, extracted)
        shape_paths = sorted(
            path for path in extracted.rglob("*") if path.is_file() and path.suffix.lower() == ".shp"
        )
        if not shape_paths:
            raise ProcessingError("ZIP contains no readable shapefile layers.")

        for shape_path in shape_paths:
            layer_name = shape_path.stem
            try:
                gdf = gpd.read_file(shape_path)
                keep_columns, required_columns = _layer_profile(entry.domain, layer_name, spec)
                extra_columns: list[str] = []
                if entry.domain == "flood":
                    flood_type, return_period = _flood_identity(layer_name, raw_path.name)
                    gdf["FLOOD_TYPE"] = flood_type
                    gdf["RETURN_PERIOD"] = return_period
                    extra_columns = ["FLOOD_TYPE", "RETURN_PERIOD"]
                gdf["SOURCE_LAYER"] = layer_name
                extra_columns.append("SOURCE_LAYER")
                output = output_dir / entry.dataset_id / f"{layer_name}.parquet"
                result = _standardise_geodataframe(
                    gdf,
                    keep_columns,
                    required_columns,
                    output,
                    target_crs,
                    extra_columns=extra_columns,
                    repair_polygon_geometry=_is_polygon_source(entry.domain, layer_name),
                )
                output_paths.append(output)
                total_features += result["feature_count"] or 0
                source_crs_values.add(result["source_crs"])
                geometry_types.update(result["geometry_type"].split(", "))
                finding = {
                    "layer": layer_name,
                    "status": "processed",
                    **result["quality"],
                }
                dropped = int(
                    finding.get("dropped_unusable_feature_count", 0)
                    + finding.get("dropped_unusable_feature_count_after_transform", 0)
                )
                if dropped:
                    finding["warning"] = (
                        f"{dropped} feature(s) were omitted because no usable polygon "
                        "remained after deterministic repair and reprojection."
                    )
                layer_findings.append(finding)
            except ProcessingError as exc:
                layer_findings.append(
                    {
                        "layer": layer_name,
                        "status": "failed",
                        "error": str(exc),
                        **exc.quality,
                    }
                )

    if not output_paths:
        layer_errors = [
            finding["error"]
            for finding in layer_findings
            if finding["status"] == "failed"
        ]
        raise ProcessingError(
            "No spatial layers were processed successfully: " + "; ".join(layer_errors),
            quality={"layers": layer_findings, "layer_errors": layer_errors},
        )

    processing_warnings = [
        finding["warning"]
        for finding in layer_findings
        if finding.get("warning")
    ]
    return {
        "source_crs": ", ".join(sorted(source_crs_values)),
        "output_crs": target_crs,
        "feature_count": total_features,
        "row_count": total_features,
        "geometry_type": ", ".join(sorted(geometry_types)),
        "processed_output_paths": output_paths,
        "quality": {"layers": layer_findings},
        "processing_errors": [
            finding["error"]
            for finding in layer_findings
            if finding["status"] == "failed"
        ],
        "processing_warnings": processing_warnings,
        "status": "PROCESSED_WITH_WARNINGS" if any(
            finding["status"] == "failed" for finding in layer_findings
        ) else "PROCESSED",
    }


def process_entry(
    entry: RegistryEntry,
    project_root: Path,
    processed_root: Path,
    config: DataSourceConfig,
) -> RegistryEntry:
    """Validate and process one registry entry, retaining visible failures."""

    processed_at = datetime.now(timezone.utc)
    raw_path = project_root / entry.raw_relative_path
    spec = config.find_spec(entry.domain, raw_path.name)
    validation = validate_source(raw_path, spec)
    quality = {**entry.quality, **validation.quality}
    updated = entry.model_copy(
        update={
            "processed_at": processed_at,
            "validation_errors": validation.validation_errors,
            "quality": quality,
        }
    )

    if not validation.valid:
        return updated.model_copy(
            update={
                "status": "VALIDATION_FAILED",
                "processing_errors": list(validation.validation_errors),
            }
        )

    if spec.mode == "register_only":
        return updated.model_copy(update={"status": "REGISTERED_ONLY"})

    try:
        output_base = processed_root / entry.dataset_id
        if spec.mode == "zoning_csv":
            result = _process_zoning_csv(raw_path, output_base.with_suffix(".parquet"), spec)
        elif spec.mode == "planning_geojson":
            result = _process_planning_geojson(
                raw_path,
                output_base.with_suffix(".parquet"),
                spec,
                config.target_crs,
            )
        elif spec.mode == "grid_excel":
            result = _process_grid_excel(
                raw_path,
                (output_base / "grid.parquet"),
                spec,
                config.target_crs,
            )
        elif spec.mode == "spatial_zip":
            result = _process_spatial_zip(
                raw_path,
                processed_root,
                entry,
                spec,
                config.target_crs,
            )
        else:
            return updated.model_copy(update={"status": "REGISTERED_ONLY"})
    except ProcessingError as exc:
        processing_errors = exc.quality.get("layer_errors", [str(exc)])
        return updated.model_copy(
            update={
                "status": "PROCESSING_FAILED",
                "processing_errors": processing_errors,
                "quality": {**quality, **exc.quality},
            }
        )

    raw_outputs = result.get("processed_output_paths")
    if raw_outputs is None:
        raw_outputs = [output_base.with_suffix(".parquet")]
    output_paths = [
        path.relative_to(project_root).as_posix() for path in raw_outputs
    ]
    limitations = list(dict.fromkeys([*entry.limitations, *result.get("limitations", [])]))
    layer_quality = result.get("quality", {}).get("layers", [])
    if any(layer.get("invalid_geometry_count_before", 0) for layer in layer_quality):
        limitations.append(
            "The source contained invalid polygon geometry; the generated copy uses "
            "deterministic make_valid repair and must not be treated as originally clean."
        )
    limitations.extend(result.get("processing_warnings", []))
    limitations = list(dict.fromkeys(limitations))
    return updated.model_copy(
        update={
            "status": result.get("status", "PROCESSED"),
            "source_crs": result.get("source_crs", updated.source_crs),
            "output_crs": result.get("output_crs"),
            "row_count": result.get("row_count"),
            "feature_count": result.get("feature_count"),
            "geometry_type": result.get("geometry_type"),
            "processed_output_path": output_paths[0] if output_paths else None,
            "processed_output_paths": output_paths,
            "limitations": limitations,
            "processing_errors": result.get("processing_errors", []),
            "quality": {**quality, **result.get("quality", {})},
        }
    )


def process_registry(
    entries: list[RegistryEntry],
    project_root: Path,
    processed_root: Path,
    config: DataSourceConfig,
) -> list[RegistryEntry]:
    """Process every discovered entry into the processed tree."""

    return [process_entry(entry, project_root, processed_root, config) for entry in entries]
