"""Run or refresh v3.0 gap-closure solver-profile artifacts."""

from __future__ import annotations

import argparse
import json
import pickle
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data_sources.model_v3_gap_closure_report import (  # noqa: E402
    GAP_CLOSURE_ROOT,
    solver_claim_boundary,
    write_model_v3_gap_closure_report,
)
from src.models.v3_solver_profiles import get_v3_solver_profile, list_v3_solver_profiles  # noqa: E402


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


def _write_profile_markdown(run_record: dict[str, Any], path: Path) -> None:
    solver = run_record.get("solver", {})
    summary = run_record.get("summary", {})
    claim = run_record.get("claim_boundary", {})
    path.write_text(
        "\n".join(
            [
                f"# v3.0 Gap-Closure Run: {run_record.get('profile', {}).get('name')}",
                "",
                "## Solver",
                "",
                f"- status: {solver.get('status_name')}",
                f"- objective: {solver.get('objective')}",
                f"- objective_bound: {solver.get('objective_bound')}",
                f"- mip_gap_pct: {solver.get('mip_gap_pct')}",
                f"- elapsed_sec: {run_record.get('elapsed_sec')}",
                f"- claim_state: {claim.get('solver_claim_state')}",
                f"- allowed_claim: {claim.get('allowed_claim')}",
                "",
                "## Summary",
                "",
                *[f"- {key}: {value}" for key, value in summary.items()],
                "",
                "## Boundary",
                "",
                str(run_record.get("research_boundary", "")),
                "",
            ]
        ),
        encoding="utf-8",
    )


def run_profile(profile_name: str, out_dir: Path = GAP_CLOSURE_ROOT, verbose: bool = True) -> dict[str, str]:
    from src.models.single_level_mip_v3_capacity_chain import solve_baseline_v3

    profile = get_v3_solver_profile(profile_name)
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = solve_baseline_v3(
        time_limit=profile.time_limit,
        mip_gap=profile.mip_gap,
        threads=profile.threads,
        solver_params=profile.solver_params,
        verbose=verbose,
    )
    pickle_path = out_dir / f"{profile.name}_result.pkl"
    with pickle_path.open("wb") as handle:
        pickle.dump(payload, handle)

    analysis = payload.get("analysis", {})
    solver = analysis.get("solver", {}) if isinstance(analysis, dict) else {}
    summary = analysis.get("summary", {}) if isinstance(analysis, dict) else {}
    run_record = _json_safe(
        {
            "source_name": f"v3.0 gap-closure run: {profile.name}",
            "source_backend": "gurobi_profile_run",
            "profile": profile.to_dict(),
            "solver": solver,
            "summary": summary,
            "facilities": analysis.get("facilities", []) if isinstance(analysis, dict) else [],
            "channel_mix": [
                {
                    "type": type_id,
                    "annual_flow_ton": flow,
                    "peak_capacity_load_ton": analysis.get("peak_load_by_type", {}).get(type_id),
                }
                for type_id, flow in (analysis.get("annual_flow_by_type", {}) if isinstance(analysis, dict) else {}).items()
            ],
            "claim_boundary": solver_claim_boundary(solver),
            "elapsed_sec": payload.get("elapsed"),
            "result_paths": {
                "pickle": str(pickle_path),
                "json": str(out_dir / f"{profile.name}_run.json"),
                "md": str(out_dir / f"{profile.name}_run.md"),
            },
            "research_boundary": (
                "This is a v3.0 solver-profile experiment for gap closure. It improves optimization evidence only "
                "to the extent indicated by solver status and MIP gap; channel shares remain scenario assumptions."
            ),
        }
    )

    json_path = out_dir / f"{profile.name}_run.json"
    md_path = out_dir / f"{profile.name}_run.md"
    json_path.write_text(json.dumps(run_record, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_profile_markdown(run_record, md_path)
    report_paths = write_model_v3_gap_closure_report(out_dir)
    return {
        "pickle_path": str(pickle_path),
        "json_path": str(json_path),
        "md_path": str(md_path),
        "report_json_path": report_paths["json_path"],
        "report_md_path": report_paths["md_path"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="bound_focus_60s", help="Named profile to run.")
    parser.add_argument("--report-only", action="store_true", help="Only refresh the comparison report.")
    parser.add_argument("--list-profiles", action="store_true", help="Print available profile definitions.")
    parser.add_argument("--quiet", action="store_true", help="Suppress Gurobi output.")
    args = parser.parse_args()

    if args.list_profiles:
        print(json.dumps(list_v3_solver_profiles(), ensure_ascii=False, indent=2))
        return

    if args.report_only:
        paths = write_model_v3_gap_closure_report()
    else:
        paths = run_profile(args.profile, verbose=not args.quiet)
    print(json.dumps(paths, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
