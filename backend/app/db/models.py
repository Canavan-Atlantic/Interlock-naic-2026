"""SQLAlchemy models for projects and immutable assessment-run snapshots."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


JSON_TYPE = JSON().with_variant(JSONB, "postgresql")


class Base(DeclarativeBase):
    """Base for the small, explicit portfolio schema."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Project(Base):
    """A durable project identity with its latest assessment pointer."""

    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    external_project_id: Mapped[str | None] = mapped_column(String(255), unique=True, index=True)
    project_name: Mapped[str | None] = mapped_column(String(500))
    project_type: Mapped[str | None] = mapped_column(String(255))
    address: Mapped[str | None] = mapped_column(String(1000))
    latitude: Mapped[float | None]
    longitude: Mapped[float | None]
    lifecycle_status: Mapped[str | None] = mapped_column(String(64))
    project_stage: Mapped[str | None] = mapped_column(String(128))
    project_context: Mapped[dict] = mapped_column(JSON_TYPE, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, onupdate=_utc_now, nullable=False
    )
    latest_run_id: Mapped[str | None] = mapped_column(String(36), index=True)

    runs: Mapped[list["AssessmentRun"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="AssessmentRun.created_at.desc()",
    )


class AssessmentRun(Base):
    """An append-only snapshot of one successful INTERLOCK result."""

    __tablename__ = "assessment_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    interlock_run_id: Mapped[str | None] = mapped_column(String(255), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)
    workflow_status: Mapped[str] = mapped_column(String(64), nullable=False)
    planned_power_mw: Mapped[float | None]
    submitted_project_context: Mapped[dict] = mapped_column(JSON_TYPE, nullable=False)
    interlock_result: Mapped[dict] = mapped_column(JSON_TYPE, nullable=False)
    total_runtime_ms: Mapped[float | None]
    evidence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    findings_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unknown_theme_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    human_review_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    citation_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    report_version: Mapped[str] = mapped_column(String(32), nullable=False)
    report_generated_on_demand: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    project: Mapped[Project] = relationship(back_populates="runs")
