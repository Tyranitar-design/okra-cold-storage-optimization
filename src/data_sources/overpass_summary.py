"""Summarize the current Overpass preview/request/validation artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESULT_DIR = PROJECT_ROOT / "results" / "real_data_sources"
PREVIEW_JSON_PATH = RESULT_DIR / "overpass_ingestion_preview.json"
PREVIEW_VALIDATION_JSON_PATH = RESULT_DIR / "overpass_ingestion_preview_validation.json"
REQUEST_JSON_PATH = RESULT_DIR / "overpass_request_preview_osm_features_overpass.json"
REQUEST_VALIDATION_JSON_PATH = RESULT_DIR / "overpass_request_preview_validation.json"


def _load_json(path: Path) -> Dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def build_overpass_summary() -> Dict[str, Any]:
    preview = _load_json(PREVIEW_JSON_PATH)
    preview_validation = _load_json(PREVIEW_VALIDATION_JSON_PATH)
    request_preview = _load_json(REQUEST_JSON_PATH)
    request_validation = _load_json(REQUEST_VALIDATION_JSON_PATH)
    artifact_paths = {
        "preview_json": str(PREVIEW_JSON_PATH),
        "preview_validation_json": str(PREVIEW_VALIDATION_JSON_PATH),
        "request_json": str(REQUEST_JSON_PATH),
        "request_validation_json": str(REQUEST_VALIDATION_JSON_PATH),
    }
    return {
        "source_name": "Overpass artifact summary",
        "artifact_paths": artifact_paths,
        "preview": preview,
        "preview_validation": preview_validation,
        "request_preview": request_preview,
        "request_validation": request_validation,
        "counts": {
            "preview_exists": preview is not None,
            "preview_validation_exists": preview_validation is not None,
            "request_preview_exists": request_preview is not None,
            "request_validation_exists": request_validation is not None,
        },
        "research_boundary": (
            "This is a static summary of existing Overpass preview artifacts. "
            "It does not download data or prove connectivity."
        ),
    }


def write_overpass_summary(out_dir: Path | None = None) -> Dict[str, str]:
    summary = build_overpass_summary()
    destination = out_dir or RESULT_DIR
    destination.mkdir(parents=True, exist_ok=True)
    json_path = destination / "overpass_artifact_summary.json"
    md_path = destination / "overpass_artifact_summary.md"
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(
        "\n".join(
            [
                "# Overpass Artifact Summary",
                "",
                f"Preview exists: {summary.get('counts', {}).get('preview_exists', False)}",
                f"Preview validation exists: {summary.get('counts', {}).get('preview_validation_exists', False)}",
                f"Request preview exists: {summary.get('counts', {}).get('request_preview_exists', False)}",
                f"Request validation exists: {summary.get('counts', {}).get('request_validation_exists', False)}",
                "",
                "## Artifact Paths",
                "",
                *[f"- {k}: {v}" for k, v in summary.get("artifact_paths", {}).items()],
                "",
                "## Boundary",
                "",
                str(summary.get("research_boundary", "")),
                "",
            ]
        ),
        encoding="utf-8",
    )
    return {"json_path": str(json_path), "md_path": str(md_path)}

