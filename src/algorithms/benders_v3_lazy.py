"""v3.0 容量链 Benders —— Gurobi lazy constraint callback 单树实现。

与手写迭代 Benders (benders_v3.py) 的关键区别：
  - master 只构建并求解 **一次**，在单棵分支定界树内完成；
  - 每当 Gurobi 在树中找到整数候选解 (MIPSOL)，callback 解子问题、
    用 cbLazy 注入 Benders 最优性割；
  - cut 永久累积、永不删除，彻底避免手写迭代里"换一组设施逃避 cut"的退化绕圈。

子问题（给定整数 z̄）：连续分配 LP，含松弛保证 relatively complete recourse。
Benders 最优性割（次梯度形式，在 z̄ 处紧）：
  η >= sub_obj(z̄) + Σ grad[j,t,c]·(z[j,t,c] - z̄[j,t,c])
  grad = ∂sub_obj/∂z = λ_sum[j,t] + μ[j,t]·capval[t,c]   (包络定理)

AI cut 钩子：所有注入的割都记录其 sub_obj / L1-norm 特征，
支持事后 learned 排序分析（与 benders_cutmgmt/DS-F-043 同接口）。
注意：lazy 单树模式下 cut 由 Gurobi 内部管理，不做硬性丢弃
（硬丢弃破坏精确收敛，见 DS-F-049），因此这里 AI 角色是
cut 重要性排序/解释，而非预算丢弃。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import gurobipy as gp
from gurobipy import GRB

from src.models.single_level_mip_v2_1 import DataConfig
from src.models.capacity_chain_assumptions import (
    CapacityChainAssumptions,
    _channel_map,
    default_assumptions,
)

BIG_M = 5e5  # 松弛缺额惩罚（量级适中，避免污染对偶/cut 系数）


@dataclass
class LazyBendersResult:
    status: str
    objective: float | None
    bound: float
    mip_gap_pct: float | None
    elapsed_sec: float
    n_lazy_cuts: int
    facilities: list[dict]
    cut_features: list[dict] = field(default_factory=list)
    claim_boundary: str = (
        "Single-tree Benders via Gurobi lazy-constraint callback on the v3.0 "
        "capacity-chain MIP. Subproblem LP solved exactly each incumbent; "
        "optimality cuts injected lazily and retained (no hard dropping). "
        "County-level case (39 nodes), not enterprise-scale validation."
    )


def _build_subproblem_template(
    config: DataConfig,
    assumptions: CapacityChainAssumptions,
    candidate_ids: list[str],
    demand_ids: list[str],
):
    """构建子问题 LP 的静态部分（约束 RHS 中依赖 z 的项在求解时更新）。

    返回 (model, x, s, pi_constrs, lam_constrs, mu_constrs, nu_constrs, meta)。
    为效率，这里每次 callback 重建一个轻量 LP（39×27×4 规模，毫秒级）。
    """
    # 为简单与正确性，子问题在每次调用时重建（见 solve_subproblem）。
    return None


def solve_subproblem(
    z_bar: dict[tuple, float],
    config: DataConfig,
    assumptions: CapacityChainAssumptions,
    candidate_ids: list[str],
    demand_ids: list[str],
) -> dict[str, Any]:
    """给定整数 z̄，求连续分配子问题，返回 sub_obj 与次梯度 grad。"""
    channels = _channel_map(assumptions)
    active_types = [ch.type_id for ch in assumptions.channels if ch.annual_share > 0]
    demand = {nid: config.get_demand(nid) for nid in demand_ids}
    precool_limit_h = config.get_preservation_params().get("precool_time_limit_h", 2.0)

    open_cap: dict[tuple, float] = {}
    installed_cap: dict[tuple, float] = {}
    for site in candidate_ids:
        for type_id in active_types:
            open_cap[site, type_id] = sum(
                z_bar.get((site, type_id, c), 0.0)
                for c in range(len(config.capacity_index[type_id]))
            )
            installed_cap[site, type_id] = sum(
                z_bar.get((site, type_id, c), 0.0)
                * config.capacity_index[type_id][c]["capacity"]
                for c in range(len(config.capacity_index[type_id]))
            )

    sub = gp.Model("sub")
    sub.setParam("OutputFlag", 0)
    sub.setParam("Method", 1)

    x: dict = {}
    for d in demand_ids:
        for j in candidate_ids:
            for t in active_types:
                x[d, j, t] = sub.addVar(lb=0.0, name=f"x_{d}_{j}_{t}")
    s: dict = {}
    for d in demand_ids:
        for t in active_types:
            s[d, t] = sub.addVar(lb=0.0, name=f"s_{d}_{t}")
    sub.update()

    pi_c: dict[tuple, gp.Constr] = {}
    for d in demand_ids:
        for t in active_types:
            pi_c[d, t] = sub.addConstr(
                gp.quicksum(x[d, j, t] for j in candidate_ids) + s[d, t]
                == channels[t].annual_share,
                name=f"cs_{d}_{t}",
            )

    lam_c: dict[tuple, gp.Constr] = {}
    for d in demand_ids:
        for j in candidate_ids:
            for t in active_types:
                rhs = open_cap.get((j, t), 0.0)
                if t == "precool" and config.get_time(d, j) > precool_limit_h:
                    rhs = 0.0
                lam_c[d, j, t] = sub.addConstr(x[d, j, t] <= rhs, name=f"ao_{d}_{j}_{t}")

    mu_c: dict[tuple, gp.Constr] = {}
    for j in candidate_ids:
        for t in active_types:
            ch = channels[t]
            peak = gp.quicksum(
                x[d, j, t] * demand[d] * ch.storage_days
                / assumptions.harvest_window_days * assumptions.harvest_peak_factor
                for d in demand_ids
            )
            mu_c[j, t] = sub.addConstr(peak <= installed_cap.get((j, t), 0.0), name=f"pc_{j}_{t}")

    transport = gp.quicksum(
        x[d, j, t] * demand[d] * config.get_dist(d, j)
        * assumptions.transport_cost_yuan_per_ton_km
        for d in demand_ids for j in candidate_ids for t in active_types
    )
    loss = gp.quicksum(
        x[d, j, t] * demand[d]
        * (config.get_time(d, j)
           * config.get_preservation_params().get("transport_loss_per_hour", 0.02)
           * channels[t].transport_loss_multiplier + channels[t].loss_rate)
        * assumptions.loss_price
        for d in demand_ids for j in candidate_ids for t in active_types
    )
    carbon = gp.quicksum(
        x[d, j, t] * demand[d]
        * (config.capacity_index[t][0]["energy_cost_per_ton"]
           * config.capacity_index[t][0]["carbon_factor"] / 1000
           + config.get_dist(d, j) * assumptions.transport_carbon_kg_per_ton_km / 1000)
        * assumptions.carbon_price
        for d in demand_ids for j in candidate_ids for t in active_types
    )
    slack_pen = BIG_M * gp.quicksum(s[d, t] for d in demand_ids for t in active_types)
    sub.setObjective(transport + loss + carbon + slack_pen, GRB.MINIMIZE)
    sub.optimize()

    if sub.Status != GRB.OPTIMAL:
        return {"feasible": False, "sub_obj": 0.0, "grad": {}, "slack_total": float("inf")}

    sub_obj = sub.ObjVal
    slack_total = sum(s[k].X for k in s)
    # 次梯度 grad[j,t,c] = λ_sum[j,t] + μ[j,t]·capval[t,c]
    grad: dict[tuple, float] = {}
    for j in candidate_ids:
        for t in active_types:
            lam_sum = sum(lam_c[d, j, t].Pi for d in demand_ids)
            mu_jt = mu_c[j, t].Pi
            for c in range(len(config.capacity_index[t])):
                capval = config.capacity_index[t][c]["capacity"]
                g = lam_sum + mu_jt * capval
                if abs(g) > 1e-8:
                    grad[j, t, c] = g
    return {"feasible": True, "sub_obj": sub_obj, "grad": grad,
            "slack_total": slack_total, "slack_active": slack_total > 1e-6}


def solve_lazy_benders(
    config: DataConfig,
    assumptions: CapacityChainAssumptions | None = None,
    time_limit: float = 300.0,
    mip_gap: float = 0.01,
    threads: int = 8,
    verbose: bool = True,
) -> LazyBendersResult:
    """单树 Benders（lazy callback）。"""
    assumptions = assumptions or default_assumptions()
    channels = _channel_map(assumptions)
    active_types = [ch.type_id for ch in assumptions.channels if ch.annual_share > 0]
    candidate_ids = list(config.candidates["node_id"])
    demand_ids = list(config.demands["node_id"])
    precool_limit_h = config.get_preservation_params().get("precool_time_limit_h", 2.0)

    master = gp.Model("master_lazy_benders")
    master.setParam("OutputFlag", 1 if verbose else 0)
    master.setParam("TimeLimit", time_limit)
    master.setParam("MIPGap", mip_gap)
    master.setParam("Threads", threads)
    master.setParam("LazyConstraints", 1)   # 必须：启用 lazy constraint

    z: dict = {}
    for j in candidate_ids:
        for t in active_types:
            for c in range(len(config.capacity_index[t])):
                z[j, t, c] = master.addVar(vtype=GRB.BINARY, name=f"z_{j}_{t}_{c}")
    eta = master.addVar(lb=0.0, name="eta")
    master.update()

    # 选址结构约束
    for j in candidate_ids:
        master.addConstr(
            gp.quicksum(z[j, t, c] for t in active_types
                        for c in range(len(config.capacity_index[t]))) <= 1,
            name=f"one_facility_{j}",
        )
    master.addConstr(
        gp.quicksum(z[j, t, c] for j in candidate_ids for t in active_types
                    for c in range(len(config.capacity_index[t]))) <= assumptions.max_facilities,
        name="max_facilities",
    )
    # 每种通道至少一个设施（保证子问题 channel_share 可由真实分配满足）
    for t in active_types:
        master.addConstr(
            gp.quicksum(z[j, t, c] for j in candidate_ids
                        for c in range(len(config.capacity_index[t]))) >= 1,
            name=f"min_one_{t}",
        )
    # precool 覆盖：每需求点 2h 内有 precool 设施
    if "precool" in active_types:
        for d in demand_ids:
            nearby = [(j, c) for j in candidate_ids
                      for c in range(len(config.capacity_index["precool"]))
                      if config.get_time(d, j) <= precool_limit_h]
            if nearby:
                master.addConstr(
                    gp.quicksum(z[j, "precool", c] for j, c in nearby) >= 1,
                    name=f"precool_cover_{d}",
                )

    fixed = gp.quicksum(
        z[j, t, c] * config.capacity_index[t][c]["fixed_cost"] * 10000
        for j in candidate_ids for t in active_types
        for c in range(len(config.capacity_index[t]))
    )
    operate = gp.quicksum(
        z[j, t, c] * config.capacity_index[t][c]["operate_cost"] * 10000
        for j in candidate_ids for t in active_types
        for c in range(len(config.capacity_index[t]))
    )
    master.setObjective(fixed + operate + eta, GRB.MINIMIZE)
    master.update()

    # callback 内累积的统计（用闭包 dict 承载，避免全局变量）
    stats = {"n_cuts": 0, "cut_features": []}

    def benders_callback(model, where):
        if where != GRB.Callback.MIPSOL:
            return
        # 取当前整数候选解
        z_vals = model.cbGetSolution([z[k] for k in z])
        z_bar = {k: zv for k, zv in zip(z.keys(), z_vals)}
        eta_val = model.cbGetSolution(eta)

        sub = solve_subproblem(z_bar, config, assumptions, candidate_ids, demand_ids)
        if not sub["feasible"]:
            return
        sub_obj = sub["sub_obj"]
        grad = sub["grad"]

        # 若 η 已满足 sub_obj（在容差内），无需加割
        if eta_val >= sub_obj - 1e-4 * max(1.0, abs(sub_obj)):
            return

        # 次梯度割：η >= sub_obj + Σ grad·(z - z̄)
        #         => η - Σ grad·z >= sub_obj - Σ grad·z̄
        grad_dot_zbar = sum(grad[k] * z_bar.get(k, 0.0) for k in grad)
        rhs = sub_obj - grad_dot_zbar
        model.cbLazy(
            eta - gp.quicksum(grad[k] * z[k] for k in grad) >= rhs
        )
        stats["n_cuts"] += 1
        l1 = sum(abs(v) for v in grad.values())
        stats["cut_features"].append({
            "cut_index": stats["n_cuts"],
            "sub_obj": round(sub_obj, 2),
            "grad_l1_norm": round(l1, 4),
            "eta_gap": round(sub_obj - eta_val, 2),
            "slack_active": sub.get("slack_active", False),
            # AI 重要性分数（与 benders_cutmgmt 同启发式）
            "score": round(sub_obj + l1 * 0.001, 4),
        })

    t0 = time.time()
    master.optimize(benders_callback)
    elapsed = time.time() - t0

    status_name = {2: "OPTIMAL", 9: "TIME_LIMIT", 3: "INFEASIBLE",
                   4: "INF_OR_UNBD"}.get(master.Status, str(master.Status))
    obj = master.ObjVal if master.SolCount > 0 else None
    gap = master.MIPGap if master.SolCount > 0 else None

    facilities = []
    if master.SolCount > 0:
        for j in candidate_ids:
            for t in active_types:
                for c in range(len(config.capacity_index[t])):
                    if z[j, t, c].X > 0.5:
                        facilities.append({
                            "site": j, "type": t,
                            "capacity": config.capacity_index[t][c]["capacity"],
                            "capacity_idx": c,
                        })

    if verbose:
        gap_str = f"{gap*100:.4f}%" if gap is not None else "N/A"
        print(f"\nLazy Benders: status={status_name}, obj={obj}, "
              f"gap={gap_str}, cuts={stats['n_cuts']}, t={elapsed:.1f}s")

    return LazyBendersResult(
        status=status_name,
        objective=obj,
        bound=master.ObjBound,
        mip_gap_pct=round(gap * 100, 4) if gap is not None else None,
        elapsed_sec=round(elapsed, 2),
        n_lazy_cuts=stats["n_cuts"],
        facilities=facilities,
        cut_features=stats["cut_features"],
    )
