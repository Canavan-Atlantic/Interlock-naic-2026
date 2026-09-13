"""Customer-facing Streamlit components for the INTERLOCK journey."""

from __future__ import annotations

import base64
import html
import os
from collections import defaultdict
from pathlib import Path
from typing import Any

import streamlit as st

try:
    from .map_view import render_map_first_view
    from .report import render_assessment_report_pdf, safe_report_filename
    from .result_summary import assessment_domain_state_summary, summarize_interlock_result
except ImportError:  # Streamlit executes frontend/app.py as a top-level script.
    from map_view import render_map_first_view
    from report import render_assessment_report_pdf, safe_report_filename
    from result_summary import assessment_domain_state_summary, summarize_interlock_result


SOURCE_LABELS = {
    "DEVELOPER_INPUT": "Developer Provided",
    "DETERMINISTIC_GIS": "Public / GIS Evidence",
    "RAG_RETRIEVAL": "Supporting Policy",
    "PROJECT_DOCUMENT": "Project Evidence",
    "AI_EXTRACTION": "Project Evidence",
}

HERO_ASSET_PATH = Path(__file__).with_name("assets") / "interlock_hero.png"
LOGO_ASSET_PATH = Path(__file__).with_name("assets") / "canavan_atlantic_logo.png"
WHITE_LOGO_ASSET_PATH = Path(__file__).with_name("assets") / "canavan_atlantic_logo_white.png"
HERO_GRADIENT = (
    "linear-gradient(90deg, rgba(2, 49, 63, 0.97) 0%, "
    "rgba(2, 55, 67, 0.88) 28%, rgba(2, 55, 67, 0.55) 43%, "
    "rgba(2, 55, 67, 0.18) 58%, rgba(0, 0, 0, 0.02) 72%)"
)

LINE_ICONS = {
    "leaf": '<svg viewBox="0 0 48 48" aria-hidden="true"><path d="M38 8C22 9 11 17 11 30c0 5 4 9 9 9 13 0 21-11 18-31Z"/><path d="M10 40c5-10 12-16 24-23"/></svg>',
    "layers": '<svg viewBox="0 0 48 48" aria-hidden="true"><path d="m24 7 17 10-17 10L7 17 24 7Z"/><path d="m10 25 14 8 14-8"/><path d="m10 34 14 8 14-8"/></svg>',
    "chart": '<svg viewBox="0 0 48 48" aria-hidden="true"><path d="M8 41h33"/><path d="M13 36V25h7v11M24 36V16h7v20M35 36V9h7v27"/></svg>',
    "shield": '<svg viewBox="0 0 48 48" aria-hidden="true"><path d="M24 6c6 5 11 6 17 7v11c0 10-7 16-17 20C14 40 7 34 7 24V13c6-1 11-2 17-7Z"/></svg>',
    "folder": '<svg viewBox="0 0 48 48" aria-hidden="true"><path d="M7 14h13l4 4h17v22H7V14Z"/><path d="M7 19h34"/></svg>',
    "search": '<svg viewBox="0 0 48 48" aria-hidden="true"><circle cx="21" cy="21" r="12"/><path d="m30 30 11 11"/></svg>',
    "document": '<svg viewBox="0 0 48 48" aria-hidden="true"><path d="M11 6h19l8 8v28H11V6Z"/><path d="M30 6v9h8M17 23h15M17 30h15M17 37h10"/></svg>',
}

ROLE_LABELS = {
    "PLANNING_CONSULTANT": "Planning consultant",
    "ECOLOGIST": "Ecologist",
    "GRID_ENGINEER": "Grid engineer",
    "EIA_ENVIRONMENTAL_CONSULTANT": "Environmental / EIA specialist",
    "DEVELOPER": "Developer / project team",
    "LEGAL_REGULATORY": "Legal / regulatory",
    "UNKNOWN": "Specialist review",
}

DOMAIN_LABELS = {
    "GRID": "Grid",
    "ENERGY": "Energy",
    "PLANNING": "Planning",
    "BIODIVERSITY": "Biodiversity",
    "ENVIRONMENT": "Environment",
    "WATER": "Water",
    "INFRASTRUCTURE": "Infrastructure",
    "GENERAL": "General project evidence",
    "UNKNOWN": "Unclassified",
}


def as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def display_value(value: object) -> str:
    if value is None or value == "":
        return "Unknown / not provided"
    if value == "Unknown":
        return "Unknown"
    return str(value)


def label(value: object, mapping: dict[str, str] | None = None) -> str:
    text = str(value or "UNKNOWN")
    if mapping and text in mapping:
        return mapping[text]
    return text.replace("_", " ").title()


def source_label(record: dict[str, Any]) -> str:
    """Translate internal provenance enums into customer-safe source labels."""

    created_by = str(record.get("created_by") or "UNKNOWN")
    source_class = str(record.get("source_class") or record.get("authority_class") or "")
    if created_by == "RAG_RETRIEVAL" and source_class in {"PRIMARY", "CURATED"}:
        return "Authoritative Policy"
    return SOURCE_LABELS.get(created_by, "Supporting Policy")


def status_class(text: str) -> str:
    upper = text.upper()
    for name in ("CONSTRAINED", "CONDITIONAL", "UNKNOWN", "CLEAR"):
        if upper.startswith(name):
            return name.lower()
    return "unknown"


def status_label(workflow_status: str) -> tuple[str, str]:
    return {
        "COMPLETE": ("Analysis complete", "complete"),
        "REQUIRES_HUMAN_REVIEW": ("Human review required", "review"),
        "FAILED": ("Assessment could not be completed", "failure"),
        "PARTIAL": ("Assessment partially completed", "failure"),
    }.get(workflow_status, ("Assessment status unavailable", "review"))


