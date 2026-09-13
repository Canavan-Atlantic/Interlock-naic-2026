"""Stage-specific bounds for the evidence investigation workflow.

The scope is deliberately small and declarative.  It controls which existing
evidence capabilities are requested; it does not interpret evidence or alter
the deterministic assessment rules.
"""

from __future__ import annotations

from dataclasses import dataclass

from .rag.models import Domain


@dataclass(frozen=True)
class StageInvestigationScope:
    """The approved policy/GIS domains for one customer assessment stage."""

    stage: str
    policy_domains: tuple[Domain, ...]
    gis_domains: tuple[Domain, ...]
    project_documents_allowed: bool


_ALL_POLICY = (
    Domain.GRID,
    Domain.ENERGY,
    Domain.PLANNING,
    Domain.BIODIVERSITY,
    Domain.ENVIRONMENT,
    Domain.WATER,
    Domain.DATA_CENTRE_POLICY,
)
_ALL_GIS = (
    Domain.GRID,
    Domain.PLANNING,
    Domain.BIODIVERSITY,
    Domain.ENVIRONMENT,
    Domain.WATER,
    Domain.GENERAL,
)

_SCOPES = {
    "Site Discovery": StageInvestigationScope(
        stage="Site Discovery",
        # Site Discovery is a screening pass.  Energy, water and project
        # documents are later-stage closure evidence, not site screening.
        policy_domains=(Domain.PLANNING, Domain.BIODIVERSITY, Domain.ENVIRONMENT),
        gis_domains=(Domain.PLANNING, Domain.BIODIVERSITY, Domain.ENVIRONMENT, Domain.GRID, Domain.GENERAL),
        project_documents_allowed=False,
    ),
    "Early Feasibility": StageInvestigationScope(
        stage="Early Feasibility",
        policy_domains=_ALL_POLICY,
        gis_domains=_ALL_GIS,
        project_documents_allowed=True,
    ),
    "Deliverability Validation": StageInvestigationScope(
        stage="Deliverability Validation",
        policy_domains=_ALL_POLICY,
        gis_domains=_ALL_GIS,
        project_documents_allowed=True,
    ),
}

_UNKNOWN_SCOPE = StageInvestigationScope(
    stage="Unknown",
    policy_domains=_ALL_POLICY,
    gis_domains=_ALL_GIS,
    project_documents_allowed=True,
)


def scope_for_stage(stage: object) -> StageInvestigationScope:
    """Return a bounded scope, with legacy-compatible full coverage fallback."""

    value = str(getattr(stage, "value", stage) or "Unknown")
    return _SCOPES.get(value, _UNKNOWN_SCOPE)


def scope_for_context(context: object) -> StageInvestigationScope:
    return scope_for_stage(getattr(context, "project_stage", None))


__all__ = ["StageInvestigationScope", "scope_for_context", "scope_for_stage"]
