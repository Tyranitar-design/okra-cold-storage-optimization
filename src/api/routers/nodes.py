"""Nodes CRUD router — list, create, update, delete cold-storage nodes.

All endpoints live under /api/v1/nodes and require appropriate roles.
"""
from __future__ import annotations

import logging
import csv
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.api.auth import UserInfo, get_current_user, require_role
from src.api.models import NodeCreate, NodeUpdate, PaginatedResponse

logger = logging.getLogger("okra.nodes_router")

router = APIRouter(prefix="/nodes", tags=["nodes"])
PROJECT_ROOT = Path(__file__).resolve().parents[3]
NODES_CSV_PATH = PROJECT_ROOT / "data" / "nodes.csv"


# ── helpers ──────────────────────────────────────────────────────
def _shape_node(row: dict[str, Any] | None) -> dict[str, Any] | None:
    """Expose DB node fields plus UI-compatible aliases."""
    if row is None:
        return None
    shaped = dict(row)
    shaped.setdefault("id", shaped.get("node_id"))
    shaped.setdefault("latitude", shaped.get("lat"))
    shaped.setdefault("longitude", shaped.get("lon"))
    shaped.setdefault("type", shaped.get("level_name") or str(shaped.get("level", "")))
    shaped.setdefault("capacity", shaped.get("okra_production_ton"))
    shaped.setdefault("active", True)
    return shaped


