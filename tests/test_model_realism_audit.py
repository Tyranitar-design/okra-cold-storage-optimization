import json
from pathlib import Path

from fastapi.testclient import TestClient

from src.api.main import app, dashboard_bootstrap
from src.data_sources.model_realism_audit import build_model_realism_audit


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODEL_REALISM_JSON_PATH = PROJECT_ROOT / "results" / "model_realism_audit.json"
APP_VUE_PATH = PROJECT_ROOT / "frontend-vue" / "src" / "App.vue"

client = TestClient(app)


def test_model_realism_audit_detects_current_model_risks():
    report = build_model_realism_audit()
    summary = report["summary"]
    check_ids = {item["id"] for item in report["checks"]}

    assert report["source_name"] == "model realism audit"
    assert summary["node_count"] == 39
    assert summary["baseline_facility_count"] == 3
    assert summary["capacity_to_annual_production_ratio"] > 0.9
    assert summary["selected_storage_types"] == ["frozen"]
    assert summary["high_risk_count"] >= 3
    assert "capacity_semantics" in check_ids
    assert "temperature_chain" in check_ids
    assert "real_data_generalization" in check_ids


def test_model_realism_endpoint_and_bootstrap():
    response = client.get("/api/v1/model/realism-audit")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["readiness_state"] == "needs_model_v3_before_strong_claims"
    assert payload["checks"]

    bootstrap = dashboard_bootstrap()
    assert "model_realism_audit" in bootstrap
    assert bootstrap["model_realism_audit"]["summary"]["high_risk_count"] >= 3


def test_model_realism_artifact_and_vue_binding():
    data = json.loads(MODEL_REALISM_JSON_PATH.read_text(encoding="utf-8"))
    # 多视图重构后内容分布到各 View 文件，搜索整个 src/ 目录
    vue_src_root = APP_VUE_PATH.parent
    vue_source = "\n".join(
        p.read_text(encoding="utf-8")
        for p in vue_src_root.rglob("*.vue")
    )

    assert data["summary"]["selected_storage_types"] == ["frozen"]
    assert "模型现实性审计" in vue_source
    assert "modelRealismAudit" in vue_source
