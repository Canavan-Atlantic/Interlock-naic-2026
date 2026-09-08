"""Schemas for structured developer project input."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator


ProjectStage = Literal[
    "Site Discovery",
    "Early Feasibility",
    "Deliverability Validation",
    "Design Definition",
    "Planning Readiness",
    "Planning Approved",
    "Construction",
    "Unknown",
]

PowerStrategy = Literal[
    "Existing Grid Connection",
    "New Grid Connection",
    "Developer-Built Substation",
    "Hybrid / Alternative Strategy",
    "Unknown",
]


class ProjectInput(BaseModel):
    """Structured information supplied by a developer."""

    project_name: str | None = None
    development_type: str | None = "Data Centre"
    project_stage: ProjectStage = "Unknown"

    site_address: str | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    site_area_hectares: float | None = Field(default=None, ge=0)

    planned_power_demand_mw: float | None = Field(default=None, ge=0)
    requested_mic_mva: float | None = Field(default=None, ge=0)

    power_strategy: PowerStrategy = "Unknown"
    energy_strategy: str | None = None

    project_phasing_notes: str | None = None

    @field_validator(
        "project_name",
        "development_type",
        "site_address",
        "energy_strategy",
        "project_phasing_notes",
        mode="before",
    )
    @classmethod
    def blank_text_is_missing(cls, value: object) -> object:
        """Represent blank optional text as an explicit missing value."""

        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator(
        "latitude",
        "longitude",
        "site_area_hectares",
        "planned_power_demand_mw",
        "requested_mic_mva",
        mode="before",
    )
    @classmethod
    def blank_number_is_missing(cls, value: object) -> object:
        """Accept an empty form value as missing rather than as zero."""

        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("project_stage", "power_strategy", mode="before")
    @classmethod
    def blank_choice_is_unknown(cls, value: object) -> object:
        """Keep an empty choice explicit as Unknown."""

        if value is None or (isinstance(value, str) and not value.strip()):
            return "Unknown"
        return value


class ProjectValidationResponse(BaseModel):
    """Response returned after deterministic project-input validation."""

    status: Literal["valid"]
    project: ProjectInput
    missing_or_unknown: list[str]


def find_missing_or_unknown(project: ProjectInput) -> list[str]:
    """Return field names that are not yet known or were marked Unknown."""

    missing_or_unknown: list[str] = []

    for field_name, value in project.model_dump().items():
        if value is None or value == "Unknown":
            missing_or_unknown.append(field_name)
        elif isinstance(value, str) and not value.strip():
            missing_or_unknown.append(field_name)

    return missing_or_unknown
