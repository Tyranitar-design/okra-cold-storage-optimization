"""Build the normalized public LRP benchmark manifest artifacts.

This script consolidates the benchmark inventory, parsed single-file samples,
and parsed paired samples into one unified manifest for future solver
experiments. It is not okra enterprise validation.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.api.benchmark_manifest import write_normalized_manifest_artifacts


def main() -> int:
    payload = write_normalized_manifest_artifacts()
    summary = payload.get("summary", {})
    print(
        json.dumps(
            {
                "total_entries": summary.get("total_entries"),
                "inventory_collections": summary.get("inventory_collections"),
                "parse_sample_entries": summary.get("parse_sample_entries"),
                "parse_pair_entries": summary.get("parse_pair_entries"),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
