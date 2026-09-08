"""Streamlit frontend for the INTERLOCK project-input and Module 4B workflow."""

import hashlib
import json
import os

import requests
import streamlit as st


st.set_page_config(page_title="INTERLOCK", page_icon=":material/link:", layout="centered")

st.title("INTERLOCK")
st.subheader("Data Centre Development Intelligence")
st.write("Evidence-linked decision support for early data-centre development.")


api_base_url = os.getenv("INTERLOCK_API_BASE_URL")

if not api_base_url:
    st.error("Backend connection is not configured. Set INTERLOCK_API_BASE_URL.")
else:
    try:
        health_response = requests.get(
            f"{api_base_url.rstrip('/')}/health",
            timeout=5,
        )
        health_response.raise_for_status()
        health_payload = health_response.json()

        if isinstance(health_payload, dict) and health_payload.get("status") == "ok":
            st.success("Backend connected")
        else:
            st.error("Backend responded, but its health status was not OK.")
    except requests.RequestException as exc:
        st.error(f"Backend connection failed: {exc}")
    except ValueError:
        st.error("Backend returned an invalid health response.")


def optional_text(value: str) -> str | None:
    """Convert an empty form text value to an explicit missing value."""

    cleaned = value.strip()
    return cleaned or None


def display_value(value: object) -> str:
    """Format null and Unknown values clearly in the submitted summary."""

    if value is None:
        return "Unknown / not provided"
    if value == "Unknown":
        return "Unknown"
    return str(value)


def display_evidence_value(value: object) -> str:
    """Format a ledger value without conflating Unknown and not provided."""

    if value is None:
        return "—"
    return str(value)


