"""Map-first presentation over the deterministic GIS evidence already stored."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

import pandas as pd
import streamlit as st


_LAYER_LABELS = {
    "flood": "Flood context",
    "biodiversity": "Protected-site / biodiversity context",
    "grid": "Nearby grid infrastructure",
    "planning": "Planning / zoning context",
    "water": "Water / wastewater context",
}


def _as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _enum(value: object) -> str:
    return str(getattr(value, "value", value) or "")


def _coordinates(value: object) -> tuple[float, float] | None:
    item = _as_dict(value)
    latitude = item.get("latitude")
    longitude = item.get("longitude")
    if latitude is None or longitude is None:
        coordinates = _as_dict(item.get("geometry")).get("coordinates")
        if isinstance(coordinates, list) and len(coordinates) >= 2 and all(isinstance(v, (int, float)) for v in coordinates[:2]):
            longitude, latitude = coordinates[:2]
    if not isinstance(latitude, (int, float)) or not isinstance(longitude, (int, float)):
        return None
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        return None
    return float(latitude), float(longitude)


def build_map_points(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Return only coordinates explicitly present in the stored payload."""

    context = _as_dict(payload.get("project_context"))
    location = _as_dict(context.get("location"))
    evidence = _as_dict(payload.get("evidence_bundle"))
    rows: list[dict[str, Any]] = []
    site = _coordinates(location)
    if site is not None:
        rows.append({"latitude": site[0], "longitude": site[1], "layer": "site", "label": "Project site"})
    for record in _as_list(evidence.get("records")):
        item = _as_dict(record)
        if _enum(item.get("created_by")) != "DETERMINISTIC_GIS":
            continue
        coords = _coordinates(item.get("value")) or _coordinates(item)
        if coords is None:
            continue
        field = str(item.get("field_name") or "").casefold()
        layer = next((name for name in _LAYER_LABELS if name in field), "planning")
        rows.append({
            "latitude": coords[0],
            "longitude": coords[1],
            "layer": layer,
            "label": str(item.get("field_name") or "GIS evidence"),
        })
    return rows


def _layer_records(payload: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    records = _as_list(_as_dict(payload.get("evidence_bundle")).get("records"))
    output: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for raw in records:
        item = _as_dict(raw)
        if _enum(item.get("created_by")) != "DETERMINISTIC_GIS":
            continue
        field = str(item.get("field_name") or "").casefold()
        layer = next((name for name in _LAYER_LABELS if name in field), None)
        if layer:
            output[layer].append(item)
    return output


def _value_summary(record: dict[str, Any]) -> str:
    field = str(record.get("field_name") or "GIS evidence")
    value = record.get("value")
    if isinstance(value, bool):
        return f"{field}: {'intersection recorded' if value else 'no intersection recorded'}"
    if isinstance(value, (int, float)):
        suffix = " nearby assets" if "asset" in field else ""
        return f"{field}: {value:g}{suffix}"
    if isinstance(value, dict):
        return f"{field}: deterministic context recorded"
    return f"{field}: unknown / not provided"


def render_map_first_view(payload: dict[str, Any], *, key_prefix: str = "decision") -> None:
    """Render a prominent, truthful spatial view without adding GIS logic."""

    st.markdown("#### Map-first project view")
    st.caption("Map markers come only from coordinates stored in the project or deterministic GIS evidence. Spatial proximity does not establish capacity, connection or approval.")
    points = build_map_points(payload)
    layer_records = _layer_records(payload)
    enabled: dict[str, bool] = {"site": True}
    with st.container(horizontal=True):
        for layer, title in _LAYER_LABELS.items():
            enabled[layer] = st.checkbox(title, value=True, key=f"{key_prefix}_layer_{layer}")

    visible = [row for row in points if enabled.get(row["layer"], False)]
    if visible:
        st.map(pd.DataFrame(visible), latitude="latitude", longitude="longitude", color=None, zoom=11, height=390)
    else:
        st.info("No stored coordinates are available for the selected layers.")

    columns = st.columns(len(_LAYER_LABELS))
    for column, (layer, title) in zip(columns, _LAYER_LABELS.items()):
        with column:
            with st.container(border=True):
                st.markdown(f"**{title}**")
                values = layer_records.get(layer, [])
                if not values:
                    st.caption("No deterministic record in this run.")
                else:
                    for record in values[:3]:
                        st.caption(_value_summary(record))
                    if len(values) > 3:
                        st.caption(f"+ {len(values) - 3} more records in Data Layers")
                    if layer == "grid":
                        st.caption("Infrastructure proximity is context only; it does not prove grid capacity, MIC or energisation.")


__all__ = ["build_map_points", "render_map_first_view"]
