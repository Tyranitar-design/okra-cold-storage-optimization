"""Single-level MIP v3.0 with peak-capacity and okra service-chain semantics."""

from __future__ import annotations

import json
import os
import pickle
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict

from src.models.capacity_chain_assumptions import (
    CapacityChainAssumptions,
    ChannelAssumption,
    _annual_flow,
    _channel_map,
    _peak_capacity_load,
    default_assumptions,
)
from src.models.single_level_mip_v2_1 import DataConfig, GRB, gp


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESULTS_ROOT = PROJECT_ROOT / "results"
DEFAULT_DATA_DIR = PROJECT_ROOT / "data"
RESULT_PICKLE_PATH = RESULTS_ROOT / "baseline_v3_capacity_chain_result.pkl"


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(val) for key, val in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            return value
    if isinstance(value, Path):
        return str(value)
    return value


def build_and_solve_v3(
    config: DataConfig,
    assumptions: CapacityChainAssumptions | None = None,
    candidate_ids: list[str] | None = None,
    demand_ids: list[str] | None = None,
    time_limit: int = 300,
    mip_gap: float = 0.01,
    threads: int = 8,
    solver_params: dict[str, Any] | None = None,
    verbose: bool = True,
) -> tuple[Any, dict[tuple[str, str, int], Any], dict[tuple[str, str, str], Any], float]:
    """Build and solve v3.0 baseline model."""

    assumptions = assumptions or default_assumptions()
    channels = _channel_map(assumptions)
    active_types = [channel.type_id for channel in assumptions.channels if channel.annual_share > 0]

    if candidate_ids is None:
        candidate_ids = list(config.candidates["node_id"])
    if demand_ids is None:
        demand_ids = list(config.demands["node_id"])

    demand = {node_id: config.get_demand(node_id) for node_id in demand_ids}

    model = gp.Model("OkraColdStorage_MIP_v3_capacity_chain")
    model.setParam("TimeLimit", time_limit)
    model.setParam("MIPGap", mip_gap)
    model.setParam("Threads", threads)
    model.setParam("OutputFlag", 1 if verbose else 0)
    for param_name, param_value in (solver_params or {}).items():
        model.setParam(param_name, param_value)

    z: dict[tuple[str, str, int], Any] = {}
    for site in candidate_ids:
        for type_id in active_types:
            for cap_idx, _cap in enumerate(config.capacity_index[type_id]):
                z[site, type_id, cap_idx] = model.addVar(vtype=GRB.BINARY, name=f"z_{site}_{type_id}_{cap_idx}")

    x: dict[tuple[str, str, str], Any] = {}
    for demand_id in demand_ids:
        for site in candidate_ids:
            for type_id in active_types:
                x[demand_id, site, type_id] = model.addVar(
                    vtype=GRB.CONTINUOUS,
                    lb=0.0,
                    ub=1.0,
                    name=f"x_{demand_id}_{site}_{type_id}",
                )

    model.update()

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
                        z[site, type_id, cap_idx] for cap_idx in range(len(config.capacity_index[type_id]))
                    ),
                    name=f"assign_open_{demand_id}_{site}_{type_id}",
                )

    for site in candidate_ids:
        model.addConstr(
            gp.quicksum(
                z[site, type_id, cap_idx]
                for type_id in active_types
                for cap_idx in range(len(config.capacity_index[type_id]))
            )
            <= 1,
            name=f"one_facility_{site}",
        )

    model.addConstr(
        gp.quicksum(
            z[site, type_id, cap_idx]
            for site in candidate_ids
            for type_id in active_types
            for cap_idx in range(len(config.capacity_index[type_id]))
        )
        <= assumptions.max_facilities,
        name="max_facilities",
    )

    precool_limit_h = config.get_preservation_params().get("precool_time_limit_h", 2.0)
    for demand_id in demand_ids:
        for site in candidate_ids:
            if config.get_time(demand_id, site) > precool_limit_h:
                model.addConstr(x[demand_id, site, "precool"] == 0.0, name=f"precool_time_{demand_id}_{site}")

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

    model.setObjective(fixed_cost + operate_cost + transport_cost + loss_cost + carbon_cost, GRB.MINIMIZE)
    model.update()

    if verbose:
        print("=" * 72)
        print("Solving OkraColdStorage_MIP_v3_capacity_chain")
        print(f"Variables={model.NumVars}, constraints={model.NumConstrs}, candidates={len(candidate_ids)}")
        print("=" * 72)

    start = time.time()
    model.optimize()
    elapsed = time.time() - start

    return model, z, x, elapsed


