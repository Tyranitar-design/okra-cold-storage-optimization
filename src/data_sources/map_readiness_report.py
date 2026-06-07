"""Build a read-only readiness report for map and spatial display surfaces."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESULTS_ROOT = PROJECT_ROOT / "results"
FRONTEND_APP_PATH = PROJECT_ROOT / "frontend-vue" / "dist" / "index.html"
MAP_READINESS_JSON_PATH = RESULTS_ROOT / "map_readiness_report.json"
MAP_READINESS_MD_PATH = RESULTS_ROOT / "map_readiness_report.md"


def _state(ready: bool, evidence_level: str = "file_or_helper_verified") -> str:
    if ready and evidence_level == "runtime_verified":
        return "runtime_verified"
    if ready:
        return "ready_with_file_fallback"
    return "needs_attention"


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return float(default)
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def build_map_readiness_report(
    *,
    map_payload: Dict[str, Any],
    logistics_layout: Dict[str, Any],
    db_probe: Dict[str, Any],
    map_provider_status: Dict[str, Any] | None = None,
    dashboard_keys: list[str] | None = None,
) -> Dict[str, Any]:
    features = map_payload.get("features", []) if isinstance(map_payload, dict) else []
    storage_nodes = logistics_layout.get("storage_nodes", []) if isinstance(logistics_layout, dict) else []
    demand_nodes = logistics_layout.get("demand_nodes", []) if isinstance(logistics_layout, dict) else []
    assignment_summary = logistics_layout.get("assignment_summary", {}) if isinstance(logistics_layout, dict) else {}
    geometry_points = [f for f in features if isinstance(f, dict) and f.get("geometry", {}).get("type") == "Point"]
    candidate_points = [
        f
        for f in geometry_points
        if bool(f.get("properties", {}).get("candidate") or f.get("properties", {}).get("is_candidate"))
    ]
    latitudes = [_safe_float(f.get("geometry", {}).get("coordinates", [None, None])[1]) for f in geometry_points]
    longitudes = [_safe_float(f.get("geometry", {}).get("coordinates", [None, None])[0]) for f in geometry_points]

    has_points = len(geometry_points) > 0
    has_candidates = len(candidate_points) > 0
    has_layout = len(storage_nodes) > 0
    db_ready = bool(db_probe.get("query_ready"))
    provider_status = map_provider_status or {}
    browser_provider_ready = bool(provider_status.get("browser_provider_ready"))
    file_fallback_ready = bool(provider_status.get("file_fallback_ready", True))

    checks = [
        {
            "id": "map_points",
            "name": "节点点位图层",
            "state": _state(has_points),
            "evidence": "/api/v1/storages/map",
            "detail": f"point_features={len(geometry_points)}, source_backend={map_payload.get('source_backend')}",
            "boundary": "Point features exist, but this does not yet mean a real basemap or road network layer is connected.",
        },
        {
            "id": "candidate_sites",
            "name": "候选点图层",
            "state": _state(has_candidates),
            "evidence": "/api/v1/storages/map",
            "detail": f"candidate_features={len(candidate_points)}",
            "boundary": "Candidate points can be shown from files, but that alone is not a live map provider integration.",
        },
        {
            "id": "layout_snapshot",
            "name": "布局快照",
            "state": _state(has_layout),
            "evidence": "/api/v1/integration/logistics/cold-storage/layout",
            "detail": f"storage_nodes={len(storage_nodes)}, demand_nodes={len(demand_nodes)}",
            "boundary": "Layout snapshot is derived from current optimization files, not from live logistics push/pull.",
        },
        {
            "id": "map_extent",
            "name": "空间范围可计算",
            "state": _state(has_points),
            "evidence": "frontend-vue/dist/index.html",
            "detail": (
                f"lat_min={min(latitudes) if latitudes else None}, "
                f"lat_max={max(latitudes) if latitudes else None}, "
                f"lon_min={min(longitudes) if longitudes else None}, "
                f"lon_max={max(longitudes) if longitudes else None}"
            ),
            "boundary": "The extent is derived from current files and is sufficient for an internal demo, not a live basemap provider.",
        },
        {
            "id": "database_ready_for_map",
            "name": "数据库可支撑地图",
            "state": _state(db_ready, "runtime_verified" if db_ready else "file_or_helper_verified"),
            "evidence": "/api/v1/db/probe",
            "detail": f"query_ready={db_probe.get('query_ready')}, source_backend={map_payload.get('source_backend')}",
            "boundary": "Only query_ready=true can support a claim that the map could reliably switch to database-backed features.",
        },
        {
            "id": "map_provider",
            "name": "地图服务商配置",
            "state": _state(browser_provider_ready, "runtime_verified" if browser_provider_ready else "file_or_helper_verified"),
            "evidence": "/api/v1/map/provider-status",
            "detail": (
                f"provider={provider_status.get('provider', 'file')}, "
                f"browser_provider_ready={browser_provider_ready}, "
                f"file_fallback_ready={file_fallback_ready}"
            ),
            "boundary": "Provider readiness only means configuration is safe to expose; it does not prove third-party map tile or route API calls succeeded.",
        },
    ]

    ready_count = sum(1 for item in checks if item["state"] in {"ready_with_file_fallback", "runtime_verified"})
    runtime_verified_count = sum(1 for item in checks if item["state"] == "runtime_verified")

    return {
        "source_name": "map readiness report",
        "result_paths": {
            "json": str(MAP_READINESS_JSON_PATH),
            "md": str(MAP_READINESS_MD_PATH),
            "frontend": str(FRONTEND_APP_PATH),
        },
        "summary": {
            "check_count": len(checks),
            "ready_count": ready_count,
            "runtime_verified_count": runtime_verified_count,
            "frontend_exists": FRONTEND_APP_PATH.exists(),
            "map_feature_count": len(features),
            "candidate_feature_count": len(candidate_points),
            "layout_storage_count": len(storage_nodes),
            "layout_demand_count": len(demand_nodes),
            "database_query_ready": bool(db_ready),
            "browser_provider_ready": bool(browser_provider_ready),
            "file_fallback_ready": bool(file_fallback_ready),
            "source_backend": map_payload.get("source_backend"),
            "dashboard_key_count": len(dashboard_keys or []),
            "extent_available": bool(latitudes and longitudes),
        },
        "checks": checks,
        "boundary_flags": [
            item["id"]
            for item in checks
            if "not" in str(item.get("boundary", "")).lower() or "only" in str(item.get("boundary", "")).lower()
        ],
        "research_boundary": (
            "This report audits map and spatial display readiness from current files and helper payloads. "
            "It distinguishes point-layer display readiness from real basemap, road-network, and PostGIS-backed map integration."
        ),
    }


def write_map_readiness_report(report: Dict[str, Any], out_dir: Path | None = None) -> Dict[str, str]:
    destination = out_dir or RESULTS_ROOT
    destination.mkdir(parents=True, exist_ok=True)
    json_path = destination / "map_readiness_report.json"
    md_path = destination / "map_readiness_report.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(
        "\n".join(
            [
                "# Map Readiness Report",
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
