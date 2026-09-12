"""Polished Streamlit frontend for the INTERLOCK development journey."""

from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Any
from urllib.parse import quote, urlencode

import requests
import streamlit as st

from components import (
    as_dict,
    as_list,
    render_decision_pack,
    render_evidence_view,
    render_insights,
    render_about,
    render_brand_header,
    render_home,
    render_methodology,
    render_demo_run_summary,
)
from demo import (
    DEMO_PROJECT_EVIDENCE_MODE,
    DEMO_PROJECT_ID,
    DEMO_PROJECT_METADATA,
    DEMO_PROJECT_PRESET,
    DEMO_PROJECT_PRESET_NAME,
    summarize_interlock_result,
)
from styles import inject_styles
from report import render_comparison_report_pdf, safe_comparison_report_filename


PAGE_NAMES = ("Home", "New Assessment", "Projects", "Decision Pack", "Assessment Comparison", "Evidence", "Insights", "About", "Methodology")
NAVIGATION_ITEMS = ("Home", "New Assessment", "Projects", "Data Layers", "Insights", "About")
NAVIGATION_ROUTES = {
    "Home": "Home",
    "New Assessment": "New Assessment",
    "Projects": "Projects",
    "Data Layers": "Evidence",
    "Insights": "Insights",
    "About": "About",
}
PAGE_TO_NAVIGATION = {
    "Home": "Home",
    "New Assessment": "New Assessment",
    "Projects": "Projects",
    "Decision Pack": "Projects",
    "Assessment Comparison": "Projects",
    "Evidence": "Data Layers",
    "Insights": "Insights",
    "About": "About",
    "Methodology": "About",
}


st.set_page_config(page_title="INTERLOCK · Canavan Atlantic", page_icon=":material/link:", layout="wide")
inject_styles()


def optional_text(value: str) -> str | None:
    cleaned = value.strip()
    return cleaned or None


def build_evidence_agent_context(
    project: dict[str, object],
    *,
    project_evidence_mode: str = "Normal project",
    project_id_override: str | None = None,
    preset_metadata: dict[str, object] | None = None,
) -> dict[str, object]:
    """Build the real ProjectContext payload without inventing missing values."""

    stable_payload = json.dumps(project, sort_keys=True, default=str).encode("utf-8")
    project_id = "streamlit-" + hashlib.sha256(stable_payload).hexdigest()[:12]
    has_coordinates = project.get("latitude") is not None and project.get("longitude") is not None
    herbata_mode = project_evidence_mode.startswith("Herbata")
    developer_inputs: dict[str, object] = {
        "source": "validated_streamlit_project_input",
        "project_evidence_mode": project_evidence_mode,
    }
    if preset_metadata:
        developer_inputs["preset_metadata"] = dict(preset_metadata)
    return {
        "project_id": "benchmark-herbata-naas" if herbata_mode else project_id_override or project_id,
        "project_name": "Herbata Data Centre benchmark" if herbata_mode else project.get("project_name"),
        "project_type": project.get("development_type"),
        "assessment_workflow": "SITE_FEASIBILITY" if has_coordinates else "SITE_DISCOVERY",
        "project_lifecycle_status": "UNKNOWN",
        "location": {
            "address": project.get("site_address"),
            "latitude": project.get("latitude"),
            "longitude": project.get("longitude"),
            "local_authority": project.get("local_authority"),
            "country": "Ireland" if herbata_mode else None,
            "jurisdiction": "IRELAND" if herbata_mode else "UNKNOWN",
        },
        "site_boundary": (
            {"area_hectares": project.get("site_area_hectares")}
            if project.get("site_area_hectares") is not None
            else None
        ),
        "planned_power_mw": project.get("planned_power_demand_mw"),
        "requested_mic_mva": project.get("requested_mic_mva"),
        "power_strategy": project.get("power_strategy"),
        "energy_strategy": project.get("energy_strategy"),
        "phasing": project.get("project_phasing_notes"),
        "project_stage": project.get("project_stage"),
        "developer_inputs": developer_inputs,
        "uploaded_document_refs": [],
        "source_project_input": {
            key: value for key, value in project.items() if key != "local_authority"
        },
    }


def project_payload_from_form(
    project_name: str,
    development_type: str,
    project_stage: str,
    site_address: str,
    local_authority: str,
    latitude: float | None,
    longitude: float | None,
    site_area_hectares: float | None,
    planned_power_demand_mw: float | None,
    requested_mic_mva: float | None,
    power_strategy: str,
    energy_strategy: str,
    project_phasing_notes: str,
) -> dict[str, object]:
    return {
        "project_name": optional_text(project_name),
        "development_type": optional_text(development_type),
        "project_stage": project_stage,
        "site_address": optional_text(site_address),
        "local_authority": optional_text(local_authority),
        "latitude": latitude,
        "longitude": longitude,
        "site_area_hectares": site_area_hectares,
        "planned_power_demand_mw": planned_power_demand_mw,
        "requested_mic_mva": requested_mic_mva,
        "power_strategy": power_strategy,
        "energy_strategy": optional_text(energy_strategy),
        "project_phasing_notes": optional_text(project_phasing_notes),
    }


def request_navigation(page: str) -> None:
    """Queue navigation for the next rerun before the navigation widget renders."""

    if page not in PAGE_NAMES:
        return
    st.session_state["pending_navigation"] = page
    st.rerun()


