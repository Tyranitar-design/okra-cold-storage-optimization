"""Public LRP benchmark Benders comparison.

This experiment compares three layers on a small set of public benchmark
instances projected into the same capacitated facility-location model:

1. direct solve;
2. classic Benders decomposition;
3. explainable AI cut-ranking evidence built on the Benders cut history;
4. AI-active Benders that uses the learned cut ranking to limit active cuts
   in the master problem.

It is still a projection benchmark, not a full routing LRP proof and not
okra enterprise validation.
"""

from __future__ import annotations

import json
import os
import pickle
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import torch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("GRB_LICENSE_FILE", r"D:\Gurobi1300\win64\bin\gurobi.lic")

from experiments._shared import gurobi_status_name, save_dataframe_bundle, write_markdown_table  # noqa: E402
from experiments.benchmark_solver_smoke import SmokeInstance, parse_smoke_instance, select_entries  # noqa: E402
from src.api.benchmark_manifest import load_normalized_manifest  # noqa: E402
from src.algorithms.benders_ai import (  # noqa: E402
    AI_BENDERS_RESEARCH_BOUNDARY,
    CUT_SCORE_FORMULA,
    _build_cut_score_records,
)
from src.algorithms.cut_features import build_cut_dataset  # noqa: E402
from src.algorithms.gnn_encoder import encode_bipartite_graph  # noqa: E402
from src.algorithms.rl_agent import train_agent_from_history  # noqa: E402

try:
    import gurobipy as gp  # noqa: E402
    from gurobipy import GRB  # noqa: E402

    GUROBI_IMPORT_ERROR = ""
except Exception as exc:  # pragma: no cover - exercised only when env is incomplete
    gp = None
    GRB = None
    GUROBI_IMPORT_ERROR = str(exc)


OUT_DIR = PROJECT_ROOT / "results" / "experiments" / "benchmark_benders_comparison"
SOURCE_ID = "DS-F-015"
TRANSPORT_UNIT_COST = 1.2


@dataclass(frozen=True)
class BenchmarkGraphBundle:
    nodes: pd.DataFrame
    edges: pd.DataFrame
    demand_nodes: pd.DataFrame
    facility_nodes: pd.DataFrame


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, tuple):
        return [_json_safe(v) for v in value]
    if hasattr(value, "tolist"):
        try:
            return _json_safe(value.tolist())
        except Exception:
            pass
    if hasattr(value, "item"):
        try:
            return _json_safe(value.item())
        except Exception:
            pass
    return value


def _euclidean(a: dict[str, float], b: dict[str, float]) -> float:
    return float(((float(a["x"]) - float(b["x"])) ** 2 + (float(a["y"]) - float(b["y"])) ** 2) ** 0.5)


def build_graph_bundle(instance: SmokeInstance) -> BenchmarkGraphBundle:
    demand_rows = []
    facility_rows = []
    for idx, customer in enumerate(instance.customers):
        node_id = f"demand::{customer['node_id']}"
        demand_rows.append(
            {
                "node_id": node_id,
                "name": f"customer_{customer['node_id']}",
                "level": 1,
                "level_name": "demand",
                "lat": float(customer["y"]),
                "lon": float(customer["x"]),
                "okra_production_ton": float(customer["demand"]),
                "is_candidate": 0,
                "population": float(customer["demand"]) * 10.0,
                "road_access": 1,
                "node_type": "demand",
                "node_key": node_id,
            }
        )

    for idx, facility in enumerate(instance.facilities):
        node_id = f"facility::{facility['node_id']}"
        facility_rows.append(
            {
                "node_id": node_id,
                "name": f"facility_{facility['node_id']}",
                "level": 2,
                "level_name": "facility",
                "lat": float(facility["y"]),
                "lon": float(facility["x"]),
                "okra_production_ton": 0.0,
                "is_candidate": 1,
                "population": 0.0,
                "road_access": 1,
                "node_type": "facility",
                "node_key": node_id,
            }
        )

    nodes = pd.DataFrame([*demand_rows, *facility_rows])
    edge_rows: list[dict[str, Any]] = []
    for i, customer in enumerate(instance.customers):
        for j, facility in enumerate(instance.facilities):
            demand_id = f"demand::{customer['node_id']}"
            facility_id = f"facility::{facility['node_id']}"
            dist = _euclidean(customer, facility)
            edge_rows.append(
                {
                    "demand_id": demand_id,
                    "demand_key": demand_id,
                    "facility_id": facility_id,
                    "facility_key": facility_id,
                    "distance_km": dist,
                    "travel_time_h": dist / 40.0,
                    "demand_ton": float(customer["demand"]),
                    "is_self": 1.0 if customer["node_id"] == facility["node_id"] else 0.0,
                }
            )
    edges = pd.DataFrame(edge_rows)
    return BenchmarkGraphBundle(
        nodes=nodes,
        edges=edges,
        demand_nodes=pd.DataFrame(demand_rows),
        facility_nodes=pd.DataFrame(facility_rows),
    )


