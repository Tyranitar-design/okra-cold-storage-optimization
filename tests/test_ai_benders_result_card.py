import json
import math
from pathlib import Path

from src.api.main import _ai_benders_result_card, dashboard_bootstrap, list_experiments
from src.data_sources.ai_benders_analysis_report import build_ai_benders_analysis_report
from src.data_sources.ai_benders_result_card import build_ai_benders_result_card
from src.data_sources.paper_evidence_pack import build_paper_evidence_pack


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_PATH = PROJECT_ROOT / "frontend" / "mis_app.html"
RESULT_CARD_PATH = PROJECT_ROOT / "results" / "ai_benders_result_card.json"
PAPER_PACK_PATH = PROJECT_ROOT / "results" / "paper_evidence_pack.json"


def test_ai_benders_result_card_matches_analysis_report():
    analysis = build_ai_benders_analysis_report()
    card = build_ai_benders_result_card()

    assert card["counts"]["cases"] == analysis["counts"]["cases"] == 3
    assert card["counts"]["detail_files"] == analysis["counts"]["detail_files"] == 3
    assert card["counts"]["selected_cut_count_total"] == 3
    assert math.isclose(
        card["summary"]["runtime_delta_pct_mean"],
        analysis["summary"]["runtime_speedup_pct_mean"],
        rel_tol=0,
        abs_tol=1e-12,
    )
    assert card["summary"]["gap_delta_pct_points_mean"] == 0.0
    assert card["summary"]["cut_delta_mean"] == 0.0

    rows_by_case = {row["case_id"]: row for row in card["rows"]}
    assert set(rows_by_case) == {"AB_5c_6d_strict", "AB_7c_8d_strict", "AB_9c_10d_strict"}
    assert rows_by_case["AB_5c_6d_strict"]["selected_cut_index"] == 1
    assert rows_by_case["AB_7c_8d_strict"]["selected_cut_index"] == 0
    assert rows_by_case["AB_9c_10d_strict"]["selected_cut_index"] == 3
    assert "coef_l1" in rows_by_case["AB_9c_10d_strict"]["top_features"]


def test_ai_benders_result_card_artifacts_are_in_sync():
    card_file = json.loads(RESULT_CARD_PATH.read_text(encoding="utf-8"))
    paper_pack = json.loads(PAPER_PACK_PATH.read_text(encoding="utf-8"))

    assert math.isclose(
        card_file["summary"]["runtime_delta_pct_mean"],
        paper_pack["summary"]["ai_benders_analysis_speedup_mean"],
        rel_tol=0,
        abs_tol=1e-12,
    )
    assert card_file["counts"]["cases"] == paper_pack["summary"]["ai_benders_analysis_cases"]
    assert card_file["counts"]["detail_files"] == paper_pack["summary"]["ai_benders_analysis_detail_files"]
    assert paper_pack["summary"]["paper_layer_count"] == 13


def test_paper_evidence_pack_is_read_only_packaging():
    pack = build_paper_evidence_pack()

    assert pack["summary"]["paper_ready"] is True
    assert pack["summary"]["paper_layer_count"] == 13
    assert pack["research_boundary"].startswith("This pack is a read-only umbrella")
    assert pack["source_reports"]["baseline_v2_1_report"]["exists"] is True
    assert pack["source_reports"]["algorithm_evidence_report"]["exists"] is True
    assert pack["source_reports"]["model_v3_robustness_screen_report"]["exists"] is True


def test_ai_benders_result_card_is_exposed_by_api_helpers():
    card_payload = _ai_benders_result_card()
    bootstrap = dashboard_bootstrap()
    experiments = list_experiments()

    assert card_payload["source"] == "/api/v1/experiments/ai-benders-result-card"
    assert bootstrap["ai_benders_result_card"]["counts"]["cases"] == 3

    experiment_ids = {item["run_id"] for item in experiments["items"]}
    assert "ai_benders_analysis_report" in experiment_ids
    assert "ai_benders_result_card" in experiment_ids
    assert "ai_benders_feature_summary" in experiment_ids


def test_mis_frontend_binds_ai_benders_result_card_panels():
    html = FRONTEND_PATH.read_text(encoding="utf-8")

    assert 'id="aiResultCardPanel"' in html
    assert 'id="aiFeatureSummaryPanel"' in html
    assert "ai_benders_result_card" in html
    assert "/api/v1/experiments/ai-benders-result-card" in html
    assert "mean_runtime_delta_pct" in html
    assert "ai_feature_dominant" in html