def analyze_v3_results(
    model: Any,
    z: dict[tuple[str, str, int], Any],
    x: dict[tuple[str, str, str], Any],
    config: DataConfig,
    candidate_ids: list[str],
    demand_ids: list[str],
    assumptions: CapacityChainAssumptions | None = None,
) -> Dict[str, Any]:
    """Create a structured v3 result analysis from solved variables."""

    assumptions = assumptions or default_assumptions()
    channels = _channel_map(assumptions)
    active_types = list(channels.keys())
    demand = {node_id: config.get_demand(node_id) for node_id in demand_ids}

    fixed_total = 0.0
    operate_total = 0.0
    facilities: list[dict[str, Any]] = []
    for site in candidate_ids:
        for type_id in active_types:
            for cap_idx, cap_info in enumerate(config.capacity_index[type_id]):
                if z[site, type_id, cap_idx].X > 0.5:
                    fixed_total += cap_info["fixed_cost"] * 10000
                    operate_total += cap_info["operate_cost"] * 10000
                    annual_flow = sum(x[demand_id, site, type_id].X * demand[demand_id] for demand_id in demand_ids)
                    channel = channels[type_id]
                    peak_load = sum(
                        x[demand_id, site, type_id].X
                        * demand[demand_id]
                        * channel.storage_days
                        / assumptions.harvest_window_days
                        * assumptions.harvest_peak_factor
                        for demand_id in demand_ids
                    )
                    facilities.append(
                        {
                            "site": site,
                            "type": type_id,
                            "type_name": config.get_storage_params(type_id)["name"],
                            "capacity": cap_info["capacity"],
                            "capacity_idx": cap_idx,
                            "fixed_cost": cap_info["fixed_cost"],
                            "operate_cost": cap_info["operate_cost"],
                            "assigned_annual_flow_ton": annual_flow,
                            "peak_capacity_load_ton": peak_load,
                            "utilization": peak_load / cap_info["capacity"] * 100 if cap_info["capacity"] else 0.0,
                        }
                    )

    transport_total = 0.0
    loss_total = 0.0
    carbon_total = 0.0
    annual_flow_by_type = {type_id: 0.0 for type_id in active_types}
    peak_load_by_type = {type_id: 0.0 for type_id in active_types}
    assignments: list[dict[str, Any]] = []
    for demand_id in demand_ids:
        for site in candidate_ids:
            for type_id in active_types:
                value = x[demand_id, site, type_id].X
                if value <= 1e-7:
                    continue
                channel = channels[type_id]
                annual_flow = value * demand[demand_id]
                peak_load = value * demand[demand_id] * channel.storage_days / assumptions.harvest_window_days * assumptions.harvest_peak_factor
                dist = config.get_dist(demand_id, site)
                travel_time = config.get_time(demand_id, site)
                transport_total += annual_flow * dist * assumptions.transport_cost_yuan_per_ton_km
                loss_total += annual_flow * (
                    travel_time
                    * config.get_preservation_params().get("transport_loss_per_hour", 0.02)
                    * channel.transport_loss_multiplier
                    + channel.loss_rate
                ) * assumptions.loss_price
                carbon_total += annual_flow * (
                    config.capacity_index[type_id][0]["energy_cost_per_ton"]
                    * config.capacity_index[type_id][0]["carbon_factor"]
                    / 1000
                    + dist * assumptions.transport_carbon_kg_per_ton_km / 1000
                ) * assumptions.carbon_price
                annual_flow_by_type[type_id] += annual_flow
                peak_load_by_type[type_id] += peak_load
                assignments.append(
                    {
                        "demand_id": demand_id,
                        "site": site,
                        "type": type_id,
                        "annual_flow_ton": annual_flow,
                        "peak_capacity_load_ton": peak_load,
                        "distance_km": dist,
                        "travel_time_h": travel_time,
                    }
                )

    total_cost = fixed_total + operate_total + transport_total + loss_total + carbon_total
    total_annual_production = sum(demand.values())
    downstream_share_sum = sum(channel.annual_share for channel in assumptions.channels if channel.type_id != "precool")
    frozen_share = channels.get("frozen").annual_share if "frozen" in channels else 0.0

    return _json_safe(
        {
            "model_version": "v3.0_capacity_chain",
            "solver": {
                "status_code": int(getattr(model, "Status", -1)),
                "status_name": _status_name(int(getattr(model, "Status", -1))),
                "sol_count": int(getattr(model, "SolCount", 0)),
                "objective": float(model.ObjVal) if getattr(model, "SolCount", 0) > 0 else None,
                "mip_gap_pct": float(getattr(model, "MIPGap", 0.0) * 100.0) if getattr(model, "SolCount", 0) > 0 else None,
                "objective_bound": float(getattr(model, "ObjBound", 0.0)) if getattr(model, "SolCount", 0) > 0 else None,
                "num_vars": int(getattr(model, "NumVars", 0)),
                "num_constraints": int(getattr(model, "NumConstrs", 0)),
            },
            "summary": {
                "total_cost": total_cost,
                "fixed_cost": fixed_total,
                "operate_cost": operate_total,
                "transport_cost": transport_total,
                "loss_cost": loss_total,
                "carbon_cost": carbon_total,
                "num_facilities": len(facilities),
                "total_annual_production_ton": total_annual_production,
                "total_service_annual_flow_ton": sum(annual_flow_by_type.values()),
                "total_peak_capacity_load_ton": sum(peak_load_by_type.values()),
                "installed_capacity_ton": sum(item["capacity"] for item in facilities),
                "fresh_chain_share": 1.0 - frozen_share,
                "frozen_or_processing_share": frozen_share,
                "downstream_share_sum": downstream_share_sum,
                "capacity_semantics": "peak_inventory_from_annual_flow",
                "selected_storage_types": sorted({item["type"] for item in facilities}),
            },
            "facilities": facilities,
            "annual_flow_by_type": annual_flow_by_type,
            "peak_load_by_type": peak_load_by_type,
            "assignments": assignments,
            "assumptions": {
                "harvest_window_days": assumptions.harvest_window_days,
                "harvest_peak_factor": assumptions.harvest_peak_factor,
                "max_facilities": assumptions.max_facilities,
                "carbon_price": assumptions.carbon_price,
                "loss_price": assumptions.loss_price,
                "channels": [asdict(channel) for channel in assumptions.channels],
            },
            "risk_response": {
                "capacity_semantics": "uses peak load instead of annual production in capacity constraints",
                "temperature_chain": "requires positive precool, cold, CA, and capped frozen/processing channels",
                "frozen_only_prevented": frozen_share < 0.5 and len({item["type"] for item in facilities}) >= 3,
                "paper_claim_boundary": (
                    "v3.0 is a corrected scenario baseline. Channel shares are auditable assumptions until real "
                    "enterprise sales/processing data are ingested."
                ),
            },
        }
    )