def solve_direct_projection(instance: SmokeInstance, time_limit: int, mip_gap: float) -> dict[str, Any]:
    if gp is None or GRB is None:
        return {
            "status_name": "GUROBI_IMPORT_FAILED",
            "status_code": None,
            "objective": None,
            "best_bound": None,
            "mip_gap_pct": None,
            "open_facilities": None,
            "open_facility_ids": [],
            "fixed_cost_yuan": None,
            "transport_cost_yuan": None,
            "total_cost_yuan": None,
            "demand_total_ton": sum(customer["demand"] for customer in instance.customers),
            "cost_per_ton": None,
            "elapsed_sec": None,
            "solver_model": "capacitated_facility_location_projection",
            "error": GUROBI_IMPORT_ERROR,
        }

    start = time.time()
    model = gp.Model(f"benchmark_direct_{instance.instance_name}")
    model.setParam("OutputFlag", 0)
    model.setParam("TimeLimit", time_limit)
    model.setParam("MIPGap", mip_gap)

    y = {
        j: model.addVar(vtype=GRB.BINARY, name=f"open_{j}")
        for j in range(instance.facility_count)
    }
    x = {
        (i, j): model.addVar(vtype=GRB.CONTINUOUS, lb=0.0, ub=1.0, name=f"assign_{i}_{j}")
        for i in range(instance.customer_count)
        for j in range(instance.facility_count)
    }

    demand_total = sum(customer["demand"] for customer in instance.customers)
    for i in range(instance.customer_count):
        model.addConstr(
            gp.quicksum(x[i, j] for j in range(instance.facility_count)) == 1.0,
            name=f"assign_once_{i}",
        )
    for i in range(instance.customer_count):
        for j in range(instance.facility_count):
            model.addConstr(x[i, j] <= y[j], name=f"assign_open_{i}_{j}")
    for j, facility in enumerate(instance.facilities):
        model.addConstr(
            gp.quicksum(x[i, j] * instance.customers[i]["demand"] for i in range(instance.customer_count))
            <= float(facility["capacity"]) * y[j],
            name=f"capacity_{j}",
        )
    model.addConstr(
        gp.quicksum(float(facility["capacity"]) * y[j] for j, facility in enumerate(instance.facilities)) >= demand_total,
        name="cover_total_demand",
    )

    fixed_cost = gp.quicksum(
        y[j] * max(0.0, float(instance.facilities[j].get("fixed_cost", 0.0)))
        for j in range(instance.facility_count)
    )
    transport_cost = gp.quicksum(
        x[i, j] * instance.customers[i]["demand"] * _euclidean(instance.customers[i], instance.facilities[j]) * TRANSPORT_UNIT_COST
        for i in range(instance.customer_count)
        for j in range(instance.facility_count)
    )
    model.setObjective(fixed_cost + transport_cost, GRB.MINIMIZE)
    model.optimize()
    elapsed = time.time() - start

    sol_count = int(getattr(model, "SolCount", 0))
    open_ids: list[str] = []
    if sol_count > 0:
        for j, facility in enumerate(instance.facilities):
            if y[j].X > 0.5:
                open_ids.append(str(facility["node_id"]))

    objective = float(model.ObjVal) if sol_count > 0 else None
    fixed_cost_val = float(fixed_cost.getValue()) if sol_count > 0 else None
    transport_cost_val = float(transport_cost.getValue()) if sol_count > 0 else None
    demand_total_ton = float(demand_total)
    return {
        "status_name": gurobi_status_name(int(model.Status)),
        "status_code": int(model.Status),
        "objective": objective,
        "best_bound": float(model.ObjBound) if sol_count > 0 else None,
        "mip_gap_pct": float(model.MIPGap * 100.0) if sol_count > 0 else None,
        "open_facilities": len(open_ids),
        "open_facility_ids": open_ids,
        "fixed_cost_yuan": fixed_cost_val,
        "transport_cost_yuan": transport_cost_val,
        "total_cost_yuan": objective,
        "demand_total_ton": demand_total_ton,
        "cost_per_ton": (objective / demand_total_ton) if objective is not None and demand_total_ton > 0 else None,
        "elapsed_sec": float(elapsed),
        "solver_model": "capacitated_facility_location_projection",
        "error": "",
    }


def solve_master_projection(
    instance: SmokeInstance,
    cut_pool: list[dict[str, Any]],
    *,
    time_limit: int,
    mip_gap: float,
    threads: int,
    verbose: bool,
) -> tuple[Any, dict[int, Any]]:
    model = gp.Model(f"benchmark_benders_master_{instance.instance_name}")
    model.setParam("OutputFlag", 1 if verbose else 0)
    model.setParam("TimeLimit", time_limit)
    model.setParam("MIPGap", mip_gap)
    model.setParam("Threads", threads)

    y = {
        j: model.addVar(vtype=GRB.BINARY, name=f"open_{j}")
        for j in range(instance.facility_count)
    }
    theta = model.addVar(lb=0.0, vtype=GRB.CONTINUOUS, name="theta")

    demand_total = sum(customer["demand"] for customer in instance.customers)
    model.addConstr(
        gp.quicksum(float(facility["capacity"]) * y[idx] for idx, facility in enumerate(instance.facilities)) >= demand_total,
        name="cover_total_demand",
    )

    fixed_cost = gp.quicksum(
        y[j] * max(0.0, float(instance.facilities[j].get("fixed_cost", 0.0)))
        for j in range(instance.facility_count)
    )

    for cut_id, cut in enumerate(cut_pool):
        cut_expr = gp.quicksum(
            float(cut["coef"].get(j, 0.0)) * y[j]
            for j in range(instance.facility_count)
        )
        model.addConstr(theta >= cut_expr + float(cut["rhs"]), name=f"benders_cut_{cut_id}")

    model.setObjective(fixed_cost + theta, GRB.MINIMIZE)
    model.optimize()
    return model, y


def solve_subproblem_projection(
    instance: SmokeInstance,
    y_solution: dict[int, float],
    *,
    verbose: bool,
) -> tuple[Any, dict[tuple[int, int], Any], dict[str, Any]]:
    model = gp.Model(f"benchmark_benders_subproblem_{instance.instance_name}")
    model.setParam("OutputFlag", 1 if verbose else 0)

    x = {
        (i, j): model.addVar(vtype=GRB.CONTINUOUS, lb=0.0, ub=1.0, name=f"assign_{i}_{j}")
        for i in range(instance.customer_count)
        for j in range(instance.facility_count)
    }
    assign_cons: dict[int, Any] = {}
    open_cons: dict[tuple[int, int], Any] = {}
    capacity_cons: dict[int, Any] = {}

    for i in range(instance.customer_count):
        assign_cons[i] = model.addConstr(
            gp.quicksum(x[i, j] for j in range(instance.facility_count)) == 1.0,
            name=f"assign_once_{i}",
        )
    for i in range(instance.customer_count):
        for j in range(instance.facility_count):
            open_flag = float(y_solution.get(j, 0.0))
            open_cons[i, j] = model.addConstr(x[i, j] <= open_flag, name=f"assign_open_{i}_{j}")
    for j, facility in enumerate(instance.facilities):
        capacity_cons[j] = model.addConstr(
            gp.quicksum(x[i, j] * instance.customers[i]["demand"] for i in range(instance.customer_count))
            <= float(facility["capacity"]) * float(y_solution.get(j, 0.0)),
            name=f"capacity_{j}",
        )

    transport_cost = gp.quicksum(
        x[i, j] * instance.customers[i]["demand"] * _euclidean(instance.customers[i], instance.facilities[j]) * TRANSPORT_UNIT_COST
        for i in range(instance.customer_count)
        for j in range(instance.facility_count)
    )
    model.setObjective(transport_cost, GRB.MINIMIZE)
    model.optimize()

    duals: dict[str, Any] = {}
    if model.Status == GRB.OPTIMAL:
        duals["alpha"] = {i: float(assign_cons[i].Pi) for i in range(instance.customer_count)}
        duals["beta"] = {
            (i, j): float(open_cons[i, j].Pi)
            for i in range(instance.customer_count)
            for j in range(instance.facility_count)
        }
        duals["gamma"] = {j: float(capacity_cons[j].Pi) for j in range(instance.facility_count)}

    return model, x, {
        "assignment_cost": float(transport_cost.getValue()) if model.SolCount > 0 else None,
        "total_cost": float(model.ObjVal) if model.SolCount > 0 else None,
        "duals": duals,
    }


