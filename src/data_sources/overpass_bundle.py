"""Generate and inspect the full static Overpass artifact bundle."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from src.data_sources.overpass_ingestion import write_overpass_ingestion_preview, write_overpass_request_preview
from src.data_sources.overpass_preview_validation import write_overpass_preview_validation
from src.data_sources.overpass_request_validation import write_overpass_request_validation
from src.data_sources.overpass_summary import write_overpass_summary
from src.data_sources.overpass_runbook import write_overpass_runbook


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESULT_DIR = PROJECT_ROOT / "results" / "real_data_sources"


def write_overpass_bundle(out_dir: Path | None = None) -> Dict[str, str]:
    destination = out_dir or RESULT_DIR
    destination.mkdir(parents=True, exist_ok=True)
    outputs: Dict[str, str] = {}
    outputs.update({f"preview_{k}": v for k, v in write_overpass_ingestion_preview(destination).items()})
    outputs.update({f"preview_validation_{k}": v for k, v in write_overpass_preview_validation(destination).items()})
    outputs.update({f"request_preview_{k}": v for k, v in write_overpass_request_preview("osm_features_overpass", destination).items()})
    outputs.update({f"request_validation_{k}": v for k, v in write_overpass_request_validation(destination).items()})
    outputs.update({f"summary_{k}": v for k, v in write_overpass_summary(destination).items()})
    outputs.update({f"runbook_{k}": v for k, v in write_overpass_runbook(destination).items()})
    return outputs


def write_overpass_bundle_report(out_dir: Path | None = None) -> Dict[str, str]:
    destination = out_dir or RESULT_DIR
    destination.mkdir(parents=True, exist_ok=True)
    report = build_overpass_bundle()
    json_path = destination / "overpass_bundle.json"
    md_path = destination / "overpass_bundle.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(
        "\n".join(
            [
                "# Overpass Bundle",
                "",
                "## Files",
                "",
                *[f"- {key}: {value}" for key, value in report.get("files", {}).items()],
                "",
                "## Existence",
                "",
                *[f"- {key}: {value}" for key, value in report.get("exists", {}).items()],
                "",
                f"Existing file count: {report.get('existing_file_count', 0)}",
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


def build_overpass_bundle() -> Dict[str, Any]:
    files = {
        "preview_json_path": str(RESULT_DIR / "overpass_ingestion_preview.json"),
        "preview_md_path": str(RESULT_DIR / "overpass_ingestion_preview.md"),
        "preview_validation_json_path": str(RESULT_DIR / "overpass_ingestion_preview_validation.json"),
        "preview_validation_md_path": str(RESULT_DIR / "overpass_ingestion_preview_validation.md"),
        "request_preview_json_path": str(RESULT_DIR / "overpass_request_preview_osm_features_overpass.json"),
        "request_preview_md_path": str(RESULT_DIR / "overpass_request_preview_osm_features_overpass.md"),
        "request_validation_json_path": str(RESULT_DIR / "overpass_request_preview_validation.json"),
        "request_validation_md_path": str(RESULT_DIR / "overpass_request_preview_validation.md"),
        "summary_json_path": str(RESULT_DIR / "overpass_artifact_summary.json"),
        "summary_md_path": str(RESULT_DIR / "overpass_artifact_summary.md"),
        "runbook_json_path": str(RESULT_DIR / "overpass_runbook.json"),
        "runbook_md_path": str(RESULT_DIR / "overpass_runbook.md"),
        "guide_json_path": str(RESULT_DIR / "overpass_guide.json"),
        "guide_md_path": str(RESULT_DIR / "overpass_guide.md"),
    }
    exists = {key: Path(path).exists() for key, path in files.items()}
    return {
        "source_name": "Overpass bundle",
        "source_backend": "bundle_status",
        "files": files,
        "exists": exists,
        "existing_file_count": sum(1 for value in exists.values() if value),
        "research_boundary": (
            "This is a read-only status report of the Overpass static bundle. "
            "It does not generate files or perform network I/O."
        ),
    }


def build_overpass_bundle_report() -> Dict[str, Any]:
    return build_overpass_bundle()