def run_interlock(
    project_payload: dict[str, object],
    project_evidence_mode: str,
    api_base_url: str,
    *,
    project_id_override: str | None = None,
    preset_metadata: dict[str, object] | None = None,
) -> None:
    """Validate once, then call the orchestrator once with safe customer errors."""

    validation_payload = {key: value for key, value in project_payload.items() if key != "local_authority"}
    try:
        validation_response = requests.post(
            f"{api_base_url.rstrip('/')}/project-input/validate",
            json=validation_payload,
            timeout=15,
        )
        validation_response.raise_for_status()
        st.session_state["validation_payload"] = validation_response.json()
    except (requests.RequestException, ValueError, TypeError):
        st.error("Project input could not be validated. Check the required fields and try again.")
        return

    context_payload = build_evidence_agent_context(
        project_payload,
        project_evidence_mode=project_evidence_mode,
        project_id_override=project_id_override,
        preset_metadata=preset_metadata,
    )
    with st.status("Running INTERLOCK", expanded=True) as progress:
        st.write("Gathering project evidence")
        st.write("Checking authoritative sources and dependencies")
        st.write("Preparing a traceable explanation")
        try:
            run_params = {
                "include_project_documents": "true",
                "include_benchmark_documents": str(project_evidence_mode.endswith("Validation")).lower(),
            }
            # Demo runs retain their established external project reference;
            # only a portfolio project UUID is sent as the persistence target.
            if project_id_override and not preset_metadata:
                run_params["project_id"] = project_id_override
            response = requests.post(
                f"{api_base_url.rstrip('/')}/interlock/run",
                params=run_params,
                json=context_payload,
                timeout=300,
            )
            response.raise_for_status()
            payload = response.json()
            workflow_status = str(payload.get("workflow_status") or "UNKNOWN")
            st.session_state["submitted_project_payload"] = project_payload
            st.session_state["interlock_payload"] = payload
            if not st.session_state.get("assessment_project_id"):
                result_context = as_dict(payload.get("project_context"))
                st.session_state["active_project_id"] = result_context.get("project_id")
            if preset_metadata:
                st.session_state["demo_run_summary"] = (
                    summarize_interlock_result(payload)
                    if workflow_status in {"COMPLETE", "REQUIRES_HUMAN_REVIEW"}
                    else None
                )
            if workflow_status in {"FAILED", "PARTIAL"}:
                progress.update(label="INTERLOCK could not complete the assessment", state="error")
            else:
                progress.update(label="INTERLOCK analysis complete", state="complete")
        except requests.HTTPError:
            progress.update(label="INTERLOCK could not complete the assessment", state="error")
            st.error("INTERLOCK could not complete the assessment. The backend returned a controlled error.")
        except (requests.RequestException, ValueError, TypeError):
            progress.update(label="INTERLOCK service unavailable", state="error")
            st.error("INTERLOCK is temporarily unavailable. No assessment result was created.")


def render_assessment_page(api_base_url: str | None) -> None:
    _ensure_assessment_form_state()
    st.markdown('<p class="interlock-section-kicker">New assessment</p>', unsafe_allow_html=True)
    st.markdown('<h1 class="interlock-section-title">Start with what you know.</h1>', unsafe_allow_html=True)
    st.markdown(
        '<p class="interlock-section-copy">You can begin with incomplete information. INTERLOCK preserves missing information as unknown rather than guessing.</p>',
        unsafe_allow_html=True,
    )
    if st.session_state.get("assessment_project_id"):
        st.info("This assessment will be saved as a new immutable run for the selected project.")
    if st.button(
        "Reload Demo Project" if st.session_state.get("demo_preset_loaded") else "Load Demo Project",
        key="load_demo_project",
        icon=":material/science:",
        help="Populate the verified Blanchardstown NAIC demo inputs. Review or edit them before running. No assessment is started.",
    ):
        _load_demo_project()
        st.rerun()
    if st.session_state.get("demo_preset_loaded"):
        st.info(f"{DEMO_PROJECT_PRESET_NAME} loaded. Review and edit the prepared inputs before running.")
    with st.form("project_input_form", border=True):
        st.markdown("#### Project")
        project_name = st.text_input("Project name (optional)", key="project_name")
        development_type = st.text_input("Project type", key="development_type")
        project_stage = st.selectbox(
            "Project stage",
            options=[
                "Site Discovery",
                "Early Feasibility",
                "Deliverability Validation",
                "Design Definition",
                "Planning Readiness",
                "Planning Approved",
                "Construction",
                "Unknown",
            ],
            key="project_stage",
        )

        st.markdown("#### Location")
        site_address = st.text_input("Address (optional)", key="site_address")
        local_authority = st.text_input("Local authority (optional)", key="local_authority")
        location_columns = st.columns(2)
        latitude = location_columns[0].number_input(
            "Latitude (optional)", min_value=-90.0, max_value=90.0, step=0.0001, format="%.4f", key="latitude"
        )
        longitude = location_columns[1].number_input(
            "Longitude (optional)", min_value=-180.0, max_value=180.0, step=0.0001, format="%.4f", key="longitude"
        )

        st.markdown("#### Power & energy")
        power_columns = st.columns(2)
        planned_power_demand_mw = power_columns[0].number_input(
            "Planned power (MW, optional)", min_value=0.0, step=1.0, format="%.2f", key="planned_power_demand_mw"
        )
        requested_mic_mva = power_columns[1].number_input(
            "Requested MIC (MVA, optional)", min_value=0.0, step=1.0, format="%.2f", key="requested_mic_mva"
        )
        power_strategy = st.selectbox(
            "Power strategy",
            options=[
                "Existing Grid Connection",
                "New Grid Connection",
                "Developer-Built Substation",
                "Hybrid / Alternative Strategy",
                "Unknown",
            ],
            key="power_strategy",
        )
        energy_strategy = st.text_input("Energy strategy (optional)", key="energy_strategy")

        st.markdown("#### Project information")
        site_area_hectares = st.number_input(
            "Site area (hectares, optional)", min_value=0.0, step=0.1, format="%.2f", key="site_area_hectares"
        )
        project_phasing_notes = st.text_area("Phasing and notes (optional)", key="project_phasing_notes")
        project_evidence_mode = st.selectbox(
            "Project evidence mode",
            options=[
                "Normal project",
                "Herbata benchmark — Early Evidence",
                "Herbata benchmark — Validation",
            ],
            key="project_evidence_mode",
            help="Early Evidence excludes benchmark-only records. Validation explicitly enables them for demonstration.",
        )
        st.caption("Blank numeric fields remain unknown; they are never converted to zero.")
        with st.container(horizontal=True, horizontal_alignment="right"):
            validate_only = st.form_submit_button("Validate Project Input")
            run_clicked = st.form_submit_button(
                "Run INTERLOCK Assessment",
                type="primary",
                icon=":material/arrow_forward:",
            )

    if not (validate_only or run_clicked):
        return
    project_payload = project_payload_from_form(
        project_name,
        development_type,
        project_stage,
        site_address,
        local_authority,
        latitude,
        longitude,
        site_area_hectares,
        planned_power_demand_mw,
        requested_mic_mva,
        power_strategy,
        energy_strategy,
        project_phasing_notes,
    )
    if not api_base_url:
        st.error("The backend connection is not configured. Set INTERLOCK_API_BASE_URL to run an assessment.")
        return
    if validate_only:
        validation_payload = {key: value for key, value in project_payload.items() if key != "local_authority"}
        try:
            response = requests.post(
                f"{api_base_url.rstrip('/')}/project-input/validate", json=validation_payload, timeout=15
            )
            response.raise_for_status()
            st.session_state["validation_payload"] = response.json()
            st.session_state["submitted_project_payload"] = project_payload
            st.success("Project input validated. Run INTERLOCK when you are ready.")
        except (requests.RequestException, ValueError, TypeError):
            st.error("Project input could not be validated. Check the required fields and try again.")
    if run_clicked:
        demo_loaded = bool(st.session_state.get("demo_preset_loaded"))
        assessment_project_id = None if demo_loaded else st.session_state.get("assessment_project_id")
        run_interlock(
            project_payload,
            project_evidence_mode,
            api_base_url,
            project_id_override=DEMO_PROJECT_ID if demo_loaded else assessment_project_id,
            preset_metadata=DEMO_PROJECT_METADATA if demo_loaded else None,
        )
        if st.session_state.get("interlock_payload"):
            request_navigation("Decision Pack")


