import json
from pathlib import Path

from fastapi.testclient import TestClient

from src.api.main import app, dashboard_bootstrap
from src.data_sources.model_v3_priority_scenario_report import (
    PRIORITY_SCENARIO_REPORT_JSON_PATH,
    PRIORITY_SCENARIO_REPORT_MD_PATH,
    assumptions_for_priority_variant,
    build_model_v3_priority_scenario_report,
    resolve_priority_variant,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
VUE_APP_PATH = PROJECT_ROOT / "frontend-vue" / "src" / "App.vue"
PAPER_PACK_PATH = PROJECT_ROOT / "results" / "paper_evidence_pack.json"

client = TestClient(app)


def test_priority_variant_resolver_uses_robustness_overrides():
    variant = resolve_priority_variant("max_facilities_tight_5")
    assumptions = assumptions_for_priority_variant("max_facilities_tight_5")

    assert variant.category == "facility_limit"
    assert assumptions.max_facilities == 5

    fresh = assumptions_for_priority_variant("fresh_heavy_cold70_ca20_frozen10")
    shares = {channel.type_id: channel.annual_share for channel in fresh.channels}
    assert shares["cold"] == 0.7
    assert shares["ca"] == 0.2
    assert shares["frozen"] == 0.1


def test_priority_scenario_report_reads_real_run_artifacts():
    report = build_model_v3_priority_scenario_report()
    summary = report["summary"]

    assert report["source_backend"] == "v3_priority_scenario_artifacts"
    assert summary["queued_variant_count"] == 4
    assert summary["run_count"] >= 1
    assert summary["variant_count"] >= 1
    assert summary["gap_satisfied_count"] >= 1
    assert report["runs"][0]["variant"]["name"] == "max_facilities_tight_5"
    assert "solver status and MIP gap" in report["research_boundary"]


def test_priority_scenario_endpoint_bootstrap_and_vue_binding():
    response = client.get("/api/v1/experiments/model-v3-priority-scenario-report")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["run_count"] >= 1
    assert payload["source"] == "/api/v1/experiments/model-v3-priority-scenario-report"

    bootstrap = dashboard_bootstrap()
    assert "model_v3_priority_scenario_report" in bootstrap
    assert bootstrap["model_v3_priority_scenario_report"]["summary"]["gap_satisfied_count"] >= 1

    vue_src_root = VUE_APP_PATH.parent
    vue_source = "\n".join(
        p.read_text(encoding="utf-8")
        for p in vue_src_root.rglob("*.vue")
    )
    assert "v3.0 优先情景求解" in vue_source
    assert "modelV3PriorityScenario" in vue_source


def test_priority_scenario_artifacts_and_paper_pack_are_materialized():
    assert PRIORITY_SCENARIO_REPORT_JSON_PATH.exists()
    assert PRIORITY_SCENARIO_REPORT_MD_PATH.exists()

    priority = json.loads(PRIORITY_SCENARIO_REPORT_JSON_PATH.read_text(encoding="utf-8"))
    paper = json.loads(PAPER_PACK_PATH.read_text(encoding="utf-8"))

    assert priority["summary"]["run_count"] >= 1
    assert paper["source_reports"]["model_v3_priority_scenario_report"]["exists"] is True
    assert paper["summary"]["model_v3_priority_scenario_run_count"] == priority["summary"]["run_count"]
    assert paper["summary"]["model_v3_priority_scenario_gap_satisfied_count"] == priority["summary"][
        "gap_satisfied_count"
    ]
