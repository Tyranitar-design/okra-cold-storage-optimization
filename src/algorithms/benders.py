"""
经典 Benders 分解原型。

说明：
- 主问题决定设施开放与容量等级
- 子问题在给定设施后做分配
- 通过子问题对偶信息生成 Benders cut
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import gurobipy as gp
from gurobipy import GRB

from src.models.layout_problem import build_layout_data, get_capacity, get_fixed_cost, get_operate_cost


@dataclass
class BendersIterationRecord:
    iteration: int
    master_obj: float
    subproblem_obj: float
    upper_bound: float
    lower_bound: float
    gap_pct: float
    cut_count: int


def solve_master_problem(
    data: Any,
    cut_pool: List[Dict[str, Any]],
    *,
    max_facilities: int,
    time_limit: int,
    mip_gap: float,
    threads: int,
    verbose: bool,
) -> Tuple[gp.Model, Dict[tuple, gp.Var]]:
    """求解主问题。"""
    model = gp.Model("Benders_Master")
    model.setParam("TimeLimit", time_limit)
    model.setParam("MIPGap", mip_gap)
    model.setParam("Threads", threads)
    model.setParam("OutputFlag", 1 if verbose else 0)

    z: Dict[tuple, gp.Var] = {}
    for j in data.candidate_ids:
        for t in data.storage_types:
            for c in range(len(data.config.capacity_index[t])):
                z[j, t, c] = model.addVar(vtype=GRB.BINARY, name=f"z_{j}_{t}_{c}")

    theta = model.addVar(lb=0.0, vtype=GRB.CONTINUOUS, name="theta")

    for j in data.candidate_ids:
        model.addConstr(
            gp.quicksum(z[j, t, c] for t in data.storage_types for c in range(len(data.config.capacity_index[t]))) <= 1,
            name=f"one_facility_{j}",
        )

    model.addConstr(
        gp.quicksum(z[j, t, c] for j in data.candidate_ids for t in data.storage_types for c in range(len(data.config.capacity_index[t])))
        <= max_facilities,
        name="max_facilities",
    )

    model.addConstr(
        gp.quicksum(
            z[j, t, c] * get_capacity(data, t, c)
            for j in data.candidate_ids for t in data.storage_types for c in range(len(data.config.capacity_index[t]))
        )
        >= sum(data.demand.values()),
        name="cover_total_demand",
    )

    fixed_cost = gp.quicksum(
        z[j, t, c] * get_fixed_cost(data, t, c) * 10000
        for j in data.candidate_ids for t in data.storage_types for c in range(len(data.config.capacity_index[t]))
    )
    operate_cost = gp.quicksum(
        z[j, t, c] * get_operate_cost(data, t, c) * 10000
        for j in data.candidate_ids for t in data.storage_types for c in range(len(data.config.capacity_index[t]))
    )

    for cut_id, cut in enumerate(cut_pool):
        cut_expr = gp.quicksum(
            cut["coef"].get((j, t, c), 0.0) * z[j, t, c]
            for j in data.candidate_ids for t in data.storage_types for c in range(len(data.config.capacity_index[t]))
        )
        model.addConstr(theta >= cut_expr + cut["rhs"], name=f"benders_cut_{cut_id}")

    model.setObjective(fixed_cost + operate_cost + theta, GRB.MINIMIZE)
    model.update()
    model.optimize()
    return model, z


def solve_subproblem(
    data: Any,
    z_solution: Dict[tuple, float],
    *,
    carbon_price: float,
    loss_price: float,
    verbose: bool,
) -> Tuple[gp.Model, Dict[tuple, gp.Var], Dict[str, Any]]:
    """给定主问题解，求解分配子问题，并返回对偶信息。"""
    model = gp.Model("Benders_Subproblem")
    model.setParam("OutputFlag", 1 if verbose else 0)

    x: Dict[tuple, gp.Var] = {}
    assign_cons: Dict[str, gp.Constr] = {}
    open_cons: Dict[tuple, gp.Constr] = {}
    capacity_cons: Dict[tuple, gp.Constr] = {}

    for i in data.demand_ids:
        for j in data.candidate_ids:
            for t in data.storage_types:
                x[i, j, t] = model.addVar(vtype=GRB.CONTINUOUS, lb=0.0, ub=1.0, name=f"x_{i}_{j}_{t}")

    pp = data.config.get_preservation_params()
    demand = data.demand
    storage_loss_rate = data.storage_loss_rate

    for i in data.demand_ids:
        assign_cons[i] = model.addConstr(
            gp.quicksum(x[i, j, t] for j in data.candidate_ids for t in data.storage_types) == 1,
            name=f"assign_once_{i}",
        )

    for i in data.demand_ids:
        for j in data.candidate_ids:
            for t in data.storage_types:
                open_flag = sum(z_solution.get((j, t, c), 0.0) for c in range(len(data.config.capacity_index[t])))
                open_cons[i, j, t] = model.addConstr(
                    x[i, j, t] <= open_flag,
                    name=f"assign_open_{i}_{j}_{t}",
                )

    for i in data.demand_ids:
        for j in data.candidate_ids:
            model.addConstr(
                data.config.get_time(i, j) * x[i, j, "precool"]
                <= pp["precool_time_limit_h"] * x[i, j, "precool"] + 20.0 * (1.0 - x[i, j, "precool"]),
                name=f"precool_{i}_{j}",
            )

    for j in data.candidate_ids:
        for t in data.storage_types:
            open_capacity = sum(
                z_solution.get((j, t, c), 0.0) * get_capacity(data, t, c)
                for c in range(len(data.config.capacity_index[t]))
            )
            capacity_cons[j, t] = model.addConstr(
                gp.quicksum(x[i, j, t] * demand[i] for i in data.demand_ids) <= open_capacity,
                name=f"capacity_{j}_{t}",
            )

    transport_cost = gp.quicksum(
        x[i, j, t] * demand[i] * data.config.get_dist(i, j) * data.transport_unit_cost
        for i in data.demand_ids for j in data.candidate_ids for t in data.storage_types
    )
    loss_cost = gp.quicksum(
        x[i, j, t] * demand[i] * (data.config.get_time(i, j) * pp["transport_loss_per_hour"] + storage_loss_rate[t]) * loss_price
        for i in data.demand_ids for j in data.candidate_ids for t in data.storage_types
    )
    carbon_cost = gp.quicksum(
        x[i, j, t] * demand[i] * (
            data.config.get_storage_params(t)["energy_cost_per_ton"] * data.config.get_storage_params(t)["carbon_factor"] / 1000.0
            + data.config.get_dist(i, j) * data.transport_carbon_factor / 1000.0
        ) * carbon_price
        for i in data.demand_ids for j in data.candidate_ids for t in data.storage_types
    )
    model.setObjective(transport_cost + loss_cost + carbon_cost, GRB.MINIMIZE)
    model.update()
    model.optimize()

    duals: Dict[str, Any] = {}
    if model.Status == GRB.OPTIMAL:
        duals["alpha"] = {i: float(assign_cons[i].Pi) for i in data.demand_ids}
        duals["beta"] = {
            (i, j, t): float(open_cons[i, j, t].Pi)
            for i in data.demand_ids for j in data.candidate_ids for t in data.storage_types
        }
        duals["gamma"] = {
            (j, t): float(capacity_cons[j, t].Pi)
            for j in data.candidate_ids for t in data.storage_types
        }

    return model, x, {
        "transport_cost": float(transport_cost.getValue()) if model.SolCount > 0 else None,
        "loss_cost": float(loss_cost.getValue()) if model.SolCount > 0 else None,
        "carbon_cost": float(carbon_cost.getValue()) if model.SolCount > 0 else None,
        "total_cost": float(model.ObjVal) if model.SolCount > 0 else None,
        "duals": duals,
    }


def build_cut_from_subproblem(data: Any, duals: Dict[str, Any]) -> Dict[str, Any]:
    """从子问题对偶信息构建 cut。"""
    coef: Dict[tuple, float] = {}
    alpha = duals.get("alpha", {})
    beta = duals.get("beta", {})
    gamma = duals.get("gamma", {})

    rhs = sum(float(alpha.get(i, 0.0)) for i in data.demand_ids)
    for j in data.candidate_ids:
        for t in data.storage_types:
            beta_sum = sum(float(beta.get((i, j, t), 0.0)) for i in data.demand_ids)
            for c in range(len(data.config.capacity_index[t])):
                coef[(j, t, c)] = beta_sum + float(gamma.get((j, t), 0.0)) * get_capacity(data, t, c)
    return {"coef": coef, "rhs": rhs}


def run_benders(
    config: Any,
    *,
    carbon_price: float = 50.0,
    loss_price: float = 3000.0,
    max_facilities: int = 8,
    candidate_ids: Optional[List[str]] = None,
    demand_ids: Optional[List[str]] = None,
    time_limit: int = 300,
    mip_gap: float = 0.01,
    threads: int = 8,
    max_iterations: int = 10,
    verbose: bool = True,
) -> Dict[str, Any]:
    """运行经典 Benders 分解。"""
    data = build_layout_data(config, candidate_ids=candidate_ids, demand_ids=demand_ids)
    cut_pool: List[Dict[str, Any]] = []
    iterations: List[BendersIterationRecord] = []
    upper_bound = float("inf")
    lower_bound = -float("inf")
    best_solution: Dict[tuple, float] = {}
    best_subproblem: Dict[str, Any] = {}

    start = time.time()
    for it in range(1, max_iterations + 1):
        master, z_vars = solve_master_problem(
            data,
            cut_pool,
            max_facilities=max_facilities,
            time_limit=time_limit,
            mip_gap=mip_gap,
            threads=threads,
            verbose=verbose,
        )
        if master.SolCount <= 0:
            break

        z_solution = {
            (j, t, c): float(z_vars[j, t, c].X)
            for j in data.candidate_ids for t in data.storage_types for c in range(len(data.config.capacity_index[t]))
        }
        lower_bound = max(lower_bound, float(master.ObjVal))

        subproblem, _, sub_summary = solve_subproblem(
            data,
            z_solution,
            carbon_price=carbon_price,
            loss_price=loss_price,
            verbose=verbose,
        )

        if subproblem.SolCount <= 0:
            # 总容量不足时，补一个覆盖约束 cut
            cut_pool.append(
                {
                    "coef": {
                        (j, t, c): get_capacity(data, t, c)
                        for j in data.candidate_ids for t in data.storage_types for c in range(len(data.config.capacity_index[t]))
                    },
                    "rhs": sum(data.demand.values()),
                }
            )
            continue

        total_obj = float(master.ObjVal + subproblem.ObjVal)
        if total_obj < upper_bound:
            upper_bound = total_obj
            best_solution = z_solution
            best_subproblem = sub_summary

        cut_pool.append(build_cut_from_subproblem(data, sub_summary.get("duals", {})))

        gap_pct = 0.0 if upper_bound == 0 else max(0.0, (upper_bound - lower_bound) / max(abs(upper_bound), 1.0) * 100.0)
        iterations.append(
            BendersIterationRecord(
                iteration=it,
                master_obj=float(master.ObjVal),
                subproblem_obj=float(subproblem.ObjVal),
                upper_bound=float(upper_bound),
                lower_bound=float(lower_bound),
                gap_pct=float(gap_pct),
                cut_count=len(cut_pool),
            )
        )
        if gap_pct <= mip_gap * 100.0:
            break

    elapsed = time.time() - start
    return {
        "elapsed": elapsed,
        "iterations": [record.__dict__ for record in iterations],
        "cut_history": cut_pool,
        "cut_count": len(cut_pool),
        "upper_bound": None if upper_bound == float("inf") else float(upper_bound),
        "lower_bound": None if lower_bound == -float("inf") else float(lower_bound),
        "best_solution": best_solution,
        "best_subproblem": best_subproblem,
        "final_gap_pct": None if not iterations else iterations[-1].gap_pct,
    }