def _query_nodes_db(
    search: str = "",
    type_filter: str = "",
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    """Query okra.nodes with optional filters and pagination."""
    from src.api.routers.deps import db_query

    conditions = []
    params: list[Any] = []

    if search:
        conditions.append("(name ILIKE %s OR node_id ILIKE %s)")
        like = f"%{search}%"
        params.extend([like, like])

    if type_filter:
        conditions.append("level_name = %s")
        params.append(type_filter)

    where_clause = " AND ".join(conditions) if conditions else "TRUE"

    # Count
    count_rows = db_query(
        f"SELECT COUNT(*) AS cnt FROM okra.nodes WHERE {where_clause}",
        tuple(params),
    )
    total = count_rows[0]["cnt"] if count_rows else 0

    # Data with pagination
    offset = (page - 1) * page_size
    order = "ORDER BY level, name"
    rows = db_query(
        f"SELECT * FROM okra.nodes WHERE {where_clause} {order} LIMIT %s OFFSET %s",
        tuple(params) + (page_size, offset),
    )

    return {"items": [_shape_node(dict(row)) for row in rows], "total": total, "page": page, "page_size": page_size}


def _to_bool(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _query_nodes_file(
    search: str = "",
    type_filter: str = "",
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    """Read node records from data/nodes.csv for cloud/file fallback demos."""
    if not NODES_CSV_PATH.exists():
        return {"items": [], "total": 0, "page": page, "page_size": page_size}

    with NODES_CSV_PATH.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    search_norm = search.strip().lower()
    type_norm = type_filter.strip()
    shaped_rows: list[dict[str, Any]] = []
    for row in rows:
        node = {
            "node_id": row.get("node_id", ""),
            "name": row.get("name", ""),
            "level": _to_int(row.get("level")),
            "level_name": row.get("level_name", ""),
            "lat": _to_float(row.get("lat")),
            "lon": _to_float(row.get("lon")),
            "okra_production_ton": _to_float(row.get("okra_production_ton")),
            "is_candidate": _to_bool(row.get("is_candidate")),
            "population": _to_float(row.get("population")),
            "road_access": _to_bool(row.get("road_access")),
            "source_backend": "file",
        }
        if search_norm and search_norm not in f"{node['node_id']} {node['name']}".lower():
            continue
        if type_norm and node["level_name"] != type_norm:
            continue
        shaped_rows.append(_shape_node(node) or node)

    shaped_rows.sort(key=lambda item: (item.get("level", 0), str(item.get("name", ""))))
    total = len(shaped_rows)
    offset = (page - 1) * page_size
    return {
        "items": shaped_rows[offset : offset + page_size],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def _get_node_or_404(node_id: str) -> dict[str, Any]:
    """Fetch a single node by ID or raise 404."""
    from src.api.routers.deps import db_query_one

    row = db_query_one("SELECT * FROM okra.nodes WHERE node_id = %s", (node_id,))
    if not row:
        raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found")
    shaped = _shape_node(dict(row))
    if shaped is None:
        raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found")
    return shaped


def _audit_node(user_id: str, action: str, node_id: str, detail: dict[str, Any] | None = None) -> None:
    from src.api.routers.deps import write_audit_log

    write_audit_log(user_id=user_id, action=action, target_type="node", target_id=node_id, detail=detail)


# ── GET /api/v1/nodes/types — cold storage type list ────────────
@router.get("/types")
async def get_node_types():
    """Return distinct cold storage type codes/names."""
    try:
        from src.api.routers.deps import db_query

        rows = db_query("SELECT type_code, type_name FROM okra.cold_storage_types ORDER BY type_code")
        return {"items": rows, "count": len(rows)}
    except Exception:
        # Fallback static list
        return {
            "items": [
                {"type_code": "cold_storage", "type_name": "冷藏库"},
                {"type_code": "precool", "type_name": "预冷库"},
                {"type_code": "freezer", "type_name": "冷冻库"},
            ],
            "count": 3,
        }


# ── GET /api/v1/nodes — paginated list ──────────────────────────
@router.get("")
async def list_nodes(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    search: str = Query("", max_length=100),
    type_: str = Query("", alias="type", max_length=50),
) -> PaginatedResponse:
    """List cold-storage nodes with optional search and type filter."""
    try:
        result = _query_nodes_db(search=search, type_filter=type_, page=page, page_size=page_size)
    except Exception as exc:
        logger.warning("Failed to query nodes from database, using file fallback: %s", exc)
        result = _query_nodes_file(search=search, type_filter=type_, page=page, page_size=page_size)
    return PaginatedResponse(
        items=result["items"],
        total=result["total"],
        page=result["page"],
        page_size=result["page_size"],
    )


# ── POST /api/v1/nodes — create ─────────────────────────────────
@router.post("", status_code=201)
async def create_node(
    req: NodeCreate,
    current_user: UserInfo = Depends(require_role("analyst")),
):
    """Create a new cold-storage node (admin/analyst only)."""
    node_id = req.node_id or f"N{uuid.uuid4().hex[:8].upper()}"
    try:
        from src.api.routers.deps import db_execute_returning

        row = db_execute_returning(
            """
            INSERT INTO okra.nodes (node_id, name, level, lat, lon, okra_production_ton, is_candidate, source_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING node_id, name, level, lat, lon, okra_production_ton, is_candidate, created_at
            """,
            (
                node_id,
                req.name,
                req.level,
                req.lat,
                req.lon,
                req.okra_production_ton,
                req.is_candidate,
                req.source_id,
            ),
        )
        _audit_node(current_user.user_id, "create_node", node_id)
        return _shape_node(row)
    except Exception as exc:
        error_str = str(exc)
        if "duplicate" in error_str.lower() or "unique" in error_str.lower():
            raise HTTPException(status_code=409, detail=f"Node '{node_id}' already exists")
        logger.error("Failed to create node: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to create node")


# ── PUT /api/v1/nodes/{id} — update ─────────────────────────────
@router.put("/{node_id}")
async def update_node(
    node_id: str,
    req: NodeUpdate,
    current_user: UserInfo = Depends(require_role("analyst")),
):
    """Update an existing node (admin/analyst only)."""
    existing = _get_node_or_404(node_id)

    updates = {}
    for field in ("name", "level", "lat", "lon", "okra_production_ton", "is_candidate", "source_id"):
        val = getattr(req, field, None)
        if val is not None:
            updates[field] = val

    if not updates:
        return existing

    set_clause = ", ".join(f"{k} = %s" for k in updates)
    values = list(updates.values()) + [node_id]

    try:
        from src.api.routers.deps import db_execute_returning

        row = db_execute_returning(
            f"UPDATE okra.nodes SET {set_clause}, updated_at = NOW() WHERE node_id = %s RETURNING *",
            tuple(values),
        )
        _audit_node(current_user.user_id, "update_node", node_id, {"changes": list(updates.keys())})
        return _shape_node(row) or existing
    except Exception as exc:
        logger.error("Failed to update node %s: %s", node_id, exc)
        raise HTTPException(status_code=500, detail="Failed to update node")


# ── DELETE /api/v1/nodes/{id} — soft delete ─────────────────────
@router.delete("/{node_id}")
async def delete_node(
    node_id: str,
    current_user: UserInfo = Depends(require_role("admin")),
):
    """Soft-delete a node (admin only)."""
    _get_node_or_404(node_id)  # ensure exists

    try:
        from src.api.routers.deps import db_execute

        db_execute(
            "DELETE FROM okra.candidate_sites WHERE node_id = %s", (node_id,)
        )
        db_execute("DELETE FROM okra.nodes WHERE node_id = %s", (node_id,))
        _audit_node(current_user.user_id, "delete_node", node_id)
        return {"message": f"Node '{node_id}' deleted", "node_id": node_id}
    except Exception as exc:
        logger.error("Failed to delete node %s: %s", node_id, exc)
        raise HTTPException(status_code=500, detail="Failed to delete node")
