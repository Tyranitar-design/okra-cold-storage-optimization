import json
from pathlib import Path

from src.api.benchmark_benders_validation import build_ai_active_validation_report
from src.data_sources.algorithm_evidence_report import build_algorithm_evidence_report
from src.data_sources.baseline_v2_1_report import build_baseline_v2_1_report
from src.data_sources.paper_evidence_pack import build_paper_evidence_pack


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ALGORITHM_REPORT_PATH = PROJECT_ROOT / "results" / "algorithm_evidence_report.json"
PAPER_PACK_PATH = PROJECT_ROOT / "results" / "paper_evidence_pack.json"
BASELINE_REPORT_PATH = PROJECT_ROOT / "results" / "baseline_v2_1_report.json"


def test_paper_pack_is_aligned_with_algorithm_and_baseline_reports():
    baseline = build_baseline_v2_1_report()
    algorithm = build_algorithm_evidence_report()
    paper = build_paper_evidence_pack()

    assert paper["summary"]["paper_ready"] is True
    assert paper["summary"]["paper_layer_count"] == 13
    assert paper["summary"]["baseline_total_cost"] == baseline["summary"]["total_cost"]
    assert paper["summary"]["baseline_v3_solver_status"] in {"OPTIMAL", "TIME_LIMIT"}
    assert paper["summary"]["baseline_v3_claim_state"] in {"gap_satisfied", "feasible_time_limit_incumbent"}
    assert paper["summary"]["baseline_v3_solver_artifact_ready"] is True
    assert paper["summary"]["model_v3_gap_closure_run_count"] >= 1
    assert paper["summary"]["model_v3_robustness_variant_count"] == 9
    assert paper["summary"]["model_v3_robustness_recommended_solver_run_count"] >= 1
    assert paper["summary"]["model_v3_priority_scenario_run_count"] >= 1
    assert paper["summary"]["model_v3_priority_scenario_gap_satisfied_count"] >= 1
    assert paper["summary"]["ai_benders_summary_rows"] == algorithm["counts"]["ai_benders_summary_rows"]
    assert paper["summary"]["benchmark_benders_has_validation"] is True
    assert paper["research_boundary"].startswith("This pack is a read-only umbrella")


def test_paper_pack_json_matches_current_packaging_contract():
    paper_file = json.loads(PAPER_PACK_PATH.read_text(encoding="utf-8"))
    algorithm_file = json.loads(ALGORITHM_REPORT_PATH.read_text(encoding="utf-8"))
    baseline_file = json.loads(BASELINE_REPORT_PATH.read_text(encoding="utf-8"))

    assert paper_file["summary"]["paper_ready"] is True
    assert paper_file["summary"]["baseline_total_cost"] == baseline_file["summary"]["total_cost"]
    assert paper_file["source_reports"]["baseline_v3_capacity_chain_report"]["exists"] is True
    assert paper_file["source_reports"]["baseline_v3_presolve_report"]["exists"] is True
    assert paper_file["source_reports"]["model_v3_gap_closure_report"]["exists"] is True
    assert paper_file["source_reports"]["model_v3_robustness_screen_report"]["exists"] is True
    assert paper_file["source_reports"]["model_v3_priority_scenario_report"]["exists"] is True
    assert paper_file["summary"]["ai_benders_cut_scores"] == algorithm_file["counts"]["ai_benders_cut_scores"]
    assert paper_file["source_reports"]["stage_report"]["exists"] is True
    assert paper_file["source_reports"]["presentation_deck"]["exists"] is True


def test_stage_report_and_paper_pack_share_validation_boundary():
    stage_report = (PROJECT_ROOT / "results" / "experiments" / "stage_report.md").read_text(encoding="utf-8")
    paper_pack = build_paper_evidence_pack()
    algorithm_report = build_algorithm_evidence_report()
    validation_report = build_ai_active_validation_report()

    assert paper_pack["summary"]["benchmark_benders_has_validation"] is True
    assert algorithm_report["counts"]["benchmark_benders_has_validation"] is True
    assert validation_report["status"]["state"] == "verified_result_present"
    assert "verified_result_present" in stage_report
    assert "同实例机制验证" in stage_report
