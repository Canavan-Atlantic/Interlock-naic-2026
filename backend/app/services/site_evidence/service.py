"""Orchestration for deterministic Module 4B site evidence."""

from __future__ import annotations

from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor
from time import perf_counter
from typing import Any, Callable

from ...schemas.evidence import EvidenceConfidence, EvidenceState
from ...schemas.project import ProjectInput
from ...schemas.site_evidence import SiteEvidenceResponse
from ..evidence import project_input_to_evidence_ledger
from .base import (
    DEFAULT_RADII_METRES,
    DomainResult,
    SiteEvidenceContext,
    SiteEvidenceError,
    build_context,
    dedupe_strings,
    evidence_record,
)
from .biodiversity import evaluate_biodiversity
from .flood import evaluate_flood
from .grid import evaluate_grid
from .ground import evaluate_ground
from .heritage import evaluate_heritage
from .planning import evaluate_planning
from .water import evaluate_water
from .zoning import evaluate_zoning


@dataclass(frozen=True)
class SiteEvidenceOptions:
    """Configurable deterministic query controls for the Module 4B MVP."""

    planning_radii_m: tuple[float, ...] = DEFAULT_RADII_METRES
    karst_radii_m: tuple[float, ...] = DEFAULT_RADII_METRES
    grid_radius_m: float = 25_000.0
    grid_voltage_classes: tuple[str, ...] | None = None
    grid_min_primary_kv: float | None = None
    planning_nearby_limit: int = 10
    grid_nearby_limit: int = 30
    domains: tuple[object, ...] | None = None


def _location_payload(context: SiteEvidenceContext) -> dict[str, Any]:
    return {
        "project_name": context.project.project_name,
        "site_address": context.project.site_address,
        "latitude": context.project.latitude,
        "longitude": context.project.longitude,
        "input_crs": "EPSG:4326",
        "easting": round(context.point_itm.x, 3),
        "northing": round(context.point_itm.y, 3),
        "transformed_crs": context.target_crs,
        "transformed_coordinates": {
            "easting": round(context.point_itm.x, 3),
            "northing": round(context.point_itm.y, 3),
        },
        "checked_at": context.checked_at.isoformat().replace("+00:00", "Z"),
    }


def _location_record(context: SiteEvidenceContext) -> Any:
    payload = _location_payload(context)
    return evidence_record(
        "site-location-transformation",
        "site.location.transformed_coordinates",
        "Project location transformed from WGS84 to EPSG:2157",
        payload["transformed_coordinates"],
        checked_at=context.checked_at,
        source_name="INTERLOCK deterministic coordinate transformation",
        source_reference="project-input.latitude,project-input.longitude",
        limitation="The input location is customer-provided; coordinate transformation is deterministic and does not verify the site position.",
        confidence=EvidenceConfidence.HIGH,
    )


def _error_result(
    context: SiteEvidenceContext,
    domain: str,
    error: Exception,
) -> DomainResult:
    message = f"{domain.title()} evidence could not be evaluated: {error}"
    record = evidence_record(
        f"site-{domain}-error",
        f"{domain}.status",
        f"{domain.title()} evidence status",
        None,
        checked_at=context.checked_at,
        source_name="INTERLOCK Module 4B",
        source_reference=None,
        evidence_state=EvidenceState.UNKNOWN,
        limitation=message,
    )
    return DomainResult(
        {
            "status": "ERROR",
            "evidence_state": "UNKNOWN",
            "error": str(error),
            "reason": message,
            "limitations": [message],
            "checked_at": context.checked_at.isoformat().replace("+00:00", "Z"),
        },
        (record,),
    )


def _run_domain(
    context: SiteEvidenceContext,
    domain: str,
    evaluator: Callable[[], DomainResult],
) -> tuple[DomainResult, float]:
    started = perf_counter()
    try:
        if context.registry_error:
            raise SiteEvidenceError(context.registry_error)
        result = evaluator()
    except Exception as exc:  # Domain failure must not invalidate other domains.
        result = _error_result(context, domain, exc)
    elapsed_ms = round((perf_counter() - started) * 1000, 3)
    return result, elapsed_ms


