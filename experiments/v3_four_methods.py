"""v3.0 容量链 + OSM 路网上的四方法对比

四个方法在同一 v3.0 模型 + 同一 OSM 矩阵上运行：
  1. gurobi_direct: 整体 MIP 直接求解（baseline）
  2. ai_warm:       Gurobi + XGBoost MIP Start（DS-F-051 的策略）
  3. nsga3_v3:      多目标遗传算法（cost/loss/carbon Pareto 前沿）
  4. alns_v3:       自适应大邻域搜索 + Pareto archive

度量：cost gap vs exact, hypervolume ratio, 运行时, 设施数, 求解时间。
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("GRB_LICENSE_FILE", r"D:\Gurobi1300\win64\bin\gurobi.lic")

from src.models.single_level_mip_v2_1 import DataConfig
from src.algorithms.layout_evaluator_v3 import make_evaluator_v3
from src.algorithms.heuristics_v3 import (
    run_nsga3_v3, run_alns_v3, hypervolume_mc_v3, pareto_filter_v3,
)
from experiments.ai_warmstart_v3 import (
    DataConfigOSM, extract_labels_from_priority_runs, extract_facility_labels_from_priority_runs,
    compute_node_features, build_training_table, train_ranker, predict_top_k,
    build_warm_facilities_for_version, solve_v3_with_optional_warm,
    RECOMMENDED_WARM_VERSION, WARM_VERSION_LABELS,
)

AI_WARMSTART_SUMMARY = PROJECT_ROOT / "results" / "experiments" / "ai_warmstart_v3" / "ai_warmstart_summary.json"


def resolve_adopted_warm_version() -> str:
    if AI_WARMSTART_SUMMARY.exists():
        try:
            payload = json.loads(AI_WARMSTART_SUMMARY.read_text(encoding="utf-8"))
            return str(payload.get("recommended_version") or RECOMMENDED_WARM_VERSION)
        except Exception:
            pass
    return RECOMMENDED_WARM_VERSION

OUT_DIR = PROJECT_ROOT / "results" / "experiments" / "v3_four_methods"
OUT_DIR.mkdir(parents=True, exist_ok=True)

EXACT_TIME_LIMIT = 600
HEURISTIC_TIME_LIMIT = 180
NSGA_POP = 50
NSGA_GEN = 25
ALNS_ITERS = 1500
SEEDS = [0, 1, 2]


def main():
    print("=== v3.0 + OSM 四方法对比 ===\n")

    print("[1] Loading config + evaluator...")
    config = DataConfigOSM()
    ev = make_evaluator_v3(config)

    # ── 训练 AI ranker（复用 ai_warmstart_v3 模块）─────────────────────────
    print("\n[2] Training AI ranker...")
    labels = extract_labels_from_priority_runs()
    facility_labels = extract_facility_labels_from_priority_runs()
    features = compute_node_features(config)
    train_df = build_training_table(features, labels)
    clf, feat_cols = train_ranker(train_df)
    top_k_sites, scored = predict_top_k(clf, features, feat_cols, k=8)
    adopted_version = resolve_adopted_warm_version()
    adopted_strategy = build_warm_facilities_for_version(
        adopted_version, top_k_sites, features, scored, facility_labels, config
    )[1]
    joint_warm_facilities, _ = build_warm_facilities_for_version(
        adopted_version, top_k_sites, features, scored, facility_labels, config
    )
    print(f"  AI top-8: {top_k_sites}")
    print(f"  Adopted {WARM_VERSION_LABELS.get(adopted_version, adopted_version)} facilities: {joint_warm_facilities}")

    # ── 1. Gurobi 直解 ─────────────────────────────────────────────────────
    print("\n[3] Method 1: gurobi_direct...")
    res_direct = solve_v3_with_optional_warm(config, None, "gurobi_direct")
    print(f"  obj={res_direct['objective']:.2f} gap={res_direct['mip_gap_pct']}% t={res_direct['elapsed_sec']}s")

    # ── 2. AI warm start ────────────────────────────────────────────────────
    print("\n[4] Method 2: ai_warm...")
    res_ai = solve_v3_with_optional_warm(
        config,
        top_k_sites,
        "ai_warm",
        warm_facilities=joint_warm_facilities,
        warm_strategy_version=adopted_version,
        warm_strategy_name=adopted_strategy,
    )
    print(f"  obj={res_ai['objective']:.2f} gap={res_ai['mip_gap_pct']}% t={res_ai['elapsed_sec']}s")

    # 精确法 reference cost (取 ai_warm 的 obj，这是当前最优)
    exact_obj = min(res_direct["objective"], res_ai["objective"])

    # ── 3. NSGA-III ─────────────────────────────────────────────────────────
    print(f"\n[5] Method 3: nsga3_v3 ({len(SEEDS)} seeds, pop={NSGA_POP}, gen={NSGA_GEN})...")
    nsga_runs = []
    for seed in SEEDS:
        ev_local = make_evaluator_v3(config)  # 重新生成（隔离评估计数）
        r = run_nsga3_v3(ev_local, pop_size=NSGA_POP, n_gen=NSGA_GEN,
                          seed=seed, time_limit=HEURISTIC_TIME_LIMIT)
        archive_objs = [a[0] for a in r.archive]
        n_front = len(r.archive)
        best_cost = r.best_cost
        cost_gap = (best_cost - exact_obj) / exact_obj * 100 if exact_obj > 0 else None
        nsga_runs.append({
            "seed": seed, "front_size": n_front, "best_cost": best_cost,
            "cost_gap_pct": cost_gap, "elapsed_sec": r.elapsed_sec,
            "n_evaluations": r.n_evaluations, "generations": r.generations,
            "archive_objs": archive_objs,
        })
        print(f"  seed={seed}: front={n_front}, best={best_cost:.2f}, gap={cost_gap:.3f}%, "
              f"t={r.elapsed_sec:.1f}s, evals={r.n_evaluations}")

    # ── 4. ALNS ─────────────────────────────────────────────────────────────
    print(f"\n[6] Method 4: alns_v3 ({len(SEEDS)} seeds, iters={ALNS_ITERS})...")
    alns_runs = []
    for seed in SEEDS:
        ev_local = make_evaluator_v3(config)
        r = run_alns_v3(ev_local, iterations=ALNS_ITERS,
                         seed=seed, time_limit=HEURISTIC_TIME_LIMIT)
        archive_objs = [a[0] for a in r.archive]
        n_front = len(r.archive)
        best_cost = r.best_cost
        cost_gap = (best_cost - exact_obj) / exact_obj * 100 if exact_obj > 0 else None
        alns_runs.append({
            "seed": seed, "front_size": n_front, "best_cost": best_cost,
            "cost_gap_pct": cost_gap, "elapsed_sec": r.elapsed_sec,
            "n_evaluations": r.n_evaluations, "iterations": r.iterations,
            "archive_objs": archive_objs,
        })
        print(f"  seed={seed}: front={n_front}, best={best_cost:.2f}, gap={cost_gap:.3f}%, "
              f"t={r.elapsed_sec:.1f}s, evals={r.n_evaluations}")

    # ── 汇总 ────────────────────────────────────────────────────────────────
    print("\n=== 汇总 ===")
    print(f"{'Method':18} {'best_cost':>13} {'gap%':>9} {'time(s)':>9} {'front':>6}")
    print("-" * 60)
    print(f"{'gurobi_direct':18} {res_direct['objective']:>13.2f} {res_direct['mip_gap_pct']:>8.4f}% "
          f"{res_direct['elapsed_sec']:>9.1f} {'1':>6}")
    print(f"{'ai_warm':18} {res_ai['objective']:>13.2f} {res_ai['mip_gap_pct']:>8.4f}% "
          f"{res_ai['elapsed_sec']:>9.1f} {'1':>6}")
    nsga_mean_gap = np.mean([r["cost_gap_pct"] for r in nsga_runs])
    nsga_mean_time = np.mean([r["elapsed_sec"] for r in nsga_runs])
    nsga_mean_front = np.mean([r["front_size"] for r in nsga_runs])
    nsga_mean_best = np.mean([r["best_cost"] for r in nsga_runs])
    print(f"{'nsga3_v3 (mean)':18} {nsga_mean_best:>13.2f} {nsga_mean_gap:>8.3f}% "
          f"{nsga_mean_time:>9.1f} {nsga_mean_front:>6.1f}")
    alns_mean_gap = np.mean([r["cost_gap_pct"] for r in alns_runs])
    alns_mean_time = np.mean([r["elapsed_sec"] for r in alns_runs])
    alns_mean_front = np.mean([r["front_size"] for r in alns_runs])
    alns_mean_best = np.mean([r["best_cost"] for r in alns_runs])
    print(f"{'alns_v3 (mean)':18} {alns_mean_best:>13.2f} {alns_mean_gap:>8.3f}% "
          f"{alns_mean_time:>9.1f} {alns_mean_front:>6.1f}")

    # ── 写报告 ──────────────────────────────────────────────────────────────
    report = {
        "experiment": "v3_four_methods_comparison",
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "config": {
            "model": "v3.0_capacity_chain",
            "distance_matrix": "OSM_road_network",
            "exact_time_limit": EXACT_TIME_LIMIT,
            "heuristic_time_limit": HEURISTIC_TIME_LIMIT,
            "nsga_pop": NSGA_POP, "nsga_gen": NSGA_GEN,
            "alns_iters": ALNS_ITERS,
            "seeds": SEEDS,
        },
        "exact_reference_obj": float(exact_obj),
        "recommended_version": adopted_version,
        "recommended_label": WARM_VERSION_LABELS.get(adopted_version, adopted_version),
        "ai_top_k_sites": top_k_sites,
        "ai_warm_facilities": joint_warm_facilities,
        "joint_strategy": adopted_strategy,
        "results": {
            "gurobi_direct": res_direct,
            "ai_warm": res_ai,
            "nsga3_v3": {
                "runs": nsga_runs,
                "mean_cost_gap_pct": float(nsga_mean_gap),
                "mean_elapsed_sec": float(nsga_mean_time),
                "mean_front_size": float(nsga_mean_front),
                "mean_best_cost": float(nsga_mean_best),
            },
            "alns_v3": {
                "runs": alns_runs,
                "mean_cost_gap_pct": float(alns_mean_gap),
                "mean_elapsed_sec": float(alns_mean_time),
                "mean_front_size": float(alns_mean_front),
                "mean_best_cost": float(alns_mean_best),
            },
        },
        "claim_boundary": (
            "Four-method comparison on v3.0 capacity-chain MIP with OSM road-network distances. "
            "Gurobi/AI warm: single-objective weighted cost with 1% gap tolerance. "
            "NSGA-III/ALNS: multi-objective Pareto over (cost, loss_ton, carbon_ton); "
            "best_cost is the minimum-cost Pareto point. "
            "Heuristics use the same v3.0 evaluator with LP subproblem (z heuristic, x LP-optimal). "
            "AI warm start trained on 4 priority scenarios (XGBoost), with the adopted warm-start version injected here. "
            "County-level case (39 nodes), not enterprise-scale validation."
        ),
    }
    out = OUT_DIR / "v3_four_methods_summary.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"\n[Done] → {out}")


if __name__ == "__main__":
    main()
