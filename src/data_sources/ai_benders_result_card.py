"""Build a compact presentation card for Benders cut-ranking case evidence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from src.data_sources.ai_benders_analysis_report import build_ai_benders_analysis_report


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESULTS_ROOT = PROJECT_ROOT / "results"
AI_BENDERS_RESULT_CARD_JSON_PATH = RESULTS_ROOT / "ai_benders_result_card.json"
AI_BENDERS_RESULT_CARD_MD_PATH = RESULTS_ROOT / "ai_benders_result_card.md"


def _feature_sets_by_case(report: Dict[str, Any]) -> Dict[str, List[str]]:
    case_ids = report.get("detail_case_ids", [])
    feature_sets = report.get("top_feature_sets", [])
    mapping: Dict[str, List[str]] = {}
    for case_id, features in zip(case_ids, feature_sets):
        if isinstance(case_id, str) and isinstance(features, list):
            mapping[case_id] = [str(feature) for feature in features if feature]
    return mapping


def _selected_cut_by_case(report: Dict[str, Any]) -> Dict[str, int | None]:
    case_ids = report.get("detail_case_ids", [])
    selected_indices = report.get("selected_cut_indices", [])
    mapping: Dict[str, int | None] = {}
    for case_id, selected in zip(case_ids, selected_indices):
        if not isinstance(case_id, str):
            continue
        first_index = selected[0] if isinstance(selected, list) and selected else None
        mapping[case_id] = int(first_index) if isinstance(first_index, (int, float)) else None
    return mapping


def build_ai_benders_result_card() -> Dict[str, Any]:
    analysis = build_ai_benders_analysis_report()
    feature_sets = _feature_sets_by_case(analysis)
    selected_cuts = _selected_cut_by_case(analysis)

    rows = []
    for item in analysis.get("case_summaries", []):
        if not isinstance(item, dict):
            continue
        case_id = str(item.get("case_id", ""))
        rows.append(
            {
                "case_id": case_id,
                "classic_runtime_sec": item.get("classic_runtime_sec"),
                "ai_runtime_sec": item.get("ai_runtime_sec"),
                "runtime_delta_pct": item.get("runtime_speedup_pct"),
                "classic_gap_pct": item.get("classic_gap_pct"),
                "ai_gap_pct": item.get("ai_gap_pct"),
                "cut_count": item.get("ai_cut_count"),
                "selected_cut_index": selected_cuts.get(case_id),
                "top_features": feature_sets.get(case_id, []),
            }
        )

    report = {
        "source_name": "Benders cut-ranking result card",
        "result_paths": {
            "json": str(AI_BENDERS_RESULT_CARD_JSON_PATH),
            "md": str(AI_BENDERS_RESULT_CARD_MD_PATH),
            "analysis_report": str(analysis.get("result_paths", {}).get("json", "")),
        },
        "counts": {
            "cases": len(rows),
            "detail_files": analysis.get("counts", {}).get("detail_files", 0),
            "selected_cut_count_total": analysis.get("summary", {}).get("selected_cut_count_total", 0),
        },
        "summary": {
            "runtime_delta_pct_mean": analysis.get("summary", {}).get("runtime_speedup_pct_mean"),
            "gap_delta_pct_points_mean": analysis.get("summary", {}).get("gap_delta_pct_points_mean"),
            "cut_delta_mean": analysis.get("summary", {}).get("cut_delta_mean"),
            "graph_embedding_dim": analysis.get("summary", {}).get("graph_embedding_dim"),
        },
        "rows": rows,
        "research_boundary": (
            "This result card is a presentation layer over existing Benders cut-ranking detail files and "
            "summary statistics. It does not retrain the model or recompute Benders."
        ),
    }
    return report


def write_ai_benders_result_card(out_dir: Path | None = None) -> Dict[str, str]:
    destination = out_dir or RESULTS_ROOT
    destination.mkdir(parents=True, exist_ok=True)
    report = build_ai_benders_result_card()
    json_path = destination / "ai_benders_result_card.json"
    md_path = destination / "ai_benders_result_card.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(
        "\n".join(
            [
                "# Benders Cut-Ranking Result Card",
                "",
                "## Case-Level Summary",
                "",
                "| Case | Classic runtime (s) | AI runtime (s) | Runtime delta (%) | Classic gap (%) | AI gap (%) | Cut count | Selected cut index | Top features |",
                "|---|---:|---:|---:|---:|---:|---:|---:|---|",
                *[
                    f"| {row.get('case_id', '')} | {row.get('classic_runtime_sec', '')} | {row.get('ai_runtime_sec', '')} | "
                    f"{row.get('runtime_delta_pct', '')} | {row.get('classic_gap_pct', '')} | {row.get('ai_gap_pct', '')} | "
                    f"{row.get('cut_count', '')} | {row.get('selected_cut_index', '')} | {', '.join(row.get('top_features', []))} |"
                    for row in report.get("rows", [])
                ],
                "",
                "## Aggregate Notes",
                "",
                *[f"- {key}: {value}" for key, value in report.get("counts", {}).items()],
                *[f"- {key}: {value}" for key, value in report.get("summary", {}).items()],
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


def write_ai_benders_result_card_bundle(out_dir: Path | None = None) -> Dict[str, str]:
    return write_ai_benders_result_card(out_dir)
