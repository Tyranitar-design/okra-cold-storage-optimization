"""Build a simple guide explaining the Overpass artifact stack."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESULT_DIR = PROJECT_ROOT / "results" / "real_data_sources"


def build_overpass_guide() -> Dict[str, Any]:
    return {
        "source_name": "Overpass guide",
        "sections": [
            {
                "title": "Preview",
                "artifacts": [
                    str(RESULT_DIR / "overpass_ingestion_preview.json"),
                    str(RESULT_DIR / "overpass_ingestion_preview.md"),
                ],
                "meaning": "Static preview of candidate datasets and case bbox.",
            },
            {
                "title": "Preview validation",
                "artifacts": [
                    str(RESULT_DIR / "overpass_ingestion_preview_validation.json"),
                    str(RESULT_DIR / "overpass_ingestion_preview_validation.md"),
                ],
                "meaning": "Checks JSON/MD consistency of the preview.",
            },
            {
                "title": "Request preview",
                "artifacts": [
                    str(RESULT_DIR / "overpass_request_preview_osm_features_overpass.json"),
                    str(RESULT_DIR / "overpass_request_preview_osm_features_overpass.md"),
                ],
                "meaning": "Shows the exact Overpass request that would be sent.",
            },
            {
                "title": "Request validation",
                "artifacts": [
                    str(RESULT_DIR / "overpass_request_preview_validation.json"),
                    str(RESULT_DIR / "overpass_request_preview_validation.md"),
                ],
                "meaning": "Checks JSON/MD consistency of the request preview.",
            },
            {
                "title": "Summary",
                "artifacts": [
                    str(RESULT_DIR / "overpass_artifact_summary.json"),
                    str(RESULT_DIR / "overpass_artifact_summary.md"),
                ],
                "meaning": "Aggregates artifact existence and high-level status.",
            },
            {
                "title": "Runbook",
                "artifacts": [
                    str(RESULT_DIR / "overpass_runbook.json"),
                    str(RESULT_DIR / "overpass_runbook.md"),
                ],
                "meaning": "Lists static commands and online commands for later execution.",
            },
            {
                "title": "Bundle",
                "artifacts": [
                    str(RESULT_DIR / "overpass_bundle.json"),
                    str(RESULT_DIR / "overpass_bundle.md"),
                ],
                "meaning": "Summarizes the current Overpass static bundle status; the refresh entry point is the script.",
            },
        ],
        "online_boundary": (
            "None of these artifacts download external data by themselves. "
            "Real OSM ingestion still requires online download/run execution."
        ),
    }


def write_overpass_guide(out_dir: Path | None = None) -> Dict[str, str]:
    guide = build_overpass_guide()
    destination = out_dir or RESULT_DIR
    destination.mkdir(parents=True, exist_ok=True)
    json_path = destination / "overpass_guide.json"
    md_path = destination / "overpass_guide.md"
    json_path.write_text(json.dumps(guide, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(
        "\n".join(
            [
                "# Overpass Guide",
                "",
                *[
                    f"## {section['title']}\n\n"
                    + "\n".join([f"- {artifact}" for artifact in section.get("artifacts", [])])
                    + f"\n\n{section.get('meaning', '')}"
                    for section in guide.get("sections", [])
                ],
                "",
                "## Online Boundary",
                "",
                str(guide.get("online_boundary", "")),
                "",
            ]
        ),
        encoding="utf-8",
    )
    return {"json_path": str(json_path), "md_path": str(md_path)}
