"""Deterministic-first Module 7 constraint assessment.

The Assessment Agent consumes an existing EvidenceBundle.  It does not call
GIS, RAG, external services, an LLM, or any project decision workflow.
"""

from __future__ import annotations

from collections import defaultdict
import re
from typing import Any, Iterable

from ..schemas.agents import (
    AgentEvidenceState,
    AssessmentFinding,
    AssessmentRequest,
    AssessmentResult,
    DependencyRecord,
    EvidenceCreatedBy,
    EvidenceRecord,
    EvidenceSourceTrust,
    HumanReviewRequest,
    HumanReviewRole,
)
from ..schemas.agents.common import HumanReviewSeverity
from ..services.rag.models import Domain, DocumentStatus, SourceClass


class AssessmentAgentError(RuntimeError):
    """Controlled error for an invalid assessment request."""


_DOMAIN_ORDER: tuple[Domain, ...] = (
    Domain.PLANNING,
    Domain.GRID,
    Domain.ENERGY,
    Domain.WATER,
    Domain.BIODIVERSITY,
    Domain.ENVIRONMENT,
    Domain.INFRASTRUCTURE,
    Domain.DATA_CENTRE_POLICY,
    Domain.GENERAL,
)

_DOMAIN_KEYWORDS: dict[Domain, tuple[str, ...]] = {
    Domain.GRID: ("grid", "mic", "connection", "energisation", "energization", "substation"),
    Domain.ENERGY: ("energy", "renewable", "commission", "dispatchable", "storage"),
    Domain.PLANNING: ("planning", "zoning", "local authority", "development plan", "planning permission"),
    Domain.BIODIVERSITY: ("biodiversity", "ecology", "ecological", "sac", "spa", "protected site"),
    Domain.ENVIRONMENT: ("environment", "flood", "ground", "geology", "heritage", "archaeology", "eia", "aa"),
    Domain.WATER: ("water", "wastewater", "uisce", "utility connection"),
    Domain.DATA_CENTRE_POLICY: ("data centre", "data-centre", "data_center"),
    Domain.INFRASTRUCTURE: ("infrastructure", "utility", "capacity", "asset"),
    Domain.GENERAL: ("project", "scope", "configuration", "stage", "phasing"),
}

_HIGH_CONSEQUENCE_DOMAINS = {Domain.GRID, Domain.PLANNING, Domain.WATER, Domain.ENVIRONMENT}
_CONSTRAINT_TERMS = (
    "prohibited",
    "not permitted",
    "cannot proceed",
    "no development",
    "incompatible with",
    "excluded from development",
)
_POLICY_INTERPRETATION_TERMS = ("policy interpretation", "policy says", "regulatory interpretation")


def _value(value: Any) -> str:
    return str(getattr(value, "value", value) or "")


