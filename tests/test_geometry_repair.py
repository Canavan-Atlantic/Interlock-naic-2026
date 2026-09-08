"""Focused tests for deterministic polygon repair in Module 4A."""

from pathlib import Path

import pytest

geopandas = pytest.importorskip("geopandas")
pytest.importorskip("pyarrow")
from shapely.geometry import GeometryCollection, LineString, Polygon

from backend.app.services.data import processing
from backend.app.services.data.processing import ProcessingError


def invalid_bowtie() -> Polygon:
    return Polygon([(0, 0), (1, 1), (0, 1), (1, 0), (0, 0)])


def polygon_frame(geometry: object) -> object:
    return geopandas.GeoDataFrame(
        {"ZONE_ID": ["fixture-1"]},
        geometry=[geometry],
        crs="EPSG:4326",
    )


def test_invalid_polygon_is_repaired_and_written(tmp_path: Path) -> None:
    frame = polygon_frame(invalid_bowtie())
    output = tmp_path / "repaired.parquet"

    result = processing._standardise_geodataframe(
        frame,
        ["ZONE_ID"],
        ["ZONE_ID"],
        output,
        "EPSG:2157",
        repair_polygon_geometry=True,
    )

    quality = result["quality"]
    assert output.exists()
    assert quality["feature_count"] == 1
    assert quality["invalid_geometry_count_before"] == 1
    assert quality["repair_attempted"] is True
    assert quality["repaired_geometry_count"] == 1
    assert quality["unusable_after_repair_count"] == 0
    assert quality["invalid_geometry_count_after_repair"] == 0
    assert quality["invalid_geometry_count_after_transform"] == 0
    assert result["output_crs"] == "EPSG:2157"

    processed = geopandas.read_parquet(output)
    assert processed.geometry.is_valid.all()
    assert set(processed.geom_type) <= {"Polygon", "MultiPolygon"}


def test_valid_polygon_remains_unchanged() -> None:
    original = Polygon([(0, 0), (0, 1), (1, 1), (1, 0), (0, 0)])
    frame = polygon_frame(original)

    repaired, quality = processing._repair_polygon_geometries(frame)

    assert repaired.geometry.iloc[0].equals(original)
    assert quality["repair_attempted"] is False
    assert quality["repaired_geometry_count"] == 0
    assert quality["invalid_geometry_count_after_repair"] == 0


def test_geometry_collection_keeps_only_polygon_components(monkeypatch: pytest.MonkeyPatch) -> None:
    frame = polygon_frame(invalid_bowtie())
    polygon = Polygon([(0, 0), (0, 1), (1, 1), (1, 0), (0, 0)])

    monkeypatch.setattr(
        processing,
        "_make_valid",
        lambda geometry: GeometryCollection([polygon, LineString([(0, 0), (1, 1)])]),
    )

    repaired, quality = processing._repair_polygon_geometries(frame)

    assert repaired.geometry.iloc[0].geom_type == "Polygon"
    assert quality["geometry_collection_repair_count"] == 1
    assert quality["unusable_after_repair_count"] == 0


def test_repair_statistics_include_before_and_after_counts(tmp_path: Path) -> None:
    frame = geopandas.GeoDataFrame(
        {"ZONE_ID": ["valid", "invalid"]},
        geometry=[
            Polygon([(0, 0), (0, 1), (1, 1), (1, 0), (0, 0)]),
            invalid_bowtie(),
        ],
        crs="EPSG:4326",
    )

    result = processing._standardise_geodataframe(
        frame,
        ["ZONE_ID"],
        ["ZONE_ID"],
        tmp_path / "mixed.parquet",
        "EPSG:2157",
        repair_polygon_geometry=True,
    )

    quality = result["quality"]
    assert quality["feature_count"] == 2
    assert quality["empty_geometry_count_before"] == 0
    assert quality["invalid_geometry_count_before"] == 1
    assert quality["repaired_geometry_count"] == 1
    assert quality["empty_geometry_count_after_repair"] == 0
    assert quality["invalid_geometry_count_after_repair"] == 0
    assert quality["invalid_geometry_count_after_transform"] == 0
    assert set(quality["output_geometry_type"].split(", ")) <= {
        "Polygon",
        "MultiPolygon",
    }


def test_unrecoverable_geometry_fails_without_writing_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frame = polygon_frame(invalid_bowtie())
    output = tmp_path / "should-not-exist.parquet"
    monkeypatch.setattr(
        processing,
        "_make_valid",
        lambda geometry: GeometryCollection([LineString([(0, 0), (1, 1)])]),
    )
    monkeypatch.setattr(processing, "_buffer_zero_repair", lambda geometry: None)

    with pytest.raises(ProcessingError) as error:
        processing._standardise_geodataframe(
            frame,
            ["ZONE_ID"],
            ["ZONE_ID"],
            output,
            "EPSG:2157",
            repair_polygon_geometry=True,
        )

    assert not output.exists()
    assert error.value.quality["unusable_after_repair_count"] == 1
    assert error.value.quality["invalid_geometry_count_before"] == 1


def test_source_frame_is_not_mutated_by_repair() -> None:
    frame = polygon_frame(invalid_bowtie())
    original_wkt = frame.geometry.iloc[0].wkt

    processing._repair_polygon_geometries(frame)

    assert frame.geometry.iloc[0].wkt == original_wkt
