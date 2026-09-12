"""Deterministic PDF reporting for a stored INTERLOCK result.

The report is deliberately a presentation layer.  It consumes the JSON-shaped
``InterlockResult`` already held by the frontend and never calls the backend,
re-runs an assessment, or derives a score or project decision.
"""

from __future__ import annotations

import re
import textwrap
from pathlib import Path
from typing import Any

try:  # PyMuPDF renamed its import module while retaining the fitz API.
    import pymupdf as fitz
except ImportError:  # Compatibility with older PyMuPDF installations.
    import fitz

try:
    from .result_summary import assessment_domain_state_summary, summarize_interlock_result
except ImportError:  # Streamlit executes frontend/app.py as a top-level script.
    from result_summary import assessment_domain_state_summary, summarize_interlock_result


REPORT_VERSION = "1.0"
PAGE_WIDTH = 595
PAGE_HEIGHT = 842
MARGIN = 48
BODY_WIDTH = PAGE_WIDTH - (2 * MARGIN)

NAVY = (0.024, 0.216, 0.278)
TEAL = (0.086, 0.478, 0.455)
TURQUOISE = (0.0, 0.659, 0.616)
INK = (0.071, 0.204, 0.278)
MUTED = (0.361, 0.451, 0.502)
LINE = (0.851, 0.894, 0.91)
PALE = (0.949, 0.98, 0.984)
AMBER = (0.651, 0.416, 0.075)
RED = (0.651, 0.239, 0.251)
BLUE = (0.208, 0.384, 0.463)
GREEN = (0.086, 0.384, 0.306)

ASSET_DIR = Path(__file__).with_name("assets")
WHITE_LOGO_PATH = ASSET_DIR / "canavan_atlantic_logo_white.png"


