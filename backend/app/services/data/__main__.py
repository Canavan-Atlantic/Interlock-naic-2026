"""Command line entry point for Module 4A data inventory and processing."""

from __future__ import annotations

import argparse
from pathlib import Path

from .processing import process_registry
from .registry import discover_raw_files, load_data_source_config, write_registry_manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="INTERLOCK Module 4A data pipeline")
    parser.add_argument(
        "command",
        choices=["inventory", "process"],
        help="Inventory raw sources or process them into data/processed.",
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path.cwd(),
        help="Project root containing data/raw and config/data_sources.yaml.",
    )
    args = parser.parse_args()

    project_root = args.project_root.resolve()
    config = load_data_source_config(project_root / "config" / "data_sources.yaml")
    entries = discover_raw_files(project_root, config)

    if args.command == "process":
        entries = process_registry(
            entries,
            project_root,
            project_root / "data" / "processed",
            config,
        )

    manifest = project_root / "data" / "processed" / "data_registry.json"
    write_registry_manifest(entries, manifest)
    print(f"Registered {len(entries)} raw dataset files.")
    print(f"Registry manifest: {manifest}")
    if args.command == "process":
        for entry in entries:
            print(f"{entry.status}: {entry.raw_relative_path}")


if __name__ == "__main__":
    main()
