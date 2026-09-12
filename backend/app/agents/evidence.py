"""Deterministic Evidence Agent orchestration for INTERLOCK Module 6.

The agent assembles provenance-preserving evidence from the existing Module 2,
3, 4B, and 5B services. It deliberately contains no LLM calls and produces no
assessment, score, recommendation, or investment decision.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from time import perf_counter
from typing import Any, Callable, Iterable

from pydantic import ValidationError

from ..schemas.agents import (
    AgentEvidenceState,
    DependencyRecord,
    EvidenceBundle,
    EvidenceCreatedBy,
    EvidenceSourceTrust,
    EvidenceRecord,
    HumanReviewRequest,
    HumanReviewRole,
    ProjectContext,
    PotentialContradiction,
    InvestigationPlan,
)
from ..schemas.agents.common import HumanReviewSeverity
from ..schemas.evidence import (
    EvidenceCategory,
    EvidenceConfidence,
    EvidenceLedger,
    EvidenceReviewStatus,
    EvidenceSourceType,
    EvidenceState,
)
from ..schemas.project import ProjectInput
from ..schemas.site_evidence import SiteEvidenceResponse
from ..services.evidence import project_input_to_evidence_ledger
from ..services.project_evidence import ProjectEvidenceChunk, ProjectEvidenceFact, ProjectEvidenceRetriever
from ..services.rag.models import (
    CitationReference,
    DocumentStatus,
    Domain,
    Jurisdiction,
    RetrievalRequest,
    SourceClass,
    Workflow,
)
from ..services.rag.retrieval import (
    IndexNotBuiltError,
    LoadedRetrievalIndex,
    StaleIndexError,
    load_retrieval_index,
    search_index,
)
from ..services.site_evidence import evaluate_site


class EvidenceAgentError(RuntimeError):
    """Controlled error for invalid Evidence Agent configuration or input."""


@dataclass(frozen=True)
class EvidenceAgentOptions:
    """Explicit switches for optional project-document evidence."""

    include_project_documents: bool = True
    include_benchmark_documents: bool = False
    project_evidence_root: Path | None = None
    project_document_query: str = (
        "project description planning engineering power energy grid water utility connection feasibility"
    )
    # Planning is advisory scope/provenance.  The concrete Evidence Agent
    # still owns every deterministic capability and its existing filters.
    investigation_plan: InvestigationPlan | None = None


@dataclass(frozen=True)
class RetrievalQueryTemplate:
    """One deterministic, testable policy-retrieval question template."""

    domain: Domain
    template: str


DEFAULT_RETRIEVAL_QUERY_TEMPLATES: tuple[RetrievalQueryTemplate, ...] = (
    RetrievalQueryTemplate(
        Domain.GRID,
        "What current grid connection requirements apply to a {project_type} "
        "with planned power {planned_power_mw} MW and requested MIC {requested_mic_mva} "
        "in {country}?",
    ),
    RetrievalQueryTemplate(
        Domain.ENERGY,
        "What current renewable, dispatchable energy, and energy-strategy "
        "requirements may apply to this {project_type} in {country}?",
    ),
    RetrievalQueryTemplate(
        Domain.PLANNING,
        "What current planning policy sources apply to this {project_type} at "
        "{address} in {local_authority}?",
    ),
    RetrievalQueryTemplate(
        Domain.BIODIVERSITY,
        "What current biodiversity and protected-site policy sources apply to "
        "this project at {address} in {country}?",
    ),
    RetrievalQueryTemplate(
        Domain.ENVIRONMENT,
        "What current environmental assessment policy sources may apply to this "
        "{project_type} in {country}?",
    ),
    RetrievalQueryTemplate(
        Domain.WATER,
        "What current water and wastewater policy sources may apply to this "
        "{project_type} at {address} in {country}?",
    ),
    RetrievalQueryTemplate(
        Domain.DATA_CENTRE_POLICY,
        "What current data-centre policy sources apply to this project in {country}?",
    ),
)

_SITE_DOMAIN_PREFIXES: tuple[tuple[str, Domain], ...] = (
    ("biodiversity", Domain.BIODIVERSITY),
    ("flood", Domain.ENVIRONMENT),
    ("planning", Domain.PLANNING),
    ("heritage", Domain.PLANNING),
    ("ground", Domain.ENVIRONMENT),
    ("grid", Domain.GRID),
    ("zoning", Domain.PLANNING),
    ("water", Domain.WATER),
    ("site", Domain.GENERAL),
)

_MISSING_LABELS = {
    "requested_mic_mva": "MIC not provided",
    "power_strategy": "power strategy not provided or marked Unknown",
    "energy_strategy": "energy strategy not provided",
    "site_address": "site address not provided",
    "latitude": "site latitude not provided",
    "longitude": "site longitude not provided",
}

_STRUCTURED_EVIDENCE_KEYS = ("evidence_records", "project_evidence", "uploaded_evidence")
_SCOPE_FIELD_NAMES = {
    "project_scope",
    "project_configuration",
    "planned_power_demand_mw",
    "planned_power_mw",
    "planned_load_mw",
    "capacity_mw",
}

_ABSOLUTE_PATH_RE = re.compile(r"(?i)[a-z]:[\\/][^\r\n;]+")


def _enum_value(value: Any) -> str | None:
    if value is None:
        return None
    return str(getattr(value, "value", value))


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _safe_text(value: Any) -> str:
    """Keep diagnostics useful without exposing host filesystem paths."""

    text = str(value)
    if "Processed dataset registry" in text or "Processed registry output" in text:
        return text.split(":", 1)[0] + ": <path unavailable>"
    return _ABSOLUTE_PATH_RE.sub("<path>", text)


def _project_input_from_context(context: ProjectContext) -> ProjectInput:
    """Adapt the canonical context to existing Module 2 services."""

    if context.source_project_input is not None:
        return context.source_project_input.model_copy(deep=True)

    return ProjectInput(
        project_name=context.project_name,
        development_type=context.project_type,
        project_stage=context.project_stage or "Unknown",
        site_address=context.location.address,
        latitude=context.location.latitude,
        longitude=context.location.longitude,
        site_area_hectares=(
            context.site_boundary.area_hectares if context.site_boundary else None
        ),
        planned_power_demand_mw=context.planned_power_mw,
        requested_mic_mva=context.requested_mic_mva,
        power_strategy=context.power_strategy or "Unknown",
        energy_strategy=context.energy_strategy,
        project_phasing_notes=context.phasing,
    )


def _domain_for_field(field_name: str) -> Domain:
    lower = field_name.casefold()
    for prefix, domain in _SITE_DOMAIN_PREFIXES:
        if lower.startswith(prefix):
            return domain
    if lower in {"planned_power_demand_mw", "requested_mic_mva", "power_strategy", "energy_strategy"}:
        return Domain.ENERGY
    return Domain.GENERAL


def _category_for_domain(domain: Domain) -> EvidenceCategory:
    if domain in {Domain.GRID, Domain.ENERGY}:
        return EvidenceCategory.POWER_AND_ENERGY
    if domain in {Domain.PLANNING, Domain.BIODIVERSITY, Domain.ENVIRONMENT, Domain.WATER}:
        return EvidenceCategory.SITE
    return EvidenceCategory.OTHER


def _agent_state(value: Any, *, deterministic: bool = False) -> AgentEvidenceState:
    raw = _enum_value(value) or AgentEvidenceState.UNKNOWN.value
    if raw == EvidenceState.PROVIDED.value and deterministic:
        return AgentEvidenceState.FACT
    if raw in {item.value for item in AgentEvidenceState}:
        return AgentEvidenceState(raw)
    if raw == "ASSUMPTION":
        return AgentEvidenceState.PROVIDED
    if raw == "MISSING_EVIDENCE":
        return AgentEvidenceState.NOT_PROVIDED
    return AgentEvidenceState.UNKNOWN


def _created_by_for_source(source_type: Any) -> tuple[EvidenceCreatedBy, bool]:
    source_value = _enum_value(source_type)
    if source_value == EvidenceSourceType.DETERMINISTIC_CALCULATION.value:
        return EvidenceCreatedBy.DETERMINISTIC_GIS, True
    if source_value == EvidenceSourceType.CUSTOMER_INPUT.value:
        return EvidenceCreatedBy.DEVELOPER_INPUT, False
    if source_value == EvidenceSourceType.HUMAN_REVIEW.value:
        return EvidenceCreatedBy.HUMAN_REVIEW, False
    if source_value == EvidenceSourceType.CUSTOMER_DOCUMENT.value:
        return EvidenceCreatedBy.PROJECT_DOCUMENT, False
    return EvidenceCreatedBy.UNKNOWN, False


def _source_trust_for_record(
    created_by: EvidenceCreatedBy,
    *,
    source_class: SourceClass | None = None,
) -> EvidenceSourceTrust:
    if created_by == EvidenceCreatedBy.RAG_RETRIEVAL:
        if source_class in {SourceClass.PRIMARY, SourceClass.CURATED}:
            return EvidenceSourceTrust.AUTHORITATIVE_POLICY
        return EvidenceSourceTrust.SUPPORTING_SOURCE
    if created_by == EvidenceCreatedBy.DETERMINISTIC_GIS:
        return EvidenceSourceTrust.DETERMINISTIC_SOURCE
    if created_by == EvidenceCreatedBy.DEVELOPER_INPUT:
        return EvidenceSourceTrust.UNVERIFIED_DEVELOPER_INPUT
    if created_by == EvidenceCreatedBy.PROJECT_DOCUMENT:
        return EvidenceSourceTrust.UNTRUSTED_PROJECT_DOCUMENT
    return EvidenceSourceTrust.UNKNOWN


def _confidence(value: Any) -> EvidenceConfidence:
    raw = _enum_value(value) or EvidenceConfidence.UNKNOWN.value
    try:
        return EvidenceConfidence(raw)
    except ValueError:
        return EvidenceConfidence.UNKNOWN


def _review_status(value: Any) -> EvidenceReviewStatus:
    raw = _enum_value(value) or EvidenceReviewStatus.UNREVIEWED.value
    try:
        return EvidenceReviewStatus(raw)
    except ValueError:
        return EvidenceReviewStatus.UNREVIEWED


def _convert_ledger_entry(
    entry: Any,
    context: ProjectContext,
    *,
    created_by: EvidenceCreatedBy | None = None,
    deterministic: bool | None = None,
    source_document_id: str | None = None,
    citation: CitationReference | None = None,
    source_class: SourceClass | None = None,
    authority_class: SourceClass | None = None,
    document_status: DocumentStatus | None = None,
    jurisdiction: Jurisdiction | None = None,
    finding: str | None = None,
    domain: Domain | None = None,
) -> EvidenceRecord:
    inferred_created_by, inferred_deterministic = _created_by_for_source(entry.source_type)
    selected_created_by = created_by or inferred_created_by
    selected_deterministic = (
        inferred_deterministic if deterministic is None else deterministic
    )
    selected_domain = domain or _domain_for_field(entry.field_name)
    return EvidenceRecord(
        evidence_id=entry.evidence_id,
        project_id=context.project_id,
        domain=selected_domain,
        category=entry.category,
        field_name=entry.field_name,
        fact=entry.fact,
        finding=finding or entry.fact,
        value=entry.value,
        unit=entry.unit,
        evidence_state=_agent_state(entry.evidence_state, deterministic=selected_deterministic),
        source=entry.source_name,
        source_type=entry.source_type,
        source_name=entry.source_name,
        source_reference=entry.source_reference,
        source_date=entry.checked_at.date().isoformat() if entry.checked_at else None,
        source_document_id=source_document_id,
        citation=citation,
        source_class=source_class,
        authority_class=authority_class,
        document_status=document_status,
        jurisdiction=jurisdiction,
        confidence=_confidence(entry.confidence),
        verification_status=_review_status(entry.review_status).value,
        limitation=_safe_text(entry.limitation) if entry.limitation else None,
        review_status=_review_status(entry.review_status),
        checked_at=entry.checked_at,
        created_by=selected_created_by,
        deterministic=selected_deterministic,
        source_trust=_source_trust_for_record(selected_created_by, source_class=source_class),
    )


def _structured_project_records(
    context: ProjectContext,
    checked_at: datetime,
) -> tuple[list[EvidenceRecord], list[str]]:
    """Convert already-structured project-document evidence, without extraction."""

    raw_items: list[dict[str, Any]] = []
    for key in _STRUCTURED_EVIDENCE_KEYS:
        value = context.developer_inputs.get(key)
        if isinstance(value, list):
            raw_items.extend(item for item in value if isinstance(item, dict))

    records: list[EvidenceRecord] = []
    warnings: list[str] = []
    for index, item in enumerate(raw_items):
        try:
            source_type = EvidenceSourceType(item.get("source_type", EvidenceSourceType.CUSTOMER_DOCUMENT.value))
            category = EvidenceCategory(item.get("category", EvidenceCategory.OTHER.value))
            state = item.get("evidence_state", item.get("state", AgentEvidenceState.PROVIDED.value))
            state_value = _agent_state(state)
            if state == "ASSUMPTION":
                state_value = AgentEvidenceState.PROVIDED
            if state == "MISSING_EVIDENCE":
                state_value = AgentEvidenceState.NOT_PROVIDED
            created_by = EvidenceCreatedBy(item.get("created_by", EvidenceCreatedBy.PROJECT_DOCUMENT.value))
            citation = (
                CitationReference.model_validate(item["citation"])
                if isinstance(item.get("citation"), dict)
                else None
            )
            checked_value = item.get("checked_at") or checked_at
            record = EvidenceRecord(
                evidence_id=str(item.get("evidence_id") or f"project-structured-{index + 1}"),
                project_id=context.project_id,
                domain=Domain(item.get("domain", Domain.GENERAL.value)),
                category=category,
                field_name=str(item.get("field_name") or "project_document_evidence"),
                fact=str(item.get("fact") or item.get("finding") or "Structured project evidence"),
                finding=str(item.get("finding") or item.get("fact") or "Structured project evidence"),
                value=item.get("value"),
                unit=item.get("unit"),
                evidence_state=state_value,
                source=str(item.get("source") or item.get("source_name") or "Project document"),
                source_type=source_type,
                source_name=str(item.get("source_name") or item.get("source") or "Project document"),
                source_reference=item.get("source_reference"),
                source_date=item.get("source_date"),
                source_document_id=item.get("source_document_id"),
                citation=citation,
                source_class=(SourceClass(item["source_class"]) if item.get("source_class") else None),
                authority_class=(SourceClass(item["authority_class"]) if item.get("authority_class") else None),
                document_status=(DocumentStatus(item["document_status"]) if item.get("document_status") else None),
                jurisdiction=(Jurisdiction(item["jurisdiction"]) if item.get("jurisdiction") else None),
                confidence=_confidence(item.get("confidence")),
                verification_status=str(item.get("verification_status") or "UNVERIFIED"),
                limitation=item.get("limitation"),
                review_status=_review_status(item.get("review_status")),
                checked_at=checked_value,
                assumption=item.get("assumption") or (str(item.get("assumption_text")) if item.get("assumption_text") else None),
                missing_evidence=list(item.get("missing_evidence") or []),
                dependency_ids=list(item.get("dependency_ids") or []),
                contradiction_ids=list(item.get("contradiction_ids") or []),
                human_review_required=bool(item.get("human_review_required", False)),
                human_review_role=HumanReviewRole(item.get("human_review_role", HumanReviewRole.UNKNOWN.value)),
                created_by=created_by,
                deterministic=bool(item.get("deterministic", False)),
                source_trust=EvidenceSourceTrust(item.get("source_trust", EvidenceSourceTrust.UNKNOWN.value)),
            )
            records.append(record)
        except (KeyError, TypeError, ValueError, ValidationError) as exc:
            warnings.append(f"Structured project evidence item {index + 1} was ignored: invalid provenance")
            _ = exc
    return records, warnings


def _format_context_value(value: Any, fallback: str = "unknown/not provided") -> str:
    text = _enum_value(value)
    return text if text not in {None, ""} else fallback


def build_retrieval_requests(
    context: ProjectContext,
    templates: Iterable[RetrievalQueryTemplate] = DEFAULT_RETRIEVAL_QUERY_TEMPLATES,
) -> list[RetrievalRequest]:
    """Build the small deterministic policy-query plan for one project."""

    location = context.location
    values = {
        "project_type": _format_context_value(context.project_type),
        "planned_power_mw": _format_context_value(context.planned_power_mw),
        "requested_mic_mva": _format_context_value(context.requested_mic_mva),
        "country": _format_context_value(location.country),
        "address": _format_context_value(location.address),
        "local_authority": _format_context_value(location.local_authority),
    }
    workflow = context.assessment_workflow or Workflow.POLICY_REGULATORY_INTELLIGENCE
    jurisdiction = _enum_value(location.jurisdiction)
    if jurisdiction == Jurisdiction.UNKNOWN.value:
        jurisdiction = None
    project_context = {
        "project_id": context.project_id,
        "project_type": context.project_type,
        "planned_power_mw": context.planned_power_mw,
        "requested_mic_mva": context.requested_mic_mva,
        "local_authority": location.local_authority,
        "country": location.country,
    }
    return [
        RetrievalRequest(
            query=template.template.format(**values),
            workflow=workflow,
            domains=[template.domain],
            jurisdiction=jurisdiction,
            jurisdiction_detail=location.local_authority,
            local_authority=location.local_authority,
            include_historical=False,
            include_supporting=True,
            top_k=5,
            primary_limit=5,
            supporting_limit=3,
            project_context=project_context,
        )
        for template in templates
    ]


def _hit_record_key(hit: dict[str, Any]) -> tuple[Any, ...]:
    record_id = hit.get("chunk_id") or hit.get("curated_record_id") or hit.get("record_id")
    finding = " ".join(str(hit.get("text") or "").split())
    return (
        hit.get("document_id"),
        hit.get("page_start"),
        hit.get("page_end"),
        record_id,
        finding,
    )


def _policy_hit_allowed(hit: dict[str, Any], context: ProjectContext) -> bool:
    status = str(hit.get("document_status") or DocumentStatus.UNKNOWN.value)
    if status in {
        DocumentStatus.PROPOSED.value,
        DocumentStatus.HISTORICAL.value,
        DocumentStatus.SUPERSEDED.value,
    }:
        return False
    source_class = str(hit.get("source_class") or SourceClass.UNKNOWN.value)
    if source_class in {SourceClass.ARCHIVE.value, SourceClass.RESTRICTED.value, SourceClass.GOVERNANCE.value}:
        return False
    local_authority = context.location.local_authority
    if local_authority and str(hit.get("jurisdiction") or "") == Jurisdiction.LOCAL_AUTHORITY.value:
        return str(hit.get("jurisdiction_detail") or "").casefold() == local_authority.casefold()
    return True


_LOCAL_AUTHORITY_GAP_DOMAINS = frozenset({Domain.PLANNING, Domain.WATER})


def _policy_gap_allowed(gap: Any, domain: Domain, context: ProjectContext) -> bool:
    """Keep only local-scope gaps that are material to the requested domain.

    Module 5B still applies its unchanged jurisdiction filters.  This guard
    prevents its generic local-authority diagnostic from becoming a false
    gap for domains normally satisfied by national/EU or NPWS evidence.
    """

    if not isinstance(gap, dict):
        return True
    if gap.get("type") != "NO_AUTHORITATIVE_LOCAL_SOURCE":
        return True
    if not context.location.local_authority:
        return False
    return domain in _LOCAL_AUTHORITY_GAP_DOMAINS


def _role_for_domain(domain: Domain) -> HumanReviewRole:
    if domain == Domain.PLANNING:
        return HumanReviewRole.PLANNING_CONSULTANT
    if domain == Domain.BIODIVERSITY:
        return HumanReviewRole.ECOLOGIST
    if domain == Domain.GRID:
        return HumanReviewRole.GRID_ENGINEER
    if domain in {Domain.ENVIRONMENT, Domain.WATER}:
        return HumanReviewRole.EIA_ENVIRONMENTAL_CONSULTANT
    if domain in {Domain.DATA_CENTRE_POLICY, Domain.ENERGY}:
        return HumanReviewRole.LEGAL_REGULATORY
    return HumanReviewRole.UNKNOWN


def _policy_record(
    hit: dict[str, Any],
    context: ProjectContext,
    domain: Domain,
    checked_at: datetime,
) -> EvidenceRecord:
    source_class = SourceClass(str(hit.get("source_class") or SourceClass.UNKNOWN.value))
    document_status = DocumentStatus(str(hit.get("document_status") or DocumentStatus.UNKNOWN.value))
    jurisdiction = Jurisdiction(str(hit.get("jurisdiction") or Jurisdiction.UNKNOWN.value))
    document_id = hit.get("document_id")
    record_id = hit.get("chunk_id") or hit.get("curated_record_id") or hit.get("record_id")
    text = str(hit.get("text") or "")
    title = str(hit.get("title") or document_id or "Retrieved policy source")
    issuer = str(hit.get("issuer") or "").strip()
    source_name = f"{issuer} — {title}" if issuer else title
    source_path = str(hit.get("source_path") or "")
    page_start = hit.get("page_start")
    page_end = hit.get("page_end")
    citation_text = str(hit.get("citation") or f"record={record_id}")
    citation = CitationReference(
        document_id=str(document_id or "unknown-document"),
        source_path=source_path,
        page_start=page_start,
        page_end=page_end,
        section_heading=hit.get("section_heading"),
        locator=citation_text,
    )
    supporting = source_class not in {SourceClass.PRIMARY, SourceClass.CURATED}
    limitation = "Supporting evidence; it is not a primary authority." if supporting else None
    if document_status != DocumentStatus.CURRENT:
        limitation = "Policy version is not current; excluded from normal current-policy evidence."
    return EvidenceRecord(
        evidence_id=f"rag-{record_id}",
        project_id=context.project_id,
        domain=domain,
        category=_category_for_domain(domain),
        field_name=f"policy.{domain.value.casefold()}",
        fact=text or f"Retrieved evidence from {title}",
        finding=text or f"Retrieved evidence from {title}",
        value={
            "record_id": record_id,
            "chunk_id": hit.get("chunk_id"),
            "curated_record_id": hit.get("curated_record_id"),
            "title": title,
            "text": text,
        },
        source=source_name,
        source_type=EvidenceSourceType.POLICY_DOCUMENT,
        source_name=source_name,
        source_reference=f"{_safe_text(source_path)}::{record_id}" if source_path else str(record_id),
        source_date=hit.get("effective_date") or hit.get("publication_date"),
        source_document_id=document_id,
        citation=citation,
        source_class=source_class,
        authority_class=source_class,
        document_status=document_status,
        jurisdiction=jurisdiction,
        evidence_state=AgentEvidenceState.PROVIDED,
        confidence=(EvidenceConfidence.HIGH if source_class == SourceClass.PRIMARY else EvidenceConfidence.MEDIUM),
        verification_status=str(hit.get("verification_status") or "UNVERIFIED"),
        limitation=_safe_text(limitation) if limitation else None,
        review_status=EvidenceReviewStatus.UNREVIEWED,
        checked_at=checked_at,
        human_review_required=bool(hit.get("requires_human_review", False)),
        human_review_role=_role_for_domain(domain),
        created_by=EvidenceCreatedBy.RAG_RETRIEVAL,
        deterministic=False,
        source_trust=_source_trust_for_record(EvidenceCreatedBy.RAG_RETRIEVAL, source_class=source_class),
    )


def _project_record_base(
    *,
    evidence_id: str,
    context: ProjectContext,
    domain: Domain,
    field_name: str,
    fact: str,
    value: Any,
    source_document_id: str,
    source_reference: str,
    source_name: str,
    source_url: str,
    citation: CitationReference,
    evidence_state: AgentEvidenceState,
    checked_at: datetime,
) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=evidence_id,
        project_id=context.project_id,
        domain=domain,
        category=_category_for_domain(domain),
        field_name=field_name,
        fact=fact,
        finding=fact,
        value=value,
        source="PROJECT DOCUMENT",
        source_type=EvidenceSourceType.CUSTOMER_DOCUMENT,
        source_name=source_name,
        source_reference=f"{_safe_text(source_url)}::{source_reference}",
        source_document_id=source_document_id,
        citation=citation,
        source_class=SourceClass.UNKNOWN,
        authority_class=SourceClass.UNKNOWN,
        document_status=DocumentStatus.SUPPORTING,
        jurisdiction=Jurisdiction.UNKNOWN,
        evidence_state=evidence_state,
        confidence=EvidenceConfidence.UNKNOWN,
        verification_status="UNVERIFIED_PROJECT_DOCUMENT",
        limitation="Untrusted project-document evidence; not authoritative policy. Human verification required.",
        review_status=EvidenceReviewStatus.UNREVIEWED,
        checked_at=checked_at,
        human_review_required=True,
        human_review_role=_role_for_domain(domain),
        created_by=EvidenceCreatedBy.PROJECT_DOCUMENT,
        deterministic=False,
        source_trust=EvidenceSourceTrust.UNTRUSTED_PROJECT_DOCUMENT,
    )


def _project_fact_record(
    fact: ProjectEvidenceFact,
    context: ProjectContext,
    checked_at: datetime,
) -> EvidenceRecord:
    value = {
        "value": fact.value,
        "status": _enum_value(fact.status),
        "benchmark_only": fact.benchmark_only,
    }
    fact_text = f"{fact.field_name}: {json.dumps(value, sort_keys=True, default=str)}"
    fact_domain = Domain.GENERAL
    lower_field = fact.field_name.casefold()
    if "grid" in lower_field:
        fact_domain = Domain.GRID
    elif "renewable" in lower_field or "power" in lower_field or "mic" in lower_field:
        fact_domain = Domain.ENERGY
    elif "water" in lower_field or "utility" in lower_field or "feasibility" in lower_field:
        fact_domain = Domain.WATER
    elif "area" in lower_field:
        fact_domain = Domain.PLANNING
    return _project_record_base(
        evidence_id=f"project-fact-{fact.fact_id}",
        context=context,
        domain=fact_domain,
        field_name=f"project.{fact.field_name}",
        fact=fact_text,
        value=value,
        source_document_id=fact.project_document_id,
        source_reference=fact.citation.locator,
        source_name=f"PROJECT DOCUMENT — {fact.project_document_id}",
        source_url=fact.source_url,
        citation=fact.citation,
        evidence_state=AgentEvidenceState.PROVIDED if fact.value is not None else AgentEvidenceState.UNKNOWN,
        checked_at=checked_at,
    )


def _project_chunk_record(
    chunk: ProjectEvidenceChunk,
    context: ProjectContext,
    checked_at: datetime,
) -> EvidenceRecord:
    value = {
        "text": chunk.text,
        "benchmark_only": chunk.benchmark_only,
        "document_type": chunk.document_type,
    }
    chunk_domain = Domain(_enum_value(chunk.domain) or Domain.UNKNOWN.value)
    return _project_record_base(
        evidence_id=f"project-chunk-{chunk.chunk_id}",
        context=context,
        domain=chunk_domain,
        field_name=f"project_document.{chunk_domain.value.casefold()}",
        fact=chunk.text,
        value=value,
        source_document_id=chunk.project_document_id,
        source_reference=chunk.citation.locator,
        source_name=f"PROJECT DOCUMENT — {chunk.project_document_id}",
        source_url=chunk.source_url,
        citation=chunk.citation,
        evidence_state=AgentEvidenceState.PROVIDED,
        checked_at=checked_at,
    )


def _normalise_source_entries(entries: Iterable[EvidenceRecord]) -> list[EvidenceRecord]:
    return list(entries)


def _missing_item_for_record(record: EvidenceRecord) -> str | None:
    if record.evidence_state not in {AgentEvidenceState.UNKNOWN, AgentEvidenceState.NOT_PROVIDED}:
        return None
    if record.field_name in _MISSING_LABELS:
        return _MISSING_LABELS[record.field_name]
    return (
        f"{_enum_value(record.domain) or Domain.UNKNOWN.value}: "
        f"{record.field_name} is {_enum_value(record.evidence_state) or AgentEvidenceState.UNKNOWN.value}"
    )


def _structured_missing_items(records: list[EvidenceRecord]) -> list[str]:
    fields = {record.field_name.casefold() for record in records}
    values = " ".join(
        str(record.value or "").casefold() for record in records
    )
    missing: list[str] = []
    if any("grid_connection_agreement" in field for field in fields) and not any(
        "energisation" in field for field in fields
    ):
        missing.append("energisation evidence unavailable")
    if any("renewable" in field or "renewable" in value for field in fields for value in [field]) and not any(
        "commission" in field for field in fields
    ):
        missing.append("renewable asset commissioning evidence unavailable")
    if any("planned_not_commissioned" in str(record.value).casefold() for record in records):
        missing.append("planned renewable asset not proven commissioned")
    return missing


def _build_contradictions(
    records: list[EvidenceRecord],
    project_id: str,
) -> list[PotentialContradiction]:
    grouped: dict[str, list[EvidenceRecord]] = defaultdict(list)
    for record in records:
        field_name = record.field_name.casefold()
        if field_name in _SCOPE_FIELD_NAMES or "scope" in field_name or "configuration" in field_name:
            if record.value is not None and record.evidence_state not in {
                AgentEvidenceState.UNKNOWN,
                AgentEvidenceState.NOT_PROVIDED,
            }:
                grouped[field_name].append(record)

    contradictions: list[PotentialContradiction] = []
    for field_name, field_records in grouped.items():
        values = {json.dumps(record.value, sort_keys=True, default=str) for record in field_records}
        if len(values) < 2:
            continue
        evidence_ids = [record.evidence_id for record in field_records]
        source_document_ids = [
            record.source_document_id
            for record in field_records
            if record.source_document_id
        ]
        domain = field_records[0].domain
        contradictions.append(
            PotentialContradiction(
                contradiction_id=f"contradiction-scope-{field_name}",
                project_id=project_id,
                domain=domain,
                evidence_ids=evidence_ids,
                source_document_ids=list(dict.fromkeys(source_document_ids)),
                type="PROJECT_SCOPE_MISMATCH",
                description=(
                    f"Distinct evidence values were supplied for {field_name}; "
                    "the Evidence Agent preserves both and does not resolve the mismatch."
                ),
                requires_human_review=True,
            )
        )
    return contradictions


def _build_dependencies(
    records: list[EvidenceRecord],
    missing: list[str],
    project_id: str,
) -> list[DependencyRecord]:
    dependencies: list[DependencyRecord] = []
    field_names = {record.field_name.casefold() for record in records}
    agreement_records = [
        record for record in records if "grid_connection_agreement" in record.field_name.casefold()
    ]
    energisation_records = [
        record for record in records if "energisation" in record.field_name.casefold()
    ]
    if agreement_records and (not energisation_records or "energisation evidence unavailable" in missing):
        dependencies.append(
            DependencyRecord(
                dependency_id="dependency-grid-agreement-energisation",
                project_id=project_id,
                from_domain=Domain.GRID,
                to_domain=Domain.GRID,
                description="Grid readiness depends on evidence of energisation; an agreement is not energisation proof.",
                status="UNRESOLVED",
                evidence_ids=[record.evidence_id for record in agreement_records],
                impact_description="The current energisation state cannot be established from the supplied agreement alone.",
                evidence_required_next=["energisation evidence"],
                human_review_required=True,
            )
        )
    planned_records = [
        record
        for record in records
        if "renewable" in record.field_name.casefold()
        or "planned_not_commissioned" in str(record.value).casefold()
    ]
    if planned_records and (
        "planned renewable asset not proven commissioned" in missing
        or "renewable asset commissioning evidence unavailable" in missing
    ):
        dependencies.append(
            DependencyRecord(
                dependency_id="dependency-renewable-commissioning",
                project_id=project_id,
                from_domain=Domain.ENERGY,
                to_domain=Domain.ENERGY,
                description="The energy strategy depends on the status of the planned renewable asset.",
                status="UNRESOLVED",
                evidence_ids=[record.evidence_id for record in planned_records],
                impact_description="Planning status is not evidence that the asset has been commissioned.",
                evidence_required_next=["renewable asset commissioning evidence"],
                human_review_required=True,
            )
        )
    _ = field_names
    return dependencies


def _build_review_requests(
    records: list[EvidenceRecord],
    dependencies: list[DependencyRecord],
    contradictions: list[PotentialContradiction],
    missing: list[str],
    project_id: str,
) -> list[HumanReviewRequest]:
    requests: list[HumanReviewRequest] = []
    seen: dict[tuple[str, str], HumanReviewRequest] = {}

    def add(domain: Domain, reason: str, evidence_ids: list[str], severity: HumanReviewSeverity) -> None:
        normalised_reason = " ".join(str(reason).split()).casefold()
        key = (_enum_value(domain) or Domain.UNKNOWN.value, normalised_reason)
        existing = seen.get(key)
        if existing is not None:
            existing.evidence_ids = list(dict.fromkeys([*existing.evidence_ids, *evidence_ids]))
            if severity == HumanReviewSeverity.HIGH_CONSEQUENCE:
                existing.severity = HumanReviewSeverity.HIGH_CONSEQUENCE
            return
        review = HumanReviewRequest(
            review_id=f"review-{(_enum_value(domain) or Domain.UNKNOWN.value).casefold()}-{len(requests) + 1}",
            project_id=project_id,
            domain=domain,
            reason=reason,
            severity=severity,
            recommended_role=_role_for_domain(domain),
            evidence_ids=list(dict.fromkeys(evidence_ids)),
            status="REQUIRED",
        )
        seen[key] = review
        requests.append(review)

    for contradiction in contradictions:
        add(
            contradiction.domain,
            contradiction.description,
            contradiction.evidence_ids,
            HumanReviewSeverity.HIGH_CONSEQUENCE,
        )
    for dependency in dependencies:
        add(
            dependency.to_domain,
            dependency.description,
            dependency.evidence_ids,
            HumanReviewSeverity.MATERIAL,
        )
    for record in records:
        if record.evidence_state == AgentEvidenceState.UNKNOWN or record.human_review_required:
            add(
                record.domain,
                record.limitation or record.finding or f"Review {record.field_name} evidence.",
                [record.evidence_id],
                HumanReviewSeverity.MATERIAL,
            )
    for item in missing:
        lower = item.casefold()
        if "grid" in lower or "mic" in lower or "energisation" in lower:
            add(Domain.GRID, item, [], HumanReviewSeverity.HIGH_CONSEQUENCE)
        elif "planning" in lower or "local" in lower:
            add(Domain.PLANNING, item, [], HumanReviewSeverity.MATERIAL)
        elif "renewable" in lower or "energy" in lower:
            add(Domain.ENERGY, item, [], HumanReviewSeverity.MATERIAL)
    return requests


def _annotate_records(
    records: list[EvidenceRecord],
    dependencies: list[DependencyRecord],
    contradictions: list[PotentialContradiction],
    reviews: list[HumanReviewRequest],
) -> list[EvidenceRecord]:
    dependency_by_evidence: dict[str, list[str]] = defaultdict(list)
    contradiction_by_evidence: dict[str, list[str]] = defaultdict(list)
    review_by_evidence: dict[str, HumanReviewRequest] = {}
    for dependency in dependencies:
        for evidence_id in dependency.evidence_ids:
            dependency_by_evidence[evidence_id].append(dependency.dependency_id)
    for contradiction in contradictions:
        for evidence_id in contradiction.evidence_ids:
            contradiction_by_evidence[evidence_id].append(contradiction.contradiction_id)
    for review in reviews:
        for evidence_id in review.evidence_ids:
            review_by_evidence[evidence_id] = review

    annotated: list[EvidenceRecord] = []
    for record in records:
        review = review_by_evidence.get(record.evidence_id)
        annotated.append(
            record.model_copy(
                update={
                    "dependency_ids": list(dict.fromkeys(record.dependency_ids + dependency_by_evidence.get(record.evidence_id, []))),
                    "contradiction_ids": list(dict.fromkeys(record.contradiction_ids + contradiction_by_evidence.get(record.evidence_id, []))),
                    "human_review_required": record.human_review_required or review is not None,
                    "human_review_role": (
                        HumanReviewRole(
                            _enum_value(review.recommended_role)
                            or HumanReviewRole.UNKNOWN.value
                        )
                        if review is not None
                        else record.human_review_role
                    ),
                }
            )
        )
    return annotated


class DeterministicEvidenceAgent:
    """Concrete implementation of the shared Evidence Agent protocol."""

    def __init__(
        self,
        project_root: Path | None = None,
        *,
        site_evidence_runner: Callable[[ProjectInput, Path], SiteEvidenceResponse] = evaluate_site,
        retrieval_runner: Callable[[Path, RetrievalRequest], dict[str, Any]] = search_index,
        retrieval_templates: Iterable[RetrievalQueryTemplate] = DEFAULT_RETRIEVAL_QUERY_TEMPLATES,
    ) -> None:
        self.project_root = (project_root or Path(__file__).resolve().parents[3]).resolve()
        self.site_evidence_runner = site_evidence_runner
        self.retrieval_runner = retrieval_runner
        self.retrieval_templates = tuple(retrieval_templates)

    def _developer_records(
        self,
        context: ProjectContext,
        project_input: ProjectInput,
        checked_at: datetime,
    ) -> tuple[list[EvidenceRecord], list[str]]:
        ledger = project_input_to_evidence_ledger(project_input, generated_at=checked_at)
        records = [_convert_ledger_entry(entry, context) for entry in ledger.entries]
        structured, warnings = _structured_project_records(context, checked_at)
        records.extend(structured)
        return records, warnings

    def _gis_records(
        self,
        context: ProjectContext,
        project_input: ProjectInput,
    ) -> tuple[list[EvidenceRecord], list[str], list[str]]:
        if project_input.latitude is None or project_input.longitude is None:
            return [], ["GIS evidence not run: latitude and longitude are not provided."], [
                "GIS evidence unavailable because site coordinates are not provided"
            ]
        try:
            response = self.site_evidence_runner(project_input, self.project_root)
        except Exception as exc:  # The bundle remains usable with a clear tool warning.
            return [], [f"Module 4B site evidence could not be evaluated: {type(exc).__name__}"], [
                "GIS evidence unavailable because the Module 4B service failed"
            ]
        records: list[EvidenceRecord] = []
        for entry in response.evidence_ledger.entries:
            if entry.evidence_id.startswith("project-input-"):
                continue
            records.append(
                _convert_ledger_entry(
                    entry,
                    context,
                    created_by=EvidenceCreatedBy.DETERMINISTIC_GIS,
                    deterministic=True,
                    domain=_domain_for_field(entry.field_name),
                )
            )
        warnings = list(response.limitations)
        missing = [
            item
            for record in records
            if (item := _missing_item_for_record(record)) is not None
        ]
        return records, warnings, missing

    def _policy_records(
        self,
        context: ProjectContext,
        checked_at: datetime,
    ) -> tuple[list[EvidenceRecord], list[str], list[str]]:
        records: list[EvidenceRecord] = []
        warnings: list[str] = []
        gaps: list[str] = []
        seen: set[tuple[Any, ...]] = set()
        loaded_index: LoadedRetrievalIndex | None = None
        load_error: Exception | None = None
        if self.retrieval_runner is search_index:
            try:
                loaded_index = load_retrieval_index(self.project_root)
            except (IndexNotBuiltError, StaleIndexError, FileNotFoundError, ValueError) as exc:
                load_error = exc
        for request in build_retrieval_requests(context, self.retrieval_templates):
            domain = Domain(_enum_value(request.domains[0]) or Domain.UNKNOWN.value)
            try:
                if load_error is not None:
                    raise load_error
                response = (
                    loaded_index.search(request)
                    if loaded_index is not None
                    else self.retrieval_runner(self.project_root, request)
                )
            except (IndexNotBuiltError, StaleIndexError, FileNotFoundError, ValueError) as exc:
                warnings.append(f"Policy retrieval for {_enum_value(domain)} unavailable: {type(exc).__name__}")
                gaps.append(f"No current policy retrieval available for {_enum_value(domain)}")
                continue
            for gap in response.get("gaps", []):
                if not _policy_gap_allowed(gap, domain, context):
                    continue
                if isinstance(gap, dict):
                    message = str(gap.get("message") or gap.get("type") or "Policy retrieval gap")
                    gaps.append(message)
                else:
                    gaps.append(str(gap))
            warnings.extend(_safe_text(item) for item in response.get("warnings", []) if item)
            for group_name in ("authoritative_results", "curated_results", "supporting_results"):
                for hit in response.get(group_name, []):
                    if not isinstance(hit, dict) or not _policy_hit_allowed(hit, context):
                        continue
                    key = _hit_record_key(hit)
                    if key in seen:
                        continue
                    seen.add(key)
                    try:
                        records.append(_policy_record(hit, context, domain, checked_at))
                    except (TypeError, ValueError, ValidationError):
                        warnings.append(f"Policy evidence record for {_enum_value(domain)} was ignored: invalid provenance")
        return records, warnings, gaps

    def _project_document_records(
        self,
        context: ProjectContext,
        checked_at: datetime,
        options: EvidenceAgentOptions,
    ) -> tuple[list[EvidenceRecord], list[str], list[str]]:
        """Load only project-scoped evidence; never route it through policy RAG."""

        if not options.include_project_documents:
            return [], [], []
        if options.investigation_plan is not None and not any(
            str(getattr(request.tool, "value", request.tool)) == "PROJECT_DOCUMENT_SEARCH"
            for request in options.investigation_plan.tool_requests
        ):
            return [], [], []
        retriever = ProjectEvidenceRetriever(options.project_evidence_root or self.project_root)
        try:
            facts = retriever.facts(
                context.project_id,
                include_benchmark=options.include_benchmark_documents,
            )
            chunks = retriever.search(
                context.project_id,
                options.project_document_query,
                include_benchmark=options.include_benchmark_documents,
                top_k=24,
            )
        except (FileNotFoundError, ValueError) as exc:
            return [], [f"Project-document evidence unavailable: {type(exc).__name__}"], [
                "No processed project-document evidence is available for this project"
            ]

        records: list[EvidenceRecord] = []
        for fact in facts:
            records.append(_project_fact_record(fact, context, checked_at))
        for chunk in chunks:
            records.append(_project_chunk_record(chunk, context, checked_at))
        if not records:
            return [], [], ["No project-document evidence matched the requested project scope"]
        return records, [], []

    def run(
        self,
        project_context: ProjectContext,
        options: EvidenceAgentOptions | None = None,
    ) -> EvidenceBundle:
        """Gather evidence into one shared bundle without assessing viability."""

        started = perf_counter()
        checked_at = _utc_now()
        options = options or EvidenceAgentOptions()
        project_input = _project_input_from_context(project_context)
        stage_started = perf_counter()
        developer_records, warnings = self._developer_records(project_context, project_input, checked_at)
        developer_elapsed_ms = round((perf_counter() - stage_started) * 1000, 3)
        stage_started = perf_counter()
        gis_records, gis_warnings, gis_missing = self._gis_records(project_context, project_input)
        gis_elapsed_ms = round((perf_counter() - stage_started) * 1000, 3)
        stage_started = perf_counter()
        policy_records, policy_warnings, retrieval_gaps = self._policy_records(project_context, checked_at)
        policy_elapsed_ms = round((perf_counter() - stage_started) * 1000, 3)
        stage_started = perf_counter()
        project_document_records, project_document_warnings, project_document_gaps = self._project_document_records(
            project_context,
            checked_at,
            options,
        )
        project_document_elapsed_ms = round((perf_counter() - stage_started) * 1000, 3)
        stage_started = perf_counter()
        warnings.extend(_safe_text(item) for item in gis_warnings)
        warnings.extend(_safe_text(item) for item in policy_warnings)
        warnings.extend(_safe_text(item) for item in project_document_warnings)

        records = [*developer_records, *gis_records, *policy_records, *project_document_records]
        missing: list[str] = []
        for record in records:
            if (item := _missing_item_for_record(record)) is not None:
                missing.append(item)
        missing.extend(gis_missing)
        missing.extend(_structured_missing_items(records))
        missing.extend(retrieval_gaps)
        missing.extend(project_document_gaps)
        missing = list(dict.fromkeys(missing))

        contradictions = _build_contradictions(records, project_context.project_id)
        dependencies = _build_dependencies(records, missing, project_context.project_id)
        reviews = _build_review_requests(
            records,
            dependencies,
            contradictions,
            missing,
            project_context.project_id,
        )
        records = _annotate_records(records, dependencies, contradictions, reviews)
        assembly_elapsed_ms = round((perf_counter() - stage_started) * 1000, 3)

        domain_summary: dict[str, Any] = {}
        for record in records:
            summary = domain_summary.setdefault(
                _enum_value(record.domain) or Domain.UNKNOWN.value,
                {"records": 0, "states": {}, "sources": {}},
            )
            summary["records"] += 1
            state = _enum_value(record.evidence_state) or AgentEvidenceState.UNKNOWN.value
            summary["states"][state] = summary["states"].get(state, 0) + 1
            source = _enum_value(record.created_by) or EvidenceCreatedBy.UNKNOWN.value
            summary["sources"][source] = summary["sources"].get(source, 0) + 1

        provenance_summary = {
            "developer_records": sum(record.created_by == EvidenceCreatedBy.DEVELOPER_INPUT for record in records),
            "structured_project_records": sum(record.created_by == EvidenceCreatedBy.PROJECT_DOCUMENT for record in records),
            "project_document_records": len(project_document_records),
            "project_document_facts": sum(record.field_name.startswith("project.") for record in project_document_records),
            "benchmark_project_document_records": sum(
                record.created_by == EvidenceCreatedBy.PROJECT_DOCUMENT
                and isinstance(record.value, dict)
                and bool(record.value.get("benchmark_only"))
                for record in project_document_records
            ),
            "timings_ms": {
                "developer_input": developer_elapsed_ms,
                "module_4b_gis": gis_elapsed_ms,
                "module_5_policy_retrieval": policy_elapsed_ms,
                "project_document_retrieval": project_document_elapsed_ms,
                "assembly_deduplication": assembly_elapsed_ms,
                "total": round((perf_counter() - started) * 1000, 3),
            },
            "gis_records": sum(record.created_by == EvidenceCreatedBy.DETERMINISTIC_GIS for record in records),
            "policy_records": sum(record.created_by == EvidenceCreatedBy.RAG_RETRIEVAL for record in records),
            "unknown_or_missing_count": len(missing),
            "execution_time_ms": round((perf_counter() - started) * 1000, 3),
        }

        return EvidenceBundle(
            project_context=project_context,
            records=records,
            domain_summary=domain_summary,
            retrieval_gaps=list(dict.fromkeys(retrieval_gaps)),
            missing_evidence=missing,
            potential_contradictions=contradictions,
            dependencies=dependencies,
            human_review_requests=reviews,
            warnings=list(dict.fromkeys(warnings)),
            provenance_summary=provenance_summary,
        )


__all__ = [
    "DEFAULT_RETRIEVAL_QUERY_TEMPLATES",
    "DeterministicEvidenceAgent",
    "EvidenceAgentOptions",
    "EvidenceAgentError",
    "RetrievalQueryTemplate",
    "build_retrieval_requests",
]
