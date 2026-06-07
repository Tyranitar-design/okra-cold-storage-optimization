"""
秋葵冷库布局多目标 ε-约束法。
"""

from __future__ import annotations

import itertools
import os
import time
from typing import Any, Dict, Iterable, List, Optional, Tuple

import gurobipy as gp
from gurobipy import GRB

from src.models.layout_problem import build_layout_data, get_capacity, get_fixed_cost, get_operate_cost


def build_epsilon_model(
    config: Any,
    *,
    carbon_price: float = 50.0,
    loss_price: float = 3000.0,
    max_facilities: int = 8,
    candidate_ids: Optional[List[str]] = None,
    demand_ids: Optional[List[str]] = None,
    eps_loss_ton: Optional[float] = None,
    eps_carbon_ton: Optional[float] = None,
    objective_name: str = "cost",
    time_limit: int = 300,
    mip_gap: float = 0.01,
    threads: int = 8,
    verbose: bool = False,
) -> Tuple[gp.Model, Dict[tuple, gp.Var], Dict[tuple, gp.Var], Dict[str, Any]]:
    """构建 ε-约束模型。"""
    data = build_layout_data(config, candidate_ids=candidate_ids, demand_ids=demand_ids)
    candidate_ids = data.candidate_ids
    demand_ids = data.demand_ids
    storage_types = data.storage_types

    model = gp.Model("OkraColdStorage_Epsilon")
    model.setParam("TimeLimit", time_limit)
    model.setParam("MIPGap", mip_gap)
    model.setParam("Threads", threads)
    model.setParam("OutputFlag", 1 if verbose else 0)

    z: Dict[tuple, gp.Var] = {}
    x: Dict[tuple, gp.Var] = {}

    for j in candidate_ids:
        for t in storage_types:
            for c in range(len(config.capacity_index[t])):
                z[j, t, c] = model.addVar(vtype=GRB.BINARY, name=f"z_{j}_{t}_{c}")

    for i in demand_ids:
        for j in candidate_ids:
            for t in storage_types:
                x[i, j, t] = model.addVar(vtype=GRB.BINARY, name=f"x_{i}_{j}_{t}")

    model.update()

    pp = config.get_preservation_params()
    storage_loss_rate = data.storage_loss_rate
    demand = data.demand

    # 基础约束
    for i in demand_ids:
        model.addConstr(gp.quicksum(x[i, j, t] for j in candidate_ids for t in storage_types) == 1)

    for i in demand_ids:
        for j in candidate_ids:
            for t in storage_types:
                model.addConstr(x[i, j, t] <= gp.quicksum(z[j, t, c] for c in range(len(config.capacity_index[t]))))

    for j in candidate_ids:
        model.addConstr(gp.quicksum(z[j, t, c] for t in storage_types for c in range(len(config.capacity_index[t]))) <= 1)

    model.addConstr(
        gp.quicksum(z[j, t, c] for j in candidate_ids for t in storage_types for c in range(len(config.capacity_index[t])))
        <= max_facilities
    )

    big_m = 20.0
    for i in demand_ids:
        for j in candidate_ids:
            model.addConstr(
                config.get_time(i, j) * x[i, j, "precool"]
                <= pp["precool_time_limit_h"] * x[i, j, "precool"] + big_m * (1 - x[i, j, "precool"])
            )

    for j in candidate_ids:
        for t in storage_types:
            model.addConstr(
                gp.quicksum(x[i, j, t] * demand[i] for i in demand_ids)
                <= gp.quicksum(z[j, t, c] * get_capacity(data, t, c) for c in range(len(config.capacity_index[t])))
            )

    fixed_cost = gp.quicksum(
        z[j, t, c] * get_fixed_cost(data, t, c) * 10000
        for j in candidate_ids for t in storage_types for c in range(len(config.capacity_index[t]))
    )
    operate_cost = gp.quicksum(
        z[j, t, c] * get_operate_cost(data, t, c) * 10000
        for j in candidate_ids for t in storage_types for c in range(len(config.capacity_index[t]))
    )
    transport_cost = gp.quicksum(
        x[i, j, t] * demand[i] * config.get_dist(i, j) * data.transport_unit_cost
        for i in demand_ids for j in candidate_ids for t in storage_types
    )
    loss_ton_expr = gp.quicksum(
        x[i, j, t] * demand[i] * (config.get_time(i, j) * pp["transport_loss_per_hour"] + storage_loss_rate[t])
        for i in demand_ids for j in candidate_ids for t in storage_types
    )
    carbon_ton_expr = gp.quicksum(
        x[i, j, t] * demand[i] * (
            config.get_storage_params(t)["energy_cost_per_ton"] * config.get_storage_params(t)["carbon_factor"] / 1000.0
            + config.get_dist(i, j) * data.transport_carbon_factor / 1000.0
        )
        for i in demand_ids for j in candidate_ids for t in storage_types
    )

    if objective_name == "cost":
        model.setObjective(fixed_cost + operate_cost + transport_cost + loss_ton_expr * loss_price + carbon_ton_expr * carbon_price, GRB.MINIMIZE)
        primary_expr = fixed_cost + operate_cost + transport_cost + loss_ton_expr * loss_price + carbon_ton_expr * carbon_price
    elif objective_name == "loss":
        model.setObjective(loss_ton_expr, GRB.MINIMIZE)
        primary_expr = loss_ton_expr
    elif objective_name == "carbon":
        model.setObjective(carbon_ton_expr, GRB.MINIMIZE)
        primary_expr = carbon_ton_expr
    else:
        raise ValueError(f"Unsupported objective_name: {objective_name}")

    if eps_loss_ton is not None:
        model.addConstr(loss_ton_expr <= eps_loss_ton, name="eps_loss")
    if eps_carbon_ton is not None:
        model.addConstr(carbon_ton_expr <= eps_carbon_ton, name="eps_carbon")

    model.update()

    start = time.time()
    model.optimize()
    elapsed = time.time() - start

    analysis = analyze_epsilon_solution(
        model,
        z,
        x,
        data,
        carbon_price=carbon_price,
        loss_price=loss_price,
        elapsed=elapsed,
    )
    analysis["primary_objective_name"] = objective_name
    analysis["eps_loss_ton"] = eps_loss_ton
    analysis["eps_carbon_ton"] = eps_carbon_ton
    analysis["primary_objective_value"] = float(primary_expr.getValue()) if model.SolCount > 0 else None
    return model, z, x, analysis


