"""Tests for Module 4A deterministic processing using small temporary fixtures."""

from pathlib import Path

from backend.app.services.data.processing import process_entry
from backend.app.services.data.registry import discover_raw_files, load_data_source_config, sha256_file


def write_zoning_config(path: Path) -> None:
    path.write_text(
        """
target_crs: EPSG:2157
domains:
  zoning:
    sources:
      - source_name: Test zoning
        patterns: ["*.csv"]
        mode: zoning_csv
        expected_columns: [OBJECTID, Plan Name, Standardised Zoning Objective]
        required_columns: [OBJECTID, Plan Name]
        limitations: [Test zoning limitation]
""",
        encoding="utf-8",
    )


def test_zoning_processing_is_tabular_and_preserves_raw_hash(tmp_path: Path) -> None:
    project_root = tmp_path
    config_path = project_root / "config.yaml"
    write_zoning_config(config_path)
    raw_path = project_root / "data" / "raw" / "zoning" / "sample.csv"
    raw_path.parent.mkdir(parents=True)
    raw_path.write_text(
        "OBJECTID,Plan Name,Standardised Zoning Objective,Shape__Area,Shape__Length\n"
        "1,Test Plan,Enterprise,123,45\n",
        encoding="utf-8",
    )
    source_hash_before = sha256_file(raw_path)
    config = load_data_source_config(config_path)
    entry = discover_raw_files(project_root, config)[0]

    processed = process_entry(
        entry,
        project_root,
        project_root / "data" / "processed",
        config,
    )

    assert processed.status == "PROCESSED"
    assert processed.row_count == 1
    assert processed.output_crs is None
    assert processed.quality["geometry_available"] is False
    assert processed.processed_output_path is not None
    assert (project_root / processed.processed_output_path).exists()
    assert sha256_file(raw_path) == source_hash_before

    import pandas as pd

    output = pd.read_parquet(project_root / processed.processed_output_path)
    assert "Shape__Area" not in output.columns
    assert "Plan Name" in output.columns
