"""Command-line entry point for a deterministic Module 4B site check."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ...schemas.project import ProjectInput
from .service import SiteEvidenceOptions, evaluate_site


def main() -> None:
    parser = argparse.ArgumentParser(description="INTERLOCK Module 4B site evidence")
    parser.add_argument("command", choices=["check"])
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--project-name", default=None)
    parser.add_argument("--project-stage", default="Unknown")
    parser.add_argument("--site-address", default=None)
    parser.add_argument("--latitude", type=float, required=True)
    parser.add_argument("--longitude", type=float, required=True)
    parser.add_argument("--grid-min-primary-kv", type=float, default=None)
    parser.add_argument("--grid-voltage-class", action="append", default=None)
    args = parser.parse_args()

    project = ProjectInput(
        project_name=args.project_name,
        project_stage=args.project_stage,
        site_address=args.site_address,
        latitude=args.latitude,
        longitude=args.longitude,
    )
    response = evaluate_site(
        project,
        args.project_root.resolve(),
        SiteEvidenceOptions(
            grid_min_primary_kv=args.grid_min_primary_kv,
            grid_voltage_classes=(
                tuple(args.grid_voltage_class) if args.grid_voltage_class else None
            ),
        ),
    )
    print(json.dumps(response.model_dump(mode="json"), indent=2))


if __name__ == "__main__":
    main()
