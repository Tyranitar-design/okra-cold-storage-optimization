"""Tests for the layout evaluator and NSGA-III / ALNS heuristic baselines."""

from __future__ import annotations

import os
import random

os.environ.setdefault("GRB_LICENSE_FILE", r"D:\Gurobi1300\win64\bin\gurobi.lic")

from experiments._shared import get_scenario_candidate_sets, load_config
from src.algorithms.layout_evaluator import OBJECTIVE_NAMES, make_evaluator
from src.algorithms.heuristics import (
    dominates,
    greedy_feasible_assignment,
    pareto_filter,
    run_alns,
    run_nsga3,
)


def _small_evaluator():
    config = load_config()
    cand = get_scenario_candidate_sets(config)["S1_9_candidates"]
    return make_evaluator(config, candidate_ids=cand, max_facilities=8)


def test_evaluator_objectives_and_feasibility():
    ev = _small_evaluator()
    assert ev.n_demand == 39
    assert ev.n_choices == len(ev.choice_list) > 0
    a = greedy_feasible_assignment(ev, random.Random(0))
    r = ev.evaluate(a)
    assert set(OBJECTIVE_NAMES) <= set(r)
    assert r["feasible"] is True
    assert r["num_facilities"] <= ev.max_facilities
    assert r["cost"] > 0
    # objectives() returns the same cost when feasible (no penalty bump)
    objs = ev.objectives(a)
    assert abs(objs[0] - r["cost"]) < 1e-6


def test_evaluator_penalises_infeasible():
    ev = _small_evaluator()
    # Force everyone onto a single choice -> capacity violation -> penalty.
    a = [0] * ev.n_demand
    objs = ev.objectives(a)
    feasible_objs = ev.objectives(greedy_feasible_assignment(ev, random.Random(1)))
    assert objs[0] > feasible_objs[0]  # infeasible is strictly worse on cost


def test_dominance_and_pareto_filter():
    assert dominates((1.0, 1.0, 1.0), (2.0, 2.0, 2.0))
    assert not dominates((1.0, 2.0, 1.0), (2.0, 1.0, 1.0))
    pts = [((1.0, 1.0, 1.0), "a"), ((2.0, 2.0, 2.0), "b"), ((1.0, 2.0, 0.5), "c")]
    front = pareto_filter(pts)
    payloads = {p for _, p in front}
    assert "b" not in payloads  # dominated by a
    assert "a" in payloads and "c" in payloads


def test_alns_produces_feasible_pareto_front():
    ev = _small_evaluator()
    res = run_alns(ev, iterations=1500, seed=0)
    assert res.method == "alns"
    assert len(res.archive) >= 1
    # every archived solution must be feasible and within facility budget
    for obj, sol in res.archive:
        r = ev.evaluate(sol)
        assert r["feasible"] is True
        assert r["num_facilities"] <= ev.max_facilities
    assert res.best_cost is not None and res.best_cost > 0


def test_nsga3_produces_feasible_pareto_front():
    ev = _small_evaluator()
    res = run_nsga3(ev, pop_size=92, n_gen=40, seed=0)
    assert res.method == "nsga3"
    # feasible-biased sampling should yield at least one feasible non-dominated point
    assert len(res.archive) >= 1
    for obj, sol in res.archive:
        assert ev.evaluate(sol)["feasible"] is True
    assert res.best_cost is not None and res.best_cost > 0
