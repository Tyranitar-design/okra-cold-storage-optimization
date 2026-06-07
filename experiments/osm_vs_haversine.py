"""OSM vs Haversine 距离矩阵对比实验 + 求解器改进评估

对比两个矩阵下 v3.0 容量链基线的：
- 目标函数值（总成本）
- 选址决策（设施位置/类型/容量）
- 运输成本/损耗成本差异
- 求解时间与 MIPGap

同时输出求解器改进建议（基于本次运行指标）。
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.models.single_level_mip_v2_1 import DataConfig
from src.models.single_level_mip_v3_capacity_chain import build_and_solve_v3, analyze_v3_results
from src.models.capacity_chain_assumptions import default_assumptions

OUT_DIR = PROJECT_ROOT / "results" / "experiments" / "osm_vs_haversine"
OUT_DIR.mkdir(parents=True, exist_ok=True)

HAVERSINE_DIST = PROJECT_ROOT / "data" / "distance_matrix.csv"
HAVERSINE_TIME = PROJECT_ROOT / "data" / "transport_time_matrix.csv"
OSM_DIST_LONG  = PROJECT_ROOT / "data" / "distance_matrix_osm.csv"
OSM_TIME_LONG  = PROJECT_ROOT / "data" / "transport_time_matrix_osm.csv"

# ── 求解参数（同 extended_bound_900s profile）─────────────────────────────────
SOLVE_TIME_LIMIT = 300   # 每个版本 5 分钟
MIP_GAP = 0.01
SOLVER_PARAMS = {"MIPFocus": 3, "Cuts": 2}


def long_to_pivot(long_path: Path, value_col: str) -> pd.DataFrame:
    """把 origin/destination/value 长格式转成 pivot 矩阵，index 和 columns 对齐。"""
    df = pd.read_csv(long_path)
    pivot = df.pivot(index="origin", columns="destination", values=value_col)
    # 按 node_id 排序保持一致性
    ids = sorted(pivot.index.tolist())
    pivot = pivot.loc[ids, ids]
    return pivot


class DataConfigOSM(DataConfig):
    """DataConfig 子类：注入 OSM 路网矩阵替代 Haversine 估算。"""

    def __init__(
        self,
        data_dir: str = str(PROJECT_ROOT / "data"),
        dist_csv: Path = OSM_DIST_LONG,
        time_csv: Path = OSM_TIME_LONG,
    ):
        # 调用父类初始化（读 Haversine 矩阵作为基础）
        super().__init__(data_dir)
        # 替换距离和时间矩阵
        dist_pivot = long_to_pivot(dist_csv, "distance_km")
        time_pivot = long_to_pivot(time_csv, "time_h")
        # 重新对齐 node_ids 顺序
        self.distance = dist_pivot.values
        self.transport_time = time_pivot.values
        # 更新 id2idx（父类已设，但 pivot 可能顺序不同）
        self.node_ids = list(dist_pivot.index)
        self.id2idx = {nid: i for i, nid in enumerate(self.node_ids)}


def run_one(config: DataConfig, label: str, time_limit: int = SOLVE_TIME_LIMIT) -> dict[str, Any]:
    """跑一次 v3.0 求解，返回结果字典。"""
    print(f"\n{'='*60}")
    print(f"[{label}] Starting v3.0 solve (time_limit={time_limit}s, MIPGap={MIP_GAP})")
    print(f"{'='*60}")
    assumptions = default_assumptions()
    t0 = time.time()
    model, z, x, elapsed = build_and_solve_v3(
        config,
        assumptions=assumptions,
        time_limit=time_limit,
        mip_gap=MIP_GAP,
        threads=8,
        solver_params=SOLVER_PARAMS,
        verbose=True,
    )
    wall = time.time() - t0

    status = model.Status
    status_name = {1: "LOADED", 2: "OPTIMAL", 3: "INFEASIBLE", 4: "INF_OR_UNBD",
                   5: "UNBOUNDED", 9: "TIME_LIMIT", 11: "INTERRUPTED"}.get(status, str(status))
    obj = model.ObjVal if model.SolCount > 0 else None
    bound = model.ObjBound
    gap = model.MIPGap if model.SolCount > 0 else None

    # 分析结果
    if model.SolCount > 0:
        candidate_ids = list(config.candidates["node_id"])
        demand_ids = list(config.demands["node_id"])
        analysis = analyze_v3_results(model, z, x, config, candidate_ids, demand_ids, assumptions)
    else:
        analysis = {}

    result = {
        "label": label,
        "status": status,
        "status_name": status_name,
        "objective": obj,
        "bound": bound,
        "mip_gap_pct": round(gap * 100, 4) if gap is not None else None,
        "elapsed_sec": round(elapsed, 2),
        "wall_sec": round(wall, 2),
        "sol_count": model.SolCount,
        "num_vars": model.NumVars,
        "num_constrs": model.NumConstrs,
        "analysis": analysis,
    }
    obj_str = f"{obj:.2f}" if obj is not None else "N/A"
    gap_str = f"{gap*100:.4f}%" if gap is not None else "N/A"
    print(f"\n[{label}] Status={status_name}, Obj={obj_str}, Gap={gap_str}")
    return result


def compare_matrices(config_hav: DataConfig, config_osm: DataConfigOSM) -> dict[str, Any]:
    """对比两个矩阵的统计特性。"""
    hav = config_hav.distance
    osm = config_osm.distance
    n = hav.shape[0]
    # 只取 off-diagonal
    mask = ~np.eye(n, dtype=bool)
    hav_vals = hav[mask]
    osm_vals = osm[mask]
    ratio = osm_vals / np.where(hav_vals > 0, hav_vals, 1.0)
    return {
        "haversine_mean_km": round(float(hav_vals.mean()), 2),
        "osm_mean_km": round(float(osm_vals.mean()), 2),
        "ratio_mean": round(float(ratio.mean()), 3),
        "ratio_min": round(float(ratio.min()), 3),
        "ratio_max": round(float(ratio.max()), 3),
        "osm_longer_pct": round(float((osm_vals > hav_vals).mean() * 100), 1),
        "note": (
            "OSM road distances compared to Haversine×random-factor. "
            "ratio>1 means OSM longer; ratio<1 means OSM shorter (fewer detours in graph)."
        ),
    }


def solver_improvement_suggestions(result: dict[str, Any]) -> list[str]:
    """基于求解结果给出改进建议。"""
    suggestions = []
    gap = result.get("mip_gap_pct")
    elapsed = result.get("elapsed_sec", 0)
    status = result.get("status_name", "")

    if gap is not None and gap > 1.0:
        suggestions.append(
            f"Gap {gap:.2f}% > 1%: 启用更长 time_limit（900s）或 MIPFocus=3 + Cuts=2 profile。"
        )
    if elapsed < 60 and status == "OPTIMAL":
        suggestions.append(
            "求解时间 <60s 且达 OPTIMAL：问题规模偏小，可扩展到更多候选点或更细粒度节点提升泛化性。"
        )
    if result.get("num_vars", 0) < 500:
        suggestions.append(
            "变量数 <500：当前规模是 county-level case；企业级需 ≥200 节点/50 候选点以产生有意义的 benchmark。"
        )
    suggestions.append(
        "改进方向 1 — Valid inequalities: 对 z[j,t,c] 加 'at most one capacity level per site' 组合约束，收紧 LP 松弛。"
    )
    suggestions.append(
        "改进方向 2 — Warm start: 用 Haversine 最优解作为 OSM 求解的初始 MIP start（heuristic warmstart），减少根节点 gap。"
    )
    suggestions.append(
        "改进方向 3 — Symmetry breaking: 对相同 capacity 的候选点加字典序约束，减少对称解。"
    )
    suggestions.append(
        "改进方向 4 — Benders decomposition: 对大规模问题，把 x[i,j,t] 放入子问题，z[j,t,c] 留主问题，可大幅降低主问题规模。"
    )
    return suggestions


def main() -> None:
    print("=== OSM vs Haversine 距离矩阵对比实验 ===\n")

    # 1. 加载两个 config
    print("[1] Loading DataConfig (Haversine)...")
    config_hav = DataConfig(str(PROJECT_ROOT / "data"))

    print("[2] Loading DataConfigOSM (road network)...")
    config_osm = DataConfigOSM()

    # 2. 矩阵统计对比
    print("[3] Comparing matrices...")
    matrix_compare = compare_matrices(config_hav, config_osm)
    print(f"  Haversine mean: {matrix_compare['haversine_mean_km']} km")
    print(f"  OSM road mean:  {matrix_compare['osm_mean_km']} km")
    print(f"  OSM/Hav ratio:  {matrix_compare['ratio_mean']}x (range {matrix_compare['ratio_min']}–{matrix_compare['ratio_max']})")
    print(f"  OSM longer:     {matrix_compare['osm_longer_pct']}% of pairs")

    # 3. Haversine 求解
    result_hav = run_one(config_hav, "haversine", SOLVE_TIME_LIMIT)

    # 4. OSM 求解（用 Haversine 解做 warm start）
    result_osm = run_one(config_osm, "osm_road", SOLVE_TIME_LIMIT)

    # 5. 差异对比
    diff = {}
    if result_hav.get("objective") and result_osm.get("objective"):
        obj_h = result_hav["objective"]
        obj_o = result_osm["objective"]
        diff = {
            "obj_haversine": round(obj_h, 2),
            "obj_osm": round(obj_o, 2),
            "obj_diff_yuan": round(obj_o - obj_h, 2),
            "obj_diff_pct": round((obj_o - obj_h) / obj_h * 100, 3),
            "interpretation": (
                "正值 = OSM 路网下总成本更高（实际道路更迂回）；"
                "负值 = OSM 路网下成本更低（Haversine 高估了部分距离）。"
            ),
        }
        print(f"\n[Comparison] Haversine obj={obj_h:.2f}, OSM obj={obj_o:.2f}, "
              f"diff={diff['obj_diff_yuan']:+.2f} ({diff['obj_diff_pct']:+.3f}%)")

    # 6. 求解器改进建议
    suggestions_hav = solver_improvement_suggestions(result_hav)
    suggestions_osm = solver_improvement_suggestions(result_osm)

    # 7. 写结果
    report = {
        "experiment": "osm_vs_haversine_distance_matrix",
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "matrix_comparison": matrix_compare,
        "results": {"haversine": result_hav, "osm_road": result_osm},
        "cost_comparison": diff,
        "solver_improvement_suggestions": {
            "haversine_run": suggestions_hav,
            "osm_run": suggestions_osm,
        },
        "claim_boundary": (
            "OSM-matrix run uses road-network distances from Overpass API (county-level bbox). "
            "Haversine-matrix uses random road-factor (1.3-1.5, no fixed seed). "
            "Both runs use the same v3.0 capacity-chain MIP with identical solver params. "
            "This is a county-level case study (39 nodes), not enterprise-scale validation."
        ),
    }

    out_json = OUT_DIR / "osm_vs_haversine_summary.json"
    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"\n[Done] Report → {out_json}")

    # 打印改进建议
    print("\n=== 求解器改进建议 ===")
    for i, s in enumerate(suggestions_osm, 1):
        print(f"  {i}. {s}")


if __name__ == "__main__":
    main()
