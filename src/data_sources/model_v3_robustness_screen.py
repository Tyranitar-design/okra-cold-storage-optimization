"""Solver-free v3.0 robustness screen for scenario and sensitivity variants."""

from __future__ import annotations

import csv
import json
import math
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Dict

from src.models.capacity_chain_assumptions import (
    CapacityChainAssumptions,
    ChannelAssumption,
    default_assumptions,
    peak_capacity_load,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = PROJECT_ROOT / "data"
RESULTS_ROOT = PROJECT_ROOT / "results" / "experiments" / "model_v3_robustness_screen"
ROBUSTNESS_REPORT_JSON_PATH = RESULTS_ROOT / "model_v3_robustness_screen_report.json"
ROBUSTNESS_REPORT_MD_PATH = RESULTS_ROOT / "model_v3_robustness_screen_report.md"


@dataclass(frozen=True)
class RobustnessVariant:
    name: str
    category: str
    description: str
    harvest_window_days: float | None = None
    harvest_peak_factor: float | None = None
    max_facilities: int | None = None
    channel_shares: dict[str, float] | None = None


ROBUSTNESS_VARIANTS: tuple[RobustnessVariant, ...] = (
    RobustnessVariant(
        name="baseline_reference",
        category="baseline",
        description="Current v3.0 assumptions used by the gap-closure run.",
    ),
    RobustnessVariant(
        name="peak_factor_low_1_4",
        category="harvest_peak_factor",
        description="Lower harvest concentration stress screen.",
        harvest_peak_factor=1.4,
    ),
    RobustnessVariant(
        name="peak_factor_high_2_2",
        category="harvest_peak_factor",
        description="Higher harvest concentration stress screen.",
        harvest_peak_factor=2.2,
    ),
    RobustnessVariant(
        name="harvest_window_short_60d",
        category="harvest_window",
        description="Shorter harvest window raises peak inventory pressure.",
        harvest_window_days=60.0,
    ),
    RobustnessVariant(
        name="harvest_window_long_120d",
        category="harvest_window",
        description="Longer harvest window lowers peak inventory pressure.",
        harvest_window_days=120.0,
    ),
    RobustnessVariant(
        name="max_facilities_tight_5",
        category="facility_limit",
        description="Tighter facility-count policy screen.",
        max_facilities=5,
    ),
    RobustnessVariant(
        name="fresh_heavy_cold70_ca20_frozen10",
        category="channel_share",
        description="Fresh-market heavy downstream share screen.",
        channel_shares={"cold": 0.70, "ca": 0.20, "frozen": 0.10},
    ),
    RobustnessVariant(
        name="processing_heavy_cold50_ca30_frozen20",
        category="channel_share",
        description="Higher processing/frozen fallback share screen.",
        channel_shares={"cold": 0.50, "ca": 0.30, "frozen": 0.20},
    ),
    RobustnessVariant(
        name="ca_heavy_cold50_ca40_frozen10",
        category="channel_share",
        description="Higher controlled-atmosphere holding share screen.",
        channel_shares={"cold": 0.50, "ca": 0.40, "frozen": 0.10},
    ),
)


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
    params_path = data_dir / "params.json"
    return {
        "nodes": _read_csv(data_dir / "nodes.csv"),
        "time_matrix": _read_matrix(data_dir / "transport_time_matrix.csv"),
        "params": json.loads(params_path.read_text(encoding="utf-8")) if params_path.exists() else {},
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


def _precool_uncovered_count(
    demand_rows: list[dict[str, str]],
    candidate_ids: list[str],
    time_matrix: dict[str, dict[str, float]],
    limit_h: float,
) -> int:
    uncovered = 0
    for row in demand_rows:
        demand_id = str(row.get("node_id"))
        feasible = any(
            _float(time_matrix.get(demand_id, {}).get(site), default=math.inf) <= limit_h
            for site in candidate_ids
        )
        if not feasible:
            uncovered += 1
    return uncovered


def _apply_variant(base: CapacityChainAssumptions, variant: RobustnessVariant) -> CapacityChainAssumptions:
    channels: tuple[ChannelAssumption, ...] = base.channels
    if variant.channel_shares:
        channels = tuple(
            replace(channel, annual_share=variant.channel_shares.get(channel.type_id, channel.annual_share))
            for channel in channels
        )
    return replace(
        base,
        harvest_window_days=variant.harvest_window_days or base.harvest_window_days,
        harvest_peak_factor=variant.harvest_peak_factor or base.harvest_peak_factor,
        max_facilities=variant.max_facilities or base.max_facilities,
        channels=channels,
    )


def _screen_variant(
    variant: RobustnessVariant,
    assumptions: CapacityChainAssumptions,
    total_production_ton: float,
    max_capacity: dict[str, float],
    precool_uncovered_count: int,
) -> dict[str, Any]:
    downstream_share_sum = sum(channel.annual_share for channel in assumptions.channels if channel.type_id != "precool")
    service_share_sum = sum(channel.annual_share for channel in assumptions.channels)
    channel_rows: list[dict[str, Any]] = []
    lower_bound_facilities = 0
    total_peak_load = 0.0
    for channel in assumptions.channels:
        channel_peak = peak_capacity_load(total_production_ton, channel, assumptions)
        total_peak_load += channel_peak
        max_capacity_ton = max_capacity.get(channel.type_id, 0.0)
        min_facilities = math.ceil(channel_peak / max_capacity_ton) if max_capacity_ton else math.inf
        lower_bound_facilities += int(min_facilities) if math.isfinite(min_facilities) else assumptions.max_facilities + 1
        channel_rows.append(
            {
                "type": channel.type_id,
                "annual_share": channel.annual_share,
                "annual_flow_ton": total_production_ton * channel.annual_share,
                "storage_days": channel.storage_days,
                "peak_capacity_load_ton": channel_peak,
                "max_capacity_level_ton": max_capacity_ton,
                "min_facilities_lower_bound": int(min_facilities) if math.isfinite(min_facilities) else None,
            }
        )

    facility_pressure = lower_bound_facilities / assumptions.max_facilities if assumptions.max_facilities else math.inf
    share_ok = abs(downstream_share_sum - 1.0) <= 1e-9
    capacity_ok = lower_bound_facilities <= assumptions.max_facilities
    precool_ok = precool_uncovered_count == 0
    screen_state = "pass" if share_ok and capacity_ok and precool_ok else "fail"
    if screen_state == "pass" and (facility_pressure >= 0.75 or variant.category == "channel_share"):
        screen_state = "watch"
    follow_up_priority = "high" if screen_state == "fail" else "medium" if screen_state == "watch" else "low"

    return {
        "name": variant.name,
        "category": variant.category,
        "description": variant.description,
        "screen_state": screen_state,
        "follow_up_priority": follow_up_priority,
        "needs_solver_run": follow_up_priority in {"high", "medium"},
        "assumption_overrides": {
            "harvest_window_days": variant.harvest_window_days,
            "harvest_peak_factor": variant.harvest_peak_factor,
            "max_facilities": variant.max_facilities,
            "channel_shares": variant.channel_shares,
        },
        "summary": {
            "total_annual_production_ton": total_production_ton,
            "total_service_annual_flow_ton": total_production_ton * service_share_sum,
            "downstream_share_sum": downstream_share_sum,
            "service_share_sum": service_share_sum,
            "total_peak_capacity_load_ton": total_peak_load,
            "lower_bound_facilities": lower_bound_facilities,
            "max_facilities": assumptions.max_facilities,
            "facility_pressure": facility_pressure,
            "precool_uncovered_count": precool_uncovered_count,
        },
        "channel_capacity_screen": channel_rows,
    }


def build_model_v3_robustness_screen_report(data_dir: Path | None = None) -> Dict[str, Any]:
    data_root = data_dir or DATA_ROOT
    inputs = _load_inputs(data_root)
    nodes = inputs["nodes"]
    demand_rows = _demand_rows(nodes)
    candidate_ids = _candidate_ids(nodes)
    params = inputs["params"]
    total_production_ton = sum(_float(row.get("okra_production_ton")) for row in demand_rows)
    max_capacity = _max_capacity_by_type(params)
    precool_limit_h = _float(params.get("okra_preservation", {}).get("precool_time_limit_h"), default=2.0)
    precool_uncovered_count = _precool_uncovered_count(
        demand_rows,
        candidate_ids,
        inputs["time_matrix"],
        precool_limit_h,
    )
    base_assumptions = default_assumptions()
    variants = [
        _screen_variant(
            variant,
            _apply_variant(base_assumptions, variant),
            total_production_ton,
            max_capacity,
            precool_uncovered_count,
        )
        for variant in ROBUSTNESS_VARIANTS
    ]
    state_counts: dict[str, int] = {}
    priority_counts: dict[str, int] = {}
    for variant in variants:
        state_counts[variant["screen_state"]] = state_counts.get(variant["screen_state"], 0) + 1
        priority_counts[variant["follow_up_priority"]] = priority_counts.get(variant["follow_up_priority"], 0) + 1
    recommended_solver_queue = [
        {
            "name": variant["name"],
            "category": variant["category"],
            "priority": variant["follow_up_priority"],
            "reason": (
                f"screen_state={variant['screen_state']}; "
                f"facility_pressure={variant['summary']['facility_pressure']:.3f}"
            ),
        }
        for variant in variants
        if variant["needs_solver_run"]
    ]
    report = {
        "source_name": "Model v3.0 robustness screen",
        "source_backend": "solver_free_robustness_screen",
        "source": "data/nodes.csv; data/transport_time_matrix.csv; data/params.json; src/models/capacity_chain_assumptions.py",
        "result_paths": {
            "json": str(ROBUSTNESS_REPORT_JSON_PATH),
            "md": str(ROBUSTNESS_REPORT_MD_PATH),
        },
        "exists": {
            "json": ROBUSTNESS_REPORT_JSON_PATH.exists(),
            "md": ROBUSTNESS_REPORT_MD_PATH.exists(),
        },
        "summary": {
            "variant_count": len(variants),
            "pass_count": state_counts.get("pass", 0),
            "watch_count": state_counts.get("watch", 0),
            "fail_count": state_counts.get("fail", 0),
            "high_priority_count": priority_counts.get("high", 0),
            "medium_priority_count": priority_counts.get("medium", 0),
            "low_priority_count": priority_counts.get("low", 0),
            "recommended_solver_run_count": len(recommended_solver_queue),
            "total_annual_production_ton": total_production_ton,
            "candidate_count": len(candidate_ids),
            "demand_node_count": len(demand_rows),
            "precool_limit_h": precool_limit_h,
            "precool_uncovered_count": precool_uncovered_count,
        },
        "variants": variants,
        "recommended_solver_queue": recommended_solver_queue,
        "assumptions": {
            "base": {
                "harvest_window_days": base_assumptions.harvest_window_days,
                "harvest_peak_factor": base_assumptions.harvest_peak_factor,
                "max_facilities": base_assumptions.max_facilities,
                "channels": [asdict(channel) for channel in base_assumptions.channels],
            },
        },
        "research_boundary": (
            "This report is a solver-free v3.0 robustness screen. It prioritizes variants for future Gurobi runs "
            "but does not provide scenario optimality, cost deltas, or enterprise validation."
        ),
        "next_action": (
            "Run long Gurobi profiles for medium/high-priority variants after choosing the most paper-relevant stress cases."
        ),
    }
    return _json_safe(report)


def write_model_v3_robustness_screen_report(out_dir: Path | None = None) -> Dict[str, str]:
    destination = out_dir or RESULTS_ROOT
    destination.mkdir(parents=True, exist_ok=True)
    report = build_model_v3_robustness_screen_report()
    json_path = destination / "model_v3_robustness_screen_report.json"
    md_path = destination / "model_v3_robustness_screen_report.md"
    report["exists"]["json"] = True
    report["exists"]["md"] = True
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(
        "\n".join(
            [
                "# Model v3.0 Robustness Screen",
                "",
                "## Summary",
                "",
                *[f"- {key}: {value}" for key, value in report.get("summary", {}).items()],
                "",
                "## Variants",
                "",
                *[
                    (
                        f"- {item.get('name')}: state={item.get('screen_state')}, "
                        f"priority={item.get('follow_up_priority')}, "
                        f"peak_load={item.get('summary', {}).get('total_peak_capacity_load_ton')}"
                    )
                    for item in report.get("variants", [])
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


def build_whatif_screen(
    max_facilities: int | None = None,
    channel_shares: dict[str, float] | None = None,
    carbon_price: float | None = None,
    harvest_peak_factor: float | None = None,
    data_dir: Path | None = None,
) -> Dict[str, Any]:
    """Run the solver-free v3.0 screen for one user-tuned parameter set.

    Reuses the same capacity-pressure logic as the robustness screen so the
    What-If panel shows real, reproducible siting feasibility — not a guess.
    Returns the tuned screen alongside the baseline for side-by-side display.
    """
    data_root = data_dir or DATA_ROOT
    inputs = _load_inputs(data_root)
    nodes = inputs["nodes"]
    demand_rows = _demand_rows(nodes)
    candidate_ids = _candidate_ids(nodes)
    params = inputs["params"]
    total_production_ton = sum(_float(row.get("okra_production_ton")) for row in demand_rows)
    max_capacity = _max_capacity_by_type(params)
    precool_limit_h = _float(params.get("okra_preservation", {}).get("precool_time_limit_h"), default=2.0)
    precool_uncovered_count = _precool_uncovered_count(
        demand_rows, candidate_ids, inputs["time_matrix"], precool_limit_h
    )
    base_assumptions = default_assumptions()

    # Baseline screen (current v3.0 assumptions, no overrides).
    baseline_variant = RobustnessVariant(
        name="baseline", category="baseline", description="当前 v3.0 基线假设"
    )
    baseline_screen = _screen_variant(
        baseline_variant, base_assumptions, total_production_ton, max_capacity, precool_uncovered_count
    )

    # Normalise downstream channel shares so cold+ca+frozen sum to 1.0 (precool stays 1.0).
    normalised_shares = None
    if channel_shares:
        cleaned = {k: max(0.0, _float(v)) for k, v in channel_shares.items() if k in {"cold", "ca", "frozen"}}
        total = sum(cleaned.values())
        if total > 0:
            normalised_shares = {k: round(v / total, 4) for k, v in cleaned.items()}

    whatif_variant = RobustnessVariant(
        name="whatif",
        category="whatif",
        description="用户自定义 What-If 参数组合",
        max_facilities=int(max_facilities) if max_facilities else None,
        harvest_peak_factor=float(harvest_peak_factor) if harvest_peak_factor else None,
        channel_shares=normalised_shares,
    )
    tuned_assumptions = _apply_variant(base_assumptions, whatif_variant)
    if carbon_price is not None:
        tuned_assumptions = replace(tuned_assumptions, carbon_price=float(carbon_price))
    whatif_screen = _screen_variant(
        whatif_variant, tuned_assumptions, total_production_ton, max_capacity, precool_uncovered_count
    )

    base_lb = baseline_screen["summary"]["lower_bound_facilities"]
    tuned_lb = whatif_screen["summary"]["lower_bound_facilities"]
    base_peak = baseline_screen["summary"]["total_peak_capacity_load_ton"]
    tuned_peak = whatif_screen["summary"]["total_peak_capacity_load_ton"]

    return _json_safe(
        {
            "source": "/api/v1/whatif/screen",
            "source_backend": "solver_free_whatif_screen",
            "inputs": {
                "max_facilities": tuned_assumptions.max_facilities,
                "channel_shares": normalised_shares,
                "carbon_price": tuned_assumptions.carbon_price,
                "harvest_peak_factor": tuned_assumptions.harvest_peak_factor,
            },
            "baseline": baseline_screen,
            "whatif": whatif_screen,
            "delta": {
                "lower_bound_facilities": tuned_lb - base_lb,
                "total_peak_capacity_load_ton": round(tuned_peak - base_peak, 1),
                "screen_state_changed": baseline_screen["screen_state"] != whatif_screen["screen_state"],
                "facility_pressure_delta": round(
                    whatif_screen["summary"]["facility_pressure"] - baseline_screen["summary"]["facility_pressure"], 4
                ),
            },
            "carbon_price_note": (
                "碳价只改变成本目标的权重，不改变这套 solver-free 容量可行性筛选结果；"
                "其对最优选址的影响需运行 Gurobi 求解才能量化。"
            ),
            "research_boundary": (
                "solver-free 容量压力筛选：基于峰值库存 vs 最大容量档推断设施数下界与可行性，"
                "不等于精确最优选址。要得到真实最优解变化，请用实时求解触发器跑 Gurobi。"
            ),
        }
    )
