from fastapi.testclient import TestClient
from pathlib import Path

import pytest

from src.api.main import app, dashboard_bootstrap
from src.data_sources.baseline_v3_presolve_report import build_baseline_v3_presolve_report


PROJECT_ROOT = Path(__file__).resolve().parents[1]
VUE_APP_PATH = PROJECT_ROOT / "frontend-vue" / "src" / "App.vue"


client = TestClient(app)


def test_baseline_v3_presolve_report_static_checks():
    report = build_baseline_v3_presolve_report()
    summary = report["summary"]

    assert summary["total_annual_production_ton"] > 0
    assert summary["downstream_share_sum"] == pytest.approx(1.0)
    assert summary["service_share_sum"] == pytest.approx(2.0)
    assert summary["total_peak_capacity_load_ton"] < summary["total_annual_production_ton"]
    assert summary["lower_bound_facilities"] <= summary["max_facilities"]
    assert summary["precool_uncovered_count"] == 0
    assert summary["solver_readiness_state"] in {"ready_to_authorize_solver_run", "solver_result_present"}
    assert any(item["id"] == "solver_artifact_state" and item["state"] in {"pending", "pass"} for item in report["checks"])


def test_baseline_v3_presolve_endpoint_and_bootstrap():
    response = client.get("/api/v1/experiments/baseline-v3-presolve-report")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["downstream_share_sum"] == pytest.approx(1.0)
    assert payload["channel_capacity_screen"]

    bootstrap = dashboard_bootstrap()
    assert "baseline_v3_presolve_report" in bootstrap
    assert bootstrap["baseline_v3_presolve_report"]["summary"]["lower_bound_facilities"] <= 8


def test_baseline_v3_presolve_vue_binding():
    # 多视图重构后内容分布到各 View 文件，搜索整个 src/ 目录
    vue_src_root = PROJECT_ROOT / "frontend-vue" / "src"
    source = "\n".join(
        p.read_text(encoding="utf-8")
        for p in vue_src_root.rglob("*.vue")
    )

    assert "v3.0 求解前预检" in source
    assert "baselineV3Presolve" in source
