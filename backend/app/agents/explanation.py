"""Deterministic, evidence-grounded Module 8 explanations.

The Explanation Agent is deliberately a presentation layer over the Module 7
AssessmentResult.  It does not gather evidence, reinterpret policy, resolve
contradictions, or make a project decision.
"""

from __future__ import annotations

from typing import Any, Iterable

from ..schemas.agents import (
    AgentEvidenceState,
    AssessmentFinding,
    AssessmentStatus,
    DependencyRecord,
    EvidenceBundle,
    EvidenceCreatedBy,
    EvidenceRecord,
    EvidenceSourceTrust,
    ExplanationAction,
    ExplanationRequest,
    ExplanationResult,
    ExplanationUnknownTheme,
    HumanReviewRequest,
)
from ..services.rag.models import CitationReference


class ExplanationAgentError(RuntimeError):
    """Controlled error for an invalid Module 8 request."""


def _value(value: Any) -> str:
    return str(getattr(value, "value", value) or "")


def _unique(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def _ids_suffix(evidence_ids: Iterable[str]) -> str:
    ids = _unique(evidence_ids)
    return f" [evidence: {', '.join(ids)}]" if ids else ""


def _status(finding: AssessmentFinding) -> str:
    return _value(finding.status)


def _is_benchmark_record(record: EvidenceRecord) -> bool:
    """Exclude explicit benchmark-only records from customer explanations."""

    if not isinstance(record.value, dict):
        return False
    value = record.value.get("benchmark_only")
    return value is True or str(value).casefold() == "true"


def _is_unknown_record(record: EvidenceRecord) -> bool:
    return _value(record.evidence_state) in {
        AgentEvidenceState.UNKNOWN.value,
        AgentEvidenceState.NOT_PROVIDED.value,
    }


def _source_label(record: EvidenceRecord) -> str:
    if (
        _value(record.source_trust) == EvidenceSourceTrust.AUTHORITATIVE_POLICY.value
        or (
            _value(record.created_by) == EvidenceCreatedBy.RAG_RETRIEVAL.value
            and _value(record.source_class) in {"PRIMARY", "CURATED"}
            and _value(record.document_status) == "CURRENT"
        )
    ):
        return "AUTHORITATIVE POLICY"
    if _value(record.created_by) == EvidenceCreatedBy.DETERMINISTIC_GIS.value:
        return "DETERMINISTIC GIS"
    if _value(record.source_trust) == EvidenceSourceTrust.DETERMINISTIC_SOURCE.value:
        return "DETERMINISTIC SOURCE"
    if _value(record.created_by) == EvidenceCreatedBy.PROJECT_DOCUMENT.value:
        return "PROJECT DOCUMENT (UNVERIFIED)"
    if _value(record.created_by) == EvidenceCreatedBy.DEVELOPER_INPUT.value:
        return "DEVELOPER-PROVIDED INPUT"
    if _value(record.source_trust) == EvidenceSourceTrust.SUPPORTING_SOURCE.value:
        return "SUPPORTING SOURCE"
    return "SOURCE TYPE UNKNOWN"


def _citation_key(citation: CitationReference) -> tuple[Any, ...]:
    payload = citation.model_dump(mode="json")
    return tuple(payload.get(key) for key in (
        "document_id",
        "source_path",
        "page_start",
        "page_end",
        "section_heading",
        "paragraph_start",
        "paragraph_end",
        "locator",
    ))


_CUSTOMER_CITATIONS_PER_ITEM = 3

_UNKNOWN_THEME_RULES: tuple[tuple[str, str, tuple[str, ...], str], ...] = (
    (
        "grid-connection-readiness",
        "GRID CONNECTION READINESS",
        ("mic", "energisation", "energization", "grid connection", "connection status", "connection offer", "grid capacity"),
        "Current evidence is insufficient to confirm project-specific grid connection readiness, including MIC, connection status and energisation where relevant.",
    ),
    (
        "planning-zoning-evidence",
        "SITE-SPECIFIC PLANNING / ZONING EVIDENCE",
        ("zoning", "local-authority", "local authority", "planning evidence", "development plan", "planning"),
        "Current evidence is insufficient to confirm authoritative site-specific planning or zoning position.",
    ),
    (
        "water-connection-readiness",
        "WATER / WASTEWATER CONNECTION READINESS",
        ("water", "wastewater", "water capacity", "water connection"),
        "Current evidence is insufficient to confirm site-specific water or wastewater capacity and connection readiness.",
    ),
    (
        "renewable-commissioning",
        "RENEWABLE COMMISSIONING",
        ("renewable", "commission", "commissioned"),
        "Current evidence is insufficient to confirm that planned renewable assets are commissioned and operational.",
    ),
    (
        "energy-strategy",
        "PROJECT ENERGY STRATEGY",
        ("energy strategy", "energy_strategy", "power strategy", "power_strategy", "planned power", "planned_power", "power demand", "power_demand"),
        "Current evidence is insufficient to confirm the project energy strategy and its supporting inputs.",
    ),
    (
        "environmental-specialist-evidence",
        "ENVIRONMENTAL / ECOLOGICAL EVIDENCE",
        ("biodiversity", "ecology", "ecological", "environment", "eia", "aa", "flood", "heritage", "archaeology"),
        "Current evidence is insufficient to confirm the relevant site-specific environmental or ecological position.",
    ),
    (
        "project-definition",
        "PROJECT DEFINITION AND PHASING",
        ("project stage", "project_stage", "site area", "site_area", "phasing", "scope"),
        "Current evidence is insufficient to confirm the project definition, stage or phasing inputs needed for the affected assessment.",
    ),
)

_ACTION_RULES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "grid-connection-readiness",
        "Confirm project-specific grid connection readiness, including MIC, connection status and energisation evidence.",
        ("mic", "energisation", "energization", "grid", "connection"),
    ),
    (
        "planning-zoning-evidence",
        "Obtain authoritative site-specific planning and zoning confirmation.",
        ("zoning", "planning", "local authority", "local-authority", "development plan"),
    ),
    (
        "water-connection-readiness",
        "Confirm site-specific water and wastewater capacity and connection status.",
        ("water", "wastewater"),
    ),
    (
        "renewable-commissioning",
        "Obtain evidence of renewable asset commissioning and operational status.",
        ("renewable", "commission", "commissioned"),
    ),
    (
        "energy-strategy",
        "Confirm the project energy strategy and supporting power inputs.",
        ("energy strategy", "energy_strategy", "power strategy", "power_strategy", "planned power", "planned_power", "power demand", "power_demand"),
    ),
    (
        "environmental-specialist-evidence",
        "Obtain the site-specific environmental or ecological evidence required for this assessment.",
        ("biodiversity", "ecology", "ecological", "environment", "eia", "aa", "flood", "heritage", "archaeology"),
    ),
    (
        "project-definition",
        "Confirm the current project definition, stage and phasing inputs.",
        ("project stage", "project_stage", "site area", "site_area", "phasing", "scope"),
    ),
)


