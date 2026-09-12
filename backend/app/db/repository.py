"""Transactional repository for project and assessment history records."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..schemas.agents import InterlockResult, ProjectContext, WorkflowStatus
from ..schemas.portfolio import (
    AssessmentRunResponse,
    AssessmentRunSummary,
    PORTFOLIO_SCHEMA_VERSION,
    ProjectDetail,
    ProjectSummary,
    REPORT_VERSION,
)
from .models import AssessmentRun, Project


SUCCESSFUL_WORKFLOW_STATUSES = {
    WorkflowStatus.COMPLETE.value,
    WorkflowStatus.REQUIRES_HUMAN_REVIEW.value,
}


def _enum_value(value: object) -> str:
    return str(getattr(value, "value", value))


def _project_fields(context: ProjectContext) -> dict[str, Any]:
    location = context.location
    return {
        "external_project_id": context.project_id,
        "project_name": context.project_name,
        "project_type": context.project_type,
        "address": location.address,
        "latitude": location.latitude,
        "longitude": location.longitude,
        "lifecycle_status": _enum_value(context.project_lifecycle_status),
        "project_stage": _enum_value(context.project_stage) if context.project_stage is not None else None,
        "project_context": context.model_dump(mode="json"),
        "updated_at": datetime.now(timezone.utc),
    }


def _run_metrics(result: InterlockResult) -> dict[str, Any]:
    evidence_count = len(result.evidence_bundle.records) if result.evidence_bundle else 0
    findings_count = len(result.assessment_result.findings) if result.assessment_result else 0
    unknown_theme_count = (
        len(result.explanation_result.material_unknown_themes)
        if result.explanation_result
        else 0
    )
    citation_count = 0
    if result.explanation_result:
        citation_count = len(result.explanation_result.source_citations) + len(
            result.explanation_result.customer_facing_citations
        )
    return {
        "total_runtime_ms": result.timings_ms.get("total"),
        "evidence_count": evidence_count,
        "findings_count": findings_count,
        "unknown_theme_count": unknown_theme_count,
        "human_review_count": len(result.human_reviews),
        "citation_count": citation_count,
    }


def _run_summary(run: AssessmentRun) -> AssessmentRunSummary:
    return AssessmentRunSummary(
        id=run.id,
        interlock_run_id=run.interlock_run_id,
        project_id=run.project_id,
        created_at=run.created_at,
        workflow_status=run.workflow_status,
        planned_power_mw=run.planned_power_mw,
        evidence_count=run.evidence_count,
        findings_count=run.findings_count,
        unknown_theme_count=run.unknown_theme_count,
        human_review_count=run.human_review_count,
        citation_count=run.citation_count,
        total_runtime_ms=run.total_runtime_ms,
        schema_version=run.schema_version,
        report_version=run.report_version,
    )


def _project_summary(session: Session, project: Project) -> ProjectSummary:
    latest = session.get(AssessmentRun, project.latest_run_id) if project.latest_run_id else None
    return ProjectSummary(
        id=project.id,
        external_project_id=project.external_project_id,
        project_name=project.project_name,
        project_type=project.project_type,
        address=project.address,
        latitude=project.latitude,
        longitude=project.longitude,
        lifecycle_status=project.lifecycle_status,
        project_stage=project.project_stage,
        created_at=project.created_at,
        updated_at=project.updated_at,
        latest_run_id=project.latest_run_id,
        latest_assessment=_run_summary(latest) if latest else None,
        run_count=len(project.runs),
    )


def project_detail(session: Session, project: Project) -> ProjectDetail:
    summary = _project_summary(session, project)
    return ProjectDetail(
        **summary.model_dump(),
        project_context=dict(project.project_context),
    )


def create_or_get_project(session: Session, context: ProjectContext) -> Project:
    """Create a project identity or refresh its current display context."""

    project = session.scalar(
        select(Project).where(Project.external_project_id == context.project_id)
    )
    if project is None:
        project = Project(id=str(uuid4()), **_project_fields(context))
        session.add(project)
        session.flush()
    else:
        for key, value in _project_fields(context).items():
            setattr(project, key, value)
        session.flush()
    return project


def project_by_id(session: Session, project_id: str) -> Project | None:
    return session.get(Project, project_id)


def project_by_reference(session: Session, project_reference: str) -> Project | None:
    """Resolve either the durable UUID or the original external project reference."""

    project = session.get(Project, project_reference)
    if project is not None:
        return project
    return session.scalar(
        select(Project).where(Project.external_project_id == project_reference)
    )


def list_projects(session: Session) -> list[ProjectSummary]:
    projects = list(session.scalars(select(Project).order_by(Project.updated_at.desc())))
    return [_project_summary(session, project) for project in projects]


def project_runs(session: Session, project_id: str) -> list[AssessmentRunSummary]:
    runs = list(
        session.scalars(
            select(AssessmentRun)
            .where(AssessmentRun.project_id == project_id)
            .order_by(AssessmentRun.created_at.desc())
        )
    )
    return [_run_summary(run) for run in runs]


def run_by_id(session: Session, run_id: str) -> AssessmentRun | None:
    run = session.get(AssessmentRun, run_id)
    if run is not None:
        return run
    return session.scalar(select(AssessmentRun).where(AssessmentRun.interlock_run_id == run_id))


def project_run_by_reference(session: Session, project_id: str, run_reference: str) -> AssessmentRun | None:
    """Resolve a run reference only when it belongs to the selected project."""

    run = run_by_id(session, run_reference)
    if run is None or run.project_id != project_id:
        return None
    return run


def run_response(run: AssessmentRun) -> AssessmentRunResponse:
    return AssessmentRunResponse(
        **_run_summary(run).model_dump(),
        submitted_project_context=dict(run.submitted_project_context),
        interlock_result=dict(run.interlock_result),
        report_available=True,
    )


def persist_successful_interlock_result(
    session: Session,
    context: ProjectContext,
    result: InterlockResult,
    *,
    stored_project_id: str | None = None,
) -> AssessmentRunResponse:
    """Atomically append a complete/review result and update the project pointer."""

    workflow_status = _enum_value(result.workflow_status)
    if workflow_status not in SUCCESSFUL_WORKFLOW_STATUSES:
        raise ValueError("Only complete or human-review assessment results can be persisted")

    if stored_project_id:
        project = session.get(Project, stored_project_id)
        if project is None:
            raise LookupError("The requested project was not found")
        for key, value in _project_fields(context).items():
            setattr(project, key, value)
    else:
        project = create_or_get_project(session, context)

    result_payload = result.model_dump(mode="json")
    run = AssessmentRun(
        id=str(uuid4()),
        project_id=project.id,
        interlock_run_id=result.run_id,
        workflow_status=workflow_status,
        planned_power_mw=context.planned_power_mw,
        submitted_project_context=context.model_dump(mode="json"),
        interlock_result=result_payload,
        schema_version=str(result.schema_version or PORTFOLIO_SCHEMA_VERSION),
        report_version=REPORT_VERSION,
        **_run_metrics(result),
    )
    session.add(run)
    session.flush()
    project.latest_run_id = run.id
    session.flush()
    return run_response(run)


__all__ = [
    "SUCCESSFUL_WORKFLOW_STATUSES",
    "create_or_get_project",
    "list_projects",
    "persist_successful_interlock_result",
    "project_by_id",
    "project_by_reference",
    "project_detail",
    "project_run_by_reference",
    "project_runs",
    "run_by_id",
    "run_response",
]