def _portfolio_get(api_base_url: str | None, path: str) -> dict[str, Any] | list[Any] | None:
    """Read portfolio data with a customer-safe error message."""

    if not api_base_url:
        st.error("The project portfolio is not configured. Set INTERLOCK_API_BASE_URL to continue.")
        return None
    try:
        response = requests.get(f"{api_base_url.rstrip('/')}{path}", timeout=20)
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, (dict, list)):
            return payload
    except (requests.RequestException, ValueError, TypeError):
        st.error("The project portfolio is temporarily unavailable.")
    return None


def _format_portfolio_value(value: object) -> str:
    if value is None or value == "":
        return "Unknown / not provided"
    return str(value)


def _open_stored_run(api_base_url: str | None, run_id: str) -> None:
    stored = _portfolio_get(api_base_url, f"/runs/{run_id}")
    if not isinstance(stored, dict):
        return
    result = as_dict(stored.get("interlock_result"))
    if not result:
        st.error("The stored assessment result is unavailable.")
        return
    st.session_state["interlock_payload"] = result
    submitted = as_dict(stored.get("submitted_project_context"))
    st.session_state["submitted_project_payload"] = as_dict(submitted.get("source_project_input")) or None
    st.session_state["active_run_id"] = stored.get("id")
    st.session_state["demo_run_summary"] = None
    st.session_state["project_portfolio_view"] = False
    st.session_state["comparison_view"] = False
    st.session_state["comparison_payload"] = None
    request_navigation("Decision Pack")


def _populate_assessment_form_from_context(context: dict[str, Any]) -> None:
    """Copy stored submitted inputs into form state before its widgets render."""

    source = as_dict(context.get("source_project_input"))
    location = as_dict(context.get("location"))
    values: dict[str, object] = {
        "project_name": context.get("project_name", source.get("project_name")),
        "development_type": context.get("project_type", source.get("development_type")) or "Data Centre",
        "project_stage": context.get("project_stage", source.get("project_stage")) or "Unknown",
        "site_address": location.get("address", source.get("site_address")),
        "local_authority": location.get("local_authority", source.get("local_authority")),
        "latitude": location.get("latitude", source.get("latitude")),
        "longitude": location.get("longitude", source.get("longitude")),
        "site_area_hectares": as_dict(context.get("site_boundary")).get(
            "area_hectares", source.get("site_area_hectares")
        ),
        "planned_power_demand_mw": context.get("planned_power_mw", source.get("planned_power_demand_mw")),
        "requested_mic_mva": context.get("requested_mic_mva", source.get("requested_mic_mva")),
        "power_strategy": context.get("power_strategy", source.get("power_strategy")) or "Unknown",
        "energy_strategy": context.get("energy_strategy", source.get("energy_strategy")),
        "project_phasing_notes": context.get("phasing", source.get("project_phasing_notes")),
        "project_evidence_mode": "Normal project",
    }
    text_fields = {
        "project_name",
        "site_address",
        "local_authority",
        "energy_strategy",
        "project_phasing_notes",
    }
    for key, value in values.items():
        if key in text_fields and value is None:
            value = ""
        st.session_state[key] = value


