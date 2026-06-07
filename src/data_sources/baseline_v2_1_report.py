"""Build a formal report for the baseline v2.1 optimization result."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import numpy as np

from src.api.services import load_pickle_payload


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = PROJECT_ROOT / "results"
BASELINE_RESULT_PATH = RESULTS_DIR / "baseline_v2_1_result.pkl"
BASELINE_REPORT_JSON_PATH = RESULTS_DIR / "baseline_v2_1_report.json"
BASELINE_REPORT_MD_PATH = RESULTS_DIR / "baseline_v2_1_report.md"


def _safe_get(payload: Dict[str, Any], *keys: str, default: Any = None) -> Any:
    current: Any = payload
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(val) for key, val in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    return value


def build_baseline_v2_1_report() -> Dict[str, Any]:
    payload = load_pickle_payload(BASELINE_RESULT_PATH) if BASELINE_RESULT_PATH.exists() else {}
    analysis = payload.get("analysis", payload if isinstance(payload, dict) else {})
    facilities = analysis.get("facilities", []) if isinstance(analysis, dict) else []
    report = {
        "source_name": "Baseline v2.1 report",
        "source": "results/baseline_v2_1_result.pkl",
        "result_paths": {
            "pickle": str(BASELINE_RESULT_PATH),
            "json": str(BASELINE_REPORT_JSON_PATH),
            "md": str(BASELINE_REPORT_MD_PATH),
        },
        "exists": {
            "pickle": BASELINE_RESULT_PATH.exists(),
            "analysis": bool(analysis),
        },
        "summary": {
            "total_cost": _safe_get(analysis, "total_cost"),
            "fixed_cost": _safe_get(analysis, "fixed_cost"),
            "operate_cost": _safe_get(analysis, "operate_cost"),
            "transport_cost": _safe_get(analysis, "transport_cost"),
            "loss_cost": _safe_get(analysis, "loss_cost"),
            "carbon_cost": _safe_get(analysis, "carbon_cost"),
            "num_facilities": _safe_get(analysis, "num_facilities"),
            "precool_violations": _safe_get(analysis, "precool_violations"),
            "elapsed": payload.get("elapsed") if isinstance(payload, dict) else None,
        },
        "facilities": facilities,
        "research_boundary": (
            "This report is a formal packaging of the existing baseline v2.1 result. "
            "It does not recompute the optimization model."
        ),
    }
    return _json_safe(report)


def write_baseline_v2_1_report(out_dir: Path | None = None) -> Dict[str, str]:
    destination = out_dir or RESULTS_DIR
    destination.mkdir(parents=True, exist_ok=True)
    report = build_baseline_v2_1_report()
    json_path = destination / "baseline_v2_1_report.json"
    md_path = destination / "baseline_v2_1_report.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(
        "\n".join(
            [
                "# Baseline v2.1 Report",
                "",
                f"- Pickle exists: {report.get('exists', {}).get('pickle', False)}",
                f"- Analysis exists: {report.get('exists', {}).get('analysis', False)}",
                "",
                "## Summary",
                "",
                *[
                    f"- {key}: {value}"
                    for key, value in report.get("summary", {}).items()
                ],
                "",
                "## Facilities",
                "",
                *[
                    f"- {item.get('site', '')} | {item.get('type_name', '')} | {item.get('capacity', '')} 吨 | 利用率 {item.get('utilization', ''):.1f}%"
                    if isinstance(item.get("utilization"), (int, float))
                    else f"- {item.get('site', '')} | {item.get('type_name', '')} | {item.get('capacity', '')} 吨"
                    for item in report.get("facilities", [])
                ],
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
