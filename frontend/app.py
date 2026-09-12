"""Polished Streamlit frontend for the INTERLOCK development journey."""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any

import requests
import streamlit as st

from components import (
    as_dict,
    as_list,
    render_decision_pack,
    render_evidence_view,
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


PAGE_NAMES = ("Home", "New Assessment", "Decision Pack", "Evidence", "Methodology")
NAVIGATION_ITEMS = ("Home", "New Assessment", "Projects", "Data Layers", "Insights", "About")
NAVIGATION_ROUTES = {
    "Home": "Home",
    "New Assessment": "New Assessment",
    "Projects": "Decision Pack",
    "Data Layers": "Evidence",
    "Insights": "Methodology",
    "About": "Methodology",
}
PAGE_TO_NAVIGATION = {
    "Home": "Home",
    "New Assessment": "New Assessment",
    "Decision Pack": "Projects",
    "Evidence": "Data Layers",
    "Methodology": "Insights",
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
            response = requests.post(
                f"{api_base_url.rstrip('/')}/interlock/run",
                params={
                    "include_project_documents": "true",
                    "include_benchmark_documents": str(project_evidence_mode.endswith("Validation")).lower(),
                },
                json=context_payload,
                timeout=300,
            )
            response.raise_for_status()
            payload = response.json()
            workflow_status = str(payload.get("workflow_status") or "UNKNOWN")
            st.session_state["submitted_project_payload"] = project_payload
            st.session_state["interlock_payload"] = payload
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
        run_interlock(
            project_payload,
            project_evidence_mode,
            api_base_url,
            project_id_override=DEMO_PROJECT_ID if demo_loaded else None,
            preset_metadata=DEMO_PROJECT_METADATA if demo_loaded else None,
        )
        if st.session_state.get("interlock_payload"):
            request_navigation("Decision Pack")


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
):
    st.session_state.setdefault(key, None)

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

active_page = NAVIGATION_ROUTES.get(selected_navigation, "Home")
if active_page != st.session_state["active_page"]:
    request_navigation(active_page)
st.session_state["_rendered_page"] = active_page

if active_page == "Home":
    start_clicked, explore_clicked = render_home()
    if start_clicked:
        request_navigation("New Assessment")
    if explore_clicked:
        request_navigation("Methodology")
elif active_page == "New Assessment":
    render_assessment_page(api_base_url)
elif active_page == "Decision Pack":
    payload = st.session_state.get("interlock_payload")
    if payload:
        render_decision_pack(payload)
        render_demo_run_summary(st.session_state.get("demo_run_summary"))
    else:
        st.markdown('<p class="interlock-section-kicker">Project / assessment result</p>', unsafe_allow_html=True)
        st.markdown('<h1 class="interlock-section-title">Your decision pack will appear here.</h1>', unsafe_allow_html=True)
        st.info("Start a new assessment to generate a traceable INTERLOCK result.")
        if st.button("Start a new site assessment", type="primary", icon=":material/arrow_forward:"):
            request_navigation("New Assessment")
elif active_page == "Evidence":
    render_evidence_page(api_base_url)
else:
    render_methodology()
