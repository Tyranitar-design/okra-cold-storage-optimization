"""Benders v3.0 cut budget K 调优扫描

扫描 cut_budget K ∈ {8, 12, 16, 20, 30, all}，观察三种 cut 管理策略
(recency_K / random_K / learned_K) 在不同预算下的收敛行为。

研究问题：
  - learned_K 是否在某个 K 阈值上开始优于 recency_K / random_K？
  - 多大的 K 才能让丢弃策略恢复精确收敛（接近 all_cuts）？

严谨性闸门：gap/iter/time 只在达到验证最优（gap≤1%）的 run 间有意义比较；
卡在大 gap 的 run 记为 FAILURE（不算"迭代更少"的胜利）。
"""

from __future__ import annotations

import json
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

OUT_DIR = PROJECT_ROOT / "results" / "experiments" / "benders_v3_ktuning"
OUT_DIR.mkdir(parents=True, exist_ok=True)

OSM_DIST = PROJECT_ROOT / "data" / "distance_matrix_osm.csv"
OSM_TIME = PROJECT_ROOT / "data" / "transport_time_matrix_osm.csv"

K_VALUES = [8, 12, 16, 20, 30]    # all_cuts 单独跑一次作 baseline
TIME_LIMIT = 200.0
GAP_TOL = 0.01
N_SEEDS_RANDOM = 3


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


def run_one(config, policy_name, policy_fn, k, seed):
    import random
    random.seed(seed)
    result = benders_solve_v3(
        config,
        assumptions=default_assumptions(),
        cut_budget=k,
        cut_policy=policy_fn,
        max_iterations=300,
        time_limit=TIME_LIMIT,
        gap_tol=GAP_TOL,
        master_time_per_iter=15.0,
        verbose=False,
    )
    solved = result.mip_gap_pct is not None and result.mip_gap_pct <= GAP_TOL * 100
    row = {
        "policy": policy_name,
        "K": k,
        "seed": seed,
        "solved_to_optimal": solved,
        "gap_pct": result.mip_gap_pct,
        "iterations": result.iterations,
        "elapsed_sec": result.elapsed_sec,
        "cuts_added": result.cuts_added,
        "cuts_dropped": result.cuts_dropped,
        "objective": result.objective,
        "status": result.status,
    }
    flag = "OK" if solved else "FAIL"
    gap_s = f"{result.mip_gap_pct:.3f}%" if result.mip_gap_pct else "N/A"
    print(f"  {policy_name:10} K={k:>4} seed={seed}: {flag:4} gap={gap_s:>9} "
          f"iter={result.iterations:>3} t={result.elapsed_sec:>6.1f}s "
          f"cuts={result.cuts_added}(drop={result.cuts_dropped})")
    return row


def main():
    print("=== Benders v3.0 cut budget K 调优扫描 ===")
    print(f"  K values: {K_VALUES} + all_cuts, time_limit={TIME_LIMIT}s, gap_tol={GAP_TOL*100}%\n")

    config = DataConfigOSM()
    rows = []

    # all_cuts baseline（K 无关）
    print("[all_cuts baseline]")
    rows.append(run_one(config, "all_cuts", policy_all_cuts, 99999, 0))

    # 三策略 × K 扫描
    for k in K_VALUES:
        print(f"\n[K={k}]")
        rows.append(run_one(config, "recency_K", policy_recency_k, k, 0))
        rows.append(run_one(config, "learned_K", policy_learned_k, k, 0))
        for seed in range(N_SEEDS_RANDOM):
            rows.append(run_one(config, "random_K", policy_random_k, k, seed))

    # ── 汇总：每个 (policy, K) 的 solved 率和平均 gap ──────────────────────────
    print("\n=== 汇总：求解到最优(gap≤1%)的能力 ===")
    print(f"{'Policy':12} {'K':>6} {'Solved':>8} {'AvgGap%':>9} {'AvgIter':>8} {'AvgTime':>8}")
    print("-" * 60)

    summary = {}
    df = pd.DataFrame(rows)
    for (policy, k), grp in df.groupby(["policy", "K"]):
        solved = int(grp["solved_to_optimal"].sum())
        total = len(grp)
        avg_gap = grp["gap_pct"].mean()
        avg_iter = grp["iterations"].mean()
        avg_time = grp["elapsed_sec"].mean()
        key = f"{policy}_K{k}"
        summary[key] = {
            "policy": policy, "K": int(k),
            "solved": solved, "total": total,
            "avg_gap_pct": round(float(avg_gap), 4) if pd.notna(avg_gap) else None,
            "avg_iterations": round(float(avg_iter), 1),
            "avg_elapsed_sec": round(float(avg_time), 1),
        }
        k_disp = "all" if k == 99999 else str(k)
        print(f"{policy:12} {k_disp:>6} {solved}/{total:<6} "
              f"{avg_gap:>8.3f} {avg_iter:>8.1f} {avg_time:>8.1f}")

    # ── 关键发现 ──────────────────────────────────────────────────────────────
    findings = []
    # learned_K 在哪个 K 开始 solved?
    learned_solved_ks = sorted([
        v["K"] for v in summary.values()
        if v["policy"] == "learned_K" and v["solved"] > 0
    ])
    recency_solved_ks = sorted([
        v["K"] for v in summary.values()
        if v["policy"] == "recency_K" and v["solved"] > 0
    ])
    if learned_solved_ks:
        findings.append(f"learned_K 在 K>={learned_solved_ks[0]} 时可求解到最优")
    else:
        findings.append("learned_K 在所有测试 K 值下均未求解到最优（K 仍太小）")
    if recency_solved_ks:
        findings.append(f"recency_K 在 K>={recency_solved_ks[0]} 时可求解到最优")
    else:
        findings.append("recency_K 在所有测试 K 值下均未求解到最优")

    report = {
        "experiment": "benders_v3_k_tuning",
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "config": {
            "K_values": K_VALUES, "time_limit": TIME_LIMIT,
            "gap_tol": GAP_TOL, "n_seeds_random": N_SEEDS_RANDOM,
            "distance_matrix": "OSM road network",
        },
        "summary": summary,
        "runs": rows,
        "findings": findings,
        "claim_boundary": (
            "Benders on v3.0 capacity-chain MIP (OSM matrix, 39 nodes / 27 candidates). "
            "Effort metrics only meaningful among runs that reached validated optimum (gap<=1%). "
            "learned_K scorer is heuristic (sub_obj + L1 norm), not trained ML. "
            "Hard cut dropping below a threshold K breaks exact convergence. County-level case."
        ),
    }

    out = OUT_DIR / "benders_v3_ktuning_summary.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"\n[Done] → {out}")
    print("\n=== 关键发现 ===")
    for f in findings:
        print(f"  - {f}")


if __name__ == "__main__":
    main()
