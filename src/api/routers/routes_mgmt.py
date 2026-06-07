"""Route plan management router — CRUD for route plans and stops.

All endpoints live under /api/v1/routes and auto-write operation logs.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from src.api.auth import UserInfo, get_current_user, require_role
from src.api.models import RoutePlanCreate, RoutePlanUpdate, RouteStopCreate

logger = logging.getLogger("okra.routes_router")

router = APIRouter(prefix="/routes", tags=["routes"])


# ── helpers ──────────────────────────────────────────────────────
def _audit(user_id: str, action: str, target_type: str, target_id: str, detail: dict[str, Any] | None = None) -> None:
    from src.api.routers.deps import write_audit_log

    write_audit_log(user_id=user_id, action=action, target_type=target_type, target_id=target_id, detail=detail)


def _shape_stop(row: dict[str, Any]) -> dict[str, Any]:
    shaped = dict(row)
    shaped.setdefault("arrival_time", shaped.get("planned_arrival"))
    shaped.setdefault("departure_time", shaped.get("planned_departure"))
    return shaped


def _shape_plan(row: dict[str, Any]) -> dict[str, Any]:
    shaped = dict(row)
    shaped.setdefault("distance_total", shaped.get("total_distance_km"))
    return shaped


# ── GET /api/v1/routes/plans — list all plans ───────────────────
@router.get("/plans")
async def list_route_plans(
    status: str = Query("", max_length=20),
    search: str = Query("", max_length=100),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    current_user: UserInfo = Depends(get_current_user),
):
    """List route plans with optional status filter."""
    from src.api.routers.deps import db_query

    try:
        conditions = []
        params: list[Any] = []
        if status:
            conditions.append("rp.status = %s")
            params.append(status)
        if search:
            conditions.append("(rp.name ILIKE %s OR rp.description ILIKE %s)")
            like = f"%{search}%"
            params.extend([like, like])

        where = " AND ".join(conditions) if conditions else "TRUE"
        offset = (page - 1) * page_size

        count_rows = db_query(f"SELECT COUNT(*) AS cnt FROM okra.route_plans rp WHERE {where}", tuple(params))
        total = count_rows[0]["cnt"] if count_rows else 0

        rows = db_query(
            f"SELECT rp.*, (SELECT COUNT(*) FROM okra.route_stops rs WHERE rs.route_plan_id = rp.id) AS stop_count "
            f"FROM okra.route_plans rp WHERE {where} ORDER BY rp.updated_at DESC LIMIT %s OFFSET %s",
            tuple(params) + (page_size, offset),
        )
        items = [_shape_plan(dict(row)) for row in rows]
        for item in items:
            stops = db_query(
                """
                SELECT rs.*, n.name AS node_name
                FROM okra.route_stops rs
                LEFT JOIN okra.nodes n ON n.node_id = rs.node_id
                WHERE rs.route_plan_id = %s
                ORDER BY rs.stop_order
                """,
                (item["id"],),
            )
            item["stops"] = [_shape_stop(dict(stop)) for stop in stops]
        return {"items": items, "total": total, "page": page, "page_size": page_size}
    except Exception as exc:
        logger.error("Failed to list route plans: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to list route plans")


# ── POST /api/v1/routes/plans — create plan ─────────────────────
@router.post("/plans", status_code=201)
async def create_route_plan(
    req: RoutePlanCreate,
    current_user: UserInfo = Depends(require_role("analyst")),
):
    """Create a new route plan (admin/analyst only)."""
    from src.api.routers.deps import db_execute_returning

    try:
        plan_id = str(uuid.uuid4())
        row = db_execute_returning(
            """
            INSERT INTO okra.route_plans (id, name, description, vehicle_type, created_by)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING *
            """,
            (plan_id, req.name, req.description, req.vehicle_type, current_user.user_id),
        )
        _audit(current_user.user_id, "create_route_plan", "route_plan", plan_id, {"name": req.name})
        return _shape_plan(row or {})
    except Exception as exc:
        logger.error("Failed to create route plan: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to create route plan")


# ── PUT /api/v1/routes/plans/{id} — update plan ─────────────────
@router.patch("/plans/{plan_id}")
@router.put("/plans/{plan_id}")
async def update_route_plan(
    plan_id: str = Path(...),
    req: RoutePlanUpdate | None = None,
    current_user: UserInfo = Depends(require_role("analyst")),
):
    """Update a route plan (admin/analyst only)."""
    from src.api.routers.deps import db_execute_returning, db_query_one

    # existing check
    existing = db_query_one("SELECT * FROM okra.route_plans WHERE id = %s", (plan_id,))
    if not existing:
        raise HTTPException(status_code=404, detail="Route plan not found")

    updates = {}
    if req is not None:
        for field in ("name", "description", "status", "vehicle_type"):
            value = getattr(req, field, None)
            if value is not None:
                updates[field] = value

    if not updates:
        return _shape_plan(existing)

    set_clause = ", ".join(f"{k} = %s" for k in updates)
    set_clause += ", updated_at = NOW()"
    values = list(updates.values()) + [plan_id]

    try:
        row = db_execute_returning(
            f"UPDATE okra.route_plans SET {set_clause} WHERE id = %s RETURNING *",
            tuple(values),
        )
        _audit(current_user.user_id, "update_route_plan", "route_plan", plan_id, {"changes": list(updates.keys())})
        return _shape_plan(row or existing)
    except Exception as exc:
        logger.error("Failed to update route plan %s: %s", plan_id, exc)
        raise HTTPException(status_code=500, detail="Failed to update route plan")


# ── DELETE /api/v1/routes/plans/{id} — delete plan ──────────────
@router.delete("/plans/{plan_id}")
async def delete_route_plan(
    plan_id: str = Path(...),
    current_user: UserInfo = Depends(require_role("admin")),
):
    """Delete a route plan and its stops (admin only)."""
    from src.api.routers.deps import db_execute, db_query_one

    existing = db_query_one("SELECT id FROM okra.route_plans WHERE id = %s", (plan_id,))
    if not existing:
        raise HTTPException(status_code=404, detail="Route plan not found")

    try:
        db_execute("DELETE FROM okra.route_plans WHERE id = %s", (plan_id,))
        _audit(current_user.user_id, "delete_route_plan", "route_plan", plan_id)
        return {"message": "Route plan deleted", "plan_id": plan_id}
    except Exception as exc:
        logger.error("Failed to delete route plan %s: %s", plan_id, exc)
        raise HTTPException(status_code=500, detail="Failed to delete route plan")


# ── GET /api/v1/routes/plans/{id}/stops — list stops ────────────
@router.get("/plans/{plan_id}/stops")
async def list_route_stops(
    plan_id: str = Path(...),
    current_user: UserInfo = Depends(get_current_user),
):
    """List all stops for a route plan, ordered by stop_order."""
    from src.api.routers.deps import db_query, db_query_one

    plan = db_query_one("SELECT id FROM okra.route_plans WHERE id = %s", (plan_id,))
    if not plan:
        raise HTTPException(status_code=404, detail="Route plan not found")

    try:
        rows = db_query(
            """
            SELECT rs.*, n.name AS node_name
            FROM okra.route_stops rs
            LEFT JOIN okra.nodes n ON n.node_id = rs.node_id
            WHERE rs.route_plan_id = %s
            ORDER BY rs.stop_order
            """,
            (plan_id,),
        )
        return {"items": [_shape_stop(dict(row)) for row in rows], "count": len(rows)}
    except Exception as exc:
        logger.error("Failed to list route stops: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to list route stops")


# ── POST /api/v1/routes/plans/{id}/stops — add stop ─────────────
@router.post("/plans/{plan_id}/stops", status_code=201)
async def add_route_stop(
    plan_id: str = Path(...),
    req: RouteStopCreate | None = None,
    current_user: UserInfo = Depends(require_role("analyst")),
):
    """Add a stop to a route plan (admin/analyst only)."""
    from src.api.routers.deps import db_execute_returning, db_query_one

    plan = db_query_one("SELECT id FROM okra.route_plans WHERE id = %s", (plan_id,))
    if not plan:
        raise HTTPException(status_code=404, detail="Route plan not found")
    if req is None:
        raise HTTPException(status_code=400, detail="Missing route stop payload")

    try:
        stop_id = str(uuid.uuid4())
        arrival = req.planned_arrival or None
        departure = req.planned_departure or None

        row = db_execute_returning(
            """
            INSERT INTO okra.route_stops (id, route_plan_id, stop_order, node_id, action,
                                           planned_arrival, planned_departure, notes)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (stop_id, plan_id, req.stop_order, req.node_id, req.action, arrival, departure, req.notes),
        )
        _audit(
            current_user.user_id,
            "add_route_stop",
            "route_stop",
            stop_id,
            {"plan_id": plan_id, "node_id": req.node_id, "stop_order": req.stop_order},
        )
        return _shape_stop(row or {})
    except Exception as exc:
        error_str = str(exc)
        if "foreign key" in error_str.lower():
            missing_node = req.node_id if req else ""
            raise HTTPException(status_code=400, detail=f"Node '{missing_node}' does not exist")
        logger.error("Failed to add route stop: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to add route stop")


@router.delete("/plans/{plan_id}/stops/{stop_id}")
async def delete_route_stop(
    plan_id: str = Path(...),
    stop_id: str = Path(...),
    current_user: UserInfo = Depends(require_role("analyst")),
):
    """Delete a stop from a route plan (admin/analyst only)."""
    from src.api.routers.deps import db_execute, db_query_one

    existing = db_query_one(
        "SELECT id FROM okra.route_stops WHERE id = %s AND route_plan_id = %s",
        (stop_id, plan_id),
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Route stop not found")

    try:
        db_execute("DELETE FROM okra.route_stops WHERE id = %s AND route_plan_id = %s", (stop_id, plan_id))
        _audit(current_user.user_id, "delete_route_stop", "route_stop", stop_id, {"plan_id": plan_id})
        return {"message": "Route stop deleted", "plan_id": plan_id, "stop_id": stop_id}
    except Exception as exc:
        logger.error("Failed to delete route stop %s: %s", stop_id, exc)
        raise HTTPException(status_code=500, detail="Failed to delete route stop")
