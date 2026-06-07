"""Validate the static Overpass ingestion preview artifacts.

This validator does not download data. It checks that the materialized preview
artifacts remain consistent with the current code-derived preview contract.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from src.data_sources.overpass_ingestion import build_overpass_ingestion_preview


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESULT_DIR = PROJECT_ROOT / "results" / "real_data_sources"
PREVIEW_JSON_PATH = RESULT_DIR / "overpass_ingestion_preview.json"
PREVIEW_MD_PATH = RESULT_DIR / "overpass_ingestion_preview.md"


def _read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _same_bbox(a: Any, b: Any) -> bool:
    try:
        a_seq = [float(x) for x in a]
        b_seq = [float(x) for x in b]
    except Exception:
        return False
    if len(a_seq) != len(b_seq):
        return False
    return all(abs(x - y) < 1e-9 for x, y in zip(a_seq, b_seq))


def build_overpass_preview_validation() -> Dict[str, Any]:
    expected = build_overpass_ingestion_preview()
    preview_exists = PREVIEW_JSON_PATH.exists() and PREVIEW_MD_PATH.exists()
    result: Dict[str, Any] = {
        "source_name": "Overpass ingestion preview validation",
        "preview_json_path": str(PREVIEW_JSON_PATH),
        "preview_md_path": str(PREVIEW_MD_PATH),
        "preview_exists": preview_exists,
        "validation_state": "missing_preview_artifacts",
        "issues": [],
        "expected_dataset_count": expected.get("dataset_count", 0),
        "expected_bbox": expected.get("bbox"),
        "expected_case_nodes_exists": expected.get("case_nodes_exists"),
        "expected_bbox_clause": expected.get("bbox_info", {}).get("bbox_clause"),
        "expected_dataset_ids": [item.get("dataset_id") for item in expected.get("datasets", [])],
        "research_boundary": (
            "This validator checks only the static preview artifacts. "
            "It does not download external data or prove Overpass connectivity."
        ),
    }
    if not preview_exists:
        result["issues"].append("preview_json_or_md_missing")
        return result

    preview = _read_json(PREVIEW_JSON_PATH)
    preview_md = _read_text(PREVIEW_MD_PATH)
    issues: List[str] = []
    if preview.get("dataset_count") != result["expected_dataset_count"]:
        issues.append("dataset_count_mismatch")
    if not _same_bbox(preview.get("bbox"), result["expected_bbox"]):
        issues.append("bbox_mismatch")
    if preview.get("case_nodes_exists") != result["expected_case_nodes_exists"]:
        issues.append("case_nodes_exists_mismatch")
    if preview.get("bbox_info", {}).get("bbox_clause") != result["expected_bbox_clause"]:
        issues.append("bbox_clause_mismatch")
    dataset_ids = [item.get("dataset_id") for item in preview.get("datasets", [])]
    if dataset_ids != result["expected_dataset_ids"]:
        issues.append("dataset_id_mismatch")
    if str(result["expected_bbox_clause"]) not in preview_md:
        issues.append("md_bbox_clause_missing")
    if str(result["expected_dataset_count"]) not in preview_md:
        issues.append("md_dataset_count_missing")
    if str(result["expected_case_nodes_exists"]) not in preview_md:
        issues.append("md_case_nodes_exists_missing")
    for dataset_id in result["expected_dataset_ids"]:
        if str(dataset_id) not in preview_md:
            issues.append(f"md_missing_{dataset_id}")

    result["issues"] = issues
    result["preview_dataset_count"] = preview.get("dataset_count")
    result["preview_bbox"] = preview.get("bbox")
    result["preview_case_nodes_exists"] = preview.get("case_nodes_exists")
    result["preview_bbox_clause"] = preview.get("bbox_info", {}).get("bbox_clause")
    result["preview_md_path"] = str(PREVIEW_MD_PATH)
    result["preview_md_contains_bbox_clause"] = str(result["expected_bbox_clause"]) in preview_md
    result["preview_md_contains_dataset_count"] = str(result["expected_dataset_count"]) in preview_md
    result["preview_md_contains_case_nodes_exists"] = str(result["expected_case_nodes_exists"]) in preview_md
    result["validation_state"] = "validated" if not issues else "validation_mismatch"
    return result


def write_overpass_preview_validation(out_dir: Path | None = None) -> Dict[str, str]:
    report = build_overpass_preview_validation()
    destination = out_dir or RESULT_DIR
    destination.mkdir(parents=True, exist_ok=True)
    json_path = destination / "overpass_ingestion_preview_validation.json"
    md_path = destination / "overpass_ingestion_preview_validation.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(
        "\n".join(
            [
                "# Overpass Ingestion Preview Validation",
                "",
                f"Validation state: {report.get('validation_state', '')}",
                f"Preview exists: {report.get('preview_exists', False)}",
                f"Expected dataset count: {report.get('expected_dataset_count', 0)}",
                f"Expected bbox: {report.get('expected_bbox', [])}",
                f"Expected case_nodes_exists: {report.get('expected_case_nodes_exists', False)}",
                f"MD contains bbox clause: {report.get('preview_md_contains_bbox_clause', False)}",
                f"MD contains dataset count: {report.get('preview_md_contains_dataset_count', False)}",
                f"MD contains case nodes exists: {report.get('preview_md_contains_case_nodes_exists', False)}",
                f"Issues: {', '.join(report.get('issues', [])) or 'none'}",
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
