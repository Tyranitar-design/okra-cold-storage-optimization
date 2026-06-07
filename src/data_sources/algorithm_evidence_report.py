"""Build a unified report for the current algorithm evidence stack."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESULTS_ROOT = PROJECT_ROOT / "results"
EXPERIMENTS_ROOT = RESULTS_ROOT / "experiments"
METHOD_SMOKE_PATH = EXPERIMENTS_ROOT / "method_smoke" / "method_smoke_summary.json"
AI_BENDERS_COMPARISON_PATH = EXPERIMENTS_ROOT / "ai_benders_comparison" / "ai_benders_comparison_summary.json"
AI_BENDERS_CUT_PATH = EXPERIMENTS_ROOT / "ai_benders_comparison" / "ai_benders_cut_scores.csv"
BENCHMARK_BENDERS_SUMMARY_PATH = EXPERIMENTS_ROOT / "benchmark_benders_comparison" / "benchmark_benders_summary.json"
BENCHMARK_BENDERS_VALIDATION_PATH = EXPERIMENTS_ROOT / "benchmark_benders_comparison" / "ai_active_validation.json"
SPO_SUMMARY_PATH = PROJECT_ROOT / "results" / "spo_smoke" / "spo_summary.json"
ALGORITHM_REPORT_JSON_PATH = RESULTS_ROOT / "algorithm_evidence_report.json"
ALGORITHM_REPORT_MD_PATH = RESULTS_ROOT / "algorithm_evidence_report.md"


def _load_json(path: Path) -> Dict[str, Any] | None:
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {"value": payload}


def build_algorithm_evidence_report() -> Dict[str, Any]:
    method_smoke = _load_json(METHOD_SMOKE_PATH)
    ai_compare = _load_json(AI_BENDERS_COMPARISON_PATH)
    benchmark_benders = _load_json(BENCHMARK_BENDERS_SUMMARY_PATH)
    benchmark_validation = _load_json(BENCHMARK_BENDERS_VALIDATION_PATH)
    spo_summary = _load_json(SPO_SUMMARY_PATH)
    rows = method_smoke.get("rows", []) if method_smoke else []
    ai_rows = ai_compare.get("summary_rows", []) if ai_compare else []
    cut_rows = ai_compare.get("cut_scores", []) if ai_compare else []
    report = {
        "source_name": "Algorithm evidence report",
        "result_paths": {
            "json": str(ALGORITHM_REPORT_JSON_PATH),
            "md": str(ALGORITHM_REPORT_MD_PATH),
            "method_smoke": str(METHOD_SMOKE_PATH),
            "ai_benders_comparison": str(AI_BENDERS_COMPARISON_PATH),
            "ai_benders_cut_scores": str(AI_BENDERS_CUT_PATH),
            "benchmark_benders_summary": str(BENCHMARK_BENDERS_SUMMARY_PATH),
            "benchmark_benders_validation": str(BENCHMARK_BENDERS_VALIDATION_PATH),
            "spo_summary": str(SPO_SUMMARY_PATH),
        },
        "counts": {
            "method_smoke_methods": len(rows),
            "ai_benders_summary_rows": len(ai_rows),
            "ai_benders_cut_scores": len(cut_rows),
            "spo_has_summary": spo_summary is not None,
            "benchmark_benders_has_summary": benchmark_benders is not None,
            "benchmark_benders_has_validation": benchmark_validation is not None,
        },
        "method_smoke": rows,
        "ai_benders_comparison": ai_compare,
        "benchmark_benders_summary": benchmark_benders,
        "benchmark_benders_validation": benchmark_validation,
        "spo_summary": spo_summary,
        "research_boundary": (
            "This report aggregates existing algorithm evidence into a single read-only view. "
            "It does not recompute KKT, epsilon, Benders, Benders cut-ranking, or SPO."
        ),
    }
    return report


def write_algorithm_evidence_report(out_dir: Path | None = None) -> Dict[str, str]:
    destination = out_dir or RESULTS_ROOT
    destination.mkdir(parents=True, exist_ok=True)
    report = build_algorithm_evidence_report()
    json_path = destination / "algorithm_evidence_report.json"
    md_path = destination / "algorithm_evidence_report.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(
        "\n".join(
            [
                "# Algorithm Evidence Report",
                "",
                "## Counts",
                "",
                *[f"- {key}: {value}" for key, value in report.get("counts", {}).items()],
                "",
                "## Method Smoke",
                "",
                *[
                    f"- {row.get('method', '')}: status={row.get('status', '')}, objective={row.get('objective', '')}, runtime={row.get('runtime_sec', '')}"
                    for row in report.get("method_smoke", [])
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


def write_algorithm_evidence_report_bundle(out_dir: Path | None = None) -> Dict[str, str]:
    return write_algorithm_evidence_report(out_dir)