def _status_name(status_code: int) -> str:
    status_map = {
        2: "OPTIMAL",
        3: "INFEASIBLE",
        4: "INF_OR_UNBD",
        5: "UNBOUNDED",
        9: "TIME_LIMIT",
        11: "INTERRUPTED",
        13: "SUBOPTIMAL",
    }
    return status_map.get(status_code, f"STATUS_{status_code}")


def solve_baseline_v3(
    data_dir: Path | str = DEFAULT_DATA_DIR,
    assumptions: CapacityChainAssumptions | None = None,
    time_limit: int = 300,
    mip_gap: float = 0.01,
    threads: int = 8,
    solver_params: dict[str, Any] | None = None,
    verbose: bool = True,
) -> Dict[str, Any]:
    """Solve the default v3.0 baseline and return structured output."""

    config = DataConfig(str(data_dir))
    assumptions = assumptions or default_assumptions()
    candidate_ids = list(config.candidates["node_id"])
    demand_ids = list(config.demands["node_id"])
    model, z, x, elapsed = build_and_solve_v3(
        config,
        assumptions=assumptions,
        candidate_ids=candidate_ids,
        demand_ids=demand_ids,
        time_limit=time_limit,
        mip_gap=mip_gap,
        threads=threads,
        solver_params=solver_params,
        verbose=verbose,
    )
    if model.SolCount <= 0:
        raise RuntimeError(f"v3.0 baseline failed to find a feasible solution; status={model.Status}")
    analysis = analyze_v3_results(model, z, x, config, candidate_ids, demand_ids, assumptions=assumptions)
    return {
        "analysis": analysis,
        "elapsed": elapsed,
        "candidate_ids": candidate_ids,
        "demand_ids": demand_ids,
        "result_paths": {"pickle": str(RESULT_PICKLE_PATH)},
    }


def write_v3_result_bundle(payload: Dict[str, Any], output_path: Path = RESULT_PICKLE_PATH) -> Dict[str, str]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("wb") as handle:
        pickle.dump(payload, handle)
    return {"pickle_path": str(output_path)}


def main() -> None:
    payload = solve_baseline_v3(verbose=True)
    paths = write_v3_result_bundle(payload)
    print(json.dumps(paths, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
