import json
from pathlib import Path

from src.api.main import (
    _ai_benders_feature_summary,
    _ai_benders_result_card,
    _db_probe_response,
    _mis_readiness_report,
    _paper_evidence_pack,
    dashboard_bootstrap,
    get_storages_map,
    logistics_contracts,
    logistics_layout_snapshot,
)
from src.api.db import database_status_payload
from src.api.main import build_seed_preview, _seed_preview_response


PROJECT_ROOT = Path(__file__).resolve().parents[1]
READINESS_JSON_PATH = PROJECT_ROOT / "results" / "mis_readiness_report.json"
FRONTEND_VUE_DIST_PATH = PROJECT_ROOT / "frontend-vue" / "dist" / "index.html"
FRONTEND_HTML_FALLBACK_PATH = PROJECT_ROOT / "frontend" / "mis_app.html"


def test_mis_readiness_report_summarizes_core_surfaces():
    report = _mis_readiness_report()
    summary = report["summary"]

    assert report["source"] == "/api/v1/experiments/mis-readiness-report"
    assert summary["check_count"] >= 7
    assert summary["ai_benders_case_count"] == 3
    assert summary["paper_layer_count"] == 13
    assert summary["logistics_interface_count"] >= 6
    assert "frontend_app" in {item["id"] for item in report["checks"]}


def test_mis_readiness_report_matches_live_helper_payloads():
    db_probe = _db_probe_response(database_status_payload())
    seed_preview = _seed_preview_response(build_seed_preview())
    map_payload = get_storages_map()
    readiness = _mis_readiness_report()

    assert readiness["summary"]["database_probe_ok"] == bool(db_probe["probe_detail"]["ok"])
    assert readiness["summary"]["map_feature_count"] == len(map_payload.get("features", []))
    assert readiness["summary"]["ready_count"] >= 5
    assert readiness["boundary_flags"]


def test_mis_readiness_report_normalizes_probe_payload_shapes():
    from src.data_sources.mis_readiness_report import build_mis_readiness_report

    report = build_mis_readiness_report(
        db_probe={"probe_detail": {"attempted": True, "ok": False, "elapsed_ms": 12.3}},
        seed_preview={"total_rows": 1, "non_empty_tables": ["x"]},
        map_payload={"features": [1]},
        ai_benders_result_card={"counts": {"cases": 3}},
        ai_benders_feature_summary={"summary": {"dominant_feature": "coef_l1"}},
        paper_evidence_pack={"summary": {"paper_ready": True, "paper_layer_count": 8}},
        logistics_contracts={"interfaces": [1, 2, 3, 4, 5, 6], "logistics_base_url": ""},
        logistics_layout={"storage_nodes": [1], "assignment_summary": {"demand_node_count": 1}},
        dashboard_keys=["db_probe"],
    )

    db_check = next(item for item in report["checks"] if item["id"] == "database_probe")
    assert db_check["detail"] == "probe_attempted=True, probe_ok=False"
    assert report["summary"]["database_probe_ok"] is False


def test_mis_readiness_report_artifact_exists_and_is_json_serializable():
    data = json.loads(READINESS_JSON_PATH.read_text(encoding="utf-8"))

    assert data["summary"]["check_count"] == len(data["checks"])
    assert data["summary"]["ai_benders_case_count"] == 3
    assert "logistics_contracts" in {item["id"] for item in data["checks"]}
    assert "map_view" in {item["id"] for item in data["checks"]}


def test_mis_readiness_report_is_exposed_by_bootstrap_and_frontend():
    bootstrap = dashboard_bootstrap()
    html = FRONTEND_VUE_DIST_PATH.read_text(encoding="utf-8") if FRONTEND_VUE_DIST_PATH.exists() else FRONTEND_HTML_FALLBACK_PATH.read_text(encoding="utf-8")

    assert "mis_readiness_report" in bootstrap
    assert "meta name=\"description\" content=\"Vue 管理信息系统\"" in html
    assert "<div id=\"app\"></div>" in html
