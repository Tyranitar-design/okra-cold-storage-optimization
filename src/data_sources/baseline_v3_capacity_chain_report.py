"""Build a formal report for the v3.0 peak-capacity/service-chain baseline."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from src.api.services import load_pickle_payload


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESULTS_ROOT = PROJECT_ROOT / "results"
BASELINE_V3_RESULT_PATH = RESULTS_ROOT / "baseline_v3_capacity_chain_result.pkl"
BASELINE_V3_REPORT_JSON_PATH = RESULTS_ROOT / "baseline_v3_capacity_chain_report.json"
BASELINE_V3_REPORT_MD_PATH = RESULTS_ROOT / "baseline_v3_capacity_chain_report.md"


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
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            return value
    if isinstance(value, Path):
        return str(value)
    return value


def _solver_claim_boundary(solver: dict[str, Any]) -> dict[str, str]:
    status_name = str(solver.get("status_name") or "MISSING")
    sol_count = int(_float(solver.get("sol_count")))
    gap_pct = _float(solver.get("mip_gap_pct"))

    if sol_count <= 0:
        return {
            "solver_claim_state": "no_feasible_solution",
            "allowed_claim": "No v3.0 solution claim is allowed because no feasible incumbent is available.",
        }
    if status_name == "OPTIMAL":
        return {
            "solver_claim_state": "gap_satisfied",
            "allowed_claim": "The v3.0 run can be cited as solved to the configured optimality tolerance.",
        }
    if status_name == "TIME_LIMIT":
        return {
            "solver_claim_state": "feasible_time_limit_incumbent",
            "allowed_claim": (
                f"The v3.0 run can be cited as a feasible incumbent with an open MIP gap "
                f"({gap_pct:.4f}%), not as a proven optimum."
            ),
        }
    return {
        "solver_claim_state": "feasible_solver_status_unclassified",
        "allowed_claim": (
            f"The v3.0 run has solver status {status_name}; review the solver log before making "
            "an optimality claim."
        ),
    }


def build_baseline_v3_capacity_chain_report() -> Dict[str, Any]:
    payload = load_pickle_payload(BASELINE_V3_RESULT_PATH) if BASELINE_V3_RESULT_PATH.exists() else {}
    analysis = payload.get("analysis", {}) if isinstance(payload, dict) else {}
    summary = analysis.get("summary", {}) if isinstance(analysis, dict) else {}
    solver = analysis.get("solver", {}) if isinstance(analysis, dict) else {}
    annual_flow_by_type = analysis.get("annual_flow_by_type", {}) if isinstance(analysis, dict) else {}
    peak_load_by_type = analysis.get("peak_load_by_type", {}) if isinstance(analysis, dict) else {}
    facilities = analysis.get("facilities", []) if isinstance(analysis, dict) else []
    risk_response = analysis.get("risk_response", {}) if isinstance(analysis, dict) else {}

    total_flow = sum(_float(value) for value in annual_flow_by_type.values())
    channel_mix = [
        {
            "type": type_id,
            "annual_flow_ton": _float(flow),
            "annual_share_pct": _float(flow) / total_flow * 100.0 if total_flow else 0.0,
            "peak_capacity_load_ton": _float(peak_load_by_type.get(type_id)),
        }
        for type_id, flow in annual_flow_by_type.items()
    ]

    checks = [
        {
            "id": "solver_status",
            "state": (
                "gap_satisfied"
                if solver.get("status_name") == "OPTIMAL"
                else "feasible_gap_open"
                if int(_float(solver.get("sol_count"))) > 0
                else "missing_solution"
            ),
            "detail": (
                f"status={solver.get('status_name')}, sol_count={int(_float(solver.get('sol_count')))}, "
                f"objective={_float(solver.get('objective')):.3f}, "
                f"bound={_float(solver.get('objective_bound')):.3f}, "
                f"gap={_float(solver.get('mip_gap_pct')):.4f}%"
            ),
            "boundary": "A time-limit incumbent is useful evidence, but it is not a proven optimum.",
        },
        {
            "id": "capacity_semantics",
            "state": "corrected" if summary.get("capacity_semantics") == "peak_inventory_from_annual_flow" else "needs_attention",
            "detail": (
                f"peak_load={_float(summary.get('total_peak_capacity_load_ton')):.3f}t, "
                f"installed_capacity={_float(summary.get('installed_capacity_ton')):.3f}t"
            ),
            "boundary": "Peak-capacity semantics improve construct validity but still depend on scenario harvest assumptions.",
        },
        {
            "id": "temperature_chain",
            "state": "corrected" if len(summary.get("selected_storage_types", [])) >= 3 else "needs_attention",
            "detail": f"selected_storage_types={summary.get('selected_storage_types', [])}",
            "boundary": "Service channels are auditable assumptions until enterprise sales/processing shares are available.",
        },
        {
            "id": "frozen_cap",
            "state": "corrected" if _float(summary.get("frozen_or_processing_share")) <= 0.1 else "needs_attention",
            "detail": f"frozen_or_processing_share={_float(summary.get('frozen_or_processing_share')):.3f}",
            "boundary": "Frozen flow is capped as processing/fallback, not interpreted as all fresh okra.",
        },
    ]

    report = {
        "source_name": "Baseline v3.0 capacity-chain report",
        "source": "results/baseline_v3_capacity_chain_result.pkl",
        "source_backend": "pickle_report",
        "result_paths": {
            "pickle": str(BASELINE_V3_RESULT_PATH),
            "json": str(BASELINE_V3_REPORT_JSON_PATH),
            "md": str(BASELINE_V3_REPORT_MD_PATH),
        },
        "exists": {
            "pickle": BASELINE_V3_RESULT_PATH.exists(),
            "analysis": bool(analysis),
        },
        "solver": solver,
        "summary": summary,
        "facilities": facilities,
        "channel_mix": channel_mix,
        "checks": checks,
        "risk_response": risk_response,
        "claim_boundary": _solver_claim_boundary(solver),
        "assumptions": analysis.get("assumptions", {}) if isinstance(analysis, dict) else {},
        "research_boundary": (
            "This report packages the v3.0 corrected baseline. It improves capacity and service-chain semantics, "
            "but channel shares remain scenario assumptions until real enterprise or official channel data are ingested."
        ),
    }
    return _json_safe(report)


def write_baseline_v3_capacity_chain_report(out_dir: Path | None = None) -> Dict[str, str]:
    destination = out_dir or RESULTS_ROOT
    destination.mkdir(parents=True, exist_ok=True)
    report = build_baseline_v3_capacity_chain_report()
    json_path = destination / "baseline_v3_capacity_chain_report.json"
    md_path = destination / "baseline_v3_capacity_chain_report.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(
        "\n".join(
            [
                "# Baseline v3.0 Capacity-Chain Report",
                "",
                "## Solver",
                "",
                f"- status: {report.get('solver', {}).get('status_name')}",
                f"- solution_count: {report.get('solver', {}).get('sol_count')}",
                f"- objective: {report.get('solver', {}).get('objective')}",
                f"- objective_bound: {report.get('solver', {}).get('objective_bound')}",
                f"- mip_gap_pct: {report.get('solver', {}).get('mip_gap_pct')}",
                f"- claim_state: {report.get('claim_boundary', {}).get('solver_claim_state')}",
                f"- allowed_claim: {report.get('claim_boundary', {}).get('allowed_claim')}",
                "",
                "## Summary",
                "",
                *[f"- {key}: {value}" for key, value in report.get("summary", {}).items()],
                "",
                "## Checks",
                "",
                *[
                    f"- {item.get('id')}: state={item.get('state')}, detail={item.get('detail')}"
                    for item in report.get("checks", [])
                ],
                "",
                "## Channel Mix",
                "",
                *[
                    (
                        f"- {item.get('type')}: annual_flow={item.get('annual_flow_ton'):.3f}t, "
                        f"share={item.get('annual_share_pct'):.2f}%, peak_load={item.get('peak_capacity_load_ton'):.3f}t"
                    )
                    for item in report.get("channel_mix", [])
                ],
                "",
                "## Boundary",
                "",
                str(report.get("research_boundary", "")),
                "",
            ]
        ),
        encoding="utf-8",
    )
    return {"json_path": str(json_path), "md_path": str(md_path)}
