"""Validate the static Overpass request preview artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from src.data_sources.overpass_ingestion import build_overpass_request_preview


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESULT_DIR = PROJECT_ROOT / "results" / "real_data_sources"
REQUEST_JSON_PATH = RESULT_DIR / "overpass_request_preview_osm_features_overpass.json"
REQUEST_MD_PATH = RESULT_DIR / "overpass_request_preview_osm_features_overpass.md"


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
    return len(a_seq) == len(b_seq) and all(abs(x - y) < 1e-9 for x, y in zip(a_seq, b_seq))


def build_overpass_request_validation() -> Dict[str, Any]:
    expected = build_overpass_request_preview("osm_features_overpass")
    request_exists = REQUEST_JSON_PATH.exists() and REQUEST_MD_PATH.exists()
    result: Dict[str, Any] = {
        "source_name": "Overpass request preview validation",
        "request_json_path": str(REQUEST_JSON_PATH),
        "request_md_path": str(REQUEST_MD_PATH),
        "request_exists": request_exists,
        "validation_state": "missing_request_artifacts",
        "issues": [],
        "expected_dataset_id": expected.get("dataset_id"),
        "expected_endpoint": expected.get("endpoint"),
        "expected_bbox": expected.get("bbox"),
        "expected_bbox_clause": expected.get("bbox_clause"),
        "expected_timeout_sec": expected.get("timeout_sec"),
        "expected_user_agent": expected.get("user_agent"),
        "research_boundary": (
            "This validator checks only the static request preview artifacts. "
            "It does not download external data or prove Overpass connectivity."
        ),
    }
    if not request_exists:
        result["issues"].append("request_json_or_md_missing")
        return result

    request = _read_json(REQUEST_JSON_PATH)
    request_md = _read_text(REQUEST_MD_PATH)
    issues: List[str] = []
    if request.get("dataset_id") != result["expected_dataset_id"]:
        issues.append("dataset_id_mismatch")
    if request.get("endpoint") != result["expected_endpoint"]:
        issues.append("endpoint_mismatch")
    if not _same_bbox(request.get("bbox"), result["expected_bbox"]):
        issues.append("bbox_mismatch")
    if request.get("bbox_clause") != result["expected_bbox_clause"]:
        issues.append("bbox_clause_mismatch")
    if request.get("timeout_sec") != result["expected_timeout_sec"]:
        issues.append("timeout_sec_mismatch")
    if request.get("user_agent") != result["expected_user_agent"]:
        issues.append("user_agent_mismatch")
    for needle, label in [
        (str(result["expected_bbox_clause"]), "md_bbox_clause_missing"),
        (str(result["expected_endpoint"]), "md_endpoint_missing"),
        (str(result["expected_timeout_sec"]), "md_timeout_missing"),
        (str(result["expected_user_agent"]), "md_user_agent_missing"),
        ("```overpass", "md_code_block_missing"),
    ]:
        if needle not in request_md:
            issues.append(label)

    result["issues"] = issues
    result["request_dataset_id"] = request.get("dataset_id")
    result["request_endpoint"] = request.get("endpoint")
    result["request_bbox"] = request.get("bbox")
    result["request_bbox_clause"] = request.get("bbox_clause")
    result["request_timeout_sec"] = request.get("timeout_sec")
    result["request_user_agent"] = request.get("user_agent")
    result["request_md_contains_bbox_clause"] = str(result["expected_bbox_clause"]) in request_md
    result["request_md_contains_endpoint"] = str(result["expected_endpoint"]) in request_md
    result["request_md_contains_timeout"] = str(result["expected_timeout_sec"]) in request_md
    result["request_md_contains_user_agent"] = str(result["expected_user_agent"]) in request_md
    result["validation_state"] = "validated" if not issues else "validation_mismatch"
    return result


def write_overpass_request_validation(out_dir: Path | None = None) -> Dict[str, str]:
    report = build_overpass_request_validation()
    destination = out_dir or RESULT_DIR
    destination.mkdir(parents=True, exist_ok=True)
    json_path = destination / "overpass_request_preview_validation.json"
    md_path = destination / "overpass_request_preview_validation.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(
        "\n".join(
            [
                "# Overpass Request Preview Validation",
                "",
                f"Validation state: {report.get('validation_state', '')}",
                f"Request exists: {report.get('request_exists', False)}",
                f"Expected dataset ID: {report.get('expected_dataset_id', '')}",
                f"Expected endpoint: {report.get('expected_endpoint', '')}",
                f"Expected bbox clause: {report.get('expected_bbox_clause', '')}",
                f"Expected timeout sec: {report.get('expected_timeout_sec', 0)}",
                f"Expected user agent: {report.get('expected_user_agent', '')}",
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