def _rule_for_key(
    rules: Iterable[tuple[str, str, tuple[str, ...], str]],
    key: str,
) -> tuple[str, str, tuple[str, ...], str] | None:
    return next((rule for rule in rules if rule[0] == key), None)


def _theme_key(text: str, domain: Any = None) -> str:
    lower = " ".join(str(text or "").split()).casefold()
    domain_value = _value(domain).casefold()
    if "water" in lower or "wastewater" in lower:
        return "water-connection-readiness"
    for key, _, terms, _ in _UNKNOWN_THEME_RULES:
        if any(term in lower for term in terms):
            return key
    if domain_value == "grid":
        return "grid-connection-readiness"
    if domain_value == "planning":
        return "planning-zoning-evidence"
    if domain_value == "water":
        return "water-connection-readiness"
    if domain_value in {"environment", "biodiversity"}:
        return "environmental-specialist-evidence"
    return "other-material-unknown"


def _action_key(text: str) -> str:
    lower = " ".join(str(text or "").split()).casefold()
    if "water" in lower or "wastewater" in lower:
        return "water-connection-readiness"
    for key, _, terms in _ACTION_RULES:
        if any(term in lower for term in terms):
            return key
    return "action:" + lower


def _action_title(key: str, source_actions: Iterable[str]) -> str:
    rule = next((rule for rule in _ACTION_RULES if rule[0] == key), None)
    if rule is not None:
        return rule[1]
    first = next(iter(source_actions), "Confirm the assessment evidence requirement.")
    return _clean(first).rstrip(".") + "."