def build_assessment_report_view_model(payload: dict[str, Any]) -> dict[str, Any]:
    """Create a deterministic, bounded report model from actual result fields."""

    context = _as_dict(payload.get("project_context"))
    location = _as_dict(context.get("location"))
    assessment = _as_dict(payload.get("assessment_result"))
    explanation = _as_dict(payload.get("explanation_result"))
    evidence = _as_dict(payload.get("evidence_bundle"))
    records = [_as_dict(item) for item in _as_list(evidence.get("records"))]
    reviews = [_as_dict(item) for item in _as_list(payload.get("human_reviews"))]
    if not reviews:
        reviews = [_as_dict(item) for item in _as_list(assessment.get("human_reviews"))]

    narrative_by_id = _finding_narratives(explanation)
    findings = []
    for finding in [_as_dict(item) for item in _as_list(assessment.get("findings"))]:
        finding_id = _text(finding.get("finding_id"), "Finding")
        findings.append(
            {
                "finding_id": finding_id,
                "domain": _display_enum(finding.get("domain"), "UNKNOWN"),
                "status": _display_enum(finding.get("status"), "UNKNOWN"),
                "narrative": narrative_by_id.get(finding_id),
                "constraint": _optional_text(finding.get("constraint")),
                "decision_impact": _optional_text(finding.get("decision_impact")),
                "material_unknowns": [_text(item) for item in _as_list(finding.get("material_unknowns"))],
                "evidence_ids": [_text(item) for item in _as_list(finding.get("evidence_ids"))],
                "dependency_ids": [_text(item) for item in _as_list(finding.get("dependency_ids"))],
                "human_review_required": bool(finding.get("human_review_required")),
            }
        )

    unknowns = []
    for theme in [_as_dict(item) for item in _as_list(explanation.get("material_unknown_themes"))]:
        unknowns.append(
            {
                "title": _text(theme.get("title"), "Material unknown"),
                "summary": _text(theme.get("summary"), "The current evidence does not resolve this theme."),
                "underlying_unknowns": [_text(item) for item in _as_list(theme.get("underlying_unknowns"))],
                "finding_ids": [_text(item) for item in _as_list(theme.get("finding_ids"))],
                "evidence_ids": [_text(item) for item in _as_list(theme.get("evidence_ids"))],
                "resolution_actions": [_text(item) for item in _as_list(theme.get("resolution_actions"))],
                "citations": [_as_dict(item) for item in _as_list(theme.get("citations"))],
            }
        )
    for unknown in _as_list(assessment.get("material_unknowns")):
        if isinstance(unknown, dict):
            unknowns.append({"title": _text(unknown.get("title"), "Material unknown"), **unknown})
        elif unknown is not None:
            unknowns.append({"title": "Material unknown", "summary": _text(unknown)})

    dependencies = _as_list(assessment.get("dependencies"))
    if dependencies:
        dependency_items = [_as_dict(item) for item in dependencies]
    else:
        dependency_items = [{"description": _text(item)} for item in _as_list(explanation.get("dependencies"))]

    actions = _as_list(explanation.get("next_action_plan"))
    if actions:
        action_items = [_as_dict(item) for item in actions]
    else:
        action_items = [{"title": "Next action", "rationale": _text(item)} for item in _as_list(explanation.get("next_actions"))]

    citations = _as_list(explanation.get("customer_facing_citations"))
    if not citations:
        citations = _as_list(explanation.get("source_citations"))
    citation_items = []
    record_by_document = {str(item.get("source_document_id")): item for item in records if item.get("source_document_id")}
    for citation in citations:
        item = _as_dict(citation)
        document_id = _text(item.get("document_id"), "Source reference")
        source_record = record_by_document.get(document_id, {})
        citation_items.append(
            {
                "document_id": document_id,
                "source_path": _text(item.get("source_path") or source_record.get("source_path"), "Not provided"),
                "locator": _text(item.get("locator"), "Locator not provided"),
                "page_start": item.get("page_start"),
                "page_end": item.get("page_end"),
                "section_heading": _optional_text(item.get("section_heading")),
            }
        )

    summary = summarize_interlock_result(payload)
    warnings = [
        _text(item)
        for item in [*_as_list(evidence.get("warnings")), *_as_list(explanation.get("warnings"))]
        if item is not None
    ]
    return {
        "report_version": REPORT_VERSION,
        "project": {
            "name": _text(context.get("project_name") or context.get("project_id"), "Unnamed project"),
            "project_id": _text(context.get("project_id"), "Not provided"),
            "type": _text(context.get("project_type"), "Not provided"),
            "workflow": _text(context.get("assessment_workflow"), "Not provided"),
            "lifecycle_status": _text(context.get("project_lifecycle_status"), "Not provided"),
            "stage": _text(context.get("project_stage"), "Not provided"),
            "address": _text(location.get("address"), "Not provided"),
            "jurisdiction": _text(location.get("jurisdiction") or location.get("country"), "Not provided"),
            "local_authority": _text(location.get("local_authority"), "Not provided"),
            "planned_power_mw": _display_value(context.get("planned_power_mw")),
            "requested_mic_mva": _display_value(context.get("requested_mic_mva")),
            "power_strategy": _display_value(context.get("power_strategy")),
            "energy_strategy": _display_value(context.get("energy_strategy")),
            "phasing": _display_value(context.get("phasing")),
        },
        "workflow_status": _text(payload.get("workflow_status"), "UNKNOWN"),
        "requires_human_review": bool(payload.get("requires_human_review")),
        "run_id": _text(payload.get("run_id"), "Not provided"),
        "generated_at": _text(payload.get("generated_at"), "Not provided"),
        "executive_summary": _text(
            explanation.get("executive_summary"),
            "No executive explanation was returned by the backend.",
        ),
        "known_facts": [_text(item) for item in _as_list(explanation.get("known_facts"))],
        "why_it_matters": [_text(item) for item in _as_list(explanation.get("why_it_matters"))],
        "domains": assessment_domain_state_summary(payload),
        "findings": findings,
        "key_findings": [_text(item) for item in _as_list(explanation.get("key_findings"))],
        "unknowns": unknowns,
        "dependencies": dependency_items,
        "contradictions": [_text(item) for item in _as_list(explanation.get("contradictions"))],
        "reviews": reviews,
        "actions": action_items,
        "citations": citation_items,
        "source_records": records,
        "constraints": [_text(item) for item in _as_list(assessment.get("constraints")) or _as_list(explanation.get("constraints"))],
        "warnings": warnings,
        "summary": summary,
        "provenance": {
            "schema_version": _text(payload.get("schema_version"), "Not provided"),
            "stage_status": _as_dict(payload.get("stage_status")),
            "stage_counts": _as_dict(payload.get("stage_counts")),
            "timings_ms": _as_dict(payload.get("timings_ms")),
            "evidence_record_count": len(records),
            "finding_count": len(findings),
            "citation_count": len(citation_items),
            "failure_stage": _text(payload.get("failure_stage"), "Not provided"),
        },
    }


