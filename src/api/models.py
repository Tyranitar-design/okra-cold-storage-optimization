"""Pydantic models for API requests and responses."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class OptimizeRequest(BaseModel):
    carbon_price: float = Field(50.0, ge=0.0)
    loss_price: float = Field(3000.0, ge=0.0)
    max_facilities: int = Field(8, ge=1)
    time_limit: int = Field(300, ge=1)
    mip_gap: float = Field(0.01, ge=0.0, le=1.0)


class RoutingRequest(BaseModel):
    scenario_id: str | None = None
    payload: dict = Field(default_factory=dict)


class LogisticsPushRequest(BaseModel):
    layout_id: str = Field("baseline_v2_1", min_length=1)
    scenario_id: str | None = None
    storage_nodes: list[dict[str, Any]] = Field(default_factory=list)
    demand_nodes: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class LogisticsRoutingSolveRequest(BaseModel):
    scenario_id: str = Field(..., min_length=1)
    layout_id: str = Field("baseline_v2_1", min_length=1)
    orders: list[dict[str, Any]] = Field(default_factory=list)
    vehicles: list[dict[str, Any]] = Field(default_factory=list)
    temperature_constraints: dict[str, Any] = Field(default_factory=dict)
    objective: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvidenceSource(BaseModel):
    source_id: str
    source_name: str
    source_type: str
    evidence_level: str
    file_path_or_url: str
    access_date: str | None = None
    license_or_permission: str | None = None
    variables: str | None = None
    preprocessing: str | None = None
    limitations: str | None = None
    used_in: str | None = None


class ExperimentCreateRequest(BaseModel):
    experiment_name: str = Field(..., min_length=1)
    experiment_type: str = Field("file_registry", min_length=1)
    model_version: str = Field("v2_1", min_length=1)
    data_version: str = Field("current_files", min_length=1)
    solver: str = Field("gurobi", min_length=1)
    description: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)


class LiveSolveRequest(BaseModel):
    mode: str = Field("cold_start", pattern="^(cold_start|ai_warm)$")
    profile: str = Field("bound_focus_60s", min_length=1)
    time_limit: int | None = Field(default=None, ge=1)
    mip_gap: float | None = Field(default=None, ge=0.0, le=1.0)


# ── MIS Phase 2: Auth / Token ──────────────────────────────────
class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=1, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user_id: str
    role: str


# ── MIS Phase 2: Node CRUD ─────────────────────────────────────
class NodeCreate(BaseModel):
    node_id: str | None = Field(default=None, min_length=1, max_length=50,
                                 description="Unique node ID; auto-generated if omitted.")
    name: str = Field(..., min_length=1, max_length=100)
    level: int = Field(..., ge=0, le=10)
    lat: float = Field(..., ge=-90.0, le=90.0)
    lon: float = Field(..., ge=-180.0, le=180.0)
    okra_production_ton: float = Field(0.0, ge=0.0)
    is_candidate: bool = False
    source_id: str | None = None


class NodeUpdate(BaseModel):
    name: str | None = None
    level: int | None = None
    lat: float | None = None
    lon: float | None = None
    okra_production_ton: float | None = None
    is_candidate: bool | None = None
    source_id: str | None = None


# ── MIS Phase 2: Route Plan CRUD ───────────────────────────────
class RoutePlanCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str = ""
    vehicle_type: str = ""


class RoutePlanUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    status: str | None = None  # draft / active / archived
    vehicle_type: str | None = None


# ── MIS Phase 2: Route Stop ────────────────────────────────────
class RouteStopCreate(BaseModel):
    stop_order: int = Field(..., ge=1)
    node_id: str = Field(..., min_length=1)
    action: str = Field("delivery", pattern="^(pickup|delivery|transit)$")
    planned_arrival: str | None = None
    planned_departure: str | None = None
    notes: str = ""


# ── MIS Phase 2: Pagination ────────────────────────────────────
class PaginatedResponse(BaseModel):
    items: list[Any]
    total: int
    page: int
    page_size: int


class WhatIfRequest(BaseModel):
    max_facilities: int | None = Field(default=None, ge=1, le=27)
    channel_shares: dict[str, float] | None = None
    carbon_price: float | None = Field(default=None, ge=0.0)
    harvest_peak_factor: float | None = Field(default=None, ge=1.0, le=3.0)


class AgentChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=1000)
    context: dict[str, Any] = Field(default_factory=dict)


class ExperimentRunRecord(BaseModel):
    run_id: str
    experiment_name: str
    experiment_type: str
    data_version: str
    status: str
    source_type: str
    source_path: str
    created_at: str | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    summary: str | None = None
    tags: list[str] = Field(default_factory=list)
