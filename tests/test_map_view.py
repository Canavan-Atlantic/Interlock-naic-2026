from frontend.map_view import build_map_points


def test_map_points_only_use_coordinates_in_stored_payload() -> None:
    payload = {
        "project_context": {"location": {"latitude": 53.4, "longitude": -6.3}},
        "evidence_bundle": {"records": [
            {"created_by": "DETERMINISTIC_GIS", "field_name": "grid.nearby_assets", "value": 4},
            {"created_by": "DETERMINISTIC_GIS", "field_name": "planning.marker", "value": {"latitude": 53.41, "longitude": -6.31}},
            {"created_by": "DETERMINISTIC_GIS", "field_name": "flood.intersects", "value": True},
            {"created_by": "RAG_RETRIEVAL", "field_name": "policy.grid", "value": {"latitude": 53.42, "longitude": -6.32}},
        ]},
    }
    points = build_map_points(payload)
    assert {(point["latitude"], point["longitude"]) for point in points} == {(53.4, -6.3), (53.41, -6.31)}
    assert not any(point["layer"] == "grid" for point in points)


def test_map_points_do_not_fabricate_missing_site_geometry() -> None:
    assert build_map_points({"project_context": {"location": {}}, "evidence_bundle": {"records": []}}) == []
