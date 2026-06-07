"""Authentication router — POST /login, GET /me, POST /refresh.

Falls back to the legacy hardcoded user dictionary when the database
is unavailable, so both v1 and v2 auth paths continue to work.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials

from src.api.auth import (
    SECRET_KEY,
    ALGORITHM,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    API_KEYS,
    UserInfo,
    get_current_user,
    security,
    api_key_header,
)
from src.api.models import LoginRequest, TokenResponse

logger = logging.getLogger("okra.auth_router")

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("JWT_REFRESH_EXPIRE_DAYS", "30"))


# ── helpers ──────────────────────────────────────────────────────
def _create_refresh_token(user_id: str) -> str:
    import jwt as _jwt

    expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    return _jwt.encode({"sub": user_id, "type": "refresh", "exp": expire}, SECRET_KEY, algorithm=ALGORITHM)


def _verify_refresh_token(token: str) -> str | None:
    """Return user_id from a valid refresh token, or None."""
    import jwt as _jwt

    try:
        payload = _jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "refresh":
            return None
        return payload.get("sub")
    except Exception:
        return None


async def _authenticate_from_db(username: str, password: str) -> dict[str, Any] | None:
    """Query okra.users for login; returns dict with hashed_password/role/display_name or None."""
    try:
        from src.api.routers.deps import db_query_one

        row = db_query_one(
            "SELECT username, hashed_password, display_name, role FROM okra.users "
            "WHERE username = %s AND is_active = TRUE",
            (username,),
        )
        if row is None:
            return None
        return dict(row)
    except Exception as exc:
        logger.debug("DB auth lookup failed (will fallback): %s", exc)
        return None


async def _authenticate_user(username: str, password: str) -> dict[str, Any] | None:
    """Authenticate against DB first, then legacy in-memory dict."""
    # --- DB path ---
    user_row = await _authenticate_from_db(username, password)
    if user_row is not None:
        from src.api.routers.deps import verify_password

        if verify_password(password, user_row["hashed_password"]):
            return {
                "user_id": user_row["username"],
                "display_name": user_row.get("display_name", username),
                "role": user_row["role"],
            }
        return None

    # --- Fallback to legacy hardcoded dict ---
    from src.api.auth import USERS_DB

    user = USERS_DB.get(username)
    if user and user["password"] == password:
        return {"user_id": username, "display_name": user["username"], "role": user["role"]}
    return None


# ── POST /api/v1/auth/login ─────────────────────────────────────
@router.post("/login", response_model=TokenResponse)
async def login_v1(req: LoginRequest):
    """Authenticate and return access + refresh tokens."""
    user = await _authenticate_user(req.username, req.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"err_code": "ERR_AUTH_001", "message": "Invalid username or password"},
        )

    from src.api.auth import create_access_token

    token = create_access_token(user["user_id"], user["role"])
    refresh = _create_refresh_token(user["user_id"])

    return TokenResponse(
        access_token=token,
        refresh_token=refresh,
        token_type="bearer",
        user_id=user["user_id"],
        role=user["role"],
    )


# ── GET /api/v1/auth/me ─────────────────────────────────────────
@router.get("/me")
async def me_v1(current_user: UserInfo = Depends(get_current_user)):
    """Return the profile of the currently authenticated user."""
    # If the user exists in DB, enrich with display_name.
    try:
        from src.api.routers.deps import db_query_one

        row = db_query_one(
            "SELECT display_name FROM okra.users WHERE username = %s",
            (current_user.user_id,),
        )
        if row:
            return {
                "user_id": current_user.user_id,
                "username": current_user.username,
                "display_name": row["display_name"],
                "role": current_user.role,
            }
    except Exception:
        pass
    return current_user


# ── POST /api/v1/auth/refresh ───────────────────────────────────
@router.post("/refresh")
async def refresh_token_v1(refresh_token: str = Query(...)):
    """Issue a new access token using a valid refresh token."""
    user_id = _verify_refresh_token(refresh_token)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"err_code": "ERR_AUTH_002", "message": "Invalid or expired refresh token"},
        )

    # Determine role from DB or fallback dict.
    role = "viewer"
    try:
        from src.api.routers.deps import db_query_one

        row = db_query_one(
            "SELECT role FROM okra.users WHERE username = %s AND is_active = TRUE",
            (user_id,),
        )
        if row:
            role = row["role"]
    except Exception:
        from src.api.auth import USERS_DB

        legacy = USERS_DB.get(user_id, {})
        role = legacy.get("role", "viewer")

    from src.api.auth import create_access_token

    new_access = create_access_token(user_id, role)
    return TokenResponse(
        access_token=new_access,
        refresh_token=refresh_token,
        token_type="bearer",
        user_id=user_id,
        role=role,
    )
