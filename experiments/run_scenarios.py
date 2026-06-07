"""
四场景候选点对比实验。

S1: 9 个候选点（县 + 乡镇）
S2: 18 个候选点（县 + 乡镇 + 9 个高产村）
S3: 27 个候选点（全部候选点）
S4: 39 个候选点（全部节点）
"""

from __future__ import annotations

import os
import pickle
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd

from experiments._shared import (
    FIGURE_ROOT,
    SCENARIO_ROOT,
    build_result_record,
    get_scenario_candidate_sets,
    load_config,
    save_dataframe_bundle,
    write_markdown_table,
)
from src.models.single_level_mip_v2_1 import analyze_results, build_and_solve_v2
from src.utils.visualization import (
    save_cost_breakdown_chart,
    save_layout_map,
    save_metric_bar_chart,
)


def run_one_scenario(config, scenario_name: str, candidate_ids: list[str]) -> tuple[dict, dict]:
    """运行单个场景并返回汇总记录与分析结果。"""
    model, z, x, elapsed = build_and_solve_v2(
        config,
        carbon_price=50.0,
        loss_price=3000.0,
        max_facilities=8,
        candidate_ids=candidate_ids,
        demand_ids=list(config.demands["node_id"]),
        time_limit=300,
        mip_gap=0.01,
        threads=8,
        verbose=False,
    )

    if model.SolCount <= 0:
        raise RuntimeError(f"{scenario_name} 未找到可行解，状态码={model.Status}")

    analysis = analyze_results(
        model,
        z,
        x,
        config,
        candidate_ids=candidate_ids,
        demand_ids=list(config.demands["node_id"]),
        verbose=False,
    )

    record = build_result_record(
        scenario_name,
        candidate_ids,
        model,
        analysis,
        elapsed,
        carbon_price=50.0,
        loss_price=3000.0,
        max_facilities=8,
        demand_total_ton=float(config.nodes["okra_production_ton"].sum()),
    )
    return record, analysis


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    config = load_config()
    scenario_sets = get_scenario_candidate_sets(config)

    print("=" * 72)
    print("  秋葵冷库布局优化 - 四场景候选点对比")
    print("=" * 72)

    records = []
    analysis_cache = {}
    for scenario_name, candidate_ids in scenario_sets.items():
        print(f"\n[{scenario_name}] candidates={len(candidate_ids)} ...")
        record, analysis = run_one_scenario(config, scenario_name, candidate_ids)
        records.append(record)
        analysis_cache[scenario_name] = analysis
        print(
            f"  cost={record['total_cost']:,.0f} | facilities={record['num_facilities']} | "
            f"time={record['solve_time_sec']:.2f}s | gap={record['mip_gap_pct']:.2f}%"
        )

        scenario_dir = SCENARIO_ROOT / scenario_name
        scenario_dir.mkdir(parents=True, exist_ok=True)
        with open(scenario_dir / "result.pkl", "wb") as fh:
            pickle.dump(
                {
                    "record": record,
                    "analysis": analysis,
                    "candidate_ids": candidate_ids,
                },
                fh,
            )

    df = pd.DataFrame(records).sort_values("candidate_count").reset_index(drop=True)
    outputs = save_dataframe_bundle(df, SCENARIO_ROOT / "scenario_comparison")
    markdown_path = write_markdown_table(
        df,
        SCENARIO_ROOT / "scenario_comparison.md",
        [
            "scenario",
            "candidate_count",
            "total_cost",
            "num_facilities",
            "solve_time_sec",
            "mip_gap_pct",
            "facility_type_summary",
        ],
    )

    print("\n场景汇总:")
    print(df[[
        "scenario",
        "candidate_count",
        "total_cost",
        "num_facilities",
        "solve_time_sec",
        "mip_gap_pct",
    ]].to_string(index=False))
    print(f"\n结果表: {outputs['csv']}")
    print(f"Excel: {outputs['xlsx']}")
    print(f"Markdown: {markdown_path}")

    fig_dir = FIGURE_ROOT / "scenarios"
    fig_dir.mkdir(parents=True, exist_ok=True)
    save_metric_bar_chart(
        df,
        "scenario",
        "total_cost",
        fig_dir / "scenario_total_cost.png",
        title="Scenario Comparison - Total Cost",
        ylabel="Total Cost (yuan)",
        color="#4C78A8",
    )
    save_metric_bar_chart(
        df,
        "scenario",
        "solve_time_sec",
        fig_dir / "scenario_solve_time.png",
        title="Scenario Comparison - Solve Time",
        ylabel="Solve Time (sec)",
        color="#F58518",
    )
    save_metric_bar_chart(
        df,
        "scenario",
        "num_facilities",
        fig_dir / "scenario_facilities.png",
        title="Scenario Comparison - Open Facilities",
        ylabel="Open Facilities",
        color="#54A24B",
    )

    baseline_analysis = analysis_cache["S3_27_candidates"]
    save_cost_breakdown_chart(
        baseline_analysis,
        fig_dir / "baseline_v2_1_cost_breakdown.png",
        title="Baseline v2.1 Cost Breakdown",
    )
    save_layout_map(
        config,
        baseline_analysis,
        fig_dir / "baseline_v2_1_layout_map.png",
        title="Baseline v2.1 Layout Map",
    )

    print(f"\n图表输出目录: {fig_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
