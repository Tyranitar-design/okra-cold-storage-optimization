"""v3.0 单目标精确性维度：Benders vs Gurobi 直接 MIP 对比

在同一个 v3.0 容量链 MIP（同加权成本目标、同 OSM 路网矩阵）上对比：
  - gurobi_direct  : Gurobi 整体 branch-and-cut
  - benders_classic: Benders 分解 (all_cuts)
  - benders_learned: Benders + learned cut 排序 (K=large)

度量：达到 1% gap 的时间、迭代数、最终 gap、最优目标值（应一致）。

这是论文"为何 AI 增强 Benders"论证的精确性维度证据；
多目标前沿维度（NSGA-III/ALNS）见 DS-F-044 (exact_vs_heuristic)。
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
from src.models.single_level_mip_v3_capacity_chain import build_and_solve_v3
from src.models.capacity_chain_assumptions import default_assumptions
from src.algorithms.benders_v3 import (
    benders_solve_v3,
    policy_all_cuts,
    policy_learned_k,
)

OUT_DIR = PROJECT_ROOT / "results" / "experiments" / "v3_exact_methods"
OUT_DIR.mkdir(parents=True, exist_ok=True)

OSM_DIST = PROJECT_ROOT / "data" / "distance_matrix_osm.csv"
OSM_TIME = PROJECT_ROOT / "data" / "transport_time_matrix_osm.csv"

TIME_LIMIT = 300.0
GAP_TOL = 0.01
LEARNED_K = 30   # K 调优后选定的较宽松预算


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


def run_gurobi_direct(config) -> dict:
    print("\n[gurobi_direct] solving...")
    t0 = time.time()
    model, z, x, elapsed = build_and_solve_v3(
        config,
        assumptions=default_assumptions(),
        time_limit=int(TIME_LIMIT),
        mip_gap=GAP_TOL,
        threads=8,
        solver_params={"MIPFocus": 3, "Cuts": 2},
        verbose=False,
    )
    obj = model.ObjVal if model.SolCount > 0 else None
    gap = model.MIPGap if model.SolCount > 0 else None
    solved = gap is not None and gap <= GAP_TOL
    row = {
        "method": "gurobi_direct",
        "objective": obj,
        "bound": model.ObjBound,
        "gap_pct": round(gap * 100, 4) if gap is not None else None,
        "elapsed_sec": round(elapsed, 2),
        "iterations": None,
        "solved_to_optimal": solved,
        "note": "Gurobi monolithic branch-and-cut",
    }
    print(f"  obj={obj:.2f}, gap={gap*100:.4f}%, t={elapsed:.1f}s")
    return row


def run_benders(config, label, policy_fn, k) -> dict:
    print(f"\n[{label}] solving...")
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
        "method": label,
        "objective": result.objective,
        "bound": result.lower_bound,
        "gap_pct": result.mip_gap_pct,
        "elapsed_sec": result.elapsed_sec,
        "iterations": result.iterations,
        "solved_to_optimal": solved,
        "cuts_added": result.cuts_added,
        "cuts_dropped": result.cuts_dropped,
        "note": f"Benders decomposition, K={k}",
    }
    gap_s = f"{result.mip_gap_pct:.4f}%" if result.mip_gap_pct else "N/A"
    obj_s = f"{result.objective:.2f}" if result.objective else "N/A"
    print(f"  obj={obj_s}, gap={gap_s}, "
          f"iter={result.iterations}, t={result.elapsed_sec:.1f}s")
    return row


def main():
    print("=== v3.0 单目标精确性维度对比 ===")
    print(f"  OSM 路网矩阵, time_limit={TIME_LIMIT}s, gap_tol={GAP_TOL*100}%")

    config = DataConfigOSM()
    rows = []

    rows.append(run_gurobi_direct(config))
    rows.append(run_benders(config, "benders_classic", policy_all_cuts, 99999))
    rows.append(run_benders(config, "benders_learned", policy_learned_k, LEARNED_K))

    # ── 汇总表 ────────────────────────────────────────────────────────────────
    print("\n=== 汇总：v3.0 精确方法对比 ===")
    print(f"{'Method':18} {'Obj':>14} {'Gap%':>8} {'Iter':>6} {'Time(s)':>9} {'Solved':>7}")
    print("-" * 70)
    for r in rows:
        obj_s = f"{r['objective']:.2f}" if r['objective'] else "N/A"
        gap_s = f"{r['gap_pct']:.4f}" if r['gap_pct'] is not None else "N/A"
        it_s = str(r['iterations']) if r['iterations'] else "-"
        solved_s = "YES" if r['solved_to_optimal'] else "NO"
        print(f"{r['method']:18} {obj_s:>14} {gap_s:>8} {it_s:>6} "
              f"{r['elapsed_sec']:>9.1f} {solved_s:>7}")

    # 速度对比
    gurobi_t = next((r['elapsed_sec'] for r in rows if r['method'] == 'gurobi_direct'), None)
    benders_t = next((r['elapsed_sec'] for r in rows if r['method'] == 'benders_classic'), None)
    speedup = round(gurobi_t / benders_t, 1) if (gurobi_t and benders_t and benders_t > 0) else None

    report = {
        "experiment": "v3_exact_methods_comparison",
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "config": {
            "time_limit": TIME_LIMIT, "gap_tol": GAP_TOL,
            "learned_K": LEARNED_K, "distance_matrix": "OSM road network",
            "model": "v3.0 capacity-chain MIP, single weighted-cost objective",
        },
        "rows": rows,
        "benders_speedup_vs_gurobi": speedup,
        "multiobjective_dimension_ref": "DS-F-044 (exact_vs_heuristic): NSGA-III 0.36% / ALNS 8.10% cost gap",
        "claim_boundary": (
            "Single-objective exactness dimension on v3.0 capacity-chain MIP (OSM matrix, 39 nodes). "
            "All three exact methods should reach the same optimum (within 1% tol); "
            "they differ in time/iterations to certify it. "
            "Benders speedup depends on instance; this is a county-level case, not enterprise-scale. "
            "Multi-objective frontier comparison (NSGA-III/ALNS) is DS-F-044, a separate v2.1-model experiment."
        ),
    }
    out = OUT_DIR / "v3_exact_methods_summary.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"\n[Done] → {out}")
    if speedup:
        print(f"\n  Benders classic vs Gurobi direct: {speedup}× speedup (this instance)")


if __name__ == "__main__":
    main()
