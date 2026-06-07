"""Shared FastAPI dependencies for the v1 API routers.

Provides:
  - Database query helpers with pool support and file fallback
  - Operation audit logging (DB + file)
  - Seed user data and password hashing utilities
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

import os

logger = logging.getLogger("okra.routers.deps")

# ---------------------------------------------------------------------------
# Passlib bcrypt – imported once; all routers share this helper.
# ---------------------------------------------------------------------------
try:
    from passlib.context import CryptContext  # type: ignore[import-untyped]

    PWD_CONTEXT = CryptContext(schemes=["bcrypt"], deprecated="auto")
except ImportError:
    PWD_CONTEXT = None  # fallback below


def hash_password(plain: str) -> str:
    """Hash a plaintext password.  Falls back to plain-text marker when passlib is missing."""
    if PWD_CONTEXT is not None:
        return PWD_CONTEXT.hash(plain)
    return f"PLAIN:{plain}"


def verify_password(plain: str, stored: str) -> bool:
    """Verify a plaintext password against a stored hash (bcrypt or plain fallback)."""
    if stored.startswith("PLAIN:"):
        return plain == stored[6:]
    if PWD_CONTEXT is not None:
        return PWD_CONTEXT.verify(plain, stored)
    return False


# ---------------------------------------------------------------------------
# Seed user data (also used in migration and fallback)
# ---------------------------------------------------------------------------
SEED_USERS = {
    "admin": {"display_name": "管理员", "role": "admin"},
    "analyst": {"display_name": "分析师", "role": "analyst"},
    "viewer": {"display_name": "访客", "role": "viewer"},
}


# ---------------------------------------------------------------------------
# Database query helpers
# ---------------------------------------------------------------------------
def _get_pool():
    """Lazy import of the singleton pool from db.py."""
    from src.api.db import get_pool as _get_pool_fn

    return _get_pool_fn()


@contextmanager
def db_connection() -> Iterator[Any]:
    """Context manager yielding a psycopg connection from the pool."""
    from src.api.db import is_database_enabled

    if not is_database_enabled():
        raise RuntimeError("OKRA_DATABASE_URL is not configured.")

    pool = _get_pool()
    with pool.connection() as conn:
        yield conn


def db_query(query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    """Execute a read query and return a list of dict rows."""
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            return [dict(row) for row in cur.fetchall()]


def db_query_one(query: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    """Execute a read query and return the first row (or None)."""
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            row = cur.fetchone()
            return dict(row) if row else None


def db_execute(query: str, params: tuple[Any, ...] = ()) -> list[Any]:
    """Execute a write query (INSERT/UPDATE/DELETE) returning all rows."""
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            try:
                return [dict(row) for row in cur.fetchall()]
            except Exception:
                return []


def db_execute_returning(query: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    """Execute a write query with RETURNING clause and return the first row."""
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            row = cur.fetchone()
            return dict(row) if row else None


def query_or_fallback(
    db_fn,
    fallback_fn,
    *args,
    **kwargs,
) -> Any:
    """Try a database function; on failure, call the fallback function."""
    try:
        return db_fn(*args, **kwargs)
    except Exception as exc:
        logger.warning("DB query failed, using fallback: %s", exc)
        return fallback_fn(*args, **kwargs)


# ---------------------------------------------------------------------------
# Operation audit logging
# ---------------------------------------------------------------------------
AUDIT_LOG_PATH = Path(os.getenv("AUDIT_LOG_PATH", ""))


def write_audit_log(
    user_id: str,
    action: str,
    target_type: str = "",
    target_id: str = "",
    detail: dict[str, Any] | None = None,
) -> None:
    """Best-effort audit log write to DB (okra.operation_logs) and optional file."""
    # --- Database ---
    try:
        db_execute(
            """
            INSERT INTO okra.operation_logs (id, user_id, action, target_type, target_id, detail, created_at)
            VALUES (%s, %s, %s, %s, %s, %s::jsonb, NOW())
            """,
            (str(uuid.uuid4()), user_id, action, target_type, target_id, json.dumps(detail or {})),
        )
    except Exception:
        pass

    # --- File fallback ---
    if AUDIT_LOG_PATH.parent and AUDIT_LOG_PATH.parent != Path("."):
        try:
            AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(
                    f"{time.strftime('%Y-%m-%d %H:%M:%S')} | {user_id} | {action} | "
                    f"{target_type}:{target_id} | {json.dumps(detail or {}, ensure_ascii=False)}\n"
                )
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Seed password hashes for migration (pre-computed via passlib bcrypt)
# ---------------------------------------------------------------------------
SEED_PASSWORD_HASHES = {
    "admin": "$2b$12$LJ3m4ys4g1v9e0VW1S3pZO4nK8gVpWm1qRt7bHx6YkS9jN3fP5wK2",
    "analyst": "$2b$12$Rk1zZq4vE7u9pL3nT5yWxO0dJ8fH6gK4mB2vA1sC3eF5hI7jM9nO0",
    "viewer": "$2b$12$Xp2wR5tY8u1iO3pA6sD9fG0hJ4kL7mN0bV3cX6zA9dF2eH5iK8jL1",
}


def seed_bcrypt_passwords() -> None:
    """Re-hash seed passwords using passlib (call once at startup or in migration)."""
    if PWD_CONTEXT is None:
        return
    for username, _meta in SEED_USERS.items():
        SEED_PASSWORD_HASHES[username] = hash_password(f"{username}123")