def _unique(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _record_text(record: EvidenceRecord) -> str:
    value = record.value
    if isinstance(value, dict):
        value_text = " ".join(str(item) for item in value.values())
    else:
        value_text = str(value or "")
    return " ".join(
        part
        for part in (record.field_name, record.fact, record.finding, record.limitation, value_text)
        if part
    ).casefold()


def _is_unknown(record: EvidenceRecord) -> bool:
    return _value(record.evidence_state) in {
        AgentEvidenceState.UNKNOWN.value,
        AgentEvidenceState.NOT_PROVIDED.value,
    }


def _is_authoritative_policy(record: EvidenceRecord) -> bool:
    return (
        _value(record.created_by) == EvidenceCreatedBy.RAG_RETRIEVAL.value
        and _value(record.source_trust) == EvidenceSourceTrust.AUTHORITATIVE_POLICY.value
        and _value(record.source_class) in {SourceClass.PRIMARY.value, SourceClass.CURATED.value}
        and _value(record.document_status) == DocumentStatus.CURRENT.value
    )


def _is_deterministic(record: EvidenceRecord) -> bool:
    return (
        _value(record.created_by) == EvidenceCreatedBy.DETERMINISTIC_GIS.value
        or bool(record.deterministic)
        or _value(record.source_trust) == EvidenceSourceTrust.DETERMINISTIC_SOURCE.value
    )


def _is_project_document(record: EvidenceRecord) -> bool:
    return (
        _value(record.created_by) == EvidenceCreatedBy.PROJECT_DOCUMENT.value
        or _value(record.source_trust) == EvidenceSourceTrust.UNTRUSTED_PROJECT_DOCUMENT.value
    )


def _domain_for_text(text: str) -> Domain:
    lower = text.casefold()
    for domain in _DOMAIN_ORDER:
        if any(keyword in lower for keyword in _DOMAIN_KEYWORDS.get(domain, ())):
            return domain
    return Domain.GENERAL


def _domain_mentions(domain: Domain, text: str) -> bool:
    lower = text.casefold()
    return any(keyword in lower for keyword in _DOMAIN_KEYWORDS.get(domain, ()))


def _explicit_constraints(records: list[EvidenceRecord]) -> list[EvidenceRecord]:
    return [
        record
        for record in records
        if not _is_unknown(record)
        and (_is_authoritative_policy(record) or _is_deterministic(record))
        and any(term in _record_text(record) for term in _CONSTRAINT_TERMS)
    ]


def _has_no_intersection(record: EvidenceRecord) -> bool:
    text = _record_text(record)
    if re.search(r"\b(no|not|does not)\b[^.]{0,80}\bintersect", text):
        return True
    if isinstance(record.value, dict):
        return record.value.get("intersects") is False or record.value.get("project_point_intersects") is False
    return False


def _missing_for_domain(
    domain: Domain,
    records: list[EvidenceRecord],
    bundle_missing: Iterable[str],
    retrieval_gaps: Iterable[str],
) -> list[str]:
    missing: list[str] = []
    for record in records:
        if _is_unknown(record):
            missing.extend(record.missing_evidence)
            missing.append(f"{record.field_name} remains {_value(record.evidence_state)}")
    for item in [*bundle_missing, *retrieval_gaps]:
        if _domain_mentions(domain, str(item)):
            missing.append(str(item))
    if domain == Domain.GRID and any("mic" in _record_text(record) for record in records if _is_unknown(record)):
        missing.append("current MIC and connection-status evidence")
    if domain == Domain.PLANNING and any("zoning" in _record_text(record) for record in records if _is_unknown(record)):
        missing.append("usable site-specific zoning evidence")
    if domain == Domain.WATER and any("water" in _record_text(record) for record in records if _is_unknown(record)):
        missing.append("site-specific water/wastewater capacity or connection evidence")
    return _unique(missing)


def _review_role(domain: Domain) -> HumanReviewRole:
    if domain == Domain.PLANNING:
        return HumanReviewRole.PLANNING_CONSULTANT
    if domain == Domain.BIODIVERSITY:
        return HumanReviewRole.ECOLOGIST
    if domain == Domain.GRID:
        return HumanReviewRole.GRID_ENGINEER
    if domain in {Domain.ENVIRONMENT, Domain.WATER}:
        return HumanReviewRole.EIA_ENVIRONMENTAL_CONSULTANT
    if domain in {Domain.ENERGY, Domain.DATA_CENTRE_POLICY}:
        return HumanReviewRole.LEGAL_REGULATORY
    return HumanReviewRole.DEVELOPER


def _severity_value(value: Any) -> int:
    return {
        HumanReviewSeverity.INFORMATIONAL.value: 0,
        HumanReviewSeverity.MATERIAL.value: 1,
        HumanReviewSeverity.HIGH_CONSEQUENCE.value: 2,
    }.get(_value(value), 1)


class DeterministicAssessmentAgent:
    """Assess one existing EvidenceBundle without gathering new evidence."""

    def run(self, request: AssessmentRequest) -> AssessmentResult:
        context = request.project_context
        bundle = request.evidence_bundle
        if context.project_id != bundle.project_context.project_id:
            raise AssessmentAgentError(
                "AssessmentRequest project_context and evidence_bundle project IDs must match"
            )

        records_by_domain: dict[Domain, list[EvidenceRecord]] = defaultdict(list)
        for record in bundle.records:
            records_by_domain[Domain(_value(record.domain))].append(record)

        relevant_domains: list[Domain] = []
        for domain in _DOMAIN_ORDER:
            if records_by_domain.get(domain):
                relevant_domains.append(domain)
        for item in [*bundle.missing_evidence, *bundle.retrieval_gaps]:
            domain = _domain_for_text(str(item))
            if domain not in relevant_domains:
                relevant_domains.append(domain)
        for dependency in bundle.dependencies:
            domain = Domain(_value(dependency.to_domain))
            if domain not in relevant_domains:
                relevant_domains.append(domain)
        for contradiction in bundle.potential_contradictions:
            domain = Domain(_value(contradiction.domain))
            if domain not in relevant_domains:
                relevant_domains.append(domain)

        findings: list[AssessmentFinding] = []
        constraints: list[str] = []
        material_unknowns: list[str] = []
        warnings = list(bundle.warnings)
        warnings.append("Module 7 is a deterministic evidence assessment; it does not produce a final project decision.")

        def add_finding(
            domain: Domain,
            status: str,
            *,
            evidence_ids: Iterable[str] = (),
            dependency_ids: Iterable[str] = (),
            constraint: str | None = None,
            unknowns: Iterable[str] = (),
            impact: str | None = None,
            required_next: Iterable[str] = (),
            review: bool = False,
        ) -> AssessmentFinding:
            finding = AssessmentFinding(
                finding_id=f"assessment-{_value(domain).casefold()}-{len(findings) + 1}",
                domain=domain,
                status=status,
                constraint=constraint,
                dependency_ids=_unique(dependency_ids),
                evidence_ids=_unique(evidence_ids),
                material_unknowns=_unique(unknowns),
                decision_impact=impact,
                evidence_required_next=_unique(required_next),
                human_review_required=review,
            )
            findings.append(finding)
            if constraint:
                constraints.append(constraint)
            material_unknowns.extend(finding.material_unknowns)
            return finding

        # Contradictions and dependencies are first-class assessment inputs.
        for contradiction in bundle.potential_contradictions:
            add_finding(
                Domain(_value(contradiction.domain)),
                "CONDITIONAL",
                evidence_ids=contradiction.evidence_ids,
                unknowns=[contradiction.description],
                impact="The conflicting evidence remains unresolved and requires human comparison before relying on it.",
                required_next=["Resolve the conflicting evidence and confirm the current project position."],
                review=True,
            )
        for dependency in bundle.dependencies:
            if _value(dependency.status) in {"UNRESOLVED", "POTENTIAL", "UNKNOWN"}:
                add_finding(
                    Domain(_value(dependency.to_domain)),
                    "CONDITIONAL",
                    evidence_ids=dependency.evidence_ids,
                    dependency_ids=[dependency.dependency_id],
                    unknowns=[dependency.description],
                    impact=dependency.impact_description or dependency.description,
                    required_next=dependency.evidence_required_next,
                    review=dependency.human_review_required or Domain(_value(dependency.to_domain)) in _HIGH_CONSEQUENCE_DOMAINS,
                )

        for domain in relevant_domains:
            records = records_by_domain.get(domain, [])
            unknown_records = [record for record in records if _is_unknown(record)]
            missing = _missing_for_domain(domain, records, bundle.missing_evidence, bundle.retrieval_gaps)
            explicit = _explicit_constraints(records)
            domain_ids = [record.evidence_id for record in records]

            if explicit:
                constraint_text = "; ".join(_unique(record.finding or record.fact for record in explicit))
                add_finding(
                    domain,
                    "CONSTRAINED",
                    evidence_ids=[record.evidence_id for record in explicit],
                    constraint=constraint_text,
                    impact="Authoritative or deterministic evidence identifies an explicit constraint; specialist review remains required.",
                    review=True,
                )
                continue

            lower_text = " ".join(_record_text(record) for record in records)
            project_document_ids = [record.evidence_id for record in records if _is_project_document(record)]
            authoritative_ids = [record.evidence_id for record in records if _is_authoritative_policy(record)]

            if domain == Domain.GRID:
                contextual_ids = [
                    record.evidence_id
                    for record in records
                    if _is_deterministic(record)
                    and any(term in _record_text(record) for term in ("nearest", "asset", "capacity", "connection"))
                ]
                if contextual_ids:
                    add_finding(
                        domain,
                        "CONDITIONAL",
                        evidence_ids=contextual_ids,
                        impact="Contextual grid assets do not establish available capacity, a connection offer, secured MIC, or an energisation date.",
                        required_next=["Project-specific operator connection and energisation evidence."],
                        review=True,
                    )
                agreement_ids = [record.evidence_id for record in records if "agreement" in _record_text(record)]
                energisation_ids = [
                    record.evidence_id
                    for record in records
                    if "energisation" in _record_text(record) or "energization" in _record_text(record)
                ]
                if agreement_ids and not any(not _is_unknown(record) for record in records if record.evidence_id in energisation_ids):
                    add_finding(
                        domain,
                        "CONDITIONAL",
                        evidence_ids=[*agreement_ids, *energisation_ids],
                        impact="A connection agreement or feasibility statement does not establish energisation or a secured MIC.",
                        required_next=["Energisation evidence and confirmed project-specific connection status."],
                        review=True,
                    )
                if any(term in lower_text for term in ("proposed substation", "planned substation", "proposed connection")):
                    add_finding(
                        domain,
                        "CONDITIONAL",
                        evidence_ids=domain_ids,
                        impact="Proposed or planned infrastructure is not evidence that the asset is commissioned or operational.",
                        required_next=["Commissioning and operational-status evidence."],
                        review=True,
                    )

            if domain == Domain.WATER and "feasibility" in lower_text and not any(
                term in lower_text for term in ("connection agreement", "secured connection", "operational connection")
            ):
                add_finding(
                    domain,
                    "CONDITIONAL",
                    evidence_ids=domain_ids,
                    impact="Water or wastewater feasibility correspondence does not establish a secured, constructed, or operational connection.",
                    required_next=["Connection agreement, constructed-infrastructure, and operational-capacity evidence."],
                    review=True,
                )

            if domain == Domain.ENERGY and any(
                "planned_not_commissioned" in _record_text(record)
                or ("planned" in _record_text(record) and "renewable" in _record_text(record))
                for record in records
            ):
                add_finding(
                    domain,
                    "CONDITIONAL",
                    evidence_ids=domain_ids,
                    impact="A planned renewable asset is not evidence that the asset is commissioned or operational.",
                    required_next=["Renewable commissioning and operational evidence."],
                    review=True,
                )

            if domain in {Domain.BIODIVERSITY, Domain.ENVIRONMENT}:
                no_intersection_ids = [record.evidence_id for record in records if _has_no_intersection(record)]
                if no_intersection_ids:
                    add_finding(
                        domain,
                        "CONDITIONAL",
                        evidence_ids=no_intersection_ids,
                        impact="No intersection was recorded for the tested spatial layer only; this does not establish absence of wider environmental or ecological risk.",
                        required_next=["Specialist ecological/EIA/AA review where required by the project scope."],
                        review=True,
                    )

            policy_interpretation_ids = [
                record.evidence_id
                for record in records
                if _is_project_document(record) and any(term in _record_text(record) for term in _POLICY_INTERPRETATION_TERMS)
            ]
            if policy_interpretation_ids:
                add_finding(
                    domain,
                    "CONDITIONAL",
                    evidence_ids=[*policy_interpretation_ids, *authoritative_ids],
                    impact="Project-document policy interpretation is non-authoritative and cannot override current authoritative policy evidence.",
                    required_next=["Human verification against the cited current authoritative source."],
                    review=True,
                )

            if missing or unknown_records:
                unknown_ids = [record.evidence_id for record in unknown_records]
                add_finding(
                    domain,
                    "UNKNOWN",
                    evidence_ids=unknown_ids,
                    unknowns=missing or [f"{_value(domain)} evidence remains incomplete."],
                    impact="The available evidence is insufficient to establish this domain as resolved.",
                    required_next=missing,
                    review=domain in _HIGH_CONSEQUENCE_DOMAINS or bool(unknown_records),
                )
            elif records and not any(finding.domain == domain for finding in findings):
                if project_document_ids and not (authoritative_ids or any(_is_deterministic(record) for record in records)):
                    add_finding(
                        domain,
                        "CONDITIONAL",
                        evidence_ids=project_document_ids,
                        impact="Project-document evidence is retained as non-authoritative and requires verification before relying on it.",
                        required_next=["Independent authoritative or deterministic corroboration."],
                        review=True,
                    )
                elif domain in {Domain.GRID, Domain.PLANNING, Domain.WATER, Domain.BIODIVERSITY, Domain.ENVIRONMENT}:
                    add_finding(
                        domain,
                        "CONDITIONAL",
                        evidence_ids=domain_ids,
                        impact="Evidence is available for this domain, but it does not by itself establish complete project readiness or absence of risk.",
                        review=domain in _HIGH_CONSEQUENCE_DOMAINS,
                    )
                else:
                    add_finding(
                        domain,
                        "CLEAR",
                        evidence_ids=domain_ids,
                        impact="No explicit hard constraint was identified in the supplied evidence; this is not a final project decision.",
                        review=False,
                    )

        human_reviews = self._human_reviews(bundle.human_review_requests, findings, context.project_id)
        return AssessmentResult(
            project_context=context,
            findings=findings,
            constraints=_unique(constraints),
            dependencies=[dependency.model_copy(deep=True) for dependency in bundle.dependencies],
            material_unknowns=_unique(material_unknowns),
            human_reviews=human_reviews,
            warnings=_unique(warnings),
        )

    @staticmethod
    def _human_reviews(
        existing: list[HumanReviewRequest],
        findings: list[AssessmentFinding],
        project_id: str,
    ) -> list[HumanReviewRequest]:
        reviews: list[HumanReviewRequest] = []
        by_key: dict[tuple[str, str], HumanReviewRequest] = {}

        def add(
            domain: Domain,
            reason: str,
            evidence_ids: Iterable[str],
            severity: HumanReviewSeverity,
        ) -> None:
            key = (_value(domain), " ".join(reason.split()).casefold())
            current = by_key.get(key)
            if current is not None:
                current.evidence_ids = _unique([*current.evidence_ids, *evidence_ids])
                if _severity_value(severity) > _severity_value(current.severity):
                    current.severity = severity
                return
            review = HumanReviewRequest(
                review_id=f"assessment-review-{_value(domain).casefold()}-{len(reviews) + 1}",
                project_id=project_id,
                domain=domain,
                reason=reason,
                severity=severity,
                recommended_role=_review_role(domain),
                evidence_ids=_unique(evidence_ids),
                status="REQUIRED",
            )
            by_key[key] = review
            reviews.append(review)

        for review in existing:
            key = (_value(review.domain), " ".join(review.reason.split()).casefold())
            existing_copy = review.model_copy(deep=True)
            current = by_key.get(key)
            if current is None:
                by_key[key] = existing_copy
                reviews.append(existing_copy)
            else:
                current.evidence_ids = _unique([*current.evidence_ids, *review.evidence_ids])
                if _severity_value(review.severity) > _severity_value(current.severity):
                    current.severity = review.severity
        for finding in findings:
            if not finding.human_review_required:
                continue
            severity = (
                HumanReviewSeverity.HIGH_CONSEQUENCE
                if _value(finding.status) == "CONSTRAINED"
                or _value(finding.domain) in {_value(domain) for domain in _HIGH_CONSEQUENCE_DOMAINS}
                and _value(finding.status) == "CONDITIONAL"
                else HumanReviewSeverity.MATERIAL
            )
            reason = finding.decision_impact or "Review the material assessment finding and its evidence."
            add(Domain(_value(finding.domain)), reason, finding.evidence_ids, severity)
        return reviews


__all__ = ["AssessmentAgentError", "DeterministicAssessmentAgent"]
