"""Curated, finite Herbata benchmark download allow-list."""

from __future__ import annotations

from dataclasses import dataclass

from .models import ProjectDocumentClassification
from ...services.rag.models import Domain


HERBATA_PROJECT_ID = "benchmark-herbata-naas"
HERBATA_VOL1_URL = "https://herbatagdc.ie/environmental-documents/vol-1-main-text"
HERBATA_VOL2_URL = "https://herbatagdc.ie/environmental-documents/volume-2-appendices"


@dataclass(frozen=True)
class HerbataDocumentSpec:
    key: str
    title: str
    listing_url: str
    classification: ProjectDocumentClassification
    document_type: str
    domain: Domain
    benchmark_only: bool
    direct_url: str | None = None


HERBATA_DOCUMENT_ALLOWLIST: tuple[HerbataDocumentSpec, ...] = (
    HerbataDocumentSpec(
        "project_description",
        "EIAR Chapter 4 Description of the Project and Need for the Project D.01",
        HERBATA_VOL1_URL,
        ProjectDocumentClassification.PROJECT_INPUT_BENCHMARK,
        "PROJECT_DESCRIPTION",
        Domain.GENERAL,
        False,
        "https://herbatagdc.ie/documents/19791/file",
    ),
    HerbataDocumentSpec(
        "sources_of_energy",
        "Appendix 1.3 - Herbata Data Centre Sources of Energy Report",
        HERBATA_VOL2_URL,
        ProjectDocumentClassification.PROJECT_INPUT_BENCHMARK,
        "ENERGY_STRATEGY",
        Domain.ENERGY,
        False,
    ),
    HerbataDocumentSpec(
        "planning_engineering",
        "Appendix 4.2 - Data Centre Application - Planning Engineering Report",
        HERBATA_VOL2_URL,
        ProjectDocumentClassification.PROJECT_INPUT_BENCHMARK,
        "ENGINEERING_REPORT",
        Domain.INFRASTRUCTURE,
        False,
        "https://herbatagdc.ie/documents/19813/file",
    ),
    HerbataDocumentSpec(
        "uisce_feasibility",
        "Appendix 4.2 E - Uisce Eireann Confirmation of Feasibility Letter",
        HERBATA_VOL2_URL,
        ProjectDocumentClassification.PROJECT_INPUT_BENCHMARK,
        "UTILITY_CORRESPONDENCE",
        Domain.WATER,
        False,
    ),
    HerbataDocumentSpec(
        "grid_substation",
        "Appendix 4.13 - 110KV Grid Substation and transmission Line Report",
        HERBATA_VOL2_URL,
        ProjectDocumentClassification.PROJECT_INPUT_BENCHMARK,
        "GRID_ENGINEERING",
        Domain.GRID,
        False,
        "https://herbatagdc.ie/documents/19842/file",
    ),
    HerbataDocumentSpec(
        "appropriate_assessment",
        "Appendix 5.3 - Appropriate Assessment Screening Report",
        HERBATA_VOL2_URL,
        ProjectDocumentClassification.BENCHMARK_ONLY,
        "APPROPRIATE_ASSESSMENT",
        Domain.ENVIRONMENT,
        True,
        "https://herbatagdc.ie/documents/19845/file",
    ),
    HerbataDocumentSpec(
        "biodiversity_eiar",
        "EIAR Chapter 5 Biodiversity D.01",
        HERBATA_VOL1_URL,
        ProjectDocumentClassification.BENCHMARK_ONLY,
        "EIA",
        Domain.BIODIVERSITY,
        True,
    ),
    HerbataDocumentSpec(
        "water_hydrology_eiar",
        "EIAR Chapter 7 Water and Hydrology D.01",
        HERBATA_VOL1_URL,
        ProjectDocumentClassification.BENCHMARK_ONLY,
        "EIA",
        Domain.WATER,
        True,
    ),
    HerbataDocumentSpec(
        "material_assets_built_services",
        "EIAR Chapter 13 Material Assets - Built Services D.01",
        HERBATA_VOL1_URL,
        ProjectDocumentClassification.BENCHMARK_ONLY,
        "EIA",
        Domain.INFRASTRUCTURE,
        True,
    ),
)
