"""Synthetic Module 4B site-evidence tests; no production datasets are required."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

geopandas = pytest.importorskip("geopandas")
pytest.importorskip("pyarrow")
from pyproj import Transformer
from shapely.geometry import LineString, Point, Polygon
from fastapi.testclient import TestClient

import backend.app.main as main_module
from backend.app.schemas.project import ProjectInput
from backend.app.services.data.registry import RegistryEntry
from backend.app.services.site_evidence.base import build_context
from backend.app.services.site_evidence.service import SiteEvidenceOptions, evaluate_site


PROJECT = ProjectInput(
    project_name="Synthetic site",
    project_stage="Early Feasibility",
    latitude=53.3879,
    longitude=-6.3750,
)


def _square(x: float, y: float, radius: float) -> Polygon:
    return Polygon(
        [
            (x - radius, y - radius),
            (x - radius, y + radius),
            (x + radius, y + radius),
            (x + radius, y - radius),
            (x - radius, y - radius),
        ]
    )


def _entry(
    root: Path,
    domain: str,
    raw_relative_path: str,
    output_name: str,
    frame: object | None,
    *,
    status: str = "PROCESSED",
    source_name: str | None = None,
) -> RegistryEntry:
    output_paths: list[str] = []
    if frame is not None:
        output = root / "data" / "processed" / output_name
        output.parent.mkdir(parents=True, exist_ok=True)
        frame.to_parquet(output, index=False)
        output_paths = [output.relative_to(root).as_posix()]
    return RegistryEntry(
        dataset_id=f"synthetic-{domain}-{output_name.replace('/', '-').replace('.', '-')}",
        domain=domain,
        source_name=source_name or f"Synthetic {domain} source",
        processing_mode="spatial_zip" if domain in {"flood", "ground", "heritage", "biodiversity"} else "register_only",
        raw_relative_path=raw_relative_path,
        file_type="zip" if raw_relative_path.endswith(".zip") else "pdf",
        file_size=1,
        sha256="0" * 64,
        discovered_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        status=status,
        processed_output_paths=output_paths,
    )


@pytest.fixture()
def synthetic_site(tmp_path: Path) -> dict[str, object]:
    root = tmp_path
    root.joinpath("data", "processed").mkdir(parents=True)
    transformer = Transformer.from_crs("EPSG:4326", "EPSG:2157", always_xy=True)
    x, y = transformer.transform(PROJECT.longitude, PROJECT.latitude)

    polygon_kwargs = {"crs": "EPSG:2157"}
    entries = [
        _entry(
            root,
            "biodiversity",
            "data/raw/biodiversity/sac.zip",
            "sac/sac_onshore.parquet",
            geopandas.GeoDataFrame(
                {"SITECODE": ["SAC-1"], "SITE_NAME": ["Synthetic SAC"]},
                geometry=[_square(x, y, 100)],
                **polygon_kwargs,
            ),
        ),
        _entry(
            root,
            "biodiversity",
            "data/raw/biodiversity/spa.zip",
            "spa/spa_onshore.parquet",
            geopandas.GeoDataFrame(
                {"SITECODE": ["SPA-1"], "SITE_NAME": ["Synthetic SPA"]},
                geometry=[_square(x + 2_000, y, 100)],
                **polygon_kwargs,
            ),
        ),
        _entry(
            root,
            "flood",
            "data/raw/flood/esds_floodmap_ext_c_c.zip",
            "flood/coastal_0010.parquet",
            geopandas.GeoDataFrame(
                {"UUID": ["C-1"], "PROJ_NAME": ["Coastal test"]},
                geometry=[_square(x, y, 50)],
                **polygon_kwargs,
            ),
        ),
        _entry(
            root,
            "flood",
            "data/raw/flood/esds_floodmap_ext_f_c.zip",
            "flood/fluvial_0100.parquet",
            geopandas.GeoDataFrame(
                {"UUID": ["F-1"], "PROJ_NAME": ["Fluvial test"]},
                geometry=[_square(x + 4_000, y, 50)],
                **polygon_kwargs,
            ),
        ),
        _entry(
            root,
            "planning",
            "data/raw/planning/applications.geojson",
            "planning/applications.parquet",
            geopandas.GeoDataFrame(
                {
                    "ApplicationNumber": ["A-1", "A-2", "A-3"],
                    "PlanningAuthority": ["Synthetic Council"] * 3,
                    "DevelopmentDescription": ["Test one", "Test two", "Test three"],
                    "DevelopmentAddress": ["Address one", "Address two", "Address three"],
                    "ApplicationStatus": ["Received"] * 3,
                    "ApplicationType": ["Permission"] * 3,
                    "Decision": [None, None, "Granted"],
                    "ReceivedDate": ["2026-01-01"] * 3,
                    "LinkAppDetails": ["https://example.test/a"] * 3,
                    "ApplicantForename": ["Private"] * 3,
                    "ApplicantSurname": ["Person"] * 3,
                    "ApplicantAddress": ["Private address"] * 3,
                },
                geometry=[Point(x + 500, y), Point(x + 2_000, y), Point(x + 6_000, y)],
                **polygon_kwargs,
            ),
        ),
        _entry(
            root,
            "heritage",
            "data/raw/heritage/smr.zip",
            "heritage/smr.parquet",
            geopandas.GeoDataFrame(
                {"ZONE_ID": ["SMR-1"]},
                geometry=[_square(x, y, 75)],
                **polygon_kwargs,
            ),
        ),
        _entry(
            root,
            "ground",
            "data/raw/ground/vulnerability.zip",
            "ground/vulnerability.parquet",
            geopandas.GeoDataFrame(
                {"VUL40KID": ["V-1", "V-2"], "VUL_CAT": ["H", "M"], "VUL_DESC": ["High", "Medium"]},
                geometry=[_square(x, y, 100), _square(x, y, 60)],
                **polygon_kwargs,
            ),
        ),
        _entry(
            root,
            "ground",
            "data/raw/ground/karst.zip",
            "ground/karst_landforms.parquet",
            geopandas.GeoDataFrame(
                {
                    "KARST40KID": ["K-1", "K-2"],
                    "KARST_TYPE": ["Cave", "Swallow hole"],
                    "KARST_NAME": ["Near", "Far"],
                    "XYACCURACY": ["1m", "2m"],
                    "COUNTY": ["Dublin", "Dublin"],
                    "DATASOURCE": ["Synthetic", "Synthetic"],
                },
                geometry=[Point(x + 1_000, y), Point(x + 4_000, y)],
                **polygon_kwargs,
            ),
        ),
        _entry(
            root,
            "ground",
            "data/raw/ground/karst.zip",
            "ground/traced_connections.parquet",
            geopandas.GeoDataFrame(
                {
                    "INPUT_SITE": ["Input"],
                    "OUTPUTSITE": ["Output"],
                    "RESULT": ["Connected"],
                    "COUNTY": ["Dublin"],
                    "LENGTH_M": [500.0],
                    "GWFLOWRATE": [1.5],
                    "DIRECTION": ["North"],
                },
                geometry=[LineString([(x - 100, y), (x + 100, y)])],
                **polygon_kwargs,
            ),
        ),
        _entry(
            root,
            "grid",
            "data/raw/grid/heatmap.xlsx",
            "grid/heatmap.parquet",
            geopandas.GeoDataFrame(
                {
                    "Station Name": ["Near HV", "Near LV"],
                    "Transformer GroupID": ["TG-1", "TG-2"],
                    "Primary kV": [110, 11],
                    "Secondary voltage(s)": ["20", "0.4"],
                    "Voltage Class": ["HV", "LV"],
                    "Transformer Configuration": ["Test", "Test"],
                    "Installed Capacity MVA": [100, 10],
                    "Demand FirmCapacity MVA": [50, 5],
                    "Demand Available MVA": [25, 2],
                    "Parent Available MVA": [20, 1],
                    "Demand Parent Constraint": ["No", "No"],
                    "Parent Feeder": ["F1", "F2"],
                    "Parent Station": ["P1", "P2"],
                    "TSO Interface Station": ["T1", "T2"],
                    "Comment": ["Indicative", "Indicative"],
                },
                geometry=[Point(x + 500, y), Point(x + 1_500, y)],
                **polygon_kwargs,
            ),
        ),
        _entry(
            root,
            "zoning",
            "data/raw/zoning/gzt.csv",
            "zoning/gzt.parquet",
            None,
            source_name="Synthetic GZT tabular source",
        ),
    ]
    for filename in (
        "data/raw/water/water.pdf",
        "data/raw/water/wastewater.pdf",
        "data/raw/grid/eirgrid-policy.pdf",
    ):
        path = root / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"registered only")
    entries.extend(
        [
            _entry(root, "water", "data/raw/water/water.pdf", "ignored", None, status="REGISTERED_ONLY"),
            _entry(root, "water", "data/raw/water/wastewater.pdf", "ignored", None, status="REGISTERED_ONLY"),
            _entry(root, "grid", "data/raw/grid/eirgrid-policy.pdf", "ignored", None, status="REGISTERED_ONLY", source_name="Synthetic EirGrid policy"),
        ]
    )
    (root / "data" / "processed" / "data_registry.json").write_text(
        json.dumps([entry.model_dump(mode="json") for entry in entries], indent=2),
        encoding="utf-8",
    )
    return {"root": root, "project": PROJECT, "entries": entries}


def _result(fixture: dict[str, object], options: SiteEvidenceOptions | None = None):
    return evaluate_site(fixture["project"], fixture["root"], options)


def test_wgs84_coordinates_transform_to_epsg_2157(synthetic_site: dict[str, object]) -> None:
    response = _result(synthetic_site)
    location = response.project_location
    assert location["input_crs"] == "EPSG:4326"
    assert location["transformed_crs"] == "EPSG:2157"
    assert location["easting"] > 0
    assert location["northing"] > 0


def test_polygon_intersection_true(synthetic_site: dict[str, object]) -> None:
    response = _result(synthetic_site)
    assert response.biodiversity["sac"]["intersects"] is True


def test_polygon_intersection_false(synthetic_site: dict[str, object]) -> None:
    response = _result(synthetic_site)
    fluvial = response.flood["fluvial"][0]
    assert fluvial["project_point_intersects"] is False


def test_nearest_polygon_distance_is_returned(synthetic_site: dict[str, object]) -> None:
    response = _result(synthetic_site)
    nearest = response.biodiversity["spa"]["nearest_protected_site"]
    assert nearest["SITE_NAME"] == "Synthetic SPA"
    assert 1_800 < nearest["distance_m"] < 2_200


def test_planning_counts_use_one_three_and_five_kilometre_radii(synthetic_site: dict[str, object]) -> None:
    response = _result(synthetic_site)
    assert response.planning["counts_within_radii"] == {"1_km": 1, "3_km": 2, "5_km": 2}


def test_planning_response_excludes_applicant_pii(synthetic_site: dict[str, object]) -> None:
    response = _result(synthetic_site)
    nearby = response.planning["nearby_records"]
    assert nearby
    assert all("ApplicantForename" not in record for record in nearby)
    assert all("ApplicantSurname" not in record for record in nearby)
    assert all("ApplicantAddress" not in record for record in nearby)


def test_flood_layers_preserve_type_and_return_period(synthetic_site: dict[str, object]) -> None:
    response = _result(synthetic_site)
    assert response.flood["coastal"][0]["flood_type"] == "coastal"
    assert response.flood["coastal"][0]["return_period"] == "0010"
    assert response.flood["fluvial"][0]["flood_type"] == "fluvial"
    assert response.flood["fluvial"][0]["return_period"] == "0100"


def test_groundwater_returns_all_overlapping_polygons(synthetic_site: dict[str, object]) -> None:
    response = _result(synthetic_site)
    groundwater = response.ground["groundwater"]
    assert groundwater["intersects"] is True
    assert groundwater["multiple_intersections"] is True
    assert {item["VUL40KID"] for item in groundwater["intersections"]} == {"V-1", "V-2"}


def test_smr_zone_intersection_uses_zone_id(synthetic_site: dict[str, object]) -> None:
    response = _result(synthetic_site)
    assert response.heritage["intersects"] is True
    assert response.heritage["intersecting_zone_ids"] == ["SMR-1"]


def test_karst_nearest_distance_is_returned(synthetic_site: dict[str, object]) -> None:
    response = _result(synthetic_site)
    landforms = response.ground["karst_landforms"]
    assert landforms["nearest_landform"]["KARST40KID"] == "K-1"
    assert 900 < landforms["nearest_landform"]["distance_m"] < 1_100


def test_grid_assets_are_contextual_not_suitability_decisions(synthetic_site: dict[str, object]) -> None:
    response = _result(synthetic_site, SiteEvidenceOptions(grid_min_primary_kv=100))
    grid = response.grid
    assert len(grid["nearby_assets"]) == 1
    assert grid["nearby_assets"][0]["Station Name"] == "Near HV"
    assert "PASS" not in json.dumps(grid).upper()
    assert "FAIL" not in json.dumps(grid).upper()


def test_zoning_is_unknown_without_geometry(synthetic_site: dict[str, object]) -> None:
    response = _result(synthetic_site)
    assert response.zoning["state"] == "UNKNOWN"
    assert "MyPlan" in response.zoning["next_data_dependency"]


def test_registered_only_water_documents_do_not_create_capacity_claims(synthetic_site: dict[str, object]) -> None:
    response = _result(synthetic_site)
    assert response.water["evidence_state"] == "UNKNOWN"
    assert response.water["site_specific_structured_capacity_available"] is False
    assert response.water["capacity_treated_as_guaranteed"] is False


def test_evidence_records_retain_public_source_provenance(synthetic_site: dict[str, object]) -> None:
    response = _result(synthetic_site)
    public_entries = [
        entry for entry in response.evidence_ledger.entries
        if entry.field_name == "biodiversity.sac.intersects"
    ]
    assert public_entries
    entry = public_entries[0]
    assert entry.source_name == "Synthetic biodiversity source"
    assert entry.source_reference is not None
    assert entry.review_status == "UNREVIEWED"


def test_unknown_and_missing_evidence_remains_explicit(synthetic_site: dict[str, object]) -> None:
    response = _result(synthetic_site)
    assert response.zoning["evidence_state"] == "UNKNOWN"
    assert response.water["evidence_state"] == "UNKNOWN"
    assert any(entry.evidence_state == "UNKNOWN" for entry in response.evidence_ledger.entries)


def test_one_domain_failure_does_not_fabricate_other_domains(synthetic_site: dict[str, object]) -> None:
    root = synthetic_site["root"]
    manifest_path = root / "data" / "processed" / "data_registry.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for entry in manifest:
        if entry["domain"] == "planning" and entry["status"] == "PROCESSED":
            entry["processed_output_paths"] = ["data/processed/planning/missing.parquet"]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    response = _result(synthetic_site)
    assert response.planning["status"] == "ERROR"
    assert response.biodiversity["sac"]["intersects"] is True


def test_only_processed_registry_outputs_are_queried(synthetic_site: dict[str, object]) -> None:
    root = synthetic_site["root"]
    manifest_path = root / "data" / "processed" / "data_registry.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for entry in manifest:
        if entry["domain"] == "flood" and "ext_f" in entry["raw_relative_path"]:
            entry["status"] = "PROCESSED_WITH_WARNINGS"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    response = _result(synthetic_site)
    assert response.flood["fluvial"][0]["status"] == "UNKNOWN"
    assert response.flood["coastal"][0]["status"] == "SUCCESS"


def test_site_evidence_api_returns_structured_response(
    synthetic_site: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(main_module, "PROJECT_ROOT", synthetic_site["root"])
    response = TestClient(main_module.app).post(
        "/evidence/site",
        json=synthetic_site["project"].model_dump(),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["project_location"]["transformed_crs"] == "EPSG:2157"
    assert "evidence_ledger" in body
    assert "recommendation" not in body
