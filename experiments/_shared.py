"""
实验脚手架共享工具。

用于把项目根目录加入 `sys.path`、绑定 Gurobi 许可证、
加载基线模型配置，并统一整理实验结果字段。
"""

from __future__ import annotations

import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("GRB_LICENSE_FILE", r"D:\Gurobi1300\win64\bin\gurobi.lic")

RESULTS_ROOT = PROJECT_ROOT / "results"
EXPERIMENT_ROOT = RESULTS_ROOT / "experiments"
SCENARIO_ROOT = EXPERIMENT_ROOT / "scenarios"
SENSITIVITY_ROOT = EXPERIMENT_ROOT / "sensitivity"
FIGURE_ROOT = EXPERIMENT_ROOT / "figures"

for path in [SCENARIO_ROOT, SENSITIVITY_ROOT, FIGURE_ROOT]:
    path.mkdir(parents=True, exist_ok=True)


def load_config():
    """加载基线模型配置。"""
    from src.models.single_level_mip_v2_1 import DataConfig

    return DataConfig()


def get_scenario_candidate_sets(config) -> Dict[str, List[str]]:
    """构造四个场景的候选点集合。"""
    nodes = config.nodes.copy()
    candidate_nodes = nodes[nodes["is_candidate"]].copy()

    town_county = candidate_nodes[candidate_nodes["level"] >= 2].sort_values(
        ["level", "node_id"], ascending=[False, True]
    )
    village_candidates = candidate_nodes[candidate_nodes["level"] == 1].sort_values(
        ["okra_production_ton", "node_id"], ascending=[False, True]
    )

    s1 = town_county["node_id"].tolist()
    s2 = s1 + village_candidates["node_id"].tolist()[: max(0, 18 - len(s1))]
    s3 = candidate_nodes["node_id"].tolist()
    s4 = nodes["node_id"].tolist()

    return {
        "S1_9_candidates": s1,
        "S2_18_candidates": s2,
        "S3_27_candidates": s3,
        "S4_39_candidates": s4,
    }


def gurobi_status_name(status_code: int) -> str:
    """把 Gurobi 状态码翻译成可读文本。"""
    status_map = {
        2: "OPTIMAL",
        3: "INFEASIBLE",
        4: "INF_OR_UNBD",
        5: "UNBOUNDED",
        9: "TIME_LIMIT",
        11: "INTERRUPTED",
        13: "SUBOPTIMAL",
    }
    return status_map.get(status_code, f"STATUS_{status_code}")


def summarize_facilities(facilities: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """汇总开放设施信息。"""
    facilities = list(facilities)
    counter = Counter(item["type_name"] for item in facilities)
    total_utilization = [float(item.get("utilization", 0.0)) for item in facilities]

    return {
        "open_facility_count": len(facilities),
        "facility_type_summary": "; ".join(
            f"{name}:{count}" for name, count in sorted(counter.items())
        ),
        "open_sites": ", ".join(item["site"] for item in facilities),
        "open_facility_details": "; ".join(
            f"{item['site']}|{item['type_name']}|{item['capacity']}t"
            for item in facilities
        ),
        "avg_utilization_pct": sum(total_utilization) / len(total_utilization)
        if total_utilization
        else 0.0,
    }


def build_result_record(
    scenario_name: str,
    candidate_ids: List[str],
    model,
    analysis: Dict[str, Any],
    elapsed: float,
    *,
    carbon_price: float,
    loss_price: float,
    max_facilities: int,
    demand_total_ton: float | None = None,
) -> Dict[str, Any]:
    """统一生成实验汇总行。"""
    facility_summary = summarize_facilities(analysis.get("facilities", []))
    record = {
        "scenario": scenario_name,
        "candidate_count": len(candidate_ids),
        "demand_count": 39,
        "max_facilities": max_facilities,
        "carbon_price": carbon_price,
        "loss_price": loss_price,
        "status_code": int(getattr(model, "Status", -1)),
        "status_name": gurobi_status_name(int(getattr(model, "Status", -1))),
        "solve_time_sec": float(elapsed),
        "mip_gap_pct": float(getattr(model, "MIPGap", 0.0) * 100.0)
        if getattr(model, "SolCount", 0) > 0
        else None,
        "total_cost": float(analysis["total_cost"]),
        "fixed_cost": float(analysis["fixed_cost"]),
        "operate_cost": float(analysis["operate_cost"]),
        "transport_cost": float(analysis["transport_cost"]),
        "loss_cost": float(analysis["loss_cost"]),
        "carbon_cost": float(analysis["carbon_cost"]),
        "precool_violations": int(analysis["precool_violations"]),
        "num_facilities": int(analysis["num_facilities"]),
        "open_facility_count": int(facility_summary["open_facility_count"]),
        "facility_type_summary": facility_summary["facility_type_summary"],
        "open_sites": facility_summary["open_sites"],
        "open_facility_details": facility_summary["open_facility_details"],
        "avg_utilization_pct": float(facility_summary["avg_utilization_pct"]),
    }

    if demand_total_ton is not None:
        record["demand_total_ton"] = float(demand_total_ton)
        record["cost_per_ton"] = (
            record["total_cost"] / float(demand_total_ton)
            if demand_total_ton > 0
            else None
        )

    return record


def save_dataframe_bundle(df: pd.DataFrame, output_stem: Path) -> Dict[str, Path]:
    """把结果表同时导出为 CSV 和 Excel。"""
    output_stem.parent.mkdir(parents=True, exist_ok=True)
    csv_path = output_stem.with_suffix(".csv")
    xlsx_path = output_stem.with_suffix(".xlsx")
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    df.to_excel(xlsx_path, index=False)
    return {"csv": csv_path, "xlsx": xlsx_path}


def write_markdown_table(df: pd.DataFrame, output_path: Path, columns: List[str]) -> Path:
    """输出一个无需额外依赖的 markdown 表格。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    view = df[columns].copy()

    def fmt_value(value: Any) -> str:
        if pd.isna(value):
            return ""
        if isinstance(value, float):
            return f"{value:,.2f}"
        return str(value)

    header = "| " + " | ".join(columns) + " |"
    separator = "| " + " | ".join(["---"] * len(columns)) + " |"
    rows = ["| " + " | ".join(fmt_value(row[col]) for col in columns) + " |" for _, row in view.iterrows()]
    output_path.write_text("\n".join([header, separator, *rows]), encoding="utf-8")
    return output_path
