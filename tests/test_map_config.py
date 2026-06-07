"""Tests for the /api/v1/map/config endpoint (browser map key gating)."""

from __future__ import annotations

import importlib

from fastapi.testclient import TestClient


def _client():
    from src.api.main import app

    return TestClient(app)


def test_map_config_withholds_key_when_not_allowed(monkeypatch):
    # No public-key opt-in -> key must NOT be served, fallback signalled.
    monkeypatch.delenv("OKRA_MAP_PUBLIC_KEY_ALLOWED", raising=False)
    monkeypatch.setenv("OKRA_MAP_PROVIDER", "amap")
    monkeypatch.setenv("OKRA_AMAP_JS_KEY", "deadbeefdeadbeefdeadbeefdeadbeef")
    client = _client()
    resp = client.get("/api/v1/map/config")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["js_key_available"] is False
    assert payload["js_key"] is None
    assert payload["browser_provider_ready"] is False


def test_map_config_serves_key_when_explicitly_allowed(monkeypatch):
    # Operator opt-in + browser provider + key present -> key is served.
    monkeypatch.setenv("OKRA_MAP_PROVIDER", "amap")
    monkeypatch.setenv("OKRA_MAP_PUBLIC_KEY_ALLOWED", "true")
    monkeypatch.setenv("OKRA_AMAP_JS_KEY", "deadbeefdeadbeefdeadbeefdeadbeef")
    client = _client()
    resp = client.get("/api/v1/map/config")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["provider"] == "amap"
    assert payload["browser_provider_ready"] is True
    assert payload["js_key_available"] is True
    assert payload["js_key"] == "deadbeefdeadbeefdeadbeefdeadbeef"
    # default center/zoom present for the frontend
    assert isinstance(payload["default_center"], list) and len(payload["default_center"]) == 2
    assert isinstance(payload["default_zoom"], int)


def test_map_config_never_serves_key_for_file_provider(monkeypatch):
    monkeypatch.setenv("OKRA_MAP_PROVIDER", "file")
    monkeypatch.setenv("OKRA_MAP_PUBLIC_KEY_ALLOWED", "true")
    monkeypatch.setenv("OKRA_AMAP_JS_KEY", "deadbeefdeadbeefdeadbeefdeadbeef")
    client = _client()
    payload = client.get("/api/v1/map/config").json()
    # file provider is not a browser provider -> no key exposure
    assert payload["js_key_available"] is False
    assert payload["js_key"] is None
