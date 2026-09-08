"""Tests for Module 4A raw-data inventory and safe source handling."""

from pathlib import Path
import zipfile

from backend.app.services.data.registry import (
    discover_raw_files,
    load_data_source_config,
    sha256_file,
    stable_dataset_id,
)
from backend.app.services.data.validation import validate_csv, validate_zip


def write_test_config(path: Path) -> None:
    path.write_text(
        """
target_crs: EPSG:2157
domains:
  zoning:
    sources:
      - source_name: Test zoning
        patterns: ["*.csv"]
        mode: zoning_csv
        expected_columns: [OBJECTID, Plan Name]
        required_columns: [OBJECTID, Plan Name]
  grid:
    sources:
      - source_name: Test document
        patterns: ["*.pdf"]
        mode: register_only
        limitations: [Deferred test document]
""",
        encoding="utf-8",
    )


def test_registry_discovers_files_with_stable_ids_and_hashes(tmp_path: Path) -> None:
    project_root = tmp_path
    config_path = project_root / "config.yaml"
    write_test_config(config_path)
    raw_root = project_root / "data" / "raw"
    (raw_root / "zoning").mkdir(parents=True)
    (raw_root / "grid").mkdir(parents=True)
    csv_path = raw_root / "zoning" / "sample.csv"
    csv_path.write_text("OBJECTID,Plan Name\n1,Test Plan\n", encoding="utf-8")
    pdf_path = raw_root / "grid" / "policy.pdf"
    pdf_path.write_bytes(b"test pdf placeholder")
    (raw_root / ".gitkeep").write_text("", encoding="utf-8")

    config = load_data_source_config(config_path)
    entries = discover_raw_files(project_root, config)
    repeated_entries = discover_raw_files(project_root, config)

    assert [entry.raw_relative_path for entry in entries] == [
        "data/raw/grid/policy.pdf",
        "data/raw/zoning/sample.csv",
    ]
    assert [entry.dataset_id for entry in entries] == [
        entry.dataset_id for entry in repeated_entries
    ]
    zoning_entry = next(entry for entry in entries if entry.domain == "zoning")
    assert zoning_entry.source_name == "Test zoning"
    assert zoning_entry.file_type == "csv"
    assert zoning_entry.sha256 == sha256_file(csv_path)
    assert stable_dataset_id(zoning_entry.raw_relative_path, "zoning") == zoning_entry.dataset_id
    assert next(entry for entry in entries if entry.domain == "grid").status == "REGISTERED_ONLY"


def test_csv_validation_reports_rows_and_missing_expected_columns(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    write_test_config(config_path)
    config = load_data_source_config(config_path)
    spec = config.find_spec("zoning", "sample.csv")
    csv_path = tmp_path / "sample.csv"
    csv_path.write_text("OBJECTID,Plan Name\n1,Test Plan\n", encoding="utf-8")

    result = validate_csv(csv_path, spec)

    assert result.valid
    assert result.row_count == 1
    assert result.quality["missing_expected_columns"] == []


def test_zip_validation_requires_spatial_companions(tmp_path: Path) -> None:
    zip_path = tmp_path / "sample.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("sample.shp", b"not a real shapefile")
    config_path = tmp_path / "config.yaml"
    write_test_config(config_path)
    config = load_data_source_config(config_path)
    spec = config.find_spec("zoning", "sample.zip")

    result = validate_zip(zip_path, spec)

    assert not result.valid
    assert any("companions" in error for error in result.validation_errors)