def render_decision_summary(payload: dict[str, Any]) -> None:
    """Render the compact result summary before the detailed assessment sections."""

    summary = summarize_interlock_result(payload)
    workflow_status = str(summary.get("workflow_status") or "UNKNOWN")
    status_text, _ = status_label(workflow_status)
    domains = assessment_domain_state_summary(payload)
    state_labels = {
        "CLEAR": "No explicit constraint",
        "CONDITIONAL": "Conditional",
        "CONSTRAINED": "Constraint recorded",
        "UNKNOWN": "Information required",
        "INFORMATIONAL": "Informational",
    }
    colours = {
        "CLEAR": "#16877d",
        "CONDITIONAL": "#c89235",
        "CONSTRAINED": "#a63d4a",
        "UNKNOWN": "#4b7890",
        "INFORMATIONAL": "#00a89d",
    }
    radius = 78
    circumference = 2 * 3.14159265359 * radius
    segment = circumference / max(len(domains), 1)
    ring_segments = "".join(
        f'<circle class="interlock-radial-segment" cx="100" cy="100" r="{radius}" '
        f'stroke="{colours.get(str(item.get("state")), "#4b7890")}" '
        f'stroke-dasharray="{segment - 3:.2f} {circumference - segment + 3:.2f}" '
        f'stroke-dashoffset="{-index * segment:.2f}" aria-label="{html.escape(str(item.get("label")))}: '
        f'{html.escape(state_labels.get(str(item.get("state")), "Information required"))}" />'
        for index, item in enumerate(domains)
    )
    legend = "".join(
        f'<li><span class="interlock-legend-dot" style="background:{colours.get(str(item.get("state")), "#4b7890")}"></span>'
        f'<span><strong>{html.escape(str(item.get("label")))}</strong>'
        f'<small>{html.escape(state_labels.get(str(item.get("state")), "Information required"))}</small></span></li>'
        for item in domains
    )
    if not domains:
        ring_segments = ""
        legend = '<li class="interlock-domain-empty">No stage-relevant domain findings were returned.</li>'
    st.markdown("#### Decision summary")
    st.markdown(
        f'<div class="interlock-domain-radial">'
        f'<div class="interlock-radial-wrap"><svg viewBox="0 0 200 200" role="img" aria-label="Stage domain evidence states">'
        f'<circle cx="100" cy="100" r="{radius}" fill="none" stroke="#d9e7e8" stroke-width="16" />'
        f'{ring_segments}</svg><div class="interlock-radial-centre"><span>WORKFLOW</span><strong>{html.escape(status_text.upper())}</strong><small>No unsupported outcome inferred</small></div></div>'
        f'<ul class="interlock-radial-legend">{legend}</ul></div>',
        unsafe_allow_html=True,
    )
    if domains:
        stage_view = as_dict(payload.get("stage_assessment_view"))
        st.caption(
            f"Stage-relevant domains shown: {len(domains)} · evidence used {stage_view.get('relevant_evidence_count', summary.get('evidence_record_count', 0))}"
            f" of {stage_view.get('total_evidence_count', summary.get('evidence_record_count', 0))} stored records."
        )
        st.caption("Domain states: " + " · ".join(
            f"{item.get('label', 'Domain')} — {state_labels.get(str(item.get('state')), 'Information required')}"
            for item in domains
        ))
    st.caption(
        "UNKNOWN means INTERLOCK does not have sufficient verified evidence to reach a reliable conclusion. "
        "Combined groups show the most cautionary state actually returned for their source domains."
    )
    metrics = (
        ("Key findings", summary.get("finding_count", 0)),
        ("Constraints", summary.get("conditional_or_constrained_finding_count", 0)),
        ("Information required", as_dict(payload.get("stage_assessment_view")).get("counts", {}).get("information_required_count", summary.get("unknown_theme_count", 0))),
        ("Professional reviews", summary.get("human_review_count", 0)),
        ("Evidence records", summary.get("evidence_record_count", 0)),
    )
    columns = st.columns(5)
    for column, (title, value) in zip(columns, metrics):
        with column:
            st.metric(title, value)


def render_finding_briefs(payload: dict[str, Any]) -> None:
    """Render structured finding context without adding conclusions."""

    assessment = as_dict(payload.get("assessment_result"))
    explanation = as_dict(payload.get("explanation_result"))
    findings = [as_dict(item) for item in as_list(assessment.get("findings"))]
    key_findings = as_list(explanation.get("key_findings"))
    reviews = [as_dict(item) for item in as_list(payload.get("human_reviews"))]
    actions = [as_dict(item) for item in as_list(explanation.get("next_action_plan"))]
    if not findings:
        return
    narrative_by_id: dict[str, str] = {}
    for value in key_findings:
        text = str(value)
        marker = "[finding:"
        if marker in text:
            finding_id = text.split(marker, 1)[1].split("]", 1)[0].strip()
            narrative_by_id[finding_id] = text.split(" [finding:", 1)[0]
    st.markdown("#### Findings at a glance")
    for finding in findings:
        finding_id = str(finding.get("finding_id") or "Finding")
        domain = label(finding.get("domain"), DOMAIN_LABELS)
        status = str(finding.get("status") or "UNKNOWN")
        evidence_ids = [str(item) for item in as_list(finding.get("evidence_ids"))]
        finding_reviews = [
            review for review in reviews
            if str(review.get("domain") or "") == str(finding.get("domain") or "")
            or bool(set(evidence_ids).intersection(as_list(review.get("evidence_ids"))))
        ]
        finding_actions = [
            action for action in actions
            if finding_id in {str(item) for item in as_list(action.get("finding_ids"))}
        ]
        with st.container(border=True):
            st.markdown(f"**{domain}** · <span class=\"interlock-pill {status_class(status)}\">{html.escape(status.replace('_', ' '))}</span>", unsafe_allow_html=True)
            if narrative_by_id.get(finding_id):
                st.write(narrative_by_id[finding_id])
            if finding.get("decision_impact"):
                st.caption(f"Why it matters: {finding['decision_impact']}")
            if finding.get("constraint"):
                st.caption(f"Constraint recorded: {finding['constraint']}")
            unknowns = as_list(finding.get("material_unknowns"))
            if unknowns:
                st.caption("What remains unknown: " + "; ".join(str(item) for item in unknowns))
            if evidence_ids:
                st.caption("Supporting evidence: " + ", ".join(evidence_ids))
            if finding_actions:
                st.caption("Next action: " + "; ".join(str(item.get("title") or "Not established") for item in finding_actions))
            if finding_reviews:
                roles = [label(item.get("recommended_role"), ROLE_LABELS) for item in finding_reviews]
                st.caption("Professional review required: " + ", ".join(dict.fromkeys(roles)))


