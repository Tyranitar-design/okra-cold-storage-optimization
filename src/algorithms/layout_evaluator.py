"""Shared solution evaluator for the okra cold-storage layout problem.

Both the exact (epsilon-constraint / MIP) and the heuristic (NSGA-III, ALNS)
methods optimise the SAME three objectives over the SAME feasible region, so a
single, authoritative evaluator avoids the classic trap of comparing methods
that secretly optimise slightly different things.

Genotype
--------
An assignment vector ``a`` of length ``len(demand_ids)`` where ``a[i]`` indexes
a (facility j, storage type t) pair from ``choice_list``. A facility is "built"
at the cheapest capacity level whose capacity covers the demand routed to that
(j, t); fixed + operating cost follow from the built capacity level.

Objectives (all minimised)
--------------------------
* ``cost``       -- fixed + operate + transport + loss*price + carbon*price (yuan)
* ``loss_ton``   -- total spoilage tonnage
* ``carbon_ton`` -- total CO2-equivalent tonnage

Constraints
-----------
* each demand point assigned exactly once (enforced by the genotype);
* at most ``max_facilities`` distinct (j, t) facilities opened;
* per-(j, t) routed demand must fit the largest available capacity level;
* pre-cool travel-time limit for any demand routed to a ``precool`` facility.

This evaluator is deliberately solver-free so it can be called millions of
times inside a metaheuristic loop.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.models.layout_problem import (
    LayoutProblemData,
    build_layout_data,
    get_capacity,
    get_fixed_cost,
    get_loss_ton_per_ton,
    get_carbon_ton_per_ton,
    get_operate_cost,
)

OBJECTIVE_NAMES = ("cost", "loss_ton", "carbon_ton")
PENALTY = 1e12  # large finite penalty for infeasible genotypes


@dataclass
class LayoutEvaluator:
    """Vectorised-ish evaluator over the (j, t) assignment genotype."""

    data: LayoutProblemData
    carbon_price: float
    loss_price: float
    max_facilities: int

    # Derived lookups (filled in __post_init__)
    choice_list: list[tuple[str, str]] = None  # index -> (facility_id, storage_type)
    n_choices: int = 0
    n_demand: int = 0

    def __post_init__(self) -> None:
        data = self.data
        self.choice_list = [
            (j, t) for j in data.candidate_ids for t in data.storage_types
        ]
        self.n_choices = len(self.choice_list)
        self.n_demand = len(data.demand_ids)
        # Precompute per-(demand, choice) unit coefficients to avoid repeated lookups.
        pp = data.config.get_preservation_params()
        self._precool_limit = float(pp["precool_time_limit_h"])
        self._unit_transport: dict[tuple[int, int], float] = {}
        self._unit_loss: dict[tuple[int, int], float] = {}
        self._unit_carbon: dict[tuple[int, int], float] = {}
        self._travel_time: dict[tuple[int, int], float] = {}
        for ci, (j, t) in enumerate(self.choice_list):
            for di, i in enumerate(data.demand_ids):
                dist = data.config.get_dist(i, j)
                self._unit_transport[di, ci] = dist * data.transport_unit_cost
                self._unit_loss[di, ci] = get_loss_ton_per_ton(data, i, j, t)
                self._unit_carbon[di, ci] = get_carbon_ton_per_ton(data, i, j, t)
                self._travel_time[di, ci] = data.config.get_time(i, j)
        # Largest capacity available per storage type (for capacity feasibility).
        self._max_cap: dict[str, float] = {}
        self._cap_levels: dict[str, list[float]] = {}
        for t in data.storage_types:
            levels = [get_capacity(data, t, c) for c in range(len(data.config.capacity_index[t]))]
            self._cap_levels[t] = levels
            self._max_cap[t] = max(levels) if levels else 0.0

    def _cheapest_level_for(self, t: str, load_ton: float) -> tuple[int, float, float]:
        """Cheapest capacity level (idx) covering load_ton; returns (idx, fixed, operate) in yuan."""
        best = None
        for c, cap in enumerate(self._cap_levels[t]):
            if cap + 1e-9 >= load_ton:
                fixed = get_fixed_cost(self.data, t, c) * 10000.0
                operate = get_operate_cost(self.data, t, c) * 10000.0
                cost = fixed + operate
                if best is None or cost < best[3]:
                    best = (c, fixed, operate, cost)
        if best is None:
            return -1, 0.0, 0.0  # infeasible: no level covers the load
        return best[0], best[1], best[2]

    def evaluate(self, assignment: list[int]) -> dict[str, Any]:
        """Evaluate one genotype. Returns objectives + feasibility detail."""
        data = self.data
        # Accumulate routed demand and variable costs per opened (j, t).
        load: dict[int, float] = {}
        transport_cost = 0.0
        loss_ton = 0.0
        carbon_ton = 0.0
        precool_violations = 0
        for di, ci in enumerate(assignment):
            d = data.demand[data.demand_ids[di]]
            load[ci] = load.get(ci, 0.0) + d
            transport_cost += self._unit_transport[di, ci] * d
            loss_ton += self._unit_loss[di, ci] * d
            carbon_ton += self._unit_carbon[di, ci] * d
            j, t = self.choice_list[ci]
            if t == "precool" and self._travel_time[di, ci] > self._precool_limit + 1e-9:
                precool_violations += 1

        # Open facilities = distinct choices used; fixed+operate from cheapest covering level.
        fixed_operate = 0.0
        capacity_violations = 0
        for ci, routed in load.items():
            j, t = self.choice_list[ci]
            idx, fixed, operate = self._cheapest_level_for(t, routed)
            if idx < 0:
                capacity_violations += 1
                fixed_operate += PENALTY  # cannot cover -> heavy penalty
            else:
                fixed_operate += fixed + operate

        num_facilities = len(load)
        facility_violation = max(0, num_facilities - self.max_facilities)

        cost = fixed_operate + transport_cost + loss_ton * self.loss_price + carbon_ton * self.carbon_price
        feasible = (capacity_violations == 0 and facility_violation == 0 and precool_violations == 0)

        # Constraint magnitude (>=0, 0 means feasible) for NSGA-III constraint handling.
        constraint_violation = float(
            capacity_violations + facility_violation + precool_violations
        )

        return {
            "cost": float(cost),
            "loss_ton": float(loss_ton),
            "carbon_ton": float(carbon_ton),
            "num_facilities": int(num_facilities),
            "precool_violations": int(precool_violations),
            "capacity_violations": int(capacity_violations),
            "facility_violation": int(facility_violation),
            "constraint_violation": constraint_violation,
            "feasible": bool(feasible),
        }

    def objectives(self, assignment: list[int]) -> tuple[float, float, float]:
        r = self.evaluate(assignment)
        cv = r["constraint_violation"]
        if cv > 0:
            # Penalise infeasible solutions proportionally on every objective.
            bump = 1.0 + cv
            return (r["cost"] * bump + PENALTY * cv, r["loss_ton"] * bump, r["carbon_ton"] * bump)
        return (r["cost"], r["loss_ton"], r["carbon_ton"])


def make_evaluator(
    config: Any,
    *,
    carbon_price: float = 50.0,
    loss_price: float = 3000.0,
    max_facilities: int = 8,
    candidate_ids: list[str] | None = None,
    demand_ids: list[str] | None = None,
) -> LayoutEvaluator:
    data = build_layout_data(config, candidate_ids=candidate_ids, demand_ids=demand_ids)
    return LayoutEvaluator(
        data=data,
        carbon_price=carbon_price,
        loss_price=loss_price,
        max_facilities=max_facilities,
    )