def _citations_for_ids(
    evidence_ids: Iterable[str],
    record_map: dict[str, EvidenceRecord],
    *,
    limit: int | None = None,
) -> list[CitationReference]:
    citations: list[CitationReference] = []
    seen: set[tuple[Any, ...]] = set()
    for evidence_id in _unique(evidence_ids):
        record = record_map.get(evidence_id)
        if record is None or record.citation is None:
            continue
        key = _citation_key(record.citation)
        if key in seen:
            continue
        seen.add(key)
        citations.append(record.citation)
        if limit is not None and len(citations) >= limit:
            break
    return citations


def _finding_text(finding: AssessmentFinding, *, evidence_ids: Iterable[str] | None = None) -> str:
    """Turn one assessment finding into a constrained human-readable item."""

    status = _status(finding)
    domain = _value(finding.domain)
    ids = list(evidence_ids if evidence_ids is not None else finding.evidence_ids)

    if status == AssessmentStatus.CONSTRAINED.value:
        detail = _clean(finding.constraint) or "A constrained status is recorded by the assessment."
        text = f"CONSTRAINED — {domain}: {detail}"
    elif status == AssessmentStatus.CONDITIONAL.value:
        detail = _clean(finding.decision_impact) or "This issue is potentially resolvable, subject to further evidence or specialist review."
        text = f"CONDITIONAL — {domain}: {detail}"
    elif status == AssessmentStatus.UNKNOWN.value:
        unknowns = _unique(finding.material_unknowns)
        detail = "; ".join(unknowns) or f"{domain} evidence is incomplete."
        text = f"UNKNOWN — {domain}: INTERLOCK has not found sufficient evidence to confirm {detail}."
    elif status == AssessmentStatus.CLEAR.value:
        detail = _clean(finding.decision_impact) or "No explicit hard constraint was identified in the supplied evidence."
        text = f"CLEAR — {domain}: {detail}"
    else:
        text = f"{status or 'NOT_ASSESSED'} — {domain}: The assessment did not classify this domain as resolved."

    if finding.evidence_required_next:
        text += f" Evidence that could resolve or progress this item: {'; '.join(_unique(finding.evidence_required_next))}."
    return f"{text} [finding: {finding.finding_id}]" + _ids_suffix(ids)


def _context_facts(request: ExplanationRequest) -> list[str]:
    context = request.project_context
    facts: list[str] = []
    if context.project_name:
        facts.append(f"DEVELOPER-PROVIDED PROJECT CONTEXT identifies the project as {context.project_name}.")
    if context.project_type:
        facts.append(f"DEVELOPER-PROVIDED PROJECT CONTEXT records the project type as {context.project_type}.")
    if context.location.address:
        facts.append(f"DEVELOPER-PROVIDED PROJECT CONTEXT records the site as {context.location.address}.")
    return facts


def _record_fact(record: EvidenceRecord) -> str:
    fact = _clean(record.finding or record.fact or record.field_name)
    return f"{_source_label(record)} [{record.evidence_id}]: {fact}"


def _review_text(
    review: HumanReviewRequest,
    *,
    evidence_ids: Iterable[str] | None = None,
    review_ids: Iterable[str] | None = None,
) -> str:
    ids = list(evidence_ids if evidence_ids is not None else review.evidence_ids)
    reviews = _unique(review_ids if review_ids is not None else [review.review_id])
    role = _value(review.recommended_role) or "UNKNOWN"
    domain = _value(review.domain) or "UNKNOWN"
    review_label = "review" if len(reviews) == 1 else "reviews"
    return (
        f"{role} review for {domain} is required: {_clean(review.reason)}"
        f" [{review_label}: {', '.join(reviews)}]"
        f"{_ids_suffix(ids)}"
    )


