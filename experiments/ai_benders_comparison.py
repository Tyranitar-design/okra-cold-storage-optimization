"""AI-Benders comparison experiment.

This experiment expands the method smoke test into several controlled
small-to-medium configurations. It is still not a full-scale proof of
algorithmic superiority, but it generates more cut-score evidence for the
paper and MIS algorithm page.
"""

from __future__ import annotations

import json
import pickle
import sys
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from experiments._shared import save_dataframe_bundle, write_markdown_table  # noqa: E402
from src.algorithms.benders import run_benders  # noqa: E402
from src.algorithms.benders_ai import run_ai_benders  # noqa: E402
from src.models.single_level_mip_v2_1 import DataConfig  # noqa: E402


OUTPUT_ROOT = PROJECT_ROOT / "results" / "experiments" / "ai_benders_comparison"


CASES = [
    {
        "case_id": "AB_5c_6d_strict",
        "candidate_count": 5,
        "demand_count": 6,
        "max_facilities": 2,
        "max_iterations": 5,
        "mip_gap": 0.001,
        "time_limit": 60,
    },
    {
        "case_id": "AB_7c_8d_strict",
        "candidate_count": 7,
        "demand_count": 8,
        "max_facilities": 3,
        "max_iterations": 5,
        "mip_gap": 0.001,
        "time_limit": 90,
    },
    {
        "case_id": "AB_9c_10d_strict",
        "candidate_count": 9,
        "demand_count": 10,
        "max_facilities": 3,
        "max_iterations": 5,
        "mip_gap": 0.001,
        "time_limit": 120,
    },
]


def _case_ids(config: DataConfig, case: dict[str, Any]) -> tuple[list[str], list[str]]:
    candidates = list(config.candidates["node_id"])[: case["candidate_count"]]
    demands = list(config.demands["node_id"])[: case["demand_count"]]
    return candidates, demands


def _method_record(case: dict[str, Any], method_name: str, summary: dict[str, Any]) -> dict[str, Any]:
    iterations = summary.get("iterations", [])
    return {
        "case_id": case["case_id"],
        "method": method_name,
        "candidate_count": case["candidate_count"],
        "demand_count": case["demand_count"],
        "max_facilities": case["max_facilities"],
        "max_iterations": case["max_iterations"],
        "mip_gap_target": case["mip_gap"],
        "upper_bound": summary.get("upper_bound"),
        "lower_bound": summary.get("lower_bound"),
        "final_gap_pct": summary.get("final_gap_pct"),
        "cut_count": summary.get("cut_count"),
        "iteration_count": len(iterations),
        "elapsed_sec": summary.get("elapsed"),
    }


def _ai_detail(case: dict[str, Any], summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "case_id": case["case_id"],
        "ai_cut_policy": summary.get("ai_cut_policy"),
        "ai_score_formula": summary.get("ai_score_formula"),
        "ai_training": summary.get("ai_training", {}),
        "ai_graph_summary": summary.get("ai_graph_summary", {}),
        "ai_feature_importance_top": summary.get("ai_feature_importance_top", []),
        "ai_selection_summary": summary.get("ai_selection_summary", {}),
        "ai_cut_scores": summary.get("ai_cut_scores", []),
        "ai_selected_iterations": summary.get("ai_selected_iterations", []),
        "upper_bound": summary.get("upper_bound"),
        "lower_bound": summary.get("lower_bound"),
        "final_gap_pct": summary.get("final_gap_pct"),
        "cut_count": summary.get("cut_count"),
    }


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    config = DataConfig()

    summary_rows: list[dict[str, Any]] = []
    ai_details: list[dict[str, Any]] = []
    all_cut_scores: list[dict[str, Any]] = []

    for case in CASES:
        candidate_ids, demand_ids = _case_ids(config, case)

        classic = run_benders(
            config,
            candidate_ids=candidate_ids,
            demand_ids=demand_ids,
            max_facilities=case["max_facilities"],
            time_limit=case["time_limit"],
            mip_gap=case["mip_gap"],
            threads=4,
            max_iterations=case["max_iterations"],
            verbose=False,
        )
        summary_rows.append(_method_record(case, "classic_benders", classic))

        ai = run_ai_benders(
            config,
            candidate_ids=candidate_ids,
            demand_ids=demand_ids,
            max_facilities=case["max_facilities"],
            time_limit=case["time_limit"],
            mip_gap=case["mip_gap"],
            threads=4,
            max_iterations=case["max_iterations"],
            top_k_cuts=1,
            verbose=False,
        )
        summary_rows.append(_method_record(case, "ai_benders", ai))
        ai_details.append(_ai_detail(case, ai))
        for record in ai.get("ai_cut_scores", []):
            item = {
                "case_id": case["case_id"],
                "cut_id": record.get("cut_id"),
                "iter_no": record.get("iter_no"),
                "score": record.get("score"),
                "selected": record.get("selected"),
                "rhs": record.get("rhs"),
                "coef_count": record.get("coef_count"),
                "gap_pct": record.get("gap_pct"),
                "policy_name": record.get("policy_name"),
            }
            all_cut_scores.append(item)

        case_path = OUTPUT_ROOT / f"{case['case_id']}_ai_detail.json"
        case_path.write_text(json.dumps(_ai_detail(case, ai), ensure_ascii=False, indent=2), encoding="utf-8")

    summary_df = pd.DataFrame(summary_rows)
    outputs = save_dataframe_bundle(summary_df, OUTPUT_ROOT / "ai_benders_comparison")
    md_path = write_markdown_table(
        summary_df,
        OUTPUT_ROOT / "ai_benders_comparison.md",
        [
            "case_id",
            "method",
            "candidate_count",
            "demand_count",
            "upper_bound",
            "final_gap_pct",
            "cut_count",
            "iteration_count",
            "elapsed_sec",
        ],
    )

    cut_df = pd.DataFrame(all_cut_scores)
    cut_outputs = save_dataframe_bundle(cut_df, OUTPUT_ROOT / "ai_benders_cut_scores")

    summary_json = OUTPUT_ROOT / "ai_benders_comparison_summary.json"
    summary_json.write_text(
        json.dumps(
            {
                "cases": CASES,
                "summary_rows": summary_rows,
                "ai_details": ai_details,
                "cut_score_rows": all_cut_scores,
                "files": {k: str(v) for k, v in outputs.items()},
                "cut_score_files": {k: str(v) for k, v in cut_outputs.items()},
                "markdown": str(md_path),
                "research_boundary": "Controlled small-to-medium comparison; not yet full benchmark proof.",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    with open(OUTPUT_ROOT / "ai_benders_comparison.pkl", "wb") as fh:
        pickle.dump({"summary_rows": summary_rows, "ai_details": ai_details, "cut_score_rows": all_cut_scores}, fh)

    print(outputs["csv"])
    print(cut_outputs["csv"])
    print(md_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
