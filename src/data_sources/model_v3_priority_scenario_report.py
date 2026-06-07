"""Read-only report for real v3.0 priority scenario runs."""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any, Dict

from src.data_sources.model_v3_gap_closure_report import solver_claim_boundary
from src.data_sources.model_v3_robustness_screen import ROBUSTNESS_VARIANTS, build_model_v3_robustness_screen_report
from src.models.capacity_chain_assumptions import CapacityChainAssumptions, ChannelAssumption, default_assumptions
from src.models.v3_solver_profiles import list_v3_solver_profiles


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESULTS_ROOT = PROJECT_ROOT / "results"
PRIORITY_SCENARIO_ROOT = RESULTS_ROOT / "experiments" / "model_v3_priority_scenarios"
PRIORITY_SCENARIO_REPORT_JSON_PATH = PRIORITY_SCENARIO_ROOT / "model_v3_priority_scenario_report.json"
PRIORITY_SCENARIO_REPORT_MD_PATH = PRIORITY_SCENARIO_ROOT / "model_v3_priority_scenario_report.md"
PRIORITY_SCENARIO_TABLE_CSV_PATH = PRIORITY_SCENARIO_ROOT / "model_v3_priority_scenario_table.csv"
PRIORITY_SCENARIO_TABLE_MD_PATH = PRIORITY_SCENARIO_ROOT / "model_v3_priority_scenario_table.md"


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


def resolve_priority_variant(name: str) -> Any:
    for variant in ROBUSTNESS_VARIANTS:
        if variant.name == name:
            return variant
    available = ", ".join(variant.name for variant in ROBUSTNESS_VARIANTS)
    raise ValueError(f"Unknown v3 robustness variant '{name}'. Available variants: {available}")


def assumptions_for_priority_variant(
    name: str,
    base: CapacityChainAssumptions | None = None,
) -> CapacityChainAssumptions:
    variant = resolve_priority_variant(name)
    assumptions = base or default_assumptions()
    channels: tuple[ChannelAssumption, ...] = assumptions.channels
    if variant.channel_shares:
        channels = tuple(
            replace(channel, annual_share=variant.channel_shares.get(channel.type_id, channel.annual_share))
            for channel in channels
        )
    return replace(
        assumptions,
        harvest_window_days=variant.harvest_window_days or assumptions.harvest_window_days,
        harvest_peak_factor=variant.harvest_peak_factor or assumptions.harvest_peak_factor,
        max_facilities=variant.max_facilities or assumptions.max_facilities,
        channels=channels,
    )


def list_priority_variants() -> list[dict[str, Any]]:
    screen = build_model_v3_robustness_screen_report()
    queued = {item.get("name"): item for item in screen.get("recommended_solver_queue", [])}
    return [
        {
            "name": variant.name,
            "category": variant.category,
            "description": variant.description,
            "queued_priority": queued.get(variant.name, {}).get("priority"),
            "queued_reason": queued.get(variant.name, {}).get("reason"),
            "assumption_overrides": {
                "harvest_window_days": variant.harvest_window_days,
                "harvest_peak_factor": variant.harvest_peak_factor,
                "max_facilities": variant.max_facilities,
                "channel_shares": variant.channel_shares,
            },
        }
        for variant in ROBUSTNESS_VARIANTS
    ]


def priority_scenario_claim_boundary(solver: dict[str, Any]) -> dict[str, str]:
    claim = dict(solver_claim_boundary(solver))
    claim["allowed_claim"] = (
        claim.get("allowed_claim", "")
        .replace("gap-closure run", "priority scenario run")
        .replace("gap-closure solution claim", "priority scenario solution claim")
    )
    return claim


def run_key(variant_name: str, profile_name: str) -> str:
    return f"{variant_name}_{profile_name}"


def priority_run_artifact_paths(root: Path = PRIORITY_SCENARIO_ROOT) -> list[Path]:
    if not root.exists():
        return []
    return sorted(root.glob("*_run.json"))


def load_priority_scenario_runs(root: Path = PRIORITY_SCENARIO_ROOT) -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    for path in priority_run_artifact_paths(root):
        payload = _read_json(path)
        if payload:
            payload.setdefault("artifact_path", str(path))
            runs.append(payload)
    return runs


