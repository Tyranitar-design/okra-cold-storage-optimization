"""NSGA-III and ALNS heuristic baselines for the okra cold-storage layout problem.

Purpose
-------
The exact method (augmented epsilon-constraint MIP via Gurobi) produces a
provably non-dominated Pareto frontier. To argue *why* an exact / AI-enhanced
exact approach is worth recommending, we must compare it against strong, widely
used metaheuristics on the SAME problem and SAME objectives:

* ``NSGA-III`` -- reference-point many-objective genetic algorithm (pymoo);
* ``ALNS``     -- adaptive large neighbourhood search with a Pareto archive.

Both consume :class:`LayoutEvaluator`, so the comparison is apples-to-apples.
We report hypervolume, frontier size, exact-dominance coverage and runtime, and
we state honestly where heuristics match the exact frontier and where they fall
short -- we do not assume a winner in advance.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from src.algorithms.layout_evaluator import LayoutEvaluator


# ---------------------------------------------------------------------------
# Feasible seeding + Pareto utilities (shared by both heuristics)
# ---------------------------------------------------------------------------

def greedy_feasible_assignment(ev: LayoutEvaluator, rng: random.Random, n_hubs: int | None = None) -> list[int]:
    """Build a feasible assignment by concentrating demand on a few cheap hubs.

    Cold storage economics reward *fewer, larger* facilities (fixed cost
    dominates), so we try a small hub count first and grow only if capacity
    forces it. ``n_hubs`` lets callers sweep the facility-count tradeoff.
    """
    data = ev.data
    n = ev.n_demand
    total_demand = sum(data.demand[data.demand_ids[di]] for di in range(n))
    # Hub candidates: cold/ca/frozen choices (large capacity), shuffled for diversity.
    hub_choices = [ci for ci, (j, t) in enumerate(ev.choice_list) if t in ("cold", "ca", "frozen")]
    rng.shuffle(hub_choices)

    # Minimum hubs needed so total capacity can cover total demand.
    if n_hubs is None:
        max_single = max(ev._max_cap[t] for t in ("cold", "ca", "frozen") if t in ev._max_cap)
        n_hubs = max(1, min(ev.max_facilities, int(np.ceil(total_demand / max(max_single, 1.0)))))
    n_hubs = min(n_hubs, ev.max_facilities, len(hub_choices))

    for _attempt in range(6):
        hubs = hub_choices[:n_hubs]
        assignment = [0] * n
        load = {ci: 0.0 for ci in hubs}
        ok = True
        # assign demands largest-first to the cheapest fitting hub
        order = sorted(range(n), key=lambda di: -data.demand[data.demand_ids[di]])
        for di in order:
            d = data.demand[data.demand_ids[di]]
            best_ci, best_cost = None, None
            for ci in hubs:
                j, t = ev.choice_list[ci]
                if t == "precool" and ev._travel_time[di, ci] > ev._precool_limit + 1e-9:
                    continue
                if load[ci] + d > ev._max_cap[t] + 1e-9:
                    continue
                unit = ev._unit_transport[di, ci] + ev._unit_loss[di, ci] * ev.loss_price + ev._unit_carbon[di, ci] * ev.carbon_price
                if best_cost is None or unit < best_cost:
                    best_cost, best_ci = unit, ci
            if best_ci is None:
                ok = False
                break
            assignment[di] = best_ci
            load[best_ci] += d
        if ok:
            return assignment
        n_hubs = min(n_hubs + 1, ev.max_facilities, len(hub_choices))
    # last resort: spread across all hubs
    hubs = hub_choices[: min(ev.max_facilities, len(hub_choices))]
    return [hubs[di % len(hubs)] for di in range(n)]


def dominates(a: tuple[float, ...], b: tuple[float, ...]) -> bool:
    """Return True if objective tuple a Pareto-dominates b (minimisation)."""
    not_worse = all(x <= y + 1e-9 for x, y in zip(a, b))
    strictly_better = any(x < y - 1e-9 for x, y in zip(a, b))
    return not_worse and strictly_better


def pareto_filter(points: list[tuple[tuple[float, ...], Any]]) -> list[tuple[tuple[float, ...], Any]]:
    """Keep only non-dominated (objective, payload) entries."""
    front: list[tuple[tuple[float, ...], Any]] = []
    for obj, payload in points:
        if any(dominates(other_obj, obj) for other_obj, _ in points if other_obj != obj):
            continue
        # de-dup identical objective tuples
        if any(other_obj == obj for other_obj, _ in front):
            continue
        front.append((obj, payload))
    return front


def hypervolume_2d_proxy(front: list[tuple[float, ...]], ref: tuple[float, ...]) -> float:
    """A simple dominated-hypervolume estimate via Monte-Carlo over a 3D box.

    Hypervolume of a 3-objective frontier has no trivial closed form; we use a
    deterministic Monte-Carlo estimate against a shared reference point so that
    the SAME estimator is applied to every method (relative comparison is valid).
    """
    if not front:
        return 0.0
    arr = np.asarray(front, dtype=float)
    ref_arr = np.asarray(ref, dtype=float)
    lows = arr.min(axis=0)
    box_vol = float(np.prod(np.maximum(ref_arr - lows, 0.0)))
    if box_vol <= 0:
        return 0.0
    rng = np.random.default_rng(12345)
    n_samples = 20000
    samples = rng.uniform(lows, ref_arr, size=(n_samples, arr.shape[1]))
    # A sample is "dominated" by the frontier if some point is <= it on all axes.
    dominated = np.zeros(n_samples, dtype=bool)
    for p in arr:
        dominated |= np.all(samples >= p, axis=1)
    return float(dominated.mean() * box_vol)


# ---------------------------------------------------------------------------
# ALNS (adaptive large neighbourhood search) with a Pareto archive
# ---------------------------------------------------------------------------

@dataclass
class ALNSResult:
    method: str
    archive: list[tuple[tuple[float, float, float], list[int]]]
    iterations: int
    elapsed_sec: float
    best_cost: float | None
    n_evaluations: int
    operator_weights: dict[str, float] = field(default_factory=dict)


def run_alns(
    ev: LayoutEvaluator,
    *,
    iterations: int = 4000,
    seed: int = 0,
    n_scalarizations: int = 12,
) -> ALNSResult:
    """ALNS that maintains a Pareto archive over the 3 objectives.

    To drive search toward different frontier regions we rotate through a set of
    weighted-sum scalarisations of the (normalised) objectives, applying classic
    destroy (random / worst-demand removal) and repair (greedy reinsertion)
    operators with adaptive weights based on recent success.
    """
    rng = random.Random(seed)
    # Seed the archive from several hub-count starts to span the facility-count
    # tradeoff (fewer big facilities vs more small ones).
    current = greedy_feasible_assignment(ev, rng)
    cur_obj = ev.objectives(current)
    archive: list[tuple[tuple[float, float, float], list[int]]] = [(cur_obj, list(current))]
    n_eval = 1
    for nh in range(1, ev.max_facilities + 1):
        seed_sol = greedy_feasible_assignment(ev, rng, n_hubs=nh)
        so = ev.objectives(seed_sol)
        n_eval += 1
        if not any(dominates(o, so) for o, _ in archive):
            archive = [(o, s) for o, s in archive if not dominates(so, o)]
            if not any(o == so for o, _ in archive):
                archive.append((so, list(seed_sol)))
        # start the active search from the cheapest seed
        if so[0] < cur_obj[0]:
            current, cur_obj = list(seed_sol), so

    # Objective normalisation scales (rough, from the seed solution magnitudes).
    scales = [max(abs(v), 1.0) for v in cur_obj]

    # Adaptive operator scores.
    destroy_ops = ["random_remove", "worst_remove", "close_facility"]
    repair_ops = ["greedy_insert", "cheapest_feasible"]
    weights = {f"{d}|{r}": 1.0 for d in destroy_ops for r in repair_ops}
    scores = {k: 0.0 for k in weights}
    uses = {k: 0 for k in weights}

    def scalar(obj: tuple[float, float, float], w: np.ndarray) -> float:
        return float(sum((o / s) * wi for o, s, wi in zip(obj, scales, w)))

    start = time.time()
    weight_vectors = [np.array([rng.random() for _ in range(3)]) for _ in range(n_scalarizations)]
    weight_vectors = [w / w.sum() for w in weight_vectors]

    for it in range(iterations):
        w = weight_vectors[it % len(weight_vectors)]
        op_key = rng.choices(list(weights.keys()), weights=list(weights.values()))[0]
        destroy, repair = op_key.split("|")

        candidate = list(current)
        # --- destroy: pick demands to reassign ---
        k = max(1, ev.n_demand // 10)
        if destroy == "random_remove":
            victims = rng.sample(range(ev.n_demand), k)
        elif destroy == "close_facility":
            # close one open facility and reassign ALL its demand elsewhere
            open_choices_now = sorted(set(candidate))
            if len(open_choices_now) > 1:
                closed = rng.choice(open_choices_now)
                victims = [di for di in range(ev.n_demand) if candidate[di] == closed]
            else:
                victims = rng.sample(range(ev.n_demand), k)
        else:  # worst_remove: demands with highest unit cost under current choice
            unit_costs = []
            for di in range(ev.n_demand):
                ci = current[di]
                uc = ev._unit_transport[di, ci] + ev._unit_loss[di, ci] * ev.loss_price + ev._unit_carbon[di, ci] * ev.carbon_price
                unit_costs.append((uc, di))
            unit_costs.sort(reverse=True)
            victims = [di for _, di in unit_costs[:k]]

        # --- repair: reassign victims ---
        # For close_facility we must NOT reopen the closed facility, so restrict
        # the open pool to the remaining ones.
        if destroy == "close_facility":
            open_choices = sorted(set(candidate[di] for di in range(ev.n_demand) if di not in set(victims)))
        else:
            open_choices = sorted(set(candidate))
        for di in victims:
            d = ev.data.demand[ev.data.demand_ids[di]]
            if destroy == "close_facility":
                # must reassign within the surviving open facilities only
                pool = open_choices if open_choices else range(ev.n_choices)
            elif repair == "greedy_insert":
                # prefer already-open choices to avoid opening new facilities
                pool = open_choices if open_choices else range(ev.n_choices)
            else:
                pool = range(ev.n_choices)
            best_ci, best_val = None, None
            for ci in pool:
                j, t = ev.choice_list[ci]
                if t == "precool" and ev._travel_time[di, ci] > ev._precool_limit + 1e-9:
                    continue
                uc = ev._unit_transport[di, ci] + ev._unit_loss[di, ci] * ev.loss_price + ev._unit_carbon[di, ci] * ev.carbon_price
                if best_val is None or uc < best_val:
                    best_val, best_ci = uc, ci
            if best_ci is not None:
                candidate[di] = best_ci

        cand_obj = ev.objectives(candidate)
        n_eval += 1

        # --- acceptance: scalarised improvement OR archive non-domination ---
        improved = scalar(cand_obj, w) < scalar(cur_obj, w) - 1e-9
        nondominated = not any(dominates(o, cand_obj) for o, _ in archive)
        reward = 0.0
        if improved:
            current, cur_obj = candidate, cand_obj
            reward = 1.0
        if nondominated:
            # update archive: drop dominated, add candidate
            archive = [(o, s) for o, s in archive if not dominates(cand_obj, o)]
            if not any(o == cand_obj for o, _ in archive):
                archive.append((cand_obj, list(candidate)))
            reward = max(reward, 2.0)

        scores[op_key] += reward
        uses[op_key] += 1
        # periodic adaptive weight update
        if (it + 1) % 100 == 0:
            for kkey in weights:
                if uses[kkey] > 0:
                    weights[kkey] = 0.8 * weights[kkey] + 0.2 * (scores[kkey] / uses[kkey] + 0.01)
                scores[kkey] = 0.0
                uses[kkey] = 0

    elapsed = time.time() - start
    # Keep only feasible, non-dominated archive entries for reporting.
    feasible_archive = [
        (o, s) for o, s in archive if ev.evaluate(s)["feasible"]
    ]
    feasible_archive = pareto_filter([(o, s) for o, s in feasible_archive])
    best_cost = min((o[0] for o, _ in feasible_archive), default=None)
    return ALNSResult(
        method="alns",
        archive=feasible_archive,
        iterations=iterations,
        elapsed_sec=elapsed,
        best_cost=best_cost,
        n_evaluations=n_eval,
        operator_weights=dict(weights),
    )


# ---------------------------------------------------------------------------
# NSGA-III via pymoo
# ---------------------------------------------------------------------------

@dataclass
class NSGA3Result:
    method: str
    archive: list[tuple[tuple[float, float, float], list[int]]]
    n_gen: int
    pop_size: int
    elapsed_sec: float
    best_cost: float | None
    n_evaluations: int


def run_nsga3(
    ev: LayoutEvaluator,
    *,
    pop_size: int = 92,
    n_gen: int = 120,
    seed: int = 0,
) -> NSGA3Result:
    """Run NSGA-III on the layout problem via pymoo."""
    from pymoo.core.problem import Problem
    from pymoo.algorithms.moo.nsga3 import NSGA3
    from pymoo.core.sampling import Sampling
    from pymoo.operators.crossover.sbx import SBX
    from pymoo.operators.mutation.pm import PM
    from pymoo.operators.repair.rounding import RoundingRepair
    from pymoo.util.ref_dirs import get_reference_directions
    from pymoo.optimize import minimize

    n_var = ev.n_demand
    n_choices = ev.n_choices

    class FeasibleBiasedSampling(Sampling):
        """Seed population with greedy feasible solutions (varying hub counts)
        plus some random genotypes for diversity."""

        def _do(self, problem, n_samples, **kwargs):
            X = np.zeros((n_samples, n_var), dtype=float)
            rng_local = random.Random(seed)
            for k in range(n_samples):
                if k < int(n_samples * 0.7):
                    nh = 1 + (k % ev.max_facilities)
                    a = greedy_feasible_assignment(ev, rng_local, n_hubs=nh)
                else:
                    a = [rng_local.randrange(n_choices) for _ in range(n_var)]
                X[k, :] = a
            return X

    class LayoutProblem(Problem):
        def __init__(self):
            super().__init__(
                n_var=n_var, n_obj=3, n_constr=1,
                xl=0, xu=n_choices - 1, vtype=int,
            )

        def _evaluate(self, X, out, *args, **kwargs):
            F = np.zeros((X.shape[0], 3))
            G = np.zeros((X.shape[0], 1))
            for k in range(X.shape[0]):
                a = [int(round(v)) % n_choices for v in X[k]]
                r = ev.evaluate(a)
                F[k, 0] = r["cost"]
                F[k, 1] = r["loss_ton"]
                F[k, 2] = r["carbon_ton"]
                G[k, 0] = r["constraint_violation"]  # <= 0 feasible
            out["F"] = F
            out["G"] = G

    ref_dirs = get_reference_directions("das-dennis", 3, n_partitions=12)
    algorithm = NSGA3(
        pop_size=pop_size,
        ref_dirs=ref_dirs,
        sampling=FeasibleBiasedSampling(),
        crossover=SBX(prob=0.9, eta=15, repair=RoundingRepair(), vtype=float),
        mutation=PM(prob=2.0 / n_var, eta=20, repair=RoundingRepair(), vtype=float),
        eliminate_duplicates=True,
    )
    problem = LayoutProblem()
    start = time.time()
    res = minimize(problem, algorithm, ("n_gen", n_gen), seed=seed, verbose=False)
    elapsed = time.time() - start

    archive: list[tuple[tuple[float, float, float], list[int]]] = []
    if res.X is not None:
        X = np.atleast_2d(res.X)
        for row in X:
            a = [int(round(v)) % n_choices for v in row]
            r = ev.evaluate(a)
            if r["feasible"]:
                archive.append(((r["cost"], r["loss_ton"], r["carbon_ton"]), a))
    archive = pareto_filter(archive)
    best_cost = min((o[0] for o, _ in archive), default=None)
    n_eval = int(getattr(res, "algorithm", algorithm).evaluator.n_eval) if hasattr(res, "algorithm") else pop_size * n_gen
    return NSGA3Result(
        method="nsga3",
        archive=archive,
        n_gen=n_gen,
        pop_size=pop_size,
        elapsed_sec=elapsed,
        best_cost=best_cost,
        n_evaluations=n_eval,
    )
