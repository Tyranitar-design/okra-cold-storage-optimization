"""v3.0 容量链 Benders 四策略对比实验

在同一个 v3.0 容量链 MIP 上运行：
  - all_cuts   (经典 Benders)
  - recency_K  (最新 K 条)
  - random_K   (随机 K 条)
  - learned_K  (AI scorer top-K)

与 Gurobi 直接 MIP 做同问题对比，支撑 AI-Benders 论文贡献。
支持 Haversine 和 OSM 两种距离矩阵。
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.models.single_level_mip_v2_1 import DataConfig
from src.models.capacity_chain_assumptions import default_assumptions
from src.algorithms.benders_v3 import (
    benders_solve_v3,
    policy_all_cuts,
    policy_recency_k,
    policy_random_k,
    policy_learned_k,
)

OUT_DIR = PROJECT_ROOT / "results" / "experiments" / "benders_v3_comparison"
OUT_DIR.mkdir(parents=True, exist_ok=True)

OSM_DIST = PROJECT_ROOT / "data" / "distance_matrix_osm.csv"
OSM_TIME = PROJECT_ROOT / "data" / "transport_time_matrix_osm.csv"

CUT_BUDGET = 12       # 每次最多保留 K 条 active cut
TIME_LIMIT = 300.0    # 每个策略 5 分钟
N_SEEDS = 3           # random_K 需要多 seed（其余策略确定性）
GAP_TOL = 0.01


def long_to_pivot(path: Path, value_col: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    pivot = df.pivot(index="origin", columns="destination", values=value_col)
    ids = sorted(pivot.index.tolist())
    return pivot.loc[ids, ids]


class DataConfigOSM(DataConfig):
    def __init__(self, data_dir: str = str(PROJECT_ROOT / "data")):
        super().__init__(data_dir)
        dist_pivot = long_to_pivot(OSM_DIST, "distance_km")
        time_pivot = long_to_pivot(OSM_TIME, "time_h")
        self.distance = dist_pivot.values
        self.transport_time = time_pivot.values
        self.node_ids = list(dist_pivot.index)
        self.id2idx = {nid: i for i, nid in enumerate(self.node_ids)}


def run_policy(config: DataConfig, policy_name: str, policy_fn, seed: int = 0) -> dict:
    """跑一个策略，返回结果字典。"""
    import random
    random.seed(seed)

    print(f"\n  [{policy_name} seed={seed}] running...")
    result = benders_solve_v3(
        config,
        assumptions=default_assumptions(),
        cut_budget=CUT_BUDGET if policy_name != "all_cuts" else 99999,
        cut_policy=policy_fn,
        max_iterations=200,
        time_limit=TIME_LIMIT,
        gap_tol=GAP_TOL,
        master_time_per_iter=20.0,
        verbose=False,
    )
    summary = {
        "policy": policy_name,
        "seed": seed,
        "status": result.status,
        "objective": result.objective,
        "lower_bound": result.lower_bound,
        "mip_gap_pct": result.mip_gap_pct,
        "iterations": result.iterations,
        "elapsed_sec": result.elapsed_sec,
        "cuts_added": result.cuts_added,
        "cuts_dropped": result.cuts_dropped,
        "solved_to_gap": result.mip_gap_pct is not None and result.mip_gap_pct <= GAP_TOL * 100,
        "facilities": result.facilities,
        "convergence": result.convergence,
    }
    status_str = f"{'OK' if summary['solved_to_gap'] else 'NO'} {result.status}"
    gap_str = f"gap={result.mip_gap_pct:.4f}%" if result.mip_gap_pct else "no sol"
    print(f"  [{policy_name} seed={seed}] {status_str}, {gap_str}, "
          f"iter={result.iterations}, t={result.elapsed_sec:.1f}s, "
          f"cuts={result.cuts_added}(drop={result.cuts_dropped})")
    return summary


def main() -> None:
    print("=== v3.0 容量链 Benders 四策略对比实验 ===")
    print(f"  cut_budget={CUT_BUDGET}, time_limit={TIME_LIMIT}s, gap_tol={GAP_TOL*100}%")

    print("\n[1] Loading OSM DataConfig...")
    config = DataConfigOSM()
    assumptions = default_assumptions()

    policies = [
        ("all_cuts",  policy_all_cuts),
        ("recency_K", policy_recency_k),
        ("random_K",  policy_random_k),
        ("learned_K", policy_learned_k),
    ]

    all_runs: list[dict] = []

    for policy_name, policy_fn in policies:
        seeds = list(range(N_SEEDS)) if policy_name == "random_K" else [0]
        for seed in seeds:
            run = run_policy(config, policy_name, policy_fn, seed)
            all_runs.append(run)

    # ── 汇总统计 ──────────────────────────────────────────────────────────────
    print("\n=== 汇总 ===")
    print(f"{'Policy':12} {'Solved':7} {'Avg gap%':9} {'Avg iter':9} {'Avg t(s)':9} {'Avg cuts':9}")
    print("-" * 64)

    policy_stats: dict[str, dict] = {}
    for policy_name, _ in policies:
        runs = [r for r in all_runs if r["policy"] == policy_name]
        solved = sum(1 for r in runs if r["solved_to_gap"])
        gaps = [r["mip_gap_pct"] for r in runs if r["mip_gap_pct"] is not None]
        iters = [r["iterations"] for r in runs]
        times = [r["elapsed_sec"] for r in runs]
        cuts = [r["cuts_added"] for r in runs]
        avg_gap = sum(gaps) / len(gaps) if gaps else None
        policy_stats[policy_name] = {
            "solved_count": solved,
            "total": len(runs),
            "avg_gap_pct": round(avg_gap, 4) if avg_gap else None,
            "avg_iterations": round(sum(iters) / len(iters), 1),
            "avg_elapsed_sec": round(sum(times) / len(times), 1),
            "avg_cuts_added": round(sum(cuts) / len(cuts), 1),
        }
        gap_str = f"{avg_gap:.4f}%" if avg_gap else "N/A"
        print(f"{policy_name:12} {solved}/{len(runs)}    {gap_str:>9} "
              f"{sum(iters)/len(iters):>8.1f} {sum(times)/len(times):>8.1f} "
              f"{sum(cuts)/len(cuts):>8.1f}")

    # ── 写报告 ────────────────────────────────────────────────────────────────
    report = {
        "experiment": "benders_v3_four_policy_comparison",
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "config": {
            "cut_budget": CUT_BUDGET,
            "time_limit": TIME_LIMIT,
            "gap_tol": GAP_TOL,
            "n_seeds_random": N_SEEDS,
            "distance_matrix": "OSM road network",
        },
        "policy_stats": policy_stats,
        "runs": all_runs,
        "claim_boundary": (
            "Benders decomposition on v3.0 capacity-chain MIP with OSM road-network distances. "
            f"cut_budget={CUT_BUDGET}. policy_all_cuts uses unlimited cuts. "
            "County-level case study (39 nodes / 27 candidates). "
            "Subproblem LP solved exactly via Gurobi dual simplex. "
            "AI learned_K uses sub_obj + L1-norm heuristic scorer (not trained ML model); "
            "true ML scorer requires labeled training data from more instances."
        ),
    }

    out_json = OUT_DIR / "benders_v3_comparison_summary.json"
    out_json.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    print(f"\n[Done] → {out_json}")


if __name__ == "__main__":
    main()
