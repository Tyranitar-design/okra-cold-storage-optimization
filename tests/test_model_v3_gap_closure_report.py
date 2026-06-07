from pathlib import Path

from fastapi.testclient import TestClient

from src.api.main import app, dashboard_bootstrap
from src.data_sources.model_v3_gap_closure_report import build_model_v3_gap_closure_report
from src.models.v3_solver_profiles import get_v3_solver_profile, list_v3_solver_profiles


PROJECT_ROOT = Path(__file__).resolve().parents[1]
VUE_APP_PATH = PROJECT_ROOT / "frontend-vue" / "src" / "App.vue"

client = TestClient(app)


def test_v3_solver_profiles_are_named_and_reproducible():
    profiles = list_v3_solver_profiles()
    names = {item["name"] for item in profiles}

    assert "baseline_300s" in names
    assert "bound_focus_60s" in names
    assert "extended_bound_900s" in names
    assert get_v3_solver_profile("bound_focus_60s").solver_params["MIPFocus"] == 3


def test_model_v3_gap_closure_report_is_solver_safe():
    report = build_model_v3_gap_closure_report()
    summary = report["summary"]

    assert report["profiles"]
    assert summary["profile_count"] >= 3
    assert summary["baseline_status"] in {"OPTIMAL", "TIME_LIMIT", None}
    assert "baseline_v3_report" in report["result_paths"]
    assert report["research_boundary"].startswith("Gap-closure runs")


def test_model_v3_gap_closure_endpoint_bootstrap_and_vue_binding():
    response = client.get("/api/v1/experiments/model-v3-gap-closure-report")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["profile_count"] >= 3

    bootstrap = dashboard_bootstrap()
    assert "model_v3_gap_closure_report" in bootstrap
    assert bootstrap["model_v3_gap_closure_report"]["summary"]["profile_count"] >= 3

    vue_src_root = VUE_APP_PATH.parent
    vue_source = "\n".join(
        p.read_text(encoding="utf-8")
        for p in vue_src_root.rglob("*.vue")
    )
    assert "v3.0 Gap 收敛证据" in vue_source
    assert "modelV3GapClosure" in vue_source