def build_cut_from_duals(instance: SmokeInstance, duals: dict[str, Any]) -> dict[str, Any]:
    coef: dict[int, float] = {}
    alpha = duals.get("alpha", {})
    beta = duals.get("beta", {})
    gamma = duals.get("gamma", {})
    rhs = sum(float(alpha.get(i, 0.0)) for i in range(instance.customer_count))
    for j, facility in enumerate(instance.facilities):
        beta_sum = sum(float(beta.get((i, j), 0.0)) for i in range(instance.customer_count))
        coef[j] = beta_sum + float(gamma.get(j, 0.0)) * float(facility["capacity"])
    return {
        "coef": coef,
        "rhs": rhs,
        "cut_type": "optimality",
    }


def solve_classic_benders(
    instance: SmokeInstance,
    *,
    time_limit: int,
    mip_gap: float,
    threads: int,
    max_iterations: int,
    verbose: bool,
) -> dict[str, Any]:
    if gp is None or GRB is None:
        return {
            "status_name": "GUROBI_IMPORT_FAILED",
            "status_code": None,
            "upper_bound": None,
            "lower_bound": None,
            "final_gap_pct": None,
            "cut_count": 0,
            "iterations": [],
            "cut_history": [],
            "elapsed_sec": 0.0,
            "solver_model": "benchmark_benders_projection",
            "error": GUROBI_IMPORT_ERROR,
        }

    start = time.time()
    cut_pool: list[dict[str, Any]] = []
    cut_history: list[dict[str, Any]] = []
    iterations: list[dict[str, Any]] = []
    best_upper = float("inf")
    best_lower = -float("inf")
    best_solution: dict[str, Any] | None = None
    best_subproblem: dict[str, Any] | None = None

    for iter_no in range(1, max_iterations + 1):
        master, y_vars = solve_master_projection(
            instance,
            [item["cut"] for item in cut_pool],
            time_limit=time_limit,
            mip_gap=mip_gap,
            threads=threads,
            verbose=verbose,
        )
        if master.SolCount <= 0:
            break

        y_solution = {j: float(var.X) for j, var in y_vars.items()}
        subproblem, _, sub_summary = solve_subproblem_projection(instance, y_solution, verbose=verbose)
        if subproblem.SolCount <= 0:
            break

        fixed_cost = sum(
            max(0.0, float(instance.facilities[j].get("fixed_cost", 0.0))) * float(y_solution.get(j, 0.0))
            for j in range(instance.facility_count)
        )
        total_cost = fixed_cost + float(sub_summary["assignment_cost"])
        if total_cost < best_upper:
            best_upper = total_cost
            best_solution = {
                "y_solution": y_solution,
                "fixed_cost_yuan": fixed_cost,
                "transport_cost_yuan": float(sub_summary["assignment_cost"]),
                "total_cost_yuan": total_cost,
            }
            best_subproblem = sub_summary

        best_lower = float(master.ObjVal)
        gap_pct = 0.0 if best_upper <= 0 else max(0.0, (best_upper - best_lower) / max(abs(best_upper), 1.0) * 100.0)
        elapsed_now = time.time() - start
        iteration_record = {
            "case_id": instance.instance_name,
            "method": "classic_benders",
            "iteration": iter_no,
            "iter_no": iter_no,
            "master_obj": float(master.ObjVal),
            "subproblem_obj": float(sub_summary["assignment_cost"]),
            "fixed_cost_yuan": fixed_cost,
            "transport_cost_yuan": float(sub_summary["assignment_cost"]),
            "upper_bound": best_upper,
            "lower_bound": best_lower,
            "gap_pct": gap_pct,
            "cut_count": len(cut_pool),
            "elapsed_sec": elapsed_now,
        }
        iterations.append(iteration_record)

        new_cut = build_cut_from_duals(instance, sub_summary["duals"])
        cut_record = {
            "cut_id": f"cut_{len(cut_pool):03d}",
            "iteration": iteration_record,
            "cut": new_cut,
        }
        cut_pool.append(cut_record)
        cut_history.append(cut_record)

        if gap_pct <= mip_gap * 100.0:
            break

    elapsed = time.time() - start
    return {
        "status_name": "OPTIMAL" if best_upper < float("inf") else "FAILED",
        "status_code": 2 if best_upper < float("inf") else None,
        "upper_bound": None if best_upper == float("inf") else float(best_upper),
        "lower_bound": None if best_lower == -float("inf") else float(best_lower),
        "final_gap_pct": None if not iterations else float(iterations[-1]["gap_pct"]),
        "cut_count": len(cut_pool),
        "iterations": iterations,
        "cut_history": cut_history,
        "best_solution": best_solution,
        "best_subproblem": best_subproblem,
        "elapsed_sec": float(elapsed),
        "solver_model": "benchmark_benders_projection",
        "error": "",
    }


