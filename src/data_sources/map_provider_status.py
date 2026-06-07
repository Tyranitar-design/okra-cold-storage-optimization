"""Map provider configuration audit without exposing credentials."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESULTS_ROOT = PROJECT_ROOT / "results"
MAP_PROVIDER_STATUS_JSON_PATH = RESULTS_ROOT / "map_provider_status.json"
MAP_PROVIDER_STATUS_MD_PATH = RESULTS_ROOT / "map_provider_status.md"

SUPPORTED_PROVIDERS = {"amap", "gaode", "tencent", "mapbox", "osm", "file"}
PUBLIC_BROWSER_PROVIDERS = {"amap", "gaode", "tencent", "mapbox"}


def _truthy_env(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _configured(value: str | None) -> bool:
    return bool(value and value.strip())


def build_map_provider_status() -> Dict[str, Any]:
    """Return a safe map provider status payload.

    The function deliberately reports only booleans and environment variable
    names. It never returns API keys or key-derived substrings.
    """

    provider_raw = os.getenv("OKRA_MAP_PROVIDER", "file").strip().lower() or "file"
    provider = provider_raw if provider_raw in SUPPORTED_PROVIDERS else "custom"
    public_key_env = os.getenv("OKRA_MAP_PUBLIC_KEY_ENV", "OKRA_AMAP_JS_KEY").strip() or "OKRA_AMAP_JS_KEY"
    server_key_env = os.getenv("OKRA_MAP_SERVER_KEY_ENV", "OKRA_AMAP_WEB_SERVICE_KEY").strip() or "OKRA_AMAP_WEB_SERVICE_KEY"
    public_key_configured = _configured(os.getenv(public_key_env))
    server_key_configured = _configured(os.getenv(server_key_env))
    public_key_allowed = _truthy_env("OKRA_MAP_PUBLIC_KEY_ALLOWED")
    provider_requires_public_key = provider in PUBLIC_BROWSER_PROVIDERS
    browser_provider_ready = bool(
        provider_requires_public_key and public_key_configured and public_key_allowed
    )
    server_provider_ready = bool(server_key_configured)
    file_fallback_ready = provider == "file" or not browser_provider_ready

    checks = [
        {
            "id": "provider_selected",
            "name": "地图服务商选择",
            "state": "ready" if provider in SUPPORTED_PROVIDERS else "needs_attention",
            "detail": f"provider={provider}",
            "boundary": "Unsupported provider names are preserved as custom and require manual front-end integration.",
        },
        {
            "id": "public_browser_key",
            "name": "浏览器地图 Key",
            "state": "ready" if public_key_configured and public_key_allowed else "needs_attention",
            "detail": (
                f"env={public_key_env}, configured={public_key_configured}, "
                f"explicitly_allowed_for_client={public_key_allowed}"
            ),
            "boundary": "A Vite/browser map key is public after bundling; only browser-scoped keys should be enabled here.",
        },
        {
            "id": "server_map_key",
            "name": "服务端地图 Key",
            "state": "ready" if server_key_configured else "needs_attention",
            "detail": f"env={server_key_env}, configured={server_key_configured}",
            "boundary": "Server-side keys can support geocoding or route matrix calls but must not be exposed to Vue bundles.",
        },
        {
            "id": "file_fallback",
            "name": "文件点位兜底",
            "state": "ready",
            "detail": f"fallback_ready={file_fallback_ready}",
            "boundary": "File fallback is suitable for demos and evidence audit, not for claiming a live basemap provider integration.",
        },
    ]

    ready_count = sum(1 for item in checks if item["state"] == "ready")
    return {
        "source_name": "map provider status",
        "result_paths": {
            "json": str(MAP_PROVIDER_STATUS_JSON_PATH),
            "md": str(MAP_PROVIDER_STATUS_MD_PATH),
        },
        "provider": provider,
        "provider_raw": provider_raw,
        "public_key_env": public_key_env,
        "server_key_env": server_key_env,
        "public_key_configured": public_key_configured,
        "server_key_configured": server_key_configured,
        "public_key_allowed_for_client": public_key_allowed,
        "browser_provider_ready": browser_provider_ready,
        "server_provider_ready": server_provider_ready,
        "file_fallback_ready": file_fallback_ready,
        "checks": checks,
        "summary": {
            "check_count": len(checks),
            "ready_count": ready_count,
            "provider": provider,
            "public_key_configured": public_key_configured,
            "server_key_configured": server_key_configured,
            "browser_provider_ready": browser_provider_ready,
            "server_provider_ready": server_provider_ready,
            "file_fallback_ready": file_fallback_ready,
        },
        "research_boundary": (
            "This payload audits whether a map provider can be enabled without exposing credentials. "
            "It never returns API key values. A provider is only browser-ready when a browser-scoped public key is "
            "configured and explicitly allowed for client exposure."
        ),
    }


def write_map_provider_status(report: Dict[str, Any], out_dir: Path | None = None) -> Dict[str, str]:
    destination = out_dir or RESULTS_ROOT
    destination.mkdir(parents=True, exist_ok=True)
    json_path = destination / "map_provider_status.json"
    md_path = destination / "map_provider_status.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(
        "\n".join(
            [
                "# Map Provider Status",
                "",
                "## Summary",
                "",
                *[f"- {key}: {value}" for key, value in report.get("summary", {}).items()],
                "",
                "## Checks",
                "",
                *[
                    f"- {item.get('id', '')}: state={item.get('state', '')}, detail={item.get('detail', '')}"
                    for item in report.get("checks", [])
                ],
                "",
                "## Boundary",
                "",
                str(report.get("research_boundary", "")),
                "",
            ]
        ),
        encoding="utf-8",
    )
    return {"json_path": str(json_path), "md_path": str(md_path)}