def _best_by_variant(
    runs: list[dict[str, Any]],
    variant_order: dict[str, int] | None = None,
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for run in runs:
        grouped.setdefault(run.get("variant", {}).get("name", "unknown"), []).append(run)

    best_rows: list[dict[str, Any]] = []
    order = variant_order or {}
    for variant_name, variant_runs in sorted(grouped.items(), key=lambda item: (order.get(item[0], 10_000), item[0])):
        feasible = [run for run in variant_runs if run.get("solver", {}).get("objective") not in (None, "")]
        if not feasible:
            best = variant_runs[0]
        else:
            best = min(feasible, key=lambda item: _float(item.get("solver", {}).get("objective"), default=float("inf")))
        best_rows.append(
            {
                "variant": variant_name,
                "profile": best.get("profile", {}).get("name"),
                "status": best.get("solver", {}).get("status_name"),
                "objective": best.get("solver", {}).get("objective"),
                "objective_bound": best.get("solver", {}).get("objective_bound"),
                "mip_gap_pct": best.get("solver", {}).get("mip_gap_pct"),
                "claim_state": best.get("claim_boundary", {}).get("solver_claim_state"),
            }
        )
    return best_rows


def _rounded(value: Any, digits: int = 4) -> float | None:
    if value in (None, ""):
        return None
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


def _selected_storage_types_text(summary: dict[str, Any]) -> str:
    value = summary.get("selected_storage_types", [])
    if isinstance(value, (list, tuple)):
        return ";".join(str(item) for item in value if item not in (None, ""))
    return str(value or "")


def _render_markdown_table(columns: list[str], rows: list[dict[str, Any]]) -> str:
    header = "| " + " | ".join(columns) + " |"
    separator = "| " + " | ".join(["---"] * len(columns)) + " |"
    body = [
        "| "
        + " | ".join("" if row.get(column) in (None, "") else str(row.get(column)) for column in columns)
        + " |"
        for row in rows
    ]
    return "\n".join([header, separator, *body]) if body else "\n".join([header, separator])


def _write_csv(path: Path, columns: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})


