"""Materialize the v3.0 solver-free robustness screen report."""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data_sources.model_v3_robustness_screen import write_model_v3_robustness_screen_report  # noqa: E402


def main() -> None:
    paths = write_model_v3_robustness_screen_report()
    print(paths["json_path"])
    print(paths["md_path"])


if __name__ == "__main__":
    main()
