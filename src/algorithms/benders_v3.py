"""v3.0 容量链 Benders 分解实现

将 build_and_solve_v3 的完整 MIP 分解为：
  Master problem:  z[j,t,c] 选址决策 (binary) + η (cost-to-go)
  Subproblem:      x[i,j,t] 分配决策 (continuous, LP, given z̄)

Benders 最优性割：
  η >= dual_obj(z̄) + ∇_z [dual_obj](z - z̄)
     = Σ_{i,t} π[i,t]*share[t]
       + Σ_{i,j,t} λ[i,j,t] * Σ_c z[j,t,c]

子问题对 z̄ 总是可行（对任意 z̄≥0 子问题有界），故只需最优性割，无可行性割。

Benders cut-ranking 钩子：
  每轮迭代产生一条 cut；当 active cut 数超过预算 K 时，
  用 CutScorer（与 benders_cutmgmt_comparison 同接口）决定保留哪些。
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import gurobipy as gp
from gurobipy import GRB

from src.models.single_level_mip_v2_1 import DataConfig
from src.models.capacity_chain_assumptions import (
    CapacityChainAssumptions,
    _channel_map,
    default_assumptions,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


# ── 数据类 ─────────────────────────────────────────────────────────────────────

@dataclass
class BendersCut:
    """一条 Benders 割（最优性割或可行性割）。"""
    iteration: int
    rhs_const: float            # Σ π[i,t]*share[t]（常数项）
    z_coeffs: dict[tuple, float]  # (j,t,c) → 系数 Σ_i λ[i,j,t] + μ·cap
    sub_obj: float              # 子问题目标值（用于诊断）
    score: float = 0.0          # AI scorer 打分（越高越重要）
    is_feasibility: bool = False  # True=可行性割（无 η），False=最优性割

    def add_to_master(self, master: gp.Model, z: dict, eta: gp.Var, name: str) -> None:
        """把这条 cut 加入主问题。"""
        if self.is_feasibility:
            # 可行性割：rhs_const + Σ z_coeffs·z <= 0（排除不可行 z̄），不含 η
            expr = self.rhs_const + gp.quicksum(
                self.z_coeffs.get(key, 0.0) * z_var
                for key, z_var in z.items()
            )
            master.addConstr(expr <= 0, name=name)
        else:
            # 最优性割：η >= rhs_const + Σ z_coeffs·z
            lhs = eta + gp.quicksum(
                -self.z_coeffs.get(key, 0.0) * z_var
                for key, z_var in z.items()
            )
            master.addConstr(lhs >= self.rhs_const, name=name)


@dataclass
class BendersResult:
    """Benders 求解结果。"""
    status: str
    objective: float | None
    lower_bound: float
    mip_gap_pct: float | None
    iterations: int
    elapsed_sec: float
    cuts_added: int
    cuts_dropped: int
    convergence: list[dict]     # per-iteration: {iter, lb, ub, gap, elapsed}
    facilities: list[dict]
    claim_boundary: str = (
        "Benders decomposition on v3.0 capacity-chain MIP. "
        "Subproblem LP solved exactly; master MIP solved with Gurobi. "
        "County-level case (39 nodes), not enterprise-scale validation."
    )


# ── 子问题 ─────────────────────────────────────────────────────────────────────

def solve_subproblem(
    z_bar: dict[tuple, float],
    config: DataConfig,
    assumptions: CapacityChainAssumptions,
    candidate_ids: list[str],
    demand_ids: list[str],
) -> dict[str, Any]:
    """
    给定 z̄，求解连续分配子问题（LP）。

    Returns dict:
        feasible:  True 当且仅当子问题 OPTIMAL
        sub_obj:   子问题目标值（运输+损耗+碳）
        pi:        dual[channel_share]  对偶值 (i,t)
        lam:       dual[assign_open]    对偶值 (i,j,t)
        mu:        dual[peak_capacity]  对偶值 (j,t)
    """
    channels = _channel_map(assumptions)
    active_types = [ch.type_id for ch in assumptions.channels if ch.annual_share > 0]
    demand = {nid: config.get_demand(nid) for nid in demand_ids}
    precool_limit_h = config.get_preservation_params().get("precool_time_limit_h", 2.0)

    open_cap: dict[tuple, float] = {}
    for site in candidate_ids:
        for type_id in active_types:
            cap_sum = sum(
                z_bar.get((site, type_id, cap_idx), 0.0)
                for cap_idx in range(len(config.capacity_index[type_id]))
            )
            open_cap[site, type_id] = cap_sum

    sub = gp.Model("subproblem")
    sub.setParam("OutputFlag", 0)
    sub.setParam("Method", 1)        # dual simplex

    x: dict = {}
    for demand_id in demand_ids:
        for site in candidate_ids:
            for type_id in active_types:
                x[demand_id, site, type_id] = sub.addVar(
                    vtype=GRB.CONTINUOUS, lb=0.0,  # 上界改为显式约束以收集对偶 ν
                    name=f"x_{demand_id}_{site}_{type_id}",
                )

    # 松弛变量：channel_share 缺额 s[i,t]，保证子问题对任意 z̄ 总可行
    # (relatively complete recourse)。惩罚 BIG_M 需适中：太大(1e7)会污染对偶值
    # 使 cut 系数爆炸、触发 Gurobi 数值容差误判；太小则松弛不被抑制。
    # 取单位缺额惩罚 ≈ 最贵单点分配成本的若干倍，量级 ~1e5。
    BIG_M = 5e5
    s: dict = {}
    for demand_id in demand_ids:
        for type_id in active_types:
            s[demand_id, type_id] = sub.addVar(
                vtype=GRB.CONTINUOUS, lb=0.0, name=f"s_{demand_id}_{type_id}"
            )

    sub.update()

    # channel_share（含松弛）：Σ_j x[i,j,t] + s[i,t] == share[t]
    pi_constrs: dict[tuple, gp.Constr] = {}
    for demand_id in demand_ids:
        for type_id in active_types:
            share = channels[type_id].annual_share
            c = sub.addConstr(
                gp.quicksum(x[demand_id, site, type_id] for site in candidate_ids)
                + s[demand_id, type_id] == share,
                name=f"cs_{demand_id}_{type_id}",
            )
            pi_constrs[demand_id, type_id] = c

    lam_constrs: dict[tuple, gp.Constr] = {}
    for demand_id in demand_ids:
        for site in candidate_ids:
            for type_id in active_types:
                rhs = open_cap.get((site, type_id), 0.0)
                if config.get_time(demand_id, site) > precool_limit_h and type_id == "precool":
                    rhs = 0.0
                c = sub.addConstr(
                    x[demand_id, site, type_id] <= rhs,
                    name=f"ao_{demand_id}_{site}_{type_id}",
                )
                lam_constrs[demand_id, site, type_id] = c

    # peak_capacity 约束（连接 x 和 z̄ 的核心耦合约束）
    # peak_load[j,t] = Σ_i x·demand·storage_days/harvest_window·peak_factor <= capacity(z̄)
    mu_constrs: dict[tuple, gp.Constr] = {}
    installed_cap: dict[tuple, float] = {}  # (j,t) → Σ_c z̄·cap_value
    for site in candidate_ids:
        for type_id in active_types:
            cap_val = sum(
                z_bar.get((site, type_id, cap_idx), 0.0)
                * config.capacity_index[type_id][cap_idx]["capacity"]
                for cap_idx in range(len(config.capacity_index[type_id]))
            )
            installed_cap[site, type_id] = cap_val
            channel = channels[type_id]
            peak_load = gp.quicksum(
                x[demand_id, site, type_id]
                * demand[demand_id]
                * channel.storage_days
                / assumptions.harvest_window_days
                * assumptions.harvest_peak_factor
                for demand_id in demand_ids
            )
            c = sub.addConstr(peak_load <= cap_val, name=f"pc_{site}_{type_id}")
            mu_constrs[site, type_id] = c

    # x <= 1 上界显式约束（收集对偶 ν，进入 cut 常数项保证强对偶紧）
    nu_constrs: dict[tuple, gp.Constr] = {}
    for demand_id in demand_ids:
        for site in candidate_ids:
            for type_id in active_types:
                c = sub.addConstr(
                    x[demand_id, site, type_id] <= 1.0,
                    name=f"ub_{demand_id}_{site}_{type_id}",
                )
                nu_constrs[demand_id, site, type_id] = c

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
    slack_penalty = BIG_M * gp.quicksum(
        s[demand_id, type_id]
        for demand_id in demand_ids
        for type_id in active_types
    )
    sub.setObjective(transport_cost + loss_cost + carbon_cost + slack_penalty, GRB.MINIMIZE)
    sub.optimize()

    if sub.Status == GRB.OPTIMAL:
        sub_obj = sub.ObjVal
        slack_total = sum(s[k].X for k in s)
        pi = {k: c.Pi for k, c in pi_constrs.items()}
        lam = {k: c.Pi for k, c in lam_constrs.items()}
        mu = {k: c.Pi for k, c in mu_constrs.items()}
        # ν·1 常数项（x<=1 上界对偶），进入 cut 常数项保证强对偶紧
        nu_const = sum(c.Pi for c in nu_constrs.values())
        return {"feasible": True, "sub_obj": sub_obj, "pi": pi, "lam": lam, "mu": mu,
                "nu_const": nu_const,
                "slack_active": slack_total > 1e-6, "slack_total": slack_total}

    # 理论上加松弛后子问题总可行；保险起见返回不可行标志
    return {"feasible": False, "sub_obj": 0.0, "pi": {}, "lam": {}, "mu": {},
            "nu_const": 0.0, "slack_active": True, "slack_total": float("inf")}


# ── 主问题 ─────────────────────────────────────────────────────────────────────

def build_master(
    config: DataConfig,
    assumptions: CapacityChainAssumptions,
    candidate_ids: list[str],
    active_types: list[str],
    eta_lower: float = 0.0,
) -> tuple[gp.Model, dict, gp.Var]:
    """构建主问题（选址 + η）。"""
    channels = _channel_map(assumptions)
    master = gp.Model("master")
    master.setParam("OutputFlag", 0)

    z: dict = {}
    for site in candidate_ids:
        for type_id in active_types:
            for cap_idx in range(len(config.capacity_index[type_id])):
                z[site, type_id, cap_idx] = master.addVar(
                    vtype=GRB.BINARY, name=f"z_{site}_{type_id}_{cap_idx}"
                )

    eta = master.addVar(lb=eta_lower, name="eta")
    master.update()

    for site in candidate_ids:
        master.addConstr(
            gp.quicksum(
                z[site, type_id, cap_idx]
                for type_id in active_types
                for cap_idx in range(len(config.capacity_index[type_id]))
            ) <= 1,
            name=f"one_facility_{site}",
        )
    master.addConstr(
        gp.quicksum(
            z[site, type_id, cap_idx]
            for site in candidate_ids
            for type_id in active_types
            for cap_idx in range(len(config.capacity_index[type_id]))
        ) >= 1,
        name="min_one_facility",
    )
    master.addConstr(
        gp.quicksum(
            z[site, type_id, cap_idx]
            for site in candidate_ids
            for type_id in active_types
            for cap_idx in range(len(config.capacity_index[type_id]))
        ) <= assumptions.max_facilities,
        name="max_facilities",
    )
    # 每种 active 通道至少开一个设施，否则子问题 channel_share 等式不可行
    for type_id in active_types:
        master.addConstr(
            gp.quicksum(
                z[site, type_id, cap_idx]
                for site in candidate_ids
                for cap_idx in range(len(config.capacity_index[type_id]))
            ) >= 1,
            name=f"min_one_{type_id}",
        )

    # precool 覆盖约束：每个需求点必须有 ≥1 个 precool 设施在 2h 内
    # 否则子问题 channel_share(precool)==1.0 与 precool_time==0 矛盾
    if "precool" in active_types:
        precool_limit_h = config.get_preservation_params().get("precool_time_limit_h", 2.0)
        demand_ids_master = list(config.demands["node_id"])
        for demand_id in demand_ids_master:
            nearby = [
                (site, cap_idx)
                for site in candidate_ids
                for cap_idx in range(len(config.capacity_index["precool"]))
                if config.get_time(demand_id, site) <= precool_limit_h
            ]
            if nearby:  # 只在有可达站点时加约束（否则问题本身不可行）
                master.addConstr(
                    gp.quicksum(z[site, "precool", cap_idx] for site, cap_idx in nearby) >= 1,
                    name=f"precool_cover_{demand_id}",
                )

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
    master.setObjective(fixed_cost + operate_cost + eta, GRB.MINIMIZE)
    master.update()
    return master, z, eta


# ── 主 Benders 循环 ────────────────────────────────────────────────────────────

CutPolicy = Callable[[list[BendersCut], int], list[BendersCut]]


def policy_all_cuts(cuts: list[BendersCut], budget: int) -> list[BendersCut]:
    """经典 Benders：保留所有 cut。"""
    return cuts


def policy_recency_k(cuts: list[BendersCut], budget: int) -> list[BendersCut]:
    """保留最新 K 条。"""
    return cuts[-budget:] if len(cuts) > budget else cuts


def policy_random_k(cuts: list[BendersCut], budget: int) -> list[BendersCut]:
    """随机保留 K 条。"""
    import random
    if len(cuts) <= budget:
        return cuts
    return random.sample(cuts, budget)


def policy_learned_k(cuts: list[BendersCut], budget: int) -> list[BendersCut]:
    """按 score 降序保留 top-K（AI 策略钩子）。"""
    if len(cuts) <= budget:
        return cuts
    return sorted(cuts, key=lambda c: c.score, reverse=True)[:budget]


def _score_cuts(cuts: list[BendersCut]) -> None:
    """
    简单特征打分（可替换为 ML 模型）：
    score = sub_obj（子问题目标越大，cut 越紧越重要）+
            norm_coeff（系数 L1 范数越大，cut 越强）
    """
    for cut in cuts:
        norm = sum(abs(v) for v in cut.z_coeffs.values())
        cut.score = cut.sub_obj + norm * 0.001


def benders_solve_v3(
    config: DataConfig,
    assumptions: CapacityChainAssumptions | None = None,
    cut_budget: int = 9999,     # 9999 = all_cuts (无限制)
    cut_policy: CutPolicy = policy_all_cuts,
    max_iterations: int = 200,
    time_limit: float = 600.0,
    gap_tol: float = 0.01,
    master_time_per_iter: float = 30.0,
    verbose: bool = True,
) -> BendersResult:
    """
    v3.0 容量链 Benders 分解主循环。

    Args:
        config:        DataConfig（支持 OSM 或 Haversine 矩阵）
        assumptions:   容量链假设（默认）
        cut_budget:    active cut 预算 K
        cut_policy:    cut 管理策略函数
        max_iterations: 最大迭代数
        time_limit:    总时限（秒）
        gap_tol:       收敛 gap 容差
        master_time_per_iter: 每次主问题求解时限
        verbose:       打印进度
    """
    assumptions = assumptions or default_assumptions()
    channels = _channel_map(assumptions)
    active_types = [ch.type_id for ch in assumptions.channels if ch.annual_share > 0]
    candidate_ids = list(config.candidates["node_id"])
    demand_ids = list(config.demands["node_id"])

    # 固定+运营成本下界（η 初始化用）
    min_fixed = min(
        config.capacity_index[t][0]["fixed_cost"] * 10000
        for t in active_types
    )
    eta_lb = 0.0

    master, z, eta = build_master(config, assumptions, candidate_ids, active_types, eta_lb)
    master.setParam("TimeLimit", master_time_per_iter)
    master.setParam("MIPGap", 0.001)   # 主问题内部精度高一点

    all_cuts: list[BendersCut] = []
    upper_bound = float("inf")
    lower_bound = -float("inf")
    convergence: list[dict] = []
    cuts_dropped = 0
    t_start = time.time()

    if verbose:
        print(f"\n{'='*64}")
        print(f"Benders v3.0: candidates={len(candidate_ids)}, "
              f"demands={len(demand_ids)}, policy={cut_policy.__name__}, K={cut_budget}")
        print(f"{'='*64}")
        print(f"{'Iter':>4} {'LB':>14} {'UB':>14} {'Gap%':>8} {'#Cuts':>6} {'t(s)':>7}")
        print("-" * 64)

    for iteration in range(1, max_iterations + 1):
        elapsed = time.time() - t_start
        if elapsed >= time_limit:
            break

        # ── 求解主问题 ─────────────────────────────────────────────────────
        master.setParam("TimeLimit", min(master_time_per_iter, time_limit - elapsed))
        master.optimize()

        if master.SolCount == 0:
            break

        lower_bound = master.ObjBound
        z_bar = {key: var.X for key, var in z.items()}
        eta_val = eta.X

        # ── 求解子问题 ─────────────────────────────────────────────────────
        sub_result = solve_subproblem(
            z_bar, config, assumptions, candidate_ids, demand_ids
        )
        sub_obj = sub_result["sub_obj"]
        pi = sub_result["pi"]
        lam = sub_result["lam"]
        mu = sub_result["mu"]
        slack_active = sub_result.get("slack_active", False)
        # 真实可行解 = 子问题求解成功 且 松弛未激活（容量足够）
        sub_feasible = sub_result["feasible"] and not slack_active

        # 当前上界 = 固定/运营成本 + 子问题分配成本（仅真实可行解才更新）
        fixed_op = sum(
            z_bar.get((site, type_id, cap_idx), 0.0)
            * config.capacity_index[type_id][cap_idx]["fixed_cost"] * 10000
            for site in candidate_ids
            for type_id in active_types
            for cap_idx in range(len(config.capacity_index[type_id]))
        ) + sum(
            z_bar.get((site, type_id, cap_idx), 0.0)
            * config.capacity_index[type_id][cap_idx]["operate_cost"] * 10000
            for site in candidate_ids
            for type_id in active_types
            for cap_idx in range(len(config.capacity_index[type_id]))
        )
        if sub_feasible:
            ub_candidate = fixed_op + sub_obj
            upper_bound = min(upper_bound, ub_candidate)

        # gap 只在有上界时计算
        if upper_bound < float("inf"):
            gap = (upper_bound - lower_bound) / max(1e-10, abs(upper_bound))
        else:
            gap = float("inf")
        elapsed = time.time() - t_start

        convergence.append({
            "iteration": iteration,
            "lower_bound": round(lower_bound, 4),
            "upper_bound": round(upper_bound, 4) if upper_bound < float("inf") else None,
            "gap_pct": round(gap * 100, 4) if gap < float("inf") else None,
            "cuts_active": len(all_cuts),
            "sub_feasible": sub_feasible,
            "elapsed_sec": round(elapsed, 2),
        })

        if verbose:
            ub_str = f"{upper_bound:>14.2f}" if upper_bound < float("inf") else f"{'inf':>14}"
            gap_str = f"{gap*100:>7.3f}%" if gap < float("inf") else f"{'inf':>8}"
            print(f"{iteration:>4} {lower_bound:>14.2f} {ub_str} "
                  f"{gap_str} {len(all_cuts):>6} {elapsed:>6.1f}s")

        if gap <= gap_tol:
            break

        # ── 生成 Benders 最优性割（次梯度形式，避免对偶符号陷阱）──────────
        # η >= sub_obj(z̄) + Σ grad[j,t,c]·(z - z̄)
        #   = [sub_obj - Σ grad·z̄] + Σ grad·z
        # 包络定理：grad[j,t,c] = ∂sub_obj/∂z = λ_sum[j,t] + μ[j,t]·capval[t,c]
        # 该形式在 z̄ 处自动等于 sub_obj（cut 紧），无需 π/ν 常数项。
        z_coeffs: dict[tuple, float] = {}
        for site in candidate_ids:
            for type_id in active_types:
                lam_sum = sum(
                    lam.get((demand_id, site, type_id), 0.0)
                    for demand_id in demand_ids
                )
                mu_jt = mu.get((site, type_id), 0.0)
                for cap_idx in range(len(config.capacity_index[type_id])):
                    cap_value = config.capacity_index[type_id][cap_idx]["capacity"]
                    coeff = lam_sum + mu_jt * cap_value
                    if abs(coeff) > 1e-8:
                        z_coeffs[site, type_id, cap_idx] = coeff
        # rhs_const = sub_obj - Σ grad·z̄
        grad_dot_zbar = sum(
            z_coeffs[key] * z_bar.get(key, 0.0) for key in z_coeffs
        )
        rhs_const = sub_obj - grad_dot_zbar
        cut = BendersCut(
            iteration=iteration, rhs_const=rhs_const,
            z_coeffs=z_coeffs, sub_obj=sub_obj, is_feasibility=False,
        )
        all_cuts.append(cut)

        # ── AI 打分 + cut 管理 ─────────────────────────────────────────────
        _score_cuts(all_cuts)
        active_cuts = cut_policy(all_cuts, cut_budget)
        cuts_dropped += len(all_cuts) - len(active_cuts)

        # 重建主问题 cut 约束（只保留 active cuts）
        for c in master.getConstrs():
            if c.ConstrName.startswith("benders_cut_"):
                master.remove(c)
        master.update()
        for idx, bc in enumerate(active_cuts):
            bc.add_to_master(master, z, eta, f"benders_cut_{idx}")
        master.update()

    # ── 提取最优设施选址 ──────────────────────────────────────────────────────
    facilities = []
    if upper_bound < float("inf"):
        # 用最后一次 z̄（最优主问题解）
        for site in candidate_ids:
            for type_id in active_types:
                for cap_idx in range(len(config.capacity_index[type_id])):
                    if z_bar.get((site, type_id, cap_idx), 0.0) > 0.5:
                        cap_info = config.capacity_index[type_id][cap_idx]
                        facilities.append({
                            "site": site,
                            "type": type_id,
                            "capacity": cap_info["capacity"],
                            "capacity_idx": cap_idx,
                        })

    elapsed_total = time.time() - t_start
    final_gap = (
        (upper_bound - lower_bound) / max(1e-10, abs(upper_bound))
        if upper_bound < float("inf") else None
    )

    if verbose:
        print("=" * 64)
        print(f"Done: {iteration} iterations, {elapsed_total:.1f}s")
        print(f"UB={upper_bound:.2f}, LB={lower_bound:.2f}, "
              f"Gap={final_gap*100:.4f}%" if final_gap else "no UB")
        print(f"Cuts total={len(all_cuts)}, dropped={cuts_dropped}")

    return BendersResult(
        status="gap_satisfied" if (final_gap and final_gap <= gap_tol) else "time_limit",
        objective=upper_bound if upper_bound < float("inf") else None,
        lower_bound=lower_bound,
        mip_gap_pct=round(final_gap * 100, 4) if final_gap else None,
        iterations=iteration,
        elapsed_sec=round(elapsed_total, 2),
        cuts_added=len(all_cuts),
        cuts_dropped=cuts_dropped,
        convergence=convergence,
        facilities=facilities,
    )
