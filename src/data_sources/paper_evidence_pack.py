"""Build a paper-level evidence pack from existing report artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESULTS_ROOT = PROJECT_ROOT / "results"
DOCS_ROOT = PROJECT_ROOT / "docs"

BASELINE_REPORT_JSON_PATH = RESULTS_ROOT / "baseline_v2_1_report.json"
BASELINE_REPORT_MD_PATH = RESULTS_ROOT / "baseline_v2_1_report.md"
BASELINE_V3_REPORT_JSON_PATH = RESULTS_ROOT / "baseline_v3_capacity_chain_report.json"
BASELINE_V3_REPORT_MD_PATH = RESULTS_ROOT / "baseline_v3_capacity_chain_report.md"
BASELINE_V3_PRESOLVE_JSON_PATH = RESULTS_ROOT / "baseline_v3_presolve_report.json"
BASELINE_V3_PRESOLVE_MD_PATH = RESULTS_ROOT / "baseline_v3_presolve_report.md"
MODEL_V3_GAP_CLOSURE_JSON_PATH = RESULTS_ROOT / "experiments" / "model_v3_gap_closure" / "model_v3_gap_closure_report.json"
MODEL_V3_GAP_CLOSURE_MD_PATH = RESULTS_ROOT / "experiments" / "model_v3_gap_closure" / "model_v3_gap_closure_report.md"
MODEL_V3_ROBUSTNESS_SCREEN_JSON_PATH = RESULTS_ROOT / "experiments" / "model_v3_robustness_screen" / "model_v3_robustness_screen_report.json"
MODEL_V3_ROBUSTNESS_SCREEN_MD_PATH = RESULTS_ROOT / "experiments" / "model_v3_robustness_screen" / "model_v3_robustness_screen_report.md"
MODEL_V3_PRIORITY_SCENARIO_JSON_PATH = RESULTS_ROOT / "experiments" / "model_v3_priority_scenarios" / "model_v3_priority_scenario_report.json"
MODEL_V3_PRIORITY_SCENARIO_MD_PATH = RESULTS_ROOT / "experiments" / "model_v3_priority_scenarios" / "model_v3_priority_scenario_report.md"
ALGORITHM_REPORT_JSON_PATH = RESULTS_ROOT / "algorithm_evidence_report.json"
ALGORITHM_REPORT_MD_PATH = RESULTS_ROOT / "algorithm_evidence_report.md"
AI_BENDERS_ANALYSIS_REPORT_JSON_PATH = RESULTS_ROOT / "ai_benders_analysis_report.json"
AI_BENDERS_ANALYSIS_REPORT_MD_PATH = RESULTS_ROOT / "ai_benders_analysis_report.md"
AI_BENDERS_FEATURE_SUMMARY_JSON_PATH = RESULTS_ROOT / "ai_benders_feature_summary.json"
AI_BENDERS_FEATURE_SUMMARY_MD_PATH = RESULTS_ROOT / "ai_benders_feature_summary.md"
STAGE_REPORT_PATH = RESULTS_ROOT / "experiments" / "stage_report.md"
DATA_EVIDENCE_REGISTRY_PATH = DOCS_ROOT / "data_evidence_registry.csv"
PAPER_DRAFT_PATH = DOCS_ROOT / "论文初稿_v2_阶段版.md"
PRESENTATION_PATH = RESULTS_ROOT / "presentation" / "okra_cold_storage_report_stage.pptx"
PAPER_PACK_JSON_PATH = RESULTS_ROOT / "paper_evidence_pack.json"
PAPER_PACK_MD_PATH = RESULTS_ROOT / "paper_evidence_pack.md"


def _load_json(path: Path) -> Dict[str, Any] | None:
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {"value": payload}


def _layer(name: str, path: Path, description: str) -> Dict[str, Any]:
    return {
        "name": name,
        "path": str(path),
        "exists": path.exists(),
        "description": description,
    }


def build_paper_evidence_pack() -> Dict[str, Any]:
    baseline_report = _load_json(BASELINE_REPORT_JSON_PATH)
    baseline_v3_report = _load_json(BASELINE_V3_REPORT_JSON_PATH)
    baseline_v3_presolve = _load_json(BASELINE_V3_PRESOLVE_JSON_PATH)
    model_v3_gap_closure = _load_json(MODEL_V3_GAP_CLOSURE_JSON_PATH)
    model_v3_robustness_screen = _load_json(MODEL_V3_ROBUSTNESS_SCREEN_JSON_PATH)
    model_v3_priority_scenario = _load_json(MODEL_V3_PRIORITY_SCENARIO_JSON_PATH)
    algorithm_report = _load_json(ALGORITHM_REPORT_JSON_PATH)
    ai_benders_analysis_report = _load_json(AI_BENDERS_ANALYSIS_REPORT_JSON_PATH)
    ai_benders_feature_summary = _load_json(AI_BENDERS_FEATURE_SUMMARY_JSON_PATH)
    baseline_summary = baseline_report.get("summary", {}) if baseline_report else {}
    baseline_v3_summary = baseline_v3_report.get("summary", {}) if baseline_v3_report else {}
    baseline_v3_solver = baseline_v3_report.get("solver", {}) if baseline_v3_report else {}
    baseline_v3_claim = baseline_v3_report.get("claim_boundary", {}) if baseline_v3_report else {}
    baseline_v3_presolve_summary = baseline_v3_presolve.get("summary", {}) if baseline_v3_presolve else {}
    model_v3_gap_closure_summary = model_v3_gap_closure.get("summary", {}) if model_v3_gap_closure else {}
    model_v3_robustness_screen_summary = (
        model_v3_robustness_screen.get("summary", {}) if model_v3_robustness_screen else {}
    )
    model_v3_priority_scenario_summary = (
        model_v3_priority_scenario.get("summary", {}) if model_v3_priority_scenario else {}
    )
    algorithm_counts = algorithm_report.get("counts", {}) if algorithm_report else {}
    ai_benders_analysis_counts = ai_benders_analysis_report.get("counts", {}) if ai_benders_analysis_report else {}
    ai_benders_analysis_summary = ai_benders_analysis_report.get("summary", {}) if ai_benders_analysis_report else {}
    ai_benders_feature_summary_counts = ai_benders_feature_summary.get("counts", {}) if ai_benders_feature_summary else {}
    ai_benders_feature_summary_summary = ai_benders_feature_summary.get("summary", {}) if ai_benders_feature_summary else {}

    layers: List[Dict[str, Any]] = [
        _layer(
            "baseline_v2_1_report",
            BASELINE_REPORT_JSON_PATH,
            "Formal packaging of the baseline v2.1 optimization result.",
        ),
        _layer(
            "baseline_v3_capacity_chain_report",
            BASELINE_V3_REPORT_JSON_PATH,
            "Corrected v3.0 capacity-chain baseline report with solver status, MIP gap, channel mix, and claim boundary.",
        ),
        _layer(
            "baseline_v3_presolve_report",
            BASELINE_V3_PRESOLVE_JSON_PATH,
            "Solver-free v3.0 readiness gate for channel shares, peak capacity load, precooling coverage, and artifact state.",
        ),
        _layer(
            "model_v3_gap_closure_report",
            MODEL_V3_GAP_CLOSURE_JSON_PATH,
            "Named solver-profile evidence for reducing or auditing the open v3.0 MIP gap.",
        ),
        _layer(
            "model_v3_robustness_screen_report",
            MODEL_V3_ROBUSTNESS_SCREEN_JSON_PATH,
            "Solver-free v3.0 robustness screen that prioritizes scenario and sensitivity variants before long Gurobi runs.",
        ),
        _layer(
            "model_v3_priority_scenario_report",
            MODEL_V3_PRIORITY_SCENARIO_JSON_PATH,
            "Real v3.0 optimization artifacts for selected robustness-screen variants with solver status and claim boundaries.",
        ),
        _layer(
            "algorithm_evidence_report",
            ALGORITHM_REPORT_JSON_PATH,
            "Read-only aggregation of method smoke, Benders cut-ranking evidence, SPO, and benchmark evidence.",
        ),
        _layer(
            "ai_benders_analysis_report",
            AI_BENDERS_ANALYSIS_REPORT_JSON_PATH,
            "Empirical summary of Benders cut-ranking runtime, gap, cut, and feature preference across the existing detail files.",
        ),
        _layer(
            "ai_benders_feature_summary",
            AI_BENDERS_FEATURE_SUMMARY_JSON_PATH,
            "Cross-case frequency summary of Benders cut-ranking top features for paper-style discussion.",
        ),
        _layer(
            "stage_report",
            STAGE_REPORT_PATH,
            "Stage report that consolidates scenario and sensitivity evidence for the current paper draft.",
        ),
        _layer(
            "data_evidence_registry",
            DATA_EVIDENCE_REGISTRY_PATH,
            "Traceable registry of data, literature, and method evidence used in the project.",
        ),
        _layer(
            "paper_draft",
            PAPER_DRAFT_PATH,
            "Current Chinese paper draft used for report and thesis alignment.",
        ),
        _layer(
            "presentation_deck",
            PRESENTATION_PATH,
            "Stage presentation deck for reporting and demo support.",
        ),
    ]

    source_reports = {
        "baseline_v2_1_report": {
            "path": str(BASELINE_REPORT_JSON_PATH),
            "exists": BASELINE_REPORT_JSON_PATH.exists(),
        },
        "baseline_v3_capacity_chain_report": {
            "path": str(BASELINE_V3_REPORT_JSON_PATH),
            "exists": BASELINE_V3_REPORT_JSON_PATH.exists(),
        },
        "baseline_v3_presolve_report": {
            "path": str(BASELINE_V3_PRESOLVE_JSON_PATH),
            "exists": BASELINE_V3_PRESOLVE_JSON_PATH.exists(),
        },
        "model_v3_gap_closure_report": {
            "path": str(MODEL_V3_GAP_CLOSURE_JSON_PATH),
            "exists": MODEL_V3_GAP_CLOSURE_JSON_PATH.exists(),
        },
        "model_v3_robustness_screen_report": {
            "path": str(MODEL_V3_ROBUSTNESS_SCREEN_JSON_PATH),
            "exists": MODEL_V3_ROBUSTNESS_SCREEN_JSON_PATH.exists(),
        },
        "model_v3_priority_scenario_report": {
            "path": str(MODEL_V3_PRIORITY_SCENARIO_JSON_PATH),
            "exists": MODEL_V3_PRIORITY_SCENARIO_JSON_PATH.exists(),
        },
        "algorithm_evidence_report": {
            "path": str(ALGORITHM_REPORT_JSON_PATH),
            "exists": ALGORITHM_REPORT_JSON_PATH.exists(),
        },
        "ai_benders_analysis_report": {
            "path": str(AI_BENDERS_ANALYSIS_REPORT_JSON_PATH),
            "exists": AI_BENDERS_ANALYSIS_REPORT_JSON_PATH.exists(),
        },
        "ai_benders_feature_summary": {
            "path": str(AI_BENDERS_FEATURE_SUMMARY_JSON_PATH),
            "exists": AI_BENDERS_FEATURE_SUMMARY_JSON_PATH.exists(),
        },
        "stage_report": {
            "path": str(STAGE_REPORT_PATH),
            "exists": STAGE_REPORT_PATH.exists(),
        },
        "data_evidence_registry": {
            "path": str(DATA_EVIDENCE_REGISTRY_PATH),
            "exists": DATA_EVIDENCE_REGISTRY_PATH.exists(),
        },
        "paper_draft": {
            "path": str(PAPER_DRAFT_PATH),
            "exists": PAPER_DRAFT_PATH.exists(),
        },
        "presentation_deck": {
            "path": str(PRESENTATION_PATH),
            "exists": PRESENTATION_PATH.exists(),
        },
    }

    paper_ready = all(item["exists"] for item in layers)
    report = {
        "source_name": "Paper evidence pack",
        "result_paths": {
            "json": str(PAPER_PACK_JSON_PATH),
            "md": str(PAPER_PACK_MD_PATH),
            "baseline_v2_1_report": str(BASELINE_REPORT_JSON_PATH),
            "baseline_v2_1_report_md": str(BASELINE_REPORT_MD_PATH),
            "baseline_v3_capacity_chain_report": str(BASELINE_V3_REPORT_JSON_PATH),
            "baseline_v3_capacity_chain_report_md": str(BASELINE_V3_REPORT_MD_PATH),
            "baseline_v3_presolve_report": str(BASELINE_V3_PRESOLVE_JSON_PATH),
            "baseline_v3_presolve_report_md": str(BASELINE_V3_PRESOLVE_MD_PATH),
            "model_v3_gap_closure_report": str(MODEL_V3_GAP_CLOSURE_JSON_PATH),
            "model_v3_gap_closure_report_md": str(MODEL_V3_GAP_CLOSURE_MD_PATH),
            "model_v3_robustness_screen_report": str(MODEL_V3_ROBUSTNESS_SCREEN_JSON_PATH),
            "model_v3_robustness_screen_report_md": str(MODEL_V3_ROBUSTNESS_SCREEN_MD_PATH),
            "model_v3_priority_scenario_report": str(MODEL_V3_PRIORITY_SCENARIO_JSON_PATH),
            "model_v3_priority_scenario_report_md": str(MODEL_V3_PRIORITY_SCENARIO_MD_PATH),
            "algorithm_evidence_report": str(ALGORITHM_REPORT_JSON_PATH),
            "algorithm_evidence_report_md": str(ALGORITHM_REPORT_MD_PATH),
            "stage_report": str(STAGE_REPORT_PATH),
            "data_evidence_registry": str(DATA_EVIDENCE_REGISTRY_PATH),
            "paper_draft": str(PAPER_DRAFT_PATH),
            "presentation_deck": str(PRESENTATION_PATH),
        },
        "source_reports": source_reports,
        "summary": {
            "baseline_total_cost": baseline_summary.get("total_cost"),
            "baseline_num_facilities": baseline_summary.get("num_facilities"),
            "baseline_precool_violations": baseline_summary.get("precool_violations"),
            "baseline_v3_total_cost": baseline_v3_summary.get("total_cost"),
            "baseline_v3_num_facilities": baseline_v3_summary.get("num_facilities"),
            "baseline_v3_solver_status": baseline_v3_solver.get("status_name"),
            "baseline_v3_mip_gap_pct": baseline_v3_solver.get("mip_gap_pct"),
            "baseline_v3_claim_state": baseline_v3_claim.get("solver_claim_state"),
            "baseline_v3_presolve_state": baseline_v3_presolve_summary.get("solver_readiness_state"),
            "baseline_v3_solver_artifact_ready": baseline_v3_presolve_summary.get("solver_artifact_ready"),
            "model_v3_gap_closure_run_count": model_v3_gap_closure_summary.get("run_count", 0),
            "model_v3_gap_closure_smallest_gap_pct": model_v3_gap_closure_summary.get("smallest_gap_pct"),
            "model_v3_gap_closure_improved": model_v3_gap_closure_summary.get("gap_improved_vs_baseline", False),
            "model_v3_gap_closure_evidence_state": model_v3_gap_closure_summary.get("evidence_state"),
            "model_v3_robustness_variant_count": model_v3_robustness_screen_summary.get("variant_count", 0),
            "model_v3_robustness_watch_count": model_v3_robustness_screen_summary.get("watch_count", 0),
            "model_v3_robustness_fail_count": model_v3_robustness_screen_summary.get("fail_count", 0),
            "model_v3_robustness_recommended_solver_run_count": model_v3_robustness_screen_summary.get(
                "recommended_solver_run_count",
                0,
            ),
            "model_v3_priority_scenario_run_count": model_v3_priority_scenario_summary.get("run_count", 0),
            "model_v3_priority_scenario_variant_count": model_v3_priority_scenario_summary.get("variant_count", 0),
            "model_v3_priority_scenario_gap_satisfied_count": model_v3_priority_scenario_summary.get(
                "gap_satisfied_count",
                0,
            ),
            "model_v3_priority_scenario_missing_queued_count": model_v3_priority_scenario_summary.get(
                "missing_queued_variant_count",
                0,
            ),
            "method_smoke_methods": algorithm_counts.get("method_smoke_methods", 0),
            "ai_benders_summary_rows": algorithm_counts.get("ai_benders_summary_rows", 0),
            "ai_benders_cut_scores": algorithm_counts.get("ai_benders_cut_scores", 0),
            "spo_has_summary": algorithm_counts.get("spo_has_summary", False),
            "benchmark_benders_has_summary": algorithm_counts.get("benchmark_benders_has_summary", False),
            "benchmark_benders_has_validation": algorithm_counts.get("benchmark_benders_has_validation", False),
            "ai_benders_analysis_cases": ai_benders_analysis_counts.get("cases", 0),
            "ai_benders_analysis_detail_files": ai_benders_analysis_counts.get("detail_files", 0),
            "ai_benders_analysis_speedup_mean": ai_benders_analysis_summary.get("runtime_speedup_pct_mean"),
            "ai_benders_feature_cases": ai_benders_feature_summary_counts.get("case_count", 0),
            "ai_benders_feature_shared_count": ai_benders_feature_summary_counts.get("shared_feature_count", 0),
            "ai_benders_feature_dominant": ai_benders_feature_summary_summary.get("dominant_feature"),
            "ai_benders_feature_summary_exists": AI_BENDERS_FEATURE_SUMMARY_JSON_PATH.exists(),
            "paper_layer_count": len(layers),
            "paper_ready": paper_ready,
        },
        "layers": layers,
        "research_boundary": (
            "This pack is a read-only umbrella over existing baseline, algorithm, paper, registry, and demo artifacts. "
            "It does not rerun optimization, algorithms, data ingestion, or literature review."
        ),
    }
    return report


def write_paper_evidence_pack(out_dir: Path | None = None) -> Dict[str, str]:
    destination = out_dir or RESULTS_ROOT
    destination.mkdir(parents=True, exist_ok=True)
    report = build_paper_evidence_pack()
    json_path = destination / "paper_evidence_pack.json"
    md_path = destination / "paper_evidence_pack.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(
        "\n".join(
            [
                "# Paper Evidence Pack",
                "",
                "## Summary",
                "",
                *[f"- {key}: {value}" for key, value in report.get("summary", {}).items()],
                "",
                "## Layers",
                "",
                *[
                    f"- {layer.get('name', '')}: exists={layer.get('exists', False)}, path={layer.get('path', '')}"
                    for layer in report.get("layers", [])
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


def write_paper_evidence_pack_bundle(out_dir: Path | None = None) -> Dict[str, str]:
    return write_paper_evidence_pack(out_dir)