class _PdfWriter:
    """Small bounded-layout wrapper around PyMuPDF's page primitives."""

    def __init__(self, document: fitz.Document) -> None:
        self.document = document
        self.page = document.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
        self.y = MARGIN

    def new_body_page(self) -> None:
        self.page = self.document.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
        self.y = MARGIN
        self.page.draw_rect(fitz.Rect(0, 0, PAGE_WIDTH, 7), color=None, fill=TEAL)
        self.y = 34

    def ensure(self, height: float) -> None:
        if self.y + height > PAGE_HEIGHT - MARGIN:
            self.new_body_page()

    def heading(self, number: str, title: str) -> None:
        self.ensure(58)
        self.page.draw_line(fitz.Point(MARGIN, self.y), fitz.Point(PAGE_WIDTH - MARGIN, self.y), color=TURQUOISE, width=2)
        self.y += 17
        self.page.insert_text((MARGIN, self.y), f"{number}  {title}", fontsize=17, fontname="hebo", color=NAVY)
        self.y += 27

    def paragraph(self, value: object, *, color: tuple[float, float, float] = INK, size: float = 9.5, gap: float = 7) -> None:
        text = _truncate(_text(value), 1500)
        if not text:
            return
        lines = max(1, len(textwrap.wrap(text, width=94, break_long_words=False, break_on_hyphens=False)))
        height = lines * (size + 3) + gap
        self.ensure(height)
        self.page.insert_textbox(
            fitz.Rect(MARGIN, self.y, PAGE_WIDTH - MARGIN, self.y + height),
            text,
            fontsize=size,
            fontname="helv",
            color=color,
        )
        self.y += height

    def bullet(self, value: object, *, prefix: str = "• ") -> None:
        self.paragraph(prefix + _truncate(_text(value), 650), size=9.2, gap=4)

    def label_value(self, label: str, value: object) -> None:
        self.ensure(25)
        self.page.insert_text((MARGIN, self.y), label.upper(), fontsize=7.3, fontname="hebo", color=TEAL)
        self.y += 12
        self.paragraph(value, size=9.2, gap=8)

    def card(self, title: str, body: object, *, accent: tuple[float, float, float] = TURQUOISE) -> None:
        text = _truncate(_text(body), 720)
        lines = max(1, len(textwrap.wrap(text, width=84, break_long_words=False, break_on_hyphens=False)))
        height = 31 + lines * 12
        self.ensure(height + 9)
        rect = fitz.Rect(MARGIN, self.y, PAGE_WIDTH - MARGIN, self.y + height)
        self.page.draw_rect(rect, color=LINE, fill=PALE, width=0.7)
        self.page.draw_rect(fitz.Rect(rect.x0, rect.y0, rect.x0 + 4, rect.y1), color=None, fill=accent)
        self.page.insert_text((rect.x0 + 15, rect.y0 + 16), _truncate(title, 90), fontsize=10, fontname="hebo", color=NAVY)
        self.page.insert_textbox(
            fitz.Rect(rect.x0 + 15, rect.y0 + 22, rect.x1 - 12, rect.y1 - 6),
            text,
            fontsize=8.7,
            fontname="helv",
            color=INK,
        )
        self.y += height + 9


def render_assessment_report_pdf(payload: dict[str, Any]) -> bytes:
    """Render a professional PDF from the stored result without a backend call."""

    model = build_assessment_report_view_model(payload)
    document = fitz.open()
    writer = _PdfWriter(document)
    _draw_cover(writer.page, model)
    _draw_report_sections(writer, model)
    pdf_bytes = document.tobytes(garbage=4, deflate=True)
    document.close()
    return pdf_bytes


def safe_report_filename(payload: dict[str, Any]) -> str:
    """Return a filesystem-safe, human-readable download name."""

    context = _as_dict(payload.get("project_context"))
    project = _text(context.get("project_name") or context.get("project_id"), "INTERLOCK assessment")
    safe_project = re.sub(r"[^A-Za-z0-9]+", "_", project).strip("_") or "INTERLOCK_assessment"
    generated = _text(payload.get("generated_at"), "")
    date_match = re.search(r"(\d{4}-\d{2}-\d{2})", generated)
    date_text = date_match.group(1) if date_match else "undated"
    return f"INTERLOCK_{safe_project}_{date_text}.pdf"


