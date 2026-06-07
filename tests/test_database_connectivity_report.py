from fastapi.testclient import TestClient

from src.api.main import app, dashboard_bootstrap
from src.data_sources.database_connectivity_report import build_database_connectivity_report


client = TestClient(app)


def test_database_connectivity_report_sanitizes_connection_details():
    report = build_database_connectivity_report(
        {
            "dialect": "postgresql+psycopg",
            "host": "localhost",
            "port": 5432,
            "database_name": "okra_cold_storage",
            "has_credentials": True,
            "database_url_configured": True,
            "driver": "psycopg",
            "driver_available": True,
            "probe_ok": False,
            "query_ready": False,
            "probe_error": 'connection failed: password authentication failed for user "okra"',
        }
    )

    rendered = str(report)
    assert report["summary"]["auth_failed"] is True
    assert report["summary"]["can_apply_seed"] is False
    seed_gate = next(item for item in report["checks"] if item["id"] == "seed_apply_gate")
    assert "auth_failed=True" in seed_gate["detail"]
    assert "postgresql+psycopg://okra" not in rendered
    assert "database_url" not in report["safe_connection"]


def test_database_connectivity_report_endpoint_and_bootstrap():
    response = client.get("/api/v1/db/connectivity-report")

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "/api/v1/db/connectivity-report"
    assert "summary" in payload
    assert "checks" in payload
    assert "safe_connection" in payload
    assert "database_url" not in payload["safe_connection"]

    bootstrap = dashboard_bootstrap()
    assert "database_connectivity_report" in bootstrap
    summary = bootstrap["database_connectivity_report"]["summary"]
    # can_apply_seed must be a boolean and must be consistent with the live probe:
    # it may be True once a real OKRA_DATABASE_URL is reachable (2026-05-29 onward),
    # or False while the database is blocked. It must never be True while auth fails.
    assert isinstance(summary["can_apply_seed"], bool)
    if summary.get("auth_failed") is True:
        assert summary["can_apply_seed"] is False