def build_evidence_agent_context(
    project: dict[str, object],
    *,
    project_evidence_mode: str = "Normal project",
) -> dict[str, object]:
    """Build the shared ProjectContext from the already validated form values."""

    stable_payload = json.dumps(project, sort_keys=True, default=str).encode("utf-8")
    project_id = "streamlit-" + hashlib.sha256(stable_payload).hexdigest()[:12]
    has_coordinates = project.get("latitude") is not None and project.get("longitude") is not None
    herbata_mode = project_evidence_mode.startswith("Herbata")
    return {
        "project_id": "benchmark-herbata-naas" if herbata_mode else project_id,
        "project_name": "Herbata Data Centre benchmark" if herbata_mode else project.get("project_name"),
        "project_type": project.get("development_type"),
        "assessment_workflow": "SITE_FEASIBILITY" if has_coordinates else "SITE_DISCOVERY",
        "project_lifecycle_status": "UNKNOWN",
        "location": {
            "address": project.get("site_address"),
            "latitude": project.get("latitude"),
            "longitude": project.get("longitude"),
            "local_authority": None,
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
        "developer_inputs": {
            "source": "validated_streamlit_project_input",
            "project_evidence_mode": project_evidence_mode,
        },
        "uploaded_document_refs": [],
        "source_project_input": project,
    }


def render_state(state: str | None) -> None:
    """Render controlled FACT/UNKNOWN/LIMITATION labels without recommendations."""

    if state == "FACT":
        st.success("FACT")
    elif state == "UNKNOWN":
        st.info("UNKNOWN")
    else:
        st.warning("LIMITATION")


def render_site_domain(payload: dict[str, object]) -> None:
    """Display a compact, transparent domain result from the site-evidence API."""

    render_state(str(payload.get("evidence_state", "UNKNOWN")))
    if payload.get("status") == "ERROR":
        st.error(str(payload.get("reason", "Domain evidence failed.")))
    elif payload.get("reason"):
        st.info(str(payload["reason"]))

    if "intersects" in payload:
        st.write(f"**Intersects:** {payload['intersects']}")
    if "project_point_intersects" in payload:
        st.write(f"**Project point intersects:** {payload['project_point_intersects']}")
    if "counts_within_radii" in payload:
        st.write("**Counts within configured radii:**")
        st.table(payload["counts_within_radii"])
    if "nearby_records" in payload and payload["nearby_records"]:
        st.write("**Nearby records:**")
        st.dataframe(payload["nearby_records"], hide_index=True)
    if "nearby_assets" in payload and payload["nearby_assets"]:
        st.write("**Nearby contextual assets:**")
        st.dataframe(payload["nearby_assets"], hide_index=True)
    for key in (
        "nearest_protected_site",
        "nearest_zone",
        "nearest_landform",
        "nearest_connection",
        "intersections",
        "intersecting_zones",
        "intersecting_connections",
        "documents",
        "policy_documents",
    ):
        value = payload.get(key)
        if value:
            st.write(f"**{key.replace('_', ' ').title()}:**")
            st.json(value)
    if payload.get("limitations"):
        st.caption("Limitation: " + " ".join(str(item) for item in payload["limitations"]))


def render_site_evidence(payload: dict[str, object]) -> None:
    """Render only the requested Module 4B evidence preview sections."""

    st.subheader("Public data evidence")
    st.caption("Deterministic public-data evidence only. No overall recommendation is produced.")
    location = payload.get("project_location", {})
    with st.container(border=True):
        st.write(
            f"**Location:** {location.get('latitude')}, {location.get('longitude')} WGS84 → "
            f"{location.get('easting')}, {location.get('northing')} {location.get('transformed_crs')}"
        )
        st.write(f"**Checked:** {location.get('checked_at')}")

    tab_names = [
        "Biodiversity",
        "Flood",
        "Planning",
        "Heritage",
        "Ground",
        "Grid",
        "Zoning",
        "Water",
    ]
    tabs = st.tabs(tab_names)
    for tab, key in zip(tabs, [name.lower() for name in tab_names]):
        with tab:
            section = payload.get(key, {})
            if isinstance(section, dict):
                if key == "biodiversity":
                    for subkey in ("sac", "spa"):
                        st.markdown(f"#### {subkey.upper()}")
                        render_site_domain(section.get(subkey, {}))
                elif key == "flood":
                    for subkey in ("coastal", "fluvial"):
                        st.markdown(f"#### {subkey.title()}")
                        for layer in section.get(subkey, []):
                            with st.container(border=True):
                                st.write(
                                    f"**{layer.get('source_layer')} · return period "
                                    f"{layer.get('return_period')}**"
                                )
                                render_site_domain(layer)
                elif key == "ground":
                    for subkey in ("groundwater", "karst_landforms", "karst_connections"):
                        st.markdown(f"#### {subkey.replace('_', ' ').title()}")
                        render_site_domain(section.get(subkey, {}))
                else:
                    render_site_domain(section)

    timings = payload.get("timings_ms", {})
    if timings:
        st.caption("Execution timings (ms): " + ", ".join(f"{key}={value}" for key, value in timings.items()))


def render_evidence_agent(payload: dict[str, object]) -> None:
    """Render the evidence bundle without introducing an assessment decision."""

    st.subheader("Evidence Agent")
    st.caption("Deterministic evidence assembly only. No Advance/Hold/Reconfigure/Stop decision is produced.")
    summary = payload.get("provenance_summary", {})
    metrics = st.columns(4)
    metrics[0].metric("Project", summary.get("developer_records", 0))
    metrics[1].metric("GIS", summary.get("gis_records", 0))
    metrics[2].metric("Policy", summary.get("policy_records", 0))
    metrics[3].metric("Unknown / missing", summary.get("unknown_or_missing_count", 0))

    records = payload.get("records", [])
    if not isinstance(records, list):
        records = []
    sections = (
        ("Developer input", {"DEVELOPER_INPUT"}),
        ("Project documents (untrusted evidence)", {"PROJECT_DOCUMENT"}),
        ("Public/GIS evidence", {"DETERMINISTIC_GIS"}),
        ("Policy/regulatory evidence", {"RAG_RETRIEVAL"}),
    )
    for title, creators in sections:
        st.markdown(f"#### {title}")
        selected = [item for item in records if item.get("created_by") in creators]
        if not selected:
            st.caption("No records in this class.")
            continue
        rows = [
            {
                "Domain": item.get("domain"),
                "State": item.get("evidence_state"),
                "Finding": item.get("finding") or item.get("fact"),
                "Source": item.get("source_name"),
                "Trust boundary": item.get("source_trust"),
                "Verification": item.get("verification_status"),
            }
            for item in selected
        ]
        st.dataframe(rows, hide_index=True)

    for title, key in (
        ("Unknowns / missing evidence", "missing_evidence"),
        ("Dependencies", "dependencies"),
        ("Potential contradictions", "potential_contradictions"),
        ("Human reviews", "human_review_requests"),
    ):
        st.markdown(f"#### {title}")
        values = payload.get(key, [])
        if values:
            st.json(values)
        else:
            st.caption("None recorded.")

    citations = [
        {
            "document_id": item.get("source_document_id"),
            "source": item.get("source_name"),
            "citation": item.get("citation"),
        }
        for item in records
        if item.get("source_document_id") or item.get("citation")
    ]
    st.markdown("#### Sources / citations")
    if citations:
        st.json(citations)
    else:
        st.caption("No structured citations recorded.")


def render_retrieval_hit(hit: dict[str, object]) -> None:
    """Display one provenance-preserving retrieval result without interpreting it."""

    st.markdown(
        f"**{hit.get('title', 'Untitled')}** · {hit.get('source_class')} · "
        f"{hit.get('document_status')}"
    )
    st.caption(
        f"{hit.get('issuer') or 'Issuer unknown'} · {hit.get('citation') or 'Citation unavailable'} · "
        f"verification: {hit.get('verification_status')}"
    )
    st.write(str(hit.get("text", "")))
    st.caption(
        "Retrieval ranks: "
        f"lexical={hit.get('lexical_rank') or '—'}, semantic={hit.get('semantic_rank') or '—'}, "
        f"fusion={hit.get('fusion_score') or '—'}"
    )


def render_retrieval_group(title: str, hits: list[dict[str, object]]) -> None:
    """Display one retrieval result class, keeping authority classes separate."""

    st.subheader(title)
    if not hits:
        st.caption("No results in this class.")
        return
    for index, hit in enumerate(hits, start=1):
        with st.container(border=True):
            st.caption(f"Result {index}")
            render_retrieval_hit(hit)


st.header("New Site Assessment")

with st.form("project_input_form"):
    st.markdown("#### Project")
    project_name = st.text_input("Project Name (optional)")
    development_type = st.text_input("Development Type", value="Data Centre")
    project_stage = st.selectbox(
        "Project Stage",
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
        index=7,
    )

    st.markdown("#### Site")
    site_address = st.text_input("Site Address (optional)")
    latitude = st.number_input(
        "Latitude (optional)",
        min_value=-90.0,
        max_value=90.0,
        value=None,
        step=0.0001,
        format="%.4f",
    )
    longitude = st.number_input(
        "Longitude (optional)",
        min_value=-180.0,
        max_value=180.0,
        value=None,
        step=0.0001,
        format="%.4f",
    )
    site_area_hectares = st.number_input(
        "Site Area (hectares, optional)",
        min_value=0.0,
        value=None,
        step=0.1,
        format="%.2f",
    )

    st.markdown("#### Power & Energy")
    planned_power_demand_mw = st.number_input(
        "Planned Power Demand (MW, optional)",
        min_value=0.0,
        value=None,
        step=1.0,
        format="%.2f",
    )
    requested_mic_mva = st.number_input(
        "Requested MIC (MVA, optional)",
        min_value=0.0,
        value=None,
        step=1.0,
        format="%.2f",
    )
    power_strategy = st.selectbox(
        "Power Strategy",
        options=[
            "Existing Grid Connection",
            "New Grid Connection",
            "Developer-Built Substation",
            "Hybrid / Alternative Strategy",
            "Unknown",
        ],
        index=4,
    )
    energy_strategy = st.text_input(
        "Energy Strategy (optional)",
        placeholder="Enter a known strategy or leave blank",
    )

    st.markdown("#### Additional Information")
    project_phasing_notes = st.text_area("Project Phasing / Notes (optional)")

    submitted = st.form_submit_button("Validate Project Input")

st.session_state.setdefault("validation_payload", None)
st.session_state.setdefault("evidence_payload", None)
st.session_state.setdefault("site_evidence_payload", None)
st.session_state.setdefault("evidence_agent_payload", None)

if submitted:
    if not api_base_url:
        st.error("Project input could not be validated because the backend URL is not configured.")
    else:
        project_payload = {
            "project_name": optional_text(project_name),
            "development_type": optional_text(development_type),
            "project_stage": project_stage,
            "site_address": optional_text(site_address),
            "latitude": latitude,
            "longitude": longitude,
            "site_area_hectares": site_area_hectares,
            "planned_power_demand_mw": planned_power_demand_mw,
            "requested_mic_mva": requested_mic_mva,
            "power_strategy": power_strategy,
            "energy_strategy": optional_text(energy_strategy),
            "project_phasing_notes": optional_text(project_phasing_notes),
        }

        try:
            validation_response = requests.post(
                f"{api_base_url.rstrip('/')}/project-input/validate",
                json=project_payload,
                timeout=10,
            )
            validation_response.raise_for_status()
            validation_payload = validation_response.json()

            st.session_state["validation_payload"] = validation_payload
            st.session_state["site_evidence_payload"] = None
            st.session_state["evidence_agent_payload"] = None
            try:
                evidence_response = requests.post(
                    f"{api_base_url.rstrip('/')}/evidence/from-project",
                    json=project_payload,
                    timeout=10,
                )
                evidence_response.raise_for_status()
                evidence_payload = evidence_response.json()

                st.session_state["evidence_payload"] = evidence_payload
            except requests.HTTPError:
                st.error("The project was validated, but the initial evidence ledger could not be generated.")
                st.session_state["evidence_payload"] = None
            except requests.RequestException:
                st.error("The project was validated, but the evidence service is unavailable.")
                st.session_state["evidence_payload"] = None
            except (KeyError, TypeError, ValueError):
                st.error("The backend returned an invalid evidence-ledger response.")
                st.session_state["evidence_payload"] = None
        except requests.HTTPError as exc:
            detail = "The submitted project input was rejected."
            try:
                error_payload = exc.response.json()
                if isinstance(error_payload, dict) and error_payload.get("detail"):
                    detail = "The submitted project input was rejected by the backend."
            except (ValueError, AttributeError):
                pass
            st.error(detail)
        except requests.RequestException:
            st.error("Project input could not be validated because the backend is unavailable.")
        except (KeyError, TypeError, ValueError):
            st.error("The backend returned an invalid validation response.")


validation_payload = st.session_state.get("validation_payload")
if validation_payload:
    st.success("Project input validated")
    st.subheader("Submitted project")
    for field_name, value in validation_payload["project"].items():
        label = field_name.replace("_", " ").title()
        st.write(f"**{label}:** {display_value(value)}")

    st.subheader("Information still missing or unknown")
    missing_fields = validation_payload.get("missing_or_unknown", [])
    if missing_fields:
        for field_name in missing_fields:
            st.markdown(f"- {field_name.replace('_', ' ').title()}")
    else:
        st.write("No fields are currently missing or marked Unknown.")

    evidence_payload = st.session_state.get("evidence_payload")
    if evidence_payload:
        st.subheader("Initial Evidence Ledger")
        count_columns = st.columns(3)
        count_columns[0].metric("Provided", evidence_payload["provided_count"])
        count_columns[1].metric("Unknown", evidence_payload["unknown_count"])
        count_columns[2].metric("Not provided", evidence_payload["not_provided_count"])
        evidence_rows = [
            {
                "Category": entry["category"],
                "Evidence": entry["fact"],
                "Value": display_evidence_value(entry["value"]),
                "Unit": entry["unit"] or "—",
                "State": entry["evidence_state"],
                "Source": entry["source_name"],
                "Confidence": entry["confidence"],
                "Review Status": entry["review_status"],
            }
            for entry in evidence_payload["entries"]
        ]
        st.table(evidence_rows)
        st.caption(
            "Customer-provided information has not yet been independently verified. "
            "Public-data checks add evidence; they do not replace customer evidence."
        )

        project_for_evidence = validation_payload["project"]
        if project_for_evidence.get("latitude") is None or project_for_evidence.get("longitude") is None:
            st.info("Provide both latitude and longitude to run the public data evidence check.")
        elif st.button(
            "Run Public Data Evidence Check",
            key="run_site_evidence",
            type="primary",
            icon=":material/search:",
        ):
            try:
                site_response = requests.post(
                    f"{api_base_url.rstrip('/')}/evidence/site",
                    json=project_for_evidence,
                    timeout=180,
                )
                site_response.raise_for_status()
                st.session_state["site_evidence_payload"] = site_response.json()
            except requests.HTTPError:
                st.error("The project was validated, but the public data evidence check failed.")
            except requests.RequestException:
                st.error("The public data evidence service is unavailable.")
            except (KeyError, TypeError, ValueError):
                st.error("The backend returned an invalid site-evidence response.")

    project_for_evidence = validation_payload["project"]
    project_evidence_mode = st.selectbox(
        "Project evidence mode",
        options=[
            "Normal project",
            "Herbata benchmark — Early Evidence",
            "Herbata benchmark — Validation",
        ],
        help="Project documents remain separate from authoritative Module 5 policy evidence. Validation explicitly includes benchmark-only documents.",
    )
    if st.button(
        "Run Evidence Agent",
        key="run_evidence_agent",
        type="primary",
        icon=":material/account_tree:",
    ):
        if not api_base_url:
            st.error("The Evidence Agent could not run because the backend URL is not configured.")
        else:
            try:
                agent_response = requests.post(
                    f"{api_base_url.rstrip('/')}/agents/evidence",
                    params={
                        "include_project_documents": "true",
                        "include_benchmark_documents": str(project_evidence_mode.endswith("Validation")).lower(),
                    },
                    json=build_evidence_agent_context(
                        project_for_evidence,
                        project_evidence_mode=project_evidence_mode,
                    ),
                    timeout=240,
                )
                agent_response.raise_for_status()
                st.session_state["evidence_agent_payload"] = agent_response.json()
            except requests.HTTPError:
                st.error("The Evidence Agent request was rejected by the backend.")
            except requests.RequestException:
                st.error("The Evidence Agent service is unavailable.")
            except (KeyError, TypeError, ValueError):
                st.error("The backend returned an invalid Evidence Agent response.")

    site_evidence_payload = st.session_state.get("site_evidence_payload")
    if site_evidence_payload:
        render_site_evidence(site_evidence_payload)

    evidence_agent_payload = st.session_state.get("evidence_agent_payload")
    if evidence_agent_payload:
        render_evidence_agent(evidence_agent_payload)


st.header("Policy & Regulatory Retrieval")
st.caption(
    "Developer/debug view for Module 5B. It retrieves cited evidence only; it does not generate a regulatory conclusion, score, or recommendation."
)
st.session_state.setdefault("rag_search_payload", None)

with st.form("rag_search_form", border=True):
    rag_query = st.text_area(
        "Policy or regulatory question",
        placeholder="What connection requirements apply to a large data centre in Ireland?",
        height=90,
    )
    rag_workflow_label = st.selectbox(
        "Workflow",
        options=[
            "Any workflow",
            "SITE_DISCOVERY",
            "SITE_FEASIBILITY",
            "POLICY_REGULATORY_INTELLIGENCE",
        ],
    )
    rag_domains = st.multiselect(
        "Domains",
        options=[
            "GRID",
            "ENERGY",
            "PLANNING",
            "BIODIVERSITY",
            "ENVIRONMENT",
            "WATER",
            "DATA_CENTRE_POLICY",
            "INFRASTRUCTURE",
            "EU_REPORTING",
            "RESPONSIBLE_AI",
            "GENERAL",
        ],
    )
    rag_jurisdiction = st.selectbox(
        "Jurisdiction",
        options=["Any jurisdiction", "IRELAND", "EU", "LOCAL_AUTHORITY"],
    )
    rag_local_authority = st.text_input(
        "Local authority (optional)",
        placeholder="Fingal or Wicklow",
    )
    rag_include_historical = st.checkbox("Include proposed/historical policy")
    rag_include_supporting = st.checkbox("Include industry/research supporting material")
    rag_top_k = st.number_input("Results per class", min_value=1, max_value=20, value=8, step=1)
    rag_submitted = st.form_submit_button("Run retrieval", type="primary", icon=":material/search:")

if rag_submitted:
    if not api_base_url:
        st.error("Retrieval could not run because the backend URL is not configured.")
    elif not rag_query.strip():
        st.error("Enter a policy or regulatory question.")
    else:
        rag_payload = {
            "query": rag_query,
            "workflow": None if rag_workflow_label == "Any workflow" else rag_workflow_label,
            "domains": rag_domains,
            "jurisdiction": None if rag_jurisdiction == "Any jurisdiction" else rag_jurisdiction,
            "local_authority": optional_text(rag_local_authority),
            "include_historical": rag_include_historical,
            "include_supporting": rag_include_supporting,
            "top_k": int(rag_top_k),
        }
        try:
            rag_response = requests.post(
                f"{api_base_url.rstrip('/')}/rag/search",
                json=rag_payload,
                timeout=30,
            )
            rag_response.raise_for_status()
            st.session_state["rag_search_payload"] = rag_response.json()
        except requests.HTTPError as exc:
            detail = "The retrieval request was rejected by the backend."
            try:
                error_payload = exc.response.json()
                if isinstance(error_payload, dict) and error_payload.get("detail"):
                    detail = str(error_payload["detail"])
            except (ValueError, AttributeError):
                pass
            st.error(detail)
        except requests.RequestException:
            st.error("The retrieval service is unavailable.")
        except ValueError:
            st.error("The backend returned an invalid retrieval response.")

rag_search_payload = st.session_state.get("rag_search_payload")
if rag_search_payload:
    if rag_search_payload.get("warnings"):
        for warning in rag_search_payload["warnings"]:
            st.warning(str(warning))
    st.caption(
        f"Mode: {rag_search_payload.get('retrieval_mode')} · "
        f"semantic available: {rag_search_payload.get('semantic_available')}"
    )
    for gap in rag_search_payload.get("gaps", []):
        st.info(f"Evidence gap: {gap.get('message', gap.get('type'))}")
    render_retrieval_group("Current authoritative evidence", rag_search_payload.get("authoritative_results", []))
    render_retrieval_group("Trusted curated records", rag_search_payload.get("curated_results", []))
    render_retrieval_group("Supporting evidence", rag_search_payload.get("supporting_results", []))
    render_retrieval_group("Proposed / historical evidence", rag_search_payload.get("historical_results", []))
    if rag_search_payload.get("comparison_candidates"):
        with st.expander("Comparison candidates"):
            st.json(rag_search_payload["comparison_candidates"])
