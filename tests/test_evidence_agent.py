"""Focused tests for the deterministic Module 6 Evidence Agent."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

import backend.app.agents.evidence as evidence_module
from backend.app.agents.evidence import (
    DeterministicEvidenceAgent,
    EvidenceAgentOptions,
    _build_review_requests,
    build_retrieval_requests,
)
from backend.app.schemas.agents import AgentEvidenceState, EvidenceBundle, EvidenceRecord as AgentEvidenceRecord, ProjectContext
from backend.app.schemas.evidence import (
    EvidenceCategory,
    EvidenceConfidence,
    EvidenceLedger,
    EvidenceRecord,
    EvidenceReviewStatus,
    EvidenceSourceType,
    EvidenceState,
)
from backend.app.schemas.project import ProjectInput
from backend.app.schemas.site_evidence import SiteEvidenceResponse
from backend.app.services.rag.models import Domain, Jurisdiction, Workflow
from backend.app.services.site_evidence.service import evaluate_site


ROOT = Path(__file__).resolve().parents[1]
CHECKED_AT = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _context(**overrides: Any) -> ProjectContext:
    values: dict[str, Any] = {
        "project_id": "agent-test-project",
        "project_name": "Synthetic Agent Test",
        "project_type": "Data Centre",
        "assessment_workflow": Workflow.SITE_FEASIBILITY,
        "location": {
            "address": "Synthetic site, Blanchardstown",
            "country": "Ireland",
            "jurisdiction": Jurisdiction.IRELAND,
            "local_authority": "Fingal",
            "latitude": None,
            "longitude": None,
        },
        "planned_power_mw": None,
        "requested_mic_mva": None,
        "power_strategy": "Unknown",
        "energy_strategy": None,
        "project_stage": "Early Feasibility",
        "developer_inputs": {},
    }
    values.update(overrides)
    return ProjectContext.model_validate(values)


def _entry(
    evidence_id: str,
    field_name: str,
    value: Any,
    *,
    state: EvidenceState = EvidenceState.PROVIDED,
    source_type: EvidenceSourceType = EvidenceSourceType.DETERMINISTIC_CALCULATION,
    source_name: str = "Synthetic Module 4B",
    source_reference: str = "synthetic-layer",
) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=evidence_id,
        category=EvidenceCategory.SITE,
        field_name=field_name,
        fact=f"Synthetic fact for {field_name}",
        value=value,
        unit=None,
        source_type=source_type,
        source_name=source_name,
        source_reference=source_reference,
        evidence_state=state,
        confidence=EvidenceConfidence.HIGH if state is EvidenceState.PROVIDED else EvidenceConfidence.UNKNOWN,
        limitation="Synthetic test limitation",
        review_status=EvidenceReviewStatus.UNREVIEWED,
        checked_at=CHECKED_AT,
    )


def _site_response(entries: list[EvidenceRecord]) -> SiteEvidenceResponse:
    ledger = EvidenceLedger(
        project_name="Synthetic Agent Test",
        generated_at=CHECKED_AT,
        entries=entries,
        provided_count=sum(item.evidence_state is EvidenceState.PROVIDED for item in entries),
        unknown_count=sum(item.evidence_state is EvidenceState.UNKNOWN for item in entries),
        not_provided_count=sum(item.evidence_state is EvidenceState.NOT_PROVIDED for item in entries),
        missing_or_unknown=[item.field_name for item in entries if item.evidence_state is not EvidenceState.PROVIDED],
    )
    empty = {"status": "OK", "evidence_state": "UNKNOWN", "limitations": []}
    return SiteEvidenceResponse(
        project_location={"latitude": 53.38, "longitude": -6.38},
        biodiversity=empty,
        flood=empty,
        planning=empty,
        heritage=empty,
        ground=empty,
        grid=empty,
        zoning=empty,
        water=empty,
        evidence_ledger=ledger,
        limitations=[],
        timings_ms={"total": 1.0},
    )


def _hit(
    record_id: str,
    *,
    source_class: str = "PRIMARY",
    document_status: str = "CURRENT",
    jurisdiction: str = "IRELAND",
    jurisdiction_detail: str | None = None,
    document_id: str = "doc-policy-001",
    page_start: int = 4,
    text: str = "Synthetic current policy evidence.",
) -> dict[str, Any]:
    return {
        "record_id": record_id,
        "chunk_id": record_id,
        "curated_record_id": None,
        "document_id": document_id,
        "title": "Synthetic Current Policy",
        "text": text,
        "source_class": source_class,
        "document_status": document_status,
        "jurisdiction": jurisdiction,
        "jurisdiction_detail": jurisdiction_detail,
        "issuer": "Synthetic Public Body",
        "publication_date": "2026-01-01",
        "effective_date": "2026-01-01",
        "page_start": page_start,
        "page_end": page_start,
        "section_heading": "Synthetic requirements",
        "citation": f"Synthetic Current Policy, p. {page_start}",
        "verification_status": "VERIFIED_METADATA",
        "requires_human_review": False,
        "source_path": "synthetic/policy.pdf",
    }


def _empty_retrieval(_root: Path, _request: Any) -> dict[str, Any]:
    return {
        "authoritative_results": [],
        "curated_results": [],
        "supporting_results": [],
        "historical_results": [],
        "gaps": [],
        "warnings": [],
    }


def test_project_context_becomes_developer_evidence_and_missing_mic_stays_unknown() -> None:
    agent = DeterministicEvidenceAgent(
        project_root=ROOT,
        site_evidence_runner=lambda *_: (_ for _ in ()).throw(AssertionError("GIS should not run")),
        retrieval_runner=_empty_retrieval,
    )
    bundle = agent.run(_context())

    mic = next(item for item in bundle.records if item.field_name == "requested_mic_mva")
    assert mic.evidence_state is AgentEvidenceState.NOT_PROVIDED
    assert mic.value is None
    assert mic.value != 0
    assert "MIC not provided" in bundle.missing_evidence


def test_module_4_deterministic_findings_and_unknowns_preserve_provenance() -> None:
    project = ProjectInput(latitude=53.38, longitude=-6.38)
    deterministic = _entry("gis-grid-001", "grid.nearest_connection", {"distance_m": 1200})
    unknown = _entry(
        "gis-zoning-001",
        "zoning.status",
        None,
        state=EvidenceState.UNKNOWN,
        source_name="INTERLOCK Module 4B",
        source_reference="zoning-registry",
    )
    agent = DeterministicEvidenceAgent(
        project_root=ROOT,
        site_evidence_runner=lambda *_: _site_response([*project_input_entries(project), deterministic, unknown]),
        retrieval_runner=_empty_retrieval,
    )
    bundle = agent.run(_context(source_project_input=project))

    grid = next(item for item in bundle.records if item.evidence_id == "gis-grid-001")
    zoning = next(item for item in bundle.records if item.evidence_id == "gis-zoning-001")
    assert grid.created_by.value == "DETERMINISTIC_GIS"
    assert grid.deterministic is True
    assert grid.value == {"distance_m": 1200}
    assert zoning.evidence_state is AgentEvidenceState.UNKNOWN
    assert any("zoning" in item.casefold() for item in bundle.missing_evidence)


def project_input_entries(project: ProjectInput) -> list[EvidenceRecord]:
    """Return only the normal Module 3 records for a mocked site response."""

    from backend.app.services.evidence import project_input_to_evidence_ledger

    return project_input_to_evidence_ledger(project, generated_at=CHECKED_AT).entries


def test_rag_citations_survive_and_primary_supporting_status_remains_distinct() -> None:
    def retrieve(_root: Path, request: Any) -> dict[str, Any]:
        return {
            "authoritative_results": [_hit(f"primary-{request.domains[0]}")],
            "curated_results": [],
            "supporting_results": [
                _hit(
                    f"supporting-{request.domains[0]}",
                    source_class="SUPPORTING_INDUSTRY",
                    document_id="doc-supporting-001",
                    page_start=9,
                )
            ],
            "historical_results": [],
            "gaps": [],
            "warnings": [],
        }

    bundle = DeterministicEvidenceAgent(
        project_root=ROOT,
        retrieval_runner=retrieve,
    ).run(_context())

    primary = next(item for item in bundle.records if item.source_document_id == "doc-policy-001")
    supporting = next(item for item in bundle.records if item.source_document_id == "doc-supporting-001")
    assert primary.source_class.value == "PRIMARY"
    assert primary.document_status.value == "CURRENT"
    assert primary.citation is not None and primary.citation.page_start == 4
    assert supporting.source_class.value == "SUPPORTING_INDUSTRY"
    assert supporting.limitation == "Supporting evidence; it is not a primary authority."


def test_proposed_policy_does_not_enter_default_evidence() -> None:
    def retrieve(_root: Path, _request: Any) -> dict[str, Any]:
        return {
            "authoritative_results": [
                _hit("proposed-001", document_status="PROPOSED"),
                _hit("current-001", document_id="doc-current-001"),
            ],
            "curated_results": [],
            "supporting_results": [],
            "historical_results": [],
            "gaps": [],
            "warnings": [],
        }

    bundle = DeterministicEvidenceAgent(project_root=ROOT, retrieval_runner=retrieve).run(_context())
    assert all(item.document_status.value != "PROPOSED" for item in bundle.records if item.created_by.value == "RAG_RETRIEVAL")


def test_fingal_local_policy_does_not_leak_into_wicklow_project() -> None:
    def retrieve(_root: Path, _request: Any) -> dict[str, Any]:
        return {
            "authoritative_results": [
                _hit(
                    "fingal-001",
                    jurisdiction="LOCAL_AUTHORITY",
                    jurisdiction_detail="Fingal",
                )
            ],
            "curated_results": [],
            "supporting_results": [],
            "historical_results": [],
            "gaps": [
                {
                    "type": "NO_AUTHORITATIVE_LOCAL_SOURCE",
                    "message": "No Wicklow local source is available.",
                }
            ],
            "warnings": [],
        }

    context = _context(
        location={
            "address": "Synthetic site, Wicklow",
            "country": "Ireland",
            "jurisdiction": "IRELAND",
            "local_authority": "Wicklow",
        }
    )
    bundle = DeterministicEvidenceAgent(project_root=ROOT, retrieval_runner=retrieve).run(context)
    assert not any(item.source_document_id == "doc-policy-001" for item in bundle.records)
    assert any("Wicklow" in item for item in bundle.retrieval_gaps)


def test_generic_local_authority_gaps_are_only_kept_for_planning_and_water() -> None:
    def retrieve(_root: Path, request: Any) -> dict[str, Any]:
        domain = getattr(request.domains[0], "value", request.domains[0])
        return {
            "authoritative_results": [],
            "curated_results": [],
            "supporting_results": [],
            "historical_results": [],
            "gaps": [{
                "type": "NO_AUTHORITATIVE_LOCAL_SOURCE",
                "domain": domain,
                "message": f"No active local-authority {domain} source for Kildare County Council is present.",
            }],
            "warnings": [],
        }

    context = _context(
        location={
            "address": "Synthetic site, Naas",
            "country": "Ireland",
            "jurisdiction": "IRELAND",
            "local_authority": "Kildare County Council",
        }
    )
    bundle = DeterministicEvidenceAgent(
        project_root=ROOT,
        retrieval_runner=retrieve,
    ).run(context, EvidenceAgentOptions(include_project_documents=False))

    assert len(bundle.retrieval_gaps) == 2
    assert all(domain in bundle.retrieval_gaps[index] for index, domain in enumerate(("PLANNING", "WATER")))
    assert not any(domain in " ".join(bundle.retrieval_gaps) for domain in ("GRID", "ENERGY", "BIODIVERSITY", "ENVIRONMENT", "DATA_CENTRE_POLICY"))


def test_duplicate_review_reasons_are_collapsed_case_and_whitespace_insensitively() -> None:
    record = AgentEvidenceRecord.model_validate({
        **_entry("review-001", "site.field", None, state=EvidenceState.UNKNOWN).model_dump(),
        "project_id": "agent-test-project",
        "domain": Domain.PLANNING,
        "evidence_state": AgentEvidenceState.UNKNOWN,
        "human_review_required": True,
    })
    duplicate = record.model_copy(update={"evidence_id": "review-002", "limitation": "  SYNTHETIC   TEST LIMITATION "})
    reviews = _build_review_requests([record, duplicate], [], [], [], "agent-test-project")

    assert len(reviews) == 1
    assert reviews[0].evidence_ids == ["review-001", "review-002"]


def test_one_evidence_run_loads_and_reuses_one_policy_index(monkeypatch: Any) -> None:
    calls = {"loads": 0, "searches": 0}

    class FakeLoadedIndex:
        def search(self, _request: Any) -> dict[str, Any]:
            calls["searches"] += 1
            return _empty_retrieval(Path("."), _request)

    def load(_root: Path) -> FakeLoadedIndex:
        calls["loads"] += 1
        return FakeLoadedIndex()

    monkeypatch.setattr(evidence_module, "load_retrieval_index", load)
    agent = DeterministicEvidenceAgent(
        project_root=ROOT,
        retrieval_runner=evidence_module.search_index,
    )
    agent.run(_context(), EvidenceAgentOptions(include_project_documents=False))

    assert calls == {"loads": 1, "searches": len(build_retrieval_requests(_context()))}


def test_duplicate_retrieved_chunks_are_deduplicated() -> None:
    duplicate = _hit("duplicate-001")

    def retrieve(_root: Path, _request: Any) -> dict[str, Any]:
        return {
            "authoritative_results": [duplicate, duplicate.copy()],
            "curated_results": [],
            "supporting_results": [],
            "historical_results": [],
            "gaps": [],
            "warnings": [],
        }

    bundle = DeterministicEvidenceAgent(project_root=ROOT, retrieval_runner=retrieve).run(_context())
    matching = [item for item in bundle.records if item.source_document_id == "doc-policy-001"]
    assert len(matching) == 1


def test_scope_mismatch_is_preserved_as_contradiction() -> None:
    structured = [
        {
            "evidence_id": "scope-earlier-001",
            "field_name": "project_scope",
            "fact": "Earlier synthetic scope",
            "value": "100MW",
            "source_type": "customer_document",
            "source_name": "Earlier synthetic scope",
            "source_reference": "earlier-scope",
            "evidence_state": "PROVIDED",
            "confidence": "MEDIUM",
            "review_status": "UNREVIEWED",
            "created_by": "PROJECT_DOCUMENT",
            "source_document_id": "doc-earlier-scope",
        },
        {
            "evidence_id": "scope-later-001",
            "field_name": "project_scope",
            "fact": "Later synthetic scope",
            "value": "200MW",
            "source_type": "customer_document",
            "source_name": "Later synthetic scope",
            "source_reference": "later-scope",
            "evidence_state": "PROVIDED",
            "confidence": "MEDIUM",
            "review_status": "UNREVIEWED",
            "created_by": "PROJECT_DOCUMENT",
            "source_document_id": "doc-later-scope",
        },
    ]
    context = _context(developer_inputs={"evidence_records": structured})
    bundle = DeterministicEvidenceAgent(project_root=ROOT, retrieval_runner=_empty_retrieval).run(context)

    assert len(bundle.potential_contradictions) == 1
    contradiction = bundle.potential_contradictions[0]
    assert contradiction.type == "PROJECT_SCOPE_MISMATCH"
    assert set(contradiction.evidence_ids) == {"scope-earlier-001", "scope-later-001"}
    assert contradiction.requires_human_review is True


def test_agreement_is_not_energisation_and_planned_is_not_commissioned() -> None:
    structured = [
        {
            "evidence_id": "agreement-001",
            "field_name": "grid_connection_agreement",
            "fact": "Synthetic agreement exists",
            "value": "exists",
            "source_type": "customer_document",
            "source_name": "Synthetic agreement",
            "source_reference": "agreement",
            "evidence_state": "PROVIDED",
            "confidence": "MEDIUM",
            "created_by": "PROJECT_DOCUMENT",
        },
        {
            "evidence_id": "renewable-001",
            "field_name": "renewable_asset_status",
            "fact": "Synthetic asset is planned but not commissioned",
            "value": "PLANNED_NOT_COMMISSIONED",
            "source_type": "customer_document",
            "source_name": "Synthetic renewable plan",
            "source_reference": "renewable-plan",
            "evidence_state": "PROVIDED",
            "confidence": "MEDIUM",
            "created_by": "PROJECT_DOCUMENT",
        },
    ]
    context = _context(developer_inputs={"evidence_records": structured})
    bundle = DeterministicEvidenceAgent(project_root=ROOT, retrieval_runner=_empty_retrieval).run(context)

    assert "energisation evidence unavailable" in bundle.missing_evidence
    assert "planned renewable asset not proven commissioned" in bundle.missing_evidence
    assert any(item.dependency_id == "dependency-grid-agreement-energisation" for item in bundle.dependencies)
    assert any(item.dependency_id == "dependency-renewable-commissioning" for item in bundle.dependencies)
    assert not any("energised" in (item.fact or "").casefold() for item in bundle.records if item.evidence_id == "agreement-001")


def test_ai_provenance_cannot_be_marked_deterministic() -> None:
    context = _context(
        developer_inputs={
            "evidence_records": [
                {
                    "evidence_id": "ai-bad-001",
                    "field_name": "grid_fact",
                    "fact": "Synthetic AI item",
                    "value": "not accepted",
                    "source_type": "deterministic_calculation",
                    "source_name": "Synthetic AI extractor",
                    "evidence_state": "FACT",
                    "created_by": "AI_EXTRACTION",
                    "deterministic": True,
                }
            ]
        }
    )
    bundle = DeterministicEvidenceAgent(project_root=ROOT, retrieval_runner=_empty_retrieval).run(context)
    assert not any(item.evidence_id == "ai-bad-001" for item in bundle.records)
    assert any("invalid provenance" in item for item in bundle.warnings)


def test_retrieval_query_plan_is_small_domain_specific_and_filtered() -> None:
    requests = build_retrieval_requests(_context())

    assert len(requests) == 7
    assert {request.domains[0] for request in requests} == {
        Domain.GRID,
        Domain.ENERGY,
        Domain.PLANNING,
        Domain.BIODIVERSITY,
        Domain.ENVIRONMENT,
        Domain.WATER,
        Domain.DATA_CENTRE_POLICY,
    }
    assert all(request.include_historical is False for request in requests)
    assert all(request.include_supporting is True for request in requests)
    assert all("Synthetic Agent Test" not in request.query for request in requests)


def test_api_returns_valid_evidence_bundle(monkeypatch: Any) -> None:
    from backend.app import main

    class FakeAgent:
        def run(self, context: ProjectContext) -> EvidenceBundle:
            return EvidenceBundle(project_context=context)

    monkeypatch.setattr(main, "DeterministicEvidenceAgent", lambda _root: FakeAgent())
    client = TestClient(main.app)
    response = client.post(
        "/agents/evidence",
        json={"project_id": "api-project-001"},
    )

    assert response.status_code == 200
    payload = EvidenceBundle.model_validate(response.json())
    assert payload.project_context.project_id == "api-project-001"
    assert "decision" not in response.json()


def test_shared_module_6_fixtures_remain_valid() -> None:
    from backend.app.schemas.agents import AssessmentResult, ExplanationResult, InterlockResult

    fixture_dir = ROOT / "tests" / "fixtures" / "agents"
    ProjectContext.model_validate_json((fixture_dir / "project_context_blanchardstown.json").read_text(encoding="utf-8"))
    EvidenceBundle.model_validate_json((fixture_dir / "evidence_bundle_example.json").read_text(encoding="utf-8"))
    AssessmentResult.model_validate_json((fixture_dir / "assessment_result_example.json").read_text(encoding="utf-8"))
    ExplanationResult.model_validate_json((fixture_dir / "explanation_result_example.json").read_text(encoding="utf-8"))
    InterlockResult.model_validate_json((fixture_dir / "interlock_result_example.json").read_text(encoding="utf-8"))
    EvidenceBundle.model_validate_json((fixture_dir / "echelon_scope_change_example.json").read_text(encoding="utf-8"))