def render_report_download(payload: dict[str, Any]) -> None:
    """Offer a PDF rendering of the stored result without calling the backend."""

    workflow_status = str(payload.get("workflow_status") or "UNKNOWN")
    if workflow_status not in {"COMPLETE", "REQUIRES_HUMAN_REVIEW"}:
        return
    try:
        pdf_bytes = render_assessment_report_pdf(payload)
        st.download_button(
            "Download Assessment Report",
            data=pdf_bytes,
            file_name=safe_report_filename(payload),
            mime="application/pdf",
            key="download_assessment_report",
            icon=":material/download:",
        )
        st.caption("Generated from the stored InterlockResult. Running a new assessment is not required.")
    except Exception:
        st.error("The assessment report could not be generated from this result.")


def asset_data_uri(path: Path, mime_type: str) -> str | None:
    """Return a data URI for a local, project-owned image asset."""

    if not path.is_file():
        return None
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def image_markup(path: Path, *, alt: str, class_name: str) -> str:
    """Render a local image asset without making remote network requests."""

    data_uri = asset_data_uri(path, "image/png")
    if not data_uri:
        return ""
    return f'<img class="{class_name}" src="{data_uri}" alt="{alt}" />'


def hero_asset_style() -> str:
    """Return a local data URI style only when the approved asset is present."""

    data_uri = asset_data_uri(HERO_ASSET_PATH, "image/png")
    if not data_uri:
        return ""
    return f' style="--interlock-hero-image: url(\'{data_uri}\')"'


def hero_background_css() -> str:
    """Return a direct image rule so the approved PNG cannot fall back silently."""

    data_uri = asset_data_uri(HERO_ASSET_PATH, "image/png")
    if not data_uri:
        return ""
    return (
        "<style>"
        f".st-key-hero_shell {{ background-image: {HERO_GRADIENT}, url(\"{data_uri}\") !important; }}"
        "</style>"
    )


def render_brand_header() -> None:
    """Render the Canavan Atlantic identity and user-facing header chrome."""

    logo = image_markup(LOGO_ASSET_PATH, alt="CANAVAN ATLANTIC", class_name="interlock-ca-logo")
    if not logo:
        logo = '<span class="interlock-ca-fallback">CANAVAN <small>ATLANTIC</small></span>'
    st.markdown(
        f"""
        <header class="interlock-site-header" aria-label="Canavan Atlantic header">
          <div class="interlock-ca-brand" aria-label="Canavan Atlantic">
            {logo}
          </div>
          <div class="interlock-profile" aria-label="Welcome, User">
            <span class="interlock-profile-icon" aria-hidden="true"></span>
            <span>Welcome, User</span><span class="interlock-chevron">⌄</span>
          </div>
        </header>
        """,
        unsafe_allow_html=True,
    )


def render_home() -> tuple[bool, bool]:
    """Render the public-facing landing page and return CTA selections."""

    st.markdown(hero_background_css(), unsafe_allow_html=True)
    with st.container(key="hero_shell"):
        st.markdown(
            f"""
        <div class="interlock-hero-content" aria-label="INTERLOCK introduction" data-interlock-hero-image="{'local' if HERO_ASSET_PATH.is_file() else 'fallback'}">
          <p class="interlock-hero-kicker">INTERLOCK</p>
          <p class="interlock-eyebrow">DATA CENTRE DEVELOPMENT INTELLIGENCE</p>
          <h1>Better sites.<br><em>Stronger decisions.</em></h1>
          <p class="interlock-hero-copy">Bring environmental, planning and infrastructure evidence together to assess data centre sites with confidence.</p>
        </div>
        """,
            unsafe_allow_html=True,
        )
        with st.container(
            horizontal=True,
            horizontal_alignment="left",
            wrap=True,
            key="hero_actions",
        ):
            start = st.button(
                "Start a new site assessment",
                type="primary",
                icon=":material/arrow_forward:",
                key="home_start_assessment",
            )
            explore = st.button(
                "Explore data layers",
                icon=":material/arrow_forward:",
                key="home_explore_methodology",
            )

    capabilities = [
        (
            "Environmental Intelligence",
            "Assess planning, biodiversity, water and flood risk.",
            "leaf",
        ),
        (
            "Integrated Data",
            "Combine public data, policy, project documents and GIS.",
            "layers",
        ),
        (
            "Actionable Insights",
            "Identify constraints, risks and opportunities.",
            "chart",
        ),
        (
            "Sustainable Growth",
            "Support resilient and responsible development.",
            "shield",
        ),
    ]
    with st.container(key="capability_strip"):
        columns = st.columns(4)
        for column, (title, copy, icon) in zip(columns, capabilities):
            with column:
                st.markdown(
                    f'<div class="interlock-capability"><div class="interlock-line-icon">{LINE_ICONS[icon]}</div>'
                    f'<div class="interlock-capability-title">{title}</div>'
                    f'<div class="interlock-capability-copy">{copy}</div></div>',
                    unsafe_allow_html=True,
                )

    truths = [
        ("MULTI-SOURCE", "Evidence integration"),
        ("TRACEABLE", "Evidence chain"),
        ("CONTROLLED", "Agent workflow"),
        ("HUMAN REVIEW", "Built in"),
    ]
    with st.container(key="truth_band"):
        columns = st.columns(4)
        for column, (title, copy) in zip(columns, truths):
            with column:
                st.markdown(
                    f'<div class="interlock-truth-item"><strong>{title}</strong><span>{copy}</span></div>',
                    unsafe_allow_html=True,
                )

    stages = [
        ("01", "Gather", "Integrate public, policy and project data.", "folder"),
        ("02", "Analyse", "Evidence analysis across key domains.", "search"),
        ("03", "Assess", "Identify constraints, risks and opportunities.", "document"),
        ("04", "Enable", "Support accountable, resilient development.", "leaf"),
    ]
    with st.container(key="approach_section"):
        approach_copy, approach_steps = st.columns([0.95, 2.05], gap="large")
        with approach_copy:
            st.markdown('<p class="interlock-section-kicker">Our approach</p>', unsafe_allow_html=True)
            st.markdown(
                '<h2 class="interlock-section-title">From data to decisions.<br>Built for a better tomorrow.</h2>',
                unsafe_allow_html=True,
            )
        with approach_steps:
            columns = st.columns(4)
            for column, (number, title, copy, icon) in zip(columns, stages):
                with column:
                    st.markdown(
                        f'<div class="interlock-approach-step"><div class="interlock-step-icon">{LINE_ICONS[icon]}</div>'
                        f'<div class="interlock-step-number">{number}</div>'
                        f'<div class="interlock-stage-title">{title}</div>'
                        f'<div class="interlock-stage-copy">{copy}</div></div>',
                        unsafe_allow_html=True,
                    )

    footer_logo = image_markup(
        WHITE_LOGO_ASSET_PATH,
        alt="CANAVAN ATLANTIC",
        class_name="interlock-footer-logo",
    ) or '<span class="interlock-ca-fallback">CANAVAN <small>ATLANTIC</small></span>'
    st.markdown(
        f'<footer class="interlock-footer"><div class="interlock-footer-brand">{footer_logo}</div>'
        '<div class="interlock-footer-motto">People. Places. Possibilities.</div>'
        '<div class="interlock-footer-copyright">© 2026 Canavan Atlantic. All rights reserved.</div></footer>',
        unsafe_allow_html=True,
    )
    return start, explore