def _reset_assessment_form() -> None:
    defaults = {
        "project_name": "",
        "development_type": "Data Centre",
        "project_stage": "Unknown",
        "site_address": "",
        "local_authority": "",
        "latitude": None,
        "longitude": None,
        "site_area_hectares": None,
        "planned_power_demand_mw": None,
        "requested_mic_mva": None,
        "power_strategy": "Unknown",
        "energy_strategy": "",
        "project_phasing_notes": "",
        "project_evidence_mode": "Normal project",
    }
    for key, value in defaults.items():
        st.session_state[key] = value


def render_projects_page(api_base_url: str | None) -> None:
    """Render the durable portfolio or one project's assessment history."""

    project_id = st.session_state.get("active_project_id")
    if project_id and st.session_state.get("project_portfolio_view"):
        render_project_detail_page(api_base_url, str(project_id))
        return

    st.markdown('<p class="interlock-section-kicker">Projects</p>', unsafe_allow_html=True)
    st.markdown('<h1 class="interlock-section-title">Project portfolio</h1>', unsafe_allow_html=True)
    st.markdown(
        '<p class="interlock-section-copy">Keep projects separate, return to completed assessments, and compare the evidence history of one site over time.</p>',
        unsafe_allow_html=True,
    )
    controls = st.container(horizontal=True, horizontal_alignment="right")
    with controls:
        if st.button("New project", key="portfolio_new_project", type="primary", icon=":material/add:"):
            st.session_state["active_project_id"] = None
            st.session_state["assessment_project_id"] = None
            st.session_state["project_portfolio_view"] = False
            st.session_state["interlock_payload"] = None
            st.session_state["submitted_project_payload"] = None
            st.session_state["demo_run_summary"] = None
            st.session_state["comparison_view"] = False
            st.session_state["comparison_payload"] = None
            _reset_assessment_form()
            request_navigation("New Assessment")
        if st.button("Refresh", key="portfolio_refresh", icon=":material/refresh:"):
            st.rerun()

    projects_payload = _portfolio_get(api_base_url, "/projects")
    if not isinstance(projects_payload, list):
        return
    if not projects_payload:
        st.info("No projects have been assessed yet. Start a new project to create the first portfolio record.")
        return

    for project in projects_payload:
        item = as_dict(project)
        latest = as_dict(item.get("latest_assessment"))
        with st.container(border=True):
            st.markdown(f"### {_format_portfolio_value(item.get('project_name'))}")
            st.caption(
                f"{_format_portfolio_value(item.get('project_type'))} · "
                f"{_format_portfolio_value(item.get('address'))}"
            )
            columns = st.columns(4)
            columns[0].metric("Latest status", _format_portfolio_value(latest.get("workflow_status")))
            columns[1].metric("Planned power (MW)", _format_portfolio_value(latest.get("planned_power_mw")))
            columns[2].metric("Unknown themes", latest.get("unknown_theme_count", 0))
            columns[3].metric("Professional reviews", latest.get("human_review_count", 0))
            st.caption(
                f"Assessments: {item.get('run_count', 0)} · "
                f"Last assessed: {_format_portfolio_value(latest.get('created_at'))}"
            )
            if st.button(
                "Open project",
                key=f"portfolio_open_{item.get('id')}",
                icon=":material/arrow_forward:",
            ):
                st.session_state["active_project_id"] = item.get("id")
                st.session_state["project_portfolio_view"] = True
                st.session_state["comparison_view"] = False
                st.session_state["comparison_payload"] = None
                request_navigation("Projects")


