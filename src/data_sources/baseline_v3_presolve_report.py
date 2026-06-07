"""Build a solver-free presolve readiness report for the v3.0 capacity-chain model."""

from __future__ import annotations

import csv
import json
import math
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict

from src.models.capacity_chain_assumptions import default_assumptions, peak_capacity_load


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = PROJECT_ROOT / "data"
RESULTS_ROOT = PROJECT_ROOT / "results"
BASELINE_V3_RESULT_PATH = RESULTS_ROOT / "baseline_v3_capacity_chain_result.pkl"
BASELINE_V3_REPORT_JSON_PATH = RESULTS_ROOT / "baseline_v3_capacity_chain_report.json"
BASELINE_V3_PRESOLVE_REPORT_JSON_PATH = RESULTS_ROOT / "baseline_v3_presolve_report.json"
BASELINE_V3_PRESOLVE_REPORT_MD_PATH = RESULTS_ROOT / "baseline_v3_presolve_report.md"


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


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _read_matrix(path: Path) -> dict[str, dict[str, float]]:
    rows = _read_csv(path)
    matrix: dict[str, dict[str, float]] = {}
    for row in rows:
        node_id = row.get("") or row.get("node_id") or row.get("origin")
        if not node_id:
            continue
        matrix[node_id] = {key: _float(value) for key, value in row.items() if key}
    return matrix


def _load_inputs(data_dir: Path = DATA_ROOT) -> dict[str, Any]:
    nodes = _read_csv(data_dir / "nodes.csv")
    params_path = data_dir / "params.json"
    params = json.loads(params_path.read_text(encoding="utf-8")) if params_path.exists() else {}
    return {
        "nodes": nodes,
        "time_matrix": _read_matrix(data_dir / "transport_time_matrix.csv"),
        "params": params,
    }


def _max_capacity_by_type(params: dict[str, Any]) -> dict[str, float]:
    storage_types = params.get("cold_storage_types", {}) if isinstance(params, dict) else {}
    max_by_type: dict[str, float] = {}
    for type_id, detail in storage_types.items():
        levels = detail.get("capacity_levels", []) if isinstance(detail, dict) else []
        max_by_type[type_id] = max((_float(level) for level in levels), default=0.0)
    return max_by_type


def _candidate_ids(nodes: list[dict[str, str]]) -> list[str]:
    return [
        str(row.get("node_id"))
        for row in nodes
        if str(row.get("is_candidate", "")).strip().lower() in {"true", "1", "yes"}
    ]


def _demand_rows(nodes: list[dict[str, str]]) -> list[dict[str, str]]:
    return [row for row in nodes if _float(row.get("okra_production_ton")) > 0.0]


def _precool_uncovered_demands(
    demand_rows: list[dict[str, str]],
    candidate_ids: list[str],
    time_matrix: dict[str, dict[str, float]],
    limit_h: float,
) -> list[dict[str, Any]]:
    uncovered: list[dict[str, Any]] = []
    for row in demand_rows:
        demand_id = str(row.get("node_id"))
        feasible_sites = [
            site
            for site in candidate_ids
            if _float(time_matrix.get(demand_id, {}).get(site), default=math.inf) <= limit_h
        ]
        if not feasible_sites:
            finite_times = [
                _float(time_matrix.get(demand_id, {}).get(site), default=math.inf)
                for site in candidate_ids
            ]
            finite_times = [value for value in finite_times if math.isfinite(value)]
            uncovered.append(
                {
                    "demand_id": demand_id,
                    "name": row.get("name", demand_id),
                    "min_travel_time_h": min(finite_times) if finite_times else None,
                    "limit_h": limit_h,
                }
            )
    return uncovered


