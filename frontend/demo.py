"""Canonical, data-backed demo inputs and run-summary helpers for Module 11."""

from __future__ import annotations

from typing import Any

try:
    from .result_summary import summarize_interlock_result
except ImportError:  # Streamlit executes frontend/app.py as a top-level script.
    from result_summary import summarize_interlock_result


DEMO_PROJECT_ID = "naic-demo-blanchardstown"
DEMO_PROJECT_PRESET_NAME = "NAIC Demo Project"
DEMO_PROJECT_EVIDENCE_MODE = "Normal project"

# These values are the existing Blanchardstown project-input scenario used by
# the repository's deterministic tests and README command.  Missing values are
# intentionally None/Unknown so the demo exercises the same evidence behavior
# as an ordinary incomplete project input.
DEMO_PROJECT_PRESET: dict[str, object] = {
    "project_name": "NAIC Test Data Centre",
    "development_type": "Data Centre",
    "project_stage": "Early Feasibility",
    "site_address": "Blanchardstown, Dublin 15",
    "local_authority": None,
    "latitude": 53.3879,
    "longitude": -6.3750,
    "site_area_hectares": None,
    "planned_power_demand_mw": 50,
    "requested_mic_mva": None,
    "power_strategy": "Unknown",
    "energy_strategy": None,
    "project_phasing_notes": "Prototype test project for INTERLOCK.",
}

DEMO_PROJECT_STAGE_PRESETS: dict[str, dict[str, object]] = {
    "Site Discovery": {
        **DEMO_PROJECT_PRESET,
        "project_stage": "Site Discovery",
        "planned_power_demand_mw": None,
        "requested_mic_mva": None,
        "power_strategy": "Unknown",
        "energy_strategy": None,
        "project_phasing_notes": "Initial desktop site screening for the canonical demo.",
    },
    "Early Feasibility": dict(DEMO_PROJECT_PRESET),
    "Deliverability Validation": {
        **DEMO_PROJECT_PRESET,
        "project_stage": "Deliverability Validation",
        "planned_power_demand_mw": 50,
        "requested_mic_mva": 60,
        "power_strategy": "New Grid Connection",
        "energy_strategy": "Grid connection with on-site resilience strategy",
        "project_phasing_notes": "Phase 1 delivery definition with grid and utility confirmations to be secured.",
    },
}

DEMO_PROJECT_METADATA: dict[str, object] = {
    "preset_name": DEMO_PROJECT_PRESET_NAME,
    "scenario": "Blanchardstown",
    "kind": "demo_benchmark_preset",
}


__all__ = [
    "DEMO_PROJECT_ID",
    "DEMO_PROJECT_EVIDENCE_MODE",
    "DEMO_PROJECT_METADATA",
    "DEMO_PROJECT_PRESET",
    "DEMO_PROJECT_STAGE_PRESETS",
    "DEMO_PROJECT_PRESET_NAME",
    "summarize_interlock_result",
]