def build_ai_evidence(instance: SmokeInstance, cut_history: list[dict[str, Any]], top_k_cuts: int = 3) -> dict[str, Any]:
    if not cut_history:
        return {
            "ai_cut_policy": None,
            "ai_score_formula": CUT_SCORE_FORMULA,
            "ai_training": {},
            "ai_graph_summary": {},
            "ai_feature_importance_top": [],
            "ai_selection_summary": {},
            "ai_cut_scores": [],
            "ai_selected_iterations": [],
            "selected_cut_count": 0,
        }

    graph_bundle = build_graph_bundle(instance)
    graph_embedding = encode_bipartite_graph(graph_bundle, hidden_dim=32)
    cut_features, rewards, _ = build_cut_dataset(cut_history)
    agent, train_result = train_agent_from_history(
        graph_embedding,
        cut_features,
        rewards,
        hidden_dim=64,
        lr=1e-3,
        epochs=120,
    )
    scores = agent.score(graph_embedding, cut_features)
    selected_indices = torch.argsort(scores, descending=True)[: max(1, min(top_k_cuts, len(cut_history)))].tolist()
    policy_name = f"learned_contextual_bandit_top_{top_k_cuts}"
    cut_score_records = _build_cut_score_records(cut_history, scores, selected_indices, policy_name)
    feature_importance = agent.feature_importance().tolist()
    selected_records = [cut_score_records[i] for i in selected_indices if i < len(cut_score_records)]
    ranked_records = sorted(
        cut_score_records,
        key=lambda item: float(item.get("score", float("-inf"))),
        reverse=True,
    )
    graph_summary = {
        "node_count": int(len(graph_bundle.nodes)),
        "edge_count": int(len(graph_bundle.edges)),
        "demand_count": int(len(graph_bundle.demand_nodes)),
        "facility_count": int(len(graph_bundle.facility_nodes)),
        "embedding_dim": int(graph_embedding.shape[-1]),
    }
    return {
        "ai_cut_policy": policy_name,
        "ai_score_formula": CUT_SCORE_FORMULA,
        "ai_training": {
            "final_loss": train_result.final_loss,
            "epochs": train_result.epochs,
            "sample_count": train_result.sample_count,
            "graph_embedding_dim": graph_summary["embedding_dim"],
            "selected_cut_indices": selected_indices,
        },
        "ai_graph_summary": graph_summary,
        "ai_feature_importance_top": [
            {"feature": name, "importance": float(value)}
            for name, value in sorted(
                zip(
                    ["rhs", "coef_count", "coef_abs_mean", "coef_abs_std", "coef_abs_max", "coef_abs_min", "coef_l1", "coef_l2", "coef_pos_ratio", "coef_neg_ratio", "iteration_idx", "master_obj", "subproblem_obj", "gap_pct", "cut_count"],
                    feature_importance,
                ),
                key=lambda item: item[1],
                reverse=True,
            )[:5]
        ],
        "ai_selection_summary": {
            "policy_name": policy_name,
            "selection_mode": "contextual_bandit_top_k",
            "score_formula": CUT_SCORE_FORMULA,
            "selected_cut_indices": selected_indices,
            "selected_cut_ids": [item["cut_id"] for item in selected_records],
            "selected_cut_count": len(selected_records),
            "top_ranked_cuts": ranked_records[: min(3, len(ranked_records))],
            "graph_summary": graph_summary,
            "training": {
                "final_loss": train_result.final_loss,
                "epochs": train_result.epochs,
                "sample_count": train_result.sample_count,
            },
            "feature_importance_top": [
                {"feature": name, "importance": float(value)}
                for name, value in sorted(
                    zip(
                        ["rhs", "coef_count", "coef_abs_mean", "coef_abs_std", "coef_abs_max", "coef_abs_min", "coef_l1", "coef_l2", "coef_pos_ratio", "coef_neg_ratio", "iteration_idx", "master_obj", "subproblem_obj", "gap_pct", "cut_count"],
                        feature_importance,
                    ),
                    key=lambda item: item[1],
                    reverse=True,
                )[:5]
            ],
            "research_boundary": AI_BENDERS_RESEARCH_BOUNDARY,
        },
        "ai_cut_scores": cut_score_records,
        "ai_selected_iterations": [cut_history[i]["iteration"] for i in selected_indices if i < len(cut_history)],
        "selected_cut_count": len(selected_records),
    }


def _cut_signature(cut: dict[str, Any], precision: int = 6) -> tuple[Any, ...]:
    coef_items = tuple(
        sorted((str(key), round(float(value), precision)) for key, value in cut.get("coef", {}).items())
    )
    return (round(float(cut.get("rhs", 0.0)), precision), coef_items)