def _dependency_text(dependency: DependencyRecord) -> str:
    status = _value(dependency.status) or "UNKNOWN"
    detail = _clean(dependency.impact_description) or _clean(dependency.description)
    action = "; ".join(_unique(dependency.evidence_required_next))
    if action:
        detail += f" Evidence that could resolve it: {action}."
    return (
        f"{dependency.dependency_id} ({status}) — {detail}"
        f"{_ids_suffix(dependency.evidence_ids)}"
    )


def _is_contradiction_finding(finding: AssessmentFinding) -> bool:
    text = " ".join(
        [
            _clean(finding.decision_impact),
            *_unique(finding.material_unknowns),
            *_unique(finding.evidence_required_next),
        ]
    ).casefold()
    return any(term in text for term in ("conflicting evidence", "scope mismatch", "scope versions", "contradiction"))


def _finding_priority(finding: AssessmentFinding) -> int:
    """Order material explanations before supporting or resolved findings."""

    status = _status(finding)
    if status == AssessmentStatus.CONSTRAINED.value:
        return 0
    if _is_contradiction_finding(finding):
        return 1
    if finding.dependency_ids:
        return 2
    if status == AssessmentStatus.UNKNOWN.value:
        return 3
    if status == AssessmentStatus.CONDITIONAL.value:
        return 4
    return 5


def _build_unknown_themes(
    assessment: Any,
    record_map: dict[str, EvidenceRecord],
    eligible_evidence_ids: set[str],
) -> list[ExplanationUnknownTheme]:
    grouped: dict[str, dict[str, list[str]]] = {}

    def add(
        key: str,
        unknown: str,
        *,
        finding_ids: Iterable[str] = (),
        evidence_ids: Iterable[str] = (),
        resolution_actions: Iterable[str] = (),
    ) -> None:
        item = grouped.setdefault(
            key,
            {
                "underlying_unknowns": [],
                "finding_ids": [],
                "evidence_ids": [],
                "resolution_actions": [],
            },
        )
        item["underlying_unknowns"] = _unique([*item["underlying_unknowns"], _clean(unknown)])
        item["finding_ids"] = _unique([*item["finding_ids"], *finding_ids])
        item["evidence_ids"] = _unique(
            [*item["evidence_ids"], *(evidence_id for evidence_id in evidence_ids if evidence_id in eligible_evidence_ids)]
        )
        item["resolution_actions"] = _unique([*item["resolution_actions"], *resolution_actions])

    for finding in assessment.findings:
        for unknown in finding.material_unknowns:
            add(
                _theme_key(unknown, finding.domain),
                unknown,
                finding_ids=[finding.finding_id],
                evidence_ids=finding.evidence_ids,
                resolution_actions=finding.evidence_required_next,
            )

    for unknown in assessment.material_unknowns:
        key = _theme_key(unknown)
        matching_findings = [
            finding
            for finding in assessment.findings
            if _theme_key(
                " ".join(
                    [
                        _value(finding.domain),
                        *finding.material_unknowns,
                        finding.decision_impact or "",
                        *finding.evidence_required_next,
                    ]
                ),
                finding.domain,
            )
            == key
        ]
        if matching_findings:
            for finding in matching_findings:
                add(
                    key,
                    unknown,
                    finding_ids=[finding.finding_id],
                    evidence_ids=finding.evidence_ids,
                    resolution_actions=finding.evidence_required_next,
                )
        else:
            add(key, unknown)

    ordered_keys = [rule[0] for rule in _UNKNOWN_THEME_RULES]
    ordered_keys.extend(key for key in grouped if key not in ordered_keys)
    themes: list[ExplanationUnknownTheme] = []
    for key in ordered_keys:
        item = grouped.get(key)
        if item is None:
            continue
        rule = _rule_for_key(_UNKNOWN_THEME_RULES, key)
        title = rule[1] if rule else "OTHER MATERIAL UNKNOWN"
        summary = rule[3] if rule else "Current evidence is insufficient to confirm this assessment item."
        themes.append(
            ExplanationUnknownTheme(
                theme_id=f"unknown-theme-{key}",
                title=title,
                summary=summary,
                underlying_unknowns=item["underlying_unknowns"],
                finding_ids=item["finding_ids"],
                evidence_ids=item["evidence_ids"],
                resolution_actions=item["resolution_actions"],
                citations=_citations_for_ids(
                    item["evidence_ids"],
                    record_map,
                    limit=_CUSTOMER_CITATIONS_PER_ITEM,
                ),
            )
        )
    return themes


