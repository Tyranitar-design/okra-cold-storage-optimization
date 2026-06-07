"""Read-only report for v3.0 gap-closure solver-profile experiments."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from src.models.v3_solver_profiles import list_v3_solver_profiles


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESULTS_ROOT = PROJECT_ROOT / "results"
GAP_CLOSURE_ROOT = RESULTS_ROOT / "experiments" / "model_v3_gap_closure"
BASELINE_V3_REPORT_JSON_PATH = RESULTS_ROOT / "baseline_v3_capacity_chain_report.json"
GAP_CLOSURE_REPORT_JSON_PATH = GAP_CLOSURE_ROOT / "model_v3_gap_closure_report.json"
GAP_CLOSURE_REPORT_MD_PATH = GAP_CLOSURE_ROOT / "model_v3_gap_closure_report.md"


def _float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(val) for key, val in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            return value
    return value


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {"value": payload}


def solver_claim_boundary(solver: dict[str, Any]) -> dict[str, str]:
    status_name = str(solver.get("status_name") or "MISSING")
    sol_count = int(_float(solver.get("sol_count")))
    gap_pct = _float(solver.get("mip_gap_pct"))
    if sol_count <= 0:
        return {
            "solver_claim_state": "no_feasible_solution",
            "allowed_claim": "No v3.0 gap-closure solution claim is allowed because no feasible incumbent is available.",
        }
    if status_name == "OPTIMAL":
        return {
            "solver_claim_state": "gap_satisfied",
            "allowed_claim": "This v3.0 gap-closure run can be cited as solved to the configured optimality tolerance.",
        }
    if status_name == "TIME_LIMIT":
        return {
            "solver_claim_state": "feasible_time_limit_incumbent",
            "allowed_claim": (
                f"This v3.0 gap-closure run can be cited as a feasible incumbent with an open MIP gap "
                f"({gap_pct:.4f}%), not as a proven optimum."
            ),
        }
    return {
        "solver_claim_state": "feasible_solver_status_unclassified",
        "allowed_claim": f"Solver status is {status_name}; review the run log before making an optimality claim.",
    }


def _run_artifact_paths(root: Path = GAP_CLOSURE_ROOT) -> list[Path]:
    if not root.exists():
        return []
    return sorted(root.glob("*_run.json"))


def _load_runs(root: Path = GAP_CLOSURE_ROOT) -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    for path in _run_artifact_paths(root):
        payload = _read_json(path)
        if payload:
            payload.setdefault("artifact_path", str(path))
            runs.append(payload)
    return runs


def _best_by_numeric(runs: list[dict[str, Any]], field_path: tuple[str, ...], *, smallest: bool = True) -> dict[str, Any] | None:
    candidates: list[tuple[float, dict[str, Any]]] = []
    for run in runs:
        value: Any = run
        for key in field_path:
            value = value.get(key, {}) if isinstance(value, dict) else {}
        numeric = _float(value, default=float("inf") if smallest else float("-inf"))
        if numeric not in {float("inf"), float("-inf")}:
            candidates.append((numeric, run))
    if not candidates:
        return None
    return (min if smallest else max)(candidates, key=lambda item: item[0])[1]


def build_model_v3_gap_closure_report(root: Path | None = None) -> Dict[str, Any]:
    report_root = root or GAP_CLOSURE_ROOT
    baseline_report = _read_json(BASELINE_V3_REPORT_JSON_PATH)
    baseline_solver = baseline_report.get("solver", {}) if baseline_report else {}
    baseline_summary = baseline_report.get("summary", {}) if baseline_report else {}
    baseline_gap = baseline_solver.get("mip_gap_pct")
    runs = _load_runs(report_root)

    best_objective_run = _best_by_numeric(runs, ("solver", "objective"), smallest=True)
    best_gap_run = _best_by_numeric(runs, ("solver", "mip_gap_pct"), smallest=True)
    best_bound_run = _best_by_numeric(runs, ("solver", "objective_bound"), smallest=False)
    gap_values = [_float(run.get("solver", {}).get("mip_gap_pct"), default=float("inf")) for run in runs]
    finite_gap_values = [value for value in gap_values if value != float("inf")]
    smallest_run_gap = min(finite_gap_values) if finite_gap_values else None
    gap_improved = (
        smallest_run_gap is not None
        and baseline_gap not in (None, "")
        and smallest_run_gap < _float(baseline_gap)
    )
    any_gap_satisfied = any(run.get("claim_boundary", {}).get("solver_claim_state") == "gap_satisfied" for run in runs)

    report = {
        "source_name": "Model v3.0 gap-closure report",
        "source_backend": "gap_closure_artifacts",
        "result_paths": {
            "json": str(GAP_CLOSURE_REPORT_JSON_PATH),
            "md": str(GAP_CLOSURE_REPORT_MD_PATH),
            "artifact_dir": str(report_root),
            "baseline_v3_report": str(BASELINE_V3_REPORT_JSON_PATH),
        },
        "exists": {
            "artifact_dir": report_root.exists(),
            "report_json": GAP_CLOSURE_REPORT_JSON_PATH.exists(),
            "report_md": GAP_CLOSURE_REPORT_MD_PATH.exists(),
            "baseline_v3_report": BASELINE_V3_REPORT_JSON_PATH.exists(),
        },
        "profiles": list_v3_solver_profiles(),
        "baseline_reference": {
            "exists": bool(baseline_report),
            "solver": baseline_solver,
            "summary": {
                "total_cost": baseline_summary.get("total_cost"),
                "num_facilities": baseline_summary.get("num_facilities"),
                "claim_state": baseline_report.get("claim_boundary", {}).get("solver_claim_state"),
            },
        },
        "runs": runs,
        "summary": {
            "profile_count": len(list_v3_solver_profiles()),
            "run_count": len(runs),
            "baseline_status": baseline_solver.get("status_name"),
            "baseline_mip_gap_pct": baseline_gap,
            "best_objective_profile": best_objective_run.get("profile", {}).get("name") if best_objective_run else None,
            "best_objective": best_objective_run.get("solver", {}).get("objective") if best_objective_run else None,
            "best_bound_profile": best_bound_run.get("profile", {}).get("name") if best_bound_run else None,
            "best_bound": best_bound_run.get("solver", {}).get("objective_bound") if best_bound_run else None,
            "smallest_gap_profile": best_gap_run.get("profile", {}).get("name") if best_gap_run else None,
            "smallest_gap_pct": smallest_run_gap,
            "gap_improved_vs_baseline": gap_improved,
            "any_gap_satisfied": any_gap_satisfied,
            "evidence_state": "gap_satisfied" if any_gap_satisfied else "gap_run_available" if runs else "no_gap_runs_yet",
        },
        "research_boundary": (
            "Gap-closure runs are solver-profile experiments for the existing v3.0 scenario model. They can improve "
            "optimization evidence, but they do not replace real enterprise channel data or justify an optimality claim "
            "unless solver status and MIP gap support it."
        ),
        "next_action": (
            "Use the gap-satisfied profile as current v3.0 solver evidence, then run v3.0 scenario/sensitivity and real-parameter calibration."
            if any_gap_satisfied
            else "Run a bounded profile such as python scripts/run_model_v3_gap_closure.py --profile bound_focus_60s."
            if not runs
            else "Compare profile gaps and decide whether a longer extended_bound_900s run is worth the execution time."
        ),
    }
    return _json_safe(report)


def write_model_v3_gap_closure_report(out_dir: Path | None = None) -> Dict[str, str]:
    destination = out_dir or GAP_CLOSURE_ROOT
    destination.mkdir(parents=True, exist_ok=True)
    report = build_model_v3_gap_closure_report(destination)
    json_path = destination / "model_v3_gap_closure_report.json"
    md_path = destination / "model_v3_gap_closure_report.md"
    report["exists"]["report_json"] = True
    report["exists"]["report_md"] = True
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(
        "\n".join(
            [
                "# Model v3.0 Gap-Closure Report",
                "",
                "## Summary",
                "",
                *[f"- {key}: {value}" for key, value in report.get("summary", {}).items()],
                "",
                "## Runs",
                "",
                *[
                    (
                        f"- {run.get('profile', {}).get('name')}: status={run.get('solver', {}).get('status_name')}, "
                        f"objective={run.get('solver', {}).get('objective')}, "
                        f"bound={run.get('solver', {}).get('objective_bound')}, "
                        f"gap={run.get('solver', {}).get('mip_gap_pct')}"
                    )
                    for run in report.get("runs", [])
                ],
                "",
                "## Boundary",
                "",
                str(report.get("research_boundary", "")),
                "",
                "## Next Action",
                "",
                str(report.get("next_action", "")),
                "",
            ]
        ),
        encoding="utf-8",
    )
    return {"json_path": str(json_path), "md_path": str(md_path)}