def solve_ai_active_benders(
    instance: SmokeInstance,
    calibration_cut_history: list[dict[str, Any]],
    *,
    time_limit: int,
    mip_gap: float,
    threads: int,
    max_iterations: int,
    active_cut_budget: int,
    verbose: bool,
) -> dict[str, Any]:
    """Run a second-stage Benders loop where AI ranking controls active cuts."""
    if gp is None or GRB is None:
        return {
            "status_name": "GUROBI_IMPORT_FAILED",
            "status_code": None,
            "upper_bound": None,
            "lower_bound": None,
            "final_gap_pct": None,
            "cut_count": 0,
            "active_cut_budget": active_cut_budget,
            "iterations": [],
            "cut_history": [],
            "active_cut_scores": [],
            "elapsed_sec": 0.0,
            "solver_model": "benchmark_ai_active_benders_projection",
            "error": GUROBI_IMPORT_ERROR,
        }
    if not calibration_cut_history:
        return {
            "status_name": "NO_CALIBRATION_CUTS",
            "status_code": None,
            "upper_bound": None,
            "lower_bound": None,
            "final_gap_pct": None,
            "cut_count": 0,
            "active_cut_budget": active_cut_budget,
            "iterations": [],
            "cut_history": [],
            "active_cut_scores": [],
            "elapsed_sec": 0.0,
            "solver_model": "benchmark_ai_active_benders_projection",
            "error": "classic Benders did not produce cuts for AI-active calibration",
        }

    graph_bundle = build_graph_bundle(instance)
    graph_embedding = encode_bipartite_graph(graph_bundle, hidden_dim=32)
    calibration_features, calibration_rewards, _ = build_cut_dataset(calibration_cut_history)
    agent, train_result = train_agent_from_history(
        graph_embedding,
        calibration_features,
        calibration_rewards,
        hidden_dim=64,
        lr=1e-3,
        epochs=120,
    )

    start = time.time()
    candidate_cut_pool: list[dict[str, Any]] = []
    seen_cut_signatures: set[tuple[Any, ...]] = set()
    iterations: list[dict[str, Any]] = []
    active_cut_scores: list[dict[str, Any]] = []
    best_upper = float("inf")
    best_lower = -float("inf")
    best_solution: dict[str, Any] | None = None
    best_subproblem: dict[str, Any] | None = None
    termination_reason = "max_iterations"
    last_selected_cut_ids: list[str] = []

    policy_name = f"ai_active_contextual_bandit_top_{active_cut_budget}"
    for iter_no in range(1, max_iterations + 1):
        active_records: list[dict[str, Any]] = []
        selected_indices: list[int] = []
        if candidate_cut_pool:
            candidate_features, _, _ = build_cut_dataset(candidate_cut_pool)
            candidate_scores = agent.score(graph_embedding, candidate_features)
            selected_indices = torch.argsort(candidate_scores, descending=True)[
                : max(1, min(active_cut_budget, len(candidate_cut_pool)))
            ].tolist()
            active_records = [candidate_cut_pool[idx] for idx in selected_indices]
            score_records = _build_cut_score_records(candidate_cut_pool, candidate_scores, selected_indices, policy_name)
            for record in score_records:
                record["selection_iter_no"] = iter_no
                record["active_cut_budget"] = active_cut_budget
                record["candidate_cut_count"] = len(candidate_cut_pool)
                record["active_cut_count"] = len(active_records)
            active_cut_scores.extend(score_records)
            last_selected_cut_ids = [
                str(candidate_cut_pool[idx].get("cut_id"))
                for idx in selected_indices
                if idx < len(candidate_cut_pool)
            ]

        master, y_vars = solve_master_projection(
            instance,
            [item["cut"] for item in active_records],
            time_limit=time_limit,
            mip_gap=mip_gap,
            threads=threads,
            verbose=verbose,
        )
        if master.SolCount <= 0:
            termination_reason = "master_no_solution"
            break

        y_solution = {j: float(var.X) for j, var in y_vars.items()}
        subproblem, _, sub_summary = solve_subproblem_projection(instance, y_solution, verbose=verbose)
        if subproblem.SolCount <= 0:
            termination_reason = "subproblem_no_solution"
            break

        fixed_cost = sum(
            max(0.0, float(instance.facilities[j].get("fixed_cost", 0.0))) * float(y_solution.get(j, 0.0))
            for j in range(instance.facility_count)
        )
        total_cost = fixed_cost + float(sub_summary["assignment_cost"])
        if total_cost < best_upper:
            best_upper = total_cost
            best_solution = {
                "y_solution": y_solution,
                "fixed_cost_yuan": fixed_cost,
                "transport_cost_yuan": float(sub_summary["assignment_cost"]),
                "total_cost_yuan": total_cost,
            }
            best_subproblem = sub_summary

        best_lower = max(best_lower, float(master.ObjVal))
        gap_pct = 0.0 if best_upper <= 0 else max(0.0, (best_upper - best_lower) / max(abs(best_upper), 1.0) * 100.0)
        elapsed_now = time.time() - start
        iteration_record = {
            "case_id": instance.instance_name,
            "method": "ai_active_benders",
            "iteration": iter_no,
            "iter_no": iter_no,
            "master_obj": float(master.ObjVal),
            "subproblem_obj": float(sub_summary["assignment_cost"]),
            "fixed_cost_yuan": fixed_cost,
            "transport_cost_yuan": float(sub_summary["assignment_cost"]),
            "upper_bound": best_upper,
            "lower_bound": best_lower,
            "gap_pct": gap_pct,
            "cut_count": len(candidate_cut_pool),
            "candidate_cut_count": len(candidate_cut_pool),
            "active_cut_count": len(active_records),
            "active_cut_budget": active_cut_budget,
            "selected_cut_ids": last_selected_cut_ids,
            "elapsed_sec": elapsed_now,
        }
        iterations.append(iteration_record)

        new_cut = build_cut_from_duals(instance, sub_summary["duals"])
        signature = _cut_signature(new_cut)
        if signature in seen_cut_signatures:
            termination_reason = "duplicate_cut"
            break
        seen_cut_signatures.add(signature)
        candidate_cut_pool.append(
            {
                "cut_id": f"active_cut_{len(candidate_cut_pool):03d}",
                "iteration": iteration_record,
                "cut": new_cut,
            }
        )

        if gap_pct <= mip_gap * 100.0:
            termination_reason = "gap_tolerance"
            break

    elapsed = time.time() - start
    unique_selected_cut_ids = sorted(
        {
            str(record.get("cut_id"))
            for record in active_cut_scores
            if bool(record.get("selected")) and record.get("cut_id") is not None
        }
    )
    return {
        "status_name": "OPTIMAL" if best_upper < float("inf") else "FAILED",
        "status_code": 2 if best_upper < float("inf") else None,
        "upper_bound": None if best_upper == float("inf") else float(best_upper),
        "lower_bound": None if best_lower == -float("inf") else float(best_lower),
        "final_gap_pct": None if not iterations else float(iterations[-1]["gap_pct"]),
        "cut_count": len(candidate_cut_pool),
        "active_cut_budget": active_cut_budget,
        "final_active_cut_count": int(iterations[-1]["active_cut_count"]) if iterations else 0,
        "unique_selected_cut_count": len(unique_selected_cut_ids),
        "unique_selected_cut_ids": unique_selected_cut_ids,
        "iterations": iterations,
        "cut_history": candidate_cut_pool,
        "active_cut_scores": active_cut_scores,
        "best_solution": best_solution,
        "best_subproblem": best_subproblem,
        "training": {
            "final_loss": train_result.final_loss,
            "epochs": train_result.epochs,
            "sample_count": train_result.sample_count,
            "calibration_cut_count": len(calibration_cut_history),
            "graph_embedding_dim": int(graph_embedding.shape[-1]),
        },
        "elapsed_sec": float(elapsed),
        "policy_name": policy_name,
        "termination_reason": termination_reason,
        "solver_model": "benchmark_ai_active_benders_projection",
        "error": "",
    }


def _case_ids(config: Any, case: dict[str, Any]) -> tuple[list[str], list[str]]:
    candidates = list(config.candidates["node_id"])[: case["candidate_count"]]
    demands = list(config.demands["node_id"])[: case["demand_count"]]
    return candidates, demands