def _draw_cover(page: fitz.Page, model: dict[str, Any]) -> None:
    page.draw_rect(fitz.Rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT), color=None, fill=NAVY)
    if WHITE_LOGO_PATH.is_file():
        page.insert_image(fitz.Rect(MARGIN, 54, MARGIN + 165, 104), filename=str(WHITE_LOGO_PATH), keep_proportion=True)
    else:
        page.insert_text((MARGIN, 86), "CANAVAN ATLANTIC", fontsize=16, fontname="hebo", color=(1, 1, 1))
    page.insert_text((MARGIN, 178), "INTERLOCK", fontsize=12, fontname="hebo", color=(0.62, 0.91, 0.88))
    page.insert_text((MARGIN, 222), "Assessment Report", fontsize=31, fontname="hebo", color=(1, 1, 1))
    page.insert_textbox(
        fitz.Rect(MARGIN, 247, PAGE_WIDTH - MARGIN, 305),
        "A traceable summary of the evidence, assessment findings, unknowns and professional review requests returned by INTERLOCK.",
        fontsize=12,
        fontname="helv",
        color=(0.88, 0.96, 0.96),
        lineheight=1.3,
    )
    project = model["project"]
    page.draw_rect(fitz.Rect(MARGIN, 385, PAGE_WIDTH - MARGIN, 535), color=(0.2, 0.39, 0.43), fill=(0.04, 0.27, 0.33), width=0.7)
    page.insert_text((MARGIN + 20, 420), _truncate(project["name"], 66), fontsize=18, fontname="hebo", color=(1, 1, 1))
    page.insert_text((MARGIN + 20, 453), _truncate(project["address"], 82), fontsize=10, fontname="helv", color=(0.78, 0.9, 0.9))
    page.insert_text((MARGIN + 20, 487), f"Workflow status  ·  {model['workflow_status']}", fontsize=9.5, fontname="hebo", color=(0.62, 0.91, 0.88))
    page.insert_text((MARGIN + 20, 511), f"Run ID  ·  {model['run_id']}", fontsize=8.8, fontname="helv", color=(0.78, 0.9, 0.9))
    page.insert_text((MARGIN, 760), "People. Places. Possibilities.", fontsize=9, fontname="hebo", color=(0.62, 0.91, 0.88))
    page.insert_text((MARGIN, 787), f"Generated from stored InterlockResult  ·  Report version {REPORT_VERSION}", fontsize=7.5, fontname="helv", color=(0.71, 0.83, 0.84))


