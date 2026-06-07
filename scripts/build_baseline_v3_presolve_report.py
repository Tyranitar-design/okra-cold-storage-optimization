"""Materialize the v3.0 presolve readiness report."""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data_sources.baseline_v3_presolve_report import write_baseline_v3_presolve_report


def main() -> None:
    paths = write_baseline_v3_presolve_report()
    print(paths["json_path"])
    print(paths["md_path"])


if __name__ == "__main__":
    main()