def render_assessment_intro() -> None:
    st.markdown('<p class="interlock-section-kicker">New assessment</p>', unsafe_allow_html=True)
    st.markdown('<h1 class="interlock-section-title">Start with what you know.</h1>', unsafe_allow_html=True)
    st.markdown(
        '<p class="interlock-section-copy">You can begin with incomplete information. INTERLOCK preserves missing information as unknown rather than guessing.</p>',
        unsafe_allow_html=True,
    )


def render_decision_pack(payload: dict[str, Any]) -> None:
    """Render the concise customer-facing layer of the stored InterlockResult."""

    context = as_dict(payload.get("project_context"))
    location = as_dict(context.get("location"))
    explanation = as_dict(payload.get("explanation_result"))
    workflow_status = str(payload.get("workflow_status") or "UNKNOWN")
    status_text, status_style = status_label(workflow_status)
    project_name = context.get("project_name") or context.get("project_id") or "Unnamed project"
    place = location.get("address") or location.get("local_authority") or location.get("country") or "Location not provided"
    stage = as_dict(payload.get("stage_intelligence"))

    st.markdown('<p class="interlock-section-kicker">Project / assessment result</p>', unsafe_allow_html=True)
    st.markdown('<h1 class="interlock-section-title interlock-pack-title">INTERLOCK Development Readiness Decision Pack</h1>', unsafe_allow_html=True)
    status_message = (
        "Automated analysis completed. Professional review is required for identified high-consequence items."
        if workflow_status == "REQUIRES_HUMAN_REVIEW"
        else "INTERLOCK could not complete the assessment. Review the safe stage status below and try again."
        if workflow_status in {"FAILED", "PARTIAL"}
        else "The current structured evidence and assessment are shown below."
    )
    st.markdown(f'<div class="interlock-status-card {status_style}"><div class="interlock-status-label">{status_text}</div><div>{status_message}</div></div>', unsafe_allow_html=True)
    with st.container(border=True):
        project_columns = st.columns(3)
        project_columns[0].markdown(f"**Project**  \n{project_name}")
        project_columns[1].markdown(f"**Location**  \n{place}")
        project_columns[2].markdown(f"**Stage**  \n{stage.get('stage') or context.get('project_stage') or 'Not provided'}")
        if payload.get("generated_at"):
            st.caption(f"Assessment timestamp: {payload['generated_at']} · Run {payload.get('run_id') or 'Not provided'}")
    if stage:
        with st.container(border=True):
            st.markdown(f"**{stage.get('customer_question') or 'Assessment question not provided'}**")
            st.caption(stage.get("purpose") or "Stage purpose not provided.")
    stage_errors = as_dict(payload.get("stage_errors"))
    if stage_errors:
        failed_stage = payload.get("failure_stage") or next(iter(stage_errors), "workflow")
        st.error(f"INTERLOCK could not complete the {label(failed_stage)} stage. No unsupported project decision was created.")

    render_map_first_view(payload)
    render_decision_summary(payload)
    _render_primary_findings(payload)
    _render_required_to_progress(payload)
    _render_primary_actions(payload)
    if payload.get("requires_human_review"):
        st.info("Human review required is a workflow state, not an application failure or a final project decision.")
    planning = as_dict(payload.get("investigation_plan"))
    # New results expose a shared stage view; planner telemetry belongs in the
    # technical detail panel.  Keep the legacy fallback visible for old stored
    # payloads that predate that contract.
    if planning and not payload.get("stage_assessment_view"):
        planning_mode = str(planning.get("planning_mode") or "UNKNOWN")
        planning_label = "Bounded intelligent orchestration" if planning_mode == "BOUNDED_LLM" and planning.get("llm_used") else "Deterministic evidence-planning fallback"
        st.caption(f"{planning_label} · {len(as_list(planning.get('selected_domains')))} domains · {len(as_list(planning.get('tool_requests')))} approved evidence requests")
    render_report_download(payload)

    if st.checkbox("Show evidence, provenance and technical detail", key="decision_pack_detail"):
        evidence = as_dict(payload.get("evidence_bundle"))
        assessment = as_dict(payload.get("assessment_result"))
        planning = as_dict(payload.get("investigation_plan"))
        if planning and os.getenv("INTERLOCK_DEBUG_UI", "").strip().casefold() in {"1", "true", "yes", "on"}:
            planning_mode = str(planning.get("planning_mode") or "UNKNOWN")
            st.markdown("#### Investigation provenance")
            st.write({
                "planning_mode": planning_mode,
                "model": planning.get("model") or "Not used",
                "selected_domains": as_list(planning.get("selected_domains")),
                "approved_evidence_requests": len(as_list(planning.get("tool_requests"))),
                "approved_tool_types": sorted({str(as_dict(value).get("tool")) for value in as_list(planning.get("tool_requests")) if as_dict(value).get("tool")}),
                "rejected_request_count": len(as_list(planning.get("rejected_requests"))),
            })
        render_human_reviews(as_list(payload.get("human_reviews")))
        render_sources(explanation, evidence)
        if os.getenv("INTERLOCK_DEBUG_UI", "").strip().casefold() in {"1", "true", "yes", "on"}:
            render_technical_details(payload, evidence, assessment)