def render_project_detail_page(api_base_url: str | None, project_id: str) -> None:
    detail_payload = _portfolio_get(api_base_url, f"/projects/{project_id}")
    if not isinstance(detail_payload, dict):
        return
    runs_payload = _portfolio_get(api_base_url, f"/projects/{project_id}/runs")
    if not isinstance(runs_payload, list):
        return

    if st.button("Back to portfolio", key="project_back_to_portfolio", icon=":material/arrow_back:"):
        st.session_state["active_project_id"] = None
        st.session_state["project_portfolio_view"] = True
        st.session_state["comparison_view"] = False
        st.session_state["comparison_payload"] = None
        request_navigation("Projects")

    st.markdown('<p class="interlock-section-kicker">Project detail</p>', unsafe_allow_html=True)
    st.markdown(
        f"<h1 class=\"interlock-section-title\">{_format_portfolio_value(detail_payload.get('project_name'))}</h1>",
        unsafe_allow_html=True,
    )
    st.markdown(
        f"<p class=\"interlock-section-copy\">{_format_portfolio_value(detail_payload.get('address'))} · "
        f"{_format_portfolio_value(detail_payload.get('project_type'))}</p>",
        unsafe_allow_html=True,
    )
    latest = as_dict(detail_payload.get("latest_assessment"))
    if latest:
        st.markdown("#### Latest assessment")
        columns = st.columns(5)
        columns[0].metric("Status", _format_portfolio_value(latest.get("workflow_status")))
        columns[1].metric("Planned power (MW)", _format_portfolio_value(latest.get("planned_power_mw")))
        columns[2].metric("Findings", latest.get("findings_count", 0))
        columns[3].metric("Unknown themes", latest.get("unknown_theme_count", 0))
        columns[4].metric("Professional reviews", latest.get("human_review_count", 0))
        action_columns = st.columns(2)
        with action_columns[0]:
            if st.button("Open latest assessment", key="project_open_latest", type="primary"):
                _open_stored_run(api_base_url, str(latest.get("id")))
        with action_columns[1]:
            if st.button("Run new assessment", key="project_run_new", icon=":material/refresh:"):
                _populate_assessment_form_from_context(as_dict(detail_payload.get("project_context")))
                st.session_state["assessment_project_id"] = project_id
                st.session_state["project_portfolio_view"] = False
                st.session_state["comparison_view"] = False
                st.session_state["comparison_payload"] = None
                request_navigation("New Assessment")
    else:
        st.info("This project has no completed assessment run yet.")

    st.markdown("#### Assessment history")
    if not runs_payload:
        st.caption("No successful assessment runs are stored for this project.")
        return
    for run in runs_payload:
        item = as_dict(run)
        with st.container(border=True):
            st.markdown(
                f"**{_format_portfolio_value(item.get('created_at'))}** · "
                f"{_format_portfolio_value(item.get('workflow_status'))}"
            )
            st.caption(
                f"Run: {_format_portfolio_value(item.get('interlock_run_id'))} · "
                f"Power: {_format_portfolio_value(item.get('planned_power_mw'))} MW · "
                f"Findings: {item.get('findings_count', 0)} · "
                f"Unknown themes: {item.get('unknown_theme_count', 0)} · "
                f"Reviews: {item.get('human_review_count', 0)}"
            )
            if st.button("Open assessment", key=f"project_open_run_{item.get('id')}"):
                _open_stored_run(api_base_url, str(item.get("id")))

    if len(runs_payload) >= 2:
        st.markdown("#### Compare assessments")
        st.caption("Select two stored runs to see what changed. The comparison uses historical data and does not rerun INTERLOCK.")
        run_ids = [str(as_dict(item).get("id")) for item in runs_payload if as_dict(item).get("id")]
        run_labels = {
            str(as_dict(item).get("id")): (
                f"{_format_portfolio_value(as_dict(item).get('created_at'))} · "
                f"{_format_portfolio_value(as_dict(item).get('planned_power_mw'))} MW · "
                f"{_format_portfolio_value(as_dict(item).get('interlock_run_id'))}"
            )
            for item in runs_payload
            if as_dict(item).get("id")
        }
        baseline_key = f"comparison_baseline_{project_id}"
        comparison_key = f"comparison_run_{project_id}"
        if st.session_state.get(baseline_key) not in run_ids:
            st.session_state[baseline_key] = run_ids[1]
        if st.session_state.get(comparison_key) not in run_ids:
            st.session_state[comparison_key] = run_ids[0]
        selection_columns = st.columns(2)
        with selection_columns[0]:
            baseline_run_id = st.selectbox(
                "Baseline assessment",
                run_ids,
                key=baseline_key,
                format_func=lambda value: run_labels.get(value, value),
            )
        with selection_columns[1]:
            comparison_run_id = st.selectbox(
                "Compared assessment",
                run_ids,
                key=comparison_key,
                format_func=lambda value: run_labels.get(value, value),
            )
        if st.button("Compare Assessments", key="compare_project_assessments", type="primary", icon=":material/compare_arrows:"):
            if baseline_run_id == comparison_run_id:
                st.error("Choose two different assessment runs to compare.")
            else:
                query = urlencode({"baseline_run_id": baseline_run_id, "comparison_run_id": comparison_run_id})
                comparison_payload = _portfolio_get(
                    api_base_url,
                    f"/projects/{quote(project_id, safe='')}/compare?{query}",
                )
                if isinstance(comparison_payload, dict):
                    st.session_state["comparison_payload"] = comparison_payload
                    st.session_state["comparison_project_id"] = project_id
                    st.session_state["comparison_view"] = True
                    request_navigation("Assessment Comparison")


def _comparison_item_text(item: dict[str, Any]) -> str:
    """Render a concise, non-fabricated summary of a changed record."""

    value = as_dict(item.get("comparison") or item.get("baseline"))
    preferred = (
        "domain", "status", "title", "summary", "description", "reason", "recommended_role",
        "severity", "source_document_id", "source_path", "locator", "evidence_id", "dependency_id", "action_id",
    )
    parts: list[str] = []
    for key in preferred:
        if key in value and value.get(key) not in (None, "", []):
            current = value.get(key)
            if isinstance(current, list):
                current = ", ".join(str(entry) for entry in current)
            parts.append(f"{key.replace('_', ' ').title()}: {current}")
    return " · ".join(parts) or "Record present in this assessment."


def _render_comparison_section(title: str, section: dict[str, Any], *, removed_title: str = "Removed / resolved") -> None:
    st.markdown(f"#### {title}")
    groups = (
        ("New", "added", "New items", "success"),
        (removed_title, "removed", removed_title, "info"),
        ("Changed", "changed", "Changed items", "warning"),
    )
    rendered_change = False
    for label_text, key, caption_text, message_type in groups:
        values = [as_dict(item) for item in as_list(section.get(key))]
        if not values:
            continue
        rendered_change = True
        st.markdown(f"**{label_text} ({len(values)})**")
        for item in values:
            with st.container(border=True):
                st.markdown(f"**{_format_portfolio_value(item.get('label'))}**")
                baseline = as_dict(item.get("baseline"))
                comparison = as_dict(item.get("comparison"))
                if baseline and comparison:
                    st.caption(f"Baseline: {_comparison_item_text({'baseline': baseline})}")
                    st.caption(f"Compared: {_comparison_item_text({'comparison': comparison})}")
                else:
                    st.caption(_comparison_item_text(item))
    if not rendered_change:
        st.caption("No added, removed or changed records were identified.")
    st.caption(f"Unchanged: {section.get('unchanged_count', 0)}")


