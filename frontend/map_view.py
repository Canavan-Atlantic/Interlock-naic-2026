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
    "zoning": "Zoning geometry",
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


def _feature_layer(feature: dict[str, Any]) -> str | None:
    properties = _as_dict(feature.get("properties"))
    value = str(properties.get("layer") or feature.get("layer") or "").casefold()
    if value.startswith("biodiversity"):
        return "biodiversity"
    if value.startswith("flood"):
        return "flood"
    if value.startswith("grid"):
        return "grid"
    if value.startswith("planning"):
        return "planning"
    if value.startswith("zoning"):
        return "zoning"
    if value.startswith("water"):
        return "water"
    if value.startswith("ground") or value.startswith("karst") or value.startswith("heritage"):
        return "planning"
    return None


def _map_features(payload: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    features = _as_list(_as_dict(payload.get("evidence_bundle")).get("map_features"))
    output: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for feature in features:
        item = _as_dict(feature)
        layer = _feature_layer(item)
        if layer:
            output[layer].append(item)
    return output


def _feature_point(feature: dict[str, Any]) -> tuple[float, float] | None:
    geometry = _as_dict(feature.get("geometry"))
    coordinates = geometry.get("coordinates")
    if geometry.get("type") == "Point" and isinstance(coordinates, list) and len(coordinates) >= 2:
        if all(isinstance(value, (int, float)) for value in coordinates[:2]):
            return float(coordinates[1]), float(coordinates[0])
    return None


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
    feature_layers = _map_features(payload)
    enabled: dict[str, bool] = {"site": True}
    with st.container(horizontal=True):
        for layer, title in _LAYER_LABELS.items():
            available = bool(feature_layers.get(layer)) or bool(layer_records.get(layer))
            enabled[layer] = st.checkbox(
                title if available else f"{title} (unavailable)",
                value=available,
                disabled=not available,
                key=f"{key_prefix}_layer_{layer}",
            )

    visible = [row for row in points if enabled.get(row["layer"], False)]
    visible_features = [feature for layer, values in feature_layers.items() if enabled.get(layer, False) for feature in values]
    if visible_features:
        try:
            import pydeck as pdk

            site = _coordinates(_as_dict(_as_dict(payload.get("project_context")).get("location")))
            feature_points = [point for feature in visible_features if (point := _feature_point(feature)) is not None]
            centres = ([site] if site else []) + feature_points
            if centres:
                latitude = sum(point[0] for point in centres) / len(centres)
                longitude = sum(point[1] for point in centres) / len(centres)
            else:
                latitude, longitude = 53.4, -6.3
            layers = []
            colours = {"flood": [166, 61, 74, 90], "biodiversity": [22, 135, 125, 90], "grid": [0, 168, 157, 220], "planning": [200, 146, 53, 90], "zoning": [75, 120, 144, 90], "water": [32, 107, 159, 90]}
            for layer, values in feature_layers.items():
                active_values = values if enabled.get(layer, False) else []
                if not active_values:
                    continue
                layers.append(pdk.Layer(
                    "GeoJsonLayer",
                    f"interlock-{key_prefix}-{layer}",
                    data={"type": "FeatureCollection", "features": active_values},
                    pickable=True,
                    stroked=True,
                    filled=True,
                    get_fill_color=colours.get(layer, [75, 120, 144, 90]),
                    get_line_color=[6, 55, 71, 210],
                    line_width_min_pixels=2,
                ))
            if enabled.get("site") and site:
                layers.append(pdk.Layer("ScatterplotLayer", f"interlock-{key_prefix}-site", data=pd.DataFrame([{"latitude": site[0], "longitude": site[1], "label": "Project site"}]), get_position="[longitude, latitude]", get_radius=130, get_fill_color=[6, 55, 71, 255], pickable=True))
            deck = pdk.Deck(
                layers=layers,
                initial_view_state=pdk.ViewState(latitude=latitude, longitude=longitude, zoom=11.5),
                tooltip={"html": "<b>{layer}</b><br/>{display_note}<br/>Source: {source_reference}", "style": {"backgroundColor": "#063747", "color": "white"}},
            )
            st.pydeck_chart(deck, height=390, key=f"{key_prefix}_spatial_map")
        except (ImportError, RuntimeError, TypeError, ValueError):
            # A native point map remains a truthful fallback if pydeck is not
            # available in a minimal runtime; no geometry is fabricated.
            if visible:
                st.map(pd.DataFrame(visible), latitude="latitude", longitude="longitude", color=None, zoom=11, height=390)
            else:
                st.info("Registered geometries are unavailable in this runtime.")
    elif visible:
        st.map(pd.DataFrame(visible), latitude="latitude", longitude="longitude", color=None, zoom=11, height=390)
    else:
        st.info("No stored geometries or coordinates are available for the selected layers.")

    columns = st.columns(len(_LAYER_LABELS))
    for column, (layer, title) in zip(columns, _LAYER_LABELS.items()):
        with column:
            with st.container(border=True):
                st.markdown(f"**{title}**")
                values = layer_records.get(layer, [])
                if not values and not feature_layers.get(layer):
                    st.caption("Unavailable from the current registered source; no geometry is shown.")
                else:
                    for record in values[:3]:
                        st.caption(_value_summary(record))
                    if len(values) > 3:
                        st.caption(f"+ {len(values) - 3} more records in Data Layers")
                    if layer == "grid":
                        st.caption("Infrastructure proximity is context only; it does not prove grid capacity, MIC or energisation.")


__all__ = ["build_map_points", "render_map_first_view"]
