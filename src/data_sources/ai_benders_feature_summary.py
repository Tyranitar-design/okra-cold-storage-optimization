"""Build a cross-case feature summary for the Benders cut-ranking evidence stack."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESULTS_ROOT = PROJECT_ROOT / "results"
AI_BENDERS_ANALYSIS_REPORT_PATH = RESULTS_ROOT / "ai_benders_analysis_report.json"
AI_BENDERS_FEATURE_SUMMARY_JSON_PATH = RESULTS_ROOT / "ai_benders_feature_summary.json"
AI_BENDERS_FEATURE_SUMMARY_MD_PATH = RESULTS_ROOT / "ai_benders_feature_summary.md"


def _load_json(path: Path) -> Dict[str, Any] | None:
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {"value": payload}


def build_ai_benders_feature_summary() -> Dict[str, Any]:
    analysis = _load_json(AI_BENDERS_ANALYSIS_REPORT_PATH)
    top_feature_sets = analysis.get("top_feature_sets", []) if analysis else []
    case_ids = analysis.get("detail_case_ids", []) if analysis else []

    counter: Counter[str] = Counter()
    for feature_list in top_feature_sets:
        if isinstance(feature_list, list):
            counter.update(str(feature) for feature in feature_list if feature)

    feature_frequency = [
        {
            "feature": feature,
            "case_count": count,
            "coverage_pct": round(count / len(top_feature_sets) * 100.0, 2) if top_feature_sets else None,
        }
        for feature, count in counter.most_common()
    ]
    shared_features = [item for item in feature_frequency if item["case_count"] >= 2]

    report = {
        "source_name": "Benders cut-ranking feature summary",
        "result_paths": {
            "json": str(AI_BENDERS_FEATURE_SUMMARY_JSON_PATH),
            "md": str(AI_BENDERS_FEATURE_SUMMARY_MD_PATH),
            "analysis_report": str(AI_BENDERS_ANALYSIS_REPORT_PATH),
        },
        "counts": {
            "case_count": len(top_feature_sets),
            "unique_feature_count": len(counter),
            "shared_feature_count": len(shared_features),
        },
        "summary": {
            "dominant_feature": feature_frequency[0]["feature"] if feature_frequency else None,
            "dominant_feature_case_count": feature_frequency[0]["case_count"] if feature_frequency else 0,
            "shared_features": shared_features,
        },
        "case_ids": case_ids,
        "top_feature_sets": top_feature_sets,
        "feature_frequency": feature_frequency,
        "research_boundary": (
            "This feature summary is derived from the existing Benders cut-ranking analysis report. "
            "It summarizes cross-case feature recurrence and does not retrain the model or recompute Benders."
        ),
    }
    return report


def write_ai_benders_feature_summary(out_dir: Path | None = None) -> Dict[str, str]:
    destination = out_dir or RESULTS_ROOT
    destination.mkdir(parents=True, exist_ok=True)
    report = build_ai_benders_feature_summary()
    json_path = destination / "ai_benders_feature_summary.json"
    md_path = destination / "ai_benders_feature_summary.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(
        "\n".join(
            [
                "# Benders Cut-Ranking Feature Summary",
                "",
                "## Summary",
                "",
                *[f"- {key}: {value}" for key, value in report.get("summary", {}).items()],
                "",
                "## Feature Frequency",
                "",
                *[
                    f"- {item.get('feature', '')}: case_count={item.get('case_count', '')}, coverage_pct={item.get('coverage_pct', '')}"
                    for item in report.get("feature_frequency", [])
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


def write_ai_benders_feature_summary_bundle(out_dir: Path | None = None) -> Dict[str, str]:
    return write_ai_benders_feature_summary(out_dir)
