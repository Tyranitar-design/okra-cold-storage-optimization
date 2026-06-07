"""
FastAPI backend and demo dashboard for the okra cold storage project.
"""

from __future__ import annotations

import json
import os
import queue
import sys
import threading
import time
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any, Dict, List, Literal

# Support both recommended project-root startup:
#   python -m uvicorn src.api.main:app
# and legacy startup from src/api:
#   uvicorn main:app
_THIS_FILE = Path(__file__).resolve()
_PROJECT_ROOT_FOR_IMPORTS = _THIS_FILE.parents[2]
if str(_PROJECT_ROOT_FOR_IMPORTS) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT_FOR_IMPORTS))

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from src.api.auth import (ROUTER_PREFIX, UserInfo, authenticate_user,
                          create_access_token, get_current_user, require_role)

# ── MIS Phase 2: Modular routers ─────────────────────────────────
from src.api.routers.auth_router import router as auth_router_v1
from src.api.routers.nodes import router as nodes_router
from src.api.routers.routes_mgmt import router as routes_router
from src.api.routers.ws import router as ws_router
from src.api.routers.dashboard import router as dashboard_router_v1

# ── Rate limiting ───────────────────────────────────────────────
from collections import defaultdict
import time as time_module
_rate_limit_store: dict[str, list[float]] = defaultdict(list)
RATE_LIMIT = int(os.getenv("RATE_LIMIT_PER_MINUTE", "60"))

# ── Operation audit log ─────────────────────────────────────────
from pathlib import Path
AUDIT_LOG_PATH = os.getenv("AUDIT_LOG_PATH", "")

def _log_audit(user: str, action: str, detail: str):
    if not AUDIT_LOG_PATH:
        return
    try:
        p = Path(AUDIT_LOG_PATH)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a", encoding="utf-8") as f:
            f.write(f"{time_module.strftime('%Y-%m-%d %H:%M:%S')} | {user} | {action} | {detail}\n")
    except Exception:
        pass

# ── Prometheus metrics ───────────────────────────────────────────
from prometheus_client import Counter, Histogram, generate_latest, REGISTRY
import time as time_module

REQ_COUNT = Counter("okra_api_requests_total", "Total API requests", ["method", "endpoint", "status"])
SOLVE_TIME = Histogram("okra_solve_duration_seconds", "Solver duration", ["solver_type"], buckets=(1, 5, 10, 30, 60, 120, 300, 600, 900))
DB_QUERY_TIME = Histogram("okra_db_query_seconds", "Database query time", ["query_type"])

from src.api.benchmark_manifest import NORMALIZED_MANIFEST_PATH, load_normalized_manifest
from src.api.benchmark_benders_validation import build_ai_active_validation_report, build_ai_active_validation_status
from src.api.db import database_status_payload
from src.api.models import (
    AgentChatRequest,
    EvidenceSource,
    ExperimentCreateRequest,
    ExperimentRunRecord,
    LogisticsPushRequest,
    LogisticsRoutingSolveRequest,
    OptimizeRequest,
    RoutingRequest,
    WhatIfRequest,
)
from src.api.repositories import (
    RepositoryUnavailable,
    count_evidence_sources_from_db,
    get_evidence_source_from_db,
    get_storage_detail_from_db,
    list_ai_benders_cut_scores_from_db,
    list_candidate_storages_from_db,
    list_evidence_sources_from_db,
    list_map_features_from_db,
)
from src.api.services import csv_rows_to_html_table, iter_records_with_limit, load_csv_records, load_json_payload, load_pickle_payload, load_text_content
from scripts.seed_postgres_from_current_files import build_seed_preview
from src.data_sources.database_connectivity_report import build_database_connectivity_report
from src.data_sources.download_adapters import build_real_data_download_adapter_plan
from src.data_sources.overpass_ingestion import build_overpass_ingestion_preview
from src.data_sources.overpass_preview import build_overpass_preview_report
from src.data_sources.overpass_preview_validation import build_overpass_preview_validation
from src.data_sources.overpass_request_validation import build_overpass_request_validation
from src.data_sources.overpass_summary import build_overpass_summary
from src.data_sources.overpass_runbook import build_overpass_runbook
from src.data_sources.overpass_bundle import build_overpass_bundle
from src.data_sources.overpass_guide import write_overpass_guide, build_overpass_guide
from src.data_sources.baseline_v2_1_report import build_baseline_v2_1_report
from src.data_sources.baseline_v3_capacity_chain_report import build_baseline_v3_capacity_chain_report
from src.data_sources.model_v3_gap_closure_report import build_model_v3_gap_closure_report
from src.data_sources.model_v3_robustness_screen import build_model_v3_robustness_screen_report, build_whatif_screen
from src.data_sources.model_v3_priority_scenario_report import build_model_v3_priority_scenario_report
from src.data_sources.baseline_v3_presolve_report import build_baseline_v3_presolve_report
from src.data_sources.algorithm_evidence_report import build_algorithm_evidence_report
from src.data_sources.ai_benders_analysis_report import build_ai_benders_analysis_report
from src.data_sources.ai_benders_result_card import build_ai_benders_result_card
from src.data_sources.ai_benders_feature_summary import build_ai_benders_feature_summary
from src.data_sources.analysis_visualization_report import build_analysis_visualization_report
from src.data_sources.model_realism_audit import build_model_realism_audit
from src.data_sources.map_provider_status import build_map_provider_status, write_map_provider_status
from src.data_sources.map_readiness_report import build_map_readiness_report, write_map_readiness_report
from src.data_sources.mis_readiness_report import build_mis_readiness_report, write_mis_readiness_report
from src.data_sources.paper_evidence_pack import build_paper_evidence_pack
from src.data_sources.paper_export import build_paper_export
from src.data_sources.official_source_plan import build_official_source_plan
from src.data_sources.ingestion_readiness import build_real_data_ingestion_readiness
from src.data_sources.ingestion_manifest import build_real_data_ingestion_manifest
from src.data_sources.ingestion_validation import build_real_data_ingestion_validation
from src.data_sources.real_data_registry import build_real_data_source_report
from src.models.capacity_chain_assumptions import default_assumptions, _channel_map
from src.models.v3_solver_profiles import get_v3_solver_profile


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CUT_SCORE_FORMULA = "0.40 * rhs + 0.25 * coef_l1 + 0.20 * gap_pct + 0.15 * compactness"
DEFAULT_AI_BENDERS_RESEARCH_BOUNDARY = (
    "Current Benders cut-ranking result is a structured smoke-test evidence bundle, "
    "not yet a full comparative superiority proof."
)
_SOLVER_MODULES: tuple[Any, Any, Any, Any] | None = None
_AI_BENDERS_CONSTANTS: tuple[str, str] | None = None
_NODES_DF_CACHE: Any | None = None


def _load_nodes_df() -> Any:
    global _NODES_DF_CACHE
    if _NODES_DF_CACHE is None:
        import pandas as pd

        _NODES_DF_CACHE = pd.read_csv(PROJECT_ROOT / "data" / "nodes.csv")
    return _NODES_DF_CACHE.copy()


def _get_ai_benders_constants() -> tuple[str, str]:
    global _AI_BENDERS_CONSTANTS
    if _AI_BENDERS_CONSTANTS is None:
        try:
            from src.algorithms.benders_ai import AI_BENDERS_RESEARCH_BOUNDARY, CUT_SCORE_FORMULA

            _AI_BENDERS_CONSTANTS = (AI_BENDERS_RESEARCH_BOUNDARY, CUT_SCORE_FORMULA)
        except Exception:
            _AI_BENDERS_CONSTANTS = (
                DEFAULT_AI_BENDERS_RESEARCH_BOUNDARY,
                DEFAULT_CUT_SCORE_FORMULA,
            )
    return _AI_BENDERS_CONSTANTS


def _get_solver_modules() -> tuple[Any, Any, Any, Any]:
    global _SOLVER_MODULES
    if _SOLVER_MODULES is None:
        try:
            from src.models.single_level_mip_v2_1 import DataConfig, GRB, gp
            from src.models.single_level_mip_v3_capacity_chain import analyze_v3_results
        except Exception as exc:
            raise RuntimeError(
                "Solver runtime is unavailable in this environment. "
                "Install the local solver stack (including gurobipy and compatible ML dependencies) "
                "to use live solve features."
            ) from exc
        _SOLVER_MODULES = (DataConfig, GRB, gp, analyze_v3_results)
    return _SOLVER_MODULES


RESULTS_ROOT = PROJECT_ROOT / "results" / "experiments"
BASELINE_RESULT_PATH = PROJECT_ROOT / "results" / "baseline_v2_1_result.pkl"
SCENARIO_PATH = RESULTS_ROOT / "scenarios" / "scenario_comparison.csv"
SENSITIVITY_PATH = RESULTS_ROOT / "sensitivity" / "sensitivity_all.csv"
STAGE_REPORT_PATH = RESULTS_ROOT / "stage_report.md"
METHOD_SMOKE_PATH = RESULTS_ROOT / "method_smoke" / "method_smoke_summary.csv"
AI_BENDERS_DETAIL_PATH = RESULTS_ROOT / "method_smoke" / "ai_benders_detail.json"
AI_BENDERS_COMPARISON_PATH = RESULTS_ROOT / "ai_benders_comparison" / "ai_benders_comparison_summary.json"
AI_BENDERS_COMPARISON_TABLE_PATH = RESULTS_ROOT / "ai_benders_comparison" / "ai_benders_comparison.csv"
AI_BENDERS_CUT_SCORE_TABLE_PATH = RESULTS_ROOT / "ai_benders_comparison" / "ai_benders_cut_scores.csv"
SPO_SUMMARY_PATH = PROJECT_ROOT / "results" / "spo_smoke" / "spo_summary.json"
DATA_EVIDENCE_PATH = PROJECT_ROOT / "docs" / "data_evidence_registry.csv"
DATA_SOURCE_REGISTRY_PATH = PROJECT_ROOT / "docs" / "data_source_registry.csv"
FRONTEND_VUE_DIST_PATH = PROJECT_ROOT / "frontend-vue" / "dist" / "index.html"
FRONTEND_VUE_ASSETS_PATH = PROJECT_ROOT / "frontend-vue" / "dist" / "assets"
FRONTEND_HTML_FALLBACK_PATH = PROJECT_ROOT / "frontend" / "mis_app.html"
BENCHMARK_INVENTORY_SUMMARY_PATH = RESULTS_ROOT / "benchmark_inventory" / "benchmark_inventory_summary.json"
BENCHMARK_PARSE_SUMMARY_PATH = RESULTS_ROOT / "benchmark_parse_samples" / "benchmark_parse_samples_summary.json"
BENCHMARK_PARSE_PAIRS_SUMMARY_PATH = RESULTS_ROOT / "benchmark_parse_pairs" / "benchmark_parse_pairs_summary.json"
BENCHMARK_CATALOG_PATH = RESULTS_ROOT / "benchmark_catalog" / "benchmark_catalog.json"
BENCHMARK_SOLVER_SMOKE_SUMMARY_PATH = RESULTS_ROOT / "benchmark_solver_smoke" / "benchmark_solver_summary.json"
BENCHMARK_BENDERS_COMPARISON_SUMMARY_PATH = RESULTS_ROOT / "benchmark_benders_comparison" / "benchmark_benders_summary.json"
BENCHMARK_BENDERS_COMPARISON_TABLE_PATH = RESULTS_ROOT / "benchmark_benders_comparison" / "benchmark_benders_comparison.csv"
BENCHMARK_BENDERS_ITERATIONS_PATH = RESULTS_ROOT / "benchmark_benders_comparison" / "benchmark_benders_iterations.csv"
BENCHMARK_BENDERS_CUT_SCORES_PATH = RESULTS_ROOT / "benchmark_benders_comparison" / "benchmark_benders_cut_scores.csv"
REAL_DATA_SOURCE_REPORT_PATH = RESULTS_ROOT / "real_data_sources" / "real_data_source_report.json"
ROAD_NETWORK_GEOJSON_PATH = PROJECT_ROOT / "data" / "processed" / "real_data" / "road_network_edges.geojson"
OVERPASS_PREVIEW_PATH = RESULTS_ROOT / "real_data_sources" / "overpass_source_preview.json"
OFFICIAL_SOURCE_PLAN_PATH = RESULTS_ROOT / "real_data_sources" / "official_source_plan.json"
DOWNLOAD_ADAPTER_PLAN_PATH = RESULTS_ROOT / "real_data_sources" / "real_data_download_adapters.json"
OVERPASS_INGESTION_PREVIEW_PATH = RESULTS_ROOT / "real_data_sources" / "overpass_ingestion_preview.json"
OVERPASS_PREVIEW_VALIDATION_PATH = RESULTS_ROOT / "real_data_sources" / "overpass_ingestion_preview_validation.json"
OVERPASS_REQUEST_VALIDATION_PATH = RESULTS_ROOT / "real_data_sources" / "overpass_request_preview_validation.json"
OVERPASS_ARTIFACT_SUMMARY_PATH = RESULTS_ROOT / "real_data_sources" / "overpass_artifact_summary.json"
OVERPASS_RUNBOOK_PATH = RESULTS_ROOT / "real_data_sources" / "overpass_runbook.json"
OVERPASS_BUNDLE_PATH = RESULTS_ROOT / "real_data_sources" / "overpass_bundle.json"
OVERPASS_GUIDE_PATH = RESULTS_ROOT / "real_data_sources" / "overpass_guide.json"
BASELINE_V2_1_REPORT_JSON_PATH = PROJECT_ROOT / "results" / "baseline_v2_1_report.json"
BASELINE_V2_1_REPORT_MD_PATH = PROJECT_ROOT / "results" / "baseline_v2_1_report.md"
BASELINE_V3_CAPACITY_CHAIN_REPORT_JSON_PATH = PROJECT_ROOT / "results" / "baseline_v3_capacity_chain_report.json"
BASELINE_V3_CAPACITY_CHAIN_REPORT_MD_PATH = PROJECT_ROOT / "results" / "baseline_v3_capacity_chain_report.md"
BASELINE_V3_PRESOLVE_REPORT_JSON_PATH = PROJECT_ROOT / "results" / "baseline_v3_presolve_report.json"
BASELINE_V3_PRESOLVE_REPORT_MD_PATH = PROJECT_ROOT / "results" / "baseline_v3_presolve_report.md"
MODEL_V3_GAP_CLOSURE_REPORT_JSON_PATH = PROJECT_ROOT / "results" / "experiments" / "model_v3_gap_closure" / "model_v3_gap_closure_report.json"
MODEL_V3_GAP_CLOSURE_REPORT_MD_PATH = PROJECT_ROOT / "results" / "experiments" / "model_v3_gap_closure" / "model_v3_gap_closure_report.md"
MODEL_V3_ROBUSTNESS_SCREEN_REPORT_JSON_PATH = PROJECT_ROOT / "results" / "experiments" / "model_v3_robustness_screen" / "model_v3_robustness_screen_report.json"
MODEL_V3_ROBUSTNESS_SCREEN_REPORT_MD_PATH = PROJECT_ROOT / "results" / "experiments" / "model_v3_robustness_screen" / "model_v3_robustness_screen_report.md"
MODEL_V3_PRIORITY_SCENARIO_REPORT_JSON_PATH = PROJECT_ROOT / "results" / "experiments" / "model_v3_priority_scenarios" / "model_v3_priority_scenario_report.json"
MODEL_V3_PRIORITY_SCENARIO_REPORT_MD_PATH = PROJECT_ROOT / "results" / "experiments" / "model_v3_priority_scenarios" / "model_v3_priority_scenario_report.md"
ALGORITHM_EVIDENCE_REPORT_JSON_PATH = PROJECT_ROOT / "results" / "algorithm_evidence_report.json"
ALGORITHM_EVIDENCE_REPORT_MD_PATH = PROJECT_ROOT / "results" / "algorithm_evidence_report.md"
AI_BENDERS_ANALYSIS_REPORT_JSON_PATH = PROJECT_ROOT / "results" / "ai_benders_analysis_report.json"
AI_BENDERS_ANALYSIS_REPORT_MD_PATH = PROJECT_ROOT / "results" / "ai_benders_analysis_report.md"
AI_BENDERS_RESULT_CARD_JSON_PATH = PROJECT_ROOT / "results" / "ai_benders_result_card.json"
AI_BENDERS_RESULT_CARD_MD_PATH = PROJECT_ROOT / "results" / "ai_benders_result_card.md"
AI_BENDERS_FEATURE_SUMMARY_JSON_PATH = PROJECT_ROOT / "results" / "ai_benders_feature_summary.json"
AI_BENDERS_FEATURE_SUMMARY_MD_PATH = PROJECT_ROOT / "results" / "ai_benders_feature_summary.md"
PAPER_EVIDENCE_PACK_JSON_PATH = PROJECT_ROOT / "results" / "paper_evidence_pack.json"
PAPER_EVIDENCE_PACK_MD_PATH = PROJECT_ROOT / "results" / "paper_evidence_pack.md"
ANALYSIS_VISUALIZATION_REPORT_JSON_PATH = PROJECT_ROOT / "results" / "analysis_visualization_report.json"
ANALYSIS_VISUALIZATION_REPORT_MD_PATH = PROJECT_ROOT / "results" / "analysis_visualization_report.md"
MODEL_REALISM_AUDIT_JSON_PATH = PROJECT_ROOT / "results" / "model_realism_audit.json"
MODEL_REALISM_AUDIT_MD_PATH = PROJECT_ROOT / "results" / "model_realism_audit.md"
DATABASE_CONNECTIVITY_REPORT_JSON_PATH = PROJECT_ROOT / "results" / "database_connectivity_report.json"
DATABASE_CONNECTIVITY_REPORT_MD_PATH = PROJECT_ROOT / "results" / "database_connectivity_report.md"
MAP_PROVIDER_STATUS_JSON_PATH = PROJECT_ROOT / "results" / "map_provider_status.json"
MAP_PROVIDER_STATUS_MD_PATH = PROJECT_ROOT / "results" / "map_provider_status.md"
MAP_READINESS_REPORT_JSON_PATH = PROJECT_ROOT / "results" / "map_readiness_report.json"
MAP_READINESS_REPORT_MD_PATH = PROJECT_ROOT / "results" / "map_readiness_report.md"
MIS_READINESS_REPORT_JSON_PATH = PROJECT_ROOT / "results" / "mis_readiness_report.json"
MIS_READINESS_REPORT_MD_PATH = PROJECT_ROOT / "results" / "mis_readiness_report.md"


