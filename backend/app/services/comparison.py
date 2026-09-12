"""Deterministic comparison of two stored INTERLOCK assessment snapshots.

This module deliberately operates on JSON already stored by Module 13.  It
does not call the orchestrator, execute evidence retrieval, use an LLM, or
mutate either source snapshot.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Iterable

from ..schemas.comparison import (
    AssessmentComparison,
    ComparisonItem,
    ComparisonSection,
    ComparisonValueChange,
    DomainComparison,
    InputComparison,
)


class ComparisonDataError(ValueError):
    """Raised when a stored snapshot cannot be compared safely."""


_STATE_PRIORITY = {
    "NOT_ASSESSED": 0,
    "CLEAR": 1,
    "INFORMATIONAL": 2,
    "UNKNOWN": 3,
    "CONDITIONAL": 4,
    "CONSTRAINED": 5,
}

_DOMAIN_GROUPS = (
    ("planning", "Planning & Zoning", ("PLANNING",)),
    ("grid-energy", "Grid & Energy", ("GRID", "ENERGY")),
    ("water", "Water / Wastewater", ("WATER",)),
    ("biodiversity-environment", "Biodiversity / Environment", ("BIODIVERSITY", "ENVIRONMENT")),
    ("infrastructure", "Infrastructure", ("INFRASTRUCTURE",)),
    ("data-centre-policy", "Data Centre Policy", ("DATA_CENTRE_POLICY",)),
    ("general", "General Project Evidence", ("GENERAL",)),
    ("eu-reporting", "EU Reporting", ("EU_REPORTING",)),
    ("responsible-ai", "Responsible AI", ("RESPONSIBLE_AI",)),
    ("unknown", "Unclassified", ("UNKNOWN",)),
)

_INPUT_LABELS = {
    "project_name": "Project name",
    "project_type": "Development type",
    "assessment_workflow": "Assessment workflow",
    "project_lifecycle_status": "Project lifecycle status",
    "location.address": "Address",
    "location.latitude": "Latitude",
    "location.longitude": "Longitude",
    "location.local_authority": "Local authority",
    "location.country": "Country",
    "location.jurisdiction": "Jurisdiction",
    "site_boundary.area_hectares": "Site area",
    "site_boundary.source_reference": "Site boundary source",
    "planned_power_mw": "Planned power",
    "requested_mic_mva": "Requested MIC",
    "power_strategy": "Power strategy",
    "energy_strategy": "Energy strategy",
    "phasing": "Project phasing",
    "project_stage": "Project stage",
    "uploaded_document_refs": "Uploaded document references",
}


def build_assessment_comparison(
    baseline: dict[str, Any],
    comparison: dict[str, Any],
    *,
    project_id: str,
    project_name: str | None = None,
    generated_at: datetime | None = None,
) -> AssessmentComparison:
    """Build a deterministic view-model from two stored run records."""

    baseline_context = _required_dict(baseline.get("submitted_project_context"), "baseline context")
    comparison_context = _required_dict(comparison.get("submitted_project_context"), "comparison context")
    baseline_result = _required_dict(baseline.get("interlock_result"), "baseline result")
    comparison_result = _required_dict(comparison.get("interlock_result"), "comparison result")

    input_changes = _compare_inputs(baseline_context, comparison_context)
    domain_changes = _compare_domains(baseline_result, comparison_result)
    finding_changes = _compare_findings(baseline_result, comparison_result)
    unknown_changes = _compare_unknowns(baseline_result, comparison_result)
    dependency_changes = _compare_dependencies(baseline_result, comparison_result)
    human_review_changes = _compare_reviews(baseline_result, comparison_result)
    next_action_changes = _compare_actions(baseline_result, comparison_result)
    evidence_changes = _compare_evidence(baseline_result, comparison_result)
    citation_changes = _compare_citations(baseline_result, comparison_result)

    summary = {
        "input_changes": input_changes.changed_count,
        "domain_changes": sum(item.changed for item in domain_changes),
        "new_findings": finding_changes.added_count,
        "removed_findings": finding_changes.removed_count,
        "changed_findings": finding_changes.changed_count,
        "new_unknowns": unknown_changes.added_count,
        "resolved_unknowns": unknown_changes.removed_count,
        "changed_unknowns": unknown_changes.changed_count,
        "new_dependencies": dependency_changes.added_count,
        "removed_dependencies": dependency_changes.removed_count,
        "changed_dependencies": dependency_changes.changed_count,
        "new_reviews": human_review_changes.added_count,
        "removed_reviews": human_review_changes.removed_count,
        "changed_reviews": human_review_changes.changed_count,
        "new_actions": next_action_changes.added_count,
        "removed_actions": next_action_changes.removed_count,
        "changed_actions": next_action_changes.changed_count,
        "new_evidence": evidence_changes.added_count,
        "removed_evidence": evidence_changes.removed_count,
        "changed_evidence": evidence_changes.changed_count,
        "new_citations": citation_changes.added_count,
        "removed_citations": citation_changes.removed_count,
        "changed_citations": citation_changes.changed_count,
    }

    return AssessmentComparison(
        project_id=project_id,
        project_name=project_name or _text(_as_dict(comparison_context).get("project_name")),
        baseline_run_id=_run_id(baseline, "baseline"),
        comparison_run_id=_run_id(comparison, "comparison"),
        baseline_interlock_run_id=_optional_text(baseline.get("interlock_run_id")),
        comparison_interlock_run_id=_optional_text(comparison.get("interlock_run_id")),
        baseline_timestamp=_timestamp(baseline.get("created_at"), "baseline"),
        comparison_timestamp=_timestamp(comparison.get("created_at"), "comparison"),
        baseline_workflow_status=_text(baseline.get("workflow_status"), "UNKNOWN"),
        comparison_workflow_status=_text(comparison.get("workflow_status"), "UNKNOWN"),
        baseline_planned_power_mw=_number(baseline.get("planned_power_mw"), baseline_context.get("planned_power_mw")),
        comparison_planned_power_mw=_number(comparison.get("planned_power_mw"), comparison_context.get("planned_power_mw")),
        generated_at=generated_at or datetime.now(timezone.utc),
        summary=summary,
        input_changes=input_changes,
        domain_changes=domain_changes,
        finding_changes=finding_changes,
        unknown_changes=unknown_changes,
        dependency_changes=dependency_changes,
        human_review_changes=human_review_changes,
        next_action_changes=next_action_changes,
        evidence_changes=evidence_changes,
        citation_changes=citation_changes,
    )


def _compare_inputs(baseline: dict[str, Any], comparison: dict[str, Any]) -> InputComparison:
    left = _flatten_inputs(baseline)
    right = _flatten_inputs(comparison)
    changes: list[ComparisonValueChange] = []
    unchanged: list[ComparisonValueChange] = []
    for path in sorted(set(left) | set(right)):
        previous = left.get(path)
        current = right.get(path)
        item = ComparisonValueChange(
            field_path=path,
            label=_INPUT_LABELS.get(path, _field_label(path)),
            previous_value=previous,
            comparison_value=current,
            previous_display=_display_input(path, previous),
            comparison_display=_display_input(path, current),
        )
        (unchanged if _same(previous, current) else changes).append(item)
    return InputComparison(
        changed=changes,
        unchanged=unchanged,
        changed_count=len(changes),
        unchanged_count=len(unchanged),
    )


def _compare_domains(baseline: dict[str, Any], comparison: dict[str, Any]) -> list[DomainComparison]:
    left = _domain_states(baseline)
    right = _domain_states(comparison)
    output: list[DomainComparison] = []
    for key, label, source_domains in _DOMAIN_GROUPS:
        if key not in left and key not in right:
            continue
        previous = left.get(key, {"state": "NOT_ASSESSED", "finding_ids": []})
        current = right.get(key, {"state": "NOT_ASSESSED", "finding_ids": []})
        previous_state = str(previous["state"])
        current_state = str(current["state"])
        output.append(
            DomainComparison(
                domain=key,
                label=label,
                source_domains=list(source_domains),
                baseline_state=previous_state,
                comparison_state=current_state,
                changed=previous_state != current_state,
                change_kind=_domain_change_kind(previous_state, current_state),
                baseline_finding_ids=list(previous["finding_ids"]),
                comparison_finding_ids=list(current["finding_ids"]),
            )
        )
    known_keys = {item[0] for item in _DOMAIN_GROUPS}
    for key in sorted((set(left) | set(right)) - known_keys):
        if key in known_keys:
            continue
        previous = left.get(key, {"state": "NOT_ASSESSED", "finding_ids": []})
        current = right.get(key, {"state": "NOT_ASSESSED", "finding_ids": []})
        previous_state = str(previous["state"])
        current_state = str(current["state"])
        output.append(
            DomainComparison(
                domain=key,
                label=key.replace("_", " ").title(),
                source_domains=[key.upper()],
                baseline_state=previous_state,
                comparison_state=current_state,
                changed=previous_state != current_state,
                change_kind=_domain_change_kind(previous_state, current_state),
                baseline_finding_ids=list(previous["finding_ids"]),
                comparison_finding_ids=list(current["finding_ids"]),
            )
        )
    return output


def _compare_findings(baseline: dict[str, Any], comparison: dict[str, Any]) -> ComparisonSection:
    return _compare_items(
        _finding_items(baseline),
        _finding_items(comparison),
        label_key=lambda item: f"{item.get('domain', 'UNKNOWN')} · {item.get('finding_id', 'Finding')}",
    )


def _compare_unknowns(baseline: dict[str, Any], comparison: dict[str, Any]) -> ComparisonSection:
    return _compare_items(
        _unknown_items(baseline),
        _unknown_items(comparison),
        label_key=lambda item: str(item.get("title") or item.get("summary") or item.get("value") or "Material unknown"),
    )


def _compare_dependencies(baseline: dict[str, Any], comparison: dict[str, Any]) -> ComparisonSection:
    return _compare_items(
        _dependency_items(baseline),
        _dependency_items(comparison),
        label_key=lambda item: str(item.get("dependency_id") or item.get("description") or "Dependency"),
    )


def _compare_reviews(baseline: dict[str, Any], comparison: dict[str, Any]) -> ComparisonSection:
    return _compare_items(
        _review_items(baseline),
        _review_items(comparison),
        label_key=lambda item: str(item.get("recommended_role") or item.get("review_id") or "Professional review"),
    )


def _compare_actions(baseline: dict[str, Any], comparison: dict[str, Any]) -> ComparisonSection:
    return _compare_items(
        _action_items(baseline),
        _action_items(comparison),
        label_key=lambda item: str(item.get("title") or item.get("value") or "Next action"),
    )


def _compare_evidence(baseline: dict[str, Any], comparison: dict[str, Any]) -> ComparisonSection:
    return _compare_items(
        _evidence_items(baseline),
        _evidence_items(comparison),
        label_key=lambda item: str(item.get("evidence_id") or "Evidence"),
    )


def _compare_citations(baseline: dict[str, Any], comparison: dict[str, Any]) -> ComparisonSection:
    return _compare_items(
        _citation_items(baseline),
        _citation_items(comparison),
        label_key=lambda item: str(item.get("document_id") or item.get("source_path") or "Citation"),
    )


def _compare_items(
    baseline_items: list[tuple[str, bool, dict[str, Any]]],
    comparison_items: list[tuple[str, bool, dict[str, Any]]],
    *,
    label_key: Any,
) -> ComparisonSection:
    left = {key: (matchable, item) for key, matchable, item in baseline_items}
    right = {key: (matchable, item) for key, matchable, item in comparison_items}
    added: list[ComparisonItem] = []
    removed: list[ComparisonItem] = []
    changed: list[ComparisonItem] = []
    unchanged: list[ComparisonItem] = []
    for key in sorted(set(left) | set(right)):
        left_value = left.get(key)
        right_value = right.get(key)
        if left_value is None:
            matchable, item = right_value
            added.append(_comparison_item(key, matchable, None, item, label_key(item)))
            continue
        if right_value is None:
            matchable, item = left_value
            removed.append(_comparison_item(key, matchable, item, None, label_key(item)))
            continue
        left_matchable, left_item = left_value
        right_matchable, right_item = right_value
        item = _comparison_item(
            key,
            left_matchable and right_matchable,
            left_item,
            right_item,
            label_key(right_item),
        )
        (unchanged if _same(left_item, right_item) else changed).append(item)
    return ComparisonSection(
        added=added,
        removed=removed,
        changed=changed,
        unchanged=unchanged,
        added_count=len(added),
        removed_count=len(removed),
        changed_count=len(changed),
        unchanged_count=len(unchanged),
    )


def _comparison_item(
    identity: str,
    matchable: bool,
    baseline: dict[str, Any] | None,
    comparison: dict[str, Any] | None,
    label: str,
) -> ComparisonItem:
    changed_fields: list[str] = []
    if baseline is not None and comparison is not None:
        changed_fields = [
            key
            for key in sorted(set(baseline) | set(comparison))
            if not _same(baseline.get(key), comparison.get(key))
        ]
    return ComparisonItem(
        identity=identity,
        label=label,
        matchable=matchable,
        baseline=baseline,
        comparison=comparison,
        changed_fields=changed_fields,
    )


def _finding_items(result: dict[str, Any]) -> list[tuple[str, bool, dict[str, Any]]]:
    findings = _as_list(_as_dict(result.get("assessment_result")).get("findings"))
    return _identified_items(findings, "finding_id", "finding")


def _unknown_items(result: dict[str, Any]) -> list[tuple[str, bool, dict[str, Any]]]:
    explanation = _as_dict(result.get("explanation_result"))
    themes = [_as_dict(item) for item in _as_list(explanation.get("material_unknown_themes"))]
    if themes:
        return _identified_items(themes, "theme_id", "unknown-theme")
    assessment = _as_dict(result.get("assessment_result"))
    return _identified_items(
        [{"value": item} if not isinstance(item, dict) else item for item in _as_list(assessment.get("material_unknowns"))],
        "unknown_id",
        "unknown",
        fallback_key=lambda item: _text(item.get("value") or item.get("title") or item.get("summary")),
    )


def _dependency_items(result: dict[str, Any]) -> list[tuple[str, bool, dict[str, Any]]]:
    assessment = _as_dict(result.get("assessment_result"))
    dependencies = _as_list(assessment.get("dependencies"))
    if not dependencies:
        dependencies = _as_list(_as_dict(result.get("evidence_bundle")).get("dependencies"))
    if not dependencies:
        dependencies = _as_list(_as_dict(result.get("explanation_result")).get("dependencies"))
    return _identified_items(
        [{"value": item} if not isinstance(item, dict) else item for item in dependencies],
        "dependency_id",
        "dependency",
        fallback_key=lambda item: _text(item.get("value") or item.get("description")),
    )


def _review_items(result: dict[str, Any]) -> list[tuple[str, bool, dict[str, Any]]]:
    reviews = _as_list(result.get("human_reviews"))
    if not reviews:
        reviews = _as_list(_as_dict(result.get("assessment_result")).get("human_reviews"))
    return _identified_items(reviews, "review_id", "review")


def _action_items(result: dict[str, Any]) -> list[tuple[str, bool, dict[str, Any]]]:
    explanation = _as_dict(result.get("explanation_result"))
    actions = _as_list(explanation.get("next_action_plan"))
    if not actions:
        actions = _as_list(explanation.get("next_actions"))
    return _identified_items(
        [{"value": item} if not isinstance(item, dict) else item for item in actions],
        "action_id",
        "action",
        fallback_key=lambda item: _text(item.get("value") or item.get("title") or item.get("rationale")),
    )


def _evidence_items(result: dict[str, Any]) -> list[tuple[str, bool, dict[str, Any]]]:
    records = [_as_dict(item) for item in _as_list(_as_dict(result.get("evidence_bundle")).get("records"))]
    by_id: dict[str, dict[str, Any]] = {}
    for record in records:
        evidence_id = _optional_text(record.get("evidence_id"))
        if evidence_id:
            by_id[evidence_id] = {
                "evidence_id": evidence_id,
                **{key: record[key] for key in ("source_document_id", "source_path", "domain", "document_status") if record.get(key) is not None},
            }
    ids = set(by_id)
    assessment = _as_dict(result.get("assessment_result"))
    for finding in _as_list(assessment.get("findings")):
        ids.update(str(item) for item in _as_list(_as_dict(finding).get("evidence_ids")) if item)
    explanation = _as_dict(result.get("explanation_result"))
    for item in _as_list(explanation.get("material_unknown_themes")):
        ids.update(str(value) for value in _as_list(_as_dict(item).get("evidence_ids")) if value)
    for item in _as_list(explanation.get("next_action_plan")):
        ids.update(str(value) for value in _as_list(_as_dict(item).get("evidence_ids")) if value)
    for item in _as_list(result.get("human_reviews")):
        ids.update(str(value) for value in _as_list(_as_dict(item).get("evidence_ids")) if value)
    return [(evidence_id, True, by_id.get(evidence_id, {"evidence_id": evidence_id})) for evidence_id in sorted(ids)]


def _citation_items(result: dict[str, Any]) -> list[tuple[str, bool, dict[str, Any]]]:
    explanation = _as_dict(result.get("explanation_result"))
    citations = _as_list(explanation.get("customer_facing_citations"))
    if not citations:
        citations = _as_list(explanation.get("source_citations"))
    items: list[tuple[str, bool, dict[str, Any]]] = []
    for index, value in enumerate(citations):
        item = _as_dict(value)
        document_id = _optional_text(item.get("document_id"))
        source_path = _optional_text(item.get("source_path"))
        locator = _optional_text(item.get("locator"))
        identity = document_id or _stable_text_key(f"{source_path}|{locator}")
        items.append((identity or f"citation-{index}", bool(document_id or source_path or locator), item))
    return items


def _identified_items(
    values: Iterable[object],
    id_key: str,
    prefix: str,
    *,
    fallback_key: Any | None = None,
) -> list[tuple[str, bool, dict[str, Any]]]:
    items: list[tuple[str, bool, dict[str, Any]]] = []
    for index, value in enumerate(values):
        item = _as_dict(value)
        stable_id = _optional_text(item.get(id_key))
        if stable_id:
            items.append((stable_id, True, item))
            continue
        fallback = _optional_text(fallback_key(item)) if fallback_key else None
        if fallback:
            items.append((_stable_text_key(fallback), True, item))
        else:
            # Unidentified records are never matched across runs.  This is a
            # conservative result rather than a false claim of identity.
            items.append((f"{prefix}-unmatched-{index}", False, item))
    return items


def _domain_states(result: dict[str, Any]) -> dict[str, dict[str, Any]]:
    findings = [_as_dict(item) for item in _as_list(_as_dict(result.get("assessment_result")).get("findings"))]
    output: dict[str, dict[str, Any]] = {}
    assigned: set[int] = set()
    for key, _label, source_domains in _DOMAIN_GROUPS:
        matches = [
            (index, finding)
            for index, finding in enumerate(findings)
            if _enum_text(finding.get("domain")) in source_domains
        ]
        if not matches:
            continue
        assigned.update(index for index, _ in matches)
        statuses = [_enum_text(finding.get("status")) or "UNKNOWN" for _, finding in matches]
        output[key] = {
            "state": max(statuses, key=lambda value: _STATE_PRIORITY.get(value, _STATE_PRIORITY["UNKNOWN"])),
            "finding_ids": [
                _text(finding.get("finding_id"))
                for _, finding in matches
                if _optional_text(finding.get("finding_id"))
            ],
        }
    for index, finding in enumerate(findings):
        if index in assigned:
            continue
        domain = _enum_text(finding.get("domain")) or "UNKNOWN"
        output[domain.casefold()] = {
            "state": _enum_text(finding.get("status")) or "UNKNOWN",
            "finding_ids": [_text(finding.get("finding_id"))] if _optional_text(finding.get("finding_id")) else [],
        }
    return output


def _flatten_inputs(context: dict[str, Any]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in context.items():
        if key in {"project_id", "developer_inputs", "source_project_input"}:
            continue
        _flatten_value(value, key, output)
    return output


def _flatten_value(value: Any, path: str, output: dict[str, Any]) -> None:
    if isinstance(value, dict):
        if not value:
            output[path] = value
            return
        for key, child in value.items():
            _flatten_value(child, f"{path}.{key}", output)
        return
    output[path] = value


def _domain_change_kind(previous: str, current: str) -> str:
    if previous == current:
        return "UNCHANGED"
    if previous == "NOT_ASSESSED":
        return "NEW_CONSTRAINT" if current in {"CONDITIONAL", "CONSTRAINED"} else "NEW_DOMAIN"
    if current == "NOT_ASSESSED":
        return "NO_LONGER_PRESENT"
    return "CHANGED"


def _required_dict(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ComparisonDataError(f"Stored {label} is not a JSON object")
    return value


def _run_id(run: dict[str, Any], label: str) -> str:
    value = _optional_text(run.get("id")) or _optional_text(run.get("run_id"))
    if not value:
        raise ComparisonDataError(f"Stored {label} run has no stable identifier")
    return value


def _timestamp(value: object, label: str) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ComparisonDataError(f"Stored {label} run has an invalid timestamp") from exc
    raise ComparisonDataError(f"Stored {label} run has no valid timestamp")


def _number(primary: object, fallback: object) -> float | None:
    value = primary if primary is not None else fallback
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _same(left: object, right: object) -> bool:
    return _canonical(left) == _canonical(right)


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _display_input(path: str, value: object) -> str:
    if value is None or value == "":
        return "Unknown / Not provided"
    if path == "planned_power_mw":
        return f"{value} MW"
    if path == "requested_mic_mva":
        return f"{value} MVA"
    if path == "site_boundary.area_hectares":
        return f"{value} hectares"
    if isinstance(value, list) and not value:
        return "None recorded"
    if isinstance(value, dict):
        return "Provided"
    return str(value)


def _field_label(path: str) -> str:
    return path.replace(".", " · ").replace("_", " ").title()


def _stable_text_key(value: str) -> str:
    return "text:" + hashlib.sha256(value.strip().casefold().encode("utf-8")).hexdigest()[:16]


def _text(value: object, default: str = "") -> str:
    return str(getattr(value, "value", value) or default)


def _optional_text(value: object) -> str | None:
    text = _text(value).strip()
    return text or None


def _enum_text(value: object) -> str:
    return _text(value).upper()


def _as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


__all__ = ["ComparisonDataError", "build_assessment_comparison"]
