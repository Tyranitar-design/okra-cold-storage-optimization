"""捕获 v3.0 求解收敛轨迹：Gurobi 直解 vs AI warm start。

用 Gurobi callback 在求解过程中记录每次 incumbent / bound 改善的
(runtime, objective, bound, gap)，生成两条收敛轨迹供前端做动画。

输出: results/experiments/v3_solve_trace/v3_solve_trace.json
  {
    "cold_start": {"trace": [{t, obj, bound, gap_pct}, ...], "final": {...}},
    "ai_warm":    {"trace": [...], "final": {...}, "warm_sites": [...], "warm_facilities": [...]},
  }
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("GRB_LICENSE_FILE", r"D:\Gurobi1300\win64\bin\gurobi.lic")

import gurobipy as gp
from gurobipy import GRB

from src.models.single_level_mip_v2_1 import DataConfig
from src.models.capacity_chain_assumptions import default_assumptions, _channel_map
from experiments.ai_warmstart_v3 import (
    DataConfigOSM, extract_labels_from_priority_runs, extract_facility_labels_from_priority_runs,
    compute_node_features, build_training_table, train_ranker, predict_top_k,
    build_warm_facilities_for_version, RECOMMENDED_WARM_VERSION, WARM_VERSION_LABELS,
)

AI_WARMSTART_SUMMARY = PROJECT_ROOT / "results" / "experiments" / "ai_warmstart_v3" / "ai_warmstart_summary.json"


def resolve_adopted_warm_version() -> str:
    if AI_WARMSTART_SUMMARY.exists():
        try:
            payload = json.loads(AI_WARMSTART_SUMMARY.read_text(encoding="utf-8"))
            return str(payload.get("recommended_version") or RECOMMENDED_WARM_VERSION)
        except Exception:
            pass
    return RECOMMENDED_WARM_VERSION

OUT_DIR = PROJECT_ROOT / "results" / "experiments" / "v3_solve_trace"
OUT_DIR.mkdir(parents=True, exist_ok=True)

TIME_LIMIT = 300
MIP_GAP = 0.01


def build_v3_model(config, warm_sites=None, warm_facilities=None):
    """构建 v3.0 MIP，可选注入 AI warm start。返回 (model, z, x)。"""
    a = default_assumptions()
    channels = _channel_map(a)
    ats = [c.type_id for c in a.channels if c.annual_share > 0]
    cids = list(config.candidates["node_id"])
    dids = list(config.demands["node_id"])
    demand = {nid: config.get_demand(nid) for nid in dids}
    precool_limit_h = config.get_preservation_params().get("precool_time_limit_h", 2.0)

    m = gp.Model("v3_trace")
    m.setParam("TimeLimit", TIME_LIMIT)
    m.setParam("MIPGap", MIP_GAP)
    m.setParam("Threads", 8)
    m.setParam("OutputFlag", 0)
    m.setParam("MIPFocus", 3)
    m.setParam("Cuts", 2)

    z = {}
    for j in cids:
        for t in ats:
            for c in range(len(config.capacity_index[t])):
                z[j, t, c] = m.addVar(vtype=GRB.BINARY, name=f"z_{j}_{t}_{c}")
    x = {}
    for d in dids:
        for j in cids:
            for t in ats:
                x[d, j, t] = m.addVar(lb=0.0, ub=1.0, name=f"x_{d}_{j}_{t}")
    m.update()

    applied_warm_facilities = warm_facilities
    if applied_warm_facilities is None and warm_sites:
        applied_warm_facilities = []
        for site in warm_sites:
            target = "cold"
            cap_idx = min(1, len(config.capacity_index[target]) - 1)
            if (site, target, cap_idx) in z:
                applied_warm_facilities.append({"site": site, "type": target, "capacity_idx": cap_idx})

    warm_sites_used = []
    n_warm = 0
    if applied_warm_facilities:
        for var in z.values():
            var.Start = 0.0
        for fac in applied_warm_facilities:
            site = str(fac["site"])
            target = str(fac["type"])
            cap_idx = int(fac["capacity_idx"])
            if (site, target, cap_idx) in z:
                z[site, target, cap_idx].Start = 1.0
                warm_sites_used.append(site)
                n_warm += 1
    warm_sites_used = list(dict.fromkeys(warm_sites_used))

    for d in dids:
        for t in ats:
            m.addConstr(gp.quicksum(x[d, j, t] for j in cids) == channels[t].annual_share)
    for d in dids:
        for j in cids:
            for t in ats:
                m.addConstr(x[d, j, t] <= gp.quicksum(
                    z[j, t, c] for c in range(len(config.capacity_index[t]))))
    for j in cids:
        m.addConstr(gp.quicksum(z[j, t, c] for t in ats
                    for c in range(len(config.capacity_index[t]))) <= 1)
    m.addConstr(gp.quicksum(z[j, t, c] for j in cids for t in ats
                for c in range(len(config.capacity_index[t]))) <= a.max_facilities)
    for d in dids:
        for j in cids:
            if config.get_time(d, j) > precool_limit_h:
                m.addConstr(x[d, j, "precool"] == 0.0)
    for j in cids:
        for t in ats:
            ch = channels[t]
            peak = gp.quicksum(x[d, j, t] * demand[d] * ch.storage_days
                               / a.harvest_window_days * a.harvest_peak_factor for d in dids)
            cap = gp.quicksum(z[j, t, c] * config.capacity_index[t][c]["capacity"]
                              for c in range(len(config.capacity_index[t])))
            m.addConstr(peak <= cap)

    fixed = gp.quicksum(z[j, t, c] * config.capacity_index[t][c]["fixed_cost"] * 10000
                        for j in cids for t in ats for c in range(len(config.capacity_index[t])))
    operate = gp.quicksum(z[j, t, c] * config.capacity_index[t][c]["operate_cost"] * 10000
                          for j in cids for t in ats for c in range(len(config.capacity_index[t])))
    transport = gp.quicksum(x[d, j, t] * demand[d] * config.get_dist(d, j)
                            * a.transport_cost_yuan_per_ton_km
                            for d in dids for j in cids for t in ats)
    loss = gp.quicksum(x[d, j, t] * demand[d]
                       * (config.get_time(d, j)
                          * config.get_preservation_params().get("transport_loss_per_hour", 0.02)
                          * channels[t].transport_loss_multiplier + channels[t].loss_rate)
                       * a.loss_price for d in dids for j in cids for t in ats)
    carbon = gp.quicksum(x[d, j, t] * demand[d]
                         * (config.capacity_index[t][0]["energy_cost_per_ton"]
                            * config.capacity_index[t][0]["carbon_factor"] / 1000
                            + config.get_dist(d, j) * a.transport_carbon_kg_per_ton_km / 1000)
                         * a.carbon_price for d in dids for j in cids for t in ats)
    m.setObjective(fixed + operate + transport + loss + carbon, GRB.MINIMIZE)
    m.update()
    return m, z, x, n_warm, warm_sites_used, applied_warm_facilities or []


def solve_with_trace(config, warm_sites, label, warm_facilities=None):
    """求解并捕获收敛轨迹。"""
    m, z, x, n_warm, warm_sites_used, applied_warm_facilities = build_v3_model(config, warm_sites, warm_facilities)
    trace = []
    t_start = time.time()

    def cb(model, where):
        if where == GRB.Callback.MIP:
            # 周期性记录 best obj / bound
            try:
                objbst = model.cbGet(GRB.Callback.MIP_OBJBST)
                objbnd = model.cbGet(GRB.Callback.MIP_OBJBND)
                runtime = model.cbGet(GRB.Callback.RUNTIME)
            except Exception:
                return
            if objbst < GRB.INFINITY and objbst > 0:
                gap = abs(objbst - objbnd) / max(1e-10, abs(objbst)) * 100
                # 只在 gap 改善时记录（避免太多点）
                if not trace or abs(trace[-1]["gap_pct"] - gap) > 0.05 or runtime - trace[-1]["t"] > 5:
                    trace.append({
                        "t": round(runtime, 2),
                        "obj": round(objbst, 2),
                        "bound": round(objbnd, 2),
                        "gap_pct": round(gap, 4),
                    })

    m.optimize(cb)
    elapsed = time.time() - t_start

    # 补最终点
    if m.SolCount > 0:
        final_gap = m.MIPGap * 100
        final = {
            "t": round(elapsed, 2),
            "obj": round(m.ObjVal, 2),
            "bound": round(m.ObjBound, 2),
            "gap_pct": round(final_gap, 4),
        }
        if not trace or trace[-1]["gap_pct"] != final["gap_pct"]:
            trace.append(final)
    else:
        final = {}

    status = {2: "OPTIMAL", 9: "TIME_LIMIT"}.get(m.Status, str(m.Status))
    print(f"  [{label}] {status}, obj={final.get('obj')}, gap={final.get('gap_pct')}%, "
          f"t={elapsed:.1f}s, trace_points={len(trace)}, warm={n_warm}")
    return {
        "label": label, "status": status, "trace": trace, "final": final,
        "elapsed_sec": round(elapsed, 2), "warm_sites_injected": len(warm_sites_used),
        "warm_facilities_injected": n_warm,
        "warm_sites": warm_sites_used, "warm_facilities": applied_warm_facilities,
    }


def main():
    print("=== v3.0 求解轨迹捕获 (cold_start vs ai_warm) ===\n")
    config = DataConfigOSM()

    # 训练 AI ranker
    print("[1] 训练 AI ranker...")
    labels = extract_labels_from_priority_runs()
    facility_labels = extract_facility_labels_from_priority_runs()
    features = compute_node_features(config)
    train_df = build_training_table(features, labels)
    clf, feat_cols = train_ranker(train_df)
    top_k, scored = predict_top_k(clf, features, feat_cols, k=8)
    adopted_version = resolve_adopted_warm_version()
    joint_warm_facilities, recommended_strategy = build_warm_facilities_for_version(
        adopted_version, top_k, features, scored, facility_labels, config
    )
    print(f"  AI top-8: {top_k}")

    print("\n[2] cold_start 求解 (无 hint)...")
    cold = solve_with_trace(config, None, "cold_start")

    print("\n[3] ai_warm 求解 (AI MIP Start)...")
    ai = solve_with_trace(config, top_k, "ai_warm", warm_facilities=joint_warm_facilities)
    ai["ai_top_k"] = top_k
    ai["warm_facilities"] = joint_warm_facilities

    report = {
        "experiment": "v3_solve_trace",
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "config": {"model": "v3.0_capacity_chain", "matrix": "OSM", "time_limit": TIME_LIMIT, "mip_gap": MIP_GAP},
        "cold_start": cold,
        "ai_warm": ai,
        "claim_boundary": (
            "v3.0 capacity-chain MIP solve traces on OSM matrix. "
            f"cold_start = no hint; ai_warm = {WARM_VERSION_LABELS.get(adopted_version, adopted_version)} with strategy {recommended_strategy} as Gurobi MIP Start. "
            "Trace records incumbent/bound at each gap improvement during branch-and-cut. "
            "County-level case (39 nodes)."
        ),
    }
    out = OUT_DIR / "v3_solve_trace.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"\n[Done] → {out}")


if __name__ == "__main__":
    main()
