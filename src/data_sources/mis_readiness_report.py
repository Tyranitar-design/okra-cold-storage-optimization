"""Build a read-only readiness report for the MIS demo surface."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESULTS_ROOT = PROJECT_ROOT / "results"
FRONTEND_APP_PATH = PROJECT_ROOT / "frontend" / "mis_app.html"
MIS_READINESS_JSON_PATH = RESULTS_ROOT / "mis_readiness_report.json"
MIS_READINESS_MD_PATH = RESULTS_ROOT / "mis_readiness_report.md"


def _state(ready: bool, evidence_level: str = "file_or_helper_verified") -> str:
    if ready and evidence_level == "runtime_verified":
        return "runtime_verified"
    if ready:
        return "ready_with_file_fallback"
    return "needs_attention"


def _normalize_probe_payload(db_probe: Dict[str, Any]) -> Dict[str, Any]:
    """Accept either the raw database status payload or the API wrapper."""
    if isinstance(db_probe.get("probe_detail"), dict):
        return db_probe["probe_detail"]
    if isinstance(db_probe.get("probe"), dict):
        probe = db_probe["probe"]
        return {
            "attempted": probe.get("attempted"),
            "ok": probe.get("ok"),
            "elapsed_ms": probe.get("elapsed_ms"),
            "current_database": probe.get("current_database"),
            "current_user": probe.get("current_user"),
            "error": probe.get("error"),
        }
    return {
        "attempted": db_probe.get("probe_attempted"),
        "ok": db_probe.get("probe_ok"),
        "elapsed_ms": db_probe.get("probe_elapsed_ms"),
        "current_database": db_probe.get("probe_current_database"),
        "current_user": db_probe.get("probe_current_user"),
        "error": db_probe.get("probe_error"),
    }


def build_mis_readiness_report(
    *,
    db_probe: Dict[str, Any],
    seed_preview: Dict[str, Any],
    map_payload: Dict[str, Any],
    ai_benders_result_card: Dict[str, Any],
    ai_benders_feature_summary: Dict[str, Any],
    paper_evidence_pack: Dict[str, Any],
    logistics_contracts: Dict[str, Any],
    logistics_layout: Dict[str, Any],
    dashboard_keys: List[str] | None = None,
) -> Dict[str, Any]:
    html = FRONTEND_APP_PATH.read_text(encoding="utf-8") if FRONTEND_APP_PATH.exists() else ""
    logistics_base_url = logistics_contracts.get("logistics_base_url") or ""
    interfaces = logistics_contracts.get("interfaces", [])
    map_features = map_payload.get("features", [])
    storage_nodes = logistics_layout.get("storage_nodes", [])
    probe = _normalize_probe_payload(db_probe)

    checks = [
        {
            "id": "frontend_app",
            "name": "MIS 前端页面",
            "state": _state(FRONTEND_APP_PATH.exists(), "runtime_verified" if html else "file_or_helper_verified"),
            "evidence": str(FRONTEND_APP_PATH),
            "detail": "frontend/mis_app.html exists and contains the management information system shell.",
            "boundary": "HTML presence does not replace browser-level visual verification.",
        },
        {
            "id": "database_probe",
            "name": "PostgreSQL 探测",
            "state": _state(bool(probe.get("ok")), "runtime_verified"),
            "evidence": "/api/v1/db/probe",
            "detail": f"probe_attempted={probe.get('attempted')}, probe_ok={probe.get('ok')}",
            "boundary": "Only probe_ok=true can support a claim of live PostgreSQL connectivity.",
        },
        {
            "id": "seed_preview",
            "name": "数据库入库预览",
            "state": _state((seed_preview.get("total_rows") or 0) > 0),
            "evidence": "/api/v1/db/seed-preview",
            "detail": f"total_rows={seed_preview.get('total_rows')}, non_empty_tables={seed_preview.get('non_empty_tables')}",
            "boundary": "Seed preview is not a database apply result.",
        },
        {
            "id": "map_view",
            "name": "地图选址视图",
            "state": _state(len(map_features) > 0),
            "evidence": "/api/v1/storages/map",
            "detail": f"features={len(map_features)}, source_backend={map_payload.get('source_backend')}",
            "boundary": "Current map can use file fallback; PostGIS-backed map requires database readiness.",
        },
        {
            "id": "ai_benders_panel",
            "name": "Benders cut-ranking 方法面板",
            "state": _state((ai_benders_result_card.get("counts", {}).get("cases") or 0) >= 3),
            "evidence": "/api/v1/experiments/ai-benders-result-card",
            "detail": (
                f"cases={ai_benders_result_card.get('counts', {}).get('cases')}, "
                f"dominant_feature={ai_benders_feature_summary.get('summary', {}).get('dominant_feature')}"
            ),
            "boundary": "This proves a demonstrable cut-ranking evidence panel, not algorithmic superiority.",
        },
        {
            "id": "paper_evidence_pack",
            "name": "论文证据包",
            "state": _state(bool(paper_evidence_pack.get("summary", {}).get("paper_ready"))),
            "evidence": "/api/v1/experiments/paper-evidence-pack",
            "detail": (
                f"layers={paper_evidence_pack.get('summary', {}).get('paper_layer_count')}, "
                f"paper_ready={paper_evidence_pack.get('summary', {}).get('paper_ready')}"
            ),
            "boundary": "The pack is read-only packaging and does not rerun optimization.",
        },
        {
            "id": "logistics_contracts",
            "name": "物流系统 REST 契约",
            "state": _state(len(interfaces) >= 6),
            "evidence": "/api/v1/integration/logistics/contracts",
            "detail": f"interfaces={len(interfaces)}, base_url_configured={bool(logistics_base_url)}",
            "boundary": "Without LOGISTICS_BASE_URL and end-to-end HTTP calls, this remains contract/mock integration.",
        },
        {
            "id": "logistics_layout_snapshot",
            "name": "物流布局快照",
            "state": _state(len(storage_nodes) > 0),
            "evidence": "/api/v1/integration/logistics/cold-storage/layout",
            "detail": (
                f"storage_nodes={len(storage_nodes)}, "
                f"demand_nodes={logistics_layout.get('assignment_summary', {}).get('demand_node_count')}"
            ),
            "boundary": "Snapshot is generated from current optimization files; it is not a pushed logistics result.",
        },
    ]

    ready_count = sum(1 for item in checks if item["state"] in {"ready_with_file_fallback", "runtime_verified"})
    runtime_verified_count = sum(1 for item in checks if item["state"] == "runtime_verified")
    blocked_or_mock = [item["id"] for item in checks if "not " in item.get("boundary", "").lower() or "without" in item.get("boundary", "").lower()]

    return {
        "source_name": "MIS readiness report",
        "result_paths": {
            "json": str(MIS_READINESS_JSON_PATH),
            "md": str(MIS_READINESS_MD_PATH),
            "frontend": str(FRONTEND_APP_PATH),
        },
        "summary": {
            "check_count": len(checks),
            "ready_count": ready_count,
            "runtime_verified_count": runtime_verified_count,
            "frontend_exists": FRONTEND_APP_PATH.exists(),
            "dashboard_key_count": len(dashboard_keys or []),
            "map_feature_count": len(map_features),
            "ai_benders_case_count": ai_benders_result_card.get("counts", {}).get("cases", 0),
            "paper_layer_count": paper_evidence_pack.get("summary", {}).get("paper_layer_count", 0),
            "logistics_interface_count": len(interfaces),
            "logistics_base_url_configured": bool(logistics_base_url),
            "database_probe_ok": bool(probe.get("ok")),
        },
        "checks": checks,
        "boundary_flags": blocked_or_mock,
        "research_boundary": (
            "This report audits MIS demo readiness from existing files and FastAPI helper payloads. "
            "It distinguishes file/helper-verified display readiness from live PostgreSQL, browser, and logistics-system verification."
        ),
    }


def write_mis_readiness_report(report: Dict[str, Any], out_dir: Path | None = None) -> Dict[str, str]:
    destination = out_dir or RESULTS_ROOT
    destination.mkdir(parents=True, exist_ok=True)
    json_path = destination / "mis_readiness_report.json"
    md_path = destination / "mis_readiness_report.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(
        "\n".join(
            [
                "# MIS Readiness Report",
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