def _render_primary_findings(payload: dict[str, Any], limit: int = 5) -> None:
    stage_view = as_dict(payload.get("stage_assessment_view"))
    if stage_view:
        findings = [as_dict(item) for item in as_list(stage_view.get("relevant_findings"))]
        st.markdown("#### Key findings")
        if not findings:
            st.caption("No stage-relevant findings were returned.")
            return
        for finding in findings[:limit]:
            status = str(finding.get("status") or "UNKNOWN")
            status_text = {
                "UNKNOWN": "Information required",
                "CONDITIONAL": "Conditional",
                "CONSTRAINED": "Constraint recorded",
                "CLEAR": "No explicit constraint",
                "INFORMATIONAL": "Informational",
            }.get(status, "Information required")
            with st.container(border=True):
                st.markdown(
                    f"**{finding.get('domain_label') or label(finding.get('domain'), DOMAIN_LABELS)}** · "
                    f"<span class=\"interlock-pill {status_class(status)}\">{html.escape(status_text)}</span>",
                    unsafe_allow_html=True,
                )
                st.write(finding.get("headline") or "Stage-relevant finding returned.")
                st.caption(f"Why it matters: {finding.get('why_it_matters') or 'Review the linked evidence.'}")
                if finding.get("evidence_ids"):
                    with st.expander("View evidence", expanded=False):
                        st.caption("Evidence IDs: " + ", ".join(str(item) for item in as_list(finding.get("evidence_ids"))))
        if len(findings) > limit:
            st.caption(f"Showing {limit} of {len(findings)} findings. View all in the evidence drill-down.")
        return
    assessment = as_dict(payload.get("assessment_result"))
    explanation = as_dict(payload.get("explanation_result"))
    findings = [as_dict(item) for item in as_list(assessment.get("findings"))]
    narratives: dict[str, str] = {}
    for value in as_list(explanation.get("key_findings")):
        text = str(value)
        if "[finding:" in text:
            narratives[text.split("[finding:", 1)[1].split("]", 1)[0].strip()] = text.split(" [finding:", 1)[0]
    st.markdown("#### Key findings")
    if not findings:
        st.caption("No structured findings were returned.")
        return
    for finding in findings[:limit]:
        finding_id = str(finding.get("finding_id") or "")
        headline = narratives.get(finding_id) or finding.get("decision_impact") or finding.get("constraint") or "Structured finding returned; review the linked evidence."
        headline = str(headline).split(" [finding:", 1)[0]
        if len(headline) > 240:
            headline = headline[:237].rstrip() + "…"
        with st.container(border=True):
            st.markdown(f"**{label(finding.get('domain'))}** · <span class=\"interlock-pill {status_class(finding.get('status', 'UNKNOWN'))}\">{str(finding.get('status') or 'UNKNOWN').replace('_', ' ')}</span>", unsafe_allow_html=True)
            st.write(headline)
            if finding.get("evidence_ids"):
                with st.expander("View evidence", expanded=False):
                    st.caption("Evidence IDs: " + ", ".join(str(item) for item in as_list(finding.get("evidence_ids"))))
    if len(findings) > limit:
        st.caption(f"Showing {limit} of {len(findings)} findings. Full traceability is available in the evidence drill-down and report appendix.")


def _render_required_to_progress(payload: dict[str, Any], limit: int = 5) -> None:
    stage_view = as_dict(payload.get("stage_assessment_view"))
    if stage_view:
        requirements = [as_dict(item) for item in as_list(stage_view.get("information_required"))]
        heading = stage_view.get("requirement_heading") or "Required to Progress"
        st.markdown(f"#### {heading}")
        if stage_view.get("not_required_at_stage"):
            st.caption("Not required at this stage: " + "; ".join(str(item) for item in as_list(stage_view.get("not_required_at_stage"))))
        if stage_view.get("provided_inputs"):
            st.caption("Inputs provided (not delivery confirmation): " + "; ".join(str(item) for item in as_list(stage_view.get("provided_inputs"))))
        if not requirements:
            st.success("No additional stage-specific information is currently recorded as required.")
            return
        for item in requirements[:limit]:
            with st.container(border=True):
                st.markdown(f"**{item.get('label') or 'Additional information'}**")
                st.write(item.get("why_required") or "The current evidence does not resolve this item.")
                st.caption(
                    f"Next: {item.get('next_step') or 'Confirm the related evidence.'}"
                    + (f" · Owner: {item['owner']}" if item.get("owner") else "")
                )
        if len(requirements) > limit:
            with st.expander(f"View all requirements ({len(requirements)})", expanded=False):
                for item in requirements[limit:]:
                    st.markdown(f"**{item.get('label') or 'Additional information'}** — {item.get('why_required') or 'Review the related evidence.'}")
                    st.caption(f"Next: {item.get('next_step') or 'Confirm the related evidence.'}")
        return
    stage = as_dict(payload.get("stage_intelligence"))
    requirements = [as_dict(item) for item in as_list(stage.get("required_to_progress")) if as_dict(item).get("status") == "REQUIRED_TO_PROGRESS"]
    explanation = as_dict(payload.get("explanation_result"))
    if not requirements:
        for theme in as_list(explanation.get("material_unknown_themes")):
            item = as_dict(theme)
            actions = as_list(item.get("resolution_actions"))
            requirements.append({
                "label": item.get("title") or "Additional information",
                "why_required": item.get("summary") or "The current evidence does not resolve this theme.",
                "next_step": actions[0] if actions else "Confirm the related evidence.",
                "owner": None,
            })
    st.markdown(f"#### {stage.get('missing_evidence_wording') or 'Required to Progress'}")
    if not requirements:
        st.success("No additional stage-specific information is currently recorded as required.")
        return
    for item in requirements[:limit]:
        with st.container(border=True):
            st.markdown(f"**{item.get('label') or 'Additional information'}**")
            st.write(item.get("why_required") or "The current evidence does not resolve this item.")
            st.caption(f"Next: {item.get('next_step') or 'Confirm the related evidence.'}" + (f" · Owner: {item['owner']}" if item.get("owner") else ""))
    if len(requirements) > limit:
        st.caption(f"Showing {limit} of {len(requirements)} required items. Full closure detail is available in the report appendix.")