def _build_action_plan(
    assessment: Any,
    record_map: dict[str, EvidenceRecord],
    eligible_evidence_ids: set[str],
) -> list[ExplanationAction]:
    grouped: dict[str, dict[str, list[str]]] = {}

    def add(
        key: str,
        source_action: str,
        *,
        finding_ids: Iterable[str] = (),
        dependency_ids: Iterable[str] = (),
        evidence_ids: Iterable[str] = (),
        rationales: Iterable[str] = (),
    ) -> None:
        item = grouped.setdefault(
            key,
            {
                "source_actions": [],
                "finding_ids": [],
                "dependency_ids": [],
                "evidence_ids": [],
                "rationales": [],
            },
        )
        item["source_actions"] = _unique([*item["source_actions"], _clean(source_action)])
        item["finding_ids"] = _unique([*item["finding_ids"], *finding_ids])
        item["dependency_ids"] = _unique([*item["dependency_ids"], *dependency_ids])
        item["evidence_ids"] = _unique(
            [*item["evidence_ids"], *(evidence_id for evidence_id in evidence_ids if evidence_id in eligible_evidence_ids)]
        )
        item["rationales"] = _unique([*item["rationales"], *(_clean(value) for value in rationales if value)])

    for finding in assessment.findings:
        for action in finding.evidence_required_next:
            add(
                _action_key(action),
                action,
                finding_ids=[finding.finding_id],
                evidence_ids=finding.evidence_ids,
                rationales=[finding.decision_impact or ""],
            )
    for dependency in assessment.dependencies:
        for action in dependency.evidence_required_next:
            add(
                _action_key(action),
                action,
                dependency_ids=[dependency.dependency_id],
                evidence_ids=dependency.evidence_ids,
                rationales=[dependency.impact_description or dependency.description],
            )

    ordered_keys = list(grouped)
    actions: list[ExplanationAction] = []
    for key in ordered_keys:
        item = grouped[key]
        evidence_ids = item["evidence_ids"]
        roles: list[str] = []
        for review in assessment.human_reviews:
            review_key = _action_key(review.reason)
            if review_key == key or set(review.evidence_ids).intersection(evidence_ids):
                role = _value(review.recommended_role)
                if role and role not in roles:
                    roles.append(role)
        rationale = (
            "This action addresses the assessment evidence requirements: "
            + "; ".join(item["rationales"])
            if item["rationales"]
            else "This action consolidates related assessment evidence requirements."
        )
        actions.append(
            ExplanationAction(
                action_id=f"action-{key}",
                title=_action_title(key, item["source_actions"]),
                rationale=rationale,
                source_actions=item["source_actions"],
                finding_ids=item["finding_ids"],
                dependency_ids=item["dependency_ids"],
                evidence_ids=evidence_ids,
                specialist_roles=roles,
                citations=_citations_for_ids(
                    evidence_ids,
                    record_map,
                    limit=_CUSTOMER_CITATIONS_PER_ITEM,
                ),
            )
        )
    return actions


def _customer_citations(
    findings: Iterable[AssessmentFinding],
    themes: Iterable[ExplanationUnknownTheme],
    actions: Iterable[ExplanationAction],
    record_map: dict[str, EvidenceRecord],
) -> list[CitationReference]:
    citations: list[CitationReference] = []
    seen: set[tuple[Any, ...]] = set()

    def add(items: Iterable[CitationReference]) -> None:
        for citation in items:
            key = _citation_key(citation)
            if key not in seen:
                seen.add(key)
                citations.append(citation)

    for finding in findings:
        if _finding_priority(finding) < 5:
            add(_citations_for_ids(finding.evidence_ids, record_map, limit=_CUSTOMER_CITATIONS_PER_ITEM))
    for theme in themes:
        add(theme.citations)
    for action in actions:
        add(action.citations)
    return citations