def _draw_report_sections(writer: _PdfWriter, model: dict[str, Any]) -> None:
    writer.new_body_page()
    writer.heading("01", "Executive summary")
    writer.paragraph(model["executive_summary"], size=11, gap=12)
    summary = model["summary"]
    writer.card("Workflow status", model["workflow_status"], accent=_status_color(model["workflow_status"]))
    writer.card(
        "Recorded scope",
        f"{summary.get('finding_count', 0)} structured findings, {summary.get('evidence_record_count', 0)} evidence records, "
        f"{summary.get('unknown_theme_count', 0)} unknown themes and {summary.get('human_review_count', 0)} professional review requests.",
    )
    if model["known_facts"]:
        writer.paragraph("Known facts", color=TEAL, size=8.5, gap=3)
        for item in model["known_facts"]:
            writer.bullet(item)
    if model["why_it_matters"]:
        writer.paragraph("Why it matters", color=TEAL, size=8.5, gap=3)
        for item in model["why_it_matters"]:
            writer.bullet(item)
    writer.paragraph("This report reflects the stored workflow result. It does not infer approval, an unsupported readiness measure, or a final project decision.", color=MUTED, size=8.2)

    writer.heading("02", "Project inputs")
    for key, value in model["project"].items():
        writer.label_value(key.replace("_", " "), value)

    writer.heading("03", "Domain summary")
    writer.paragraph("The visual states below are the states actually returned by structured assessment findings. Separate domain slots are shown only when the current schema contains that domain; unsupported slots are not fabricated.", color=MUTED, size=8.7)
    _draw_domain_summary(writer, model["domains"])

    writer.heading("04", "Findings")
    if model["findings"]:
        for finding in model["findings"]:
            body_parts = [f"Status: {finding['status']}"]
            if finding.get("narrative"):
                body_parts.append(finding["narrative"])
            if finding.get("decision_impact"):
                body_parts.append(f"Why it matters: {finding['decision_impact']}")
            if finding.get("constraint"):
                body_parts.append(f"Constraint recorded: {finding['constraint']}")
            if finding.get("material_unknowns"):
                body_parts.append("Unknowns: " + "; ".join(finding["material_unknowns"]))
            if finding.get("evidence_ids"):
                body_parts.append("Evidence IDs: " + ", ".join(finding["evidence_ids"]))
            writer.card(f"{finding['domain']}  ·  {finding['finding_id']}", "\n".join(body_parts), accent=_status_color(finding["status"]))
    else:
        writer.paragraph("No structured findings were returned by the assessment stage.", color=MUTED)
        for item in model["key_findings"]:
            writer.card("Key finding returned by explanation stage", item, accent=BLUE)

    writer.heading("05", "Unknowns")
    if model["unknowns"]:
        for unknown in model["unknowns"]:
            body = unknown.get("summary") or "The current evidence does not resolve this theme."
            if unknown.get("underlying_unknowns"):
                body += "\nUnresolved items: " + "; ".join(unknown["underlying_unknowns"])
            if unknown.get("resolution_actions"):
                body += "\nPossible resolution: " + "; ".join(unknown["resolution_actions"])
            writer.card(unknown.get("title", "Material unknown"), body, accent=BLUE)
    else:
        writer.paragraph("No consolidated material unknown themes were returned.", color=MUTED)

    writer.heading("06", "Dependencies")
    if model["dependencies"]:
        for dependency in model["dependencies"]:
            item = _as_dict(dependency)
            title = _text(item.get("dependency_id"), "Dependency")
            body = _text(item.get("impact_description") or item.get("description"), "Dependency impact not described.")
            if item.get("status"):
                body = f"Status: {_display_enum(item['status'])}\n{body}"
            if item.get("evidence_ids"):
                body += "\nEvidence IDs: " + ", ".join(_text(ref) for ref in _as_list(item["evidence_ids"]))
            writer.card(title, body, accent=AMBER)
    else:
        writer.paragraph("No unresolved dependencies are recorded in the current assessment.", color=MUTED)

    writer.heading("07", "Contradictions")
    if model["contradictions"]:
        for item in model["contradictions"]:
            writer.card("Potential contradiction requiring review", item, accent=AMBER)
    else:
        writer.paragraph("No material evidence contradictions were returned.", color=MUTED)

    writer.heading("08", "Professional review")
    if model["reviews"]:
        for review in model["reviews"]:
            item = _as_dict(review)
            role = _display_enum(item.get("recommended_role"), "Specialist review")
            domain = _display_enum(item.get("domain"), "UNKNOWN")
            body = _text(item.get("reason"), "Review the related evidence.")
            body += f"\nSeverity: {_display_enum(item.get('severity'), 'MATERIAL')}"
            if item.get("evidence_ids"):
                body += "\nEvidence IDs: " + ", ".join(_text(ref) for ref in _as_list(item["evidence_ids"]))
            writer.card(f"{role}  ·  {domain}", body, accent=AMBER)
    else:
        writer.paragraph("No unresolved specialist reviews are recorded.", color=MUTED)

    writer.heading("09", "Actions")
    if model["actions"]:
        for action in model["actions"]:
            item = _as_dict(action)
            body = _text(item.get("rationale"), "Resolve the related evidence gap before relying on this point.")
            if item.get("specialist_roles"):
                body += "\nSpecialist roles: " + ", ".join(_text(role) for role in _as_list(item["specialist_roles"]))
            if item.get("evidence_ids"):
                body += "\nEvidence IDs: " + ", ".join(_text(ref) for ref in _as_list(item["evidence_ids"]))
            writer.card(_text(item.get("title"), "Next action"), body, accent=TEAL)
    else:
        writer.paragraph("No consolidated next actions were returned.", color=MUTED)

    writer.heading("10", "Sources & citations")
    if model["citations"]:
        for citation in model["citations"]:
            title = f"{citation['document_id']}  ·  {citation['locator']}"
            body = f"Source path: {citation['source_path']}"
            if citation.get("section_heading"):
                body += f"\nSection: {citation['section_heading']}"
            if citation.get("page_start") is not None:
                page_text = str(citation["page_start"])
                if citation.get("page_end") is not None and citation["page_end"] != citation["page_start"]:
                    page_text += f"–{citation['page_end']}"
                body += f"\nPages: {page_text}"
            writer.card(title, body, accent=TEAL)
    else:
        writer.paragraph("No customer-facing citations were returned.", color=MUTED)
    if model["source_records"]:
        writer.paragraph(f"Evidence provenance includes {len(model['source_records'])} stored evidence records. Full evidence IDs remain available in the Streamlit Decision Pack.", color=MUTED, size=8.2)

    writer.heading("11", "Methodology & limitations")
    writer.paragraph("This PDF is generated from the successful stored InterlockResult in the browser session. It presents deterministic evidence, structured assessment findings, explanation fields, unknowns, dependencies, contradictions, actions and human-review requests as returned by the workflow.")
    writer.bullet("UNKNOWN is preserved as an evidence state and is not converted into a negative conclusion.")
    writer.bullet("The report does not call an agent, retrieve new policy, alter citations, calculate a score, or produce a final project decision.")
    writer.bullet("Domain groupings are presentation groupings only; combined groups retain the most cautionary state among their actual source domains.")
    if model["constraints"]:
        writer.paragraph("Recorded constraints", color=TEAL, size=8.5, gap=3)
        for item in model["constraints"]:
            writer.bullet(item)
    for item in model["warnings"]:
        writer.card("Workflow warning", item, accent=AMBER)

    writer.heading("12", "Provenance")
    provenance = model["provenance"]
    for key in ("schema_version", "evidence_record_count", "finding_count", "citation_count", "failure_stage"):
        writer.label_value(key.replace("_", " "), provenance.get(key))
    for title, values in (("Stage status", provenance.get("stage_status")), ("Stage counts", provenance.get("stage_counts")), ("Timings (ms)", provenance.get("timings_ms"))):
        writer.label_value(title, _format_mapping(values))
    writer.paragraph(
        f"Run ID: {model['run_id']}\nGenerated at: {model['generated_at']}\nReport version: {model['report_version']}",
        color=MUTED,
        size=8.2,
    )


