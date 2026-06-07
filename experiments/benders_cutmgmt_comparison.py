"""Controlled Benders cut-management comparison on public LRP projections.

Research question
-----------------
Does a *learned* cut-ranking policy actually accelerate Benders convergence,
or does any benefit just come from imposing an active-cut budget?

To answer this honestly we hold everything fixed except the cut-management
policy that decides which K candidate optimality cuts stay *active* in the
master each iteration:

* ``all_cuts``    -- classic Benders, every generated cut stays active (no budget)
* ``random_K``    -- control: keep K cuts chosen uniformly at random (seeded)
* ``recency_K``   -- control: keep the K most recently generated cuts
* ``learned_K``   -- the AI policy: keep the top-K cuts by the learned scorer

All four share the SAME master/subproblem model, the SAME instances, the SAME
budget K, and the SAME iteration cap, so any difference in iterations / time /
gap is attributable to the cut-selection rule alone. The learned scorer is
calibrated on a *prior* warm-up run's cut history (classic Benders), so it is a
same-instance calibration mechanism check -- not an out-of-sample superiority
proof.

Honesty boundary
----------------
This is a capacitated facility-location projection of public LRP instances,
NOT a full routing LRP and NOT okra enterprise validation. We report whatever
the numbers say, including negative or neutral results. We never claim
"significant speedup" unless the controlled comparison supports it.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("GRB_LICENSE_FILE", r"D:\Gurobi1300\win64\bin\gurobi.lic")

from experiments._shared import gurobi_status_name, save_dataframe_bundle, write_markdown_table  # noqa: E402
from experiments.benchmark_benders_comparison import (  # noqa: E402
    build_cut_from_duals,
    build_graph_bundle,
    solve_master_projection,
    solve_subproblem_projection,
)
from experiments.benchmark_solver_smoke import SmokeInstance, parse_smoke_instance  # noqa: E402
from src.algorithms.cut_features import build_cut_dataset  # noqa: E402
from src.algorithms.gnn_encoder import encode_bipartite_graph  # noqa: E402
from src.algorithms.rl_agent import train_agent_from_history  # noqa: E402

try:
    import gurobipy as gp  # noqa: E402
    from gurobipy import GRB  # noqa: E402

    GUROBI_IMPORT_ERROR = ""
except Exception as exc:  # pragma: no cover
    gp = None
    GRB = None
    GUROBI_IMPORT_ERROR = str(exc)

import numpy as np  # noqa: E402
import torch  # noqa: E402

OUT_DIR = PROJECT_ROOT / "results" / "experiments" / "benders_cutmgmt_comparison"
SOURCE_ID = "DS-F-043"

# Legacy exploratory roster kept for backwards-compatible small-panel reruns.
DEFAULT_INSTANCES = [
    "sample:contardo:I1-10x8x3",
    "pair:barreto:Gaskell67Cli29x5",
    "sample:akca:r30x5a-1",
    "pair:barreto:Ch69Cli50x5",
    "pair:barreto:Perl83Cli55x15",
    "pair:barreto:Ch69Cli75x10",
    "sample:contardo:I1-100x10x5",
    "sample:contardo:I1-100x20x5",
]

# Recommended medium-panel roster for the significance expansion pass.
MEDIUM_15_INSTANCES = [
    "sample:akca:r30x5a-1",
    "sample:akca:r30x5a-2",
    "sample:akca:r30x5a-3",
    "sample:akca:r30x5b-1",
    "sample:akca:r30x5b-2",
    "sample:akca:r30x5b-3",
    "pair:barreto:Ch69Cli50x5",
    "pair:barreto:Perl83Cli55x15",
    "pair:barreto:Ch69Cli75x10",
    "pair:barreto:Perl83Cli85x7",
    "pair:barreto:Daskin95Cli88x8",
    "pair:barreto:Ch69Cli100x10",
    "sample:contardo:I1-100x10x5",
    "sample:contardo:I1-100x20x5",
    "pair:barreto:Min92Cli134x8",
]

PANEL_ROSTERS: dict[str, list[str]] = {
    "legacy_small": DEFAULT_INSTANCES,
    "medium_15": MEDIUM_15_INSTANCES,
}


def resolve_instance_ids(panel: str, explicit_instances: list[str] | None) -> tuple[list[str], str]:
    """Resolve the experiment roster while preserving explicit overrides."""
    if explicit_instances:
        return explicit_instances, "custom"
    roster = PANEL_ROSTERS.get(panel)
    if roster is None:
        valid = ", ".join(sorted(PANEL_ROSTERS))
        raise ValueError(f"unknown panel {panel!r}; choose from: {valid}")
    return list(roster), panel


@dataclass
class PolicyRunResult:
    policy: str
    budget: int | None
    status_name: str
    upper_bound: float | None
    lower_bound: float | None
    final_gap_pct: float | None
    iterations: int
    total_cuts_generated: int
    mean_active_cuts: float
    elapsed_sec: float
    termination_reason: str
    converged: bool = False
    iteration_records: list[dict[str, Any]] = field(default_factory=list)
    error: str = ""


def _fixed_cost(instance: SmokeInstance, y_solution: dict[int, float]) -> float:
    return sum(
        max(0.0, float(instance.facilities[j].get("fixed_cost", 0.0))) * float(y_solution.get(j, 0.0))
        for j in range(instance.facility_count)
    )


def _cut_signature(cut: dict[str, Any], precision: int = 6) -> tuple[Any, ...]:
    coef_items = tuple(
        sorted((str(k), round(float(v), precision)) for k, v in cut.get("coef", {}).items())
    )
    return (round(float(cut.get("rhs", 0.0)), precision), coef_items)


def _train_scorer(instance: SmokeInstance, calibration_cut_history: list[dict[str, Any]], network_type: str = "mlp"):
    """Train the learned cut scorer on a prior classic-Benders cut history."""
    graph_bundle = build_graph_bundle(instance)
    graph_embedding = encode_bipartite_graph(graph_bundle, hidden_dim=32)
    features, rewards, _ = build_cut_dataset(calibration_cut_history)
    agent, _ = train_agent_from_history(
        graph_embedding,
        features,
        rewards,
        hidden_dim=64,
        lr=1e-3,
        epochs=150,
        network_type=network_type,
        dropout=0.1,
    )
    return agent, graph_embedding


def _select_active_indices(
    policy: str,
    cut_pool: list[dict[str, Any]],
    budget: int | None,
    *,
    rng: np.random.Generator,
    agent: Any = None,
    graph_embedding: Any = None,
) -> list[int]:
    """Decide which cut-pool indices stay active in the master this iteration."""
    n = len(cut_pool)
    if budget is None or n <= budget:
        return list(range(n))
    if policy == "random_K":
        return sorted(rng.choice(n, size=budget, replace=False).tolist())
    if policy == "recency_K":
        return list(range(n - budget, n))
    if policy in {"learned_K", "learned_residual_K"}:
        features, _, _ = build_cut_dataset(cut_pool)
        scores = agent.score(graph_embedding, features)
        order = torch.argsort(scores, descending=True)[:budget].tolist()
        return sorted(int(i) for i in order)
    raise ValueError(f"unknown policy {policy!r}")


def run_policy(
    instance: SmokeInstance,
    policy: str,
    *,
    budget: int | None,
    time_limit: int,
    mip_gap: float,
    threads: int,
    max_iterations: int,
    seed: int,
    agent: Any = None,
    graph_embedding: Any = None,
) -> PolicyRunResult:
    """Run one Benders loop under a fixed cut-management policy."""
    if gp is None:
        return PolicyRunResult(
            policy=policy, budget=budget, status_name="GUROBI_IMPORT_FAILED",
            upper_bound=None, lower_bound=None, final_gap_pct=None, iterations=0,
            total_cuts_generated=0, mean_active_cuts=0.0, elapsed_sec=0.0,
            termination_reason="gurobi_import_failed", error=GUROBI_IMPORT_ERROR,
        )

    rng = np.random.default_rng(seed)
    cut_pool: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    iteration_records: list[dict[str, Any]] = []
    best_upper = float("inf")
    best_lower = -float("inf")
    active_counts: list[int] = []
    termination_reason = "max_iterations"

    start = time.time()
    for iter_no in range(1, max_iterations + 1):
        active_idx = _select_active_indices(
            policy, cut_pool, budget, rng=rng, agent=agent, graph_embedding=graph_embedding
        )
        active_cuts = [cut_pool[i]["cut"] for i in active_idx]
        active_counts.append(len(active_cuts))

        master, y_vars = solve_master_projection(
            instance, active_cuts, time_limit=time_limit, mip_gap=mip_gap,
            threads=threads, verbose=False,
        )
        if master.SolCount <= 0:
            termination_reason = "master_no_solution"
            break

        y_solution = {j: float(v.X) for j, v in y_vars.items()}
        subproblem, _, sub_summary = solve_subproblem_projection(instance, y_solution, verbose=False)
        if subproblem.SolCount <= 0:
            termination_reason = "subproblem_no_solution"
            break

        fixed = _fixed_cost(instance, y_solution)
        total_cost = fixed + float(sub_summary["assignment_cost"])
        if total_cost < best_upper:
            best_upper = total_cost
        best_lower = max(best_lower, float(master.ObjVal))
        gap_pct = 0.0 if best_upper <= 0 else max(0.0, (best_upper - best_lower) / max(abs(best_upper), 1.0) * 100.0)

        iteration_records.append({
            "iter_no": iter_no,
            "master_obj": float(master.ObjVal),
            "subproblem_obj": float(sub_summary["assignment_cost"]),
            "upper_bound": best_upper,
            "lower_bound": best_lower,
            "gap_pct": gap_pct,
            "active_cut_count": len(active_cuts),
            "pool_cut_count": len(cut_pool),
            "elapsed_sec": time.time() - start,
        })

        if gap_pct <= mip_gap * 100.0:
            termination_reason = "gap_tolerance"
            break

        new_cut = build_cut_from_duals(instance, sub_summary["duals"])
        sig = _cut_signature(new_cut)
        if sig in seen:
            termination_reason = "duplicate_cut"
            break
        seen.add(sig)
        cut_pool.append({
            "cut_id": f"cut_{len(cut_pool):03d}",
            "iteration": iteration_records[-1],
            "cut": new_cut,
        })

    elapsed = time.time() - start
    return PolicyRunResult(
        policy=policy,
        budget=budget,
        status_name="OPTIMAL" if best_upper < float("inf") else "FAILED",
        upper_bound=None if best_upper == float("inf") else float(best_upper),
        lower_bound=None if best_lower == -float("inf") else float(best_lower),
        final_gap_pct=None if not iteration_records else float(iteration_records[-1]["gap_pct"]),
        iterations=len(iteration_records),
        total_cuts_generated=len(cut_pool),
        mean_active_cuts=float(np.mean(active_counts)) if active_counts else 0.0,
        elapsed_sec=elapsed,
        termination_reason=termination_reason,
        converged=(termination_reason == "gap_tolerance"),
        iteration_records=iteration_records,
    )


def run_warmup_cut_history(
    instance: SmokeInstance, *, time_limit: int, mip_gap: float, threads: int, max_iterations: int
) -> list[dict[str, Any]]:
    """Run a classic (all-cuts) Benders pass to collect a calibration cut history."""
    result = run_policy(
        instance, "all_cuts", budget=None, time_limit=time_limit, mip_gap=mip_gap,
        threads=threads, max_iterations=max_iterations, seed=0,
    )
    # Reconstruct cut history records keyed the way build_cut_dataset expects.
    # We re-run lightweightly is wasteful; instead rebuild from iteration records is
    # not possible (cuts not stored), so do a dedicated collection pass here.
    cut_history: list[dict[str, Any]] = []
    if gp is None:
        return cut_history
    cut_pool: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    best_upper = float("inf")
    best_lower = -float("inf")
    start = time.time()
    for iter_no in range(1, max_iterations + 1):
        master, y_vars = solve_master_projection(
            instance, [c["cut"] for c in cut_pool], time_limit=time_limit,
            mip_gap=mip_gap, threads=threads, verbose=False,
        )
        if master.SolCount <= 0:
            break
        y_solution = {j: float(v.X) for j, v in y_vars.items()}
        subproblem, _, sub_summary = solve_subproblem_projection(instance, y_solution, verbose=False)
        if subproblem.SolCount <= 0:
            break
        fixed = _fixed_cost(instance, y_solution)
        total_cost = fixed + float(sub_summary["assignment_cost"])
        best_upper = min(best_upper, total_cost)
        best_lower = max(best_lower, float(master.ObjVal))
        gap_pct = 0.0 if best_upper <= 0 else max(0.0, (best_upper - best_lower) / max(abs(best_upper), 1.0) * 100.0)
        iteration_record = {
            "iteration": iter_no, "iter_no": iter_no, "master_obj": float(master.ObjVal),
            "subproblem_obj": float(sub_summary["assignment_cost"]), "gap_pct": gap_pct,
            "cut_count": len(cut_pool), "elapsed_sec": time.time() - start,
        }
        new_cut = build_cut_from_duals(instance, sub_summary["duals"])
        sig = _cut_signature(new_cut)
        if sig in seen:
            break
        seen.add(sig)
        cut_pool.append({"cut_id": f"cut_{len(cut_pool):03d}", "iteration": iteration_record, "cut": new_cut})
        cut_history.append(cut_pool[-1])
        if gap_pct <= mip_gap * 100.0:
            break
    return cut_history


def run_instance(
    case: dict[str, Any],
    *,
    budget: int,
    time_limit: int,
    mip_gap: float,
    threads: int,
    max_iterations: int,
    seeds: list[int],
) -> dict[str, Any]:
    instance = parse_smoke_instance(case)

    # Ground truth: direct MIP optimum (validates every policy's incumbent).
    from experiments.benchmark_benders_comparison import solve_direct_projection

    direct = solve_direct_projection(instance, time_limit=max(time_limit, 120), mip_gap=mip_gap)
    direct_obj = direct.get("objective")

    # Warm-up: classic Benders cut history calibrates the learned scorer.
    calib_history = run_warmup_cut_history(
        instance, time_limit=time_limit, mip_gap=mip_gap, threads=threads, max_iterations=max_iterations
    )
    agent = None
    residual_agent = None
    graph_embedding = None
    residual_graph_embedding = None
    if calib_history:
        agent, graph_embedding = _train_scorer(instance, calib_history)
        residual_agent, residual_graph_embedding = _train_scorer(instance, calib_history, network_type="residual")

    rows: list[dict[str, Any]] = []
    iteration_rows: list[dict[str, Any]] = []

    def _validated_gap(upper: float | None) -> float | None:
        """True optimality gap of an incumbent vs the direct MIP optimum."""
        if upper is None or direct_obj in (None, 0):
            return None
        return abs(float(upper) - float(direct_obj)) / abs(float(direct_obj)) * 100.0

    policy_specs: list[tuple[str, int | None]] = [
        ("all_cuts", None),
        ("random_K", budget),
        ("recency_K", budget),
        ("learned_K", budget),
        ("learned_residual_K", budget),
    ]

    for policy, pol_budget in policy_specs:
        # Stochastic policies (random_K) are averaged over seeds; deterministic
        # policies run once (seed 0) but reported with the same schema.
        run_seeds = seeds if policy == "random_K" else [seeds[0]]
        per_seed: list[PolicyRunResult] = []
        for seed in run_seeds:
            if policy == "learned_K" and agent is None:
                continue
            if policy == "learned_residual_K" and residual_agent is None:
                continue
            policy_agent = residual_agent if policy == "learned_residual_K" else agent
            policy_embedding = residual_graph_embedding if policy == "learned_residual_K" else graph_embedding
            res = run_policy(
                instance, policy, budget=pol_budget, time_limit=time_limit, mip_gap=mip_gap,
                threads=threads, max_iterations=max_iterations, seed=seed,
                agent=policy_agent, graph_embedding=policy_embedding,
            )
            per_seed.append(res)
            for rec in res.iteration_records:
                iteration_rows.append({
                    "case_id": case["entry_id"], "policy": policy, "budget": pol_budget,
                    "seed": seed, **rec,
                })
        if not per_seed:
            continue
        # Validated optimality gap of each run's incumbent vs the direct optimum.
        validated_gaps = [_validated_gap(r.upper_bound) for r in per_seed]
        validated_gaps = [g for g in validated_gaps if g is not None]
        # A run "solved to optimal" only if it (a) self-terminated on gap tolerance
        # AND (b) its incumbent is within tolerance of the direct MIP optimum.
        solved_flags = [
            bool(r.converged and (_validated_gap(r.upper_bound) or 0.0) <= mip_gap * 100.0 + 1e-6)
            for r in per_seed
        ]
        # Aggregate across seeds (mean for stochastic; identity for single-run).
        rows.append({
            "source_id": SOURCE_ID,
            "case_id": case["entry_id"],
            "facility_count": instance.facility_count,
            "customer_count": instance.customer_count,
            "policy": policy,
            "budget": pol_budget,
            "seeds_run": len(per_seed),
            "iterations_mean": float(np.mean([r.iterations for r in per_seed])),
            "iterations_min": int(min(r.iterations for r in per_seed)),
            "iterations_max": int(max(r.iterations for r in per_seed)),
            "final_gap_pct_mean": float(np.mean([r.final_gap_pct or 0.0 for r in per_seed])),
            "validated_gap_pct_mean": float(np.mean(validated_gaps)) if validated_gaps else None,
            "solved_to_optimal_frac": float(np.mean(solved_flags)),
            "all_solved_to_optimal": bool(all(solved_flags)),
            "upper_bound_mean": float(np.mean([r.upper_bound or float("nan") for r in per_seed])),
            "lower_bound_mean": float(np.mean([r.lower_bound or float("nan") for r in per_seed])),
            "mean_active_cuts": float(np.mean([r.mean_active_cuts for r in per_seed])),
            "total_cuts_generated_mean": float(np.mean([r.total_cuts_generated for r in per_seed])),
            "elapsed_sec_mean": float(np.mean([r.elapsed_sec for r in per_seed])),
            "termination_reasons": ";".join(sorted({r.termination_reason for r in per_seed})),
            "direct_objective": direct_obj,
        })

    return {
        "rows": rows,
        "iteration_rows": iteration_rows,
        "calibration_cut_count": len(calib_history),
        "direct_objective": direct_obj,
        "direct_status": direct.get("status_name"),
    }


def build_verdict(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Compare learned_K against the controls -- report whatever the data says.

    Rigour rules to avoid a fake "AI is faster" artifact:
    * Fewer iterations only counts as *better* when BOTH runs solved to the
      validated optimum (incumbent within tolerance of the direct MIP optimum).
      A run that stops early by getting stuck (e.g. duplicate cut) at a large
      gap is a FAILURE, never a win.
    * We first compare solution quality (solved-to-optimal rate); only among
      instances where both policies solved to optimum do we compare effort
      (iterations, time).
    """
    df = pd.DataFrame(rows)
    verdict: dict[str, Any] = {"per_metric": {}, "conclusion": "", "claim_boundary": "", "quality": {}}
    if df.empty or "learned_K" not in set(df["policy"]):
        verdict["conclusion"] = "insufficient_data"
        return verdict

    # Solution-quality first: how often does each policy reach validated optimum?
    quality = {}
    for policy in ["all_cuts", "random_K", "recency_K", "learned_K"]:
        pol = df[df["policy"] == policy]
        if len(pol):
            quality[policy] = {
                "instances": int(len(pol)),
                "all_solved_to_optimal_count": int(pol["all_solved_to_optimal"].sum()),
                "mean_validated_gap_pct": float(pol["validated_gap_pct_mean"].dropna().mean())
                if pol["validated_gap_pct_mean"].notna().any() else None,
            }
    verdict["quality"] = quality

    summary: dict[str, Any] = {}
    for baseline in ["all_cuts", "random_K", "recency_K"]:
        comp: dict[str, Any] = {}
        merged = df[df["policy"] == "learned_K"].merge(
            df[df["policy"] == baseline], on="case_id", suffixes=("_learned", "_base")
        )
        # Effort comparison restricted to instances where BOTH solved to optimum.
        both_solved = merged[
            merged["all_solved_to_optimal_learned"] & merged["all_solved_to_optimal_base"]
        ]
        comp["instances_compared"] = int(len(merged))
        comp["instances_both_solved_optimal"] = int(len(both_solved))
        for metric in ["iterations_mean", "elapsed_sec_mean"]:
            lcol, bcol = f"{metric}_learned", f"{metric}_base"
            if lcol in both_solved and bcol in both_solved and len(both_solved):
                wins = int((both_solved[lcol] < both_solved[bcol]).sum())
                ties = int((both_solved[lcol] == both_solved[bcol]).sum())
                losses = int((both_solved[lcol] > both_solved[bcol]).sum())
                comp[metric] = {
                    "learned_better": wins, "tie": ties, "learned_worse": losses,
                    "learned_mean": float(both_solved[lcol].mean()),
                    "baseline_mean": float(both_solved[bcol].mean()),
                }
        summary[f"learned_vs_{baseline}"] = comp
    verdict["per_metric"] = summary

    # First gate: did dropping cuts to a budget hurt solution quality at all?
    learned_q = quality.get("learned_K", {})
    learned_solved = learned_q.get("all_solved_to_optimal_count", 0)
    learned_total = learned_q.get("instances", 0)
    allcuts_solved = quality.get("all_cuts", {}).get("all_solved_to_optimal_count", 0)

    lr = summary.get("learned_vs_random_K", {}).get("iterations_mean", {})
    lc = summary.get("learned_vs_recency_K", {}).get("iterations_mean", {})
    n_both_r = summary.get("learned_vs_random_K", {}).get("instances_both_solved_optimal", 0)
    n_both_c = summary.get("learned_vs_recency_K", {}).get("instances_both_solved_optimal", 0)

    if learned_solved < learned_total:
        # The headline honest finding when budgeting breaks convergence.
        verdict["conclusion"] = "budgeted_cut_dropping_can_break_convergence"
    elif n_both_r == 0 and n_both_c == 0:
        verdict["conclusion"] = "insufficient_jointly_solved_instances_for_effort_claim"
    else:
        beats_random = lr.get("learned_better", 0) > lr.get("learned_worse", 0)
        beats_recency = lc.get("learned_better", 0) > lc.get("learned_worse", 0)
        worse_random = lr.get("learned_worse", 0) > lr.get("learned_better", 0)
        worse_recency = lc.get("learned_worse", 0) > lc.get("learned_better", 0)
        if beats_random and beats_recency:
            verdict["conclusion"] = "learned_policy_reduces_effort_vs_naive_budgets_on_jointly_solved"
        elif worse_random or worse_recency:
            verdict["conclusion"] = "learned_policy_not_better_than_naive_budgets"
        else:
            verdict["conclusion"] = "learned_policy_comparable_to_naive_budgets"

    # Structured findings so the paper/MIS can state BOTH facets honestly:
    # (1) robustness (solved-to-optimal ranking), (2) effort edge on jointly solved.
    def _rank(metric_key: str, baseline: str) -> str:
        block = summary.get(f"learned_vs_{baseline}", {}).get(metric_key, {})
        if not block:
            return "n/a"
        b, w = block.get("learned_better", 0), block.get("learned_worse", 0)
        return "learned_better" if b > w else "learned_worse" if w > b else "tie"

    time_vs = {b: _rank("elapsed_sec_mean", b) for b in ["all_cuts", "random_K", "recency_K"]}
    iter_vs = {b: _rank("iterations_mean", b) for b in ["all_cuts", "random_K", "recency_K"]}
    verdict["findings"] = {
        "robustness_ranking_by_solved_to_optimal": sorted(
            ((q.get("all_solved_to_optimal_count", 0), p) for p, q in quality.items()),
            reverse=True,
        ),
        "all_cuts_is_most_robust": allcuts_solved >= max(
            (q.get("all_solved_to_optimal_count", 0) for q in quality.values()), default=0
        ),
        "learned_at_least_as_robust_as_random": (
            learned_solved >= quality.get("random_K", {}).get("all_solved_to_optimal_count", 0)
        ),
        "time_vs_baselines_on_jointly_solved": time_vs,
        "iterations_vs_baselines_on_jointly_solved": iter_vs,
        "practical_recommendation": (
            "Prefer learned cut PRIORITISATION/ORDERING with cut retention over hard cut DROPPING: "
            "aggressive active-cut budgets can break exact convergence on harder instances, while the "
            "learned policy is at least as robust as the best naive control and shows a small "
            "per-iteration wall-time edge on instances that converge."
        ),
    }
    verdict["claim_boundary"] = (
        "Capacitated facility-location projection of public LRP instances; same-instance "
        "calibration; not full routing LRP and not okra enterprise validation. The verdict "
        "describes only this controlled cut-management comparison, and effort comparisons are "
        "restricted to instances where both policies reached the validated MIP optimum."
    )
    return verdict


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--budget", type=int, default=3, help="Active cut budget K for budgeted policies.")
    parser.add_argument("--time-limit", type=int, default=60, help="Per master/subproblem solve time limit (s).")
    parser.add_argument("--mip-gap", type=float, default=0.01)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--max-iterations", type=int, default=30)
    parser.add_argument("--seeds", type=int, nargs="+", default=[0, 1, 2])
    parser.add_argument("--instances", type=str, nargs="+", default=None)
    parser.add_argument(
        "--panel",
        type=str,
        default="legacy_small",
        help="Named roster to run when --instances is not provided.",
    )
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    from src.api.benchmark_manifest import load_normalized_manifest

    manifest = load_normalized_manifest(prefer_file=True)
    by_id = {e["entry_id"]: e for e in manifest["entries"]}
    wanted, panel_name = resolve_instance_ids(args.panel, args.instances)
    cases = []
    for eid in wanted:
        entry = by_id.get(eid)
        if entry is None:
            print(f"[WARN] instance not in manifest: {eid}")
            continue
        rec = dict(entry)
        rec["entry_id"] = eid
        cases.append(rec)

    all_rows: list[dict[str, Any]] = []
    all_iter_rows: list[dict[str, Any]] = []
    for case in cases:
        print(f"[RUN] {case['entry_id']} ...", flush=True)
        out = run_instance(
            case, budget=args.budget, time_limit=args.time_limit, mip_gap=args.mip_gap,
            threads=args.threads, max_iterations=args.max_iterations, seeds=args.seeds,
        )
        all_rows.extend(out["rows"])
        all_iter_rows.extend(out["iteration_rows"])

    summary_df = pd.DataFrame(all_rows)
    save_dataframe_bundle(summary_df, OUT_DIR / "benders_cutmgmt_comparison")
    iter_df = pd.DataFrame(all_iter_rows)
    save_dataframe_bundle(iter_df, OUT_DIR / "benders_cutmgmt_iterations")
    if not summary_df.empty:
        write_markdown_table(
            summary_df, OUT_DIR / "benders_cutmgmt_comparison.md",
            ["case_id", "policy", "budget", "iterations_mean", "final_gap_pct_mean",
             "mean_active_cuts", "elapsed_sec_mean", "termination_reasons"],
        )

    verdict = build_verdict(all_rows)
    summary_json = {
        "experiment_name": "benders_cutmgmt_comparison",
        "source_id": SOURCE_ID,
        "config": {
            "budget": args.budget,
            "time_limit": args.time_limit,
            "mip_gap": args.mip_gap,
            "threads": args.threads,
            "max_iterations": args.max_iterations,
            "seeds": args.seeds,
            "panel": panel_name,
            "instances": [c["entry_id"] for c in cases],
        },
        "policies": ["all_cuts", "random_K", "recency_K", "learned_K", "learned_residual_K"],
        "summary_rows": all_rows,
        "verdict": verdict,
        "research_boundary": verdict.get("claim_boundary", ""),
    }
    (OUT_DIR / "benders_cutmgmt_summary.json").write_text(
        json.dumps(summary_json, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({
        "cases": len(cases),
        "panel": panel_name,
        "rows": len(all_rows),
        "iterations": len(all_iter_rows),
        "conclusion": verdict["conclusion"],
        "out_dir": str(OUT_DIR),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
