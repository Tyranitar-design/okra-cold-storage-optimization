from fastapi.testclient import TestClient

from src.api.main import app, dashboard_bootstrap


client = TestClient(app)


def test_mis_app_page_exposes_core_sections():
    response = client.get("/app")

    assert response.status_code == 200
    html = response.text
    assert "秋葵冷库优化 MIS" in html
    assert "meta name=\"description\" content=\"Vue 管理信息系统\"" in html
    assert "/assets/" in html
    assert "<div id=\"app\"></div>" in html


def test_dashboard_bootstrap_exposes_runtime_payloads():
    payload = dashboard_bootstrap()

    assert "mis_readiness_report" in payload
    assert "algorithm_evidence_report" in payload
    assert "ai_benders_result_card" in payload
    assert "paper_evidence_pack" in payload
    assert "map" in payload
    assert "integration" in payload
    integration = payload["integration"]
    assert integration["contract_version"] == "v1"
    assert integration["interfaces"]
    assert all("path" in item and "purpose" in item for item in integration["interfaces"])
    assert payload["paper_evidence_pack"]["summary"]["paper_ready"] is True
    assert payload["algorithm_evidence_report"]["counts"]["benchmark_benders_has_validation"] is True


def test_favicon_route_returns_svg_icon():
    response = client.get("/favicon.ico")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/svg+xml")
    assert "<svg" in response.text
