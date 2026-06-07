import json
from pathlib import Path

from fastapi.testclient import TestClient

from src.api.main import app, dashboard_bootstrap
from src.data_sources.baseline_v3_capacity_chain_report import build_baseline_v3_capacity_chain_report


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = PROJECT_ROOT / "results" / "baseline_v3_capacity_chain_report.json"
VUE_APP_PATH = PROJECT_ROOT / "frontend-vue" / "src" / "App.vue"

client = TestClient(app)


def test_baseline_v3_report_has_capacity_chain_semantics():
    report = build_baseline_v3_capacity_chain_report()

    if not report["exists"]["pickle"]:
        assert report["summary"] == {}
        assert report["channel_mix"] == []
        return

    summary = report["summary"]
    assert report["claim_boundary"]["solver_claim_state"] in {
        "gap_satisfied",
        "feasible_time_limit_incumbent",
        "feasible_solver_status_unclassified",
    }
    assert summary["capacity_semantics"] == "peak_inventory_from_annual_flow"
    assert summary["total_peak_capacity_load_ton"] < summary["total_annual_production_ton"]
    assert summary["frozen_or_processing_share"] <= 0.1
    assert len(summary["selected_storage_types"]) >= 3
    assert any(item["id"] == "solver_status" for item in report["checks"])
    assert any(item["id"] == "capacity_semantics" and item["state"] == "corrected" for item in report["checks"])


def test_baseline_v3_endpoint_and_bootstrap():
    response = client.get("/api/v1/experiments/baseline-v3-capacity-chain-report")

    assert response.status_code == 200
    payload = response.json()
    if payload["exists"]["pickle"]:
        assert payload["summary"]["capacity_semantics"] == "peak_inventory_from_annual_flow"
        assert payload["channel_mix"]
    else:
        assert payload["summary"] == {}

    bootstrap = dashboard_bootstrap()
    assert "baseline_v3_capacity_chain_report" in bootstrap
    bootstrap_payload = bootstrap["baseline_v3_capacity_chain_report"]
    if bootstrap_payload["exists"]["pickle"]:
        assert bootstrap_payload["summary"]["frozen_or_processing_share"] <= 0.1
    else:
        assert bootstrap_payload["summary"] == {}


def test_baseline_v3_artifact_and_vue_binding():
    # 多视图重构后内容分布到各 View 文件，搜索整个 src/ 目录
    vue_src_root = PROJECT_ROOT / "frontend-vue" / "src"
    all_vue = "\n".join(
        p.read_text(encoding="utf-8")
        for p in vue_src_root.rglob("*.vue")
    )

    if REPORT_PATH.exists():
        data = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
        if data["exists"]["pickle"]:
            assert data["summary"]["capacity_semantics"] == "peak_inventory_from_annual_flow"
    assert "v3.0 容量链基线" in all_vue
    assert "baselineV3Report" in all_vue
