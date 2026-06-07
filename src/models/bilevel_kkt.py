"""
秋葵冷库布局双层模型的 KKT 单层转化版本。

说明：
- 上层负责设施选址、类型和容量等级
- 下层在给定设施开放状态后，按单位广义成本对需求进行分配
- 这里采用乐观双层的 KKT 转化思路，但实际实现使用显式线性化的
  单层 MILP 来保持可运行性和可验证性
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import gurobipy as gp
from gurobipy import GRB

from src.models.layout_problem import (
    build_layout_data,
    get_capacity,
    get_carbon_ton_per_ton,
    get_fixed_cost,
    get_lower_level_unit_cost,
    get_operate_cost,
    get_social_cost_components,
)


def build_and_solve_bilevel_kkt(
    config: Any,
    carbon_price: float = 50.0,
    loss_price: float = 3000.0,
    max_facilities: int = 8,
    candidate_ids: Optional[List[str]] = None,
    demand_ids: Optional[List[str]] = None,
    time_limit: int = 300,
    mip_gap: float = 0.01,
    threads: int = 8,
    verbose: bool = True,
) -> Tuple[gp.Model, Dict[tuple, gp.Var], Dict[tuple, gp.Var], Dict[str, Any]]:
    """构建并求解双层 KKT 单层转化模型。"""
    data = build_layout_data(config, candidate_ids=candidate_ids, demand_ids=demand_ids)
    candidate_ids = data.candidate_ids
    demand_ids = data.demand_ids
    storage_types = data.storage_types

    model = gp.Model("OkraColdStorage_Bilevel_KKT")
    model.setParam("TimeLimit", time_limit)
    model.setParam("MIPGap", mip_gap)
    model.setParam("Threads", threads)
    model.setParam("OutputFlag", 1 if verbose else 0)

    z: Dict[tuple, gp.Var] = {}
    x: Dict[tuple, gp.Var] = {}
    w: Dict[tuple, gp.Var] = {}
    alpha: Dict[str, gp.Var] = {}
    beta: Dict[tuple, gp.Var] = {}
    gamma: Dict[tuple, gp.Var] = {}

    # 上层决策：设施开放与容量等级
    for j in candidate_ids:
        for t in storage_types:
            for c in range(len(config.capacity_index[t])):
                z[j, t, c] = model.addVar(vtype=GRB.BINARY, name=f"z_{j}_{t}_{c}")

    # 下层决策：分配（放松为 LP，便于 KKT/强对偶精确化）
    for i in demand_ids:
        for j in candidate_ids:
            for t in storage_types:
                x[i, j, t] = model.addVar(vtype=GRB.CONTINUOUS, lb=0.0, ub=1.0, name=f"x_{i}_{j}_{t}")

    # 下层对偶变量
    for i in demand_ids:
        alpha[i] = model.addVar(lb=-GRB.INFINITY, ub=GRB.INFINITY, vtype=GRB.CONTINUOUS, name=f"alpha_{i}")
    for i in demand_ids:
        for j in candidate_ids:
            for t in storage_types:
                beta[i, j, t] = model.addVar(lb=0.0, vtype=GRB.CONTINUOUS, name=f"beta_{i}_{j}_{t}")
    for j in candidate_ids:
        for t in storage_types:
            gamma[j, t] = model.addVar(lb=0.0, vtype=GRB.CONTINUOUS, name=f"gamma_{j}_{t}")

    # 仅保留占位变量，避免旧接口破坏
    for i in demand_ids:
        for j in candidate_ids:
            for t in storage_types:
                w[i, j, t] = model.addVar(vtype=GRB.CONTINUOUS, lb=0.0, ub=1.0, name=f"w_{i}_{j}_{t}")

    model.update()

    # 上层约束
    for i in demand_ids:
        model.addConstr(gp.quicksum(x[i, j, t] for j in candidate_ids for t in storage_types) == 1, name=f"assign_once_{i}")

    for i in demand_ids:
        for j in candidate_ids:
            for t in storage_types:
                model.addConstr(
                    x[i, j, t] <= gp.quicksum(z[j, t, c] for c in range(len(config.capacity_index[t]))),
                    name=f"assign_open_{i}_{j}_{t}",
                )

    for j in candidate_ids:
        model.addConstr(
            gp.quicksum(z[j, t, c] for t in storage_types for c in range(len(config.capacity_index[t]))) <= 1,
            name=f"one_facility_{j}",
        )

    model.addConstr(
        gp.quicksum(z[j, t, c] for j in candidate_ids for t in storage_types for c in range(len(config.capacity_index[t])))
        <= max_facilities,
        name="max_facilities",
    )

    pp = config.get_preservation_params()
    big_m = 20.0
    for i in demand_ids:
        for j in candidate_ids:
            model.addConstr(
                config.get_time(i, j) * x[i, j, "precool"]
                <= pp["precool_time_limit_h"] * x[i, j, "precool"] + big_m * (1 - x[i, j, "precool"]),
                name=f"precool_{i}_{j}",
            )

    for j in candidate_ids:
        for t in storage_types:
            total_assigned = gp.quicksum(x[i, j, t] * data.demand[i] for i in demand_ids)
            total_capacity = gp.quicksum(
                z[j, t, c] * get_capacity(data, t, c)
                for c in range(len(config.capacity_index[t]))
            )
            model.addConstr(total_assigned <= total_capacity, name=f"capacity_{j}_{t}")

    # 下层最优性：强对偶 + 对偶可行
    lower_cost_expr = gp.LinExpr()
    dual_objective_expr = gp.LinExpr()
    for i in demand_ids:
        dual_objective_expr += alpha[i]
    for i in demand_ids:
        for j in candidate_ids:
            for t in storage_types:
                lower_unit_cost = get_lower_level_unit_cost(data, i, j, t, carbon_price, loss_price, include_carbon=True)
                model.addConstr(
                    alpha[i] + beta[i, j, t] + data.demand[i] * gamma[j, t] <= lower_unit_cost,
                    name=f"dual_feas_{i}_{j}_{t}",
                )
                lower_cost_expr += x[i, j, t] * data.demand[i] * lower_unit_cost
                dual_objective_expr += beta[i, j, t] * gp.quicksum(z[j, t, c] for c in range(len(config.capacity_index[t])))
    for j in candidate_ids:
        for t in storage_types:
            dual_objective_expr += gamma[j, t] * gp.quicksum(
                z[j, t, c] * get_capacity(data, t, c)
                for c in range(len(config.capacity_index[t]))
            )

    # 目标函数：上层建设/运营 + 上层静态碳排放
    fixed_cost = gp.quicksum(
        z[j, t, c] * get_fixed_cost(data, t, c) * 10000
        for j in candidate_ids for t in storage_types for c in range(len(config.capacity_index[t]))
    )
    operate_cost = gp.quicksum(
        z[j, t, c] * get_operate_cost(data, t, c) * 10000
        for j in candidate_ids for t in storage_types for c in range(len(config.capacity_index[t]))
    )
    static_carbon = gp.quicksum(
        z[j, t, c] * get_capacity(data, t, c)
        * data.config.get_storage_params(t)["energy_cost_per_ton"]
        * data.config.get_storage_params(t)["carbon_factor"] / 1000.0
        * carbon_price
        for j in candidate_ids for t in storage_types for c in range(len(config.capacity_index[t]))
    )

    model.addConstr(lower_cost_expr == dual_objective_expr, name="lower_level_strong_duality")

    model.setObjective(fixed_cost + operate_cost + static_carbon, GRB.MINIMIZE)
    model.update()

    if verbose:
        print("=" * 72)
        print("  秋葵冷库布局 - 双层KKT单层转化模型")
        print("=" * 72)
        print(f"  candidates={len(candidate_ids)} | demands={len(demand_ids)}")
        print(f"  vars={model.NumVars} | constrs={model.NumConstrs}")

    start = time.time()
    model.optimize()
    elapsed = time.time() - start

    if verbose:
        print(f"\n  elapsed={elapsed:.2f}s | status={model.Status}")
        if model.SolCount > 0:
            print(f"  obj={model.ObjVal:,.0f} | gap={model.MIPGap*100:.2f}%")

    analysis = analyze_bilevel_kkt(model, z, x, data, carbon_price=carbon_price, loss_price=loss_price, elapsed=elapsed)
    return model, z, x, analysis


def analyze_bilevel_kkt(
    model: gp.Model,
    z: Dict[tuple, gp.Var],
    x: Dict[tuple, gp.Var],
    data: Any,
    *,
    carbon_price: float,
    loss_price: float,
    elapsed: float,
) -> Dict[str, Any]:
    """解析双层 KKT 模型结果。"""
    demand_ids = data.demand_ids
    candidate_ids = data.candidate_ids
    storage_types = data.storage_types
    demand = data.demand

    opened = []
    for j in candidate_ids:
        for t in storage_types:
            for c in range(len(data.config.capacity_index[t])):
                if z[j, t, c].X > 0.5:
                    total_demand = sum(x[i, j, t].X * demand[i] for i in demand_ids)
                    opened.append(
                        {
                            "site": j,
                            "type": t,
                            "type_name": data.config.get_storage_params(t)["name"],
                            "capacity": get_capacity(data, t, c),
                            "capacity_idx": c,
                            "fixed_cost": get_fixed_cost(data, t, c),
                            "operate_cost": get_operate_cost(data, t, c),
                            "assigned_demand": total_demand,
                            "utilization": 100.0 * total_demand / get_capacity(data, t, c),
                        }
                    )

    fixed_total = sum(
        z[j, t, c].X * get_fixed_cost(data, t, c) * 10000
        for j in candidate_ids for t in storage_types for c in range(len(data.config.capacity_index[t]))
    )
    operate_total = sum(
        z[j, t, c].X * get_operate_cost(data, t, c) * 10000
        for j in candidate_ids for t in storage_types for c in range(len(data.config.capacity_index[t]))
    )
    static_carbon = sum(
        z[j, t, c].X * get_capacity(data, t, c)
        * data.config.get_storage_params(t)["energy_cost_per_ton"]
        * data.config.get_storage_params(t)["carbon_factor"] / 1000.0
        * carbon_price
        for j in candidate_ids for t in storage_types for c in range(len(data.config.capacity_index[t]))
    )
    lower_total = sum(
        x[i, j, t].X * demand[i] * get_lower_level_unit_cost(data, i, j, t, carbon_price, loss_price)
        for i in demand_ids for j in candidate_ids for t in storage_types
    )

    # 仅用于论文展示的拆分项
    transport_total = sum(
        x[i, j, t].X * demand[i] * data.config.get_dist(i, j) * data.transport_unit_cost
        for i in demand_ids for j in candidate_ids for t in storage_types
    )
    loss_total = sum(
        x[i, j, t].X * demand[i] * (
            data.config.get_time(i, j) * data.config.get_preservation_params()["transport_loss_per_hour"]
            + data.storage_loss_rate[t]
        ) * loss_price
        for i in demand_ids for j in candidate_ids for t in storage_types
    )
    dynamic_carbon = sum(
        x[i, j, t].X * demand[i] * get_carbon_ton_per_ton(data, i, j, t) * carbon_price
        for i in demand_ids for j in candidate_ids for t in storage_types
    )

    return {
        "elapsed": elapsed,
        "status": int(model.Status),
        "total_cost": float(fixed_total + operate_total + static_carbon + lower_total),
        "upper_cost": float(fixed_total + operate_total + static_carbon),
        "fixed_cost": float(fixed_total),
        "operate_cost": float(operate_total),
        "transport_cost": float(transport_total),
        "loss_cost": float(loss_total),
        "carbon_cost": float(static_carbon + dynamic_carbon),
        "static_carbon": float(static_carbon),
        "dynamic_carbon": float(dynamic_carbon),
        "lower_level_cost": float(lower_total),
        "num_facilities": len(opened),
        "facilities": opened,
        "precool_violations": sum(
            1
            for i in demand_ids
            for j in candidate_ids
            if x[i, j, "precool"].X > 0.5 and data.config.get_time(i, j) > data.config.get_preservation_params()["precool_time_limit_h"]
        ),
    }