def build_baseline_v3_presolve_report(data_dir: Path | None = None) -> Dict[str, Any]:
    """Compute static feasibility and claim-boundary checks before the v3 solver run."""

    data_root = data_dir or DATA_ROOT
    inputs = _load_inputs(data_root)
    nodes = inputs["nodes"]
    params = inputs["params"]
    assumptions = default_assumptions()
    demand_rows = _demand_rows(nodes)
    candidate_ids = _candidate_ids(nodes)
    total_production_ton = sum(_float(row.get("okra_production_ton")) for row in demand_rows)
    max_capacity = _max_capacity_by_type(params)
    downstream_share_sum = sum(channel.annual_share for channel in assumptions.channels if channel.type_id != "precool")
    service_share_sum = sum(channel.annual_share for channel in assumptions.channels)
    precool_limit_h = _float(
        params.get("okra_preservation", {}).get("precool_time_limit_h"),
        default=2.0,
    )
    uncovered_demands = _precool_uncovered_demands(
        demand_rows,
        candidate_ids,
        inputs["time_matrix"],
        limit_h=precool_limit_h,
    )

    channel_rows: list[dict[str, Any]] = []
    lower_bound_facilities = 0
    for channel in assumptions.channels:
        channel_peak = peak_capacity_load(total_production_ton, channel, assumptions)
        max_capacity_ton = max_capacity.get(channel.type_id, 0.0)
        min_facilities = math.ceil(channel_peak / max_capacity_ton) if max_capacity_ton else math.inf
        lower_bound_facilities += int(min_facilities) if math.isfinite(min_facilities) else assumptions.max_facilities + 1
        channel_rows.append(
            {
                "type": channel.type_id,
                "label": channel.label,
                "annual_share": channel.annual_share,
                "annual_flow_ton": total_production_ton * channel.annual_share,
                "storage_days": channel.storage_days,
                "peak_capacity_load_ton": channel_peak,
                "max_capacity_level_ton": max_capacity_ton,
                "min_facilities_lower_bound": int(min_facilities) if math.isfinite(min_facilities) else None,
                "capacity_screen_state": "pass" if math.isfinite(min_facilities) and min_facilities <= assumptions.max_facilities else "fail",
                "channel_note": channel.channel_note,
            }
        )

    result_exists = BASELINE_V3_RESULT_PATH.exists()
    report_exists = BASELINE_V3_REPORT_JSON_PATH.exists()
    capacity_feasible = lower_bound_facilities <= assumptions.max_facilities
    downstream_share_ok = abs(downstream_share_sum - 1.0) <= 1e-9
    precool_share_ok = any(channel.type_id == "precool" and abs(channel.annual_share - 1.0) <= 1e-9 for channel in assumptions.channels)
    precool_coverage_ok = len(uncovered_demands) == 0
    solver_artifact_ready = result_exists and report_exists
    solver_readiness_state = "ready_to_authorize_solver_run" if capacity_feasible and downstream_share_ok and precool_share_ok and precool_coverage_ok else "needs_model_or_data_fix"
    if solver_artifact_ready:
        solver_readiness_state = "solver_result_present"

    checks = [
        {
            "id": "downstream_share_sum",
            "state": "pass" if downstream_share_ok else "fail",
            "detail": f"cold+ca+frozen={downstream_share_sum:.3f}; precool is first-mile service, not a final product channel",
            "boundary": "Total service flow includes mandatory precooling plus downstream product channels, so it can exceed annual production.",
        },
        {
            "id": "capacity_lower_bound",
            "state": "pass" if capacity_feasible else "fail",
            "detail": f"lower_bound_facilities={lower_bound_facilities}, max_facilities={assumptions.max_facilities}",
            "boundary": "This is a necessary static screen, not proof that the full MIP is feasible or optimal.",
        },
        {
            "id": "precool_time_coverage",
            "state": "pass" if precool_coverage_ok else "fail",
            "detail": f"uncovered_demand_nodes={len(uncovered_demands)}, limit_h={precool_limit_h:.2f}",
            "boundary": "Checks whether every demand node has at least one candidate within the hard precooling time limit.",
        },
        {
            "id": "solver_artifact_state",
            "state": "pass" if solver_artifact_ready else "pending",
            "detail": f"result_pickle={result_exists}, report_json={report_exists}",
            "boundary": (
                "Artifact presence only allows solver-status review; any v3.0 optimum claim still depends on "
                "the reported solver status and MIP gap."
            ),
        },
    ]

    next_action = (
        "Review the v3.0 solver report status and MIP gap before making any paper-level optimality claim."
        if solver_artifact_ready
        else "Run python scripts/run_baseline_v3_capacity_chain.py after execution approval to generate the real v3 solver artifacts."
    )

    report = {
        "source_name": "Baseline v3.0 presolve readiness report",
        "source": "data/nodes.csv; data/transport_time_matrix.csv; data/params.json; src/models/capacity_chain_assumptions.py",
        "source_backend": "static_presolve_report",
        "result_paths": {
            "json": str(BASELINE_V3_PRESOLVE_REPORT_JSON_PATH),
            "md": str(BASELINE_V3_PRESOLVE_REPORT_MD_PATH),
            "solver_pickle": str(BASELINE_V3_RESULT_PATH),
            "solver_report_json": str(BASELINE_V3_REPORT_JSON_PATH),
        },
        "exists": {
            "json": BASELINE_V3_PRESOLVE_REPORT_JSON_PATH.exists(),
            "md": BASELINE_V3_PRESOLVE_REPORT_MD_PATH.exists(),
            "solver_pickle": result_exists,
            "solver_report_json": report_exists,
        },
        "summary": {
            "solver_readiness_state": solver_readiness_state,
            "total_annual_production_ton": total_production_ton,
            "total_service_annual_flow_ton": total_production_ton * service_share_sum,
            "downstream_annual_flow_ton": total_production_ton * downstream_share_sum,
            "service_share_sum": service_share_sum,
            "downstream_share_sum": downstream_share_sum,
            "total_peak_capacity_load_ton": sum(row["peak_capacity_load_ton"] for row in channel_rows),
            "candidate_count": len(candidate_ids),
            "demand_node_count": len(demand_rows),
            "lower_bound_facilities": lower_bound_facilities,
            "max_facilities": assumptions.max_facilities,
            "precool_limit_h": precool_limit_h,
            "precool_uncovered_count": len(uncovered_demands),
            "solver_artifact_ready": solver_artifact_ready,
        },
        "channel_capacity_screen": channel_rows,
        "uncovered_precool_demands": uncovered_demands,
        "checks": checks,
        "assumptions": {
            "harvest_window_days": assumptions.harvest_window_days,
            "harvest_peak_factor": assumptions.harvest_peak_factor,
            "max_facilities": assumptions.max_facilities,
            "channels": [asdict(channel) for channel in assumptions.channels],
        },
        "research_boundary": (
            "This presolve report is a static feasibility and claim-boundary screen. It can support readiness to run "
            "the v3.0 solver, but it is not an optimization result and cannot be cited as a v3.0 optimum."
        ),
        "next_action": next_action,
    }
    return _json_safe(report)


def write_baseline_v3_presolve_report(out_dir: Path | None = None) -> Dict[str, str]:
    destination = out_dir or RESULTS_ROOT
    destination.mkdir(parents=True, exist_ok=True)
    report = build_baseline_v3_presolve_report()
    json_path = destination / "baseline_v3_presolve_report.json"
    md_path = destination / "baseline_v3_presolve_report.md"
    report["exists"]["json"] = True
    report["exists"]["md"] = True
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(
        "\n".join(
            [
                "# Baseline v3.0 Presolve Readiness Report",
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
                "## Channel Capacity Screen",
                "",
                *[
                    (
                        f"- {item.get('type')}: annual_flow={item.get('annual_flow_ton'):.3f}t, "
                        f"peak_load={item.get('peak_capacity_load_ton'):.3f}t, "
                        f"max_capacity={item.get('max_capacity_level_ton'):.3f}t, "
                        f"min_facilities={item.get('min_facilities_lower_bound')}"
                    )
                    for item in report.get("channel_capacity_screen", [])
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
