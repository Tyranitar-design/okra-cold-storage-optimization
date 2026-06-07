"""
单因素灵敏度分析。

围绕四个最关键参数逐一扫描：
- 碳价
- 损耗单价
- 预冷时间上限
- 最大设施数
"""

from __future__ import annotations

import pickle
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd

from experiments._shared import (
    FIGURE_ROOT,
    SENSITIVITY_ROOT,
    build_result_record,
    load_config,
    save_dataframe_bundle,
    write_markdown_table,
)
from src.models.single_level_mip_v2_1 import analyze_results, build_and_solve_v2
from src.utils.visualization import save_sensitivity_curve


BASELINE = {
    "carbon_price": 50.0,
    "loss_price": 3000.0,
    "precool_time_limit_h": 2.0,
    "max_facilities": 8,
}


def run_case(config, *, carbon_price, loss_price, precool_time_limit_h, max_facilities) -> tuple[dict, dict]:
    """运行一个灵敏度场景。"""
    original_precool_limit = config.params["okra_preservation"]["precool_time_limit_h"]
    config.params["okra_preservation"]["precool_time_limit_h"] = precool_time_limit_h

    candidate_ids = list(config.candidates["node_id"])
    demand_ids = list(config.demands["node_id"])
    try:
        model, z, x, elapsed = build_and_solve_v2(
            config,
            carbon_price=carbon_price,
            loss_price=loss_price,
            max_facilities=max_facilities,
            candidate_ids=candidate_ids,
            demand_ids=demand_ids,
            time_limit=240,
            mip_gap=0.01,
            threads=8,
            verbose=False,
        )
    finally:
        config.params["okra_preservation"]["precool_time_limit_h"] = original_precool_limit

    if model.SolCount <= 0:
        raise RuntimeError(f"灵敏度场景求解失败，状态码={model.Status}")

    analysis = analyze_results(
        model,
        z,
        x,
        config,
        candidate_ids=candidate_ids,
        demand_ids=demand_ids,
        verbose=False,
    )

    record = build_result_record(
        scenario_name=(
            f"carbon={carbon_price}_loss={loss_price}_"
            f"precool={precool_time_limit_h}_fac={max_facilities}"
        ),
        candidate_ids=candidate_ids,
        model=model,
        analysis=analysis,
        elapsed=elapsed,
        carbon_price=carbon_price,
        loss_price=loss_price,
        max_facilities=max_facilities,
        demand_total_ton=float(config.nodes["okra_production_ton"].sum()),
    )
    record["precool_time_limit_h"] = precool_time_limit_h
    return record, analysis


def sweep_variable(config, variable_name: str, values: list[float]) -> pd.DataFrame:
    """对单变量做扫描。"""
    rows = []
    for value in values:
        kwargs = dict(BASELINE)
        kwargs[variable_name] = value
        print(f"[{variable_name}] = {value} ...")
        record, _ = run_case(config, **kwargs)
        record["sweep_variable"] = variable_name
        record["sweep_value"] = value
        rows.append(record)
        print(
            f"  total={record['total_cost']:,.0f} | facilities={record['num_facilities']} | "
            f"time={record['solve_time_sec']:.2f}s"
        )
    return pd.DataFrame(rows)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    config = load_config()

    print("=" * 72)
    print("  秋葵冷库布局优化 - 单因素灵敏度分析")
    print("=" * 72)

    sweeps = {
        "carbon_price": [0, 50, 100, 200, 500],
        "loss_price": [1000, 3000, 5000, 10000],
        "precool_time_limit_h": [1, 1.5, 2, 3, 4],
        "max_facilities": [3, 5, 8, 10, 15],
    }

    all_frames = []
    for variable_name, values in sweeps.items():
        df = sweep_variable(config, variable_name, values)
        all_frames.append(df)

        variable_dir = SENSITIVITY_ROOT / variable_name
        variable_dir.mkdir(parents=True, exist_ok=True)
        outputs = save_dataframe_bundle(df, variable_dir / f"{variable_name}_sweep")
        markdown_path = write_markdown_table(
            df,
            variable_dir / f"{variable_name}_sweep.md",
            [
                "sweep_value",
                "total_cost",
                "num_facilities",
                "solve_time_sec",
                "mip_gap_pct",
                "facility_type_summary",
            ],
        )
        fig_dir = FIGURE_ROOT / "sensitivity"
        fig_dir.mkdir(parents=True, exist_ok=True)
        save_sensitivity_curve(
            df,
            "sweep_value",
            fig_dir / f"{variable_name}_sensitivity.png",
            title=f"Sensitivity - {variable_name}",
        )

        print(f"  CSV: {outputs['csv']}")
        print(f"  XLSX: {outputs['xlsx']}")
        print(f"  MD: {markdown_path}")

        with open(variable_dir / f"{variable_name}_sweep.pkl", "wb") as fh:
            pickle.dump({"records": df.to_dict(orient="records")}, fh)

    combined = pd.concat(all_frames, ignore_index=True)
    combined_outputs = save_dataframe_bundle(combined, SENSITIVITY_ROOT / "sensitivity_all")
    combined_md = write_markdown_table(
        combined,
        SENSITIVITY_ROOT / "sensitivity_all.md",
        [
            "sweep_variable",
            "sweep_value",
            "total_cost",
            "num_facilities",
            "solve_time_sec",
        ],
    )
    print(f"\n总表: {combined_outputs['csv']}")
    print(f"总表Excel: {combined_outputs['xlsx']}")
    print(f"总表Markdown: {combined_md}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
