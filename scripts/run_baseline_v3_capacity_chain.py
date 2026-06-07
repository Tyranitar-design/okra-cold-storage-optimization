"""Run and package the v3.0 capacity-chain baseline."""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data_sources.baseline_v3_capacity_chain_report import write_baseline_v3_capacity_chain_report
from src.models.single_level_mip_v3_capacity_chain import solve_baseline_v3, write_v3_result_bundle


def main() -> None:
    payload = solve_baseline_v3(verbose=True)
    result_paths = write_v3_result_bundle(payload)
    report_paths = write_baseline_v3_capacity_chain_report()
    print(result_paths["pickle_path"])
    print(report_paths["json_path"])
    print(report_paths["md_path"])


if __name__ == "__main__":
    main()
