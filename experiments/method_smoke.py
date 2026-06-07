"""
方法层烟雾测试汇总。

目标：
- 验证双层 KKT
- 验证 ε-约束
- 验证经典 Benders 与 AI-Benders
- 验证 SPO 参数学习
"""

from __future__ import annotations

import json
import pickle
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from experiments._shared import save_dataframe_bundle, write_markdown_table  # noqa: E402
from src.algorithms.benders import run_benders  # noqa: E402
from src.algorithms.benders_ai import run_ai_benders  # noqa: E402
from src.data_driven.spo_pipeline import run_spo_pipeline  # noqa: E402
from src.models.epsilon_constraint import build_epsilon_model  # noqa: E402
from src.models.single_level_mip_v2_1 import DataConfig  # noqa: E402
from src.models.bilevel_kkt import build_and_solve_bilevel_kkt  # noqa: E402


OUTPUT_ROOT = PROJECT_ROOT / "results" / "experiments" / "method_smoke"


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    config = DataConfig()
    candidate_ids = list(config.candidates["node_id"])[:5]
    demand_ids = list(config.demands["node_id"])[:6]

    rows = []

    kkt_model, _, _, kkt_analysis = build_and_solve_bilevel_kkt(
        config,
        candidate_ids=candidate_ids,
        demand_ids=demand_ids,
        max_facilities=2,
        time_limit=60,
        mip_gap=0.05,
        threads=4,
        verbose=False,
    )
    rows.append(
        {
            "method": "KKT_bilevel",
            "status": int(kkt_analysis["status"]),
            "objective": kkt_analysis["total_cost"],
            "metric_1": kkt_analysis["num_facilities"],
            "metric_2": kkt_analysis["precool_violations"],
            "runtime_sec": kkt_analysis["elapsed"],
            "note": "small-instance smoke test",
        }
    )

    eps_model, _, _, eps_analysis = build_epsilon_model(
        config,
        candidate_ids=candidate_ids,
        demand_ids=demand_ids,
        max_facilities=2,
        time_limit=60,
        mip_gap=0.05,
        threads=4,
        verbose=False,
    )
    rows.append(
        {
            "method": "epsilon_constraint",
            "status": int(eps_analysis["status"]),
            "objective": eps_analysis["total_cost"],
            "metric_1": eps_analysis["loss_ton"],
            "metric_2": eps_analysis["carbon_ton"],
            "runtime_sec": eps_analysis["elapsed"],
            "note": "small-instance smoke test",
        }
    )

    benders_summary = run_benders(
        config,
        candidate_ids=candidate_ids,
        demand_ids=demand_ids,
        max_facilities=2,
        time_limit=60,
        mip_gap=0.05,
        threads=4,
        max_iterations=3,
        verbose=False,
    )
    rows.append(
        {
            "method": "benders",
            "status": 2 if benders_summary["upper_bound"] is not None else 0,
            "objective": benders_summary["upper_bound"],
            "metric_1": benders_summary["cut_count"],
            "metric_2": benders_summary["final_gap_pct"],
            "runtime_sec": benders_summary["elapsed"],
            "note": "classic decomposition",
        }
    )

    ai_benders_summary = run_ai_benders(
        config,
        candidate_ids=candidate_ids,
        demand_ids=demand_ids,
        max_facilities=2,
        time_limit=60,
        mip_gap=0.05,
        threads=4,
        max_iterations=3,
        top_k_cuts=1,
        verbose=False,
    )
    rows.append(
        {
            "method": "ai_benders",
            "status": 2 if ai_benders_summary["upper_bound"] is not None else 0,
            "objective": ai_benders_summary["upper_bound"],
            "metric_1": ai_benders_summary["cut_count"],
            "metric_2": ai_benders_summary["final_gap_pct"],
            "runtime_sec": ai_benders_summary["elapsed"],
            "note": ai_benders_summary["ai_cut_policy"],
        }
    )

    ai_detail_path = OUTPUT_ROOT / "ai_benders_detail.json"
    ai_detail_path.write_text(
        json.dumps(
            {
                "ai_cut_policy": ai_benders_summary.get("ai_cut_policy"),
                "ai_score_formula": ai_benders_summary.get("ai_score_formula"),
                "ai_training": ai_benders_summary.get("ai_training", {}),
                "ai_graph_summary": ai_benders_summary.get("ai_graph_summary", {}),
                "ai_feature_importance_top": ai_benders_summary.get("ai_feature_importance_top", []),
                "ai_selection_summary": ai_benders_summary.get("ai_selection_summary", {}),
                "ai_cut_scores": ai_benders_summary.get("ai_cut_scores", []),
                "ai_selected_iterations": ai_benders_summary.get("ai_selected_iterations", []),
                "note": "structured AI-Benders evidence bundle for paper and MIS ingestion",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    spo_summary = run_spo_pipeline(
        config,
        output_dir=OUTPUT_ROOT / "spo",
        samples_per_combination=2,
        random_state=42,
    )
    rows.append(
        {
            "method": "spo_pipeline",
            "status": 1,
            "objective": None,
            "metric_1": spo_summary["metrics"]["alpha_r2"],
            "metric_2": spo_summary["metrics"]["beta_r2"],
            "runtime_sec": None,
            "note": f"rows={spo_summary['dataset_rows']}",
        }
    )

    df = pd.DataFrame(rows)
    outputs = save_dataframe_bundle(df, OUTPUT_ROOT / "method_smoke_summary")
    md_path = write_markdown_table(
        df,
        OUTPUT_ROOT / "method_smoke_summary.md",
        ["method", "status", "objective", "metric_1", "metric_2", "runtime_sec", "note"],
    )

    summary_json = OUTPUT_ROOT / "method_smoke_summary.json"
    summary_json.write_text(
        json.dumps(
            {
                "rows": rows,
                "files": {k: str(v) for k, v in outputs.items()},
                "markdown": str(md_path),
                "ai_benders_detail": str(ai_detail_path),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    with open(OUTPUT_ROOT / "method_smoke_summary.pkl", "wb") as fh:
        pickle.dump(rows, fh)

    print(outputs["csv"])
    print(md_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