def _merge_ledgers(project: ProjectInput, context: SiteEvidenceContext, records: list[Any]) -> Any:
    customer_ledger = project_input_to_evidence_ledger(
        project,
        generated_at=context.checked_at,
    )
    entries = [*customer_ledger.entries, *records]
    return customer_ledger.model_copy(
        update={
            "entries": entries,
            "provided_count": sum(
                entry.evidence_state is EvidenceState.PROVIDED for entry in entries
            ),
            "unknown_count": sum(
                entry.evidence_state is EvidenceState.UNKNOWN for entry in entries
            ),
            "not_provided_count": sum(
                entry.evidence_state is EvidenceState.NOT_PROVIDED for entry in entries
            ),
            "missing_or_unknown": [
                entry.field_name
                for entry in entries
                if entry.evidence_state
                in {EvidenceState.UNKNOWN, EvidenceState.NOT_PROVIDED}
            ],
        }
    )


def evaluate_site(
    project: ProjectInput,
    project_root: Any | None = None,
    options: SiteEvidenceOptions | None = None,
) -> SiteEvidenceResponse:
    """Evaluate all independent deterministic evidence domains for one site."""

    overall_started = perf_counter()
    context = build_context(project, project_root)
    selected = options or SiteEvidenceOptions()
    evaluations: dict[str, DomainResult] = {}
    timings: dict[str, float] = {}
    records = [_location_record(context)]

    all_domain_calls: tuple[tuple[str, Callable[[], DomainResult]], ...] = (
        ("biodiversity", lambda: evaluate_biodiversity(context)),
        ("flood", lambda: evaluate_flood(context)),
        (
            "planning",
            lambda: evaluate_planning(
                context,
                selected.planning_radii_m,
                selected.planning_nearby_limit,
            ),
        ),
        ("heritage", lambda: evaluate_heritage(context)),
        ("ground", lambda: evaluate_ground(context, selected.karst_radii_m)),
        (
            "grid",
            lambda: evaluate_grid(
                context,
                radius_m=selected.grid_radius_m,
                voltage_classes=selected.grid_voltage_classes,
                minimum_primary_kv=selected.grid_min_primary_kv,
                nearby_limit=selected.grid_nearby_limit,
            ),
        ),
        ("zoning", lambda: evaluate_zoning(context)),
        ("water", lambda: evaluate_water(context)),
    )
    requested = {
        str(getattr(value, "value", value)).casefold()
        for value in selected.domains
    } if selected.domains is not None else None
    domain_calls = tuple(
        (domain, evaluator)
        for domain, evaluator in all_domain_calls
        if requested is None or domain in requested
    )
    # These evaluators read independent, cached processed layers.  Execute
    # them concurrently while collecting futures in the declared order so
    # the evidence ledger remains byte-for-byte deterministic for a run.
    if domain_calls:
        with ThreadPoolExecutor(max_workers=len(domain_calls), thread_name_prefix="interlock-gis") as executor:
            futures = [executor.submit(_run_domain, context, domain, evaluator) for domain, evaluator in domain_calls]
            for (domain, _), future in zip(domain_calls, futures):
                result, elapsed = future.result()
                evaluations[domain] = result
                timings[domain] = elapsed
                records.extend(result.records)
    for domain, _ in all_domain_calls:
        if domain not in evaluations:
            evaluations[domain] = DomainResult(
                {
                    "status": "NOT_RUN",
                    "evidence_state": "NOT_PROVIDED",
                    "reason": "Not run for this assessment stage scope.",
                    "limitations": ["This domain was outside the bounded evidence scope for this stage."],
                    "checked_at": context.checked_at.isoformat().replace("+00:00", "Z"),
                }
            )

    timings["total"] = round((perf_counter() - overall_started) * 1000, 3)
    limitations = [
        "Module 4B returns deterministic evidence only; it does not produce an overall recommendation.",
        *(
            limitation
            for result in evaluations.values()
            for limitation in result.payload.get("limitations", [])
        ),
    ]
    ledger = _merge_ledgers(project, context, records)
    return SiteEvidenceResponse(
        project_location=_location_payload(context),
        biodiversity=evaluations["biodiversity"].payload,
        flood=evaluations["flood"].payload,
        planning=evaluations["planning"].payload,
        heritage=evaluations["heritage"].payload,
        ground=evaluations["ground"].payload,
        grid=evaluations["grid"].payload,
        zoning=evaluations["zoning"].payload,
        water=evaluations["water"].payload,
        evidence_ledger=ledger,
        limitations=dedupe_strings(limitations),
        timings_ms=timings,
        map_features=[
            feature
            for result in evaluations.values()
            for feature in result.payload.get("map_features", [])
            if isinstance(feature, dict)
        ],
    )