def _render_primary_actions(payload: dict[str, Any], limit: int = 5) -> None:
    stage_view = as_dict(payload.get("stage_assessment_view"))
    if stage_view:
        actions = [as_dict(item) for item in as_list(stage_view.get("next_actions"))]
        st.markdown("#### Next actions")
        if not actions:
            st.caption("No consolidated next actions were returned.")
            return
        for action in actions[:limit]:
            with st.container(border=True):
                st.markdown(f"**{action.get('title') or 'Next action'}**")
                domain = action.get("domain_label") or action.get("domain") or "Project evidence"
                st.caption(f"{domain} · Owner: {action.get('owner') or 'Project team'} · {action.get('reason') or 'Resolve the related evidence gap.'}")
                with st.expander("Why this action?", expanded=False):
                    st.write(action.get("why_this_action") or action.get("reason") or "Resolve the related evidence gap.")
        if len(actions) > limit:
            st.caption(f"Showing {limit} of {len(actions)} actions. Related evidence remains available in the drill-down.")
        return
    explanation = as_dict(payload.get("explanation_result"))
    actions = [as_dict(item) for item in as_list(explanation.get("next_action_plan"))]
    st.markdown("#### Next actions")
    if not actions:
        st.caption("No consolidated next actions were returned.")
        return
    for action in actions[:limit]:
        with st.container(border=True):
            st.markdown(f"**{action.get('title') or 'Next action'}**")
            roles = ", ".join(label(item, ROLE_LABELS) for item in as_list(action.get("specialist_roles")))
            st.caption((f"Owner: {roles} · " if roles else "") + str(action.get("rationale") or "Resolve the related evidence gap."))
    if len(actions) > limit:
        st.caption(f"Showing {limit} of {len(actions)} actions. Related evidence remains available in the drill-down.")


def render_demo_run_summary(summary: dict[str, Any] | None) -> None:
    """Render the actual result summary for a successfully run demo preset."""

    if not summary:
        return
    st.markdown("#### Demo run summary")
    st.caption("Derived from the completed InterlockResult returned for this demo run.")
    metric_items = (
        ("Evidence records", summary.get("evidence_record_count", 0)),
        ("Findings", summary.get("finding_count", 0)),
        ("Unknown themes", summary.get("unknown_theme_count", 0)),
        ("Human reviews", summary.get("human_review_count", 0)),
    )
    columns = st.columns(4)
    for column, (title, value) in zip(columns, metric_items):
        with column:
            st.metric(title, value)
    st.write(
        {
            "workflow_status": summary.get("workflow_status"),
            "conditional_or_constrained_findings": summary.get("conditional_or_constrained_finding_count", 0),
            "material_unknowns": summary.get("material_unknown_count", 0),
            "dependencies": summary.get("dependency_count", 0),
            "contradictions": summary.get("contradiction_count", 0),
            "customer_facing_citations": summary.get("customer_facing_citation_count", 0),
            "source_counts": {
                source_label({"created_by": source}): count
                for source, count in as_dict(summary.get("source_counts")).items()
            },
            "stage_counts": summary.get("stage_counts", {}),
            "timings_ms": summary.get("timings_ms", {}),
        }
    )


def render_human_reviews(reviews: list[Any]) -> None:
    st.markdown("#### Human review")
    if not reviews:
        st.caption("No unresolved specialist reviews are recorded.")
        return
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for value in reviews:
        item = as_dict(value)
        groups[(str(item.get("recommended_role") or "UNKNOWN"), str(item.get("domain") or "UNKNOWN"))].append(item)
    st.info("Professional review is a core part of the workflow. These requests do not represent approval or a final project decision.")
    for (role, domain), items in groups.items():
        with st.container(border=True):
            st.markdown(f"**{label(role, ROLE_LABELS)}** · {label(domain, DOMAIN_LABELS)}")
            for item in items:
                severity = label(item.get("severity"))
                st.markdown(f"**{severity}** — {item.get('reason') or 'Review the related evidence.'}")
                refs = as_list(item.get("evidence_ids"))
                if refs:
                    st.caption("Related evidence: " + ", ".join(str(ref) for ref in refs))
                st.caption(f"Review ID: {item.get('review_id') or 'Not provided'}")


def render_action_plan(actions: list[Any]) -> None:
    st.markdown("#### Next action plan")
    if not actions:
        st.caption("No consolidated next actions were returned.")
        return
    for index, value in enumerate(actions, start=1):
        item = as_dict(value)
        with st.container(border=True):
            st.markdown(f'<div class="interlock-number">{index:02d}</div>', unsafe_allow_html=True)
            st.markdown(f"**{item.get('title') or 'Next action'}**")
            st.write(item.get("rationale") or "Resolve the related evidence gap before relying on this point.")
            roles = as_list(item.get("specialist_roles"))
            if roles:
                st.caption("Specialist roles: " + ", ".join(label(role, ROLE_LABELS) for role in roles))
            refs = [*as_list(item.get("finding_ids")), *as_list(item.get("dependency_ids")), *as_list(item.get("evidence_ids"))]
            if refs or item.get("citations"):
                with st.expander("View action traceability"):
                    if refs:
                        st.write({"references": refs})
                    if item.get("citations"):
                        st.write({"citations": item["citations"]})


