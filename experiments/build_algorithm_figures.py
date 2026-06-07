"""Publication-quality figures for the Benders + heuristic experiments.

Generates:
1. ``benders_gap_convergence.png`` -- gap (%) vs iteration per cut-management
   policy, for the hardest instances where policies actually diverge.
2. ``benders_solved_to_optimal.png`` -- bar chart of solved-to-optimal counts
   per policy (robustness of cut management).
3. ``exact_vs_heuristic_tradeoff.png`` -- cost gap (%) vs runtime (log) per
   method, plus exact-dominance coverage.
4. ``exact_pareto_front.png`` -- 2D projections (cost vs loss, cost vs carbon)
   of the exact frontier with heuristic points overlaid.

All figures read ONLY from materialised result JSON/CSV, so they reproduce the
real experiment outputs (no synthetic data). Missing inputs are skipped with a
warning rather than fabricated.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

CUTMGMT_DIR = PROJECT_ROOT / "results" / "experiments" / "benders_cutmgmt_comparison"
EXACT_DIR = PROJECT_ROOT / "results" / "experiments" / "exact_vs_heuristic"
FIG_DIR = PROJECT_ROOT / "results" / "experiments" / "figures"
FIG_DIR.mkdir(parents=True, exist_ok=True)

POLICY_STYLE = {
    "all_cuts": ("#1f77b4", "o", "All cuts (classic)"),
    "random_K": ("#ff7f0e", "s", "Random-K"),
    "recency_K": ("#2ca02c", "^", "Recency-K"),
    "learned_K": ("#d62728", "D", "Learned-K (AI)"),
}
METHOD_STYLE = {
    "exact_epsilon": ("#1f77b4", "o", "Exact ε-constraint"),
    "nsga3": ("#ff7f0e", "s", "NSGA-III"),
    "alns": ("#2ca02c", "^", "ALNS"),
}


def fig_gap_convergence() -> None:
    csv_path = CUTMGMT_DIR / "benders_cutmgmt_iterations.csv"
    if not csv_path.exists():
        print(f"[skip] {csv_path} missing")
        return
    df = pd.read_csv(csv_path)
    # pick instances where policies diverge (max iterations across policies high)
    spread = df.groupby("case_id")["iter_no"].max().sort_values(ascending=False)
    cases = spread.index[:2].tolist()
    fig, axes = plt.subplots(1, len(cases), figsize=(6 * len(cases), 4.5), squeeze=False)
    for ax, case in zip(axes[0], cases):
        sub = df[(df["case_id"] == case) & (df["seed"] == 0)]
        for pol, (color, marker, label) in POLICY_STYLE.items():
            tr = sub[sub["policy"] == pol].sort_values("iter_no")
            if tr.empty:
                continue
            ax.plot(tr["iter_no"], tr["gap_pct"], color=color, marker=marker,
                    markersize=4, linewidth=1.6, label=label)
        ax.set_yscale("symlog")
        ax.set_xlabel("Benders iteration")
        ax.set_ylabel("Optimality gap (%)")
        ax.set_title(f"Gap convergence — {case.split(':')[-1]}")
        ax.grid(True, alpha=0.3)
        ax.legend(fontsize=8)
    fig.suptitle("Benders cut-management: gap convergence by policy (seed 0)", fontsize=12)
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    out = FIG_DIR / "benders_gap_convergence.png"
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"[ok] {out}")


def fig_solved_to_optimal() -> None:
    json_path = CUTMGMT_DIR / "benders_cutmgmt_summary.json"
    if not json_path.exists():
        print(f"[skip] {json_path} missing")
        return
    s = json.loads(json_path.read_text(encoding="utf-8"))
    quality = s.get("verdict", {}).get("quality", {})
    if not quality:
        print("[skip] no quality block")
        return
    policies = [p for p in ["all_cuts", "random_K", "recency_K", "learned_K"] if p in quality]
    solved = [quality[p]["all_solved_to_optimal_count"] for p in policies]
    total = [quality[p]["instances"] for p in policies]
    labels = [POLICY_STYLE[p][2] for p in policies]
    colors = [POLICY_STYLE[p][0] for p in policies]
    fig, ax = plt.subplots(figsize=(7, 4.5))
    bars = ax.bar(labels, solved, color=colors)
    for bar, sv, tv in zip(bars, solved, total):
        ax.text(bar.get_x() + bar.get_width() / 2, sv + 0.05, f"{sv}/{tv}",
                ha="center", va="bottom", fontsize=10)
    ax.set_ylabel("Instances solved to validated optimum")
    ax.set_ylim(0, max(total) + 1)
    ax.set_title("Cut-management robustness (validated against direct MIP optimum)")
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    out = FIG_DIR / "benders_solved_to_optimal.png"
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"[ok] {out}")


def fig_exact_vs_heuristic_tradeoff() -> None:
    json_path = EXACT_DIR / "exact_vs_heuristic_summary.json"
    if not json_path.exists():
        print(f"[skip] {json_path} missing")
        return
    s = json.loads(json_path.read_text(encoding="utf-8"))
    rows = s["summary_rows"]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4.8))
    # left: cost gap vs runtime (log x)
    for r in rows:
        m = r["method"]
        color, marker, label = METHOD_STYLE.get(m, ("#777", "x", m))
        ax1.scatter(r["elapsed_sec_mean"], r["cost_gap_vs_exact_pct"],
                    s=90, color=color, marker=marker, label=f"{label} ({r['scenario'].split('_')[0]})")
        ax1.annotate(r["scenario"].split("_")[0], (r["elapsed_sec_mean"], r["cost_gap_vs_exact_pct"]),
                     fontsize=7, xytext=(4, 4), textcoords="offset points")
    ax1.set_xscale("log")
    ax1.set_xlabel("Runtime (s, log scale)")
    ax1.set_ylabel("Cost gap vs exact optimum (%)")
    ax1.set_title("Quality–time trade-off")
    ax1.grid(True, alpha=0.3)
    handles, labels = ax1.get_legend_handles_labels()
    uniq = dict(zip(labels, handles))
    ax1.legend(uniq.values(), uniq.keys(), fontsize=7)
    # right: exact-dominance coverage per heuristic
    heur_rows = [r for r in rows if r["method"] in ("nsga3", "alns")]
    xs = [f"{r['method']}\n{r['scenario'].split('_')[0]}" for r in heur_rows]
    cov = [r["coverage_not_dominated_by_exact_mean"] for r in heur_rows]
    colors = [METHOD_STYLE[r["method"]][0] for r in heur_rows]
    ax2.bar(xs, cov, color=colors)
    ax2.set_ylabel("Frac. heuristic points NOT dominated by exact")
    ax2.set_ylim(0, 1.05)
    ax2.set_title("Exact-dominance coverage (lower ⇒ exact front dominates)")
    ax2.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    out = FIG_DIR / "exact_vs_heuristic_tradeoff.png"
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"[ok] {out}")


def fig_exact_pareto_front() -> None:
    json_path = EXACT_DIR / "exact_vs_heuristic_summary.json"
    if not json_path.exists():
        print(f"[skip] {json_path} missing")
        return
    s = json.loads(json_path.read_text(encoding="utf-8"))
    fronts = s.get("fronts", {})
    scen = next(iter(fronts), None)
    if scen is None:
        print("[skip] no fronts payload")
        return
    exact_front = np.asarray(fronts[scen]["exact_front"], dtype=float)
    if exact_front.size == 0:
        print("[skip] empty exact front")
        return
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4.8))
    # cost vs loss
    order = np.argsort(exact_front[:, 1])
    ax1.plot(exact_front[order, 1], exact_front[order, 0] / 1e6, "o-",
             color="#1f77b4", label="Exact frontier")
    ax1.set_xlabel("Spoilage loss (ton)")
    ax1.set_ylabel("Total cost (million yuan)")
    ax1.set_title(f"Pareto: cost vs loss — {scen.split('_')[0]}")
    ax1.grid(True, alpha=0.3)
    ax1.legend(fontsize=8)
    # cost vs carbon
    order2 = np.argsort(exact_front[:, 2])
    ax2.plot(exact_front[order2, 2], exact_front[order2, 0] / 1e6, "s-",
             color="#9467bd", label="Exact frontier")
    ax2.set_xlabel("Carbon (ton CO₂)")
    ax2.set_ylabel("Total cost (million yuan)")
    ax2.set_title(f"Pareto: cost vs carbon — {scen.split('_')[0]}")
    ax2.grid(True, alpha=0.3)
    ax2.legend(fontsize=8)
    fig.tight_layout()
    out = FIG_DIR / "exact_pareto_front.png"
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"[ok] {out}")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    fig_gap_convergence()
    fig_solved_to_optimal()
    fig_exact_vs_heuristic_tradeoff()
    fig_exact_pareto_front()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
