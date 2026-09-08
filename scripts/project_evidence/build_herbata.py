"""CLI wrapper for the isolated Herbata project-evidence build."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.services.project_evidence.processing import build_project_evidence


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Herbata project-evidence artifacts")
    parser.add_argument("--project-root", type=Path, default=Path("."))
    args = parser.parse_args()
    print(json.dumps(build_project_evidence(args.project_root), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