def render_sources(explanation: dict[str, Any], evidence: dict[str, Any]) -> None:
    st.markdown("#### Evidence & sources")
    records = [as_dict(record) for record in as_list(evidence.get("records"))]
    citations = as_list(explanation.get("customer_facing_citations"))
    record_by_document = {}
    for record in records:
        document_id = record.get("source_document_id")
        if document_id:
            record_by_document[str(document_id)] = record
    if citations:
        for citation in citations:
            item = as_dict(citation)
            document_id = str(item.get("document_id") or "")
            record = record_by_document.get(document_id, {})
            with st.container(border=True):
                st.markdown(f"**{source_label(record)}** · {document_id or 'Source reference'}")
                st.caption(item.get("locator") or item.get("source_path") or "Structured citation returned by the backend.")
    else:
        st.caption("No customer-facing citations were returned.")
    with st.expander("View supporting evidence"):
        rows = [
            {
                "Source type": source_label(record),
                "Domain": label(record.get("domain"), DOMAIN_LABELS),
                "State": label(record.get("evidence_state")),
                "Source": record.get("source_name") or record.get("source_document_id") or "Not provided",
                "Evidence ID": record.get("evidence_id") or "Not provided",
            }
            for record in records
        ]
        if rows:
            st.dataframe(rows, hide_index=True)
        else:
            st.caption("No evidence records were returned.")


def render_technical_details(payload: dict[str, Any], evidence: dict[str, Any], assessment: dict[str, Any]) -> None:
    with st.expander("Technical details"):
        st.write(
            {
                "run_id": payload.get("run_id"),
                "workflow_status": payload.get("workflow_status"),
                "stage_status": payload.get("stage_status", {}),
                "stage_timings_ms": payload.get("timings_ms", {}),
                "stage_counts": payload.get("stage_counts", {}),
                "failure_stage": payload.get("failure_stage"),
                "stage_errors": payload.get("stage_errors", {}),
            }
        )
        evidence_ids = [item.get("evidence_id") for item in as_list(evidence.get("records")) if isinstance(item, dict)]
        finding_ids = [item.get("finding_id") for item in as_list(assessment.get("findings")) if isinstance(item, dict)]
        st.write({"evidence_ids": evidence_ids, "finding_ids": finding_ids})