class DeterministicExplanationAgent:
    """Explain one existing AssessmentResult without changing its meaning."""

    def run(self, request: ExplanationRequest) -> ExplanationResult:
        context = request.project_context
        assessment = request.assessment_result
        if context.project_id != assessment.project_context.project_id:
            raise ExplanationAgentError(
                "ExplanationRequest project_context and assessment_result project IDs must match"
            )

        bundle = request.evidence_bundle
        if bundle is not None:
            if bundle.project_context.project_id != context.project_id:
                raise ExplanationAgentError(
                    "ExplanationRequest evidence_bundle and project_context project IDs must match"
                )

        all_record_map: dict[str, EvidenceRecord] = {}
        if bundle is not None:
            all_record_map = {
                record.evidence_id: record
                for record in bundle.records
                if not _is_benchmark_record(record)
            }

        finding_ids = [evidence_id for finding in assessment.findings for evidence_id in finding.evidence_ids]
        dependency_ids = [evidence_id for dependency in assessment.dependencies for evidence_id in dependency.evidence_ids]
        review_ids = [evidence_id for review in assessment.human_reviews for evidence_id in review.evidence_ids]
        contradiction_ids = [
            evidence_id
            for finding in assessment.findings
            if _is_contradiction_finding(finding)
            for evidence_id in finding.evidence_ids
        ]
        bundle_contradiction_ids = [
            evidence_id
            for contradiction in (bundle.potential_contradictions if bundle is not None else [])
            for evidence_id in contradiction.evidence_ids
        ]
        referenced_ids = _unique(
            [*finding_ids, *dependency_ids, *review_ids, *contradiction_ids, *bundle_contradiction_ids]
        )
        benchmark_ids = {
            record.evidence_id
            for record in (bundle.records if bundle is not None else [])
            if _is_benchmark_record(record)
        }
        # Preserve assessment references even when the optional evidence bundle
        # is incomplete, while still excluding explicit benchmark-only IDs.
        referenced_ids = [evidence_id for evidence_id in referenced_ids if evidence_id not in benchmark_ids]
        record_ids = [evidence_id for evidence_id in referenced_ids if evidence_id in all_record_map]

        ordered_findings = sorted(
            enumerate(assessment.findings),
            key=lambda item: (_finding_priority(item[1]), item[0]),
        )
        key_findings = [
            _finding_text(finding, evidence_ids=[evidence_id for evidence_id in finding.evidence_ids if evidence_id in referenced_ids] if bundle is not None else finding.evidence_ids)
            for _, finding in ordered_findings
        ]
        conditional_issues = [
            text
            for text, (_, finding) in zip(key_findings, ordered_findings)
            if _status(finding) == AssessmentStatus.CONDITIONAL.value
        ]

        constraints = _unique(assessment.constraints)
        material_unknowns = _unique(
            [
                *assessment.material_unknowns,
                *(unknown for finding in assessment.findings for unknown in finding.material_unknowns),
            ]
        )
        why_it_matters = _unique(
            [
                *(_clean(finding.decision_impact) for _, finding in ordered_findings if finding.decision_impact),
                *(constraint for constraint in constraints),
                *(_clean(dependency.impact_description or dependency.description) for dependency in assessment.dependencies),
            ]
        )
        dependencies = [_dependency_text(dependency) for dependency in assessment.dependencies]

        contradictions: list[str] = []
        if bundle is not None:
            for contradiction in bundle.potential_contradictions:
                ids = [evidence_id for evidence_id in contradiction.evidence_ids if evidence_id in referenced_ids]
                contradictions.append(
                    f"CONTRADICTION — {_value(contradiction.domain)}: {_clean(contradiction.description)}"
                    f"{_ids_suffix(ids)}"
                )
        contradictions.extend(
            _finding_text(finding, evidence_ids=[evidence_id for evidence_id in finding.evidence_ids if evidence_id in referenced_ids] if bundle is not None else finding.evidence_ids)
            for _, finding in ordered_findings
            if _is_contradiction_finding(finding)
        )
        contradictions = _unique(contradictions)

        human_handoffs: list[str] = []
        grouped_reviews: dict[tuple[str, str, str], dict[str, Any]] = {}
        for review in assessment.human_reviews:
            role = _value(review.recommended_role)
            key = (role, _value(review.domain), _clean(review.reason).casefold())
            group = grouped_reviews.setdefault(
                key,
                {"review": review, "review_ids": [], "evidence_ids": []},
            )
            group["review_ids"] = _unique([*group["review_ids"], review.review_id])
            group["evidence_ids"] = _unique([*group["evidence_ids"], *review.evidence_ids])
        for group in grouped_reviews.values():
            ids = [evidence_id for evidence_id in group["evidence_ids"] if evidence_id in referenced_ids] if bundle is not None else group["evidence_ids"]
            human_handoffs.append(
                _review_text(
                    group["review"],
                    evidence_ids=ids,
                    review_ids=group["review_ids"],
                )
            )

        next_actions = _unique(
            [
                action
                for finding in assessment.findings
                for action in finding.evidence_required_next
            ]
            + [
                action
                for dependency in assessment.dependencies
                for action in dependency.evidence_required_next
            ]
        )

        known_facts = _context_facts(request)
        if bundle is not None:
            for evidence_id in record_ids:
                record = all_record_map[evidence_id]
                if not _is_unknown_record(record):
                    known_facts.append(_record_fact(record))
        known_facts = _unique(known_facts)

        citations: list[CitationReference] = []
        citation_keys: set[tuple[Any, ...]] = set()
        if bundle is not None:
            for evidence_id in record_ids:
                citation = all_record_map[evidence_id].citation
                if citation is None or _citation_key(citation) in citation_keys:
                    continue
                citation_keys.add(_citation_key(citation))
                citations.append(citation)

        material_unknown_themes = _build_unknown_themes(
            assessment,
            all_record_map,
            set(referenced_ids),
        )
        next_action_plan = _build_action_plan(
            assessment,
            all_record_map,
            set(referenced_ids),
        )
        customer_facing_citations = _customer_citations(
            (finding for _, finding in ordered_findings),
            material_unknown_themes,
            next_action_plan,
            all_record_map,
        )

        if constraints:
            summary = f"The assessment records {len(constraints)} explicit constraint(s) supported by the supplied assessment."
        elif material_unknowns:
            summary = "The assessment remains evidence-limited: material unknowns require resolution before the affected matters can be confirmed."
        elif conditional_issues:
            summary = "The assessment identifies conditional issues that may be resolvable subject to the evidence and specialist reviews listed below."
        else:
            summary = "The assessment contains no explicit hard constraint in the supplied result; this explanation does not make a project decision."
        if assessment.human_reviews:
            summary += f" {len(assessment.human_reviews)} specialist review request(s) remain recorded."

        warnings = _unique(
            [
                *assessment.warnings,
                "Module 8 explains the structured assessment; it does not gather evidence, resolve uncertainty, or produce a final project decision.",
                "Detailed material_unknowns, next_actions, evidence_ids and source_citations remain available for provenance-preserving drill-down; customer-facing themes and action plans are consolidated views.",
            ]
        )
        return ExplanationResult(
            executive_summary=summary,
            key_findings=key_findings,
            conditional_issues=conditional_issues,
            contradictions=contradictions,
            why_it_matters=why_it_matters,
            known_facts=known_facts,
            material_unknowns=material_unknowns,
            constraints=constraints,
            dependencies=dependencies,
            next_actions=next_actions,
            human_handoffs=human_handoffs,
            evidence_ids=referenced_ids,
            source_citations=citations,
            material_unknown_themes=material_unknown_themes,
            next_action_plan=next_action_plan,
            customer_facing_citations=customer_facing_citations,
            warnings=warnings,
        )


__all__ = ["DeterministicExplanationAgent", "ExplanationAgentError"]