def _direct_record(case: dict[str, Any], instance: SmokeInstance, direct: dict[str, Any]) -> dict[str, Any]:
    case_id = str(case.get("case_id") or case.get("entry_id") or instance.instance_name)
    candidate_count = int(case.get("candidate_count") or case.get("facility_count") or instance.facility_count)
    demand_count = int(case.get("demand_count") or case.get("customer_count") or instance.customer_count)
    demand_total = float(sum(customer["demand"] for customer in instance.customers))
    return {
        "source_id": SOURCE_ID,
        "case_id": case_id,
        "method": "direct",
        "run_key": f"benchmark_direct_{case_id}",
        "experiment_key": "benchmark_benders_comparison",
        "candidate_count": candidate_count,
        "demand_count": demand_count,
        "status_code": direct.get("status_code"),
        "status_name": direct.get("status_name"),
        "objective": direct.get("objective"),
        "direct_objective": direct.get("objective"),
        "objective_gap_pct": 0.0 if direct.get("objective") not in (None, 0) else None,
        "fixed_cost_yuan": direct.get("fixed_cost_yuan"),
        "transport_cost_yuan": direct.get("transport_cost_yuan"),
        "loss_cost_yuan": 0.0,
        "carbon_cost_yuan": 0.0,
        "total_cost_yuan": direct.get("total_cost_yuan"),
        "lower_bound": direct.get("objective"),
        "upper_bound": direct.get("objective"),
        "final_gap_pct": 0.0,
        "cut_count": 0,
        "iteration_count": 0,
        "open_facilities": direct.get("open_facilities"),
        "selected_cut_count": 0,
        "runtime_sec": direct.get("elapsed_sec"),
        "policy_name": "direct_mip",
        "note": "direct solve baseline on public benchmark projection",
        "demand_total_ton": direct.get("demand_total_ton"),
        "cost_per_ton": direct.get("cost_per_ton"),
        "mip_gap_target": case.get("mip_gap", 0.01),
        "mip_gap_actual": direct.get("mip_gap_pct"),
    }


def _classic_record(
    case: dict[str, Any],
    instance: SmokeInstance,
    classic: dict[str, Any],
    direct_objective: float | None,
) -> dict[str, Any]:
    case_id = str(case.get("case_id") or case.get("entry_id") or instance.instance_name)
    candidate_count = int(case.get("candidate_count") or case.get("facility_count") or instance.facility_count)
    demand_count = int(case.get("demand_count") or case.get("customer_count") or instance.customer_count)
    objective = classic.get("upper_bound")
    objective_gap_pct = None
    if direct_objective not in (None, 0) and objective is not None:
        objective_gap_pct = abs(float(objective) - float(direct_objective)) / abs(float(direct_objective)) * 100.0
    demand_total = float(sum(customer["demand"] for customer in instance.customers))
    return {
        "source_id": SOURCE_ID,
        "case_id": case_id,
        "method": "classic_benders",
        "run_key": f"benchmark_classic_benders_{case_id}",
        "experiment_key": "benchmark_benders_comparison",
        "candidate_count": candidate_count,
        "demand_count": demand_count,
        "status_code": classic.get("status_code"),
        "status_name": classic.get("status_name"),
        "objective": objective,
        "direct_objective": direct_objective,
        "objective_gap_pct": objective_gap_pct,
        "fixed_cost_yuan": classic.get("best_solution", {}).get("fixed_cost_yuan") if classic.get("best_solution") else None,
        "transport_cost_yuan": classic.get("best_solution", {}).get("transport_cost_yuan") if classic.get("best_solution") else None,
        "loss_cost_yuan": 0.0,
        "carbon_cost_yuan": 0.0,
        "total_cost_yuan": objective,
        "lower_bound": classic.get("lower_bound"),
        "upper_bound": classic.get("upper_bound"),
        "final_gap_pct": classic.get("final_gap_pct"),
        "cut_count": classic.get("cut_count"),
        "iteration_count": len(classic.get("iterations", [])),
        "open_facilities": len(classic.get("best_solution", {}).get("y_solution", {})) if classic.get("best_solution") else None,
        "selected_cut_count": classic.get("cut_count"),
        "runtime_sec": classic.get("elapsed_sec"),
        "policy_name": "all_cuts",
        "note": "classic Benders decomposition on public benchmark projection",
        "demand_total_ton": demand_total,
        "cost_per_ton": (objective / demand_total) if objective is not None and demand_total > 0 else None,
        "mip_gap_target": case.get("mip_gap", 0.01),
        "mip_gap_actual": classic.get("final_gap_pct"),
    }


def _ai_record(
    case: dict[str, Any],
    instance: SmokeInstance,
    classic: dict[str, Any],
    ai: dict[str, Any],
    direct_objective: float | None,
) -> dict[str, Any]:
    case_id = str(case.get("case_id") or case.get("entry_id") or instance.instance_name)
    candidate_count = int(case.get("candidate_count") or case.get("facility_count") or instance.facility_count)
    demand_count = int(case.get("demand_count") or case.get("customer_count") or instance.customer_count)
    objective = classic.get("upper_bound")
    objective_gap_pct = None
    if direct_objective not in (None, 0) and objective is not None:
        objective_gap_pct = abs(float(objective) - float(direct_objective)) / abs(float(direct_objective)) * 100.0
    demand_total = float(sum(customer["demand"] for customer in instance.customers))
    return {
        "source_id": SOURCE_ID,
        "case_id": case_id,
        "method": "ai_benders",
        "run_key": f"benchmark_ai_benders_{case_id}",
        "experiment_key": "benchmark_benders_comparison",
        "candidate_count": candidate_count,
        "demand_count": demand_count,
        "status_code": classic.get("status_code"),
        "status_name": classic.get("status_name"),
        "objective": objective,
        "direct_objective": direct_objective,
        "objective_gap_pct": objective_gap_pct,
        "fixed_cost_yuan": classic.get("best_solution", {}).get("fixed_cost_yuan") if classic.get("best_solution") else None,
        "transport_cost_yuan": classic.get("best_solution", {}).get("transport_cost_yuan") if classic.get("best_solution") else None,
        "loss_cost_yuan": 0.0,
        "carbon_cost_yuan": 0.0,
        "total_cost_yuan": objective,
        "lower_bound": classic.get("lower_bound"),
        "upper_bound": classic.get("upper_bound"),
        "final_gap_pct": classic.get("final_gap_pct"),
        "cut_count": classic.get("cut_count"),
        "iteration_count": len(classic.get("iterations", [])),
        "open_facilities": len(classic.get("best_solution", {}).get("y_solution", {})) if classic.get("best_solution") else None,
        "selected_cut_count": ai.get("selected_cut_count"),
        "runtime_sec": classic.get("elapsed_sec"),
        "policy_name": ai.get("ai_cut_policy"),
        "note": "classic Benders + explainable AI cut ranking prototype",
        "demand_total_ton": demand_total,
        "cost_per_ton": (objective / demand_total) if objective is not None and demand_total > 0 else None,
        "mip_gap_target": case.get("mip_gap", 0.01),
        "mip_gap_actual": classic.get("final_gap_pct"),
    }