def render_evidence_view(payload: dict[str, Any] | None) -> None:
    st.markdown('<p class="interlock-section-kicker">Evidence</p>', unsafe_allow_html=True)
    st.markdown('<h1 class="interlock-section-title">Evidence chain</h1>', unsafe_allow_html=True)
    st.markdown(
        '<p class="interlock-section-copy">Inspect how developer inputs, public/GIS evidence, project documents and policy sources are kept distinct before they reach the assessment.</p>',
        unsafe_allow_html=True,
    )
    if not payload:
        st.info("Run a new assessment to populate the evidence chain.")
        return
    evidence = as_dict(payload.get("evidence_bundle"))
    records = [as_dict(item) for item in as_list(evidence.get("records"))]
    counts: dict[str, int] = defaultdict(int)
    for record in records:
        counts[source_label(record)] += 1
    st.caption("Source classes remain distinct so the evidence chain can be reviewed before assessment.")
    count_columns = st.columns(5)
    source_classes = (
        "Developer Provided",
        "Public / GIS Evidence",
        "Authoritative Policy",
        "Project Evidence",
        "Supporting Policy",
    )
    for column, source_class in zip(count_columns, source_classes):
        with column:
            st.markdown(
                f'<div class="interlock-evidence-count"><strong>{counts.get(source_class, 0)}</strong>'
                f'<span>{source_class}</span></div>',
                unsafe_allow_html=True,
            )
    stage_view = as_dict(payload.get("stage_assessment_view"))
    if stage_view:
        counts_view = as_dict(stage_view.get("counts"))
        st.caption(
            f"Stage-relevant evidence: {counts_view.get('relevant_evidence_count', stage_view.get('relevant_evidence_count', 0))}"
            f" of {counts_view.get('total_evidence_count', stage_view.get('total_evidence_count', len(records)))} stored records"
            f" · Current run: {payload.get('run_id') or 'Not provided'}"
        )
    else:
        st.caption(f"Current run: {payload.get('run_id') or 'Not provided'} · {len(records)} evidence records")
    render_map_first_view(payload, key_prefix="layers")
    domains = ["All"] + sorted({label(item.get("domain"), DOMAIN_LABELS) for item in records})
    sources = ["All"] + sorted({source_label(item) for item in records})
    filter_columns = st.columns(3)
    selected_domain = filter_columns[0].selectbox("Domain", domains, key="evidence_domain_filter")
    selected_source = filter_columns[1].selectbox("Source class", sources, key="evidence_source_filter")
    page_size = filter_columns[2].selectbox("Records per page", [5, 10, 20], index=1, key="evidence_page_size")
    search_query = st.text_input("Search evidence", key="evidence_search_query", placeholder="Search domain, finding or source")
    query = search_query.casefold().strip()
    filtered = [
        item for item in records
        if (selected_domain == "All" or label(item.get("domain"), DOMAIN_LABELS) == selected_domain)
        and (selected_source == "All" or source_label(item) == selected_source)
        and (not query or query in " ".join(str(item.get(key) or "") for key in ("evidence_id", "field_name", "finding", "fact", "source_name")).casefold())
    ]
    page_count = max(1, (len(filtered) + page_size - 1) // page_size)
    if st.session_state.get("evidence_page", 1) > page_count:
        st.session_state["evidence_page"] = 1
    page_options = list(range(1, page_count + 1))
    page = st.selectbox("Evidence page", page_options, key="evidence_page")
    start = (int(page) - 1) * page_size
    page_records = filtered[start : start + page_size]
    st.caption(f"Showing {len(page_records)} of {len(filtered)} matching records · page {page} of {page_count}")
    if not page_records:
        st.info("No evidence records match the selected filters.")
    for item in page_records:
        title = f"{label(item.get('domain'), DOMAIN_LABELS)} · {item.get('evidence_id') or 'Evidence record'}"
        with st.expander(title, expanded=False):
            st.markdown(
                f"**State:** {label(item.get('evidence_state'))}  "
                f"\n**Source:** {source_label(item)}"
            )
            st.write(item.get("finding") or item.get("fact") or "Structured evidence record.")
            st.caption(f"Source reference: {item.get('source_document_id') or item.get('source_name') or 'Not provided'}")
            st.caption(f"Maturity: {_evidence_maturity(item)}")
    with st.expander("Citations and provenance", expanded=False):
        render_sources(as_dict(payload.get("explanation_result")), evidence)
    with st.expander("Developer / Debug Inspection", icon=":material/bug_report:"):
        st.caption("Technical inspection is paginated to keep the primary evidence view responsive.")
        st.dataframe(
            [
                {
                    "Evidence ID": item.get("evidence_id"),
                    "Domain": label(item.get("domain"), DOMAIN_LABELS),
                    "Source type": source_label(item),
                    "State": label(item.get("evidence_state")),
                    "Maturity": _evidence_maturity(item),
                }
                for item in page_records
            ],
            hide_index=True,
        )


def _evidence_maturity(record: dict[str, Any]) -> str:
    """Map provenance to a display category without increasing certainty."""

    created_by = str(record.get("created_by") or "UNKNOWN")
    trust = str(record.get("source_trust") or "UNKNOWN")
    state = str(record.get("evidence_state") or "UNKNOWN")
    if created_by == "DEVELOPER_INPUT":
        return "Developer Input"
    if created_by == "DETERMINISTIC_GIS":
        return "Deterministic Derived Evidence"
    if trust == "AUTHORITATIVE_POLICY":
        return "Observed / Authoritative Evidence"
    if state in {"UNKNOWN", "NOT_PROVIDED"} or record.get("human_review_required"):
        return "Confirmation Required"
    return "Assumption / Contextual Evidence"


def _render_maturity(payload: dict[str, Any]) -> None:
    records = [as_dict(item) for item in as_list(as_dict(payload.get("evidence_bundle")).get("records"))]
    counts: dict[str, int] = defaultdict(int)
    for record in records:
        counts[_evidence_maturity(record)] += 1
    st.markdown("#### Evidence maturity")
    st.caption("Maturity describes provenance and closure needs; it does not convert context into a confirmed fact.")
    columns = st.columns(5)
    for column, title in zip(columns, ("Developer Input", "Observed / Authoritative Evidence", "Deterministic Derived Evidence", "Assumption / Contextual Evidence", "Confirmation Required")):
        with column:
            st.metric(title, counts.get(title, 0))


def render_insights(payload: dict[str, Any] | None) -> None:
    st.markdown('<p class="interlock-section-kicker">Insights</p>', unsafe_allow_html=True)
    st.markdown('<h1 class="interlock-section-title">Project intelligence at a glance.</h1>', unsafe_allow_html=True)
    if not payload:
        st.info("Run an assessment to populate project-specific insights.")
        return
    stage = as_dict(payload.get("stage_intelligence"))
    if stage:
        st.markdown(f"**{stage.get('customer_question') or 'Assessment question not provided'}**")
        st.caption(stage.get("purpose") or "Stage purpose not provided.")
    render_decision_summary(payload)
    _render_maturity(payload)
    _render_required_to_progress(payload, limit=5)


def render_about() -> None:
    st.markdown('<p class="interlock-section-kicker">About INTERLOCK</p>', unsafe_allow_html=True)
    st.markdown('<h1 class="interlock-section-title">Evidence before confidence.</h1>', unsafe_allow_html=True)
    st.markdown('<p class="interlock-section-copy">INTERLOCK helps development teams understand what is evidenced, what is constrained, what remains unknown and what should happen next.</p>', unsafe_allow_html=True)
    topics = [
        ("Controlled workflow", "Project inputs are validated, evidence is gathered, deterministic assessment rules run, and the result is explained and persisted."),
        ("AI within guardrails", "Bounded intelligent orchestration may select approved evidence questions. It does not replace deterministic evidence or assessment rules."),
        ("Evidence-first", "Developer inputs, deterministic GIS, policy retrieval and project evidence remain identifiable by provenance."),
        ("Human accountability", "Grid, planning, environmental, legal and developer reviews remain visible where specialist confirmation is required."),
        ("Important limitations", "Unknown means unknown. Nearby infrastructure does not prove capacity. INTERLOCK does not create a readiness score or an Advance, Hold, Reconfigure or Stop decision."),
    ]
    for title, copy in topics:
        with st.container(border=True):
            st.markdown(f"**{title}**")
            st.write(copy)


def render_methodology() -> None:
    st.markdown('<p class="interlock-section-kicker">Methodology</p>', unsafe_allow_html=True)
    st.markdown('<h1 class="interlock-section-title">A controlled path to earlier clarity.</h1>', unsafe_allow_html=True)
    st.markdown(
        '<p class="interlock-section-copy">INTERLOCK separates deterministic evidence, structured assessment, customer-facing explanation and professional review. The result is traceable without pretending that missing evidence is a negative conclusion.</p>',
        unsafe_allow_html=True,
    )
    topics = [
        ("Evidence first", "Developer inputs, deterministic GIS, public sources, authoritative policy and project documents remain identifiable by source and provenance."),
        ("Unknown means unknown", "Blank or unresolved fields are carried forward as uncertainty. They are not silently converted into zeros, approvals or failures."),
        ("Review is accountable", "Grid, planning, environmental, legal and developer reviews remain visible where the evidence needs specialist validation."),
        ("No unsupported decision", "The current workflow reports evidence, findings, constraints, unknowns, dependencies, contradictions and actions. It does not output Advance, Hold, Reconfigure or Stop."),
    ]
    for title, copy in topics:
        with st.container(border=True):
            st.markdown(f"**{title}**")
            st.write(copy)


__all__ = [
    "DOMAIN_LABELS",
    "ROLE_LABELS",
    "as_dict",
    "as_list",
    "display_value",
    "label",
    "render_assessment_intro",
    "render_brand_header",
    "render_decision_pack",
    "render_decision_summary",
    "render_demo_run_summary",
    "render_evidence_view",
    "render_finding_briefs",
    "render_home",
    "render_methodology",
    "render_insights",
    "render_about",
    "render_report_download",
    "render_sources",
    "source_label",
    "status_label",
]