def render_comparison_page() -> None:
    """Render the customer-first comparison of two stored run snapshots."""

    payload = as_dict(st.session_state.get("comparison_payload"))
    if not payload:
        st.info("Select two stored assessment runs from a project to compare them.")
        return
    if st.button("Back to project history", key="comparison_back_to_project", icon=":material/arrow_back:"):
        st.session_state["comparison_view"] = False
        st.session_state["project_portfolio_view"] = True
        request_navigation("Projects")

    st.markdown('<p class="interlock-section-kicker">Assessment comparison</p>', unsafe_allow_html=True)
    st.markdown('<h1 class="interlock-section-title">What changed?</h1>', unsafe_allow_html=True)
    st.markdown(
        '<p class="interlock-section-copy">A neutral comparison of two stored INTERLOCK assessments. Differences are shown from the recorded data; no new assessment has been run.</p>',
        unsafe_allow_html=True,
    )
    run_columns = st.columns(3)
    with run_columns[0]:
        st.markdown("**Baseline run**")
        st.caption(_format_portfolio_value(payload.get("baseline_run_id")))
        st.caption(f"{_format_portfolio_value(payload.get('baseline_timestamp'))} · {_format_portfolio_value(payload.get('baseline_workflow_status'))}")
        st.metric("Planned power (MW)", _format_portfolio_value(payload.get("baseline_planned_power_mw")))
    with run_columns[1]:
        st.markdown("**Compared run**")
        st.caption(_format_portfolio_value(payload.get("comparison_run_id")))
        st.caption(f"{_format_portfolio_value(payload.get('comparison_timestamp'))} · {_format_portfolio_value(payload.get('comparison_workflow_status'))}")
        st.metric("Planned power (MW)", _format_portfolio_value(payload.get("comparison_planned_power_mw")))
    with run_columns[2]:
        st.markdown("**Project**")
        st.markdown(f"### {_format_portfolio_value(payload.get('project_name'))}")
        st.caption("Stored comparison · no rerun")

    summary = as_dict(payload.get("summary"))
    metric_values = (
        ("Input changes", summary.get("input_changes", 0)),
        ("Domain changes", summary.get("domain_changes", 0)),
        ("New findings", summary.get("new_findings", 0)),
        ("Resolved unknowns", summary.get("resolved_unknowns", 0)),
        ("New reviews", summary.get("new_reviews", 0)),
        ("New actions", summary.get("new_actions", 0)),
    )
    metric_columns = st.columns(6)
    for column, (label_text, value) in zip(metric_columns, metric_values):
        with column:
            st.metric(label_text, value)

    st.markdown("### Inputs")
    input_changes = as_dict(payload.get("input_changes"))
    changed_inputs = [as_dict(item) for item in as_list(input_changes.get("changed"))]
    if changed_inputs:
        for item in changed_inputs:
            with st.container(border=True):
                st.markdown(f"**{_format_portfolio_value(item.get('label'))}**")
                st.write(
                    f"{_format_portfolio_value(item.get('previous_display'))}  →  "
                    f"{_format_portfolio_value(item.get('comparison_display'))}"
                )
    else:
        st.caption("No stored project input fields changed.")
    with st.expander("Show unchanged inputs"):
        unchanged_inputs = [as_dict(item) for item in as_list(input_changes.get("unchanged"))]
        if unchanged_inputs:
            for item in unchanged_inputs:
                st.caption(f"{item.get('label')}: {item.get('previous_display')}")
        else:
            st.caption("No unchanged input fields were recorded.")

    st.markdown("### Domains")
    domain_changes = [as_dict(item) for item in as_list(payload.get("domain_changes"))]
    for item in domain_changes:
        with st.container(border=True):
            state_columns = st.columns(4)
            state_columns[0].markdown(f"**{_format_portfolio_value(item.get('label'))}**")
            state_columns[1].metric("Baseline", _format_portfolio_value(item.get("baseline_state")))
            state_columns[2].markdown("### →")
            state_columns[3].metric("Compared", _format_portfolio_value(item.get("comparison_state")))
            st.caption(_format_portfolio_value(item.get("change_kind")))

    _render_comparison_section("Findings", as_dict(payload.get("finding_changes")))
    _render_comparison_section("Unknowns", as_dict(payload.get("unknown_changes")), removed_title="Resolved / removed")
    _render_comparison_section("Dependencies", as_dict(payload.get("dependency_changes")))
    _render_comparison_section("Human reviews", as_dict(payload.get("human_review_changes")), removed_title="No longer required")
    _render_comparison_section("Next actions", as_dict(payload.get("next_action_changes")))
    _render_comparison_section("Evidence", as_dict(payload.get("evidence_changes")))
    _render_comparison_section("Citations", as_dict(payload.get("citation_changes")))

    try:
        started = time.perf_counter()
        pdf_bytes = render_comparison_report_pdf(payload)
        elapsed_ms = (time.perf_counter() - started) * 1000
        st.download_button(
            "Download Comparison Report",
            data=pdf_bytes,
            file_name=safe_comparison_report_filename(payload),
            mime="application/pdf",
            key="download_comparison_report",
            icon=":material/download:",
        )
        st.caption(f"Generated from the stored comparison in {elapsed_ms:.1f} ms. Running a new assessment is not required.")
    except Exception:
        st.error("The comparison report could not be generated from these stored runs.")


