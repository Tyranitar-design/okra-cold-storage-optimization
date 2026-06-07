"""Build a read-only analysis and visualization report from existing results."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict

from src.api.services import load_csv_records, load_json_payload


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESULTS_ROOT = PROJECT_ROOT / "results"
EXPERIMENTS_ROOT = RESULTS_ROOT / "experiments"
SCENARIO_CSV = EXPERIMENTS_ROOT / "scenarios" / "scenario_comparison.csv"
SENSITIVITY_CSV = EXPERIMENTS_ROOT / "sensitivity" / "sensitivity_all.csv"
METHOD_SMOKE_CSV = EXPERIMENTS_ROOT / "method_smoke" / "method_smoke_summary.csv"
BASELINE_REPORT_JSON = RESULTS_ROOT / "baseline_v2_1_report.json"
FIGURES_ROOT = EXPERIMENTS_ROOT / "figures"
ANALYSIS_VISUALIZATION_JSON_PATH = RESULTS_ROOT / "analysis_visualization_report.json"
ANALYSIS_VISUALIZATION_MD_PATH = RESULTS_ROOT / "analysis_visualization_report.md"


def _float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _pct_delta(value: float, baseline: float) -> float:
    if baseline == 0:
        return 0.0
    return (value - baseline) / baseline * 100.0


def _existing_figures() -> list[dict[str, Any]]:
    if not FIGURES_ROOT.exists():
        return []
    figures: list[dict[str, Any]] = []
    for path in sorted(FIGURES_ROOT.rglob("*.png")):
        figures.append(
            {
                "name": path.stem,
                "path": str(path),
                "relative_path": str(path.relative_to(PROJECT_ROOT)),
                "size_bytes": path.stat().st_size,
            }
        )
    return figures


def _scenario_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"count": 0, "items": []}
    costs = [_float(row.get("total_cost")) for row in rows]
    times = [_float(row.get("solve_time_sec")) for row in rows]
    baseline_cost = costs[0]
    items = []
    for row, cost, runtime in zip(rows, costs, times):
        items.append(
            {
                "scenario": row.get("scenario"),
                "candidate_count": int(_float(row.get("candidate_count"))),
                "status_name": row.get("status_name"),
                "total_cost": cost,
                "solve_time_sec": runtime,
                "mip_gap_pct": _float(row.get("mip_gap_pct")),
                "num_facilities": int(_float(row.get("num_facilities"))),
                "open_sites": row.get("open_sites"),
                "cost_delta_pct_vs_first": _pct_delta(cost, baseline_cost),
            }
        )
    return {
        "count": len(rows),
        "items": items,
        "cost_min": min(costs),
        "cost_max": max(costs),
        "cost_spread_pct": _pct_delta(max(costs), min(costs)),
        "runtime_min_sec": min(times),
        "runtime_max_sec": max(times),
        "stable_open_sites": len({row.get("open_sites") for row in rows}) == 1,
        "all_optimal": all(str(row.get("status_name", "")).upper() == "OPTIMAL" for row in rows),
    }


def _sensitivity_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get("sweep_variable", "unknown"))].append(row)

    groups = []
    for variable, group_rows in sorted(grouped.items()):
        costs = [_float(row.get("total_cost")) for row in group_rows]
        runtimes = [_float(row.get("solve_time_sec")) for row in group_rows]
        open_sites = {row.get("open_sites") for row in group_rows}
        groups.append(
            {
                "sweep_variable": variable,
                "count": len(group_rows),
                "sweep_values": [_float(row.get("sweep_value")) for row in group_rows],
                "cost_min": min(costs) if costs else 0,
                "cost_max": max(costs) if costs else 0,
                "cost_spread_pct": _pct_delta(max(costs), min(costs)) if costs else 0,
                "runtime_min_sec": min(runtimes) if runtimes else 0,
                "runtime_max_sec": max(runtimes) if runtimes else 0,
                "stable_open_sites": len(open_sites) == 1,
                "open_site_patterns": sorted(open_sites),
            }
        )
    return {
        "count": len(rows),
        "group_count": len(groups),
        "groups": groups,
        "all_groups_stable_open_sites": all(group["stable_open_sites"] for group in groups) if groups else False,
    }


def _method_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    items = []
    for row in rows:
        items.append(
            {
                "method": row.get("method"),
                "status": row.get("status"),
                "objective": _float(row.get("objective")),
                "metric_1": _float(row.get("metric_1")),
                "metric_2": _float(row.get("metric_2")),
                "runtime_sec": _float(row.get("runtime_sec")),
                "note": row.get("note"),
            }
        )
    return {
        "count": len(rows),
        "items": items,
        "methods": [item["method"] for item in items],
        "has_ai_benders": any(item["method"] == "ai_benders" for item in items),
        "has_spo_pipeline": any(item["method"] == "spo_pipeline" for item in items),
    }


def _baseline_cost_breakdown(baseline: dict[str, Any]) -> list[dict[str, Any]]:
    summary = baseline.get("summary", {}) if isinstance(baseline, dict) else {}
    total = _float(summary.get("total_cost"))
    components = [
        ("fixed_cost", "建设成本"),
        ("operate_cost", "运营成本"),
        ("transport_cost", "运输成本"),
        ("loss_cost", "损耗成本"),
        ("carbon_cost", "碳成本"),
    ]
    return [
        {
            "component": key,
            "label": label,
            "value": _float(summary.get(key)),
            "share_pct": (_float(summary.get(key)) / total * 100.0) if total else 0.0,
        }
        for key, label in components
    ]


def build_analysis_visualization_report() -> Dict[str, Any]:
    scenario_rows = load_csv_records(SCENARIO_CSV)
    sensitivity_rows = load_csv_records(SENSITIVITY_CSV)
    method_rows = load_csv_records(METHOD_SMOKE_CSV)
    baseline_report = load_json_payload(BASELINE_REPORT_JSON) if BASELINE_REPORT_JSON.exists() else {}
    figures = _existing_figures()

    scenario_summary = _scenario_summary(scenario_rows)
    sensitivity_summary = _sensitivity_summary(sensitivity_rows)
    method_summary = _method_summary(method_rows)
    baseline_breakdown = _baseline_cost_breakdown(baseline_report)

    checks = [
        {
            "id": "scenario_analysis",
            "state": "ready" if scenario_summary["count"] >= 4 else "needs_attention",
            "detail": f"rows={scenario_summary['count']}, stable_open_sites={scenario_summary.get('stable_open_sites')}",
            "boundary": "Scenario analysis covers current candidate-set sweeps only.",
        },
        {
            "id": "sensitivity_analysis",
            "state": "ready" if sensitivity_summary["group_count"] >= 4 else "needs_attention",
            "detail": f"rows={sensitivity_summary['count']}, groups={sensitivity_summary['group_count']}",
            "boundary": "Sensitivity analysis covers configured one-factor sweeps, not global uncertainty.",
        },
        {
            "id": "method_smoke_analysis",
            "state": "ready" if method_summary["count"] >= 5 else "needs_attention",
            "detail": f"methods={method_summary['methods']}",
            "boundary": "Method smoke proves runnable prototypes, not full-scale algorithm dominance.",
        },
        {
            "id": "figure_assets",
            "state": "ready" if len(figures) >= 8 else "needs_attention",
            "detail": f"figures={len(figures)}",
            "boundary": "Existing figures are useful evidence assets but still require final visual QA before manuscript submission.",
        },
    ]

    return {
        "source_name": "analysis visualization report",
        "source_backend": "existing_result_files",
        "result_paths": {
            "json": str(ANALYSIS_VISUALIZATION_JSON_PATH),
            "md": str(ANALYSIS_VISUALIZATION_MD_PATH),
            "scenario_csv": str(SCENARIO_CSV),
            "sensitivity_csv": str(SENSITIVITY_CSV),
            "method_smoke_csv": str(METHOD_SMOKE_CSV),
            "figures_root": str(FIGURES_ROOT),
        },
        "summary": {
            "scenario_count": scenario_summary["count"],
            "sensitivity_row_count": sensitivity_summary["count"],
            "sensitivity_group_count": sensitivity_summary["group_count"],
            "method_count": method_summary["count"],
            "figure_count": len(figures),
            "scenario_cost_spread_pct": scenario_summary.get("cost_spread_pct", 0),
            "scenario_stable_open_sites": scenario_summary.get("stable_open_sites", False),
            "sensitivity_all_groups_stable_open_sites": sensitivity_summary.get("all_groups_stable_open_sites", False),
        },
        "scenario": scenario_summary,
        "sensitivity": sensitivity_summary,
        "methods": method_summary,
        "baseline_cost_breakdown": baseline_breakdown,
        "figures": figures,
        "checks": checks,
        "research_boundary": (
            "This report packages existing scenario, sensitivity, method smoke, baseline, and figure assets for MIS visualization. "
            "It does not rerun optimization and does not extend conclusions beyond the current result files."
        ),
    }


def write_analysis_visualization_report(report: Dict[str, Any], out_dir: Path | None = None) -> Dict[str, str]:
    destination = out_dir or RESULTS_ROOT
    destination.mkdir(parents=True, exist_ok=True)
    json_path = destination / "analysis_visualization_report.json"
    md_path = destination / "analysis_visualization_report.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(
        "\n".join(
            [
                "# Analysis Visualization Report",
                "",
                "## Summary",
                "",
                *[f"- {key}: {value}" for key, value in report.get("summary", {}).items()],
                "",
                "## Checks",
                "",
                *[
                    f"- {item.get('id', '')}: state={item.get('state', '')}, detail={item.get('detail', '')}"
                    for item in report.get("checks", [])
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
