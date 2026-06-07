"""Replicate the fixed best Optuna AI warm-start configuration.

This script does not search hyperparameters. It loads the best trial from
``ai_warmstart_optuna_summary.json`` and reruns that exact XGBoost/warm-start/
Gurobi configuration several times. The output is a stability check for the
formal Optuna evidence, not a new optimization study.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from experiments.ai_warmstart_optuna import (  # noqa: E402
    CLAIM_BOUNDARY,
    OUT_DIR,
    SUMMARY_JSON,
    _json_safe,
    _prepare_context,
    _run_trial,
)
from experiments.ai_warmstart_v3 import solve_v3_with_optional_warm  # noqa: E402


RECHECK_JSON = OUT_DIR / "ai_warmstart_optuna_recheck_summary.json"
RECHECK_CSV = OUT_DIR / "ai_warmstart_optuna_recheck_trials.csv"
RECHECK_MD = OUT_DIR / "ai_warmstart_optuna_recheck.md"


def _load_summary(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"Missing Optuna summary: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _trial_params_from_summary(summary: dict[str, Any]) -> dict[str, Any]:
    best = summary.get("best_trial", {})
    best_params = best.get("params") or summary.get("best_params", {})
    xgb_params = best.get("xgb_params") or {
        "n_estimators": best_params.get("xgb_n_estimators"),
        "max_depth": best_params.get("xgb_max_depth"),
        "learning_rate": best_params.get("xgb_learning_rate"),
        "subsample": best_params.get("xgb_subsample"),
        "colsample_bytree": best_params.get("xgb_colsample_bytree"),
        "reg_lambda": best_params.get("xgb_reg_lambda"),
        "min_child_weight": best_params.get("xgb_min_child_weight"),
        "n_jobs": 1,
        "verbosity": 0,
    }
    solver_params = best.get("solver_params") or {
        "MIPFocus": best_params.get("gurobi_MIPFocus"),
        "Cuts": best_params.get("gurobi_Cuts"),
        "Heuristics": best_params.get("gurobi_Heuristics"),
        "Presolve": best_params.get("gurobi_Presolve"),
    }
    required = {
        "top_k": best_params.get("top_k"),
        "warm_strategy": best_params.get("warm_strategy"),
    }
    if required["top_k"] is None or not required["warm_strategy"]:
        raise SystemExit("Best trial summary does not contain top_k/warm_strategy.")
    return {
        "xgb_params": {k: v for k, v in xgb_params.items() if v is not None},
        "solver_params": {k: v for k, v in solver_params.items() if v is not None},
        "top_k": int(required["top_k"]),
        "warm_strategy": str(required["warm_strategy"]),
    }


def _row_from_result(replication: int, result: dict[str, Any]) -> dict[str, Any]:
    row = result["row"]
    return {
        "replication": replication,
        "label": row.get("label"),
        "status": row.get("status"),
        "elapsed_sec": result.get("elapsed_sec"),
        "gap_pct": result.get("gap_pct"),
        "objective": result.get("objective"),
        "objective_delta_pct": result.get("objective_delta_pct"),
        "objective_consistent": result.get("objective_consistent"),
        "solved_to_tol": result.get("solved_to_tol"),
        "speedup_vs_cold": result.get("speedup_vs_cold"),
        "top_sites": "|".join(result.get("top_sites", [])),
        "warm_facilities_injected": row.get("warm_facilities_injected"),
        "warm_strategy_version": row.get("warm_strategy_version"),
        "warm_strategy_name": row.get("warm_strategy_name"),
    }


def _stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    elapsed = [float(r["elapsed_sec"]) for r in rows if r.get("elapsed_sec") is not None]
    speedups = [float(r["speedup_vs_cold"]) for r in rows if r.get("speedup_vs_cold") is not None]
    gaps = [float(r["gap_pct"]) for r in rows if r.get("gap_pct") is not None]
    return {
        "replication_count": len(rows),
        "elapsed_sec_min": round(min(elapsed), 4) if elapsed else None,
        "elapsed_sec_mean": round(statistics.fmean(elapsed), 4) if elapsed else None,
        "elapsed_sec_max": round(max(elapsed), 4) if elapsed else None,
        "elapsed_sec_stdev": round(statistics.stdev(elapsed), 4) if len(elapsed) > 1 else 0.0 if elapsed else None,
        "speedup_vs_cold_mean": round(statistics.fmean(speedups), 4) if speedups else None,
        "gap_pct_max": round(max(gaps), 4) if gaps else None,
        "all_objective_consistent": all(bool(r.get("objective_consistent")) for r in rows) if rows else None,
        "all_solved_to_tol": all(bool(r.get("solved_to_tol")) for r in rows) if rows else None,
    }


def _render_markdown(summary: dict[str, Any]) -> str:
    stats = summary.get("replication_stats", {})
    ref = summary.get("reference_best_trial", {})
    lines = [
        "# AI Warm Start Optuna Best-Trial Recheck",
        "",
        f"- Built at: `{summary.get('built_at')}`",
        f"- Reference best trial: `#{ref.get('number')}`",
        f"- Reference elapsed: `{ref.get('elapsed_sec')}` s",
        f"- Reference speedup: `{ref.get('speedup_vs_cold')}` x",
        f"- Recheck replications: `{stats.get('replication_count')}`",
        f"- Recheck elapsed mean: `{stats.get('elapsed_sec_mean')}` s",
        f"- Recheck elapsed min/max: `{stats.get('elapsed_sec_min')}` / `{stats.get('elapsed_sec_max')}` s",
        f"- Recheck speedup mean: `{stats.get('speedup_vs_cold_mean')}` x",
        f"- Max gap: `{stats.get('gap_pct_max')}` %",
        f"- All objective consistent: `{stats.get('all_objective_consistent')}`",
        f"- All solved to tolerance: `{stats.get('all_solved_to_tol')}`",
        "",
        "## Claim Boundary",
        "",
        summary.get("claim_boundary", ""),
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, default=SUMMARY_JSON)
    parser.add_argument("--replications", type=int, default=3)
    parser.add_argument("--trial-time-limit", type=float, default=None)
    parser.add_argument("--mip-gap", type=float, default=None)
    parser.add_argument("--skip-cold", action="store_true", help="Use the cold baseline from the Optuna summary instead of rerunning it.")
    parser.add_argument("--dry-run", action="store_true", help="Only print the loaded best-trial configuration.")
    args = parser.parse_args()

    summary = _load_summary(args.summary)
    trial_params = _trial_params_from_summary(summary)
    if args.dry_run:
        print(json.dumps(_json_safe(trial_params), ensure_ascii=False, indent=2))
        return

    if args.replications <= 0:
        raise SystemExit("--replications must be positive unless --dry-run is used.")

    context = _prepare_context()
    config = context["config"]
    trial_time_limit = float(args.trial_time_limit or summary.get("trial_time_limit") or 180.0)
    mip_gap = float(args.mip_gap or summary.get("mip_gap") or 0.01)
    cold_start = summary.get("cold_start", {})
    if not args.skip_cold:
        cold_start = solve_v3_with_optional_warm(
            config,
            None,
            "optuna_best_recheck_cold_start",
            time_limit=trial_time_limit,
            mip_gap=mip_gap,
            solver_params={"MIPFocus": 3, "Cuts": 2},
        )

    baseline_objective = cold_start.get("objective")
    cold_elapsed = cold_start.get("elapsed_sec")
    rows: list[dict[str, Any]] = []
    raw_results: list[dict[str, Any]] = []
    for idx in range(1, args.replications + 1):
        result = _run_trial(
            config=config,
            train_df=context["train_df"],
            features=context["features"],
            facility_labels=context["facility_labels"],
            trial_params=trial_params,
            baseline_objective=baseline_objective,
            cold_elapsed_sec=cold_elapsed,
            trial_time_limit=trial_time_limit,
            mip_gap=mip_gap,
            label=f"optuna_best_recheck_{idx}",
        )
        raw_results.append(result)
        rows.append(_row_from_result(idx, result))
        print(
            f"[recheck {idx}] elapsed={result.get('elapsed_sec')}s "
            f"gap={result.get('gap_pct')} speedup={result.get('speedup_vs_cold')}"
        )

    payload = {
        "experiment": "v3_ai_warmstart_optuna_best_recheck",
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source_summary": str(args.summary),
        "reference_best_trial": summary.get("best_trial", {}),
        "trial_params": trial_params,
        "trial_time_limit": trial_time_limit,
        "mip_gap": mip_gap,
        "cold_start": cold_start,
        "replications": rows,
        "replication_stats": _stats(rows),
        "raw_results": _json_safe(raw_results),
        "claim_boundary": (
            "This recheck reruns the fixed Optuna best configuration to assess timing stability. "
            + CLAIM_BOUNDARY
        ),
        "outputs": {
            "summary_json": str(RECHECK_JSON),
            "trials_csv": str(RECHECK_CSV),
            "report_md": str(RECHECK_MD),
        },
    }
    RECHECK_JSON.write_text(json.dumps(_json_safe(payload), ensure_ascii=False, indent=2), encoding="utf-8")
    pd.DataFrame(rows).to_csv(RECHECK_CSV, index=False, encoding="utf-8-sig")
    RECHECK_MD.write_text(_render_markdown(payload), encoding="utf-8")
    print(f"[done] {RECHECK_JSON}")


if __name__ == "__main__":
    main()
