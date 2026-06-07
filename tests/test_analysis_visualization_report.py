import json
from pathlib import Path

from fastapi.testclient import TestClient

from src.api.main import app, dashboard_bootstrap
from src.data_sources.analysis_visualization_report import build_analysis_visualization_report


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ANALYSIS_VIS_JSON_PATH = PROJECT_ROOT / "results" / "analysis_visualization_report.json"

client = TestClient(app)


def test_analysis_visualization_report_packages_existing_results():
    report = build_analysis_visualization_report()
    summary = report["summary"]

    assert report["source_name"] == "analysis visualization report"
    assert summary["scenario_count"] == 4
    assert summary["sensitivity_group_count"] >= 4
    assert summary["method_count"] >= 5
    assert summary["figure_count"] >= 8
    assert report["scenario"]["stable_open_sites"] is True
    assert any(item["component"] == "fixed_cost" for item in report["baseline_cost_breakdown"])


def test_analysis_visualization_endpoint_and_bootstrap():
    response = client.get("/api/v1/analysis/visualization-report")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["scenario_count"] == 4
    assert "scenario" in payload
    assert "figures" in payload

    bootstrap = dashboard_bootstrap()
    assert "analysis_visualization_report" in bootstrap
    assert bootstrap["analysis_visualization_report"]["summary"]["figure_count"] >= 8


def test_analysis_visualization_artifact_exists():
    data = json.loads(ANALYSIS_VIS_JSON_PATH.read_text(encoding="utf-8"))

    assert data["summary"]["scenario_count"] == 4
    assert data["checks"]
