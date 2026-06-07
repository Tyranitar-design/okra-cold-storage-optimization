"""Build a runbook for the current Overpass artifact stack."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESULT_DIR = PROJECT_ROOT / "results" / "real_data_sources"


def build_overpass_runbook() -> Dict[str, Any]:
    return {
        "source_name": "Overpass runbook",
        "artifact_stack": [
            {
                "name": "preview",
                "path": str(RESULT_DIR / "overpass_ingestion_preview.json"),
                "purpose": "Static preview of the candidate Overpass datasets.",
            },
            {
                "name": "preview_validation",
                "path": str(RESULT_DIR / "overpass_ingestion_preview_validation.json"),
                "purpose": "JSON/MD consistency validation for the preview.",
            },
            {
                "name": "request_preview",
                "path": str(RESULT_DIR / "overpass_request_preview_osm_features_overpass.json"),
                "purpose": "Static preview of the exact Overpass request.",
            },
            {
                "name": "request_validation",
                "path": str(RESULT_DIR / "overpass_request_preview_validation.json"),
                "purpose": "JSON/MD consistency validation for the request preview.",
            },
            {
                "name": "artifact_summary",
                "path": str(RESULT_DIR / "overpass_artifact_summary.json"),
                "purpose": "Aggregated status summary of the artifact stack.",
            },
        ],
        "execution_commands": [
            "python scripts/overpass_ingest.py preview",
            "python scripts/validate_overpass_preview.py",
            "python scripts/overpass_ingest.py request-preview --dataset-id osm_features_overpass",
            "python scripts/validate_overpass_request_preview.py",
            "python scripts/overpass_summary.py",
        ],
        "online_execution_commands": [
            "python scripts/overpass_ingest.py download --dataset-id osm_features_overpass",
            "python scripts/overpass_ingest.py clean --dataset-id osm_features_overpass --raw-path data/raw/osm/overpass_features_raw.json --cleaned-path data/processed/real_data/osm_features.geojson",
            "python scripts/overpass_ingest.py run --dataset-id osm_features_overpass",
            "python scripts/overpass_ingest.py download --dataset-id road_network_edges_overpass",
            "python scripts/overpass_ingest.py clean --dataset-id road_network_edges_overpass --raw-path data/raw/osm/overpass_roads_raw.json --cleaned-path data/processed/real_data/road_network_edges.geojson",
            "python scripts/overpass_ingest.py run --dataset-id road_network_edges_overpass",
        ],
        "research_boundary": (
            "This runbook only organizes the current Overpass artifact stack and next-step commands. "
            "It does not download data or prove connectivity."
        ),
    }


def write_overpass_runbook(out_dir: Path | None = None) -> Dict[str, str]:
    report = build_overpass_runbook()
    destination = out_dir or RESULT_DIR
    destination.mkdir(parents=True, exist_ok=True)
    json_path = destination / "overpass_runbook.json"
    md_path = destination / "overpass_runbook.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(
        "\n".join(
            [
                "# Overpass Runbook",
                "",
                "## Artifact Stack",
                "",
                *[
                    f"- {item['name']}: {item['path']} ({item['purpose']})"
                    for item in report.get("artifact_stack", [])
                ],
                "",
                "## Static Execution Commands",
                "",
                *[f"- {cmd}" for cmd in report.get("execution_commands", [])],
                "",
                "## Online Execution Commands",
                "",
                *[f"- {cmd}" for cmd in report.get("online_execution_commands", [])],
                "",
                "## Boundary",
                "",
                str(report.get("research_boundary", "")),
                "",
            ]
        ),
        encoding="utf-8",
    )
    return {"json_path": str(json_path), "md_path": str(md_path)}

