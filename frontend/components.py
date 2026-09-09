"""Customer-facing Streamlit components for the INTERLOCK journey."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

import streamlit as st


SOURCE_LABELS = {
    "DEVELOPER_INPUT": "Developer provided",
    "DETERMINISTIC_GIS": "Public / GIS evidence",
    "RAG_RETRIEVAL": "Authoritative policy",
    "PROJECT_DOCUMENT": "Project evidence",
    "AI_EXTRACTION": "Extracted project evidence",
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
        return "Authoritative policy"
    return SOURCE_LABELS.get(created_by, "Supporting evidence")


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


def render_topbar(active_page: str) -> str:
    """Render the branded identity; navigation is owned by the caller."""

    st.markdown(
        '<div class="interlock-topbar"><div class="interlock-brand-wordmark">INTERLOCK</div>'
        '<div class="interlock-brand-caption">Canavan Atlantic · Development intelligence</div></div>',
        unsafe_allow_html=True,
    )
    return active_page


def render_home() -> tuple[bool, bool]:
    """Render the public-facing landing page and return CTA selections."""

    st.markdown(
        """
        <section class="interlock-hero" aria-label="INTERLOCK introduction">
          <div class="interlock-hero-content">
            <p class="interlock-eyebrow">Data centre development intelligence</p>
            <h1>Better sites.<br><em>Stronger decisions.</em></h1>
            <p class="interlock-hero-copy">Bring environmental, planning and infrastructure evidence together to assess data centre projects with greater confidence.</p>
            <p class="interlock-hero-note">See the whole project earlier — with evidence, uncertainty and professional review kept visible.</p>
          </div>
        </section>
        """,
        unsafe_allow_html=True,
    )
    st.space("small")
    with st.container(horizontal=True, horizontal_alignment="left"):
        start = st.button(
            "Start a new site assessment",
            type="primary",
            icon=":material/arrow_forward:",
            key="home_start_assessment",
        )
        explore = st.button(
            "Explore how INTERLOCK works",
            icon=":material/lan:",
            key="home_explore_methodology",
        )

    st.markdown('<p class="interlock-section-kicker">What INTERLOCK brings together</p>', unsafe_allow_html=True)
    st.markdown('<h2 class="interlock-section-title">Evidence-led infrastructure decisions.</h2>', unsafe_allow_html=True)
    st.markdown(
        '<p class="interlock-section-copy">A controlled workflow for understanding what the current evidence supports, what could delay a project, and what still needs accountable human attention.</p>',
        unsafe_allow_html=True,
    )
    capabilities = [
        (
            "Environmental intelligence",
            "Planning, biodiversity, flood, water, heritage and ground evidence.",
            ":material/public:",
        ),
        (
            "Integrated evidence",
            "Developer inputs, deterministic GIS, authoritative policy and project documents.",
            ":material/hub:",
        ),
        (
            "Traceable assessment",
            "Constraints, conditions, unknowns, dependencies and contradictions stay connected to source evidence.",
            ":material/account_tree:",
        ),
        (
            "Human-accountable decisions",
            "High-consequence findings remain subject to professional human review.",
            ":material/groups:",
        ),
    ]
    columns = st.columns(4)
    for column, (title, copy, icon) in zip(columns, capabilities):
        with column:
            with st.container(border=True, height="stretch"):
                st.markdown(f"{icon}")
                st.markdown(f'<div class="interlock-capability-title">{title}</div>', unsafe_allow_html=True)
                st.markdown(f'<div class="interlock-capability-copy">{copy}</div>', unsafe_allow_html=True)

    st.markdown('<p class="interlock-section-kicker">How INTERLOCK works</p>', unsafe_allow_html=True)
    st.markdown('<h2 class="interlock-section-title">A clear path from evidence to accountable review.</h2>', unsafe_allow_html=True)
    stages = [
        ("01", "Evidence", "Developer inputs, project documents, public/GIS evidence and authoritative policy."),
        ("02", "Assessment", "Constraints, conditional issues, unknowns, dependencies and contradictions."),
        ("03", "Explanation", "Concise rationale, material unknown themes, next actions and traceable citations."),
        ("04", "Human review", "Specialists validate high-consequence findings before accountable decisions are made."),
    ]
    columns = st.columns(4)
    for column, (number, title, copy) in zip(columns, stages):
        with column:
            with st.container(border=True, height="stretch"):
                st.markdown(f'<div class="interlock-number">{number}</div>', unsafe_allow_html=True)
                st.markdown(f'<div class="interlock-stage-title">{title}</div>', unsafe_allow_html=True)
                st.markdown(f'<div class="interlock-stage-copy">{copy}</div>', unsafe_allow_html=True)

    st.markdown(
        '<footer class="interlock-footer"><div class="interlock-footer-caption">Canavan Atlantic</div><p><strong>INTERLOCK</strong> keeps the evidence chain visible from early site assessment through professional review.</p><p>It does not guarantee planning approval, grid capacity, water capacity, viability or investment success.</p></footer>',
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
    """Render the backend InterlockResult as the customer-facing decision pack."""

    context = as_dict(payload.get("project_context"))
    location = as_dict(context.get("location"))
    explanation = as_dict(payload.get("explanation_result"))
    assessment = as_dict(payload.get("assessment_result"))
    evidence = as_dict(payload.get("evidence_bundle"))
    workflow_status = str(payload.get("workflow_status") or "UNKNOWN")
    status_text, status_style = status_label(workflow_status)
    project_name = context.get("project_name") or context.get("project_id") or "Unnamed project"
    place = location.get("address") or location.get("local_authority") or location.get("country") or "Location not provided"

    st.markdown('<p class="interlock-section-kicker">Project / assessment result</p>', unsafe_allow_html=True)
    st.markdown('<h1 class="interlock-section-title">INTERLOCK Development Readiness Decision Pack</h1>', unsafe_allow_html=True)
    status_message = (
        "Automated analysis completed. Professional review is required for identified high-consequence items."
        if workflow_status == "REQUIRES_HUMAN_REVIEW"
        else "INTERLOCK could not complete the assessment. Review the safe stage status below and try again."
        if workflow_status in {"FAILED", "PARTIAL"}
        else "The current structured evidence and assessment are shown below."
    )
    st.markdown(
        f'<div class="interlock-status-card {status_style}"><div class="interlock-status-label">{status_text}</div><div>{status_message}</div></div>',
        unsafe_allow_html=True,
    )
    stage_errors = as_dict(payload.get("stage_errors"))
    if stage_errors:
        failed_stage = payload.get("failure_stage") or next(iter(stage_errors), "workflow")
        st.error(f"INTERLOCK could not complete the {label(failed_stage)} stage. No unsupported project decision was created.")
    st.space("small")
    with st.container(border=True):
        project_columns = st.columns(3)
        project_columns[0].markdown(f"**Project**  \n{project_name}")
        project_columns[1].markdown(f"**Location**  \n{place}")
        project_columns[2].markdown(f"**Run**  \n{payload.get('run_id') or 'Not provided'}")
        if payload.get("generated_at"):
            st.caption(f"Assessment timestamp: {payload['generated_at']}")

    stage_status = as_dict(payload.get("stage_status"))
    if stage_status:
        st.markdown("#### Workflow trace")
        stage_columns = st.columns(3)
        for column, stage in zip(stage_columns, ("evidence", "assessment", "explanation")):
            with column:
                value = str(stage_status.get(stage, "NOT_STARTED"))
                icon = ":material/check_circle:" if value == "COMPLETE" else ":material/error:"
                st.markdown(f"{icon} **{label(stage)}**  \n{label(value)}")

    st.markdown("#### Executive summary")
    with st.container(border=True):
        st.write(explanation.get("executive_summary") or "No executive explanation was returned by the backend.")
        if payload.get("requires_human_review"):
            st.caption("Human review is a workflow state, not an application failure or a final project decision.")

    st.markdown("#### Key findings")
    findings = as_list(explanation.get("key_findings"))
    if findings:
        for finding in findings:
            text = str(finding)
            css_class = status_class(text)
            with st.container(border=True):
                st.markdown(f'<span class="interlock-pill {css_class}">{css_class}</span>', unsafe_allow_html=True)
                st.write(text.split(" [finding:", 1)[0])
                if " [finding:" in text:
                    with st.expander("View finding traceability"):
                        st.caption(text)
    else:
        st.caption("No structured key findings were returned.")

    constraints = as_list(explanation.get("constraints"))
    if constraints:
        st.markdown("#### Constraints")
        for constraint in constraints:
            with st.container(border=True):
                st.markdown('<span class="interlock-pill constrained">constraint</span>', unsafe_allow_html=True)
                st.write(str(constraint))
    else:
        st.caption("No explicit hard constraints are recorded in the current assessment.")

    st.markdown("#### Material unknowns")
    unknown_themes = as_list(explanation.get("material_unknown_themes"))
    if unknown_themes:
        for theme in unknown_themes:
            item = as_dict(theme)
            with st.container(border=True):
                st.markdown(f"**{item.get('title') or 'Material unknown'}**")
                st.write(item.get("summary") or "The current evidence does not resolve this theme.")
                actions = as_list(item.get("resolution_actions"))
                if actions:
                    st.markdown("**What may resolve it**")
                    for action in actions:
                        st.markdown(f"- {action}")
                refs = [*as_list(item.get("finding_ids")), *as_list(item.get("evidence_ids"))]
                if refs:
                    with st.expander("View supporting references"):
                        st.write(refs)
    else:
        st.caption("No consolidated material unknown themes were returned.")

    st.markdown("#### Dependencies")
    dependencies = as_list(assessment.get("dependencies"))
    if dependencies:
        for dependency in dependencies:
            item = as_dict(dependency)
            with st.container(border=True):
                st.markdown(f"**{item.get('dependency_id') or 'Dependency'}** · {label(item.get('status'))}")
                st.write(item.get("impact_description") or item.get("description") or "Dependency impact not described.")
                if item.get("evidence_ids"):
                    st.caption("Evidence: " + ", ".join(str(ref) for ref in item["evidence_ids"]))
                if item.get("human_review_required"):
                    st.caption("Specialist review is required for this dependency.")
    elif as_list(explanation.get("dependencies")):
        for dependency in explanation["dependencies"]:
            with st.container(border=True):
                st.write(str(dependency))
    else:
        st.caption("No unresolved dependencies are recorded in the current assessment.")

    st.markdown("#### Contradictions")
    contradictions = as_list(explanation.get("contradictions"))
    if contradictions:
        for contradiction in contradictions:
            with st.container(border=True):
                st.markdown('<span class="interlock-pill conditional">review carefully</span>', unsafe_allow_html=True)
                st.write(str(contradiction))
    else:
        st.caption("No material evidence contradictions identified in the current assessment.")

    render_human_reviews(as_list(payload.get("human_reviews")))
    render_action_plan(as_list(explanation.get("next_action_plan")))
    render_sources(explanation, evidence)
    render_technical_details(payload, evidence, assessment)


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
    with st.container(border=True):
        st.write("**Current run:** " + str(payload.get("run_id") or "Not provided"))
        st.write("**Evidence records:** " + str(len(records)))
        if counts:
            st.write(dict(counts))
    render_sources(as_dict(payload.get("explanation_result")), evidence)
    with st.expander("Developer / debug evidence inspection"):
        if records:
            st.dataframe(
                [
                    {
                        "Evidence ID": item.get("evidence_id"),
                        "Domain": label(item.get("domain"), DOMAIN_LABELS),
                        "Source type": source_label(item),
                        "State": label(item.get("evidence_state")),
                        "Finding": item.get("finding") or item.get("fact"),
                    }
                    for item in records
                ],
                hide_index=True,
            )
        else:
            st.caption("No evidence records returned.")


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
    "render_decision_pack",
    "render_evidence_view",
    "render_home",
    "render_methodology",
    "render_sources",
    "source_label",
    "status_label",
]
