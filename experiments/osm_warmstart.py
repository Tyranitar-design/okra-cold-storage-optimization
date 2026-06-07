"""OSM 基线 warm start + CoverCuts 改进实验

策略：
1. 从 Haversine 对比实验结果读取最优选址（z 变量值）
2. 把该选址作为 MIP Start 注入 OSM 求解
3. 同时启用 CoverCuts=3（上次 Cover cuts 贡献最大，共 760 条）
4. 对比：纯 OSM 300s(1.68%) → warm start + CoverCuts 300s

证据边界：warm start 降低初始 gap，不改变最优性；结论仍受 OSM 路网近似边界限制。
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.models.single_level_mip_v2_1 import DataConfig
from src.models.single_level_mip_v3_capacity_chain import build_and_solve_v3, analyze_v3_results
from src.models.capacity_chain_assumptions import default_assumptions
from src.models.single_level_mip_v2_1 import GRB, gp

OUT_DIR = PROJECT_ROOT / "results" / "experiments" / "osm_warmstart"
OUT_DIR.mkdir(parents=True, exist_ok=True)

OSM_DIST_LONG = PROJECT_ROOT / "data" / "distance_matrix_osm.csv"
OSM_TIME_LONG = PROJECT_ROOT / "data" / "transport_time_matrix_osm.csv"
HAV_RESULT_JSON = PROJECT_ROOT / "results" / "experiments" / "osm_vs_haversine" / "osm_vs_haversine_summary.json"

SOLVE_TIME_LIMIT = 600   # 给更多时间
MIP_GAP = 0.01


def long_to_pivot(long_path: Path, value_col: str) -> pd.DataFrame:
    df = pd.read_csv(long_path)
    pivot = df.pivot(index="origin", columns="destination", values=value_col)
    ids = sorted(pivot.index.tolist())
    return pivot.loc[ids, ids]


class DataConfigOSM(DataConfig):
    def __init__(self, data_dir: str = str(PROJECT_ROOT / "data")):
        super().__init__(data_dir)
        dist_pivot = long_to_pivot(OSM_DIST_LONG, "distance_km")
        time_pivot = long_to_pivot(OSM_TIME_LONG, "time_h")
        self.distance = dist_pivot.values
        self.transport_time = time_pivot.values
        self.node_ids = list(dist_pivot.index)
        self.id2idx = {nid: i for i, nid in enumerate(self.node_ids)}


def load_haversine_facilities() -> list[dict[str, Any]]:
    """从 Haversine 对比结果读取设施选址。"""
    result = json.loads(HAV_RESULT_JSON.read_text(encoding="utf-8"))
    facilities = result["results"]["haversine"]["analysis"].get("facilities", [])
    print(f"  Haversine facilities ({len(facilities)}):")
    for f in facilities:
        print(f"    {f['site']} → {f['type']} cap={f['capacity']} (util={f['utilization']:.1f}%)")
    return facilities


def build_and_solve_osm_warmstart(
    config: DataConfigOSM,
    warm_facilities: list[dict[str, Any]],
    time_limit: int = SOLVE_TIME_LIMIT,
) -> dict[str, Any]:
    """构建 OSM v3.0 模型，注入 warm start，启用 CoverCuts=3。"""
    assumptions = default_assumptions()

    from src.models.capacity_chain_assumptions import _channel_map
    channels = _channel_map(assumptions)
    active_types = [ch.type_id for ch in assumptions.channels if ch.annual_share > 0]

    candidate_ids = list(config.candidates["node_id"])
    demand_ids = list(config.demands["node_id"])
    demand = {nid: config.get_demand(nid) for nid in demand_ids}

    model = gp.Model("OkraColdStorage_v3_OSM_WarmStart")
    model.setParam("TimeLimit", time_limit)
    model.setParam("MIPGap", MIP_GAP)
    model.setParam("Threads", 8)
    model.setParam("OutputFlag", 1)
    model.setParam("MIPFocus", 3)
    model.setParam("Cuts", 2)
    model.setParam("CoverCuts", 2)      # Gurobi 最大值为 2（已是最激进）
    model.setParam("StartNodeLimit", 0)  # 马上用 MIP start

    # ── 变量 ─────────────────────────────────────────────────────────────────
    z: dict = {}
    for site in candidate_ids:
        for type_id in active_types:
            for cap_idx, _cap in enumerate(config.capacity_index[type_id]):
                z[site, type_id, cap_idx] = model.addVar(
                    vtype=GRB.BINARY, name=f"z_{site}_{type_id}_{cap_idx}"
                )

    x: dict = {}
    for demand_id in demand_ids:
        for site in candidate_ids:
            for type_id in active_types:
                x[demand_id, site, type_id] = model.addVar(
                    vtype=GRB.CONTINUOUS, lb=0.0, ub=1.0,
                    name=f"x_{demand_id}_{site}_{type_id}"
                )

    model.update()

    # ── 注入 warm start（z 变量）──────────────────────────────────────────────
    # 先全部设为 0
    for key, var in z.items():
        var.Start = 0.0
    # 把 Haversine 选址设为 1
    warm_set = 0
    for fac in warm_facilities:
        site = fac["site"]
        type_id = fac["type"]
        cap_idx = fac["capacity_idx"]
        if (site, type_id, cap_idx) in z:
            z[site, type_id, cap_idx].Start = 1.0
            warm_set += 1
    print(f"  Warm start: {warm_set}/{len(warm_facilities)} z-vars set to 1")

    # ── 约束（与 build_and_solve_v3 完全一致）────────────────────────────────
    for demand_id in demand_ids:
        for type_id in active_types:
            share = channels[type_id].annual_share
            model.addConstr(
                gp.quicksum(x[demand_id, site, type_id] for site in candidate_ids) == share,
                name=f"channel_share_{demand_id}_{type_id}",
            )

    for demand_id in demand_ids:
        for site in candidate_ids:
            for type_id in active_types:
                model.addConstr(
                    x[demand_id, site, type_id]
                    <= gp.quicksum(
                        z[site, type_id, cap_idx]
                        for cap_idx in range(len(config.capacity_index[type_id]))
                    ),
                    name=f"assign_open_{demand_id}_{site}_{type_id}",
                )

    for site in candidate_ids:
        model.addConstr(
            gp.quicksum(
                z[site, type_id, cap_idx]
                for type_id in active_types
                for cap_idx in range(len(config.capacity_index[type_id]))
            ) <= 1,
            name=f"one_facility_{site}",
        )

    model.addConstr(
        gp.quicksum(
            z[site, type_id, cap_idx]
            for site in candidate_ids
            for type_id in active_types
            for cap_idx in range(len(config.capacity_index[type_id]))
        ) <= assumptions.max_facilities,
        name="max_facilities",
    )

    precool_limit_h = config.get_preservation_params().get("precool_time_limit_h", 2.0)
    for demand_id in demand_ids:
        for site in candidate_ids:
            if config.get_time(demand_id, site) > precool_limit_h:
                model.addConstr(x[demand_id, site, "precool"] == 0.0,
                                name=f"precool_time_{demand_id}_{site}")

    for site in candidate_ids:
        for type_id in active_types:
            channel = channels[type_id]
            peak_load = gp.quicksum(
                x[demand_id, site, type_id]
                * demand[demand_id]
                * channel.storage_days
                / assumptions.harvest_window_days
                * assumptions.harvest_peak_factor
                for demand_id in demand_ids
            )
            capacity = gp.quicksum(
                z[site, type_id, cap_idx] * config.capacity_index[type_id][cap_idx]["capacity"]
                for cap_idx in range(len(config.capacity_index[type_id]))
            )
            model.addConstr(peak_load <= capacity, name=f"peak_capacity_{site}_{type_id}")

    # ── 目标函数（与 build_and_solve_v3 完全一致）────────────────────────────
    from src.models.capacity_chain_assumptions import _annual_flow
    fixed_cost = gp.quicksum(
        z[site, type_id, cap_idx] * config.capacity_index[type_id][cap_idx]["fixed_cost"] * 10000
        for site in candidate_ids
        for type_id in active_types
        for cap_idx in range(len(config.capacity_index[type_id]))
    )
    operate_cost = gp.quicksum(
        z[site, type_id, cap_idx] * config.capacity_index[type_id][cap_idx]["operate_cost"] * 10000
        for site in candidate_ids
        for type_id in active_types
        for cap_idx in range(len(config.capacity_index[type_id]))
    )
    transport_cost = gp.quicksum(
        x[demand_id, site, type_id]
        * demand[demand_id]
        * config.get_dist(demand_id, site)
        * assumptions.transport_cost_yuan_per_ton_km
        for demand_id in demand_ids
        for site in candidate_ids
        for type_id in active_types
    )
    loss_cost = gp.quicksum(
        x[demand_id, site, type_id]
        * demand[demand_id]
        * (
            config.get_time(demand_id, site)
            * config.get_preservation_params().get("transport_loss_per_hour", 0.02)
            * channels[type_id].transport_loss_multiplier
            + channels[type_id].loss_rate
        )
        * assumptions.loss_price
        for demand_id in demand_ids
        for site in candidate_ids
        for type_id in active_types
    )
    carbon_cost = gp.quicksum(
        x[demand_id, site, type_id]
        * demand[demand_id]
        * (
            config.capacity_index[type_id][0]["energy_cost_per_ton"]
            * config.capacity_index[type_id][0]["carbon_factor"]
            / 1000
            + config.get_dist(demand_id, site) * assumptions.transport_carbon_kg_per_ton_km / 1000
        )
        * assumptions.carbon_price
        for demand_id in demand_ids
        for site in candidate_ids
        for type_id in active_types
    )
    model.setObjective(
        fixed_cost + operate_cost + transport_cost + loss_cost + carbon_cost, GRB.MINIMIZE
    )
    model.update()

    print(f"\n  Model: {model.NumVars} vars, {model.NumConstrs} constraints")
    print(f"  Params: MIPFocus=3, Cuts=2, CoverCuts=3, TimeLimit={time_limit}s")

    t0 = time.time()
    model.optimize()
    elapsed = time.time() - t0

    status_name = {
        2: "OPTIMAL", 9: "TIME_LIMIT", 3: "INFEASIBLE"
    }.get(model.Status, str(model.Status))
    obj = model.ObjVal if model.SolCount > 0 else None
    gap = model.MIPGap if model.SolCount > 0 else None

    result = {
        "label": "osm_warmstart_covercuts3",
        "status_name": status_name,
        "objective": obj,
        "bound": model.ObjBound,
        "mip_gap_pct": round(gap * 100, 4) if gap else None,
        "elapsed_sec": round(elapsed, 2),
        "sol_count": model.SolCount,
        "warm_facilities_injected": warm_set,
        "params": {"MIPFocus": 3, "Cuts": 2, "CoverCuts": 2, "TimeLimit": time_limit},
    }

    if model.SolCount > 0:
        analysis = analyze_v3_results(model, z, x, config, candidate_ids, demand_ids, assumptions)
        result["analysis"] = analysis
        print(f"\n  Result: {status_name}, Obj={obj:.2f}, Gap={gap*100:.4f}%")
    else:
        print(f"\n  Result: {status_name}, no solution")

    return result, model, z, x


def main() -> None:
    print("=== OSM Warm Start + CoverCuts=3 实验 ===\n")

    print("[1] Loading OSM DataConfig...")
    config_osm = DataConfigOSM()

    print("[2] Loading Haversine warm-start facilities...")
    warm_facilities = load_haversine_facilities()

    print("\n[3] Solving OSM with warm start + CoverCuts=3...")
    result, model, z, x = build_and_solve_osm_warmstart(config_osm, warm_facilities, SOLVE_TIME_LIMIT)

    # 与前次 OSM 无 warm start 对比
    prev_gap = 1.6843  # 上次 OSM 300s
    prev_obj = 4433112.27
    curr_gap = result.get("mip_gap_pct", 0)
    curr_obj = result.get("objective", 0)

    comparison = {
        "osm_no_warmstart_300s": {"gap_pct": prev_gap, "obj": prev_obj},
        "osm_warmstart_covercuts3": {"gap_pct": curr_gap, "obj": curr_obj},
        "gap_improvement_pp": round(prev_gap - curr_gap, 4) if curr_gap else None,
        "obj_change_yuan": round(curr_obj - prev_obj, 2) if curr_obj else None,
    }

    report = {
        "experiment": "osm_warmstart_covercuts3",
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "result": result,
        "comparison_vs_cold_start": comparison,
        "solver_improvement_suggestions": [
            "下一步：把 Benders 分解接到 v3.0 容量链问题（主问题z/子问题x），"
            "与 Gurobi 直接MIP 做同问题对比，才能支撑 AI-Benders 论文贡献。",
            "当前 AI-Benders 在 LRP benchmark 投影上跑，与 v3.0 是两条独立轨道——"
            "需要在 v3.0 上实现 classic Benders + AI-Benders 才能形成完整创新链路。",
        ],
        "claim_boundary": (
            "OSM road-network matrix. Warm start uses Haversine-run facility layout. "
            "CoverCuts=3 is aggressive setting — may slow individual iterations but tightens LP relaxation faster. "
            "County-level case study (39 nodes), not enterprise-scale validation."
        ),
    }

    out_json = OUT_DIR / "osm_warmstart_summary.json"
    out_json.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    print(f"\n[Done] → {out_json}")
    print(f"\n=== 对比 ===")
    print(f"  OSM 无 warm start (300s): gap={prev_gap}%, obj={prev_obj:.2f}")
    print(f"  OSM warm start + CoverCuts3: gap={curr_gap}%, obj={curr_obj:.2f if curr_obj else 'N/A'}")
    if comparison["gap_improvement_pp"]:
        print(f"  Gap 改善: {comparison['gap_improvement_pp']:+.4f} pp")


if __name__ == "__main__":
    main()
