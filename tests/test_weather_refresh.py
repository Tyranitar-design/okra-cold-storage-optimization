import json

from src.api.main import weather_panel, weather_refresh


def test_weather_panel_exposes_mobile_snapshot_fields():
    payload = weather_panel()

    assert payload["source"] == "/api/v1/weather/panel"
    assert "fetched_at" in payload
    assert "current" in payload
    assert "forecast" in payload
    assert "cold_chain_linkage" in payload
    assert "claim_boundary" in payload


def test_weather_refresh_uses_cache_without_exposing_gaode_secret():
    payload = weather_refresh(force=False, max_age_seconds=10**9)

    assert payload["source"] == "/api/v1/weather/panel"
    assert payload["refresh"]["used_cache"] is True
    assert "current" in payload
    assert "forecast" in payload

    raw = json.dumps(payload, ensure_ascii=False)
    assert "OKRA_AMAP_WEB_SERVICE_KEY" not in raw
    assert "高德地图后端API key" not in raw
    assert "appkey" not in raw.lower()
