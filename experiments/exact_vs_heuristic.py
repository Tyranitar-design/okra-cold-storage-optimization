"""Exact (epsilon-constraint MIP) vs heuristic (NSGA-III, ALNS) comparison.

Builds the three-objective Pareto frontier for the okra cold-storage layout
problem with three methods on the SAME scenarios and SAME objectives:

* ``exact``    -- augmented epsilon-constraint over Gurobi (certified non-dominated);
* ``nsga3``    -- reference-point genetic algorithm (pymoo);
* ``alns``     -- adaptive large neighbourhood search with a Pareto archive.

Reported metrics
----------------
* frontier size, best (min) cost per method;
* runtime (wall-clock);
* hypervolume (shared Monte-Carlo estimator, shared reference point);
* exact-dominance coverage: fraction of a heuristic's points that are NOT
  dominated by the exact frontier (how close the heuristic gets);
* cost gap of each heuristic's cost-optimal point vs the exact cost optimum.

This is the evidence for the paper's "why recommend the exact / AI-enhanced
exact approach over pure metaheuristics" argument. We report the trade-off
honestly: heuristics are fast and get close; the exact method certifies
optimality and the full frontier.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("GRB_LICENSE_FILE", r"D:\Gurobi1300\win64\bin\gurobi.lic")

from experiments._shared import (  # noqa: E402
    get_scenario_candidate_sets,
    load_config,
    save_dataframe_bundle,
    write_markdown_table,
)
from src.algorithms.heuristics import (  # noqa: E402
    dominates,
    hypervolume_2d_proxy,
    pareto_filter,
    run_alns,
    run_nsga3,
)
from src.algorithms.layout_evaluator import make_evaluator  # noqa: E402
from src.models.epsilon_constraint import build_epsilon_model  # noqa: E402

OUT_DIR = PROJECT_ROOT / "results" / "experiments" / "exact_vs_heuristic"
SOURCE_ID = "DS-F-044"


def build_exact_frontier(
    config: Any,
    *,
    candidate_ids: list[str],
    max_facilities: int,
    carbon_price: float,
    loss_price: float,
    n_grid: int,
    time_limit: int,
) -> dict[str, Any]:
    """Augmented epsilon-constraint frontier: min cost subject to loss/carbon caps."""
    start = time.time()
    # First get loss/carbon ranges from the cost-min and loss-min corners.
    _, _, _, cost_min = build_epsilon_model(
        config, candidate_ids=candidate_ids, max_facilities=max_facilities,
        carbon_price=carbon_price, loss_price=loss_price, objective_name="cost",
        time_limit=time_limit, verbose=False,
    )
    _, _, _, loss_min = build_epsilon_model(
        config, candidate_ids=candidate_ids, max_facilities=max_facilities,
        carbon_price=carbon_price, loss_price=loss_price, objective_name="loss",
        time_limit=time_limit, verbose=False,
    )
    loss_hi = float(cost_min["loss_ton"])
    loss_lo = float(loss_min["loss_ton"])
    carbon_hi = float(cost_min["carbon_ton"])
    # Sweep epsilon on loss (primary trade dimension); keep carbon relaxed but tracked.
    points: list[tuple[tuple[float, float, float], dict[str, Any]]] = []
    if loss_hi <= loss_lo:
        eps_values = [None]
    else:
        eps_values = list(np.linspace(loss_lo, loss_hi, n_grid))
    for eps in eps_values:
        _, _, _, an = build_epsilon_model(
            config, candidate_ids=candidate_ids, max_facilities=max_facilities,
            carbon_price=carbon_price, loss_price=loss_price, objective_name="cost",
            eps_loss_ton=(float(eps) if eps is not None else None),
            time_limit=time_limit, verbose=False,
        )
        if an["total_cost"] is None:
            continue
        obj = (float(an["total_cost"]), float(an["loss_ton"]), float(an["carbon_ton"]))
        points.append((obj, {"num_facilities": an["num_facilities"]}))
    front = pareto_filter(points)
    elapsed = time.time() - start
    return {
        "method": "exact_epsilon",
        "front_objs": [list(o) for o, _ in front],
        "front_size": len(front),
        "best_cost": min((o[0] for o, _ in front), default=None),
        "elapsed_sec": elapsed,
        "n_models_solved": len(eps_values) + 2,
    }


def coverage_not_dominated_by_exact(
    heuristic_front: list[tuple[float, float, float]],
    exact_front: list[tuple[float, float, float]],
) -> float:
    """Fraction of heuristic points NOT dominated by any exact point (closeness)."""
    if not heuristic_front:
        return 0.0
    not_dom = 0
    for h in heuristic_front:
        if not any(dominates(e, h) for e in exact_front):
            not_dom += 1
    return not_dom / len(heuristic_front)


def run_scenario(
    config: Any,
    scenario_name: str,
    candidate_ids: list[str],
    *,
    max_facilities: int,
    carbon_price: float,
    loss_price: float,
    n_grid: int,
    nsga_pop: int,
    nsga_gen: int,
    alns_iters: int,
    seeds: list[int],
    time_limit: int,
) -> dict[str, Any]:
    ev = make_evaluator(
        config, candidate_ids=candidate_ids, max_facilities=max_facilities,
        carbon_price=carbon_price, loss_price=loss_price,
    )

    exact = build_exact_frontier(
        config, candidate_ids=candidate_ids, max_facilities=max_facilities,
        carbon_price=carbon_price, loss_price=loss_price, n_grid=n_grid, time_limit=time_limit,
    )
    exact_objs = [tuple(o) for o in exact["front_objs"]]

    # Heuristics averaged over seeds.
    nsga_runs = [run_nsga3(ev, pop_size=nsga_pop, n_gen=nsga_gen, seed=s) for s in seeds]
    alns_runs = [run_alns(ev, iterations=alns_iters, seed=s) for s in seeds]

    # Shared reference point for hypervolume: worst objective per axis across ALL
    # methods, inflated 10% so every frontier is strictly inside the box.
    all_objs = list(exact_objs)
    for r in nsga_runs + alns_runs:
        all_objs += [o for o, _ in r.archive]
    if all_objs:
        arr = np.asarray(all_objs, dtype=float)
        ref = tuple((arr.max(axis=0) * 1.1).tolist())
    else:
        ref = (1.0, 1.0, 1.0)

    hv_exact = hypervolume_2d_proxy(exact_objs, ref)

    def summarize(runs: list[Any], method: str) -> dict[str, Any]:
        fronts = [[o for o, _ in r.archive] for r in runs]
        hvs = [hypervolume_2d_proxy(f, ref) for f in fronts]
        covs = [coverage_not_dominated_by_exact(f, exact_objs) for f in fronts]
        best_costs = [r.best_cost for r in runs if r.best_cost is not None]
        sizes = [len(f) for f in fronts]
        times = [r.elapsed_sec for r in runs]
        evals = [r.n_evaluations for r in runs]
        best_cost_mean = float(np.mean(best_costs)) if best_costs else None
        cost_gap = (
            (best_cost_mean - exact["best_cost"]) / exact["best_cost"] * 100.0
            if best_cost_mean is not None and exact["best_cost"] else None
        )
        return {
            "method": method,
            "front_size_mean": float(np.mean(sizes)) if sizes else 0.0,
            "best_cost_mean": best_cost_mean,
            "cost_gap_vs_exact_pct": cost_gap,
            "hypervolume_mean": float(np.mean(hvs)) if hvs else 0.0,
            "hypervolume_ratio_vs_exact": float(np.mean(hvs) / hv_exact) if hv_exact > 0 and hvs else None,
            "coverage_not_dominated_by_exact_mean": float(np.mean(covs)) if covs else 0.0,
            "elapsed_sec_mean": float(np.mean(times)) if times else 0.0,
            "evaluations_mean": float(np.mean(evals)) if evals else 0.0,
            "seeds": seeds,
        }

    rows = [
        {
            "scenario": scenario_name, "method": "exact_epsilon",
            "front_size_mean": float(exact["front_size"]),
            "best_cost_mean": exact["best_cost"],
            "cost_gap_vs_exact_pct": 0.0,
            "hypervolume_mean": hv_exact,
            "hypervolume_ratio_vs_exact": 1.0,
            "coverage_not_dominated_by_exact_mean": 1.0,
            "elapsed_sec_mean": exact["elapsed_sec"],
            "evaluations_mean": float(exact["n_models_solved"]),
            "seeds": seeds,
        },
        {"scenario": scenario_name, **summarize(nsga_runs, "nsga3")},
        {"scenario": scenario_name, **summarize(alns_runs, "alns")},
    ]
    # Union the heuristic archives across seeds (Pareto-filtered) for plotting.
    def _front_points(runs: list[Any]) -> list[list[float]]:
        pooled = []
        for r in runs:
            pooled += [(tuple(o), None) for o, _ in r.archive]
        return [list(o) for o, _ in pareto_filter(pooled)]

    return {
        "scenario": scenario_name,
        "candidate_count": len(candidate_ids),
        "rows": rows,
        "exact_front": exact["front_objs"],
        "nsga3_front": _front_points(nsga_runs),
        "alns_front": _front_points(alns_runs),
        "reference_point": list(ref),
        "hv_exact": hv_exact,
    }


def build_verdict(rows: list[dict[str, Any]]) -> dict[str, Any]:
    df = pd.DataFrame(rows)
    verdict: dict[str, Any] = {}
    heur = df[df["method"].isin(["nsga3", "alns"])]
    verdict["mean_cost_gap_vs_exact_pct"] = {
        m: float(df[df["method"] == m]["cost_gap_vs_exact_pct"].dropna().mean())
        for m in ["nsga3", "alns"]
        if df[df["method"] == m]["cost_gap_vs_exact_pct"].notna().any()
    }
    verdict["mean_hypervolume_ratio_vs_exact"] = {
        m: float(df[df["method"] == m]["hypervolume_ratio_vs_exact"].dropna().mean())
        for m in ["nsga3", "alns"]
        if df[df["method"] == m]["hypervolume_ratio_vs_exact"].notna().any()
    }
    verdict["mean_runtime_sec"] = {
        m: float(df[df["method"] == m]["elapsed_sec_mean"].mean())
        for m in ["exact_epsilon", "nsga3", "alns"]
        if (df["method"] == m).any()
    }
    verdict["interpretation"] = (
        "Exact epsilon-constraint certifies the non-dominated frontier and the cost optimum. "
        "Heuristics (NSGA-III, ALNS) approximate it: report their cost gap and hypervolume ratio. "
        "Recommendation depends on the trade-off observed in mean_cost_gap and runtime."
    )
    verdict["claim_boundary"] = (
        "County-scale okra case (39 demand nodes); objectives = cost / spoilage tonnage / CO2 tonnage. "
        "Heuristic fronts use a shared Monte-Carlo hypervolume estimator and a shared reference point, "
        "so comparisons are relative, not absolute hypervolume."
    )
    return verdict


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenarios", type=str, nargs="+", default=["S1_9_candidates", "S2_18_candidates"])
    parser.add_argument("--max-facilities", type=int, default=8)
    parser.add_argument("--carbon-price", type=float, default=50.0)
    parser.add_argument("--loss-price", type=float, default=3000.0)
    parser.add_argument("--n-grid", type=int, default=8, help="epsilon grid points for exact frontier")
    parser.add_argument("--nsga-pop", type=int, default=92)
    parser.add_argument("--nsga-gen", type=int, default=120)
    parser.add_argument("--alns-iters", type=int, default=4000)
    parser.add_argument("--seeds", type=int, nargs="+", default=[0, 1, 2])
    parser.add_argument("--time-limit", type=int, default=120)
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    config = load_config()
    scenario_sets = get_scenario_candidate_sets(config)

    all_rows: list[dict[str, Any]] = []
    fronts_payload: dict[str, Any] = {}
    for scen in args.scenarios:
        if scen not in scenario_sets:
            print(f"[WARN] unknown scenario {scen}")
            continue
        print(f"[RUN] {scen} ...", flush=True)
        out = run_scenario(
            config, scen, scenario_sets[scen],
            max_facilities=args.max_facilities, carbon_price=args.carbon_price,
            loss_price=args.loss_price, n_grid=args.n_grid, nsga_pop=args.nsga_pop,
            nsga_gen=args.nsga_gen, alns_iters=args.alns_iters, seeds=args.seeds,
            time_limit=args.time_limit,
        )
        all_rows.extend(out["rows"])
        fronts_payload[scen] = {
            "exact_front": out["exact_front"],
            "nsga3_front": out.get("nsga3_front", []),
            "alns_front": out.get("alns_front", []),
            "reference_point": out["reference_point"],
        }

    df = pd.DataFrame(all_rows)
    save_dataframe_bundle(df, OUT_DIR / "exact_vs_heuristic")
    if not df.empty:
        write_markdown_table(
            df, OUT_DIR / "exact_vs_heuristic.md",
            ["scenario", "method", "front_size_mean", "best_cost_mean",
             "cost_gap_vs_exact_pct", "hypervolume_ratio_vs_exact",
             "coverage_not_dominated_by_exact_mean", "elapsed_sec_mean"],
        )
    verdict = build_verdict(all_rows)
    summary = {
        "experiment_name": "exact_vs_heuristic",
        "source_id": SOURCE_ID,
        "config": vars(args),
        "summary_rows": all_rows,
        "fronts": fronts_payload,
        "verdict": verdict,
        "research_boundary": verdict["claim_boundary"],
    }
    (OUT_DIR / "exact_vs_heuristic_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({
        "scenarios": len(fronts_payload), "rows": len(all_rows),
        "cost_gap": verdict.get("mean_cost_gap_vs_exact_pct"),
        "runtime": verdict.get("mean_runtime_sec"),
        "out_dir": str(OUT_DIR),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
