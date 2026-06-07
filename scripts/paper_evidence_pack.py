"""Write the paper evidence pack artifacts to disk."""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data_sources.paper_evidence_pack import write_paper_evidence_pack


def main() -> None:
    result = write_paper_evidence_pack()
    print(result["json_path"])
    print(result["md_path"])


if __name__ == "__main__":
    main()
