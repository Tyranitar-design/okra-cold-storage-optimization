from fastapi.testclient import TestClient

from src.api.main import app, dashboard_bootstrap
from src.data_sources.map_provider_status import build_map_provider_status
from src.data_sources.map_readiness_report import build_map_readiness_report


client = TestClient(app)


def test_map_provider_status_does_not_expose_key_values(monkeypatch):
    monkeypatch.setenv("OKRA_MAP_PROVIDER", "amap")
    monkeypatch.setenv("OKRA_MAP_PUBLIC_KEY_ENV", "OKRA_AMAP_JS_KEY")
    monkeypatch.setenv("OKRA_AMAP_JS_KEY", "secret-browser-key-value")
    monkeypatch.setenv("OKRA_MAP_PUBLIC_KEY_ALLOWED", "true")

    report = build_map_provider_status()
    rendered = str(report)

    assert report["provider"] == "amap"
    assert report["public_key_configured"] is True
    assert report["public_key_allowed_for_client"] is True
    assert report["browser_provider_ready"] is True
    assert "secret-browser-key-value" not in rendered


def test_map_provider_status_endpoint_and_bootstrap_are_safe():
    response = client.get("/api/v1/map/provider-status")

    assert response.status_code == 200
    payload = response.json()
    assert "summary" in payload
    assert "public_key_env" in payload
    assert "public_key_configured" in payload
    assert "public_key_value" not in payload

    bootstrap = dashboard_bootstrap()
    assert "map_provider_status" in bootstrap
    assert "map_provider_status" not in bootstrap["map_provider_status"].get("public_key_env", "")


def test_map_readiness_includes_map_provider_check(monkeypatch):
    monkeypatch.setenv("OKRA_MAP_PROVIDER", "amap")
    monkeypatch.setenv("OKRA_MAP_PUBLIC_KEY_ENV", "OKRA_AMAP_JS_KEY")
    monkeypatch.setenv("OKRA_AMAP_JS_KEY", "browser-only-key")
    monkeypatch.setenv("OKRA_MAP_PUBLIC_KEY_ALLOWED", "true")

    provider_status = build_map_provider_status()
    report = build_map_readiness_report(
        map_payload={"source_backend": "file", "features": []},
        logistics_layout={"storage_nodes": [], "demand_nodes": []},
        db_probe={"query_ready": False},
        map_provider_status=provider_status,
        dashboard_keys=["map_provider_status"],
    )

    provider_check = next(item for item in report["checks"] if item["id"] == "map_provider")
    assert provider_check["state"] == "runtime_verified"
    assert report["summary"]["browser_provider_ready"] is True
