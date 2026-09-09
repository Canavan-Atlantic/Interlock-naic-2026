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
    ExplanationRequest,
    ExplanationResult,
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


def _review_text(review: HumanReviewRequest, *, evidence_ids: Iterable[str] | None = None) -> str:
    ids = list(evidence_ids if evidence_ids is not None else review.evidence_ids)
    role = _value(review.recommended_role) or "UNKNOWN"
    domain = _value(review.domain) or "UNKNOWN"
    return (
        f"{role} review for {domain} is required: {_clean(review.reason)}"
        f" [review: {review.review_id}]"
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
        seen_reviews: set[tuple[str, str, str]] = set()
        for review in assessment.human_reviews:
            role = _value(review.recommended_role)
            key = (role, _value(review.domain), _clean(review.reason).casefold())
            if key in seen_reviews:
                continue
            seen_reviews.add(key)
            ids = [evidence_id for evidence_id in review.evidence_ids if evidence_id in referenced_ids] if bundle is not None else review.evidence_ids
            human_handoffs.append(_review_text(review, evidence_ids=ids))

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
            warnings=warnings,
        )


__all__ = ["DeterministicExplanationAgent", "ExplanationAgentError"]
