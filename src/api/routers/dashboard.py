"""Dashboard router — thin proxies over the existing main.py helpers.

Existing bootstrap and summary routes in main.py remain intact.
This file provides the v1-prefixed dashboard endpoints as a starting
point for future migration; when ready, the old main.py routes can be
pointed at these functions instead.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends

from src.api.auth import UserInfo, get_current_user

logger = logging.getLogger("okra.dashboard_router")

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


# ── GET /api/v1/dashboard/bootstrap ──────────────────────────────
@router.get("/bootstrap")
async def dashboard_bootstrap_v1(current_user: UserInfo = Depends(get_current_user)) -> dict[str, Any]:
    """
    Aggregated bootstrap payload for the MIS front-end.

    Delegates to the existing ``dashboard_bootstrap`` function in main.py
    so we do not duplicate logic.  When main.py is fully modularised, this
    handler can be moved to a standalone file.
    """
    try:
        # Import at runtime to avoid circular imports
        from src.api.main import dashboard_bootstrap as _raw_bootstrap

        # _raw_bootstrap is a sync function (not async)
        if callable(_raw_bootstrap):
            # It's defined with @app.get and returns a dict directly
            # We call it directly
            result = _raw_bootstrap()
            return result
    except Exception as exc:
        logger.warning("dashboard_bootstrap delegation failed: %s", exc)

    return {
        "status": "partial",
        "note": "Full bootstrap requires main.py dashboard helpers to be available.",
    }


# ── GET /api/v1/dashboard/summary ───────────────────────────────
@router.get("/summary")
async def dashboard_summary_v1(current_user: UserInfo = Depends(get_current_user)) -> dict[str, Any]:
    """Project summary overview for the dashboard."""
    try:
        from src.api.main import summary as _summary

        return _summary()
    except Exception as exc:
        logger.warning("summary delegation failed: %s", exc)
        return {"status": "partial", "note": str(exc)}


# ── GET /api/v1/dashboard/experiments ────────────────────────────
@router.get("/experiments")
async def dashboard_experiments_v1(current_user: UserInfo = Depends(get_current_user)) -> dict[str, Any]:
    """List experiments for the dashboard."""
    try:
        from src.api.main import list_experiments

        return list_experiments()
    except Exception as exc:
        logger.warning("experiments delegation failed: %s", exc)
        return {"status": "partial", "note": str(exc)}


# ── GET /api/v1/dashboard/storages ──────────────────────────────
@router.get("/storages")
async def dashboard_storages_v1(current_user: UserInfo = Depends(get_current_user)) -> dict[str, Any]:
    """Storage facilities summary for the dashboard."""
    try:
        from src.api.main import get_storages

        return get_storages()
    except Exception as exc:
        logger.warning("storages delegation failed: %s", exc)
        return {"status": "partial", "note": str(exc)}