def _draw_domain_summary(writer: _PdfWriter, domains: list[dict[str, Any]]) -> None:
    if not domains:
        writer.paragraph("No structured domain findings were returned by the assessment stage.", color=MUTED)
        return
    for index, item in enumerate(domains):
        writer.ensure(30)
        color = _status_color(item.get("state"))
        x = MARGIN + (index % 2) * (BODY_WIDTH / 2)
        y = writer.y
        writer.page.draw_circle(fitz.Point(x + 9, y + 7), 7, color=color, fill=color)
        writer.page.insert_text((x + 23, y + 10), _truncate(f"{item['label']}  ·  {item['state']}", 42), fontsize=8.8, fontname="hebo", color=INK)
        writer.page.insert_text((x + 23, y + 22), f"Findings: {len(item.get('finding_ids', []))}  |  Evidence: {len(item.get('evidence_ids', []))}", fontsize=7.4, fontname="helv", color=MUTED)
        if index % 2 == 1 or index == len(domains) - 1:
            writer.y += 36


def _finding_narratives(explanation: dict[str, Any]) -> dict[str, str]:
    output: dict[str, str] = {}
    for value in _as_list(explanation.get("key_findings")):
        text = _text(value)
        if "[finding:" in text:
            finding_id = text.split("[finding:", 1)[1].split("]", 1)[0].strip()
            output[finding_id] = text.split(" [finding:", 1)[0]
    return output


def _status_color(value: object) -> tuple[float, float, float]:
    status = _display_enum(value, "UNKNOWN")
    if status == "CLEAR":
        return GREEN
    if status == "INFORMATIONAL":
        return TURQUOISE
    if status == "CONDITIONAL":
        return AMBER
    if status == "CONSTRAINED":
        return RED
    return BLUE


def _format_mapping(value: object) -> str:
    if not isinstance(value, dict) or not value:
        return "Not provided"
    return "; ".join(f"{key}: {val}" for key, val in value.items())


def _display_value(value: object) -> str:
    if value is None or value == "":
        return "Not provided"
    if _display_enum(value) == "Unknown":
        return "Unknown"
    return str(value)


def _display_enum(value: object, default: str = "UNKNOWN") -> str:
    if value is None or value == "":
        return default
    return str(getattr(value, "value", value))


def _optional_text(value: object) -> str | None:
    if value is None or value == "":
        return None
    return str(value)


def _text(value: object, default: str = "") -> str:
    result = _optional_text(value)
    return result if result is not None else default


def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 1)].rstrip() + "…"


def _as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


__all__ = ["REPORT_VERSION", "build_assessment_report_view_model", "render_assessment_report_pdf", "safe_report_filename"]
