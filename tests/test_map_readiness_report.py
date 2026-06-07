import json
from pathlib import Path

from src.api.main import dashboard_bootstrap, get_storages_map, logistics_layout_snapshot
from src.api.db import database_status_payload
from src.data_sources.map_readiness_report import build_map_readiness_report


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MAP_READINESS_JSON_PATH = PROJECT_ROOT / "results" / "map_readiness_report.json"
FRONTEND_VUE_DIST_PATH = PROJECT_ROOT / "frontend-vue" / "dist" / "index.html"
FRONTEND_HTML_FALLBACK_PATH = PROJECT_ROOT / "frontend" / "mis_app.html"


def test_map_readiness_report_summarizes_map_surface():
    report = build_map_readiness_report(
        map_payload=get_storages_map(),
        logistics_layout=logistics_layout_snapshot(),
        db_probe=database_status_payload(),
        dashboard_keys=["map", "db_probe", "integration"],
    )
    summary = report["summary"]

    assert report["source_name"] == "map readiness report"
    assert summary["check_count"] >= 4
    assert summary["map_feature_count"] > 0
    assert "map_points" in {item["id"] for item in report["checks"]}
    assert "database_ready_for_map" in {item["id"] for item in report["checks"]}


def test_map_readiness_report_is_exposed_by_bootstrap_and_frontend():
    bootstrap = dashboard_bootstrap()
    html = FRONTEND_VUE_DIST_PATH.read_text(encoding="utf-8") if FRONTEND_VUE_DIST_PATH.exists() else FRONTEND_HTML_FALLBACK_PATH.read_text(encoding="utf-8")

    assert "map_readiness_report" in bootstrap
    assert "meta name=\"description\" content=\"Vue 管理信息系统\"" in html
    assert "<div id=\"app\"></div>" in html


def test_map_readiness_report_artifact_exists_and_is_json_serializable():
    data = json.loads(MAP_READINESS_JSON_PATH.read_text(encoding="utf-8"))

    assert data["summary"]["check_count"] == len(data["checks"])
    assert data["summary"]["map_feature_count"] > 0
    assert "map_points" in {item["id"] for item in data["checks"]}
