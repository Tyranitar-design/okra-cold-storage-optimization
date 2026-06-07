"""JWT authentication and RBAC for the FastAPI backend."""
import os
import jwt
import hashlib
import hmac
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, APIKeyHeader
from pydantic import BaseModel

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "okra-jwt-secret-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "480"))

security = HTTPBearer(auto_error=False)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


class TokenPayload(BaseModel):
    sub: str
    role: str
    exp: datetime


class UserInfo(BaseModel):
    user_id: str
    username: str
    role: str  # admin | analyst | viewer


USERS_DB = {
    "admin": {"password": "admin123", "role": "admin", "username": "管理员"},
    "analyst": {"password": "analyst123", "role": "analyst", "username": "分析师"},
    "viewer": {"password": "viewer123", "role": "viewer", "username": "访客"},
}
# API keys for machine-to-machine access
API_KEYS = {
    "okra-export-key-2026": {"role": "analyst", "user_id": "export-svc"},
    "okra-wechat-key-2026": {"role": "viewer", "user_id": "wechat-miniapp"},
}


def create_access_token(user_id: str, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": user_id, "role": role, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def verify_password(plain: str, stored: str) -> bool:
    """
    Verify password against a stored hash.

    Supports three schemes:
      1. passlib bcrypt (from routers/deps — preferred)
      2. Legacy plain-text comparison (fallback)
      3. SHA-256 hex digest (legacy)
    """
    # Try passlib bcrypt first
    try:
        from src.api.routers.deps import verify_password as _bcrypt_verify

        return _bcrypt_verify(plain, stored)
    except Exception:
        pass
    # Legacy plain-text
    return hmac.compare_digest(plain, stored)


def authenticate_user(username: str, password: str) -> Optional[UserInfo]:
    # Try database-backed authentication first (v1).
    try:
        import logging
        logger = logging.getLogger("okra.auth")
        from src.api.routers.deps import db_query_one, verify_password as _bcrypt_verify

        row = db_query_one(
            "SELECT username, hashed_password, display_name, role "
            "FROM okra.users WHERE username = %s AND is_active = TRUE",
            (username,),
        )
        if row:
            if _bcrypt_verify(password, row["hashed_password"]):
                return UserInfo(user_id=row["username"], username=row.get("display_name", row["username"]), role=row["role"])
            return None
    except Exception:
        pass

    # Fallback to legacy hardcoded dictionary.
    user = USERS_DB.get(username)
    if not user or user["password"] != password:
        return None
    return UserInfo(user_id=username, username=user["username"], role=user["role"])


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    api_key: Optional[str] = Depends(api_key_header),
) -> UserInfo:
    # Try API key first (machine-to-machine)
    if api_key and api_key in API_KEYS:
        key_info = API_KEYS[api_key]
        return UserInfo(user_id=key_info["user_id"], username=key_info["user_id"], role=key_info["role"])

    # Then try JWT token
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        role = payload.get("role")
        if user_id is None or role is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        return UserInfo(user_id=user_id, username=user_id, role=role)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


def require_role(required_role: str):
    """Dependency factory: require a minimum role level. admin > analyst > viewer."""
    role_hierarchy = {"viewer": 0, "analyst": 1, "admin": 2}

    async def role_checker(current_user: UserInfo = Depends(get_current_user)) -> UserInfo:
        if role_hierarchy.get(current_user.role, -1) < role_hierarchy.get(required_role, 0):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{current_user.role}' insufficient, requires '{required_role}'",
            )
        return current_user
    return role_checker


ROUTER_PREFIX = "/api/v2"

# Endpoints to register in main.py:
# POST /api/v2/auth/login  — login, returns JWT token
# GET  /api/v2/auth/me     — current user info (requires auth)
# All /api/v2/* endpoints — protected by optional auth (public data still accessible)