def _ai_active_record(
    case: dict[str, Any],
    instance: SmokeInstance,
    ai_active: dict[str, Any],
    direct_objective: float | None,
) -> dict[str, Any]:
    case_id = str(case.get("case_id") or case.get("entry_id") or instance.instance_name)
    candidate_count = int(case.get("candidate_count") or case.get("facility_count") or instance.facility_count)
    demand_count = int(case.get("demand_count") or case.get("customer_count") or instance.customer_count)
    objective = ai_active.get("upper_bound")
    objective_gap_pct = None
    if direct_objective not in (None, 0) and objective is not None:
        objective_gap_pct = abs(float(objective) - float(direct_objective)) / abs(float(direct_objective)) * 100.0
    demand_total = float(sum(customer["demand"] for customer in instance.customers))
    return {
        "source_id": SOURCE_ID,
        "case_id": case_id,
        "method": "ai_active_benders",
        "run_key": f"benchmark_ai_active_benders_{case_id}",
        "experiment_key": "benchmark_benders_comparison",
        "candidate_count": candidate_count,
        "demand_count": demand_count,
        "status_code": ai_active.get("status_code"),
        "status_name": ai_active.get("status_name"),
        "objective": objective,
        "direct_objective": direct_objective,
        "objective_gap_pct": objective_gap_pct,
        "fixed_cost_yuan": ai_active.get("best_solution", {}).get("fixed_cost_yuan") if ai_active.get("best_solution") else None,
        "transport_cost_yuan": ai_active.get("best_solution", {}).get("transport_cost_yuan") if ai_active.get("best_solution") else None,
        "loss_cost_yuan": 0.0,
        "carbon_cost_yuan": 0.0,
        "total_cost_yuan": objective,
        "lower_bound": ai_active.get("lower_bound"),
        "upper_bound": ai_active.get("upper_bound"),
        "final_gap_pct": ai_active.get("final_gap_pct"),
        "cut_count": ai_active.get("cut_count"),
        "iteration_count": len(ai_active.get("iterations", [])),
        "open_facilities": len(ai_active.get("best_solution", {}).get("y_solution", {})) if ai_active.get("best_solution") else None,
        "selected_cut_count": ai_active.get("unique_selected_cut_count"),
        "runtime_sec": ai_active.get("elapsed_sec"),
        "policy_name": ai_active.get("policy_name"),
        "note": "AI-active Benders using learned cut ranking as active master cut budget",
        "demand_total_ton": demand_total,
        "cost_per_ton": (objective / demand_total) if objective is not None and demand_total > 0 else None,
        "mip_gap_target": case.get("mip_gap", 0.01),
        "mip_gap_actual": ai_active.get("final_gap_pct"),
        "active_cut_budget": ai_active.get("active_cut_budget"),
        "final_active_cut_count": ai_active.get("final_active_cut_count"),
        "termination_reason": ai_active.get("termination_reason"),
    }


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    class _Config:
        pass

    manifest = load_normalized_manifest(prefer_file=True)
    selected_entries = select_entries(manifest, max_instances=3)

    rows: list[dict[str, Any]] = []
    iteration_rows: list[dict[str, Any]] = []
    cut_score_rows: list[dict[str, Any]] = []
    details: list[dict[str, Any]] = []
    cases: list[dict[str, Any]] = []

    for case in selected_entries:
        instance = parse_smoke_instance(case)
        case_record = dict(case)
        case_record["case_id"] = case_record.get("entry_id")
        case_record["candidate_count"] = int(case_record.get("facility_count") or instance.facility_count)
        case_record["demand_count"] = int(case_record.get("customer_count") or instance.customer_count)
        case_record["mip_gap"] = 0.01
        cases.append(
            {
                "case_id": case["entry_id"],
                "instance_name": instance.instance_name,
                "parser_name": instance.parser_name,
                "customer_count": instance.customer_count,
                "facility_count": instance.facility_count,
                "source_path": instance.source_path,
            }
        )

        direct = solve_direct_projection(instance, time_limit=60, mip_gap=0.01)
        classic = solve_classic_benders(
            instance,
            time_limit=60,
            mip_gap=0.01,
            threads=4,
            max_iterations=8,
            verbose=False,
        )
        ai = build_ai_evidence(instance, classic.get("cut_history", []), top_k_cuts=3)
        ai_active = solve_ai_active_benders(
            instance,
            classic.get("cut_history", []),
            time_limit=60,
            mip_gap=0.01,
            threads=4,
            max_iterations=8,
            active_cut_budget=2,
            verbose=False,
        )

        rows.append(_direct_record(case_record, instance, direct))
        rows.append(_classic_record(case_record, instance, classic, direct.get("objective")))
        rows.append(_ai_record(case_record, instance, classic, ai, direct.get("objective")))
        rows.append(_ai_active_record(case_record, instance, ai_active, direct.get("objective")))

        for iter_row in classic.get("iterations", []):
            enriched_iter = dict(iter_row)
            enriched_iter["case_id"] = case_record["case_id"]
            enriched_iter["instance_name"] = instance.instance_name
            enriched_iter["run_key"] = f"benchmark_classic_benders_{case_record['case_id']}"
            iteration_rows.append(enriched_iter)
        for iter_row in ai_active.get("iterations", []):
            enriched_iter = dict(iter_row)
            enriched_iter["case_id"] = case_record["case_id"]
            enriched_iter["instance_name"] = instance.instance_name
            enriched_iter["run_key"] = f"benchmark_ai_active_benders_{case_record['case_id']}"
            iteration_rows.append(enriched_iter)

        for record in ai.get("ai_cut_scores", []):
            cut_score_rows.append(
                {
                    "source_id": SOURCE_ID,
                    "case_id": case_record["case_id"],
                    "method": "ai_benders",
                    "run_key": f"benchmark_ai_benders_{case_record['case_id']}",
                    "iter_no": record.get("iter_no"),
                    "cut_id": record.get("cut_id"),
                    "cut_type": record.get("cut_type"),
                    "features_json": record.get("features", {}),
                    "score": record.get("score"),
                    "selected": bool(record.get("selected")),
                    "policy_name": record.get("policy_name"),
                    "rhs": record.get("rhs"),
                    "coef_count": record.get("coef_count"),
                    "gap_pct": record.get("gap_pct"),
                    "score_formula": record.get("score_formula"),
                    "dominant_factors": record.get("dominant_factors"),
                    "reason_text": record.get("reason_text"),
                }
            )
        for record in ai_active.get("active_cut_scores", []):
            cut_score_rows.append(
                {
                    "source_id": SOURCE_ID,
                    "case_id": case_record["case_id"],
                    "method": "ai_active_benders",
                    "run_key": f"benchmark_ai_active_benders_{case_record['case_id']}",
                    "iter_no": record.get("selection_iter_no") or record.get("iter_no"),
                    "cut_id": record.get("cut_id"),
                    "cut_type": record.get("cut_type"),
                    "features_json": record.get("features", {}),
                    "score": record.get("score"),
                    "selected": bool(record.get("selected")),
                    "policy_name": record.get("policy_name"),
                    "rhs": record.get("rhs"),
                    "coef_count": record.get("coef_count"),
                    "gap_pct": record.get("gap_pct"),
                    "score_formula": record.get("score_formula"),
                    "dominant_factors": record.get("dominant_factors"),
                    "reason_text": record.get("reason_text"),
                    "active_cut_budget": record.get("active_cut_budget"),
                    "candidate_cut_count": record.get("candidate_cut_count"),
                    "active_cut_count": record.get("active_cut_count"),
                }
            )

        details.append(
            {
                "case_id": case_record["case_id"],
                "direct": direct,
                "classic_benders": classic,
                "ai_benders": ai,
                "ai_active_benders": ai_active,
            }
        )

        case_detail_path = OUT_DIR / f"{case_record['case_id'].replace(':', '_')}_ai_detail.json"
        case_detail_path.write_text(
            json.dumps(
                {
                    "case_id": case_record["case_id"],
                    "direct": _json_safe(direct),
                    "classic_benders": _json_safe(classic),
                    "ai_benders": _json_safe(ai),
                    "ai_active_benders": _json_safe(ai_active),
                    "research_boundary": AI_BENDERS_RESEARCH_BOUNDARY,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    summary_df = pd.DataFrame(rows)
    outputs = save_dataframe_bundle(summary_df, OUT_DIR / "benchmark_benders_comparison")
    iteration_df = pd.DataFrame(iteration_rows)
    iteration_outputs = save_dataframe_bundle(iteration_df, OUT_DIR / "benchmark_benders_iterations")
    cut_df = pd.DataFrame(cut_score_rows)
    cut_outputs = save_dataframe_bundle(cut_df, OUT_DIR / "benchmark_benders_cut_scores")

    md_path = write_markdown_table(
        summary_df,
        OUT_DIR / "benchmark_benders_comparison.md",
        [
            "case_id",
            "method",
            "objective",
            "objective_gap_pct",
            "cut_count",
            "iteration_count",
            "selected_cut_count",
            "runtime_sec",
        ],
    )

    objective_gap_summary = {}
    for method in ["classic_benders", "ai_benders", "ai_active_benders"]:
        method_rows = [row for row in rows if row["method"] == method and row.get("objective_gap_pct") is not None]
        if method_rows:
            objective_gap_summary[method] = {
                "mean_gap_pct": float(sum(row["objective_gap_pct"] for row in method_rows) / len(method_rows)),
                "max_gap_pct": float(max(row["objective_gap_pct"] for row in method_rows)),
                "min_gap_pct": float(min(row["objective_gap_pct"] for row in method_rows)),
            }

    ai_active_rows = [row for row in rows if row.get("method") == "ai_active_benders"]
    ai_active_summary = {
        "method": "ai_active_benders",
        "case_count": len(ai_active_rows),
        "active_cut_budget": 2,
        "mean_selected_cut_count": (
            float(sum(float(row.get("selected_cut_count") or 0.0) for row in ai_active_rows) / len(ai_active_rows))
            if ai_active_rows else None
        ),
        "termination_reasons": sorted({str(row.get("termination_reason")) for row in ai_active_rows if row.get("termination_reason")}),
        "research_boundary": (
            "AI-active Benders uses same-instance calibration cut history to rank active master cuts. "
            "It is a second-stage mechanism check, not an out-of-sample superiority proof."
        ),
    }

    summary_json = {
        "experiment_name": "benchmark_benders_comparison",
        "source_id": SOURCE_ID,
        "cases": _json_safe(cases),
        "summary_rows": _json_safe(rows),
        "iteration_rows": _json_safe(iteration_rows),
        "cut_score_rows": _json_safe(cut_score_rows),
        "ai_details": _json_safe(details),
        "files": {k: str(v) for k, v in outputs.items()},
        "iteration_files": {k: str(v) for k, v in iteration_outputs.items()},
        "cut_score_files": {k: str(v) for k, v in cut_outputs.items()},
        "markdown": str(md_path),
        "total_cases": len(cases),
        "method_rows": len(rows),
        "iteration_count": len(iteration_rows),
        "cut_score_count": len(cut_score_rows),
        "objective_gap_summary": objective_gap_summary,
        "ai_active_summary": ai_active_summary,
        "research_boundary": (
            "Classic Benders and AI-Benders variants on public benchmark facility-location projections. "
            "AI-active Benders uses learned cut ranking to limit active master cuts, but this remains a same-instance "
            "calibration mechanism check, not full routing proof, not okra enterprise validation, and not an "
            "out-of-sample AI superiority proof."
        ),
    }
    (OUT_DIR / "benchmark_benders_summary.json").write_text(
        json.dumps(summary_json, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    with open(OUT_DIR / "benchmark_benders_comparison.pkl", "wb") as fh:
        pickle.dump(summary_json, fh)

    print(json.dumps({"rows": len(rows), "iterations": len(iteration_rows), "cuts": len(cut_score_rows), "out_dir": str(OUT_DIR)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