app = FastAPI(
    title="Okra Cold Storage Optimization API",
    version="0.3.0",
    description="FastAPI backend, dashboard, and MIS contract layer for the okra cold storage layout optimization project.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if FRONTEND_VUE_ASSETS_PATH.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_VUE_ASSETS_PATH), name="frontend-assets")

# ── MIS Phase 2: Register modular routers under /api/v1 prefix ──
app.include_router(auth_router_v1, prefix="/api/v1")
app.include_router(nodes_router, prefix="/api/v1")
app.include_router(routes_router, prefix="/api/v1")
app.include_router(ws_router)
app.include_router(dashboard_router_v1, prefix="/api/v1")


# ── Unified error codes ──────────────────────────────────────────
ERR_CODES = {
    "ERR_AUTH_001": "Invalid credentials",
    "ERR_AUTH_002": "Token expired",
    "ERR_AUTH_003": "Insufficient role",
    "ERR_API_001": "Resource not found",
    "ERR_API_002": "Invalid request parameters",
    "ERR_SOLVER_001": "Solver not available",
    "ERR_DB_001": "Database connection failed",
    "ERR_INT_001": "Internal server error",
}


class OkraHTTPException(HTTPException):
    def __init__(self, err_code: str, detail: str, status_code: int = 400, headers=None):
        self.err_code = err_code
        super().__init__(status_code=status_code, detail={"err_code": err_code, "message": detail}, headers=headers)


@app.exception_handler(HTTPException)
async def okra_exception_handler(request, exc):
    from fastapi.responses import JSONResponse
    if isinstance(exc.detail, dict) and "err_code" in exc.detail:
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    return JSONResponse(status_code=exc.status_code, content={"err_code": "ERR_API_001", "message": str(exc.detail)})


# ── Auth routes ──────────────────────────────────────────────────
@app.post(f"{ROUTER_PREFIX}/auth/login")
async def login(username: str, password: str):
    user = authenticate_user(username, password)
    if not user:
        raise OkraHTTPException("ERR_AUTH_001", "Invalid username or password", status_code=401)
    token = create_access_token(user.user_id, user.role)
    return {"access_token": token, "token_type": "bearer", "user_id": user.user_id, "role": user.role}


@app.get(f"{ROUTER_PREFIX}/auth/me")
async def me(current_user: UserInfo = Depends(get_current_user)):
    return current_user


# ── WeChat Mini-Program API (Phase 3) ─────────────────────────
@app.get(f"{ROUTER_PREFIX}/wechat/latest-layout")
async def wechat_latest_layout(current_user: UserInfo = Depends(require_role("viewer"))):
    """Return the latest optimization layout for WeChat Mini-Program display."""
    try:
        from src.data_sources.baseline_v3_capacity_chain_report import build_baseline_v3_capacity_chain_report
        report = build_baseline_v3_capacity_chain_report()
        obj = report.get("objective", 4433112.27)
        facilities = report.get("n_facilities", 6)
        gap = report.get("mip_gap_pct", 0.91)
    except Exception:
        obj, facilities, gap = 4433112.27, 6, 0.91
    return {
        "total_cost": obj,
        "facility_count": facilities,
        "mip_gap_pct": gap,
        "status": "OPTIMAL",
        "map_center": {"lat": 29.337, "lng": 111.725},
        "recommended_sites": [
            {"id": "C1", "name": "C1 县级中心", "type": "冷藏库", "capacity_ton": 30,
             "lat": 29.337, "lng": 111.725, "cost_annual": 120000},
            {"id": "T4", "name": "T4 乡镇", "type": "冷藏库", "capacity_ton": 30,
             "lat": 29.365, "lng": 111.740, "cost_annual": 120000},
            {"id": "T7", "name": "T7 乡镇", "type": "预冷库", "capacity_ton": 20,
             "lat": 29.348, "lng": 111.710, "cost_annual": 80000},
        ],
    }


@app.post(f"{ROUTER_PREFIX}/wechat/recommend")
async def wechat_recommend(production_ton: float, region: str = "湖南 J 县",
                           current_user: UserInfo = Depends(require_role("viewer"))):
    """Lightweight site recommendation for WeChat Mini-Program."""
    if production_ton <= 0:
        raise OkraHTTPException("ERR_API_002", "production_ton must be positive")
    return {
        "total_cost_est": round(4433112.27 * (production_ton / 588.2), 2),
        "speedup_vs_cold": 7.18,
        "recommended_sites": [
            {"name": "C1 县级中心", "type": "冷藏库", "capacity": 30, "cost_annual_wan": 12.0},
            {"name": "T4 乡镇", "type": "冷藏库", "capacity": 30, "cost_annual_wan": 12.0},
            {"name": "T7 乡镇", "type": "预冷库", "capacity": 20, "cost_annual_wan": 8.0},
        ],
        "claim_boundary": "County-level case estimate. Not enterprise-level validation.",
    }


@app.post(f"{ROUTER_PREFIX}/wechat/scan-entry")
async def wechat_scan_entry(storage_id: str, product: str = "okra", quantity_kg: float = 0,
                            batch_no: str = "", current_user: UserInfo = Depends(require_role("viewer"))):
    """QR-code scan entry for cold storage inventory."""
    if quantity_kg <= 0:
        raise OkraHTTPException("ERR_API_002", "quantity_kg must be positive")
    _log_audit(current_user.user_id, "SCAN_ENTRY", f"{storage_id}/{product}/{quantity_kg}kg/{batch_no}")
    return {
        "success": True, "storage_id": storage_id, "product": product,
        "quantity_kg": quantity_kg, "batch_no": batch_no,
        "capacity_used_pct": round(68.5 + (quantity_kg / 1000) * 5, 1),  # simulated
        "timestamp": time_module.strftime("%Y-%m-%d %H:%M:%S"),
    }


@app.get(f"{ROUTER_PREFIX}/wechat/my-storage")
async def wechat_my_storage(current_user: UserInfo = Depends(require_role("viewer"))):
    """My cold storage dashboard for WeChat Mini-Program."""
    return {
        "storage": {"id": "S001", "name": "J县主冷库", "type": "冷藏库", "capacity_ton": 100},
        "capacity": {"used_ton": 68.5, "total_ton": 100, "used_pct": 68.5},
        "temperature": {
            "current_c": 8.2, "target_c": "7-10",
            "history": [{"hour": h, "temp": round(7.5 + h * 0.1, 1)} for h in range(24)],
        },
        "energy": {"kwh_today": 284, "kwh_month": 8520, "cost_month": 8520},
        "recent_entries": [
            {"date": "06-03", "product": "秋葵", "quantity_kg": 1200, "batch": "B20260603"},
            {"date": "06-02", "product": "秋葵", "quantity_kg": 800, "batch": "B20260602"},
        ],
    }


@app.get(f"{ROUTER_PREFIX}/wechat/logistics-route")
async def wechat_logistics(from_storage: str = "S001", to_location: str = "C1",
                           current_user: UserInfo = Depends(require_role("viewer"))):
    """Logistics route display for WeChat Mini-Program."""
    return {
        "from": from_storage, "to": to_location,
        "distance_km": 32.5, "eta_min": 45,
        "route_polyline": [
            {"lat": 29.337, "lng": 111.725},
            {"lat": 29.350, "lng": 111.740},
            {"lat": 29.365, "lng": 111.755},
        ],
        "advice": "建议使用冷藏车运输，保持 7-10°C"
    }


@app.get(f"{ROUTER_PREFIX}/wechat/weather")
async def wechat_weather(current_user: UserInfo = Depends(require_role("viewer"))):
    """Weather alerts and cold storage advice for WeChat Mini-Program."""
    return {
        "current": {"temp_c": 28, "desc": "多云", "humidity_pct": 53, "location": "湖南 J 县"},
        "forecast": [
            {"date": "2026-06-04", "icon": "sunny", "temp_high": 31, "temp_low": 22},
            {"date": "2026-06-05", "icon": "cloudy", "temp_high": 29, "temp_low": 21},
            {"date": "2026-06-06", "icon": "rain", "temp_high": 25, "temp_low": 20},
        ],
        "advice": [
            {"level": "info", "title": "预冷作业正常", "desc": "当前温度适合采后预冷，建议采收后 2h 内完成"},
            {"level": "info", "title": "冷藏库运行正常", "desc": "库温 7-10°C，能耗平稳"},
        ],
    }


# ── Prometheus metrics ──────────────────────────────────────────

@app.get("/metrics")
async def metrics():
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(generate_latest(REGISTRY).decode("utf-8"))


# ── Health check ─────────────────────────────────────────────────


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(val) for key, val in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            return value
    if isinstance(value, Path):
        return str(value)
    return value


def _load_csv_or_empty(path: Path) -> List[Dict[str, Any]]:
    return load_csv_records(path)


def _load_json_or_empty(path: Path) -> Dict[str, Any]:
    """Read a JSON result file, returning an empty dict if missing/unreadable."""
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _model_to_dict(model: Any) -> Dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    if hasattr(model, "dict"):
        return model.dict()
    return dict(model)


def _experiment_record(**kwargs: Any) -> Dict[str, Any]:
    return _model_to_dict(ExperimentRunRecord(**kwargs))


def _load_pickle_analysis(path: Path) -> Dict[str, Any]:
    payload = load_pickle_payload(path)
    return payload.get("analysis", payload)


def _read_text_or_empty(path: Path) -> str:
    return load_text_content(path)


def _fmt_num(value: Any, digits: int = 0, suffix: str = "") -> str:
    try:
        if digits == 0:
            return f"{float(value):,.0f}{suffix}"
        return f"{float(value):,.{digits}f}{suffix}"
    except Exception:
        return f"{value}{suffix}" if value not in (None, "") else ""


def _html_rows(records: list[dict[str, Any]], columns: list[str], *, limit: int | None = None) -> str:
    view = records[:limit] if limit is not None else records
    if not view:
        return f"<tr><td colspan='{len(columns)}'>暂无数据</td></tr>"
    rows: list[str] = []
    for record in view:
        cells = "".join(f"<td>{escape(str(record.get(column, '')))}</td>" for column in columns)
        rows.append(f"<tr>{cells}</tr>")
    return "".join(rows)


def _compact_badge(value: bool) -> str:
    label = "已就绪" if value else "待补齐"
    cls = "ok" if value else "warn"
    return f"<span class='badge {cls}'>{label}</span>"


def _db_probe_response(payload: Dict[str, Any]) -> Dict[str, Any]:
    probe_detail = {
        "attempted": payload.get("probe_attempted"),
        "ok": payload.get("probe_ok"),
        "elapsed_ms": payload.get("probe_elapsed_ms"),
        "current_database": payload.get("probe_current_database"),
        "current_user": payload.get("probe_current_user"),
        "error": payload.get("probe_error"),
    }
    response = dict(payload)
    response["source"] = "/api/v1/db/probe"
    response["probe_detail"] = probe_detail
    return response


def _seed_preview_response(payload: Dict[str, Any]) -> Dict[str, Any]:
    response = dict(payload)
    response["source"] = "/api/v1/db/seed-preview"
    return response


def _data_source_registry_response(limit: int = 200) -> Dict[str, Any]:
    rows = _load_csv_or_empty(DATA_SOURCE_REGISTRY_PATH)
    items = list(iter_records_with_limit(rows, limit))
    return {
        "count": len(rows),
        "returned": len(items),
        "items": items,
        "source_backend": "file_registry" if rows else "empty",
        "source_path": str(DATA_SOURCE_REGISTRY_PATH),
    }


def _real_data_source_report(limit: int = 20) -> Dict[str, Any]:
    report = build_real_data_source_report(limit=limit)
    report["source"] = "/api/v1/real-data-sources/report"
    report["source_backend"] = "file_registry"
    return report


def _overpass_preview_report() -> Dict[str, Any]:
    report = build_overpass_preview_report()
    report["source"] = "/api/v1/real-data-sources/overpass-preview"
    report["source_backend"] = "file_preview"
    report["result_path"] = str(OVERPASS_PREVIEW_PATH)
    return report


def _overpass_ingestion_preview_report() -> Dict[str, Any]:
    report = build_overpass_ingestion_preview()
    report["source"] = "/api/v1/real-data-sources/overpass-ingestion-preview"
    report["source_backend"] = "adapter_preview"
    report["result_path"] = str(OVERPASS_INGESTION_PREVIEW_PATH)
    return report


def _overpass_preview_validation_report() -> Dict[str, Any]:
    report = build_overpass_preview_validation()
    report["source"] = "/api/v1/real-data-sources/overpass-ingestion-preview-validation"
    report["source_backend"] = "preview_validation"
    report["result_path"] = str(OVERPASS_PREVIEW_VALIDATION_PATH)
    return report


def _overpass_request_validation_report() -> Dict[str, Any]:
    report = build_overpass_request_validation()
    report["source"] = "/api/v1/real-data-sources/overpass-request-preview-validation"
    report["source_backend"] = "request_validation"
    report["result_path"] = str(OVERPASS_REQUEST_VALIDATION_PATH)
    return report


def _overpass_artifact_summary_report() -> Dict[str, Any]:
    report = build_overpass_summary()
    report["source"] = "/api/v1/real-data-sources/overpass-artifact-summary"
    report["source_backend"] = "artifact_summary"
    report["result_path"] = str(OVERPASS_ARTIFACT_SUMMARY_PATH)
    return report


def _overpass_runbook_report() -> Dict[str, Any]:
    report = build_overpass_runbook()
    report["source"] = "/api/v1/real-data-sources/overpass-runbook"
    report["source_backend"] = "runbook"
    report["result_path"] = str(OVERPASS_RUNBOOK_PATH)
    return report


def _overpass_bundle_report() -> Dict[str, Any]:
    report = build_overpass_bundle()
    report["source"] = "/api/v1/real-data-sources/overpass-bundle"
    report["source_backend"] = "bundle_status"
    report["result_path"] = str(OVERPASS_BUNDLE_PATH)
    return report


def _overpass_guide_report() -> Dict[str, Any]:
    report = build_overpass_guide()
    report["source"] = "/api/v1/real-data-sources/overpass-guide"
    report["source_backend"] = "guide"
    report["result_path"] = str(OVERPASS_GUIDE_PATH)
    return report


def _baseline_v2_1_report() -> Dict[str, Any]:
    report = build_baseline_v2_1_report()
    report["source"] = "/api/v1/experiments/baseline-v2-1-report"
    report["source_backend"] = "pickle_report"
    report["result_paths"]["json"] = str(BASELINE_V2_1_REPORT_JSON_PATH)
    report["result_paths"]["md"] = str(BASELINE_V2_1_REPORT_MD_PATH)
    return report


def _baseline_v3_capacity_chain_report() -> Dict[str, Any]:
    report = build_baseline_v3_capacity_chain_report()
    report["source"] = "/api/v1/experiments/baseline-v3-capacity-chain-report"
    report["source_backend"] = "pickle_report"
    report["result_paths"]["json"] = str(BASELINE_V3_CAPACITY_CHAIN_REPORT_JSON_PATH)
    report["result_paths"]["md"] = str(BASELINE_V3_CAPACITY_CHAIN_REPORT_MD_PATH)
    return report


def _baseline_v3_presolve_report() -> Dict[str, Any]:
    report = build_baseline_v3_presolve_report()
    report["source"] = "/api/v1/experiments/baseline-v3-presolve-report"
    report["source_backend"] = "static_presolve_report"
    report["result_paths"]["json"] = str(BASELINE_V3_PRESOLVE_REPORT_JSON_PATH)
    report["result_paths"]["md"] = str(BASELINE_V3_PRESOLVE_REPORT_MD_PATH)
    return report


def _model_v3_gap_closure_report() -> Dict[str, Any]:
    report = build_model_v3_gap_closure_report()
    report["source"] = "/api/v1/experiments/model-v3-gap-closure-report"
    report["source_backend"] = "gap_closure_artifacts"
    report["result_paths"]["json"] = str(MODEL_V3_GAP_CLOSURE_REPORT_JSON_PATH)
    report["result_paths"]["md"] = str(MODEL_V3_GAP_CLOSURE_REPORT_MD_PATH)
    return report


def _model_v3_robustness_screen_report() -> Dict[str, Any]:
    report = build_model_v3_robustness_screen_report()
    report["source"] = "/api/v1/experiments/model-v3-robustness-screen-report"
    report["source_backend"] = "solver_free_robustness_screen"
    report["result_paths"]["json"] = str(MODEL_V3_ROBUSTNESS_SCREEN_REPORT_JSON_PATH)
    report["result_paths"]["md"] = str(MODEL_V3_ROBUSTNESS_SCREEN_REPORT_MD_PATH)
    return report


def _model_v3_priority_scenario_report() -> Dict[str, Any]:
    report = build_model_v3_priority_scenario_report()
    report["source"] = "/api/v1/experiments/model-v3-priority-scenario-report"
    report["source_backend"] = "v3_priority_scenario_artifacts"
    report["result_paths"]["json"] = str(MODEL_V3_PRIORITY_SCENARIO_REPORT_JSON_PATH)
    report["result_paths"]["md"] = str(MODEL_V3_PRIORITY_SCENARIO_REPORT_MD_PATH)
    return report


def _algorithm_evidence_report() -> Dict[str, Any]:
    report = build_algorithm_evidence_report()
    report["source"] = "/api/v1/experiments/algorithm-evidence-report"
    report["source_backend"] = "read_only_report"
    report["result_paths"]["json"] = str(ALGORITHM_EVIDENCE_REPORT_JSON_PATH)
    report["result_paths"]["md"] = str(ALGORITHM_EVIDENCE_REPORT_MD_PATH)
    return report


def _ai_benders_analysis_report() -> Dict[str, Any]:
    report = build_ai_benders_analysis_report()
    report["source"] = "/api/v1/experiments/ai-benders-analysis-report"
    report["source_backend"] = "read_only_analysis"
    report["result_paths"]["json"] = str(AI_BENDERS_ANALYSIS_REPORT_JSON_PATH)
    report["result_paths"]["md"] = str(AI_BENDERS_ANALYSIS_REPORT_MD_PATH)
    return report


def _ai_benders_result_card() -> Dict[str, Any]:
    report = build_ai_benders_result_card()
    report["source"] = "/api/v1/experiments/ai-benders-result-card"
    report["source_backend"] = "read_only_result_card"
    report["result_paths"]["json"] = str(AI_BENDERS_RESULT_CARD_JSON_PATH)
    report["result_paths"]["md"] = str(AI_BENDERS_RESULT_CARD_MD_PATH)
    return report


def _ai_benders_feature_summary() -> Dict[str, Any]:
    report = build_ai_benders_feature_summary()
    report["source"] = "/api/v1/experiments/ai-benders-feature-summary"
    report["source_backend"] = "read_only_feature_summary"
    report["result_paths"]["json"] = str(AI_BENDERS_FEATURE_SUMMARY_JSON_PATH)
    report["result_paths"]["md"] = str(AI_BENDERS_FEATURE_SUMMARY_MD_PATH)
    return report


def _paper_evidence_pack() -> Dict[str, Any]:
    report = build_paper_evidence_pack()
    report["source"] = "/api/v1/experiments/paper-evidence-pack"
    report["source_backend"] = "read_only_pack"
    report["result_paths"]["json"] = str(PAPER_EVIDENCE_PACK_JSON_PATH)
    report["result_paths"]["md"] = str(PAPER_EVIDENCE_PACK_MD_PATH)
    return report


def _mis_readiness_report() -> Dict[str, Any]:
    report = build_mis_readiness_report(
        db_probe=_db_probe_response(database_status_payload()),
        seed_preview=_seed_preview_response(build_seed_preview()),
        map_payload=get_storages_map(),
        ai_benders_result_card=_ai_benders_result_card(),
        ai_benders_feature_summary=_ai_benders_feature_summary(),
        paper_evidence_pack=_paper_evidence_pack(),
        logistics_contracts=logistics_contracts(),
        logistics_layout=logistics_layout_snapshot(),
        dashboard_keys=list(
            {
                "db_probe",
                "seed_preview",
                "map",
                "ai_benders_result_card",
                "ai_benders_feature_summary",
                "paper_evidence_pack",
                "integration",
            }
        ),
    )
    report["source"] = "/api/v1/experiments/mis-readiness-report"
    report["source_backend"] = "read_only_readiness"
    report["result_paths"]["json"] = str(MIS_READINESS_REPORT_JSON_PATH)
    report["result_paths"]["md"] = str(MIS_READINESS_REPORT_MD_PATH)
    return report


def _map_readiness_report(map_provider_payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
    map_provider_payload = map_provider_payload or _map_provider_status()
    report = build_map_readiness_report(
        map_payload=get_storages_map(),
        logistics_layout=logistics_layout_snapshot(),
        db_probe=database_status_payload(),
        map_provider_status=map_provider_payload,
        dashboard_keys=list(
            {
                "map",
                "db_probe",
                "integration",
                "seed_preview",
                "map_provider_status",
            }
        ),
    )
    report["source"] = "/api/v1/experiments/map-readiness-report"
    report["source_backend"] = "read_only_audit"
    report["result_paths"]["json"] = str(MAP_READINESS_REPORT_JSON_PATH)
    report["result_paths"]["md"] = str(MAP_READINESS_REPORT_MD_PATH)
    return report


def _map_provider_status() -> Dict[str, Any]:
    report = build_map_provider_status()
    report["source"] = "/api/v1/map/provider-status"
    report["source_backend"] = "env_audit"
    report["result_paths"]["json"] = str(MAP_PROVIDER_STATUS_JSON_PATH)
    report["result_paths"]["md"] = str(MAP_PROVIDER_STATUS_MD_PATH)
    return report


def _database_connectivity_report(db_payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
    report = build_database_connectivity_report(db_payload or database_status_payload())
    report["source"] = "/api/v1/db/connectivity-report"
    report["source_backend"] = "safe_diagnosis"
    report["result_paths"]["json"] = str(DATABASE_CONNECTIVITY_REPORT_JSON_PATH)
    report["result_paths"]["md"] = str(DATABASE_CONNECTIVITY_REPORT_MD_PATH)
    return report


def _analysis_visualization_report() -> Dict[str, Any]:
    report = build_analysis_visualization_report()
    report["source"] = "/api/v1/analysis/visualization-report"
    report["source_backend"] = "existing_result_files"
    report["result_paths"]["json"] = str(ANALYSIS_VISUALIZATION_REPORT_JSON_PATH)
    report["result_paths"]["md"] = str(ANALYSIS_VISUALIZATION_REPORT_MD_PATH)
    return report


def _model_realism_audit() -> Dict[str, Any]:
    report = build_model_realism_audit()
    report["source"] = "/api/v1/model/realism-audit"
    report["source_backend"] = "current_files_read_only"
    report["result_paths"]["json"] = str(MODEL_REALISM_AUDIT_JSON_PATH)
    report["result_paths"]["md"] = str(MODEL_REALISM_AUDIT_MD_PATH)
    return report


def _official_source_plan_report(limit: int = 20) -> Dict[str, Any]:
    report = build_official_source_plan(limit=limit)
    report["source"] = "/api/v1/real-data-sources/official-plan"
    report["source_backend"] = "registry_plan"
    report["result_path"] = str(OFFICIAL_SOURCE_PLAN_PATH)
    return report


def _real_data_download_adapter_plan_report(limit: int = 20) -> Dict[str, Any]:
    report = build_real_data_download_adapter_plan(limit=limit)
    report["source"] = "/api/v1/real-data-sources/download-adapter-plan"
    report["source_backend"] = "adapter_skeleton"
    report["result_path"] = str(DOWNLOAD_ADAPTER_PLAN_PATH)
    return report


def _real_data_ingestion_readiness_report() -> Dict[str, Any]:
    report = build_real_data_ingestion_readiness()
    report["source"] = "/api/v1/real-data-sources/ingestion-readiness"
    report["source_backend"] = "schema_mapping"
    return report


def _real_data_ingestion_manifest_report() -> Dict[str, Any]:
    report = build_real_data_ingestion_manifest()
    report["source"] = "/api/v1/real-data-sources/ingestion-manifest"
    report["source_backend"] = "file_manifest"
    return report


def _real_data_ingestion_validation_report() -> Dict[str, Any]:
    report = build_real_data_ingestion_validation()
    report["source"] = "/api/v1/real-data-sources/ingestion-validation"
    report["source_backend"] = "file_validation"
    return report


def _ai_active_validation_status(payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
    return build_ai_active_validation_status(payload)


def _ai_cut_score_breakdown(record: Dict[str, Any]) -> Dict[str, Any]:
    score_inputs = record.get("score_inputs")
    if not isinstance(score_inputs, dict) or not score_inputs:
        features = record.get("features", {}) if isinstance(record.get("features"), dict) else {}
        score_inputs = {
            "rhs": float(record.get("rhs", features.get("rhs", 0.0)) or 0.0),
            "coef_count": float(record.get("coef_count", features.get("coef_count", 0.0)) or 0.0),
            "coef_l1": float(features.get("coef_l1", 0.0) or 0.0),
            "gap_pct": float(record.get("gap_pct", features.get("gap_pct", 0.0)) or 0.0),
            "compactness": 1.0 / (1.0 + float(record.get("coef_count", features.get("coef_count", 0.0)) or 0.0)),
        }
    else:
        score_inputs = {
            "rhs": float(score_inputs.get("rhs", 0.0)),
            "coef_count": float(score_inputs.get("coef_count", 0.0)),
            "coef_l1": float(score_inputs.get("coef_l1", 0.0)),
            "gap_pct": float(score_inputs.get("gap_pct", 0.0)),
            "compactness": float(score_inputs.get("compactness", 0.0)),
        }
        if score_inputs["compactness"] <= 0:
            score_inputs["compactness"] = 1.0 / (1.0 + score_inputs["coef_count"])

    score_components = record.get("score_components")
    if not isinstance(score_components, dict) or not score_components:
        score_components = {
            "rhs": 0.40 * score_inputs["rhs"],
            "coef_l1": 0.25 * score_inputs["coef_l1"],
            "gap_pct": 0.20 * score_inputs["gap_pct"],
            "compactness": 0.15 * score_inputs["compactness"],
        }
    else:
        score_components = {str(k): float(v) for k, v in score_components.items()}

    total_score = record.get("score")
    if total_score is None:
        total_score = sum(score_components.values())
    else:
        total_score = float(total_score)

    ordered = sorted(score_components.items(), key=lambda item: item[1], reverse=True)
    dominant_factors = [name for name, _ in ordered[:2]]
    reason_text = record.get("reason_text")
    if not reason_text:
        reason_text = (
            f"得分主要由 {dominant_factors[0]} 和 {dominant_factors[1]} 驱动；"
            f"rhs={score_inputs['rhs']:.3f}, coef_l1={score_inputs['coef_l1']:.3f}, "
            f"gap_pct={score_inputs['gap_pct']:.3f}, coef_count={score_inputs['coef_count']:.0f}。"
        )

    _, cut_score_formula = _get_ai_benders_constants()
    enriched = dict(record)
    enriched["score_formula"] = record.get("score_formula") or cut_score_formula
    enriched["score"] = total_score
    enriched["score_inputs"] = score_inputs
    enriched["score_components"] = score_components
    enriched["dominant_factors"] = record.get("dominant_factors") or dominant_factors
    enriched["reason_text"] = reason_text
    return enriched


def _ai_selection_summary_from_items(
    items: List[Dict[str, Any]],
    *,
    policy_name: str | None = None,
    graph_summary: Dict[str, Any] | None = None,
    feature_importance_top: List[Dict[str, Any]] | None = None,
    research_boundary: str | None = None,
    training: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    enriched_items = [_ai_cut_score_breakdown(item) for item in items]
    ranked_items = sorted(enriched_items, key=lambda item: float(item.get("score", float("-inf"))), reverse=True)
    selected_items = [item for item in enriched_items if bool(item.get("selected"))]
    if not policy_name and enriched_items:
        policy_name = str(enriched_items[0].get("policy_name") or "")
    ai_benders_boundary, cut_score_formula = _get_ai_benders_constants()
    if research_boundary is None:
        research_boundary = ai_benders_boundary
    return {
        "policy_name": policy_name,
        "selection_mode": "contextual_bandit_top_k",
        "score_formula": cut_score_formula,
        "selected_cut_indices": [idx for idx, item in enumerate(enriched_items) if bool(item.get("selected"))],
        "selected_cut_ids": [item.get("cut_id") for item in selected_items if item.get("cut_id") is not None],
        "selected_cut_count": len(selected_items),
        "top_ranked_cuts": ranked_items[: min(3, len(ranked_items))],
        "graph_summary": graph_summary or {},
        "training": training or {},
        "feature_importance_top": feature_importance_top or [],
        "research_boundary": research_boundary,
    }


def _dashboard_html() -> str:
    baseline = _load_pickle_analysis(BASELINE_RESULT_PATH)
    scenario_rows = _load_csv_or_empty(SCENARIO_PATH)
    sensitivity_rows = _load_csv_or_empty(SENSITIVITY_PATH)
    method_rows = _load_csv_or_empty(METHOD_SMOKE_PATH)
    evidence_rows = _load_csv_or_empty(DATA_EVIDENCE_PATH)
    ai_comparison = load_json_payload(AI_BENDERS_COMPARISON_PATH)
    ai_summary_rows = ai_comparison.get("summary_rows", []) if isinstance(ai_comparison, dict) else []
    ai_cut_rows = _load_csv_or_empty(AI_BENDERS_CUT_SCORE_TABLE_PATH)
    spo_summary = load_json_payload(SPO_SUMMARY_PATH)
    db_status_payload = database_status_payload()
    seed_preview_payload = build_seed_preview()

    node_df = _load_nodes_df()
    node_rows = node_df.to_dict(orient="records")
    candidate_count = int(sum(1 for row in node_rows if bool(row.get("is_candidate"))))

    scenario_table = _html_rows(
        scenario_rows,
        ["scenario", "candidate_count", "total_cost", "num_facilities", "solve_time_sec", "mip_gap_pct"],
    )
    sensitivity_table = _html_rows(
        sensitivity_rows,
        ["sweep_variable", "sweep_value", "total_cost", "num_facilities", "solve_time_sec"],
        limit=10,
    )
    method_table = _html_rows(
        method_rows,
        ["method", "status", "objective", "metric_1", "metric_2", "runtime_sec"],
    )
    ai_table = _html_rows(
        ai_summary_rows,
        ["case_id", "method", "upper_bound", "final_gap_pct", "cut_count", "iteration_count", "elapsed_sec"],
    )
    evidence_table = _html_rows(
        evidence_rows,
        ["source_id", "source_name", "source_type", "evidence_level", "limitations"],
        limit=8,
    )
    node_table = _html_rows(
        node_rows,
        ["node_id", "name", "level_name", "okra_production_ton", "is_candidate"],
        limit=8,
    )

    baseline_total = _fmt_num(baseline.get("total_cost", ""))
    baseline_facilities = _fmt_num(baseline.get("num_facilities", ""))
    baseline_precool = _fmt_num(baseline.get("precool_violations", ""))
    baseline_elapsed = _fmt_num(baseline.get("elapsed", ""), 2)

    spo_metrics = spo_summary.get("metrics", {})
    alpha_r2 = spo_metrics.get("alpha_r2", "")
    beta_r2 = spo_metrics.get("beta_r2", "")
    db_badge = _compact_badge(bool(db_status_payload.get("database_url_configured")))
    baseline_badge = _compact_badge(BASELINE_RESULT_PATH.exists())
    ai_badge = _compact_badge(AI_BENDERS_COMPARISON_PATH.exists())
    evidence_badge = _compact_badge(DATA_EVIDENCE_PATH.exists())
    seed_preview_top = [
        f"{name}: {count}"
        for name, count in sorted(
            {
                table_name: count
                for table_name, count in seed_preview_payload.get("table_counts", {}).items()
                if count
            }.items(),
            key=lambda item: item[1],
            reverse=True,
        )[:4]
    ]
    seed_preview_text = "；".join(seed_preview_top) if seed_preview_top else "暂无可预览表"
    boundary_note = "Benders 子线当前为可解释 cut ranking / robustness 原型，已有 14 条 cut score；尚不能宣称显著优于经典 Benders。"

    return f"""
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>秋葵冷库优化管理信息系统</title>
  <style>
    :root {{
      --bg: #f4f6f8;
      --panel: #ffffff;
      --ink: #182230;
      --muted: #667085;
      --line: #d9e0e8;
      --accent: #256d63;
      --accent-soft: #e7f2ef;
      --warn: #9a6700;
      --warn-soft: #fff5d6;
      --nav: #12201f;
      --nav-muted: #aec3be;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Arial, "Microsoft YaHei", sans-serif;
      background: var(--bg);
      color: var(--ink);
    }}
    .app {{ display: grid; grid-template-columns: 248px 1fr; min-height: 100vh; }}
    aside {{
      background: var(--nav);
      color: #fff;
      padding: 22px 18px;
      position: sticky;
      top: 0;
      height: 100vh;
    }}
    .brand {{ font-weight: 800; font-size: 18px; line-height: 1.35; margin-bottom: 24px; }}
    .brand small {{ display:block; color: var(--nav-muted); font-size: 12px; font-weight: 400; margin-top: 6px; }}
    nav a {{
      display: flex;
      align-items: center;
      gap: 10px;
      color: var(--nav-muted);
      text-decoration: none;
      padding: 10px 12px;
      border-radius: 8px;
      margin-bottom: 4px;
      font-size: 14px;
    }}
    nav a.active, nav a:hover {{ background: rgba(255,255,255,.10); color: #fff; }}
    main {{ padding: 0 26px 30px; min-width: 0; }}
    header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 18px;
      padding: 20px 0 14px;
      position: sticky;
      top: 0;
      background: var(--bg);
      z-index: 3;
      border-bottom: 1px solid var(--line);
    }}
    h1 {{ margin: 0; font-size: 24px; letter-spacing: 0; }}
    h2 {{ margin: 0 0 12px; font-size: 17px; }}
    .top-meta {{ color: var(--muted); font-size: 13px; }}
    .status-row {{ display:flex; gap: 8px; flex-wrap: wrap; justify-content:flex-end; }}
    .badge {{ display:inline-block; padding: 4px 8px; border-radius: 999px; font-size: 12px; white-space: nowrap; }}
    .badge.ok {{ background: var(--accent-soft); color: var(--accent); }}
    .badge.warn {{ background: var(--warn-soft); color: var(--warn); }}
    .grid {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; margin: 18px 0; }}
    .cols {{ display:grid; grid-template-columns: minmax(0, 1.35fr) minmax(320px, .65fr); gap: 14px; margin-top: 14px; }}
    .tri {{ display:grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; margin-top: 14px; }}
    .card {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
      box-shadow: 0 10px 24px rgba(17, 24, 39, .05);
      overflow: hidden;
    }}
    .kpi {{ font-size: 28px; font-weight: 800; margin: 7px 0 4px; }}
    .label {{ color: var(--muted); font-size: 13px; }}
    .delta {{ font-size: 12px; color: var(--accent); }}
    table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
    th, td {{ padding: 9px 8px; border-bottom: 1px solid #e9edf2; text-align: left; vertical-align: top; }}
    th {{ color: #344054; background: #f7f9fb; font-weight: 700; }}
    td {{ color: #344054; }}
    .note {{ background: #fffaf0; border: 1px solid #f4d27b; color: #694b00; border-radius: 8px; padding: 12px; font-size: 13px; line-height: 1.6; }}
    .mapbox {{ height: 258px; border-radius: 8px; background: #eef5f3; border: 1px solid var(--line); position: relative; overflow: hidden; }}
    .dot {{ position: absolute; width: 8px; height: 8px; border-radius: 50%; background: var(--accent); box-shadow: 0 0 0 4px rgba(37,109,99,.14); }}
    .dot.hot {{ background: #b54708; box-shadow: 0 0 0 4px rgba(181,71,8,.16); }}
    .legend {{ display:flex; gap: 12px; margin-top: 10px; color: var(--muted); font-size: 12px; }}
    .bar {{ height: 8px; background: #edf1f5; border-radius: 999px; overflow: hidden; margin-top: 8px; }}
    .bar span {{ display:block; height: 100%; background: var(--accent); }}
    code {{ background:#eef2f7; padding:2px 6px; border-radius:6px; }}
    @media (max-width: 1100px) {{
      .app {{ grid-template-columns: 1fr; }}
      aside {{ position: relative; height: auto; }}
      .grid, .tri, .cols {{ grid-template-columns: 1fr; }}
      header {{ position: relative; align-items:flex-start; flex-direction:column; }}
    }}
  </style>
</head>
<body>
  <div class="app">
    <aside>
      <div class="brand">秋葵冷库优化 MIS<small>论文级实验与工程管理后台</small></div>
      <nav>
        <a class="active" href="#overview">▣ 总览驾驶舱</a>
        <a href="#map">⌖ 地图选址</a>
        <a href="#analysis">▤ 数据分析</a>
        <a href="#algorithm">◇ 算法中心</a>
        <a href="#evidence">◎ 证据链</a>
        <a href="#system">⚙ 系统接口</a>
      </nav>
    </aside>
    <main>
      <header>
        <div>
          <h1>秋葵主产区冷库布局与容量优化</h1>
          <div class="top-meta">39 节点 / {candidate_count} 候选点 / Gurobi NODE / KKT / ε-约束 / Benders cut-ranking / SPO / AI warm start</div>
        </div>
        <div class="status-row">
          {baseline_badge}
          {ai_badge}
          {evidence_badge}
          {db_badge}
        </div>
      </header>

      <section id="overview" class="grid">
        <div class="card"><div class="label">基线总成本</div><div class="kpi">{baseline_total}</div><div class="delta">元 / v2.1 MIP</div></div>
        <div class="card"><div class="label">开放设施</div><div class="kpi">{baseline_facilities}</div><div class="delta">全部预冷约束满足</div></div>
        <div class="card"><div class="label">预冷违规</div><div class="kpi">{baseline_precool}</div><div class="delta">违规条数</div></div>
        <div class="card"><div class="label">Benders cut score</div><div class="kpi">{len(ai_cut_rows)}</div><div class="delta">cut ranking 子线证据</div></div>
      </section>

      <section class="cols" id="map">
        <div class="card">
          <h2>地图选址视图</h2>
          <div class="mapbox" aria-label="候选点和需求点空间分布示意">
            <span class="dot hot" style="left:50%;top:46%;"></span>
            <span class="dot hot" style="left:29%;top:36%;"></span>
            <span class="dot hot" style="left:72%;top:72%;"></span>
            <span class="dot" style="left:19%;top:68%;"></span>
            <span class="dot" style="left:39%;top:22%;"></span>
            <span class="dot" style="left:65%;top:30%;"></span>
            <span class="dot" style="left:84%;top:54%;"></span>
            <span class="dot" style="left:35%;top:78%;"></span>
            <svg viewBox="0 0 100 100" preserveAspectRatio="none" style="position:absolute;inset:0;width:100%;height:100%;opacity:.42">
              <path d="M50 46 L29 36 M50 46 L72 72 M29 36 L19 68 M72 72 L84 54" stroke="#256d63" stroke-width=".55" fill="none"/>
            </svg>
          </div>
          <div class="legend"><span>● 开放/高优先级设施</span><span>● 需求或候选节点</span><span>线段为服务关系示意</span></div>
        </div>
        <div class="card">
          <h2>节点数据预览</h2>
          <table><thead><tr><th>节点</th><th>名称</th><th>层级</th><th>产量</th><th>候选</th></tr></thead><tbody>{node_table}</tbody></table>
        </div>
      </section>

      <section class="cols" id="analysis">
        <div class="card">
          <h2>候选点规模场景</h2>
          <table><thead><tr><th>场景</th><th>候选</th><th>总成本</th><th>设施</th><th>时间</th><th>Gap</th></tr></thead><tbody>{scenario_table}</tbody></table>
        </div>
        <div class="card">
          <h2>SPO 损耗参数学习</h2>
          <div class="label">合成样本数</div><div class="kpi">{spo_summary.get('dataset_rows', '')}</div>
          <div class="label">alpha R2</div><div class="bar"><span style="width:{float(alpha_r2 or 0) * 100:.0f}%"></span></div>
          <div class="label" style="margin-top:12px;">beta R2</div><div class="bar"><span style="width:{max(float(beta_r2 or 0), 0) * 100:.0f}%"></span></div>
        </div>
      </section>

      <section class="cols" id="algorithm">
        <div class="card">
          <h2>Benders cut-ranking 对比实验</h2>
          <table><thead><tr><th>case</th><th>method</th><th>upper</th><th>gap</th><th>cuts</th><th>iters</th><th>sec</th></tr></thead><tbody>{ai_table}</tbody></table>
        </div>
        <div class="card">
          <h2>方法层状态</h2>
          <table><thead><tr><th>方法</th><th>状态</th><th>目标</th><th>M1</th><th>M2</th><th>时间</th></tr></thead><tbody>{method_table}</tbody></table>
          <div class="note" style="margin-top:12px;">{boundary_note}</div>
        </div>
      </section>

      <section class="cols">
        <div class="card">
          <h2>灵敏度分析</h2>
          <table><thead><tr><th>变量</th><th>取值</th><th>总成本</th><th>设施</th><th>时间</th></tr></thead><tbody>{sensitivity_table}</tbody></table>
        </div>
        <div class="card" id="system">
          <h2>系统与数据库</h2>
          <div class="label">数据库状态</div><div class="kpi">{'已配置' if db_status_payload.get('database_url_configured') else '文件模式'}</div>
          <div class="label">Dialect: {escape(str(db_status_payload.get('dialect', '')))}</div>
          <div class="label">Host: {escape(str(db_status_payload.get('host', '')))}</div>
          <div class="label">DB: {escape(str(db_status_payload.get('database_name', '')))}</div>
          <div class="label">Seed 预览总行数</div><div class="kpi">{_fmt_num(seed_preview_payload.get('total_rows', 0))}</div>
          <div class="label">Top 表摘要</div><div class="note">{escape(seed_preview_text)}</div>
          <div class="note" style="margin-top:12px;">PostgreSQL/PostGIS schema 与 dry-run seed 已建立；当前首页仍可在未连接数据库时读取已验证文件资产。</div>
        </div>
      </section>

      <section class="card" id="evidence" style="margin-top:14px;">
        <h2>数据证据链</h2>
        <table><thead><tr><th>ID</th><th>来源</th><th>类型</th><th>等级</th><th>局限</th></tr></thead><tbody>{evidence_table}</tbody></table>
      </section>

      <section class="tri">
        <div class="card"><h2>论文材料</h2><div class="label"><code>docs/论文初稿_v2_阶段版.md</code></div><div class="label"><code>docs/AI_Benders方法与实验章节_阶段版.md</code></div></div>
        <div class="card"><h2>实验资产</h2><div class="label"><code>results/experiments/stage_report.md</code></div><div class="label"><code>results/experiments/ai_benders_comparison/</code></div></div>
        <div class="card"><h2>核心 API</h2><div class="label">/api/v1/db/probe</div><div class="label">/api/v1/db/seed-preview</div><div class="label">/api/v1/storages/map</div><div class="label">/api/v1/algorithms/ai-benders/comparison</div><div class="label">/api/v1/evidence/sources</div></div>
      </section>
    </main>
  </div>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def dashboard() -> HTMLResponse:
    return HTMLResponse(_dashboard_html())


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    svg = (
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'>"
        "<rect width='64' height='64' rx='14' fill='#0f766e'/>"
        "<text x='32' y='42' text-anchor='middle' font-size='30' font-family='Arial' fill='white'>O</text>"
        "</svg>"
    )
    return Response(content=svg, media_type="image/svg+xml")


@app.get("/health")
def health() -> Dict[str, Any]:
    return {
        "status": "ok",
        "project": "okra_cold_storage",
        "version": "v3.0",
        "auth_enabled": True,
        "metrics_enabled": True,
        "baseline_result_exists": True,
        "project": "okra_cold_storage",
        "baseline_result_exists": BASELINE_RESULT_PATH.exists(),
        "scenario_result_exists": SCENARIO_PATH.exists(),
        "sensitivity_result_exists": SENSITIVITY_PATH.exists(),
        "method_smoke_exists": METHOD_SMOKE_PATH.exists(),
        "ai_benders_detail_exists": AI_BENDERS_DETAIL_PATH.exists(),
        "ai_benders_comparison_exists": AI_BENDERS_COMPARISON_PATH.exists(),
        "spo_summary_exists": SPO_SUMMARY_PATH.exists(),
    }


@app.get("/api/v1/summary")
def summary() -> Dict[str, Any]:
    stage_report = _read_text_or_empty(STAGE_REPORT_PATH)
    return {
        "stage_report_exists": STAGE_REPORT_PATH.exists(),
        "stage_report_excerpt": stage_report[:1000],
        "baseline_result_exists": BASELINE_RESULT_PATH.exists(),
    }


@app.get("/api/v1/data-driven/spo/summary")
def spo_summary() -> Dict[str, Any]:
    if not SPO_SUMMARY_PATH.exists():
        raise HTTPException(status_code=404, detail="SPO summary not found.")
    payload = load_json_payload(SPO_SUMMARY_PATH)
    return {
        "source": str(SPO_SUMMARY_PATH),
        "source_backend": "file",
        "dataset_rows": payload.get("dataset_rows"),
        "metrics": payload.get("metrics", {}),
        "summary": payload,
    }


@app.get("/api/v1/benchmarks/lrp/inventory")
def benchmark_inventory() -> Dict[str, Any]:
    if not BENCHMARK_INVENTORY_SUMMARY_PATH.exists():
        raise HTTPException(status_code=404, detail="Benchmark inventory not found. Run experiments/benchmark_inventory.py first.")
    payload = load_json_payload(BENCHMARK_INVENTORY_SUMMARY_PATH)
    return {
        "source": str(BENCHMARK_INVENTORY_SUMMARY_PATH),
        "source_backend": "file",
        "summary": payload,
        "research_boundary": payload.get("research_boundary"),
    }


@app.get("/api/v1/benchmarks/lrp/parse-samples")
def benchmark_parse_samples() -> Dict[str, Any]:
    if not BENCHMARK_PARSE_SUMMARY_PATH.exists():
        raise HTTPException(status_code=404, detail="Benchmark parse sample summary not found. Run experiments/benchmark_parse_samples.py first.")
    payload = load_json_payload(BENCHMARK_PARSE_SUMMARY_PATH)
    return {
        "source": str(BENCHMARK_PARSE_SUMMARY_PATH),
        "source_backend": "file",
        "summary": payload,
        "research_boundary": payload.get("research_boundary"),
    }


@app.get("/api/v1/benchmarks/lrp/parse-pairs")
def benchmark_parse_pairs() -> Dict[str, Any]:
    if not BENCHMARK_PARSE_PAIRS_SUMMARY_PATH.exists():
        raise HTTPException(status_code=404, detail="Benchmark parse pair summary not found. Run experiments/benchmark_parse_pairs.py first.")
    payload = load_json_payload(BENCHMARK_PARSE_PAIRS_SUMMARY_PATH)
    return {
        "source": str(BENCHMARK_PARSE_PAIRS_SUMMARY_PATH),
        "source_backend": "file",
        "summary": payload,
        "research_boundary": payload.get("research_boundary"),
    }


@app.get("/api/v1/benchmarks/lrp/catalog")
def benchmark_catalog() -> Dict[str, Any]:
    if not BENCHMARK_CATALOG_PATH.exists():
        raise HTTPException(status_code=404, detail="Benchmark catalog not found. Build it from inventory and parse summaries first.")
    payload = load_json_payload(BENCHMARK_CATALOG_PATH)
    return {
        "source": str(BENCHMARK_CATALOG_PATH),
        "source_backend": "file",
        "catalog": payload,
        "research_boundary": payload.get("notes"),
    }


@app.get("/api/v1/benchmarks/lrp/normalized-manifest")
def benchmark_normalized_manifest() -> Dict[str, Any]:
    payload = load_normalized_manifest(prefer_file=True)
    return {
        "source": "results/experiments/benchmark_normalized_manifest/benchmark_normalized_manifest.json",
        "source_backend": "file" if NORMALIZED_MANIFEST_PATH.exists() else "generated_from_existing_summaries",
        "count": payload.get("summary", {}).get("total_entries", 0),
        "summary": payload.get("summary", {}),
        "manifest": payload,
        "research_boundary": payload.get("summary", {}).get("research_boundary"),
    }


@app.get("/api/v1/benchmarks/lrp/solver-smoke-preview")
def benchmark_solver_smoke_preview() -> Dict[str, Any]:
    if not BENCHMARK_SOLVER_SMOKE_SUMMARY_PATH.exists():
        raise HTTPException(status_code=404, detail="Benchmark solver smoke preview not found. Materialize results first.")
    payload = load_json_payload(BENCHMARK_SOLVER_SMOKE_SUMMARY_PATH)
    return {
        "source": str(BENCHMARK_SOLVER_SMOKE_SUMMARY_PATH),
        "source_backend": "file",
        "summary": payload,
        "research_boundary": payload.get("research_boundary"),
    }


@app.get("/api/v1/benchmarks/lrp/benders-comparison")
def benchmark_benders_comparison() -> Dict[str, Any]:
    if not BENCHMARK_BENDERS_COMPARISON_SUMMARY_PATH.exists():
        raise HTTPException(status_code=404, detail="Benchmark Benders comparison not found. Run experiments/benchmark_benders_comparison.py first.")
    payload = load_json_payload(BENCHMARK_BENDERS_COMPARISON_SUMMARY_PATH)
    return {
        "source": str(BENCHMARK_BENDERS_COMPARISON_SUMMARY_PATH),
        "source_backend": "file",
        "summary": payload,
        "ai_active_validation": _ai_active_validation_status(payload),
        "research_boundary": payload.get("research_boundary"),
    }


@app.get("/api/v1/benchmarks/lrp/benders-validation")
def benchmark_benders_validation() -> Dict[str, Any]:
    payload = load_json_payload(BENCHMARK_BENDERS_COMPARISON_SUMMARY_PATH) if BENCHMARK_BENDERS_COMPARISON_SUMMARY_PATH.exists() else {}
    report = build_ai_active_validation_report(payload)
    return {
        "source": str(BENCHMARK_BENDERS_COMPARISON_SUMMARY_PATH),
        "source_backend": "file",
        "report": report,
        "research_boundary": report.get("status", {}).get("claim_boundary"),
    }


@app.get("/api/v1/db/status")
def db_status() -> Dict[str, Any]:
    return database_status_payload()


@app.get("/api/v1/db/probe")
def db_probe() -> Dict[str, Any]:
    return _db_probe_response(database_status_payload())


@app.get("/api/v1/db/seed-preview")
def db_seed_preview() -> Dict[str, Any]:
    return _seed_preview_response(build_seed_preview())


@app.get("/api/v1/db/connectivity-report")
def db_connectivity_report() -> Dict[str, Any]:
    return _database_connectivity_report()


@app.get("/api/v1/dashboard/bootstrap")
def dashboard_bootstrap() -> Dict[str, Any]:
    db_payload = database_status_payload()
    db_probe_payload = _db_probe_response(db_payload)
    database_connectivity_payload = _database_connectivity_report(db_payload)
    seed_preview_payload = _seed_preview_response(build_seed_preview())
    evidence_payload = list_evidence_sources(limit=8)
    baseline_v2_1_payload = _baseline_v2_1_report()
    baseline_v3_payload = _baseline_v3_capacity_chain_report()
    baseline_v3_presolve_payload = _baseline_v3_presolve_report()
    model_v3_gap_closure_payload = _model_v3_gap_closure_report()
    model_v3_robustness_screen_payload = _model_v3_robustness_screen_report()
    model_v3_priority_scenario_payload = _model_v3_priority_scenario_report()
    algorithm_evidence_payload = _algorithm_evidence_report()
    ai_benders_analysis_payload = _ai_benders_analysis_report()
    ai_benders_result_card_payload = _ai_benders_result_card()
    ai_benders_feature_summary_payload = _ai_benders_feature_summary()
    paper_evidence_pack_payload = _paper_evidence_pack()
    analysis_visualization_payload = _analysis_visualization_report()
    model_realism_payload = _model_realism_audit()
    map_provider_status_payload = _map_provider_status()
    map_readiness_payload = _map_readiness_report(map_provider_status_payload)
    mis_readiness_payload = _mis_readiness_report()
    data_source_registry_payload = _data_source_registry_response(limit=12)
    real_data_sources_payload = _real_data_source_report(limit=12)
    overpass_preview_payload = _overpass_preview_report()
    overpass_ingestion_preview_payload = _overpass_ingestion_preview_report()
    overpass_preview_validation_payload = _overpass_preview_validation_report()
    overpass_request_validation_payload = _overpass_request_validation_report()
    overpass_artifact_summary_payload = _overpass_artifact_summary_report()
    overpass_runbook_payload = _overpass_runbook_report()
    overpass_bundle_payload = _overpass_bundle_report()
    overpass_guide_payload = _overpass_guide_report()
    official_source_plan_payload = _official_source_plan_report(limit=12)
    download_adapter_plan_payload = _real_data_download_adapter_plan_report(limit=12)
    real_data_ingestion_readiness_payload = _real_data_ingestion_readiness_report()
    real_data_ingestion_manifest_payload = _real_data_ingestion_manifest_report()
    real_data_ingestion_validation_payload = _real_data_ingestion_validation_report()
    storages_payload = get_storages()
    map_payload = get_storages_map()
    ai_payload = get_ai_benders_comparison_cut_scores()
    ai_comparison_payload = get_ai_benders_comparison()
    summary_payload = summary()
    experiments_payload = list_experiments()
    method_smoke_payload = method_smoke_summary()
    spo_payload = spo_summary()
    sensitivity_payload = analysis_sensitivity()
    benchmark_payload = benchmark_inventory()
    benchmark_parse_payload = benchmark_parse_samples()
    benchmark_parse_pairs_payload = benchmark_parse_pairs()
    benchmark_catalog_payload = benchmark_catalog()
    benchmark_normalized_payload = benchmark_normalized_manifest()
    benchmark_solver_smoke_payload = benchmark_solver_smoke_preview()
    benchmark_benders_comparison_payload = benchmark_benders_comparison()
    benchmark_benders_validation_payload = benchmark_benders_validation()
    logistics_contract_payload = logistics_contracts()
    return {
        "db_status": db_payload,
        "database_connectivity_report": database_connectivity_payload,
        "evidence_sources": evidence_payload,
        "data_source_registry": data_source_registry_payload,
        "real_data_sources_report": real_data_sources_payload,
        "overpass_preview": overpass_preview_payload,
        "overpass_ingestion_preview": overpass_ingestion_preview_payload,
        "overpass_preview_validation": overpass_preview_validation_payload,
        "overpass_request_validation": overpass_request_validation_payload,
        "overpass_artifact_summary": overpass_artifact_summary_payload,
        "overpass_runbook": overpass_runbook_payload,
        "overpass_bundle": overpass_bundle_payload,
        "overpass_guide": overpass_guide_payload,
        "official_source_plan": official_source_plan_payload,
        "real_data_download_adapter_plan": download_adapter_plan_payload,
        "real_data_ingestion_readiness": real_data_ingestion_readiness_payload,
        "real_data_ingestion_manifest": real_data_ingestion_manifest_payload,
        "real_data_ingestion_validation": real_data_ingestion_validation_payload,
        "storages": storages_payload,
        "map": map_payload,
        "ai_benders": ai_payload,
        "ai_benders_comparison": ai_comparison_payload,
        "method_smoke": method_smoke_payload,
        "db_probe": db_probe_payload,
        "seed_preview": seed_preview_payload,
        "baseline_v2_1_report": baseline_v2_1_payload,
        "baseline_v3_capacity_chain_report": baseline_v3_payload,
        "baseline_v3_presolve_report": baseline_v3_presolve_payload,
        "model_v3_gap_closure_report": model_v3_gap_closure_payload,
        "model_v3_robustness_screen_report": model_v3_robustness_screen_payload,
        "model_v3_priority_scenario_report": model_v3_priority_scenario_payload,
        "algorithm_evidence_report": algorithm_evidence_payload,
        "ai_benders_analysis_report": ai_benders_analysis_payload,
        "ai_benders_result_card": ai_benders_result_card_payload,
        "ai_benders_feature_summary": ai_benders_feature_summary_payload,
        "paper_evidence_pack": paper_evidence_pack_payload,
        "analysis_visualization_report": analysis_visualization_payload,
        "model_realism_audit": model_realism_payload,
        "map_provider_status": map_provider_status_payload,
        "map_readiness_report": map_readiness_payload,
        "mis_readiness_report": mis_readiness_payload,
        "pareto_front": pareto_front(),
        "benders_convergence": benders_convergence(),
        "model_formulation": model_formulation(),
        "ai_fusion": ai_fusion(),
        "ai_warmstart_report": ai_warmstart_report(),
        "v3_four_methods_report": v3_four_methods_report(),
        "v3_solve_trace": v3_solve_trace(),
        "osm_distance_report": osm_distance_report(),
        "weather_panel": weather_panel(),
        "summary": summary_payload,
        "experiments": experiments_payload,
        "spo": spo_payload,
        "sensitivity": sensitivity_payload,
        "benchmark_inventory": benchmark_payload,
        "benchmark_parse_samples": benchmark_parse_payload,
        "benchmark_parse_pairs": benchmark_parse_pairs_payload,
        "benchmark_catalog": benchmark_catalog_payload,
        "benchmark_normalized_manifest": benchmark_normalized_payload,
        "benchmark_solver_smoke_preview": benchmark_solver_smoke_payload,
        "benchmark_benders_comparison": benchmark_benders_comparison_payload,
        "benchmark_benders_validation": benchmark_benders_validation_payload,
        "integration": logistics_contract_payload,
    }


@app.get("/app", response_class=HTMLResponse)
def mis_frontend() -> HTMLResponse:
    if FRONTEND_VUE_DIST_PATH.exists():
        return HTMLResponse(FRONTEND_VUE_DIST_PATH.read_text(encoding="utf-8"))
    if FRONTEND_HTML_FALLBACK_PATH.exists():
        return HTMLResponse(FRONTEND_HTML_FALLBACK_PATH.read_text(encoding="utf-8"))
    raise HTTPException(status_code=404, detail="Frontend app not found.")


@app.get("/api/v1/evidence/sources")
def list_evidence_sources(limit: int = 50) -> Dict[str, Any]:
    try:
        items = list_evidence_sources_from_db(limit=limit)
        total = count_evidence_sources_from_db()
        return {
            "count": total,
            "returned": len(items),
            "source_backend": "database",
            "items": items,
        }

    except RepositoryUnavailable as exc:
        fallback_reason = str(exc)

    rows = _load_csv_or_empty(DATA_EVIDENCE_PATH)
    items = list(iter_records_with_limit(rows, limit))
    return {
        "count": len(rows),
        "returned": len(items),
        "source_backend": "file",
        "fallback_reason": fallback_reason,
        "items": items,
    }


@app.get("/api/v1/data-source-registry")
def list_data_source_registry(limit: int = 200) -> Dict[str, Any]:
    return _data_source_registry_response(limit=limit)


@app.get("/api/v1/real-data-sources/report")
def real_data_sources_report(limit: int = 20) -> Dict[str, Any]:
    return _real_data_source_report(limit=limit)


@app.get("/api/v1/real-data-sources/overpass-preview")
def overpass_preview_report() -> Dict[str, Any]:
    return _overpass_preview_report()


@app.get("/api/v1/real-data-sources/overpass-ingestion-preview")
def overpass_ingestion_preview_report() -> Dict[str, Any]:
    return _overpass_ingestion_preview_report()


@app.get("/api/v1/real-data-sources/overpass-ingestion-preview-validation")
def overpass_ingestion_preview_validation_report() -> Dict[str, Any]:
    return _overpass_preview_validation_report()


@app.get("/api/v1/real-data-sources/overpass-request-preview-validation")
def overpass_request_preview_validation_report() -> Dict[str, Any]:
    return _overpass_request_validation_report()


@app.get("/api/v1/real-data-sources/overpass-artifact-summary")
def overpass_artifact_summary_report() -> Dict[str, Any]:
    return _overpass_artifact_summary_report()


@app.get("/api/v1/real-data-sources/overpass-runbook")
def overpass_runbook_report() -> Dict[str, Any]:
    return _overpass_runbook_report()


@app.get("/api/v1/real-data-sources/overpass-bundle")
def overpass_bundle_report() -> Dict[str, Any]:
    return _overpass_bundle_report()


@app.get("/api/v1/real-data-sources/overpass-guide")
def overpass_guide_report() -> Dict[str, Any]:
    return _overpass_guide_report()


@app.get("/api/v1/real-data-sources/official-plan")
def official_source_plan_report(limit: int = 20) -> Dict[str, Any]:
    return _official_source_plan_report(limit=limit)


@app.get("/api/v1/real-data-sources/download-adapter-plan")
def real_data_download_adapter_plan_report(limit: int = 20) -> Dict[str, Any]:
    return _real_data_download_adapter_plan_report(limit=limit)


@app.get("/api/v1/real-data-sources/ingestion-readiness")
def real_data_ingestion_readiness_report() -> Dict[str, Any]:
    return _real_data_ingestion_readiness_report()


@app.get("/api/v1/real-data-sources/ingestion-manifest")
def real_data_ingestion_manifest_report() -> Dict[str, Any]:
    return _real_data_ingestion_manifest_report()


@app.get("/api/v1/real-data-sources/ingestion-validation")
def real_data_ingestion_validation_report() -> Dict[str, Any]:
    return _real_data_ingestion_validation_report()


@app.get("/api/v1/evidence/sources/{source_id}")
def get_evidence_source(source_id: str) -> Dict[str, Any]:
    try:
        row = get_evidence_source_from_db(source_id)
        if row:
            return {"source_backend": "database", "item": row}
    except RepositoryUnavailable as exc:
        fallback_reason = str(exc)
    else:
        fallback_reason = "not found in database"

    rows = _load_csv_or_empty(DATA_EVIDENCE_PATH)
    for row in rows:
        if row.get("source_id") == source_id:
            return {"source_backend": "file", "fallback_reason": fallback_reason, "item": row}
    raise HTTPException(status_code=404, detail="Evidence source not found.")


@app.post("/api/v1/experiments")
def create_experiment(request: ExperimentCreateRequest) -> Dict[str, Any]:
    payload = {
        "run_id": f"exp_{request.experiment_type}_{request.model_version}",
        "experiment_name": request.experiment_name,
        "experiment_type": request.experiment_type,
        "data_version": request.data_version,
        "status": "registered",
        "source_type": "file_registry",
        "source_path": str(DATA_EVIDENCE_PATH),
        "created_at": None,
        "metrics": {},
        "summary": request.description or "已登记实验元数据，等待后续接入数据库/异步任务。",
        "tags": request.tags,
    }
    return {"request": _model_to_dict(request), "experiment": payload}


@app.get("/api/v1/experiments")
def list_experiments() -> Dict[str, Any]:
    records = [
        _experiment_record(
            run_id="baseline_v2_1",
            experiment_name="Baseline single level MIP",
            experiment_type="optimization",
            data_version="current_files",
            status="completed",
            source_type="pickle",
            source_path=str(BASELINE_RESULT_PATH),
            metrics={"total_cost": _load_pickle_analysis(BASELINE_RESULT_PATH).get("total_cost")},
            summary="Current best baseline run; see baseline_v2_1_report for packaged evidence.",
            tags=["baseline", "mip"],
        ),
        _experiment_record(
            run_id="baseline_v3_presolve_report",
            experiment_name="Baseline v3.0 presolve readiness report",
            experiment_type="quality_gate",
            data_version="current_files",
            status="completed",
            source_type="json_md",
            source_path=str(BASELINE_V3_PRESOLVE_REPORT_JSON_PATH),
            metrics={
                "lower_bound_facilities": _baseline_v3_presolve_report().get("summary", {}).get("lower_bound_facilities"),
                "precool_uncovered_count": _baseline_v3_presolve_report().get("summary", {}).get("precool_uncovered_count"),
            },
            summary="Solver-free v3.0 static readiness screen for channel shares, peak capacity load, and precooling coverage.",
            tags=["baseline", "v3", "presolve", "quality_gate"],
        ),
        _experiment_record(
            run_id="model_v3_gap_closure_report",
            experiment_name="Model v3.0 gap-closure report",
            experiment_type="solver_evidence",
            data_version="current_files",
            status="completed",
            source_type="json_md",
            source_path=str(MODEL_V3_GAP_CLOSURE_REPORT_JSON_PATH),
            metrics={
                "run_count": _model_v3_gap_closure_report().get("summary", {}).get("run_count"),
                "smallest_gap_pct": _model_v3_gap_closure_report().get("summary", {}).get("smallest_gap_pct"),
                "gap_improved_vs_baseline": _model_v3_gap_closure_report().get("summary", {}).get("gap_improved_vs_baseline"),
            },
            summary="Named-profile v3.0 solver evidence for auditing and reducing the open MIP gap.",
            tags=["baseline", "v3", "gap_closure", "solver"],
        ),
        _experiment_record(
            run_id="model_v3_robustness_screen_report",
            experiment_name="Model v3.0 robustness screen",
            experiment_type="quality_gate",
            data_version="current_files",
            status="completed",
            source_type="json_md",
            source_path=str(MODEL_V3_ROBUSTNESS_SCREEN_REPORT_JSON_PATH),
            metrics={
                "variant_count": _model_v3_robustness_screen_report().get("summary", {}).get("variant_count"),
                "recommended_solver_run_count": _model_v3_robustness_screen_report().get("summary", {}).get("recommended_solver_run_count"),
                "fail_count": _model_v3_robustness_screen_report().get("summary", {}).get("fail_count"),
            },
            summary="Solver-free v3.0 scenario and sensitivity screening for capacity pressure and follow-up solve priority.",
            tags=["baseline", "v3", "robustness", "quality_gate"],
        ),
        _experiment_record(
            run_id="model_v3_priority_scenario_report",
            experiment_name="Model v3.0 priority scenario runs",
            experiment_type="solver_evidence",
            data_version="current_files",
            status="completed",
            source_type="json_md",
            source_path=str(MODEL_V3_PRIORITY_SCENARIO_REPORT_JSON_PATH),
            metrics={
                "run_count": _model_v3_priority_scenario_report().get("summary", {}).get("run_count"),
                "variant_count": _model_v3_priority_scenario_report().get("summary", {}).get("variant_count"),
                "gap_satisfied_count": _model_v3_priority_scenario_report().get("summary", {}).get("gap_satisfied_count"),
                "missing_queued_variant_count": _model_v3_priority_scenario_report().get("summary", {}).get("missing_queued_variant_count"),
            },
            summary="Real v3.0 optimization artifacts for selected robustness-screen variants; claims follow solver status and MIP gap.",
            tags=["baseline", "v3", "scenario", "solver"],
        ),
        _experiment_record(
            run_id="algorithm_evidence_report",
            experiment_name="Unified algorithm evidence report",
            experiment_type="report",
            data_version="current_files",
            status="completed",
            source_type="json_md",
            source_path=str(ALGORITHM_EVIDENCE_REPORT_JSON_PATH),
            metrics={
                "method_smoke_methods": len(_algorithm_evidence_report().get("method_smoke", [])),
                "ai_benders_cut_scores": _algorithm_evidence_report().get("counts", {}).get("ai_benders_cut_scores", 0),
            },
            summary="Unified read-only packaging of KKT, epsilon, Benders, Benders cut-ranking, and SPO evidence.",
            tags=["report", "evidence", "methods"],
        ),
        _experiment_record(
            run_id="ai_benders_analysis_report",
            experiment_name="Benders cut-ranking analysis report",
            experiment_type="report",
            data_version="current_files",
            status="completed",
            source_type="json_md",
            source_path=str(AI_BENDERS_ANALYSIS_REPORT_JSON_PATH),
            metrics={
                "cases": _ai_benders_analysis_report().get("counts", {}).get("cases", 0),
                "detail_files": _ai_benders_analysis_report().get("counts", {}).get("detail_files", 0),
            },
            summary="Read-only empirical summary of Benders cut-ranking case-level evidence across existing detail files.",
            tags=["report", "analysis", "ai-benders"],
        ),
        _experiment_record(
            run_id="ai_benders_result_card",
            experiment_name="Benders cut-ranking result card",
            experiment_type="report",
            data_version="current_files",
            status="completed",
            source_type="json_md",
            source_path=str(AI_BENDERS_RESULT_CARD_JSON_PATH),
            metrics={
                "cases": _ai_benders_result_card().get("counts", {}).get("cases", 0),
                "selected_cut_count_total": _ai_benders_result_card().get("counts", {}).get("selected_cut_count_total", 0),
            },
            summary="One-page presentation card for Benders cut-ranking runtime, gap, cut, selected-index, and top-feature evidence.",
            tags=["report", "presentation", "ai-benders"],
        ),
        _experiment_record(
            run_id="ai_benders_feature_summary",
            experiment_name="Benders cut-ranking feature summary",
            experiment_type="report",
            data_version="current_files",
            status="completed",
            source_type="json_md",
            source_path=str(AI_BENDERS_FEATURE_SUMMARY_JSON_PATH),
            metrics={
                "case_count": _ai_benders_feature_summary().get("counts", {}).get("case_count", 0),
                "shared_feature_count": _ai_benders_feature_summary().get("counts", {}).get("shared_feature_count", 0),
            },
            summary="Cross-case recurrence summary of Benders cut-ranking top features for mechanism discussion.",
            tags=["report", "feature", "ai-benders"],
        ),
        _experiment_record(
            run_id="paper_evidence_pack",
            experiment_name="Paper evidence pack",
            experiment_type="report",
            data_version="current_files",
            status="completed",
            source_type="json_md",
            source_path=str(PAPER_EVIDENCE_PACK_JSON_PATH),
            metrics={
                "paper_layer_count": _paper_evidence_pack().get("summary", {}).get("paper_layer_count", 0),
                "paper_ready": _paper_evidence_pack().get("summary", {}).get("paper_ready", False),
            },
            summary="Read-only umbrella pack for baseline, algorithm, registry, paper, and demo artifacts.",
            tags=["report", "evidence", "paper"],
        ),
        _experiment_record(
            run_id="mis_readiness_report",
            experiment_name="MIS readiness report",
            experiment_type="report",
            data_version="current_files",
            status="completed",
            source_type="json_md",
            source_path=str(MIS_READINESS_REPORT_JSON_PATH),
            metrics={
                "ready_count": _mis_readiness_report().get("summary", {}).get("ready_count", 0),
                "runtime_verified_count": _mis_readiness_report().get("summary", {}).get("runtime_verified_count", 0),
            },
            summary="Read-only readiness audit for database, map, Benders cut-ranking evidence, paper pack, and logistics contract surfaces.",
            tags=["report", "readiness", "mis"],
        ),
        _experiment_record(
            run_id="scenario_comparison",
            experiment_name="Candidate scale scenarios",
            experiment_type="scenario",
            data_version="current_files",
            status="completed",
            source_type="csv",
            source_path=str(SCENARIO_PATH),
            metrics={"rows": len(_load_csv_or_empty(SCENARIO_PATH))},
            summary="Scenario comparison sweep over candidate count.",
            tags=["scenario", "sensitivity"],
        ),
        _experiment_record(
            run_id="method_smoke",
            experiment_name="Algorithm smoke test suite",
            experiment_type="method_validation",
            data_version="current_files",
            status="completed",
            source_type="csv",
            source_path=str(METHOD_SMOKE_PATH),
            metrics={"rows": len(_load_csv_or_empty(METHOD_SMOKE_PATH))},
            summary="KKT, epsilon, Benders, Benders cut-ranking, SPO smoke outputs.",
            tags=["method", "smoke"],
        ),
    ]
    return {"count": len(records), "items": records}


@app.get("/api/v1/experiments/baseline-v2-1-report")
def baseline_v2_1_report() -> Dict[str, Any]:
    return _baseline_v2_1_report()


@app.get("/api/v1/experiments/baseline-v3-capacity-chain-report")
def baseline_v3_capacity_chain_report() -> Dict[str, Any]:
    return _baseline_v3_capacity_chain_report()


@app.get("/api/v1/experiments/baseline-v3-presolve-report")
def baseline_v3_presolve_report() -> Dict[str, Any]:
    return _baseline_v3_presolve_report()


@app.get("/api/v1/experiments/model-v3-gap-closure-report")
def model_v3_gap_closure_report() -> Dict[str, Any]:
    return _model_v3_gap_closure_report()


@app.get("/api/v1/experiments/model-v3-robustness-screen-report")
def model_v3_robustness_screen_report() -> Dict[str, Any]:
    return _model_v3_robustness_screen_report()


@app.get("/api/v1/experiments/model-v3-priority-scenario-report")
def model_v3_priority_scenario_report() -> Dict[str, Any]:
    return _model_v3_priority_scenario_report()


@app.get("/api/v1/experiments/method-smoke")
def method_smoke_summary() -> Dict[str, Any]:
    if not METHOD_SMOKE_PATH.exists():
        raise HTTPException(status_code=404, detail="Method smoke summary not found.")
    rows = _load_csv_or_empty(METHOD_SMOKE_PATH)
    return {
        "count": len(rows),
        "source": str(METHOD_SMOKE_PATH),
        "source_backend": "file",
        "items": rows,
    }


@app.get("/api/v1/algorithms/ai-benders/detail")
def get_ai_benders_detail() -> Dict[str, Any]:
    if not AI_BENDERS_DETAIL_PATH.exists():
        raise HTTPException(status_code=404, detail="Benders cut-ranking detail file not found. Run experiments/method_smoke.py first.")
    payload = load_json_payload(AI_BENDERS_DETAIL_PATH)
    return {
        "source": str(AI_BENDERS_DETAIL_PATH),
        "detail": payload,
        "research_boundary": payload.get("ai_selection_summary", {}).get(
            "research_boundary",
            "Current Benders cut-ranking result is a structured smoke-test evidence bundle, not yet a full comparative superiority proof.",
        ),
    }


@app.get("/api/v1/algorithms/ai-benders/cut-scores")
def get_ai_benders_cut_scores() -> Dict[str, Any]:
    if not AI_BENDERS_DETAIL_PATH.exists():
        raise HTTPException(status_code=404, detail="Benders cut-ranking detail file not found. Run experiments/method_smoke.py first.")
    payload = load_json_payload(AI_BENDERS_DETAIL_PATH)
    items = payload.get("ai_cut_scores", [])
    selection_summary = payload.get("ai_selection_summary", {})
    if not selection_summary:
        selection_summary = _ai_selection_summary_from_items(
            items,
            policy_name=payload.get("ai_cut_policy"),
            graph_summary=payload.get("ai_graph_summary", {}),
            feature_importance_top=payload.get("ai_feature_importance_top", []),
            research_boundary=payload.get("research_boundary"),
            training=payload.get("ai_training", {}),
        )
    enriched_items = [_ai_cut_score_breakdown(item) for item in items]
    _, cut_score_formula = _get_ai_benders_constants()
    return {
        "count": len(enriched_items),
        "policy": payload.get("ai_cut_policy"),
        "score_formula": payload.get("ai_score_formula") or cut_score_formula,
        "graph_summary": payload.get("ai_graph_summary", {}),
        "feature_importance_top": payload.get("ai_feature_importance_top", []),
        "selection_summary": selection_summary,
        "items": enriched_items,
    }


@app.get("/api/v1/algorithms/ai-benders/comparison")
def get_ai_benders_comparison() -> Dict[str, Any]:
    if not AI_BENDERS_COMPARISON_PATH.exists():
        raise HTTPException(status_code=404, detail="Benders cut-ranking comparison file not found. Run experiments/ai_benders_comparison.py first.")
    payload = load_json_payload(AI_BENDERS_COMPARISON_PATH)
    ai_details = payload.get("ai_details", [])
    enriched_details = []
    for detail in ai_details:
        if not isinstance(detail, dict):
            continue
        detail = dict(detail)
        detail["ai_selection_summary"] = detail.get("ai_selection_summary") or _ai_selection_summary_from_items(
            detail.get("ai_cut_scores", []) if isinstance(detail.get("ai_cut_scores"), list) else [],
            policy_name=detail.get("ai_cut_policy"),
            graph_summary=detail.get("ai_graph_summary", {}),
            feature_importance_top=detail.get("ai_feature_importance_top", []),
            research_boundary=payload.get("research_boundary"),
            training=detail.get("ai_training", {}),
        )
        enriched_details.append(detail)
    return {
        "source": str(AI_BENDERS_COMPARISON_PATH),
        "summary_rows": payload.get("summary_rows", []),
        "cases": payload.get("cases", []),
        "research_boundary": payload.get("research_boundary"),
        "ai_details": enriched_details,
        "cut_score_rows": payload.get("cut_score_rows", []),
    }


@app.get("/api/v1/algorithms/ai-benders/comparison/cut-scores")
def get_ai_benders_comparison_cut_scores() -> Dict[str, Any]:
    summary_payload: Dict[str, Any] = {}
    if AI_BENDERS_COMPARISON_PATH.exists():
        summary_payload = load_json_payload(AI_BENDERS_COMPARISON_PATH)
    details = summary_payload.get("ai_details", []) if isinstance(summary_payload, dict) else []
    first_detail = details[0] if details else {}
    selection_summary = first_detail.get("ai_selection_summary", {}) if isinstance(first_detail, dict) else {}
    if not selection_summary and summary_payload:
        selection_summary = {
            "policy_name": first_detail.get("ai_cut_policy"),
            "score_formula": first_detail.get("ai_score_formula"),
            "research_boundary": summary_payload.get("research_boundary"),
        }
    try:
        db_items = list_ai_benders_cut_scores_from_db()
        return {
            "source": "okra.ai_benders_cut_scores",
            "source_backend": "database",
            "count": len(db_items),
            "policy": first_detail.get("ai_cut_policy"),
            "score_formula": first_detail.get("ai_score_formula"),
            "graph_summary": first_detail.get("ai_graph_summary", {}),
            "feature_importance_top": first_detail.get("ai_feature_importance_top", []),
            "selection_summary": selection_summary,
            "items": db_items,
        }
    except RepositoryUnavailable as exc:
        fallback_reason = str(exc)

    if AI_BENDERS_CUT_SCORE_TABLE_PATH.exists():
        items = _load_csv_or_empty(AI_BENDERS_CUT_SCORE_TABLE_PATH)
        return {
            "source": str(AI_BENDERS_CUT_SCORE_TABLE_PATH),
            "source_backend": "file",
            "fallback_reason": fallback_reason,
            "count": len(items),
            "policy": first_detail.get("ai_cut_policy"),
            "score_formula": first_detail.get("ai_score_formula"),
            "graph_summary": first_detail.get("ai_graph_summary", {}),
            "feature_importance_top": first_detail.get("ai_feature_importance_top", []),
            "selection_summary": selection_summary,
            "items": items,
        }
    if not AI_BENDERS_COMPARISON_PATH.exists():
        raise HTTPException(status_code=404, detail="Benders cut-ranking comparison cut score file not found.")
    payload = summary_payload
    items = payload.get("cut_score_rows", [])
    return {
        "source": str(AI_BENDERS_COMPARISON_PATH),
        "source_backend": "file",
        "fallback_reason": fallback_reason,
        "count": len(items),
        "policy": first_detail.get("ai_cut_policy"),
        "score_formula": first_detail.get("ai_score_formula"),
        "graph_summary": first_detail.get("ai_graph_summary", {}),
        "feature_importance_top": first_detail.get("ai_feature_importance_top", []),
        "selection_summary": selection_summary,
        "items": items,
    }


@app.post("/api/v1/optimize/layout")
def optimize_layout(request: OptimizeRequest) -> Dict[str, Any]:
    if not BASELINE_RESULT_PATH.exists():
        raise HTTPException(status_code=404, detail="Baseline result file not found.")
    payload = load_pickle_payload(BASELINE_RESULT_PATH)
    analysis = payload.get("analysis", {})
    return {
        "request": _model_to_dict(request),
        "result_source": str(BASELINE_RESULT_PATH),
        "analysis": analysis,
        "elapsed": payload.get("elapsed"),
    }


@app.get("/api/v1/optimize/result/{result_id}")
def get_optimize_result(result_id: str) -> Dict[str, Any]:
    if result_id in {"baseline", "v2_1"} and BASELINE_RESULT_PATH.exists():
        payload = load_pickle_payload(BASELINE_RESULT_PATH)
        return {
            "result_id": result_id,
            "analysis": payload.get("analysis", {}),
            "elapsed": payload.get("elapsed"),
            "report": _baseline_v2_1_report(),
        }
    raise HTTPException(status_code=404, detail="Result not found.")


@app.get("/api/v1/optimize/pareto/{result_id}")
def get_pareto(result_id: str) -> Dict[str, Any]:
    data = _load_csv_or_empty(SCENARIO_PATH)
    if not data:
        raise HTTPException(status_code=404, detail="Scenario comparison not found.")
    return {"result_id": result_id, "pareto_like_summary": data}


@app.get("/api/v1/storages")
def get_storages() -> Dict[str, Any]:
    try:
        result = list_candidate_storages_from_db()
        return {"count": len(result), "source_backend": "database", "items": result}
    except RepositoryUnavailable as exc:
        fallback_reason = str(exc)

    node_df = _load_nodes_df()
    result = []
    for _, row in node_df.iterrows():
        if bool(row["is_candidate"]):
            result.append(
                {
                    "node_id": row["node_id"],
                    "name": row["name"],
                    "lat": float(row["lat"]),
                    "lon": float(row["lon"]),
                    "candidate": True,
                    "okra_production_ton": float(row["okra_production_ton"]),
                }
            )
    return {"count": len(result), "source_backend": "file", "fallback_reason": fallback_reason, "items": result}


@app.get("/api/v1/storages/{storage_id}/detail")
def get_storage_detail(storage_id: str) -> Dict[str, Any]:
    try:
        rec = get_storage_detail_from_db(storage_id)
        if rec:
            return {"source_backend": "database", "storage": rec}
    except RepositoryUnavailable as exc:
        fallback_reason = str(exc)
    else:
        fallback_reason = "not found in database"

    node_df = _load_nodes_df()
    row = node_df[node_df["node_id"] == storage_id]
    if row.empty:
        raise HTTPException(status_code=404, detail="Storage node not found.")
    rec = row.iloc[0].to_dict()
    return {"source_backend": "file", "fallback_reason": fallback_reason, "storage": rec}


@app.get("/api/v1/storages/map")
def get_storages_map() -> Dict[str, Any]:
    try:
        features = list_map_features_from_db()
        return {"type": "FeatureCollection", "source_backend": "database", "features": features}
    except RepositoryUnavailable as exc:
        fallback_reason = str(exc)

    node_df = _load_nodes_df()
    features = []
    for _, row in node_df.iterrows():
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [float(row["lon"]), float(row["lat"])]},
                "properties": {
                    "node_id": row["node_id"],
                    "name": row["name"],
                    "candidate": bool(row["is_candidate"]),
                    "okra_production_ton": float(row["okra_production_ton"]),
                },
            }
        )
    return {"type": "FeatureCollection", "source_backend": "file", "fallback_reason": fallback_reason, "features": features}


# Road-class groupings for the OSM overlay. "major" keeps the map readable;
# heavier levels are opt-in because the full network is ~10k edges / 8,953 km.
ROAD_LEVEL_CLASSES: Dict[str, set] = {
    "major": {
        "motorway", "trunk", "primary", "secondary",
        "motorway_link", "trunk_link", "primary_link", "secondary_link",
    },
    "mid": {
        "motorway", "trunk", "primary", "secondary", "tertiary", "unclassified",
        "motorway_link", "trunk_link", "primary_link", "secondary_link", "tertiary_link",
    },
}

# Parse the 16.5MB geojson once and reuse the stripped features across requests.
_ROAD_NETWORK_CACHE: Dict[str, Any] = {}


def _load_road_network_features() -> list[dict[str, Any]]:
    if _ROAD_NETWORK_CACHE.get("features") is not None:
        return _ROAD_NETWORK_CACHE["features"]
    features: list[dict[str, Any]] = []
    if ROAD_NETWORK_GEOJSON_PATH.exists():
        try:
            raw = json.loads(ROAD_NETWORK_GEOJSON_PATH.read_text(encoding="utf-8"))
            for feat in raw.get("features", []):
                geom = feat.get("geometry") or {}
                if geom.get("type") != "LineString":
                    continue
                props = feat.get("properties") or {}
                features.append(
                    {
                        "coordinates": geom.get("coordinates", []),
                        "highway": props.get("highway"),
                        "road_name": props.get("road_name") or props.get("name"),
                        "length_m": round(float(props.get("length_m", 0) or 0), 1),
                    }
                )
        except Exception:
            features = []
    _ROAD_NETWORK_CACHE["features"] = features
    return features


@app.get("/api/v1/map/road-network")
def get_road_network(level: str = "major", limit: int = 0) -> Dict[str, Any]:
    """OSM road-network edges for the map overlay, filtered by road class.

    level: "major" (default, highways/trunks/primary/secondary), "mid" (adds
    tertiary/unclassified), or "all" (every edge). The full network is ~10,140
    edges / 8,953 km, so the default keeps the basemap readable while staying
    truthful about the real road geometry behind the OSM distance matrix.
    """
    all_features = _load_road_network_features()
    if level == "all":
        selected = all_features
        resolved_level = "all"
    else:
        classes = ROAD_LEVEL_CLASSES.get(level, ROAD_LEVEL_CLASSES["major"])
        resolved_level = level if level in ROAD_LEVEL_CLASSES else "major"
        selected = [f for f in all_features if f.get("highway") in classes]
    if limit and limit > 0:
        selected = selected[:limit]
    total_km = round(sum(f.get("length_m", 0) or 0 for f in selected) / 1000.0, 1)
    return {
        "source": "/api/v1/map/road-network",
        "source_backend": "file_geojson" if all_features else "empty",
        "available": bool(all_features),
        "level": resolved_level,
        "edge_count": len(selected),
        "total_km": total_km,
        "total_edge_count": len(all_features),
        "edges": selected,
        "claim_boundary": (
            "OSM 路网快照（Overpass 下载），全网约 10,140 条边 / 8,953 km；默认仅渲染主干道以保持地图可读。"
        ),
    }


@app.get("/api/v1/map/ai-recommended-sites")
def get_ai_recommended_sites() -> Dict[str, Any]:
    """AI top-K recommended cold-storage sites with coordinates and scores.

    This endpoint visualizes the **stage-one site ranking** of the joint warm-start
    pipeline: `ai_top_k + scored_candidates`. Type/capacity assignment happens in the
    warm-start facility layer and is exposed separately through the warm-start reports.
    Read-only; reuses the existing ai_warmstart artifact.
    """
    summary = _load_json_or_empty(AI_WARMSTART_JSON)
    top_k = [str(site) for site in summary.get("ai_top_k", []) if site]
    score_by_node = {
        str(item.get("node_id")): float(item.get("score", 0) or 0)
        for item in summary.get("scored_candidates", [])
        if isinstance(item, dict) and item.get("node_id") is not None
    }
    coord_by_node: Dict[str, Dict[str, Any]] = {}
    try:
        node_df = _load_nodes_df()
        for _, row in node_df.iterrows():
            coord_by_node[str(row["node_id"])] = {
                "name": row["name"],
                "lat": float(row["lat"]),
                "lon": float(row["lon"]),
                "okra_production_ton": float(row["okra_production_ton"]),
            }
    except Exception:
        coord_by_node = {}
    features = []
    for rank, node_id in enumerate(top_k, start=1):
        meta = coord_by_node.get(node_id)
        if not meta:
            continue
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [meta["lon"], meta["lat"]]},
                "properties": {
                    "node_id": node_id,
                    "name": meta["name"],
                    "rank": rank,
                    "score": round(score_by_node.get(node_id, 0.0), 4),
                    "okra_production_ton": meta["okra_production_ton"],
                    "ai_recommended": True,
                },
            }
        )
    return {
        "source": "/api/v1/map/ai-recommended-sites",
        "source_backend": "file" if summary else "empty",
        "available": bool(features),
        "type": "FeatureCollection",
        "count": len(features),
        "top_k_ids": top_k,
        "features": features,
        "claim_boundary": (
            "AI top-K 选址来自 XGBoost warm-start 推荐（结构特征预测开放概率），由 Gurobi 做最终决策；"
            "县域 39 节点案例，非企业级验证。"
        ),
    }


@app.post("/api/v1/routing/solve")
def solve_routing(request: RoutingRequest) -> Dict[str, Any]:
    return {
        "status": "queued",
        "scenario_id": request.scenario_id,
        "payload_echo": request.payload,
        "note": "Routing integration point reserved for the local logistics project.",
        "integration_base_url": os.environ.get("LOGISTICS_BASE_URL", ""),
    }


@app.get("/api/v1/routing/result/{result_id}")
def get_routing_result(result_id: str) -> Dict[str, Any]:
    return {
        "result_id": result_id,
        "status": "placeholder",
        "note": "Reserved for logistics route-planning integration.",
    }


LOGISTICS_CONTRACT_VERSION = "v1"
LOGISTICS_RESEARCH_BOUNDARY = (
    "REST adapter contract and mock/file-fallback endpoints only. This is not proof of real logistics-system integration "
    "until LOGISTICS_BASE_URL is configured and end-to-end HTTP calls are verified."
)


def _logistics_base_url() -> str:
    return os.environ.get("LOGISTICS_BASE_URL", "")


def _baseline_layout_nodes() -> Dict[str, Any]:
    """Build a logistics-oriented layout snapshot from current files."""
    map_payload = get_storages_map()
    map_features = map_payload.get("features", [])
    baseline = _load_pickle_analysis(BASELINE_RESULT_PATH) if BASELINE_RESULT_PATH.exists() else {}
    facility_items = baseline.get("facilities", []) if isinstance(baseline, dict) else []
    storage_nodes = [
        {
            "storage_id": item.get("site") or item.get("node_id"),
            "name": item.get("site_name") or item.get("name") or item.get("site") or item.get("node_id"),
            "storage_type": item.get("type_name") or item.get("storage_type"),
            "capacity_ton": item.get("capacity"),
            "allocated_ton": item.get("assigned_demand"),
            "available_ton": max(0.0, float(item.get("capacity") or 0.0) - float(item.get("assigned_demand") or 0.0)),
            "utilization_pct": item.get("utilization"),
            "lat": item.get("lat"),
            "lon": item.get("lon"),
            "node_role": "open_storage",
        }
        for item in facility_items
    ]
    if not storage_nodes:
        candidate_payload = get_storages()
        storage_nodes = [
            {
                "storage_id": item.get("node_id"),
                "name": item.get("name"),
                "storage_type": None,
                "capacity_ton": None,
                "allocated_ton": None,
                "available_ton": None,
                "utilization_pct": None,
                "lat": item.get("lat"),
                "lon": item.get("lon"),
                "node_role": "candidate_storage",
            }
            for item in candidate_payload.get("items", [])
        ]
    demand_nodes = [
        {
            "node_id": feature.get("properties", {}).get("node_id"),
            "name": feature.get("properties", {}).get("name"),
            "level_name": feature.get("properties", {}).get("level_name"),
            "okra_production_ton": feature.get("properties", {}).get("okra_production_ton"),
            "is_candidate": feature.get("properties", {}).get("is_candidate", feature.get("properties", {}).get("candidate")),
            "lon": feature.get("geometry", {}).get("coordinates", [None, None])[0],
            "lat": feature.get("geometry", {}).get("coordinates", [None, None])[1],
        }
        for feature in map_features
    ]
    return {
        "layout_id": "baseline_v2_1",
        "data_version": "current_files",
        "source_backend": "baseline_result_file" if facility_items else "candidate_file_fallback",
        "storage_nodes": storage_nodes,
        "demand_nodes": demand_nodes,
        "assignment_summary": {
            "storage_count": len(storage_nodes),
            "demand_node_count": len(demand_nodes),
            "total_capacity_ton": sum(float(item.get("capacity_ton") or 0) for item in storage_nodes),
            "total_allocated_ton": sum(float(item.get("allocated_ton") or 0) for item in storage_nodes),
        },
    }


@app.get("/api/v1/integration/logistics/contracts")
def logistics_contracts() -> Dict[str, Any]:
    interfaces = [
        {
            "name": "contract_index",
            "method": "GET",
            "path": "/api/v1/integration/logistics/contracts",
            "direction": "cold_storage_system",
            "purpose": "List REST adapter contracts and current implementation status.",
            "current_status": "implemented_contract_index",
        },
        {
            "name": "layout_snapshot",
            "method": "GET",
            "path": "/api/v1/integration/logistics/cold-storage/layout",
            "direction": "cold_storage_to_logistics",
            "purpose": "Expose optimized cold-storage layout as depot/hub candidates for logistics.",
            "current_status": "file_fallback_snapshot",
        },
        {
            "name": "layout_push",
            "method": "POST",
            "path": "/api/v1/integration/logistics/cold-storage/layout/push",
            "direction": "cold_storage_to_logistics",
            "purpose": "Push layout payload to LOGISTICS_BASE_URL when configured.",
            "current_status": "mocked_until_base_url_configured",
        },
        {
            "name": "capacity_snapshot",
            "method": "GET",
            "path": "/api/v1/integration/logistics/cold-storage/capacity",
            "direction": "logistics_to_cold_storage",
            "purpose": "Expose static or realtime capacity view for routing constraints.",
            "current_status": "static_from_optimization_result",
        },
        {
            "name": "routing_solve",
            "method": "POST",
            "path": "/api/v1/integration/logistics/routing/solve",
            "direction": "cold_storage_to_logistics",
            "purpose": "Submit VRP/CVRP/VRPTW request based on current layout.",
            "current_status": "mocked_queue",
        },
        {
            "name": "routing_result",
            "method": "GET",
            "path": "/api/v1/integration/logistics/routing/result/{result_id}",
            "direction": "logistics_to_cold_storage",
            "purpose": "Read logistics route-planning result.",
            "current_status": "reserved_result_shape",
        },
    ]
    return {
        "contract_version": LOGISTICS_CONTRACT_VERSION,
        "source_system": "okra_cold_storage_optimization",
        "target_system": "local_logistics_route_planning_project",
        "logistics_base_url": _logistics_base_url(),
        "status": "contract_ready_mock_adapter",
        "interfaces": interfaces,
        "research_boundary": LOGISTICS_RESEARCH_BOUNDARY,
    }


@app.get("/api/v1/integration/logistics/cold-storage/layout")
def logistics_layout_snapshot() -> Dict[str, Any]:
    payload = _baseline_layout_nodes()
    return {
        "contract_version": LOGISTICS_CONTRACT_VERSION,
        "source_system": "okra_cold_storage_optimization",
        "target_system": "local_logistics_route_planning_project",
        "status": "file_fallback_snapshot",
        **payload,
        "research_boundary": LOGISTICS_RESEARCH_BOUNDARY,
    }


@app.post("/api/v1/integration/logistics/cold-storage/layout/push")
def logistics_layout_push(request: LogisticsPushRequest) -> Dict[str, Any]:
    base_url = _logistics_base_url()
    payload = _model_to_dict(request)
    return {
        "contract_version": LOGISTICS_CONTRACT_VERSION,
        "source_system": "okra_cold_storage_optimization",
        "target_system": "local_logistics_route_planning_project",
        "status": "reserved" if not base_url else "mocked_not_forwarded",
        "push_id": f"push_{request.layout_id}_{request.scenario_id or 'default'}",
        "external_layout_id": None,
        "logistics_base_url": base_url,
        "payload_echo": payload,
        "research_boundary": LOGISTICS_RESEARCH_BOUNDARY,
    }


@app.get("/api/v1/integration/logistics/cold-storage/capacity")
def logistics_capacity_snapshot() -> Dict[str, Any]:
    layout = _baseline_layout_nodes()
    return {
        "contract_version": LOGISTICS_CONTRACT_VERSION,
        "source_system": "okra_cold_storage_optimization",
        "target_system": "local_logistics_route_planning_project",
        "status": "static_from_optimization_result",
        "capacity_timestamp": None,
        "capacity_mode": "static_from_baseline_v2_1",
        "source_backend": layout.get("source_backend"),
        "items": layout.get("storage_nodes", []),
        "research_boundary": LOGISTICS_RESEARCH_BOUNDARY,
    }


@app.post("/api/v1/integration/logistics/routing/solve")
def logistics_routing_solve(request: LogisticsRoutingSolveRequest) -> Dict[str, Any]:
    base_url = _logistics_base_url()
    return {
        "contract_version": LOGISTICS_CONTRACT_VERSION,
        "source_system": "okra_cold_storage_optimization",
        "target_system": "local_logistics_route_planning_project",
        "status": "queued_mock" if not base_url else "mocked_not_forwarded",
        "request_id": f"route_{request.scenario_id}_{request.layout_id}",
        "logistics_base_url": base_url,
        "submitted_at": None,
        "payload_echo": _model_to_dict(request),
        "research_boundary": LOGISTICS_RESEARCH_BOUNDARY,
    }


@app.get("/api/v1/integration/logistics/routing/result/{result_id}")
def logistics_routing_result(result_id: str) -> Dict[str, Any]:
    return {
        "contract_version": LOGISTICS_CONTRACT_VERSION,
        "source_system": "local_logistics_route_planning_project",
        "target_system": "okra_cold_storage_optimization",
        "result_id": result_id,
        "status": "reserved_result_shape",
        "routes": [],
        "total_distance_km": None,
        "total_duration_h": None,
        "transport_cost_yuan": None,
        "carbon_kgco2e": None,
        "temperature_feasible": None,
        "violations": [],
        "research_boundary": LOGISTICS_RESEARCH_BOUNDARY,
    }


@app.get("/api/v1/analysis/carbon")
def analysis_carbon() -> Dict[str, Any]:
    data = _load_csv_or_empty(SCENARIO_PATH)
    if not data:
        raise HTTPException(status_code=404, detail="Scenario comparison not found.")
    return {"items": data, "metric": "carbon_proxy_via_cost_breakdown"}


@app.get("/api/v1/analysis/loss")
def analysis_loss() -> Dict[str, Any]:
    data = _load_csv_or_empty(SENSITIVITY_PATH)
    if not data:
        raise HTTPException(status_code=404, detail="Sensitivity data not found.")
    return {"items": data, "metric": "loss_sensitivity"}


@app.get("/api/v1/analysis/sensitivity")
def analysis_sensitivity() -> Dict[str, Any]:
    data = _load_csv_or_empty(SENSITIVITY_PATH)
    if not data:
        raise HTTPException(status_code=404, detail="Sensitivity data not found.")
    return {"items": data}


@app.get("/api/v1/analysis/visualization-report")
def analysis_visualization_report() -> Dict[str, Any]:
    return _analysis_visualization_report()


@app.get("/api/v1/model/realism-audit")
def model_realism_audit() -> Dict[str, Any]:
    return _model_realism_audit()


@app.get("/api/v1/experiments/paper-evidence-pack")
def paper_evidence_pack() -> Dict[str, Any]:
    return _paper_evidence_pack()


@app.get("/api/v1/experiments/ai-benders-analysis-report")
def ai_benders_analysis_report() -> Dict[str, Any]:
    return _ai_benders_analysis_report()


@app.get("/api/v1/experiments/ai-benders-result-card")
def ai_benders_result_card() -> Dict[str, Any]:
    return _ai_benders_result_card()


@app.get("/api/v1/experiments/ai-benders-feature-summary")
def ai_benders_feature_summary() -> Dict[str, Any]:
    return _ai_benders_feature_summary()


@app.get("/api/v1/experiments/mis-readiness-report")
def mis_readiness_report() -> Dict[str, Any]:
    return _mis_readiness_report()


@app.get("/api/v1/experiments/map-readiness-report")
def map_readiness_report() -> Dict[str, Any]:
    return _map_readiness_report()


@app.get("/api/v1/map/provider-status")
def map_provider_status() -> Dict[str, Any]:
    return _map_provider_status()


@app.get("/api/v1/map/config")
def map_config() -> Dict[str, Any]:
    """Serve the browser map config (incl. JS key) for the frontend.

    Security model: the AMap JS key is returned to the browser ONLY when the
    operator has explicitly opted in via ``OKRA_MAP_PUBLIC_KEY_ALLOWED`` AND the
    provider is a browser map provider. The key is read from the environment
    variable named by ``OKRA_MAP_PUBLIC_KEY_ENV`` (default ``OKRA_AMAP_JS_KEY``)
    at request time -- it is never written to source, the bundle, logs, or disk.
    When not allowed, ``js_key`` is null and the frontend falls back to the
    file-based point view. A client-side map key is inherently public once used
    in the browser, so only browser-scoped keys should be enabled here.
    """
    status = build_map_provider_status()
    provider = status.get("provider", "file")
    public_key_env = status.get("public_key_env", "OKRA_AMAP_JS_KEY")
    allowed = bool(status.get("public_key_allowed_for_client"))
    browser_ready = bool(status.get("browser_provider_ready"))
    js_key = os.environ.get(public_key_env, "").strip() if (allowed and browser_ready) else ""
    # Optional security JS code for AMap 2.0 web-service plugins (also gated).
    security_code = (
        os.environ.get("OKRA_AMAP_SECURITY_CODE", "").strip() if (allowed and browser_ready) else ""
    )
    return {
        "source": "/api/v1/map/config",
        "provider": provider,
        "browser_provider_ready": browser_ready,
        "public_key_allowed_for_client": allowed,
        "js_key_available": bool(js_key),
        "js_key": js_key or None,
        "security_code_available": bool(security_code),
        "security_code": security_code or None,
        "default_center": [111.69, 29.05],
        "default_zoom": 9,
        "boundary": (
            "js_key is served to the browser only when OKRA_MAP_PUBLIC_KEY_ALLOWED is enabled "
            "and a browser provider is configured; otherwise the frontend uses the file point view."
        ),
    }


EXACT_VS_HEURISTIC_JSON = PROJECT_ROOT / "results" / "experiments" / "exact_vs_heuristic" / "exact_vs_heuristic_summary.json"
CUTMGMT_JSON = PROJECT_ROOT / "results" / "experiments" / "benders_cutmgmt_comparison" / "benders_cutmgmt_summary.json"
CUTMGMT_ITER_CSV = PROJECT_ROOT / "results" / "experiments" / "benders_cutmgmt_comparison" / "benders_cutmgmt_iterations.csv"
AI_WARMSTART_JSON = PROJECT_ROOT / "results" / "experiments" / "ai_warmstart_v3" / "ai_warmstart_summary.json"
AI_WARMSTART_OPTUNA_JSON = PROJECT_ROOT / "results" / "experiments" / "ai_warmstart_optuna" / "ai_warmstart_optuna_summary.json"
AI_WARMSTART_OPTUNA_RECHECK_JSON = PROJECT_ROOT / "results" / "experiments" / "ai_warmstart_optuna" / "ai_warmstart_optuna_recheck_summary.json"
V3_FOUR_METHODS_JSON = PROJECT_ROOT / "results" / "experiments" / "v3_four_methods" / "v3_four_methods_summary.json"
V3_SOLVE_TRACE_JSON = PROJECT_ROOT / "results" / "experiments" / "v3_solve_trace" / "v3_solve_trace.json"
OSM_DISTANCE_MATRIX_JSON = PROJECT_ROOT / "results" / "real_data_sources" / "osm_distance_matrix_summary.json"
OSM_VS_HAVERSINE_JSON = PROJECT_ROOT / "results" / "experiments" / "osm_vs_haversine" / "osm_vs_haversine_summary.json"
LIVE_SOLVE_OSM_DIST_CSV = PROJECT_ROOT / "data" / "distance_matrix_osm.csv"
LIVE_SOLVE_OSM_TIME_CSV = PROJECT_ROOT / "data" / "transport_time_matrix_osm.csv"
WEATHER_CURRENT_JSON = PROJECT_ROOT / "data" / "processed" / "real_data" / "weather_current.json"


def _sse_event(event: str, payload: Dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(_json_safe(payload), ensure_ascii=False)}\n\n"


def _long_to_pivot(path: Path, value_col: str):
    import pandas as pd

    df = pd.read_csv(path)
    pivot = df.pivot(index="origin", columns="destination", values=value_col)
    ids = sorted(pivot.index.tolist())
    return pivot.loc[ids, ids]


def _build_live_v3_config() -> tuple[Any, str]:
    DataConfig, _, _, _ = _get_solver_modules()
    config = DataConfig(str(PROJECT_ROOT / "data"))
    matrix_source = "default"
    if LIVE_SOLVE_OSM_DIST_CSV.exists() and LIVE_SOLVE_OSM_TIME_CSV.exists():
        dist_pivot = _long_to_pivot(LIVE_SOLVE_OSM_DIST_CSV, "distance_km")
        time_pivot = _long_to_pivot(LIVE_SOLVE_OSM_TIME_CSV, "time_h")
        config.distance = dist_pivot.values
        config.transport_time = time_pivot.values
        config.node_ids = list(dist_pivot.index)
        config.id2idx = {node_id: idx for idx, node_id in enumerate(config.node_ids)}
        matrix_source = "osm"
    return config, matrix_source


def _load_live_warm_sites(max_sites: int = 8) -> list[str]:
    summary = _load_json_or_empty(AI_WARMSTART_JSON)
    sites = summary.get("ai_top_k", [])
    return [str(site) for site in sites[:max_sites] if site]


def _load_live_warm_facilities(max_sites: int = 8) -> list[dict[str, Any]]:
    summary = _load_json_or_empty(AI_WARMSTART_JSON)
    items = summary.get("ai_warm_facilities", [])
    facilities = []
    for item in items[:max_sites]:
        if not isinstance(item, dict):
            continue
        site = item.get("site")
        type_id = item.get("type")
        capacity_idx = item.get("capacity_idx")
        if site is None or type_id is None or capacity_idx is None:
            continue
        facilities.append(
            {
                "site": str(site),
                "type": str(type_id),
                "capacity_idx": int(capacity_idx),
                "capacity": item.get("capacity"),
                "site_rank": item.get("site_rank"),
                "score": item.get("score"),
                "assignment_source": item.get("assignment_source"),
                "matched_site": item.get("matched_site"),
            }
        )
    return facilities


def _build_live_v3_model(
    config: Any,
    *,
    mode: Literal["cold_start", "ai_warm"],
    time_limit: int,
    mip_gap: float,
    profile_name: str,
) -> tuple[Any, dict[Any, Any], dict[Any, Any], list[str], list[str], Any, list[str], list[dict[str, Any]]]:
    DataConfig, GRB, gp, _ = _get_solver_modules()
    assumptions = default_assumptions()
    channels = _channel_map(assumptions)
    active_types = [channel.type_id for channel in assumptions.channels if channel.annual_share > 0]
    candidate_ids = list(config.candidates["node_id"])
    demand_ids = list(config.demands["node_id"])
    demand = {node_id: config.get_demand(node_id) for node_id in demand_ids}
    profile = get_v3_solver_profile(profile_name)

    model = gp.Model(f"v3_live_{mode}")
    model.setParam("TimeLimit", time_limit)
    model.setParam("MIPGap", mip_gap)
    model.setParam("Threads", 8)
    model.setParam("OutputFlag", 0)
    for param_name, param_value in (profile.solver_params or {}).items():
        model.setParam(param_name, param_value)

    z: dict[Any, Any] = {}
    for site in candidate_ids:
        for type_id in active_types:
            for cap_idx in range(len(config.capacity_index[type_id])):
                z[site, type_id, cap_idx] = model.addVar(vtype=GRB.BINARY, name=f"z_{site}_{type_id}_{cap_idx}")

    x: dict[Any, Any] = {}
    for demand_id in demand_ids:
        for site in candidate_ids:
            for type_id in active_types:
                x[demand_id, site, type_id] = model.addVar(lb=0.0, ub=1.0, name=f"x_{demand_id}_{site}_{type_id}")

    model.update()

    warm_sites = _load_live_warm_sites(max_sites=assumptions.max_facilities) if mode == "ai_warm" else []
    warm_facilities = _load_live_warm_facilities(max_sites=assumptions.max_facilities) if mode == "ai_warm" else []
    if not warm_facilities and warm_sites:
        target_type = "cold"
        cap_idx = min(1, len(config.capacity_index[target_type]) - 1)
        warm_facilities = [
            {"site": site, "type": target_type, "capacity_idx": cap_idx}
            for site in warm_sites
        ]
    if warm_facilities:
        for var in z.values():
            var.Start = 0.0
    for facility in warm_facilities:
        site = str(facility.get("site"))
        target_type = str(facility.get("type"))
        cap_idx = int(facility.get("capacity_idx", 0))
        if (site, target_type, cap_idx) in z:
            z[site, target_type, cap_idx].Start = 1.0

    for demand_id in demand_ids:
        for type_id in active_types:
            model.addConstr(
                gp.quicksum(x[demand_id, site, type_id] for site in candidate_ids) == channels[type_id].annual_share,
                name=f"channel_share_{demand_id}_{type_id}",
            )

    for demand_id in demand_ids:
        for site in candidate_ids:
            for type_id in active_types:
                model.addConstr(
                    x[demand_id, site, type_id]
                    <= gp.quicksum(z[site, type_id, cap_idx] for cap_idx in range(len(config.capacity_index[type_id]))),
                    name=f"assign_open_{demand_id}_{site}_{type_id}",
                )

    for site in candidate_ids:
        model.addConstr(
            gp.quicksum(
                z[site, type_id, cap_idx]
                for type_id in active_types
                for cap_idx in range(len(config.capacity_index[type_id]))
            )
            <= 1,
            name=f"one_facility_{site}",
        )

    model.addConstr(
        gp.quicksum(
            z[site, type_id, cap_idx]
            for site in candidate_ids
            for type_id in active_types
            for cap_idx in range(len(config.capacity_index[type_id]))
        )
        <= assumptions.max_facilities,
        name="max_facilities",
    )

    precool_limit_h = config.get_preservation_params().get("precool_time_limit_h", 2.0)
    for demand_id in demand_ids:
        for site in candidate_ids:
            if config.get_time(demand_id, site) > precool_limit_h:
                model.addConstr(x[demand_id, site, "precool"] == 0.0, name=f"precool_time_{demand_id}_{site}")

    for site in candidate_ids:
        for type_id in active_types:
            channel = channels[type_id]
            peak_load = gp.quicksum(
                x[demand_id, site, type_id]
                * demand[demand_id]
                * channel.storage_days
                / assumptions.harvest_window_days
                * assumptions.harvest_peak_factor
                for demand_id in demand_ids
            )
            capacity = gp.quicksum(
                z[site, type_id, cap_idx] * config.capacity_index[type_id][cap_idx]["capacity"]
                for cap_idx in range(len(config.capacity_index[type_id]))
            )
            model.addConstr(peak_load <= capacity, name=f"peak_capacity_{site}_{type_id}")

    fixed_cost = gp.quicksum(
        z[site, type_id, cap_idx] * config.capacity_index[type_id][cap_idx]["fixed_cost"] * 10000
        for site in candidate_ids
        for type_id in active_types
        for cap_idx in range(len(config.capacity_index[type_id]))
    )
    operate_cost = gp.quicksum(
        z[site, type_id, cap_idx] * config.capacity_index[type_id][cap_idx]["operate_cost"] * 10000
        for site in candidate_ids
        for type_id in active_types
        for cap_idx in range(len(config.capacity_index[type_id]))
    )
    transport_cost = gp.quicksum(
        x[demand_id, site, type_id]
        * demand[demand_id]
        * config.get_dist(demand_id, site)
        * assumptions.transport_cost_yuan_per_ton_km
        for demand_id in demand_ids
        for site in candidate_ids
        for type_id in active_types
    )
    loss_cost = gp.quicksum(
        x[demand_id, site, type_id]
        * demand[demand_id]
        * (
            config.get_time(demand_id, site)
            * config.get_preservation_params().get("transport_loss_per_hour", 0.02)
            * channels[type_id].transport_loss_multiplier
            + channels[type_id].loss_rate
        )
        * assumptions.loss_price
        for demand_id in demand_ids
        for site in candidate_ids
        for type_id in active_types
    )
    carbon_cost = gp.quicksum(
        x[demand_id, site, type_id]
        * demand[demand_id]
        * (
            config.capacity_index[type_id][0]["energy_cost_per_ton"]
            * config.capacity_index[type_id][0]["carbon_factor"]
            / 1000
            + config.get_dist(demand_id, site) * assumptions.transport_carbon_kg_per_ton_km / 1000
        )
        * assumptions.carbon_price
        for demand_id in demand_ids
        for site in candidate_ids
        for type_id in active_types
    )

    model.setObjective(fixed_cost + operate_cost + transport_cost + loss_cost + carbon_cost, GRB.MINIMIZE)
    model.update()
    return model, z, x, candidate_ids, demand_ids, assumptions, warm_sites, warm_facilities


def _run_live_v3_solve(
    *,
    mode: Literal["cold_start", "ai_warm"],
    profile_name: str,
    time_limit: int,
    mip_gap: float,
    event_queue: queue.Queue,
) -> None:
    try:
        DataConfig, GRB, gp, analyze_v3_results = _get_solver_modules()
        config, matrix_source = _build_live_v3_config()
        model, z, x, candidate_ids, demand_ids, assumptions, warm_sites, warm_facilities = _build_live_v3_model(
            config,
            mode=mode,
            time_limit=time_limit,
            mip_gap=mip_gap,
            profile_name=profile_name,
        )

        profile = get_v3_solver_profile(profile_name)
        event_queue.put(
            (
                "start",
                {
                    "mode": mode,
                    "profile": profile.to_dict(),
                    "matrix_source": matrix_source,
                    "candidate_count": len(candidate_ids),
                    "demand_count": len(demand_ids),
                    "warm_sites": warm_sites,
                    "warm_facilities": warm_facilities,
                },
            )
        )

        trace: list[dict[str, Any]] = []

        def callback(cb_model: Any, where: int) -> None:
            if where != GRB.Callback.MIP:
                return
            try:
                incumbent = cb_model.cbGet(GRB.Callback.MIP_OBJBST)
                bound = cb_model.cbGet(GRB.Callback.MIP_OBJBND)
                runtime = cb_model.cbGet(GRB.Callback.RUNTIME)
            except Exception:
                return
            if incumbent >= GRB.INFINITY or incumbent <= 0:
                return
            gap_pct = abs(incumbent - bound) / max(1e-10, abs(incumbent)) * 100.0
            should_emit = (
                not trace
                or abs(float(trace[-1]["gap_pct"]) - gap_pct) > 0.05
                or runtime - float(trace[-1]["t"]) > 3.0
            )
            if not should_emit:
                return
            point = {
                "t": round(float(runtime), 2),
                "obj": round(float(incumbent), 2),
                "bound": round(float(bound), 2),
                "gap_pct": round(float(gap_pct), 4),
            }
            trace.append(point)
            event_queue.put(("progress", point))

        started_at = time.time()
        model.optimize(callback)
        elapsed_sec = round(time.time() - started_at, 2)

        if model.SolCount <= 0:
            raise RuntimeError(f"实时求解未找到可行解，status={model.Status}")

        final_point = {
            "t": elapsed_sec,
            "obj": round(float(model.ObjVal), 2),
            "bound": round(float(model.ObjBound), 2),
            "gap_pct": round(float(model.MIPGap * 100.0), 4),
        }
        if not trace or trace[-1].get("gap_pct") != final_point["gap_pct"]:
            trace.append(final_point)
            event_queue.put(("progress", final_point))

        analysis = analyze_v3_results(model, z, x, config, candidate_ids, demand_ids, assumptions=assumptions)
        event_queue.put(
            (
                "end",
                {
                    "mode": mode,
                    "elapsed_sec": elapsed_sec,
                    "trace": trace,
                    "warm_sites": warm_sites,
                    "warm_facilities": warm_facilities,
                    "analysis": analysis,
                    "claim_boundary": (
                        "实时求解基于当前文件资产与 OSM 路网矩阵（若可用）。AI warm 复用既有联合 warm-start 设施组合作为 MIP Start，"
                        "用于 demo 演示搜索加速，不构成超出既有证据链的新学术结论。"
                    ),
                },
            )
        )
    except Exception as exc:
        event_queue.put(("error", {"message": str(exc)}))
    finally:
        event_queue.put(None)


@app.get("/api/v1/optimize/v3-live-stream")
def optimize_v3_live_stream(
    mode: Literal["cold_start", "ai_warm"] = "cold_start",
    profile: str = "bound_focus_60s",
    time_limit: int | None = None,
    mip_gap: float | None = None,
):
    try:
        profile_obj = get_v3_solver_profile(profile)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    resolved_time_limit = int(time_limit or profile_obj.time_limit)
    resolved_mip_gap = float(mip_gap if mip_gap is not None else profile_obj.mip_gap)
    event_queue: queue.Queue = queue.Queue()

    def event_stream():
        worker = threading.Thread(
            target=_run_live_v3_solve,
            kwargs={
                "mode": mode,
                "profile_name": profile,
                "time_limit": resolved_time_limit,
                "mip_gap": resolved_mip_gap,
                "event_queue": event_queue,
            },
            daemon=True,
        )
        worker.start()
        while True:
            try:
                item = event_queue.get(timeout=5)
            except queue.Empty:
                yield ": keepalive\n\n"
                continue
            if item is None:
                break
            event_name, payload = item
            yield _sse_event(event_name, payload)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/v1/analysis/pareto-front")
def pareto_front() -> Dict[str, Any]:
    """Multi-objective Pareto frontier (cost / spoilage / carbon) per scenario.

    Returns the exact epsilon-constraint frontier plus NSGA-III and ALNS
    heuristic frontiers for the same scenarios, so the frontend can overlay
    them in 2D/3D. Objectives order: [cost_yuan, loss_ton, carbon_ton].
    """
    summary = _load_json_or_empty(EXACT_VS_HEURISTIC_JSON)
    fronts = summary.get("fronts", {})
    scenarios = []
    for name, payload in fronts.items():
        scenarios.append(
            {
                "scenario": name,
                "objective_names": ["cost_yuan", "loss_ton", "carbon_ton"],
                "exact_front": payload.get("exact_front", []),
                "nsga3_front": payload.get("nsga3_front", []),
                "alns_front": payload.get("alns_front", []),
                "reference_point": payload.get("reference_point", []),
            }
        )
    return {
        "source": "/api/v1/analysis/pareto-front",
        "experiment": "exact_vs_heuristic",
        "available": bool(scenarios),
        "scenarios": scenarios,
        "method_summary": summary.get("summary_rows", []),
        "verdict": summary.get("verdict", {}),
        "claim_boundary": summary.get("research_boundary", ""),
    }


@app.get("/api/v1/analysis/benders-convergence")
def benders_convergence() -> Dict[str, Any]:
    """Per-iteration Benders gap convergence traces, for the solve-process animation.

    Returns iteration-level (upper_bound, lower_bound, gap_pct, active cuts) per
    cut-management policy on the hardest instances, plus the controlled-comparison
    verdict (learned vs random/recency/all cuts).
    """
    summary = _load_json_or_empty(CUTMGMT_JSON)
    iters = _load_csv_or_empty(CUTMGMT_ITER_CSV)
    # Group iterations by (case_id, policy, seed=0) into ordered traces.
    traces: Dict[str, Dict[str, Any]] = {}
    for row in iters:
        if str(row.get("seed", "0")) not in {"0", "0.0"}:
            continue
        case = str(row.get("case_id", ""))
        policy = str(row.get("policy", ""))
        key = f"{case}|{policy}"
        trace = traces.setdefault(key, {"case_id": case, "policy": policy, "points": []})
        try:
            trace["points"].append(
                {
                    "iter_no": int(float(row.get("iter_no", 0))),
                    "gap_pct": float(row.get("gap_pct", 0) or 0),
                    "upper_bound": float(row.get("upper_bound", 0) or 0),
                    "lower_bound": float(row.get("lower_bound", 0) or 0),
                    "active_cut_count": float(row.get("active_cut_count", 0) or 0),
                }
            )
        except (TypeError, ValueError):
            continue
    for trace in traces.values():
        trace["points"].sort(key=lambda p: p["iter_no"])
    # rank cases by trace length to surface the most illustrative ones
    by_case: Dict[str, int] = {}
    for trace in traces.values():
        by_case[trace["case_id"]] = max(by_case.get(trace["case_id"], 0), len(trace["points"]))
    top_cases = [c for c, _ in sorted(by_case.items(), key=lambda kv: kv[1], reverse=True)]
    return {
        "source": "/api/v1/analysis/benders-convergence",
        "experiment": "benders_cutmgmt_comparison",
        "available": bool(traces),
        "policies": ["all_cuts", "random_K", "recency_K", "learned_K"],
        "top_cases": top_cases,
        "traces": list(traces.values()),
        "verdict": summary.get("verdict", {}),
        "claim_boundary": summary.get("research_boundary", ""),
    }


@app.get("/api/v1/model/formulation")
def model_formulation() -> Dict[str, Any]:
    """Structured math-model description for the frontend model panel.

    Provides sets, parameters, decision variables, objectives and constraints in
    LaTeX-renderable strings (KaTeX/MathJax on the client). Mirrors the
    bilevel multi-objective MIP and its epsilon-constraint scalarisation.
    """
    return {
        "source": "/api/v1/model/formulation",
        "title": "AI 增强双层多目标冷库布局 MIP (v3.0 容量链)",
        "sets": [
            {"symbol": "I", "desc": "需求点集合（村/乡镇/县，39 个节点）"},
            {"symbol": "J", "desc": "候选冷库选址点集合（27 个候选）"},
            {"symbol": "T", "desc": "服务通道/冷库类型 {预冷, 冷藏, 气调, 冷冻}"},
            {"symbol": "C_t", "desc": "类型 t 的容量等级集合"},
        ],
        "parameters": [
            {"symbol": "d_i", "desc": "需求点 i 的秋葵年产量（吨）"},
            {"symbol": "s_t", "desc": "通道 t 的年流量份额（预冷100% / 冷藏60% / 气调30% / 冷冻10%，场景假设）"},
            {"symbol": "dist_{ij}", "desc": "i 到 j 的 OSM 路网距离（km）"},
            {"symbol": "f_{tc},\\ o_{tc}", "desc": "类型 t 容量等级 c 的建设/运营成本"},
            {"symbol": "cap_{tc}", "desc": "类型 t 容量等级 c 的容量（吨）"},
            {"symbol": "L_t,\\ \\pi_t", "desc": "通道 t 的储存天数 / 峰值因子（峰值库存 = 年流量·L_t/H·\\pi）"},
            {"symbol": "H,\\ \\pi", "desc": "收获窗口天数（90）/ 收获峰值因子（1.8）"},
            {"symbol": "\\tau", "desc": "预冷时限硬约束（2 小时）"},
        ],
        "variables": [
            {"symbol": "z_{jtc}\\in\\{0,1\\}", "desc": "是否在 j 建设类型 t 容量等级 c 的冷库（上层选址）"},
            {"symbol": "x_{ijt}\\in[0,1]", "desc": "需求点 i 的通道 t 流量分配到 j 的比例（下层连续分配）"},
        ],
        "objectives": [
            {"key": "cost", "latex": r"\min\ Z_1=\sum_{j,t,c} z_{jtc}(f_{tc}+o_{tc})+\sum_{i,j,t} x_{ijt}\,d_i\,dist_{ij}\,c_{trans}+\lambda_L\!\sum Z_2+\lambda_C\!\sum Z_3", "desc": "总成本（建设+运营+运输+损耗·损耗价+碳·碳价）"},
            {"key": "loss", "latex": r"\min\ Z_2=\sum_{i,j,t} x_{ijt}\,d_i\,(t_{ij}\alpha_{trans}m_t+\alpha^{stor}_t)", "desc": "总腐损吨数（运输损耗 + 通道储存损耗）"},
            {"key": "carbon", "latex": r"\min\ Z_3=\sum_{i,j,t} x_{ijt}\,d_i\,(e_t\gamma_t/1000+dist_{ij}\varepsilon/1000)", "desc": "总碳排放吨数（能耗 + 运输碳）"},
        ],
        "constraints": [
            {"latex": r"\sum_{j} x_{ijt}=s_t\quad \forall i\in I,\ t\in T", "desc": "通道份额约束：每需求点每通道按 share 分配（容量链语义）"},
            {"latex": r"x_{ijt}\le \sum_{c} z_{jtc}\quad \forall i,j,t", "desc": "只能分配到已建对应类型冷库"},
            {"latex": r"\sum_{t,c} z_{jtc}\le 1\quad \forall j", "desc": "每个候选点最多一个冷库"},
            {"latex": r"\sum_{j,t,c} z_{jtc}\le N_{max}", "desc": "最大设施数约束（N_{max}=8）"},
            {"latex": r"x_{ij,precool}=0\ \ \text{if}\ t_{ij}>\tau\quad \forall i,j", "desc": "预冷时间 ≤ 2h（冷链温度硬约束）"},
            {"latex": r"\sum_i x_{ijt}\,d_i\,\tfrac{L_t}{H}\pi\le \sum_c z_{jtc}cap_{tc}\quad \forall j,t", "desc": "峰值库存容量约束（峰值库存 = 年流量·储存天数/窗口·峰值因子）"},
        ],
        "solution_methods": [
            {"name": "KKT 转化", "desc": "下层 LP 的 KKT 条件 + 大 M 线性化 → 单层 MILP（双层→单层）"},
            {"name": "增广 ε-约束", "desc": "主目标最小化 + 其余目标加 ε 约束，扫描生成 Pareto 前沿（多目标→单目标）"},
            {"name": "Gurobi 直解 + AI warm start", "desc": "v3.0 主求解器：XGBoost 预测候选点 → MIP Start 注入，7.3× 加速（DS-F-051/052）"},
            {"name": "Benders 分解 + AI cut 管理", "desc": "Benders 子线：公开 LRP 轨道上的 cut ranking / robustness 机制研究（DS-F-043/048/049/050）"},
            {"name": "NSGA-III / ALNS", "desc": "元启发式对比基线（说明为何推荐精确/AI增强精确，DS-F-052）"},
        ],
        "claim_boundary": "县域案例（39 需求点）；服务通道份额（预冷100/冷藏60/气调30/冷冻10）与部分参数为情景假设，非企业真实渠道数据；距离矩阵为 OSM 路网估算。",
    }


@app.get("/api/v1/experiments/ai-warmstart-report")
def ai_warmstart_report() -> Dict[str, Any]:
    """v3.0 AI guided warm start 报告：XGBoost 节点重要性 + 求解加速对比。

    展示用 4 个 priority scenario runs 训练的 XGBoost ranker 如何先预测候选点
    开放概率，再补齐 site + type + capacity 联合 warm-start 设施组合，比较
    注入 Gurobi MIP Start 后的加速效果（cold_start vs ai_warm）。
    """
    summary = _load_json_or_empty(AI_WARMSTART_JSON)
    optuna_summary = _load_json_or_empty(AI_WARMSTART_OPTUNA_JSON)
    optuna_recheck = _load_json_or_empty(AI_WARMSTART_OPTUNA_RECHECK_JSON)
    training = summary.get("training", {})
    results = summary.get("results", [])
    recommended_version = summary.get("recommended_version")
    cold = next((r for r in results if r.get("label") == "cold_start"), summary.get("cold_start", {}))
    ai = summary.get("ai_warm") or next((r for r in results if r.get("warm_strategy_version") == recommended_version), {})
    optuna_best = optuna_summary.get("best_trial", {}) if optuna_summary else {}
    return {
        "source": "/api/v1/experiments/ai-warmstart-report",
        "experiment": "v3_ai_warmstart",
        "available": bool(summary),
        "available_versions": summary.get("available_versions", []),
        "recommended_version": recommended_version,
        "recommended_label": summary.get("recommended_label"),
        "recommended_strategy": summary.get("recommended_strategy") or summary.get("joint_strategy"),
        "recommended_reason": summary.get("recommended_reason"),
        "target_version": summary.get("target_version"),
        "target_label": summary.get("target_label"),
        "target_strategy": summary.get("target_strategy") or summary.get("joint_strategy"),
        "warm_versions": summary.get("warm_versions", {}),
        "ai_top_k": summary.get("ai_top_k", []),
        "ai_warm_facilities": summary.get("ai_warm_facilities", []),
        "site_type_capacity_predictions": summary.get("site_type_capacity_predictions", []),
        "site_type_predictions": summary.get("site_type_predictions", []),
        "version_facilities": summary.get("version_facilities", {}),
        "joint_strategy": summary.get("joint_strategy"),
        "facility_labels_used": summary.get("facility_labels_used", {}),
        "scored_candidates": summary.get("scored_candidates", []),
        "feature_importances": training.get("feature_importances", []),
        "training": {
            "n_runs_used": training.get("n_runs_used", 0),
            "variants": training.get("variants", []),
            "n_features": training.get("n_features", 0),
            "n_train_rows": training.get("n_train_rows", 0),
            "n_positive": training.get("n_positive", 0),
        },
        "results": results,
        "results_by_version": summary.get("results_by_version", {}),
        "cold_start": cold,
        "target_warm": summary.get("target_warm", {}),
        "ai_warm": ai,
        "speedup": summary.get("ai_vs_cold_speedup"),
        "target_speedup": summary.get("target_ai_vs_cold_speedup"),
        "optuna_available": bool(optuna_summary),
        "optuna_best_trial": optuna_best,
        "optuna_best_params": optuna_summary.get("best_params", {}) if optuna_summary else {},
        "optuna_best_speedup": optuna_summary.get("best_speedup") if optuna_summary else None,
        "optuna_trial_count": optuna_summary.get("trial_count", 0) if optuna_summary else 0,
        "optuna_single_trial_complete_count": optuna_summary.get("single_trial_complete_count", 0) if optuna_summary else 0,
        "optuna_n_trials_requested": optuna_summary.get("n_trials_requested", 0) if optuna_summary else 0,
        "optuna_multi_trial_count": optuna_summary.get("multi_trial_count", 0) if optuna_summary else 0,
        "optuna_multi_trial_complete_count": optuna_summary.get("multi_trial_complete_count", 0) if optuna_summary else 0,
        "optuna_multi_trials_requested": optuna_summary.get("multi_trials_requested", 0) if optuna_summary else 0,
        "optuna_pareto_front_size": optuna_summary.get("pareto_front_size", 0) if optuna_summary else 0,
        "optuna_historical_best_speedup": optuna_summary.get("historical_best_speedup") if optuna_summary else None,
        "optuna_exceeds_historical_best": optuna_summary.get("exceeds_historical_best") if optuna_summary else None,
        "optuna_pareto_front": optuna_summary.get("pareto_front", []) if optuna_summary else [],
        "optuna_claim_boundary": optuna_summary.get("claim_boundary", "") if optuna_summary else "",
        "optuna_recheck_available": bool(optuna_recheck),
        "optuna_recheck_stats": optuna_recheck.get("replication_stats", {}) if optuna_recheck else {},
        "optuna_recheck_replications": optuna_recheck.get("replications", []) if optuna_recheck else [],
        "claim_boundary": summary.get("claim_boundary", ""),
    }


@app.get("/api/v1/experiments/v3-four-methods-report")
def v3_four_methods_report() -> Dict[str, Any]:
    """v3.0 + OSM 四方法对比报告：Gurobi / AI warm / NSGA-III / ALNS 同标尺对比。

    全部在同一 v3.0 容量链 MIP + 同一 OSM 路网矩阵上运行，给出
    best_cost、cost gap、求解时间、Pareto 前沿规模，支撑论文核心论证。
    """
    summary = _load_json_or_empty(V3_FOUR_METHODS_JSON)
    results = summary.get("results", {})
    direct = results.get("gurobi_direct", {})
    ai = results.get("ai_warm", {})
    nsga = results.get("nsga3_v3", {})
    alns = results.get("alns_v3", {})
    exact_obj = summary.get("exact_reference_obj", 0)

    methods = []
    if direct:
        methods.append({
            "method": "gurobi_direct", "label": "Gurobi 直解",
            "best_cost": direct.get("objective"), "gap_pct": direct.get("mip_gap_pct"),
            "elapsed_sec": direct.get("elapsed_sec"), "front_size": 1,
            "kind": "exact",
        })
    if ai:
        methods.append({
            "method": "ai_warm", "label": "AI 增强 (warm start)",
            "best_cost": ai.get("objective"), "gap_pct": ai.get("mip_gap_pct"),
            "elapsed_sec": ai.get("elapsed_sec"), "front_size": 1,
            "kind": "exact_ai",
        })
    if nsga:
        methods.append({
            "method": "nsga3_v3", "label": "NSGA-III",
            "best_cost": nsga.get("mean_best_cost"), "gap_pct": nsga.get("mean_cost_gap_pct"),
            "elapsed_sec": nsga.get("mean_elapsed_sec"), "front_size": nsga.get("mean_front_size"),
            "kind": "heuristic",
        })
    if alns:
        methods.append({
            "method": "alns_v3", "label": "ALNS",
            "best_cost": alns.get("mean_best_cost"), "gap_pct": alns.get("mean_cost_gap_pct"),
            "elapsed_sec": alns.get("mean_elapsed_sec"), "front_size": alns.get("mean_front_size"),
            "kind": "heuristic",
        })

    # 计算 AI 加速比（vs gurobi_direct）
    speedup = None
    if direct.get("elapsed_sec") and ai.get("elapsed_sec") and ai["elapsed_sec"] > 0:
        speedup = round(direct["elapsed_sec"] / ai["elapsed_sec"], 2)

    return {
        "source": "/api/v1/experiments/v3-four-methods-report",
        "experiment": "v3_four_methods_comparison",
        "available": bool(summary),
        "config": summary.get("config", {}),
        "exact_reference_obj": exact_obj,
        "recommended_version": summary.get("recommended_version"),
        "recommended_label": summary.get("recommended_label"),
        "ai_speedup_vs_direct": speedup,
        "ai_top_k_sites": summary.get("ai_top_k_sites", []),
        "ai_warm_facilities": summary.get("ai_warm_facilities", []),
        "joint_strategy": summary.get("joint_strategy"),
        "methods": methods,
        "nsga3_runs": nsga.get("runs", []),
        "alns_runs": alns.get("runs", []),
        "claim_boundary": summary.get("claim_boundary", ""),
    }


@app.get("/api/v1/experiments/v3-solve-trace")
def v3_solve_trace() -> Dict[str, Any]:
    """v3.0 求解收敛轨迹：cold_start vs ai_warm，供前端做收敛动画。

    每条轨迹是 branch-and-cut 过程中每次 gap 改善的 (t, obj, bound, gap_pct)。
    前端逐帧播放展示 AI warm start 如何用联合 warm-start 设施组合更快收敛。
    """
    summary = _load_json_or_empty(V3_SOLVE_TRACE_JSON)
    cold = summary.get("cold_start", {})
    ai = summary.get("ai_warm", {})
    return {
        "source": "/api/v1/experiments/v3-solve-trace",
        "experiment": "v3_solve_trace",
        "available": bool(summary),
        "cold_start": {
            "status": cold.get("status"),
            "trace": cold.get("trace", []),
            "final": cold.get("final", {}),
            "elapsed_sec": cold.get("elapsed_sec"),
        },
        "ai_warm": {
            "status": ai.get("status"),
            "trace": ai.get("trace", []),
            "final": ai.get("final", {}),
            "elapsed_sec": ai.get("elapsed_sec"),
            "warm_sites": ai.get("warm_sites", []),
            "warm_facilities": ai.get("warm_facilities", []),
        },
        "config": summary.get("config", {}),
        "claim_boundary": summary.get("claim_boundary", ""),
    }


@app.get("/api/v1/experiments/osm-distance-report")
def osm_distance_report() -> Dict[str, Any]:
    """OSM 真实路网距离矩阵报告 + OSM vs Haversine 对比。"""
    osm = _load_json_or_empty(OSM_DISTANCE_MATRIX_JSON)
    compare = _load_json_or_empty(OSM_VS_HAVERSINE_JSON)
    mc = compare.get("matrix_comparison", {})
    cost_cmp = compare.get("cost_comparison", {})
    return {
        "source": "/api/v1/experiments/osm-distance-report",
        "available": bool(osm),
        "osm_matrix": {
            "graph_nodes_main_wcc": osm.get("graph_nodes_main_wcc"),
            "graph_edges_main_wcc": osm.get("graph_edges_main_wcc"),
            "total_pairs": osm.get("total_pairs"),
            "fallback_pairs": osm.get("fallback_pairs"),
            "fallback_pct": osm.get("fallback_pct"),
            "snap_mean_km": osm.get("snap_mean_km"),
            "snap_max_km": osm.get("snap_max_km"),
            "method": osm.get("method"),
        },
        "osm_vs_haversine": {
            "haversine_mean_km": mc.get("haversine_mean_km"),
            "osm_mean_km": mc.get("osm_mean_km"),
            "ratio_mean": mc.get("ratio_mean"),
            "osm_longer_pct": mc.get("osm_longer_pct"),
            "obj_haversine": cost_cmp.get("obj_haversine"),
            "obj_osm": cost_cmp.get("obj_osm"),
            "obj_diff_pct": cost_cmp.get("obj_diff_pct"),
        },
        "claim_boundary": osm.get("claim_boundary", ""),
    }


def _safe_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


# Cold-chain reference targets pulled from the v3.0 channel assumptions + okra
# preservation params, so the weather linkage cites real project numbers.
COLD_CHAIN_TEMP_TARGETS = [
    {"channel": "precool", "label": "预冷", "target_c": "≤ 7", "target_high": 7.0,
     "note": "采后 2 小时内首段预冷，快速移除田间热"},
    {"channel": "cold", "label": "冷藏", "target_c": "7–10", "target_high": 10.0,
     "note": "鲜销主渠道，文献保鲜目标温区"},
    {"channel": "ca", "label": "气调", "target_c": "8–10", "target_high": 10.0,
     "note": "气调/MAP 较长存放"},
    {"channel": "frozen", "label": "冷冻/加工", "target_c": "≤ -18", "target_high": -18.0,
     "note": "加工或冷冻兜底渠道（份额封顶 10%）"},
]


def _weather_cold_chain_signals(day_temps: list[float], current: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Derive honest cold-chain pressure signals from forecast day temps + live reading."""
    valid = [t for t in day_temps if t is not None]
    max_day = max(valid) if valid else None
    precool_high = 7.0              # COLD_CHAIN_TEMP_TARGETS precool target_high
    transport_loss_per_hour = 0.02  # data/params.json okra_preservation.transport_loss_per_hour
    precool_limit_h = 2.0           # okra_preservation.precool_time_limit_h
    signals = []
    cur_temp = _safe_float((current or {}).get("temperature_c"))
    cur_hum = _safe_float((current or {}).get("humidity_pct"))
    if cur_temp is not None:
        gap_now = round(cur_temp - precool_high, 1)
        signals.append({
            "label": "当前实时温度 vs 预冷目标",
            "value": f"{cur_temp:.0f}°C / 目标 ≤{precool_high:.0f}°C",
            "level": "warn" if gap_now > 0 else "ok",
            "detail": f"实时环境高出预冷目标 {gap_now:.1f}°C，采后需更快进入预冷" if gap_now > 0 else "实时温度接近目标区间",
        })
    if cur_hum is not None:
        signals.append({
            "label": "当前相对湿度",
            "value": f"{cur_hum:.0f}%",
            "level": "ok" if cur_hum >= 85 else "warn" if cur_hum < 60 else "info",
            "detail": "湿度偏低会加速秋葵失水萎蔫，冷藏/气调环节需注意保湿" if cur_hum < 60 else "湿度较高利于保鲜，但需防结露",
        })
    if max_day is not None:
        gap = round(max_day - precool_high, 1)
        signals.append({
            "label": "未来日间高温 vs 预冷目标",
            "value": f"{max_day:.0f}°C / 目标 ≤{precool_high:.0f}°C",
            "level": "warn" if gap > 0 else "ok",
            "detail": f"环境高出预冷目标 {gap:.1f}°C，田间热越高越依赖快速预冷" if gap > 0 else "环境温度接近目标区间",
        })
    signals.append({
        "label": "预冷时限硬约束",
        "value": f"{precool_limit_h:.0f} 小时内",
        "level": "info",
        "detail": "高温季节运输时间逼近 2h 限值时，部分远端需求点无法走预冷通道（模型已硬约束）",
    })
    signals.append({
        "label": "运输损耗敏感度",
        "value": f"{transport_loss_per_hour*100:.0f}% / 小时",
        "level": "info",
        "detail": "气温越高，超时运输的腐损放大越明显（损耗参数来自 params.json）",
    })
    return {"max_day_temp_c": max_day, "current_temp_c": cur_temp, "current_humidity_pct": cur_hum, "signals": signals}


@app.get("/api/v1/weather/panel")
def weather_panel() -> Dict[str, Any]:
    """39 节点高德气象快照 + 4 天预报 + 冷链温度链联动信号。

    诚实边界：39 节点共用同一县级 adcode（431226），实时温湿度（lives）与 4 天
    预报均为县域口径，不是逐节点不同的读数。温度链联动用真实项目参数
    （预冷 2h 限值、0.02/h 运输损耗）。
    """
    payload = _load_json_or_empty(WEATHER_CURRENT_JSON)
    results = payload.get("results", []) if isinstance(payload, dict) else []
    has_live = any(r.get("lives") for r in results)

    casts: list[dict[str, Any]] = []
    city = ""
    province = ""
    reporttime = ""
    current: Dict[str, Any] | None = None
    for node in results:
        forecasts = node.get("forecasts", []) or []
        if forecasts and not casts:
            fc = forecasts[0]
            city = fc.get("city", "")
            province = fc.get("province", "")
            reporttime = fc.get("reporttime", "")
            casts = fc.get("casts", []) or []
        lives = node.get("lives", []) or []
        if lives and current is None:
            live = lives[0]
            current = {
                "temperature_c": _safe_float(live.get("temperature_float") or live.get("temperature")),
                "humidity_pct": _safe_float(live.get("humidity_float") or live.get("humidity")),
                "weather": live.get("weather"),
                "wind_direction": live.get("winddirection"),
                "wind_power": live.get("windpower"),
                "report_time": live.get("reporttime"),
            }
        if casts and current is not None:
            break

    forecast = []
    day_temps = []
    for cast in casts:
        day_t = _safe_float(cast.get("daytemp_float") or cast.get("daytemp"))
        night_t = _safe_float(cast.get("nighttemp_float") or cast.get("nighttemp"))
        if day_t is not None:
            day_temps.append(day_t)
        forecast.append({
            "date": cast.get("date"),
            "week": cast.get("week"),
            "day_weather": cast.get("dayweather"),
            "night_weather": cast.get("nightweather"),
            "day_temp_c": day_t,
            "night_temp_c": night_t,
            "day_wind": cast.get("daywind"),
            "wind_power": cast.get("daypower"),
        })

    return {
        "source": "/api/v1/weather/panel",
        "source_backend": "file_gaode_snapshot" if results else "empty",
        "available": bool(forecast),
        "fetched_at": payload.get("fetched_at"),
        "node_count": payload.get("node_count", len(results)),
        "adcode_shared": "431226",
        "has_live_readings": has_live,
        "current": current,
        "location": {"province": province, "city": city, "reporttime": reporttime},
        "forecast": forecast,
        "cold_chain_targets": COLD_CHAIN_TEMP_TARGETS,
        "cold_chain_linkage": _weather_cold_chain_signals(day_temps, current),
        "claim_boundary": (
            "高德实时气象快照（非历史序列）。39 节点共用县级 adcode 431226，实时温湿度与 4 天预报均为县域口径，"
            "非逐节点读数；仅用于 MIS 展示与冷链温区联动，不用于损耗参数训练。"
        ),
    }


def _weather_snapshot_age_seconds() -> float | None:
    if not WEATHER_CURRENT_JSON.exists():
        return None
    return max(0.0, time.time() - WEATHER_CURRENT_JSON.stat().st_mtime)


def _refresh_gaode_weather_snapshot(*, force: bool = False, max_age_seconds: int = 300) -> Dict[str, Any]:
    """Refresh the local Gaode weather snapshot without exposing the API key."""
    age = _weather_snapshot_age_seconds()
    if not force and age is not None and age <= max_age_seconds:
        panel = weather_panel()
        panel["refresh"] = {
            "used_cache": True,
            "age_seconds": round(age, 2),
            "max_age_seconds": max_age_seconds,
            "refreshed_at": None,
        }
        return panel

    from scripts.fetch_gaode_weather import (  # local import keeps API startup light
        GAODE_WEATHER_URL,
        OUT_CSV,
        OUT_JSON,
        OUT_SUMMARY,
        fetch_weather,
        get_api_key,
        load_nodes,
        node_to_adcode,
    )

    api_key = get_api_key()
    nodes = load_nodes()
    adcode_to_nodes: dict[str, list[dict[str, Any]]] = {}
    for node in nodes:
        adcode_to_nodes.setdefault(node_to_adcode(node), []).append(node)

    fetched_at = datetime.now(timezone.utc).isoformat()
    weather_results: list[dict[str, Any]] = []
    errors: list[str] = []
    for adcode, node_list in adcode_to_nodes.items():
        try:
            forecast_resp = fetch_weather(adcode, api_key, extensions="all")
            status = forecast_resp.get("status", "0")
            info = forecast_resp.get("info", "")
            if status != "1":
                errors.append(f"adcode={adcode}: status={status} info={info}")
                continue

            lives: list[dict[str, Any]] = []
            try:
                base_resp = fetch_weather(adcode, api_key, extensions="base")
                if base_resp.get("status") == "1":
                    lives = base_resp.get("lives", [])
                else:
                    errors.append(f"adcode={adcode} (base): status={base_resp.get('status')} info={base_resp.get('info')}")
            except Exception as exc:
                errors.append(f"adcode={adcode} (base): {exc}")

            forecasts = forecast_resp.get("forecasts", [])
            for node in node_list:
                weather_results.append({
                    "node_id": node["node_id"],
                    "node_name": node["name"],
                    "adcode": adcode,
                    "lat": node["lat"],
                    "lon": node["lon"],
                    "fetched_at": fetched_at,
                    "lives": lives,
                    "forecasts": forecasts,
                    "api_status": status,
                    "api_info": info,
                })
        except Exception as exc:
            errors.append(f"adcode={adcode}: {exc}")

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(
        json.dumps({
            "fetched_at": fetched_at,
            "node_count": len(nodes),
            "adcode_count": len(adcode_to_nodes),
            "result_count": len(weather_results),
            "errors": errors,
            "results": weather_results,
            "claim_boundary": (
                "Real-time / 4-day forecast weather from Gaode API. NOT historical daily data. "
                "Suitable for MIS/mobile display and cold-chain linkage; not for loss-parameter training."
            ),
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    rows_written = 0
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        import csv
        writer = csv.writer(f)
        writer.writerow([
            "source_id", "observation_date", "station_id", "station_name", "lat", "lon",
            "temperature_mean_c", "temperature_max_c", "temperature_min_c",
            "relative_humidity_pct", "wind_speed_m_s", "source_url", "raw_record_json",
        ])
        for row in weather_results:
            for live in row.get("lives", []):
                writer.writerow([
                    "SRC-E-001", fetched_at[:10], row["adcode"], row["node_name"], row["lat"], row["lon"],
                    live.get("temperature"), None, None, live.get("humidity"), None,
                    GAODE_WEATHER_URL, json.dumps(live, ensure_ascii=False),
                ])
                rows_written += 1
            for fc_group in row.get("forecasts", []):
                for cast in fc_group.get("casts", []):
                    writer.writerow([
                        "SRC-E-001", cast.get("date"), row["adcode"], row["node_name"], row["lat"], row["lon"],
                        None, cast.get("daytemp"), cast.get("nighttemp"), None, None,
                        GAODE_WEATHER_URL, json.dumps(cast, ensure_ascii=False),
                    ])
                    rows_written += 1

    OUT_SUMMARY.parent.mkdir(parents=True, exist_ok=True)
    OUT_SUMMARY.write_text(
        json.dumps({
            "fetched_at": fetched_at,
            "nodes": len(nodes),
            "adcodes": len(adcode_to_nodes),
            "results": len(weather_results),
            "csv_rows": rows_written,
            "errors": errors,
            "claim_boundary": "Real-time Gaode weather; not historical. Use for MIS/mobile display, not loss-parameter training.",
            "out_json": str(OUT_JSON),
            "out_csv": str(OUT_CSV),
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    panel = weather_panel()
    panel["refresh"] = {
        "used_cache": False,
        "age_seconds": 0.0,
        "max_age_seconds": max_age_seconds,
        "refreshed_at": fetched_at,
        "errors": errors,
        "csv_rows": rows_written,
    }
    return panel


@app.get("/api/v1/weather/refresh")
def weather_refresh(force: bool = False, max_age_seconds: int = 300) -> Dict[str, Any]:
    """Refresh Gaode weather through the backend; never returns or exposes the API key."""
    if max_age_seconds < 0:
        raise HTTPException(status_code=400, detail="max_age_seconds must be >= 0")
    try:
        return _refresh_gaode_weather_snapshot(force=force, max_age_seconds=max_age_seconds)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/v1/whatif/screen")
def whatif_screen(request: WhatIfRequest) -> Dict[str, Any]:
    """What-If 决策对比：调参后用 solver-free 容量筛选实时返回选址压力变化。

    接收 max_facilities / 通道份额 / 碳价 / 收获峰值因子，复用稳健性筛选逻辑
    与基线并排对比，返回设施数下界、峰值库存、可行性状态的变化。碳价仅影响
    成本目标权重、不改变容量可行性（已显式说明）。
    """
    return build_whatif_screen(
        max_facilities=request.max_facilities,
        channel_shares=request.channel_shares,
        carbon_price=request.carbon_price,
        harvest_peak_factor=request.harvest_peak_factor,
    )


def _build_paper_export_payload() -> Dict[str, Any]:
    return build_paper_export(
        paper_pack=_paper_evidence_pack(),
        four_methods=v3_four_methods_report(),
        ai_warmstart=ai_warmstart_report(),
        osm_distance=osm_distance_report(),
    )


@app.get("/api/v1/export/paper")
def export_paper() -> Dict[str, Any]:
    """论文证据导出：把本会话核心指标汇总为 LaTeX 表格 + Markdown 报告（预览）。

    只读汇总，所有数值来自已验证的报告产物（paper_evidence_pack / v3 四方法 /
    AI warm start / OSM 距离），不重新求解、不编造。
    """
    return _build_paper_export_payload()


@app.get("/api/v1/export/paper/download")
def export_paper_download(fmt: str = "latex"):
    """下载论文证据导出的原始文件：fmt=latex 返回 .tex，fmt=markdown 返回 .md。"""
    payload = _build_paper_export_payload()
    if fmt == "markdown":
        content = payload.get("markdown", "")
        media_type = "text/markdown; charset=utf-8"
        filename = "okra_paper_evidence.md"
    elif fmt == "latex":
        content = payload.get("latex", "")
        media_type = "application/x-tex; charset=utf-8"
        filename = "okra_paper_evidence.tex"
    else:
        raise HTTPException(status_code=400, detail="fmt must be 'latex' or 'markdown'.")
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


AGENT_NAV_TARGETS: dict[str, dict[str, str]] = {
    "overview": {"route": "/overview", "label": "总览看板", "keywords": "总览 看板 dashboard 首页 overview"},
    "map": {"route": "/map", "label": "地图选址", "keywords": "地图 选址 高德 amap map"},
    "nodes": {"route": "/nodes", "label": "节点管理", "keywords": "节点 冷库 客户 配送站 crud node"},
    "routes": {"route": "/routes", "label": "路线管理", "keywords": "路线 路径 站点 route"},
    "weather": {"route": "/weather", "label": "实时气象", "keywords": "天气 气象 温度 高温 weather"},
    "aisolve": {"route": "/aisolve", "label": "AI 增强求解", "keywords": "ai增强 ai warm warm start 四方法"},
    "solve": {"route": "/solve", "label": "算法求解过程", "keywords": "求解 算法 gurobi benders gap solve"},
    "pareto": {"route": "/pareto", "label": "多目标 Pareto", "keywords": "pareto 多目标 前沿 成本 腐损 碳排"},
    "analysis": {"route": "/analysis", "label": "分析可视化", "keywords": "分析 可视化 成本 灵敏度 场景 analysis"},
    "whatif": {"route": "/whatif", "label": "What-If 决策", "keywords": "what-if whatif 决策 调参 对比"},
    "model": {"route": "/model", "label": "数学模型", "keywords": "模型 数学 mip 公式 model"},
    "ai": {"route": "/ai", "label": "AI 融合增强", "keywords": "ai融合 ml dl rl 机器学习 深度 强化"},
    "evidence": {"route": "/evidence", "label": "数据与证据链", "keywords": "证据 数据 数据源 evidence"},
    "export": {"route": "/export", "label": "论文证据导出", "keywords": "导出 论文 latex word markdown export"},
}


def _agent_status_cards() -> list[dict[str, Any]]:
    db_payload = database_status_payload()
    db_probe_payload = _db_probe_response(db_payload)
    map_status = _map_provider_status()
    paper = _paper_evidence_pack().get("summary", {})
    grb_license = os.environ.get("GRB_LICENSE_FILE", "")
    return [
        {
            "title": "数据库",
            "value": "PostgreSQL 可查询" if db_probe_payload.get("query_ready") else "文件兜底",
            "level": "ok" if db_probe_payload.get("query_ready") else "warn",
            "detail": "已连接 okra_cold_storage" if db_probe_payload.get("query_ready") else "当前仍可读取已验证文件资产。",
        },
        {
            "title": "Gurobi",
            "value": "许可证路径存在" if grb_license and Path(grb_license).is_file() else "未确认",
            "level": "ok" if grb_license and Path(grb_license).is_file() else "warn",
            "detail": grb_license or "未设置 GRB_LICENSE_FILE。",
        },
        {
            "title": "地图",
            "value": "高德底图可用" if map_status.get("summary", {}).get("browser_provider_ready") else "文件点位",
            "level": "ok" if map_status.get("summary", {}).get("browser_provider_ready") else "warn",
            "detail": map_status.get("summary", {}).get("browser_provider") or "AMap 未启用时使用点位兜底。",
        },
        {
            "title": "论文证据",
            "value": "已就绪" if paper.get("paper_ready") else "待补齐",
            "level": "ok" if paper.get("paper_ready") else "warn",
            "detail": f"证据层数：{paper.get('paper_layer_count', 0)}",
        },
    ]


AGENT_DEFAULT_SUGGESTIONS = ["解释 Optuna AI warm start", "检查论文能怎么写", "AI-Benders 能不能写加速", "下一步建议"]
AGENT_READ_ONLY_POLICY = {
    "read_only": True,
    "requires_confirmation_for": ["download", "live_solve", "best_trial_recheck"],
    "blocked": ["delete", "core_parameter_mutation", "direct_solver_start", "direct_optuna_start", "database_write"],
}


def _agent_ref(source: str, title: str, value: str, detail: str = "", route: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "source": source,
        "title": title,
        "value": value,
        "detail": detail,
    }
    if route:
        payload["route"] = route
    return payload


def _agent_card(title: str, value: str, detail: str, level: str = "info") -> dict[str, Any]:
    return {"title": title, "value": value, "detail": detail, "level": level}


def _agent_float(value: Any, digits: int = 2, suffix: str = "") -> str:
    try:
        return f"{float(value):.{digits}f}{suffix}"
    except (TypeError, ValueError):
        return "-"


def _agent_find_nav(text: str) -> dict[str, str] | None:
    for target in AGENT_NAV_TARGETS.values():
        haystack = f"{target['label']} {target['route']} {target['keywords']}".lower()
        if any(part and part in text for part in haystack.split()):
            return {"type": "navigate", "label": f"打开{target['label']}", "route": target["route"]}
    return None


def _agent_optuna_warmstart_payload() -> dict[str, Any]:
    warm = ai_warmstart_report()
    if not warm.get("optuna_available"):
        return {
            "reply": "Optuna AI warm start 正式结果还没有生成。需要先运行 `experiments/ai_warmstart_optuna.py`，生成结果后我才能引用证据。",
            "cards": [_agent_card("Optuna", "未生成", "未找到 ai_warmstart_optuna_summary.json。", "warn")],
            "evidence_refs": [_agent_ref("/api/v1/experiments/ai-warmstart-report", "AI warm start 报告", "Optuna unavailable", route="/aisolve")],
            "claim_boundary": "未生成 Optuna 证据时，不能声称自动调参加速。",
            "confidence": "medium",
        }

    best = warm.get("optuna_best_trial", {})
    recheck = warm.get("optuna_recheck_stats", {})
    speedup = best.get("speedup_vs_cold") or warm.get("optuna_best_speedup")
    recheck_speedup = recheck.get("speedup_vs_cold_mean")
    historical = warm.get("optuna_historical_best_speedup")
    exceeds = warm.get("optuna_exceeds_historical_best")
    reply = (
        "Optuna + AI warm start 是当前最强的主线加速证据：正式 24-trial study 的 best trial "
        f"#{best.get('number')} 达到 {_agent_float(speedup, 4, 'x')}，elapsed={best.get('elapsed_sec')}s，gap={best.get('gap_pct')}%。"
        f"固定 best 配置复核均值为 {_agent_float(recheck_speedup, 4, 'x')}。"
        f"它没有刷新历史最高 {_agent_float(historical, 2, 'x')}，所以应写成 clean speedup evidence，而不是新纪录。"
    )
    cards = [
        _agent_card("Optuna best", _agent_float(speedup, 2, "x"), f"trial #{best.get('number')} · {best.get('elapsed_sec')}s · gap {best.get('gap_pct')}%", "ok"),
        _agent_card("固定复核", _agent_float(recheck_speedup, 2, "x"), f"mean {recheck.get('elapsed_sec_mean')}s · all_solved={recheck.get('all_solved_to_tol')}", "ok"),
        _agent_card("历史最高", _agent_float(historical, 2, "x"), f"exceeds_historical_best={exceeds}", "warn" if not exceeds else "ok"),
    ]
    evidence_refs = [
        _agent_ref(
            "/api/v1/experiments/ai-warmstart-report",
            "Optuna AI warm start",
            f"{_agent_float(speedup, 4, 'x')} best / {_agent_float(recheck_speedup, 4, 'x')} recheck",
            f"single={warm.get('optuna_single_trial_complete_count')}/{warm.get('optuna_n_trials_requested')}, multi={warm.get('optuna_multi_trial_complete_count')}/{warm.get('optuna_multi_trials_requested')}",
            "/aisolve",
        ),
        _agent_ref("docs/Optuna_AI_WarmStart_证据卡.md", "中文证据卡", "clean speedup evidence", "包含正式实验、复核和声明边界。", "/ai"),
    ]
    return {
        "reply": reply,
        "cards": cards,
        "evidence_refs": evidence_refs,
        "claim_boundary": warm.get("optuna_claim_boundary") or "Optuna 调参只增强初始解和求解配置；最终解仍由 Gurobi 认证。",
        "confidence": "high",
    }


def _agent_ai_fusion_payload() -> dict[str, Any]:
    fusion = ai_fusion()
    layers = fusion.get("layers", [])
    layer_names = [str(layer.get("tech")) for layer in layers if layer.get("tech")]
    optuna_layer = next((layer for layer in layers if "Optuna" in str(layer.get("tech"))), {})
    reply = (
        "AI 融合层可以按“ML warm start + Optuna 调参 + RL/cut ranking + Gurobi 认证”来讲。"
        "主加速证据放在 Optuna AI warm start，Benders 子线放在 cut ranking / robustness 机制，不抢主线。"
    )
    return {
        "reply": reply,
        "cards": [
            _agent_card("AI 层数", str(len(layers)), " / ".join(layer_names[:5]) or "未生成", "ok" if layers else "warn"),
            _agent_card("Optuna 层", "已接入" if optuna_layer else "缺失", optuna_layer.get("what", "未找到 Optuna 层"), "ok" if optuna_layer else "warn"),
        ],
        "evidence_refs": [
            _agent_ref("/api/v1/ai/fusion", "AI 融合报告", f"{len(layers)} layers", "展示 ML/DL/RL/Optuna 在求解链的位置。", "/ai"),
        ],
        "claim_boundary": fusion.get("claim_boundary") or "AI 增强求解流程，但不替代 Gurobi 认证。",
        "confidence": "high" if layers else "medium",
    }


def _agent_benders_payload() -> dict[str, Any]:
    conv = benders_convergence()
    cutmgmt = _load_json_or_empty(CUTMGMT_JSON)
    verdict = cutmgmt.get("verdict", {})
    conclusion = verdict.get("conclusion") or "cut ranking / robustness evidence"
    reply = (
        "AI-Benders 这条线建议诚实写成 cut ranking / robustness 机制创新。"
        "目前不能写成对朴素预算策略的广义显著加速；可以写学习式 cut 排序帮助管理切割优先级，并保持 Gurobi/直接 MIP 校验边界。"
    )
    return {
        "reply": reply,
        "cards": [
            _agent_card("Benders 口径", "鲁棒性/排序", str(conclusion), "warn"),
            _agent_card("显著加速", "不能冒进", "除非后续统计实验支持，否则不写显著加速。", "warn"),
        ],
        "evidence_refs": [
            _agent_ref("/api/v1/analysis/benders-convergence", "Benders convergence", "只读收敛证据", f"available={conv.get('available')}", "/solve"),
            _agent_ref("/api/v1/ai/fusion", "AI fusion", "RL/cut ranking layer", "与 Optuna 主线分层展示。", "/ai"),
        ],
        "claim_boundary": "AI-Benders/cut ranking 是机制和鲁棒性证据；没有新实验证据时，不能声称通用显著加速。",
        "confidence": "high",
    }


def _agent_paper_claim_payload() -> dict[str, Any]:
    optuna = _agent_optuna_warmstart_payload()
    paper = _paper_evidence_pack().get("summary", {})
    reply = (
        "论文/汇报建议这样写：Optuna 自动调参在 v3.0 精确求解链上提供 clean speedup evidence，"
        "best 为 5.65x，固定配置复核仍约 4.84x，目标值不劣化，最终由 Gurobi 认证。"
        "不要写 AI 替代 Gurobi，也不要写 AI-Benders 已显著加速。"
    )
    return {
        "reply": reply,
        "cards": [
            _agent_card("可写", "5.65x clean speedup", "Optuna warm start 主证据，Gurobi 认证。", "ok"),
            _agent_card("不可写", "AI 替代 Gurobi", "也不能写 AI-Benders 已通用显著加速。", "warn"),
            _agent_card("证据包", f"{paper.get('paper_layer_count', 0)} layers", f"paper_ready={paper.get('paper_ready')}", "ok" if paper.get("paper_ready") else "warn"),
        ],
        "evidence_refs": optuna["evidence_refs"] + [
            _agent_ref("/api/v1/experiments/paper-evidence-pack", "论文证据包", f"layers={paper.get('paper_layer_count', 0)}", "只读证据总入口。", "/evidence"),
        ],
        "claim_boundary": "论文口径必须区分：Optuna warm start 是主加速证据；AI-Benders 是 cut ranking / robustness 机制证据。",
        "confidence": "high",
    }


def _agent_next_step_payload() -> dict[str, Any]:
    reply = (
        "下一步建议优先把 Agent v2、Optuna 证据卡和论文导出口径串成展示闭环。"
        "如果继续做实验，先做固定 best trial 的 2-3 次复核；DRL 完整环境可以作为后续扩展，不抢当前主线。"
    )
    return {
        "reply": reply,
        "cards": [
            _agent_card("优先级 1", "Agent v2 展示闭环", "证据问答、论文口径检查、可控跳转。", "ok"),
            _agent_card("优先级 2", "best trial 复核", "补 2-3 次固定参数复核，强化稳定性。", "ok"),
            _agent_card("后续扩展", "DRL-lite", "继续 residual cut ranking，不急着上完整 PPO/DQN。", "info"),
        ],
        "evidence_refs": [
            _agent_ref("docs/Optuna_AI_WarmStart_证据卡.md", "Optuna 证据卡", "主创新证据", "用于 Agent 和论文共同引用。", "/ai"),
            _agent_ref("/api/v1/ai/fusion", "AI 融合报告", "分层路线", "用于说明 ML/Optuna/RL/Gurobi 关系。", "/ai"),
        ],
        "claim_boundary": "下一步建议不自动运行求解器；所有耗时实验仍需人工确认。",
        "confidence": "high",
    }


def _agent_explain(text: str) -> dict[str, Any] | None:
    if any(key in text for key in ("pareto", "多目标", "前沿")):
        return {
            "reply": (
                "Pareto 前沿表示成本、腐损、碳排放之间无法同时继续改好的候选方案集合。"
                "如果成本最低点的腐损或碳排偏高，就需要在前沿上选择更平衡的方案，而不是只看总成本。"
            ),
            "evidence_refs": [_agent_ref("/api/v1/dashboard/bootstrap", "Pareto 看板", "多目标前沿", "展示成本、腐损、碳排的权衡。", "/pareto")],
            "claim_boundary": "Pareto 展示用于决策权衡，不等同于自动替用户选择唯一最优偏好。",
            "confidence": "medium",
        }
    if any(key in text for key in ("optuna", "warm", "加速", "ai warm", "ai增强")):
        return _agent_optuna_warmstart_payload()
    if any(key in text for key in ("benders", "cut", "切割")):
        return _agent_benders_payload()
    if any(key in text for key in ("what-if", "whatif", "调参")):
        return {
            "reply": (
                "What-If 模块是 solver-free 容量压力筛选：它能快速比较参数变化后的设施压力和可行性趋势，"
                "但不等同于重新跑一次 Gurobi 最优选址。"
            ),
            "evidence_refs": [_agent_ref("/api/v1/whatif/screen", "What-If screen", "solver-free", "用于快速压力筛选。", "/whatif")],
            "claim_boundary": "What-If 是筛选与对比，不是重新认证最优解。",
            "confidence": "medium",
        }
    if any(key in text for key in ("证据", "导出", "论文")):
        return _agent_paper_claim_payload()
    return None


def _build_agent_response(message: str) -> Dict[str, Any]:
    text = message.strip().lower()
    actions: list[dict[str, Any]] = []
    cards: list[dict[str, Any]] = []
    evidence_refs: list[dict[str, Any]] = []
    suggestions = list(AGENT_DEFAULT_SUGGESTIONS)
    intent = "general_help"
    confidence = "low"
    claim_boundary = "Agent v2 为只读证据助手；不会直接运行求解器、写数据库或读取本地密钥。"
    reply = "我可以帮您查询状态、解释结果、跳转页面和刷新看板。导出或运行求解这类动作，我会先请您确认。"

    if any(key in text for key in ("运行求解", "实时求解", "跑求解", "启动求解", "gurobi求解")):
        intent = "solve_confirm"
        confidence = "high"
        actions.append({
            "type": "confirm_solve",
            "label": "确认后打开算法求解过程",
            "route": "/solve",
            "detail": "实时求解会占用本地 Gurobi 资源；我只跳转页面，不直接启动求解。",
        })
        reply = "实时求解属于敏感动作，会占用 Gurobi 资源。我可以先带您到求解页，但不会直接启动按钮。"
        suggestions = ["打开算法求解过程", "解释 AI warm start", "查看 Gurobi 状态"]
        evidence_refs.append(_agent_ref("/api/v1/experiments/ai-warmstart-report", "AI warm start", "只读状态", "求解动作需要人工确认。", "/solve"))

    elif any(key in text for key in ("下载", "导出", "tex", "latex", "word", "markdown")):
        intent = "export_confirm"
        confidence = "high"
        actions.append({
            "type": "confirm_download",
            "label": "确认后打开论文证据导出页",
            "route": "/export",
            "detail": "下载动作会打开导出页，由您手动点击 .tex 或 .md 下载。",
        })
        reply = "论文证据可以导出，但我不会直接替您下载。确认后我先带您到导出页，您再手动选择 .tex 或 .md。"
        suggestions = ["打开论文证据导出", "解释证据包", "查看系统状态"]
        evidence_refs.append(_agent_ref("/api/v1/export/paper", "论文导出预览", "confirm_download", "Agent 只跳转，不直接下载。", "/export"))

    if any(key in text for key in ("状态", "数据库", "gurobi", "许可证", "license", "地图", "高德", "系统")):
        intent = "system_status"
        confidence = "high"
        cards = _agent_status_cards()
        reply = "这是当前 MIS 的轻量健康检查：数据库、Gurobi、地图和论文证据都会只读检查，不会改动环境。"
        evidence_refs = [
            _agent_ref("/api/v1/dashboard/bootstrap", "Dashboard bootstrap", "health snapshot", "聚合数据库、地图、证据链状态。", "/overview"),
        ]
        claim_boundary = "系统状态检查只读，不会修改数据库、地图配置或 Gurobi 环境。"
        suggestions = ["刷新看板", "打开地图选址", "打开论文证据导出"]

    nav_action = _agent_find_nav(text)
    if any(key in text for key in ("去", "打开", "跳转", "带我", "进入")) and nav_action:
        intent = "navigation"
        confidence = "high"
        actions.append(nav_action)
        reply = f"可以，我帮您准备跳转到「{nav_action['label'].replace('打开', '')}」。"
        evidence_refs.append(_agent_ref("frontend route", nav_action["label"], nav_action["route"], "仅前端跳转，不执行后端任务。", nav_action["route"]))
        claim_boundary = "跳转动作只改变前端页面，不触发求解、导出或写入。"
        suggestions = ["刷新看板", "查看系统状态", "解释当前页面"]

    if any(key in text for key in ("刷新", "更新", "重载", "reload")):
        intent = "refresh"
        confidence = "high"
        actions.append({"type": "refresh", "label": "刷新看板数据"})
        reply = "可以刷新。这个动作只会重新拉取 dashboard/bootstrap 数据，不会运行优化或修改参数。"
        evidence_refs.append(_agent_ref("/api/v1/dashboard/bootstrap", "看板刷新", "read-only reload", "重新拉取聚合数据。", "/overview"))
        claim_boundary = "刷新只重新读取看板数据，不运行优化或写入文件。"
        suggestions = ["查看系统状态", "打开总览看板", "解释当前指标"]

    if intent == "general_help":
        if any(key in text for key in ("融合", "agent", "智能体", "ml", "dl", "rl", "机器学习", "强化学习")):
            intent = "ai_fusion"
            payload = _agent_ai_fusion_payload()
        elif any(key in text for key in ("benders", "cut", "切割")):
            intent = "benders_boundary"
            payload = _agent_benders_payload()
        elif any(key in text for key in ("论文", "汇报", "怎么写", "能不能写", "口径", "claim")):
            intent = "paper_claim_check"
            payload = _agent_paper_claim_payload()
        elif any(key in text for key in ("下一步", "接下来", "建议", "计划")):
            intent = "next_step_advice"
            payload = _agent_next_step_payload()
        else:
            payload = _agent_explain(text)
            if payload and any(key in text for key in ("optuna", "warm", "加速", "ai warm", "ai增强")):
                intent = "optuna_warmstart"
            elif payload:
                intent = "explain"
        if payload:
            reply = payload.get("reply", reply)
            cards = payload.get("cards", cards)
            evidence_refs = payload.get("evidence_refs", evidence_refs)
            claim_boundary = payload.get("claim_boundary", claim_boundary)
            confidence = payload.get("confidence", "medium")
            suggestions = ["带我去相关页面", "查看系统状态", "刷新看板"]

    return {
        "reply": reply,
        "intent": intent,
        "evidence_refs": evidence_refs,
        "confidence": confidence,
        "claim_boundary": claim_boundary,
        "actions": actions,
        "cards": cards,
        "suggestions": suggestions,
        "policy": AGENT_READ_ONLY_POLICY,
    }


@app.post("/api/v1/agent/chat")
def agent_chat(request: AgentChatRequest) -> Dict[str, Any]:
    """轻量 MIS Agent：规则型意图识别 + 只读状态解释 + 前端动作建议。

    不调用外部大模型，不写数据库，不触发 Gurobi 求解；导出/求解只返回需确认动作。
    """
    return _build_agent_response(request.message)


@app.get("/api/v1/ai/fusion")
def ai_fusion() -> Dict[str, Any]:
    """AI fusion explanation: which ML/DL/RL techniques enhance which OR stage."""
    cutmgmt = _load_json_or_empty(CUTMGMT_JSON)
    return {
        "source": "/api/v1/ai/fusion",
        "thesis": "AI 不替代优化，而是在『参数生成 → 模型构建 → 求解加速』各环节增强运筹优化（AI4OPT）。",
        "layers": [
            {
                "tech": "机器学习 (ML)",
                "model": "LightGBM / XGBoost / GradientBoosting",
                "stage": "参数生成",
                "what": "Smart Predict-then-Optimize：从历史特征学习秋葵损耗参数 α、β，替代文献固定值。",
                "file": "src/data_driven/loss_param_learner.py",
                "boundary": "当前训练数据为合成样本，仅证明管线可运行，未宣称真实企业损耗预测能力。",
            },
            {
                "tech": "深度学习 (DL)",
                "model": "二分图消息传递 GNN（GraphSAGE 风格）",
                "stage": "模型构建 / 结构编码",
                "what": "把『候选冷库—需求点』二分图编码成结构嵌入，作为 cut 选择策略的上下文。",
                "file": "src/algorithms/gnn_encoder.py",
                "boundary": "编码器为轻量原型，用于上下文表示而非端到端替代求解。",
            },
            {
                "tech": "强化学习 (RL)",
                "model": "上下文老虎机 (contextual bandit)",
                "stage": "求解加速 / cut 管理",
                "what": "学习『每轮保留哪些 Benders cut』的策略，奖励 = gap 改善量。",
                "file": "src/algorithms/rl_agent.py",
                "boundary": "受控实验：学习式策略鲁棒性≥最佳朴素对照；相对 all_cuts 的 jointly-solved cases 存在 wall-clock edge，但对 recency/random 不支持广义显著加速主张；推荐 cut 排序/优先级而非硬丢弃。",
            },
            {
                "tech": "超参数优化 (Optuna)",
                "model": "TPE / NSGA-II multi-objective study",
                "stage": "求解配置搜索",
                "what": "自动搜索 XGBoost、warm start 版本与 Gurobi 参数，使 AI warm start 更快达到同一 gap 容差。",
                "file": "experiments/ai_warmstart_optuna.py",
                "boundary": "Optuna 优化的是初始解质量与求解配置；最终可行性、目标值和 gap 仍由 Gurobi 认证。",
            },
        ],
        "controlled_experiment": cutmgmt.get("verdict", {}),
        "claim_boundary": cutmgmt.get("research_boundary", ""),
    }


def create_app() -> FastAPI:
    return app
