import json
from pathlib import Path

from fastapi.testclient import TestClient

from src.api.main import app, dashboard_bootstrap
from src.data_sources.model_v3_robustness_screen import (
    ROBUSTNESS_REPORT_JSON_PATH,
    ROBUSTNESS_REPORT_MD_PATH,
    build_model_v3_robustness_screen_report,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
VUE_APP_PATH = PROJECT_ROOT / "frontend-vue" / "src" / "App.vue"
PAPER_PACK_PATH = PROJECT_ROOT / "results" / "paper_evidence_pack.json"

client = TestClient(app)


def test_model_v3_robustness_screen_report_is_solver_free_and_traceable():
    report = build_model_v3_robustness_screen_report()
    summary = report["summary"]

    assert report["source_backend"] == "solver_free_robustness_screen"
    assert summary["variant_count"] == 9
    assert summary["total_annual_production_ton"] > 0
    assert summary["precool_uncovered_count"] == 0
    assert summary["recommended_solver_run_count"] >= 1
    assert summary["fail_count"] == 0
    assert "does not provide scenario optimality" in report["research_boundary"]
    assert all("channel_capacity_screen" in variant for variant in report["variants"])


def test_model_v3_robustness_endpoint_bootstrap_and_vue_binding():
    response = client.get("/api/v1/experiments/model-v3-robustness-screen-report")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["variant_count"] == 9
    assert payload["source"] == "/api/v1/experiments/model-v3-robustness-screen-report"

    bootstrap = dashboard_bootstrap()
    assert "model_v3_robustness_screen_report" in bootstrap
    assert bootstrap["model_v3_robustness_screen_report"]["summary"]["recommended_solver_run_count"] >= 1

    vue_src_root = VUE_APP_PATH.parent
    vue_source = "\n".join(
        p.read_text(encoding="utf-8")
        for p in vue_src_root.rglob("*.vue")
    )
    assert "v3.0 稳健性筛选" in vue_source
    assert "modelV3RobustnessScreen" in vue_source


def test_model_v3_robustness_artifacts_and_paper_pack_are_materialized():
    assert ROBUSTNESS_REPORT_JSON_PATH.exists()
    assert ROBUSTNESS_REPORT_MD_PATH.exists()

    robustness = json.loads(ROBUSTNESS_REPORT_JSON_PATH.read_text(encoding="utf-8"))
    paper = json.loads(PAPER_PACK_PATH.read_text(encoding="utf-8"))

    assert robustness["summary"]["variant_count"] == 9
    assert paper["source_reports"]["model_v3_robustness_screen_report"]["exists"] is True
    assert paper["summary"]["model_v3_robustness_variant_count"] == robustness["summary"]["variant_count"]
    assert paper["summary"]["model_v3_robustness_recommended_solver_run_count"] == robustness["summary"][
        "recommended_solver_run_count"
    ]
