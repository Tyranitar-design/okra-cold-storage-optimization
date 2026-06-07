"""v3.0 capacity-chain layout evaluator for heuristics (NSGA-III / ALNS).

设计
----
v3.0 容量链模型的决策变量是 z[j,t,c]（离散选址）+ x[i,j,t]（连续多通道分配）。
启发式只搜索 z 空间（选址决策），给定 z 后用 LP 子问题求最优 x。
这与 v2.1 的 LayoutEvaluator (单点分配 a[i]) 是不同语义。

基因型 (genome)
---------------
每候选点 j 编码一个整数 g[j] ∈ {0, 1, 2, ..., total_choices}：
  - g[j] = 0: 该候选点不开放（无设施）
  - g[j] = k > 0: 该候选点开放第 (type, cap_idx) 选择，按 choice_table[k-1] 解码

choice_table 列出所有 (type, cap_idx) 组合（4 types × ~4 caps = ~16 选项）。

约束（启发式自动惩罚）
-----------------------
- 每候选点至多一个设施（基因型自然保证）
- 总设施数 <= max_facilities（违反则惩罚）
- 每种通道至少一个设施（违反则 LP 子问题靠松弛兜底，自然惩罚）
- precool 覆盖（同上，子问题用松弛保证可行 + BIG_M 惩罚）
- peak_capacity（子问题硬约束 + 松弛）

三目标
------
- cost (yuan)       = fixed + operate + transport + loss·loss_price + carbon·carbon_price
- loss_ton          = total spoilage tonnage from x assignments
- carbon_ton        = total CO2-equivalent tonnage

LP 子问题在每次 evaluate() 时重建并求解（毫秒级），整个 NSGA-III 100 代 × 100 pop
约 10 万次 evaluate ≈ 几分钟。
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


PENALTY_INFEASIBLE = 1e12
BIG_M_SLACK = 5e5  # subproblem 松弛缺额惩罚


@dataclass
class LayoutEvaluatorV3:
    """v3.0 capacity-chain evaluator for heuristics."""

    config: DataConfig
    assumptions: CapacityChainAssumptions
    candidate_ids: list[str]
    demand_ids: list[str]
    active_types: list[str] = field(init=False)
    choice_table: list[tuple[str, int]] = field(init=False)
    n_candidates: int = field(init=False)
    n_choices: int = field(init=False)

    # 缓存
    _channels: Any = field(init=False)
    _demand: dict[str, float] = field(init=False)
    _precool_limit_h: float = field(init=False)

    # 子问题求解统计
    _eval_count: int = 0
    _lp_solve_time_total: float = 0.0

    def __post_init__(self):
        self._channels = _channel_map(self.assumptions)
        self.active_types = [c.type_id for c in self.assumptions.channels if c.annual_share > 0]
        # 构造 choice_table: 所有 (type, cap_idx) 组合
        self.choice_table = []
        for t in self.active_types:
            for c in range(len(self.config.capacity_index[t])):
                self.choice_table.append((t, c))
        self.n_candidates = len(self.candidate_ids)
        self.n_choices = len(self.choice_table)
        self._demand = {nid: self.config.get_demand(nid) for nid in self.demand_ids}
        self._precool_limit_h = self.config.get_preservation_params().get("precool_time_limit_h", 2.0)

    # ── 基因型解码 ────────────────────────────────────────────────────────────

    def decode_genome(self, genome: list[int]) -> dict[tuple, float]:
        """genome[j] ∈ {0, 1, ..., n_choices}; 0=不开放; k>0=choice_table[k-1]
        返回 z_bar dict: (site, type, cap_idx) → 0/1。"""
        z = {(j, t, c): 0.0 for j in self.candidate_ids for t in self.active_types
             for c in range(len(self.config.capacity_index[t]))}
        for jdx, g in enumerate(genome):
            if g <= 0:
                continue
            site = self.candidate_ids[jdx]
            choice_idx = (g - 1) % self.n_choices  # 安全 wrap
            t, c = self.choice_table[choice_idx]
            z[site, t, c] = 1.0
        return z

    # ── 静态可行性检查（不调 LP）────────────────────────────────────────────

    def static_feasibility(self, z: dict) -> tuple[bool, str]:
        n_open = sum(1 for v in z.values() if v > 0.5)
        if n_open == 0:
            return False, "no_facility_open"
        if n_open > self.assumptions.max_facilities:
            return False, f"exceeds_max_facilities_{n_open}"
        # 每种通道至少一个设施
        for t in self.active_types:
            if not any(z[(j, t, c)] > 0.5 for j in self.candidate_ids
                       for c in range(len(self.config.capacity_index[t]))):
                return False, f"no_facility_for_type_{t}"
        return True, "ok"

    # ── LP 子问题求解 ────────────────────────────────────────────────────────

    def solve_subproblem_v3(self, z_bar: dict) -> dict[str, Any]:
        """给定 z_bar，求 LP 子问题，返回三目标分量 + slack 信息。"""
        config = self.config
        a = self.assumptions
        ch = self._channels
        ats = self.active_types
        cids = self.candidate_ids
        dids = self.demand_ids
        demand = self._demand

        installed_cap: dict[tuple, float] = {}
        open_cap: dict[tuple, float] = {}
        for site in cids:
            for t in ats:
                cap_val = sum(
                    z_bar.get((site, t, c), 0.0) * config.capacity_index[t][c]["capacity"]
                    for c in range(len(config.capacity_index[t]))
                )
                installed_cap[site, t] = cap_val
                open_cap[site, t] = sum(
                    z_bar.get((site, t, c), 0.0)
                    for c in range(len(config.capacity_index[t]))
                )

        sub = gp.Model("sub_v3_eval")
        sub.setParam("OutputFlag", 0)
        sub.setParam("Method", 1)

        x = {(d, j, t): sub.addVar(lb=0.0, name=f"x_{d}_{j}_{t}")
             for d in dids for j in cids for t in ats}
        s = {(d, t): sub.addVar(lb=0.0, name=f"s_{d}_{t}") for d in dids for t in ats}
        sub.update()

        for d in dids:
            for t in ats:
                sub.addConstr(
                    gp.quicksum(x[d, j, t] for j in cids) + s[d, t] == ch[t].annual_share,
                )

        for d in dids:
            for j in cids:
                for t in ats:
                    rhs = open_cap.get((j, t), 0.0)
                    if t == "precool" and config.get_time(d, j) > self._precool_limit_h:
                        rhs = 0.0
                    sub.addConstr(x[d, j, t] <= rhs)

        for j in cids:
            for t in ats:
                ch_t = ch[t]
                peak = gp.quicksum(
                    x[d, j, t] * demand[d] * ch_t.storage_days
                    / a.harvest_window_days * a.harvest_peak_factor
                    for d in dids
                )
                sub.addConstr(peak <= installed_cap.get((j, t), 0.0))

        # 三目标分量（变量分别累计）
        transport = gp.quicksum(
            x[d, j, t] * demand[d] * config.get_dist(d, j) * a.transport_cost_yuan_per_ton_km
            for d in dids for j in cids for t in ats
        )
        loss_ton_var = gp.quicksum(
            x[d, j, t] * demand[d]
            * (config.get_time(d, j)
               * config.get_preservation_params().get("transport_loss_per_hour", 0.02)
               * ch[t].transport_loss_multiplier + ch[t].loss_rate)
            for d in dids for j in cids for t in ats
        )
        carbon_ton_var = gp.quicksum(
            x[d, j, t] * demand[d]
            * (config.capacity_index[t][0]["energy_cost_per_ton"]
               * config.capacity_index[t][0]["carbon_factor"] / 1000
               + config.get_dist(d, j) * a.transport_carbon_kg_per_ton_km / 1000)
            for d in dids for j in cids for t in ats
        )
        slack_pen = BIG_M_SLACK * gp.quicksum(s[d, t] for d in dids for t in ats)
        # 子问题 LP 目标：min weighted (cost = transport + loss·price + carbon·price + slack)
        sub.setObjective(
            transport + loss_ton_var * a.loss_price + carbon_ton_var * a.carbon_price + slack_pen,
            GRB.MINIMIZE,
        )

        t0 = time.time()
        sub.optimize()
        self._lp_solve_time_total += time.time() - t0

        if sub.Status != GRB.OPTIMAL:
            return {"feasible": False, "transport": 0.0, "loss_ton": 0.0,
                    "carbon_ton": 0.0, "slack_total": float("inf")}

        slack_total = sum(s[k].X for k in s)
        return {
            "feasible": True,
            "transport": float(transport.getValue()),
            "loss_ton": float(loss_ton_var.getValue()),
            "carbon_ton": float(carbon_ton_var.getValue()),
            "slack_total": slack_total,
            "slack_active": slack_total > 1e-4,
        }

    # ── 主评估接口 ────────────────────────────────────────────────────────────

    def evaluate(self, genome: list[int]) -> dict[str, Any]:
        """评估一个基因型，返回三目标值（最小化）+ 可行性信息。"""
        self._eval_count += 1
        z = self.decode_genome(genome)
        ok, reason = self.static_feasibility(z)
        if not ok:
            return {
                "cost": PENALTY_INFEASIBLE, "loss_ton": PENALTY_INFEASIBLE,
                "carbon_ton": PENALTY_INFEASIBLE, "feasible": False,
                "infeasible_reason": reason, "n_facilities": sum(1 for v in z.values() if v > 0.5),
            }

        sub = self.solve_subproblem_v3(z)
        if not sub["feasible"]:
            return {
                "cost": PENALTY_INFEASIBLE, "loss_ton": PENALTY_INFEASIBLE,
                "carbon_ton": PENALTY_INFEASIBLE, "feasible": False,
                "infeasible_reason": "subproblem_infeasible",
                "n_facilities": sum(1 for v in z.values() if v > 0.5),
            }

        # 固定+运营成本
        fixed = sum(
            z[(j, t, c)] * self.config.capacity_index[t][c]["fixed_cost"] * 10000
            for j in self.candidate_ids for t in self.active_types
            for c in range(len(self.config.capacity_index[t]))
        )
        operate = sum(
            z[(j, t, c)] * self.config.capacity_index[t][c]["operate_cost"] * 10000
            for j in self.candidate_ids for t in self.active_types
            for c in range(len(self.config.capacity_index[t]))
        )

        cost = (fixed + operate + sub["transport"]
                + sub["loss_ton"] * self.assumptions.loss_price
                + sub["carbon_ton"] * self.assumptions.carbon_price)

        n_facilities = sum(1 for v in z.values() if v > 0.5)
        # 如果松弛激活，认为该解不真实可行，加重惩罚使启发式避开
        if sub["slack_active"]:
            cost += BIG_M_SLACK * sub["slack_total"]

        return {
            "cost": float(cost),
            "loss_ton": float(sub["loss_ton"]),
            "carbon_ton": float(sub["carbon_ton"]),
            "feasible": not sub["slack_active"],
            "slack_total": float(sub["slack_total"]),
            "n_facilities": n_facilities,
            "fixed_cost": float(fixed),
            "operate_cost": float(operate),
            "transport_cost": float(sub["transport"]),
        }


def make_evaluator_v3(config: DataConfig, assumptions: CapacityChainAssumptions | None = None,
                     candidate_ids: list[str] | None = None,
                     demand_ids: list[str] | None = None) -> LayoutEvaluatorV3:
    """便捷构造器。"""
    a = assumptions or default_assumptions()
    cids = candidate_ids or list(config.candidates["node_id"])
    dids = demand_ids or list(config.demands["node_id"])
    return LayoutEvaluatorV3(
        config=config, assumptions=a, candidate_ids=cids, demand_ids=dids,
    )
