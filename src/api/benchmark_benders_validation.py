"""Shared validation helpers for benchmark Benders AI-active evidence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESULTS_ROOT = PROJECT_ROOT / "results" / "experiments" / "benchmark_benders_comparison"
SUMMARY_PATH = RESULTS_ROOT / "benchmark_benders_summary.json"
COMPARISON_PATH = RESULTS_ROOT / "benchmark_benders_comparison.csv"
ITERATIONS_PATH = RESULTS_ROOT / "benchmark_benders_iterations.csv"
CUT_SCORES_PATH = RESULTS_ROOT / "benchmark_benders_cut_scores.csv"
VALIDATION_JSON_PATH = RESULTS_ROOT / "ai_active_validation.json"
VALIDATION_MD_PATH = RESULTS_ROOT / "ai_active_validation.md"


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _extract_ai_active_rows(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    summary_rows = payload.get("summary_rows", []) if isinstance(payload, dict) else []
    iteration_rows = payload.get("iteration_rows", []) if isinstance(payload, dict) else []
    cut_score_rows = payload.get("cut_score_rows", []) if isinstance(payload, dict) else []

    ai_active_rows = [
        row for row in summary_rows
        if str(row.get("method", "")).lower() == "ai_active_benders"
    ]
    ai_active_iterations = [
        row for row in iteration_rows
        if str(row.get("method", "")).lower() == "ai_active_benders"
        or "ai_active_benders" in str(row.get("run_key", "")).lower()
    ]
    ai_active_cut_scores = [
        row for row in cut_score_rows
        if str(row.get("method", "")).lower() == "ai_active_benders"
        or "ai_active_benders" in str(row.get("run_key", "")).lower()
    ]
    return ai_active_rows, ai_active_iterations, ai_active_cut_scores


def build_ai_active_validation_status(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Summarize whether AI-active Benders has actual run evidence."""

    summary_payload = payload if isinstance(payload, dict) else _read_json(SUMMARY_PATH)
    ai_active_rows, ai_active_iterations, ai_active_cut_scores = _extract_ai_active_rows(summary_payload)

    result_has_ai_active = bool(ai_active_rows)
    source_exists = SUMMARY_PATH.exists()
    expected_outputs = [str(SUMMARY_PATH), str(COMPARISON_PATH), str(ITERATIONS_PATH), str(CUT_SCORES_PATH)]

    if result_has_ai_active:
        state = "verified_result_present"
        evidence_level = "run_result"
        next_action = (
            "Review gap, selected-cut count, active cut score, and termination reasons before claiming acceleration."
        )
        claim_boundary = (
            "AI-active Benders result rows are present, but acceleration claims still require multi-instance "
            "comparison against classic Benders and careful gap/runtime analysis."
        )
    elif source_exists:
        state = "code_ready_result_missing"
        evidence_level = "code_contract_only"
        next_action = (
            "Run `python -m py_compile experiments/benchmark_benders_comparison.py` and then "
            "`python experiments/benchmark_benders_comparison.py`; verify ai_active_benders rows appear in "
            "benchmark_benders_comparison.csv, benchmark_benders_iterations.csv, benchmark_benders_cut_scores.csv, "
            "and benchmark_benders_summary.json."
        )
        claim_boundary = (
            "Current files do not contain ai_active_benders run rows. Treat AI-active Benders as a second-stage "
            "mechanism design and contract, not as a verified experiment result."
        )
    else:
        state = "missing_benchmark_summary"
        evidence_level = "missing"
        next_action = "Run the benchmark Benders comparison script after restoring Python execution."
        claim_boundary = (
            "No benchmark Benders summary file is available, so AI-active Benders cannot be discussed as a result."
        )

    return {
        "state": state,
        "result_has_ai_active": result_has_ai_active,
        "evidence_level": evidence_level,
        "ai_active_method_rows": len(ai_active_rows),
        "ai_active_iteration_rows": len(ai_active_iterations),
        "ai_active_cut_score_rows": len(ai_active_cut_scores),
        "expected_outputs": expected_outputs,
        "next_action": next_action,
        "claim_boundary": claim_boundary,
    }


