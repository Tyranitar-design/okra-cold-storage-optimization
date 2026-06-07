"""Build a compact analysis report for the Benders cut-ranking evidence stack."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESULTS_ROOT = PROJECT_ROOT / "results"
EXPERIMENTS_ROOT = RESULTS_ROOT / "experiments"
AI_BENDERS_SUMMARY_PATH = EXPERIMENTS_ROOT / "ai_benders_comparison" / "ai_benders_comparison_summary.json"
AI_BENDERS_DETAIL_PATHS = sorted((EXPERIMENTS_ROOT / "ai_benders_comparison").glob("*_ai_detail.json"))
AI_BENDERS_CUT_PATH = EXPERIMENTS_ROOT / "ai_benders_comparison" / "ai_benders_cut_scores.csv"
AI_BENDERS_ANALYSIS_JSON_PATH = RESULTS_ROOT / "ai_benders_analysis_report.json"
AI_BENDERS_ANALYSIS_MD_PATH = RESULTS_ROOT / "ai_benders_analysis_report.md"


def _load_json(path: Path) -> Dict[str, Any] | None:
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {"value": payload}


def _safe_min(values: List[float]) -> float | None:
    return min(values) if values else None


def _safe_max(values: List[float]) -> float | None:
    return max(values) if values else None


def _safe_mean(values: List[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _safe_ratio(numerator: float | None, denominator: float | None) -> float | None:
    if not isinstance(numerator, (int, float)) or not isinstance(denominator, (int, float)) or not denominator:
        return None
    return numerator / denominator * 100.0


def build_ai_benders_analysis_report() -> Dict[str, Any]:
    summary = _load_json(AI_BENDERS_SUMMARY_PATH)
    summary_rows = summary.get("summary_rows", []) if summary else []
    ai_rows = [row for row in summary_rows if row.get("method") == "ai_benders"]
    classic_rows = [row for row in summary_rows if row.get("method") == "classic_benders"]
    detail_payloads = [payload for path in AI_BENDERS_DETAIL_PATHS if (payload := _load_json(path))]

    runtime_deltas: List[float] = []
    gap_deltas: List[float] = []
    cut_deltas: List[float] = []
    case_summaries: List[Dict[str, Any]] = []

    for classic_row in classic_rows:
        match = next((row for row in ai_rows if row.get("case_id") == classic_row.get("case_id")), None)
        if not match:
            continue
        classic_runtime = classic_row.get("elapsed_sec")
        ai_runtime = match.get("elapsed_sec")
        classic_gap = classic_row.get("final_gap_pct")
        ai_gap = match.get("final_gap_pct")
        classic_cut = classic_row.get("cut_count")
        ai_cut = match.get("cut_count")
        runtime_delta = _safe_ratio(classic_runtime - ai_runtime if isinstance(classic_runtime, (int, float)) and isinstance(ai_runtime, (int, float)) else None, classic_runtime)
        if runtime_delta is not None:
            runtime_deltas.append(runtime_delta)
        if isinstance(classic_gap, (int, float)) and isinstance(ai_gap, (int, float)):
            gap_deltas.append(classic_gap - ai_gap)
        if isinstance(classic_cut, (int, float)) and isinstance(ai_cut, (int, float)):
            cut_deltas.append(classic_cut - ai_cut)
        case_summaries.append(
            {
                "case_id": classic_row.get("case_id"),
                "classic_runtime_sec": classic_runtime,
                "ai_runtime_sec": ai_runtime,
                "runtime_speedup_pct": runtime_delta,
                "classic_gap_pct": classic_gap,
                "ai_gap_pct": ai_gap,
                "gap_delta_pct_points": classic_gap - ai_gap if isinstance(classic_gap, (int, float)) and isinstance(ai_gap, (int, float)) else None,
                "classic_cut_count": classic_cut,
                "ai_cut_count": ai_cut,
                "cut_delta": classic_cut - ai_cut if isinstance(classic_cut, (int, float)) and isinstance(ai_cut, (int, float)) else None,
            }
        )

    all_selected_cut_count = 0
    final_losses: List[float] = []
    graph_embedding_dims: List[int] = []
    top_feature_sets: List[List[str]] = []
    policy_names: List[str] = []
    selected_indices: List[List[int]] = []
    detail_case_ids: List[str] = []

    for detail in detail_payloads:
        detail_case_ids.append(str(detail.get("case_id", "")))
        policy_names.append(str(detail.get("ai_cut_policy", "")))
        ai_training = detail.get("ai_training", {}) if isinstance(detail.get("ai_training"), dict) else {}
        ai_graph_summary = detail.get("ai_graph_summary", {}) if isinstance(detail.get("ai_graph_summary"), dict) else {}
        final_loss = ai_training.get("final_loss")
        if isinstance(final_loss, (int, float)):
            final_losses.append(float(final_loss))
        embedding_dim = ai_graph_summary.get("embedding_dim")
        if isinstance(embedding_dim, (int, float)):
            graph_embedding_dims.append(int(embedding_dim))
        selected = ai_training.get("selected_cut_indices", [])
        if isinstance(selected, list):
            all_selected_cut_count += len(selected)
            selected_indices.append([int(idx) for idx in selected if isinstance(idx, (int, float))])
        features = detail.get("ai_feature_importance_top", [])
        if isinstance(features, list):
            top_feature_sets.append([str(item.get("feature")) for item in features if isinstance(item, dict) and item.get("feature")])

    selected_cut_rows = 0
    if AI_BENDERS_CUT_PATH.exists():
        selected_cut_rows = sum(1 for line in AI_BENDERS_CUT_PATH.read_text(encoding="utf-8").splitlines()[1:] if line.strip())

    report = {
        "source_name": "Benders cut-ranking analysis report",
        "result_paths": {
            "json": str(AI_BENDERS_ANALYSIS_JSON_PATH),
            "md": str(AI_BENDERS_ANALYSIS_MD_PATH),
            "ai_benders_summary": str(AI_BENDERS_SUMMARY_PATH),
            "ai_benders_detail_files": [str(path) for path in AI_BENDERS_DETAIL_PATHS],
            "ai_benders_cut_scores": str(AI_BENDERS_CUT_PATH),
        },
        "counts": {
            "cases": len(summary.get("cases", [])) if summary else 0,
            "summary_rows": len(summary_rows),
            "classic_rows": len(classic_rows),
            "ai_rows": len(ai_rows),
            "detail_files": len(detail_payloads),
            "cut_score_rows": selected_cut_rows,
        },
        "summary": {
            "runtime_speedup_pct_mean": _safe_mean(runtime_deltas),
            "runtime_speedup_pct_min": _safe_min(runtime_deltas),
            "runtime_speedup_pct_max": _safe_max(runtime_deltas),
            "gap_delta_pct_points_mean": _safe_mean(gap_deltas),
            "cut_delta_mean": _safe_mean(cut_deltas),
            "selected_cut_count_total": all_selected_cut_count,
            "final_loss_mean": _safe_mean(final_losses),
            "graph_embedding_dim": graph_embedding_dims[0] if graph_embedding_dims else None,
        },
        "case_summaries": case_summaries,
        "detail_case_ids": detail_case_ids,
        "ai_cut_policy_names": policy_names,
        "selected_cut_indices": selected_indices,
        "top_feature_sets": top_feature_sets,
        "research_boundary": (
            "This analysis report is derived from existing Benders cut-ranking summary/detail artifacts. "
            "It summarizes empirical behavior and does not recompute Benders or train a new model."
        ),
    }
    return report


def write_ai_benders_analysis_report(out_dir: Path | None = None) -> Dict[str, str]:
    destination = out_dir or RESULTS_ROOT
    destination.mkdir(parents=True, exist_ok=True)
    report = build_ai_benders_analysis_report()
    json_path = destination / "ai_benders_analysis_report.json"
    md_path = destination / "ai_benders_analysis_report.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(
        "\n".join(
            [
                "# Benders Cut-Ranking Analysis Report",
                "",
                "## Summary",
                "",
                *[f"- {key}: {value}" for key, value in report.get("summary", {}).items()],
                "",
                "## Case Summaries",
                "",
                *[
                    f"- {item.get('case_id', '')}: classic_runtime={item.get('classic_runtime_sec', '')}, ai_runtime={item.get('ai_runtime_sec', '')}, "
                    f"runtime_speedup_pct={item.get('runtime_speedup_pct', '')}, gap_delta_pct_points={item.get('gap_delta_pct_points', '')}, cut_delta={item.get('cut_delta', '')}"
                    for item in report.get("case_summaries", [])
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


def write_ai_benders_analysis_report_bundle(out_dir: Path | None = None) -> Dict[str, str]:
    return write_ai_benders_analysis_report(out_dir)