def _ensure_assessment_form_state() -> None:
    defaults: dict[str, object] = {
        "project_name": "",
        "development_type": "Data Centre",
        "project_stage": "Unknown",
        "site_address": "",
        "local_authority": "",
        "latitude": None,
        "longitude": None,
        "site_area_hectares": None,
        "planned_power_demand_mw": None,
        "requested_mic_mva": None,
        "power_strategy": "Unknown",
        "energy_strategy": "",
        "project_phasing_notes": "",
        "project_evidence_mode": "Normal project",
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def _load_demo_project() -> None:
    text_fields = {
        "project_name",
        "development_type",
        "site_address",
        "local_authority",
        "energy_strategy",
        "project_phasing_notes",
    }
    for key, value in DEMO_PROJECT_PRESET.items():
        st.session_state[key] = "" if key in text_fields and value is None else value
    st.session_state["project_evidence_mode"] = DEMO_PROJECT_EVIDENCE_MODE
    st.session_state["demo_preset_loaded"] = True
    st.session_state["demo_run_summary"] = None


def render_public_data_debug(project_payload: dict[str, object] | None, api_base_url: str | None) -> None:
    if not api_base_url or not project_payload:
        st.caption("Validate a project and configure the backend to use the public-data debug check.")
        return
    if project_payload.get("latitude") is None or project_payload.get("longitude") is None:
        st.info("Provide latitude and longitude to run the Module 4B public-data check.")
        return
    if st.button("Run public data evidence check", key="debug_site_evidence", icon=":material/search:"):
        try:
            response = requests.post(
                f"{api_base_url.rstrip('/')}/evidence/site",
                json={key: value for key, value in project_payload.items() if key != "local_authority"},
                timeout=180,
            )
            response.raise_for_status()
            st.session_state["site_evidence_payload"] = response.json()
        except (requests.RequestException, ValueError, TypeError):
            st.error("The public-data evidence check could not be completed.")
    if st.session_state.get("site_evidence_payload"):
        st.json(st.session_state["site_evidence_payload"])


def render_rag_debug(api_base_url: str | None) -> None:
    with st.form("rag_search_form", border=True):
        query = st.text_area("Policy or regulatory question", placeholder="What connection requirements apply in Ireland?")
        workflow = st.selectbox("Workflow", ["Any workflow", "SITE_DISCOVERY", "SITE_FEASIBILITY", "POLICY_REGULATORY_INTELLIGENCE"])
        domains = st.multiselect("Domains", ["GRID", "ENERGY", "PLANNING", "BIODIVERSITY", "ENVIRONMENT", "WATER", "INFRASTRUCTURE", "GENERAL"])
        jurisdiction = st.selectbox("Jurisdiction", ["Any jurisdiction", "IRELAND", "EU", "LOCAL_AUTHORITY"])
        local_authority = st.text_input("Local authority (optional)")
        include_historical = st.checkbox("Include proposed / historical policy")
        include_supporting = st.checkbox("Include industry / research supporting material")
        top_k = st.number_input("Results per class", min_value=1, max_value=20, value=8, step=1)
        submitted = st.form_submit_button("Run retrieval", type="primary", icon=":material/search:")
    if submitted:
        if not api_base_url:
            st.error("The retrieval service is not configured.")
        elif not query.strip():
            st.error("Enter a policy or regulatory question.")
        else:
            try:
                response = requests.post(
                    f"{api_base_url.rstrip('/')}/rag/search",
                    json={
                        "query": query,
                        "workflow": None if workflow == "Any workflow" else workflow,
                        "domains": domains,
                        "jurisdiction": None if jurisdiction == "Any jurisdiction" else jurisdiction,
                        "local_authority": optional_text(local_authority),
                        "include_historical": include_historical,
                        "include_supporting": include_supporting,
                        "top_k": int(top_k),
                    },
                    timeout=30,
                )
                response.raise_for_status()
                st.session_state["rag_search_payload"] = response.json()
            except (requests.RequestException, ValueError, TypeError):
                st.error("The policy retrieval request could not be completed.")
    payload = st.session_state.get("rag_search_payload")
    if payload:
        st.caption(f"Mode: {payload.get('retrieval_mode')} · semantic available: {payload.get('semantic_available')}")
        for warning in as_list(payload.get("warnings")):
            st.warning(str(warning))
        for group_name, key in (
            ("Current authoritative evidence", "authoritative_results"),
            ("Trusted curated records", "curated_results"),
            ("Supporting evidence", "supporting_results"),
            ("Proposed / historical evidence", "historical_results"),
        ):
            results = as_list(payload.get(key))
            st.markdown(f"#### {group_name}")
            if results:
                for result in results:
                    item = as_dict(result)
                    with st.container(border=True):
                        st.markdown(f"**{item.get('title') or 'Untitled'}** · {item.get('source_class') or 'Source class unknown'}")
                        st.caption(str(item.get("citation") or "Citation unavailable"))
                        st.write(str(item.get("text") or ""))
            else:
                st.caption("No results in this class.")


def render_individual_agent_debug(context_payload: dict[str, object] | None, api_base_url: str | None) -> None:
    if not context_payload or not api_base_url:
        st.caption("Run a validated assessment to use the individual agent endpoints.")
        return
    if st.button("Run Evidence Agent endpoint", key="debug_evidence_agent", icon=":material/account_tree:"):
        try:
            response = requests.post(
                f"{api_base_url.rstrip('/')}/agents/evidence",
                json=context_payload,
                timeout=240,
            )
            response.raise_for_status()
            st.session_state["evidence_agent_payload"] = response.json()
        except (requests.RequestException, ValueError, TypeError):
            st.error("The Evidence Agent endpoint could not be completed.")
    evidence_payload = st.session_state.get("evidence_agent_payload")
    if evidence_payload and st.button("Run Assessment Agent endpoint", key="debug_assessment_agent", icon=":material/assessment:"):
        try:
            response = requests.post(
                f"{api_base_url.rstrip('/')}/agents/assessment",
                json={"project_context": evidence_payload.get("project_context"), "evidence_bundle": evidence_payload},
                timeout=30,
            )
            response.raise_for_status()
            st.session_state["assessment_payload"] = response.json()
        except (requests.RequestException, ValueError, TypeError):
            st.error("The Assessment Agent endpoint could not be completed.")
    assessment_payload = st.session_state.get("assessment_payload")
    if assessment_payload and st.button("Run Explanation Agent endpoint", key="debug_explanation_agent", icon=":material/description:"):
        try:
            response = requests.post(
                f"{api_base_url.rstrip('/')}/agents/explanation",
                json={
                    "project_context": assessment_payload.get("project_context"),
                    "assessment_result": assessment_payload,
                    "evidence_bundle": evidence_payload,
                },
                timeout=30,
            )
            response.raise_for_status()
            st.session_state["explanation_payload"] = response.json()
        except (requests.RequestException, ValueError, TypeError):
            st.error("The Explanation Agent endpoint could not be completed.")
    for key in ("evidence_agent_payload", "assessment_payload", "explanation_payload"):
        if st.session_state.get(key):
            with st.expander(f"Raw {key.replace('_', ' ')}"):
                st.json(st.session_state[key])


def render_evidence_page(api_base_url: str | None) -> None:
    render_evidence_view(st.session_state.get("interlock_payload"))
    with st.expander("Developer / Debug Tools", icon=":material/build:"):
        st.markdown("#### Module 4B public-data check")
        render_public_data_debug(st.session_state.get("submitted_project_payload"), api_base_url)
        st.markdown("#### Module 5B policy retrieval")
        render_rag_debug(api_base_url)
        st.markdown("#### Individual Module 6–8 endpoints")
        submitted = st.session_state.get("submitted_project_payload")
        context = build_evidence_agent_context(submitted) if submitted else None
        render_individual_agent_debug(context, api_base_url)


st.session_state.setdefault("active_page", "Home")
st.session_state.setdefault("active_navigation", PAGE_TO_NAVIGATION.get(st.session_state["active_page"], "Home"))
st.session_state.setdefault("_rendered_page", st.session_state["active_page"])
st.session_state.setdefault("pending_navigation", None)
for key in (
    "validation_payload",
    "submitted_project_payload",
    "interlock_payload",
    "site_evidence_payload",
    "evidence_agent_payload",
    "assessment_payload",
    "explanation_payload",
    "rag_search_payload",
    "demo_preset_loaded",
    "demo_run_summary",
    "active_project_id",
    "active_run_id",
    "assessment_project_id",
    "comparison_project_id",
    "comparison_baseline_run_id",
    "comparison_run_id",
    "comparison_payload",
):
    st.session_state.setdefault(key, None)
if st.session_state.get("project_portfolio_view") is None:
    st.session_state["project_portfolio_view"] = False
if st.session_state.get("comparison_view") is None:
    st.session_state["comparison_view"] = False

pending_navigation = st.session_state.pop("pending_navigation", None)
if pending_navigation in PAGE_NAMES:
    st.session_state["active_page"] = pending_navigation
    st.session_state["active_navigation"] = PAGE_TO_NAVIGATION.get(pending_navigation, "Home")
elif st.session_state["active_page"] != st.session_state.get("_rendered_page"):
    # Keeps AppTest/programmatic state changes and restored sessions aligned
    # before the keyed navigation widget is instantiated.
    st.session_state["active_navigation"] = PAGE_TO_NAVIGATION.get(st.session_state["active_page"], "Home")


render_brand_header()
api_base_url = os.getenv("INTERLOCK_API_BASE_URL")

selected_navigation = st.pills(
    "Primary navigation",
    list(NAVIGATION_ITEMS),
    key="active_navigation",
    label_visibility="collapsed",
    selection_mode="single",
)
if not selected_navigation:
    selected_navigation = st.session_state["active_navigation"]

if selected_navigation != "Projects" and st.session_state.get("comparison_view"):
    st.session_state["comparison_view"] = False

if selected_navigation == "Projects":
    # Preserve the established post-assessment Decision Pack landing state,
    # while allowing the explicit portfolio view to open independently.
    active_page = (
        "Assessment Comparison"
        if st.session_state.get("comparison_view") and st.session_state.get("comparison_payload")
        else "Projects"
        if st.session_state.get("project_portfolio_view") or not st.session_state.get("interlock_payload")
        else "Decision Pack"
    )
else:
    active_page = NAVIGATION_ROUTES.get(selected_navigation, "Home")
if active_page != st.session_state["active_page"]:
    request_navigation(active_page)
st.session_state["_rendered_page"] = active_page

if active_page == "Home":
    start_clicked, explore_clicked = render_home()
    if start_clicked:
        request_navigation("New Assessment")
    if explore_clicked:
        request_navigation("About")
elif active_page == "New Assessment":
    render_assessment_page(api_base_url)
elif active_page == "Projects":
    render_projects_page(api_base_url)
elif active_page == "Decision Pack":
    payload = st.session_state.get("interlock_payload")
    if payload:
        if st.button("View project portfolio", key="decision_view_portfolio", icon=":material/folder_open:"):
            st.session_state["project_portfolio_view"] = True
            request_navigation("Projects")
        render_decision_pack(payload)
        render_demo_run_summary(st.session_state.get("demo_run_summary"))
    else:
        st.markdown('<p class="interlock-section-kicker">Project / assessment result</p>', unsafe_allow_html=True)
        st.markdown('<h1 class="interlock-section-title">Your decision pack will appear here.</h1>', unsafe_allow_html=True)
        st.info("Start a new assessment to generate a traceable INTERLOCK result.")
        if st.button("Start a new site assessment", type="primary", icon=":material/arrow_forward:"):
            request_navigation("New Assessment")
elif active_page == "Assessment Comparison":
    render_comparison_page()
elif active_page == "Evidence":
    render_evidence_page(api_base_url)
elif active_page == "Insights":
    render_insights(st.session_state.get("interlock_payload"))
else:
    render_about()