def analyze_epsilon_solution(
    model: gp.Model,
    z: Dict[tuple, gp.Var],
    x: Dict[tuple, gp.Var],
    data: Any,
    *,
    carbon_price: float,
    loss_price: float,
    elapsed: float,
) -> Dict[str, Any]:
    """分析 ε-约束模型结果。"""
    candidate_ids = data.candidate_ids
    demand_ids = data.demand_ids
    storage_types = data.storage_types
    demand = data.demand

    fixed_total = sum(
        z[j, t, c].X * get_fixed_cost(data, t, c) * 10000
        for j in candidate_ids for t in storage_types for c in range(len(data.config.capacity_index[t]))
    )
    operate_total = sum(
        z[j, t, c].X * get_operate_cost(data, t, c) * 10000
        for j in candidate_ids for t in storage_types for c in range(len(data.config.capacity_index[t]))
    )
    transport_total = sum(
        x[i, j, t].X * demand[i] * data.config.get_dist(i, j) * data.transport_unit_cost
        for i in demand_ids for j in candidate_ids for t in storage_types
    )
    loss_total = sum(
        x[i, j, t].X * demand[i] * (data.config.get_time(i, j) * data.config.get_preservation_params()["transport_loss_per_hour"] + data.storage_loss_rate[t]) * loss_price
        for i in demand_ids for j in candidate_ids for t in storage_types
    )
    carbon_total = sum(
        x[i, j, t].X * demand[i] * (
            data.config.get_storage_params(t)["energy_cost_per_ton"] * data.config.get_storage_params(t)["carbon_factor"] / 1000.0
            + data.config.get_dist(i, j) * data.transport_carbon_factor / 1000.0
        ) * carbon_price
        for i in demand_ids for j in candidate_ids for t in storage_types
    )
    loss_ton = sum(
        x[i, j, t].X * demand[i] * (data.config.get_time(i, j) * data.config.get_preservation_params()["transport_loss_per_hour"] + data.storage_loss_rate[t])
        for i in demand_ids for j in candidate_ids for t in storage_types
    )
    carbon_ton = sum(
        x[i, j, t].X * demand[i] * (
            data.config.get_storage_params(t)["energy_cost_per_ton"] * data.config.get_storage_params(t)["carbon_factor"] / 1000.0
            + data.config.get_dist(i, j) * data.transport_carbon_factor / 1000.0
        )
        for i in demand_ids for j in candidate_ids for t in storage_types
    )

    facilities = []
    for j in candidate_ids:
        for t in storage_types:
            for c in range(len(data.config.capacity_index[t])):
                if z[j, t, c].X > 0.5:
                    total_demand = sum(x[i, j, t].X * demand[i] for i in demand_ids)
                    facilities.append(
                        {
                            "site": j,
                            "type": t,
                            "type_name": data.config.get_storage_params(t)["name"],
                            "capacity": get_capacity(data, t, c),
                            "capacity_idx": c,
                            "assigned_demand": total_demand,
                            "utilization": 100.0 * total_demand / get_capacity(data, t, c),
                        }
                    )

    return {
        "elapsed": elapsed,
        "status": int(model.Status),
        "total_cost": float(model.ObjVal) if model.SolCount > 0 else None,
        "fixed_cost": float(fixed_total),
        "operate_cost": float(operate_total),
        "transport_cost": float(transport_total),
        "loss_cost": float(loss_total),
        "carbon_cost": float(carbon_total),
        "loss_ton": float(loss_ton),
        "carbon_ton": float(carbon_ton),
        "num_facilities": len(facilities),
        "facilities": facilities,
        "precool_violations": sum(
            1
            for i in demand_ids
            for j in candidate_ids
            if x[i, j, "precool"].X > 0.5 and data.config.get_time(i, j) > data.config.get_preservation_params()["precool_time_limit_h"]
        ),
    }
