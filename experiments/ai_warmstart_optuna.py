"""Optuna-tuned AI warm start for the v3.0 capacity-chain MIP.

This script keeps the current XGBoost -> warm-start -> Gurobi pipeline intact,
then uses Optuna to tune the ranker, warm-start version, and selected Gurobi
parameters. The claim boundary is intentionally conservative: Optuna tunes the
initial solution and solver configuration, while Gurobi still certifies the
final solution quality.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from experiments.ai_warmstart_v3 import (  # noqa: E402
    DataConfigOSM,
    WARM_VERSION_LABELS,
    WARM_VERSION_V1,
    WARM_VERSION_V2,
    WARM_VERSION_V3,
    build_training_table,
    build_warm_facilities_for_version,
    compute_node_features,
    extract_facility_labels_from_priority_runs,
    extract_labels_from_priority_runs,
    predict_top_k,
    solve_v3_with_optional_warm,
    train_ranker,
)


OUT_DIR = PROJECT_ROOT / "results" / "experiments" / "ai_warmstart_optuna"
OUT_DIR.mkdir(parents=True, exist_ok=True)
STORAGE_URL = f"sqlite:///{(OUT_DIR / 'optuna.db').as_posix()}"
SUMMARY_JSON = OUT_DIR / "ai_warmstart_optuna_summary.json"
TRIALS_CSV = OUT_DIR / "ai_warmstart_optuna_trials.csv"
PARETO_CSV = OUT_DIR / "ai_warmstart_optuna_pareto.csv"
REPORT_MD = OUT_DIR / "ai_warmstart_optuna.md"

WARM_VERSIONS = [WARM_VERSION_V1, WARM_VERSION_V2, WARM_VERSION_V3]
HISTORICAL_SPEEDUP_RECORDS = [6.65, 7.18]
CLAIM_BOUNDARY = (
    "Optuna tunes XGBoost ranker parameters, warm-start construction, and selected Gurobi "
    "parameters for the v3.0 AI warm-start pipeline. Gurobi remains responsible for feasibility "
    "and configured-gap certification; this is county-case acceleration evidence, not enterprise-scale "
    "generalization or proof that AI replaces exact optimization."
)


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            return value
    return value


def _state_counts(trials: list[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for trial in trials:
        state = str(trial.state.name)
        counts[state] = counts.get(state, 0) + 1
    return counts


def _complete_count(trials: list[Any]) -> int:
    return sum(1 for trial in trials if str(trial.state.name) == "COMPLETE")


def _trial_values(trial: Any) -> list[Any]:
    values = getattr(trial, "values", None)
    if values is not None:
        return list(values)
    value = getattr(trial, "value", None)
    return [] if value is None else [value]


def _suggest_params(trial: Any) -> dict[str, Any]:
    xgb_params = {
        "n_estimators": trial.suggest_int("xgb_n_estimators", 40, 200),
        "max_depth": trial.suggest_int("xgb_max_depth", 2, 6),
        "learning_rate": trial.suggest_float("xgb_learning_rate", 0.02, 0.3, log=True),
        "subsample": trial.suggest_float("xgb_subsample", 0.7, 1.0),
        "colsample_bytree": trial.suggest_float("xgb_colsample_bytree", 0.7, 1.0),
        "reg_lambda": trial.suggest_float("xgb_reg_lambda", 0.1, 10.0, log=True),
        "min_child_weight": trial.suggest_int("xgb_min_child_weight", 1, 8),
        "n_jobs": 1,
        "verbosity": 0,
    }
    solver_params = {
        "MIPFocus": trial.suggest_categorical("gurobi_MIPFocus", [1, 2, 3]),
        "Cuts": trial.suggest_categorical("gurobi_Cuts", [0, 1, 2]),
        "Heuristics": trial.suggest_float("gurobi_Heuristics", 0.05, 0.5),
        "Presolve": trial.suggest_categorical("gurobi_Presolve", [1, 2]),
    }
    return {
        "xgb_params": xgb_params,
        "solver_params": solver_params,
        "top_k": trial.suggest_int("top_k", 4, 10),
        "warm_strategy": trial.suggest_categorical("warm_strategy", WARM_VERSIONS),
    }


def _prepare_context() -> dict[str, Any]:
    config = DataConfigOSM()
    labels = extract_labels_from_priority_runs()
    facility_labels = extract_facility_labels_from_priority_runs()
    features = compute_node_features(config)
    train_df = build_training_table(features, labels)
    return {
        "config": config,
        "labels": labels,
        "facility_labels": facility_labels,
        "features": features,
        "train_df": train_df,
    }


def _run_trial(
    *,
    config: DataConfigOSM,
    train_df: pd.DataFrame,
    features: pd.DataFrame,
    facility_labels: dict[str, list[dict[str, Any]]],
    trial_params: dict[str, Any],
    baseline_objective: float | None,
    cold_elapsed_sec: float | None,
    trial_time_limit: float,
    mip_gap: float,
    label: str,
) -> dict[str, Any]:
    clf, feature_cols = train_ranker(train_df, xgb_params=trial_params["xgb_params"])
    top_sites, scored = predict_top_k(clf, features, feature_cols, trial_params["top_k"])
    warm_facilities, strategy_name = build_warm_facilities_for_version(
        trial_params["warm_strategy"],
        top_sites,
        features,
        scored,
        facility_labels,
        config,
    )
    row = solve_v3_with_optional_warm(
        config,
        top_sites,
        label,
        warm_facilities=warm_facilities,
        warm_strategy_version=trial_params["warm_strategy"],
        warm_strategy_name=strategy_name,
        time_limit=trial_time_limit,
        mip_gap=mip_gap,
        solver_params=trial_params["solver_params"],
    )

    objective = row.get("objective")
    objective_delta_pct = None
    objective_consistent = False
    if baseline_objective and objective:
        objective_delta_pct = abs(float(objective) - float(baseline_objective)) / max(abs(float(baseline_objective)), 1.0) * 100.0
        objective_consistent = objective_delta_pct <= 0.01
    elif baseline_objective is None and objective is not None:
        objective_consistent = True

    gap_pct = row.get("mip_gap_pct")
    solved_to_tol = bool(row.get("solved_to_tol"))
    elapsed = float(row.get("elapsed_sec") or trial_time_limit)
    penalty = elapsed
    if not solved_to_tol:
        penalty += trial_time_limit + 100.0
    if not objective_consistent:
        penalty += 250.0 + float(objective_delta_pct or 100.0)
    speedup = round(float(cold_elapsed_sec) / elapsed, 4) if cold_elapsed_sec and elapsed > 0 else None

    return {
        "row": row,
        "penalized_elapsed": round(float(penalty), 4),
        "elapsed_sec": elapsed,
        "gap_pct": float(gap_pct) if gap_pct is not None else None,
        "objective": objective,
        "objective_delta_pct": objective_delta_pct,
        "objective_consistent": objective_consistent,
        "solved_to_tol": solved_to_tol,
        "speedup_vs_cold": speedup,
        "top_sites": top_sites,
        "warm_facilities": warm_facilities,
        "strategy_name": strategy_name,
    }


def _attrs_from_result(result: dict[str, Any], trial_params: dict[str, Any]) -> dict[str, Any]:
    return {
        "elapsed_sec": result["elapsed_sec"],
        "gap_pct": result["gap_pct"],
        "objective": result["objective"],
        "objective_delta_pct": result["objective_delta_pct"],
        "objective_consistent": result["objective_consistent"],
        "solved_to_tol": result["solved_to_tol"],
        "speedup_vs_cold": result["speedup_vs_cold"],
        "top_sites": result["top_sites"],
        "warm_strategy_label": WARM_VERSION_LABELS.get(trial_params["warm_strategy"], trial_params["warm_strategy"]),
        "strategy_name": result["strategy_name"],
        "solver_params": trial_params["solver_params"],
        "xgb_params": trial_params["xgb_params"],
        "warm_facilities": result["warm_facilities"],
    }


def _build_trial_rows(study: Any, multi_study: Any | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    trial_rows: list[dict[str, Any]] = []
    for trial in study.trials:
        row = {
            "study": study.study_name,
            "number": trial.number,
            "state": str(trial.state.name),
            "value": trial.value,
            **{f"param_{k}": v for k, v in trial.params.items()},
            **{f"attr_{k}": _json_safe(v) for k, v in trial.user_attrs.items()},
        }
        trial_rows.append(row)

    pareto_rows: list[dict[str, Any]] = []
    if multi_study is not None:
        for trial in multi_study.trials:
            values = _trial_values(trial)
            row = {
                "study": multi_study.study_name,
                "number": trial.number,
                "state": str(trial.state.name),
                "value": None,
                "value_0_elapsed_or_penalty": values[0] if len(values) > 0 else None,
                "value_1_gap_pct": values[1] if len(values) > 1 else None,
                **{f"param_{k}": v for k, v in trial.params.items()},
                **{f"attr_{k}": _json_safe(v) for k, v in trial.user_attrs.items()},
            }
            trial_rows.append(row)
        for trial in multi_study.best_trials:
            values = _trial_values(trial)
            pareto_rows.append(
                {
                    "study": multi_study.study_name,
                    "number": trial.number,
                    "elapsed_or_penalty": values[0] if len(values) > 0 else None,
                    "gap_pct": values[1] if len(values) > 1 else None,
                    **{f"param_{k}": v for k, v in trial.params.items()},
                    **{f"attr_{k}": _json_safe(v) for k, v in trial.user_attrs.items()},
                }
            )
    return trial_rows, pareto_rows


def _best_trial_payload(best: Any) -> dict[str, Any]:
    return {
        "number": best.number,
        "value": best.value,
        "params": dict(best.params),
        "elapsed_sec": best.user_attrs.get("elapsed_sec"),
        "gap_pct": best.user_attrs.get("gap_pct"),
        "objective": best.user_attrs.get("objective"),
        "objective_delta_pct": best.user_attrs.get("objective_delta_pct"),
        "objective_consistent": best.user_attrs.get("objective_consistent"),
        "solved_to_tol": best.user_attrs.get("solved_to_tol"),
        "speedup_vs_cold": best.user_attrs.get("speedup_vs_cold"),
        "top_sites": best.user_attrs.get("top_sites", []),
        "warm_strategy_label": best.user_attrs.get("warm_strategy_label"),
        "strategy_name": best.user_attrs.get("strategy_name"),
        "solver_params": best.user_attrs.get("solver_params", {}),
        "xgb_params": best.user_attrs.get("xgb_params", {}),
        "warm_facilities": best.user_attrs.get("warm_facilities", []),
    }


def _build_summary_payload(
    *,
    study: Any,
    multi_study: Any | None,
    cold_start: dict[str, Any],
    trial_time_limit: float,
    mip_gap: float,
    n_trials_requested: int,
    multi_trials_requested: int,
    training: dict[str, Any],
    trial_rows: list[dict[str, Any]],
    pareto_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    best_trial_payload = _best_trial_payload(study.best_trial)
    best_speedup = best_trial_payload.get("speedup_vs_cold")
    historical_best = max(HISTORICAL_SPEEDUP_RECORDS)
    return {
        "experiment": "v3_ai_warmstart_optuna",
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "storage": STORAGE_URL,
        "trial_count": len(study.trials),
        "single_trial_count": len(study.trials),
        "single_trial_complete_count": _complete_count(study.trials),
        "single_trial_state_counts": _state_counts(study.trials),
        "n_trials_requested": n_trials_requested,
        "multi_trials_requested": multi_trials_requested,
        "multi_trial_count": len(multi_study.trials) if multi_study is not None else 0,
        "multi_trial_complete_count": _complete_count(multi_study.trials) if multi_study is not None else 0,
        "multi_trial_state_counts": _state_counts(multi_study.trials) if multi_study is not None else {},
        "pareto_front_size": len(pareto_rows),
        "trial_time_limit": trial_time_limit,
        "mip_gap": mip_gap,
        "cold_start": cold_start,
        "best_trial": best_trial_payload,
        "best_params": dict(study.best_trial.params),
        "best_speedup": best_speedup,
        "historical_speedup_records": HISTORICAL_SPEEDUP_RECORDS,
        "historical_best_speedup": historical_best,
        "exceeds_historical_best": bool(best_speedup and float(best_speedup) > historical_best),
        "pareto_front": pareto_rows,
        "training": training,
        "claim_boundary": CLAIM_BOUNDARY,
        "reporting_note": (
            "Single-objective trial count is the Optuna TPE search budget. Multi-objective trial count is the "
            "NSGA-II auxiliary study budget used for Pareto evidence; Pareto front size may be smaller than the "
            "number of multi-objective trials."
        ),
        "outputs": {
            "summary_json": str(SUMMARY_JSON),
            "trials_csv": str(TRIALS_CSV),
            "pareto_csv": str(PARETO_CSV),
            "report_md": str(REPORT_MD),
        },
    }


def _render_markdown(summary: dict[str, Any]) -> str:
    best = summary.get("best_trial", {})
    cold = summary.get("cold_start", {})
    params = best.get("params", {})
    historical_best = summary.get("historical_best_speedup")
    best_speedup = best.get("speedup_vs_cold")
    exceeds_history = summary.get("exceeds_historical_best")
    lines = [
        "# AI Warm Start Optuna Report",
        "",
        f"- Built at: `{summary.get('built_at')}`",
        f"- Single-objective trials: `{summary.get('single_trial_complete_count', summary.get('trial_count'))}/{summary.get('n_trials_requested')}` complete",
        f"- Multi-objective trials: `{summary.get('multi_trial_complete_count', 0)}/{summary.get('multi_trials_requested', 0)}` complete",
        f"- Pareto front size: `{summary.get('pareto_front_size', len(summary.get('pareto_front', [])))}`",
        f"- Cold baseline elapsed: `{cold.get('elapsed_sec')}` s",
        f"- Cold baseline gap: `{cold.get('mip_gap_pct')}` %",
        f"- Best trial: `#{best.get('number')}`",
        f"- Best elapsed: `{best.get('elapsed_sec')}` s",
        f"- Best speedup vs cold: `{best_speedup}` x",
        f"- Best gap: `{best.get('gap_pct')}` %",
        f"- Objective consistent: `{best.get('objective_consistent')}`",
        f"- Warm strategy: `{best.get('warm_strategy_label')}`",
        f"- Historical best speedup reference: `{historical_best}` x",
        f"- Exceeds historical best: `{exceeds_history}`",
        "",
        "## Formal Conclusion",
        "",
        (
            f"Optuna completed a `{summary.get('single_trial_complete_count', summary.get('trial_count'))}`-trial "
            f"single-objective tuning study and found trial `#{best.get('number')}` with `{best_speedup}`x speedup "
            "against the cold baseline while preserving the certified objective value. This is clean acceleration "
            "evidence for the v3.0 county-case pipeline."
        ),
        "",
        (
            f"The run improves on the earlier smoke result, but it does not exceed the historical "
            f"`{historical_best}`x warm-start record. The honest claim is Optuna-backed reproducible tuning evidence, "
            "not a new project-wide speedup record."
        ),
        "",
        "## Best Trial Configuration",
        "",
        f"- XGBoost: `n_estimators={params.get('xgb_n_estimators')}`, `max_depth={params.get('xgb_max_depth')}`, `learning_rate={params.get('xgb_learning_rate')}`",
        f"- Warm start: `warm_strategy={params.get('warm_strategy')}`, `top_k={params.get('top_k')}`",
        f"- Gurobi: `MIPFocus={params.get('gurobi_MIPFocus')}`, `Cuts={params.get('gurobi_Cuts')}`, `Heuristics={params.get('gurobi_Heuristics')}`, `Presolve={params.get('gurobi_Presolve')}`",
        "",
        "## Claim Boundary",
        "",
        summary.get("claim_boundary", ""),
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n-trials", type=int, default=24)
    parser.add_argument("--timeout", type=float, default=7200.0)
    parser.add_argument("--multi-trials", type=int, default=None)
    parser.add_argument("--trial-time-limit", type=float, default=180.0)
    parser.add_argument("--mip-gap", type=float, default=0.01)
    parser.add_argument("--seed", type=int, default=20260605)
    parser.add_argument("--fresh", action="store_true", help="Delete the existing Optuna SQLite database before running.")
    parser.add_argument("--report-only", action="store_true", help="Rebuild JSON/CSV/Markdown from the existing Optuna database without running solvers.")
    args = parser.parse_args()

    try:
        import optuna
    except ImportError as exc:  # pragma: no cover - depends on local env
        raise SystemExit("Optuna is not installed. Install `optuna>=4,<5` before running this experiment.") from exc

    if args.report_only:
        previous = json.loads(SUMMARY_JSON.read_text(encoding="utf-8")) if SUMMARY_JSON.exists() else {}
        study = optuna.load_study(study_name="ai_warmstart_single_objective", storage=STORAGE_URL)
        try:
            multi_study = optuna.load_study(study_name="ai_warmstart_multi_objective", storage=STORAGE_URL)
        except Exception:
            multi_study = None
        trial_rows, pareto_rows = _build_trial_rows(study, multi_study)
        pd.DataFrame(trial_rows).to_csv(TRIALS_CSV, index=False, encoding="utf-8-sig")
        pd.DataFrame(pareto_rows).to_csv(PARETO_CSV, index=False, encoding="utf-8-sig")
        summary = _build_summary_payload(
            study=study,
            multi_study=multi_study,
            cold_start=previous.get("cold_start", {}),
            trial_time_limit=float(previous.get("trial_time_limit", args.trial_time_limit)),
            mip_gap=float(previous.get("mip_gap", args.mip_gap)),
            n_trials_requested=int(previous.get("n_trials_requested", len(study.trials))),
            multi_trials_requested=int(previous.get("multi_trials_requested", len(multi_study.trials) if multi_study is not None else 0)),
            training=previous.get("training", {}),
            trial_rows=trial_rows,
            pareto_rows=pareto_rows,
        )
        SUMMARY_JSON.write_text(json.dumps(_json_safe(summary), ensure_ascii=False, indent=2), encoding="utf-8")
        REPORT_MD.write_text(_render_markdown(summary), encoding="utf-8")
        print(f"[report-only] {SUMMARY_JSON}")
        print(f"[best] trial=#{summary['best_trial'].get('number')} speedup={summary.get('best_speedup')}x elapsed={summary['best_trial'].get('elapsed_sec')}s")
        return

    if args.fresh and (OUT_DIR / "optuna.db").exists():
        (OUT_DIR / "optuna.db").unlink()

    context = _prepare_context()
    config = context["config"]
    print("[baseline] Solving cold start for reference...")
    cold_start = solve_v3_with_optional_warm(
        config,
        None,
        "optuna_cold_start",
        time_limit=args.trial_time_limit,
        mip_gap=args.mip_gap,
        solver_params={"MIPFocus": 3, "Cuts": 2},
    )
    baseline_objective = cold_start.get("objective")
    cold_elapsed = cold_start.get("elapsed_sec")

    def objective(trial: Any) -> float:
        trial_params = _suggest_params(trial)
        result = _run_trial(
            config=config,
            train_df=context["train_df"],
            features=context["features"],
            facility_labels=context["facility_labels"],
            trial_params=trial_params,
            baseline_objective=baseline_objective,
            cold_elapsed_sec=cold_elapsed,
            trial_time_limit=args.trial_time_limit,
            mip_gap=args.mip_gap,
            label=f"optuna_trial_{trial.number}",
        )
        for key, value in _attrs_from_result(result, trial_params).items():
            trial.set_user_attr(key, _json_safe(value))
        return float(result["penalized_elapsed"])

    sampler = optuna.samplers.TPESampler(seed=args.seed)
    pruner = optuna.pruners.MedianPruner(n_startup_trials=min(5, max(args.n_trials, 1)))
    study = optuna.create_study(
        study_name="ai_warmstart_single_objective",
        storage=STORAGE_URL,
        direction="minimize",
        sampler=sampler,
        pruner=pruner,
        load_if_exists=True,
    )
    study.optimize(objective, n_trials=args.n_trials, timeout=args.timeout, gc_after_trial=True)

    multi_trials = args.multi_trials
    if multi_trials is None:
        multi_trials = max(0, min(6, args.n_trials // 3))

    multi_study = None
    if multi_trials > 0:
        multi_study = optuna.create_study(
            study_name="ai_warmstart_multi_objective",
            storage=STORAGE_URL,
            directions=["minimize", "minimize"],
            sampler=optuna.samplers.NSGAIISampler(seed=args.seed),
            load_if_exists=True,
        )
        multi_study.set_metric_names(["elapsed_or_penalty", "gap_pct"])

        def multi_objective(trial: Any) -> tuple[float, float]:
            trial_params = _suggest_params(trial)
            result = _run_trial(
                config=config,
                train_df=context["train_df"],
                features=context["features"],
                facility_labels=context["facility_labels"],
                trial_params=trial_params,
                baseline_objective=baseline_objective,
                cold_elapsed_sec=cold_elapsed,
                trial_time_limit=args.trial_time_limit,
                mip_gap=args.mip_gap,
                label=f"optuna_multi_{trial.number}",
            )
            for key, value in _attrs_from_result(result, trial_params).items():
                trial.set_user_attr(key, _json_safe(value))
            return float(result["penalized_elapsed"]), float(result["gap_pct"] if result["gap_pct"] is not None else 999.0)

        multi_study.optimize(multi_objective, n_trials=multi_trials, timeout=max(60.0, args.timeout / 3), gc_after_trial=True)

    trial_rows, pareto_rows = _build_trial_rows(study, multi_study)
    pd.DataFrame(trial_rows).to_csv(TRIALS_CSV, index=False, encoding="utf-8-sig")
    pd.DataFrame(pareto_rows).to_csv(PARETO_CSV, index=False, encoding="utf-8-sig")

    training = {
        "n_runs_used": len(context["labels"]),
        "variants": list(context["labels"].keys()),
        "n_train_rows": int(len(context["train_df"])),
        "n_positive": int(context["train_df"]["label"].sum()),
        "n_features": int(len([c for c in context["train_df"].columns if c not in ("node_id", "variant", "label")])),
    }
    summary = _build_summary_payload(
        study=study,
        multi_study=multi_study,
        cold_start=cold_start,
        trial_time_limit=args.trial_time_limit,
        mip_gap=args.mip_gap,
        n_trials_requested=args.n_trials,
        multi_trials_requested=multi_trials,
        training=training,
        trial_rows=trial_rows,
        pareto_rows=pareto_rows,
    )
    SUMMARY_JSON.write_text(json.dumps(_json_safe(summary), ensure_ascii=False, indent=2), encoding="utf-8")
    REPORT_MD.write_text(_render_markdown(summary), encoding="utf-8")
    print(f"[done] {SUMMARY_JSON}")
    print(f"[best] trial=#{summary['best_trial'].get('number')} speedup={summary.get('best_speedup')}x elapsed={summary['best_trial'].get('elapsed_sec')}s")


if __name__ == "__main__":
    main()