def _paper_table_rows(
    runs: list[dict[str, Any]],
    best_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    runs_by_variant: dict[str, list[dict[str, Any]]] = {}
    for run in runs:
        variant_name = str(run.get("variant", {}).get("name") or "")
        runs_by_variant.setdefault(variant_name, []).append(run)

    rows: list[dict[str, Any]] = []
    for rank, best in enumerate(best_rows, start=1):
        variant_name = str(best.get("variant") or "")
        profile_name = str(best.get("profile") or "")
        candidate_runs = runs_by_variant.get(variant_name, [])
        run = next(
            (
                item
                for item in candidate_runs
                if str(item.get("profile", {}).get("name") or "") == profile_name
            ),
            candidate_runs[0] if candidate_runs else {},
        )
        variant = run.get("variant", {}) if run else {}
        summary = run.get("summary", {}) if run else {}
        rows.append(
            {
                "rank": rank,
                "variant": variant_name,
                "category": variant.get("category"),
                "profile": profile_name,
                "status": best.get("status"),
                "objective": _rounded(best.get("objective")),
                "objective_bound": _rounded(best.get("objective_bound")),
                "mip_gap_pct": _rounded(best.get("mip_gap_pct")),
                "claim_state": best.get("claim_state"),
                "num_facilities": summary.get("num_facilities"),
                "selected_storage_types": _selected_storage_types_text(summary),
            }
        )
    return rows


def _sort_runs_by_report_order(
    runs: list[dict[str, Any]],
    queued_variants: list[dict[str, Any]],
    priority_variants: list[dict[str, Any]],
    profiles: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    queued_order = {str(item.get("name")): idx for idx, item in enumerate(queued_variants)}
    variant_order = {str(item.get("name")): idx for idx, item in enumerate(priority_variants)}
    profile_order = {str(item.get("name")): idx for idx, item in enumerate(profiles)}

    def sort_key(run: dict[str, Any]) -> tuple[int, int, int, str]:
        variant_name = str(run.get("variant", {}).get("name") or "")
        profile_name = str(run.get("profile", {}).get("name") or "")
        return (
            0 if variant_name in queued_order else 1,
            queued_order.get(variant_name, variant_order.get(variant_name, 10_000)),
            profile_order.get(profile_name, 10_000),
            str(run.get("run_key") or run.get("artifact_path") or ""),
        )

    return sorted(runs, key=sort_key)


def build_model_v3_priority_scenario_report(root: Path | None = None) -> Dict[str, Any]:
    report_root = root or PRIORITY_SCENARIO_ROOT
    profiles = list_v3_solver_profiles()
    priority_variants = list_priority_variants()
    queued = [item for item in priority_variants if item.get("queued_priority")]
    runs = _sort_runs_by_report_order(
        load_priority_scenario_runs(report_root),
        queued_variants=queued,
        priority_variants=priority_variants,
        profiles=profiles,
    )
    status_counts: dict[str, int] = {}
    claim_counts: dict[str, int] = {}
    for run in runs:
        status = str(run.get("solver", {}).get("status_name") or "MISSING")
        claim = str(run.get("claim_boundary", {}).get("solver_claim_state") or "missing")
        status_counts[status] = status_counts.get(status, 0) + 1
        claim_counts[claim] = claim_counts.get(claim, 0) + 1

    run_variant_names = sorted({run.get("variant", {}).get("name") for run in runs if run.get("variant", {}).get("name")})
    missing_queued = [item for item in queued if item.get("name") not in set(run_variant_names)]
    variant_order = {str(item.get("name")): idx for idx, item in enumerate(queued)}
    best_rows = _best_by_variant(runs, variant_order=variant_order)

    report = {
        "source_name": "Model v3.0 priority scenario report",
        "source_backend": "v3_priority_scenario_artifacts",
        "result_paths": {
            "json": str(PRIORITY_SCENARIO_REPORT_JSON_PATH),
            "md": str(PRIORITY_SCENARIO_REPORT_MD_PATH),
            "artifact_dir": str(report_root),
        },
        "exists": {
            "artifact_dir": report_root.exists(),
            "report_json": PRIORITY_SCENARIO_REPORT_JSON_PATH.exists(),
            "report_md": PRIORITY_SCENARIO_REPORT_MD_PATH.exists(),
        },
        "profiles": profiles,
        "priority_variants": priority_variants,
        "queued_variants": queued,
        "runs": runs,
        "best_by_variant": best_rows,
        "summary": {
            "queued_variant_count": len(queued),
            "run_count": len(runs),
            "variant_count": len(run_variant_names),
            "gap_satisfied_count": claim_counts.get("gap_satisfied", 0),
            "time_limit_count": status_counts.get("TIME_LIMIT", 0),
            "no_feasible_solution_count": claim_counts.get("no_feasible_solution", 0),
            "status_counts": status_counts,
            "claim_counts": claim_counts,
            "missing_queued_variant_count": len(missing_queued),
            "first_missing_queued_variant": missing_queued[0].get("name") if missing_queued else None,
        },
        "research_boundary": (
            "Priority scenario runs are real v3.0 optimization artifacts for selected robustness-screen variants. "
            "They support scenario evidence only according to solver status and MIP gap; channel shares and harvest "
            "settings remain auditable scenario assumptions until enterprise records are ingested."
        ),
        "next_action": (
            f"Run the next queued variant: {missing_queued[0].get('name')}."
            if missing_queued
            else "All queued variants have at least one materialized run; compare gaps before authorizing longer profiles."
        ),
    }
    return _json_safe(report)


def write_model_v3_priority_scenario_report(out_dir: Path | None = None) -> Dict[str, str]:
    destination = out_dir or PRIORITY_SCENARIO_ROOT
    destination.mkdir(parents=True, exist_ok=True)
    report = build_model_v3_priority_scenario_report(destination)
    json_path = destination / "model_v3_priority_scenario_report.json"
    md_path = destination / "model_v3_priority_scenario_report.md"
    report["exists"]["report_json"] = True
    report["exists"]["report_md"] = True
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(
        "\n".join(
            [
                "# Model v3.0 Priority Scenario Report",
                "",
                "## Summary",
                "",
                *[f"- {key}: {value}" for key, value in report.get("summary", {}).items()],
                "",
                "## Runs",
                "",
                *[
                    (
                        f"- {run.get('run_key')}: variant={run.get('variant', {}).get('name')}, "
                        f"profile={run.get('profile', {}).get('name')}, "
                        f"status={run.get('solver', {}).get('status_name')}, "
                        f"gap={run.get('solver', {}).get('mip_gap_pct')}, "
                        f"claim={run.get('claim_boundary', {}).get('solver_claim_state')}"
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