def build_ai_active_validation_report(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return a richer validation report for saving to JSON/Markdown."""

    summary_payload = payload if isinstance(payload, dict) else _read_json(SUMMARY_PATH)
    status = build_ai_active_validation_status(summary_payload)
    ai_active_rows, ai_active_iterations, ai_active_cut_scores = _extract_ai_active_rows(summary_payload)

    return {
        "summary_source": str(SUMMARY_PATH),
        "summary_exists": SUMMARY_PATH.exists(),
        "comparison_exists": COMPARISON_PATH.exists(),
        "iterations_exists": ITERATIONS_PATH.exists(),
        "cut_scores_exists": CUT_SCORES_PATH.exists(),
        "status": status,
        "summary_row_count": len(summary_payload.get("summary_rows", [])) if isinstance(summary_payload, dict) else 0,
        "iteration_row_count": len(summary_payload.get("iteration_rows", [])) if isinstance(summary_payload, dict) else 0,
        "cut_score_row_count": len(summary_payload.get("cut_score_rows", [])) if isinstance(summary_payload, dict) else 0,
        "ai_active_method_cases": sorted({str(row.get("case_id", "")) for row in ai_active_rows if row.get("case_id")}),
        "ai_active_method_rows": ai_active_rows,
        "ai_active_iteration_rows": ai_active_iterations,
        "ai_active_cut_score_rows": ai_active_cut_scores,
        "result_files": {
            "summary_path": str(SUMMARY_PATH),
            "comparison_path": str(COMPARISON_PATH),
            "iterations_path": str(ITERATIONS_PATH),
            "cut_scores_path": str(CUT_SCORES_PATH),
        },
    }


def render_ai_active_validation_markdown(report: dict[str, Any]) -> str:
    """Render a compact markdown report for human review."""

    status = report.get("status", {}) if isinstance(report, dict) else {}
    ai_active_cases = report.get("ai_active_method_cases", []) if isinstance(report, dict) else []
    lines = [
        "# AI-active Benders Validation Report",
        "",
        "## Status",
        "",
        "| item | value |",
        "| --- | --- |",
        f"| state | {status.get('state', '')} |",
        f"| evidence_level | {status.get('evidence_level', '')} |",
        f"| result_has_ai_active | {status.get('result_has_ai_active', '')} |",
        f"| ai_active_method_rows | {status.get('ai_active_method_rows', '')} |",
        f"| ai_active_iteration_rows | {status.get('ai_active_iteration_rows', '')} |",
        f"| ai_active_cut_score_rows | {status.get('ai_active_cut_score_rows', '')} |",
        "",
        "## File Checks",
        "",
        f"- summary_exists: {report.get('summary_exists', False)}",
        f"- comparison_exists: {report.get('comparison_exists', False)}",
        f"- iterations_exists: {report.get('iterations_exists', False)}",
        f"- cut_scores_exists: {report.get('cut_scores_exists', False)}",
        "",
        "## Next Action",
        "",
        str(status.get("next_action", "")),
        "",
        "## Claim Boundary",
        "",
        str(status.get("claim_boundary", "")),
        "",
        "## Cases",
        "",
        ", ".join(ai_active_cases) if ai_active_cases else "No ai_active_benders case rows detected.",
        "",
    ]
    return "\n".join(lines)


def write_ai_active_validation_artifacts(
    payload: dict[str, Any] | None = None,
    out_dir: Path | None = None,
) -> dict[str, str]:
    """Write JSON and Markdown validation artifacts."""

    report = build_ai_active_validation_report(payload)
    destination = out_dir or RESULTS_ROOT
    destination.mkdir(parents=True, exist_ok=True)

    json_path = destination / VALIDATION_JSON_PATH.name
    md_path = destination / VALIDATION_MD_PATH.name
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_ai_active_validation_markdown(report), encoding="utf-8")

    return {"json_path": str(json_path), "md_path": str(md_path)}
