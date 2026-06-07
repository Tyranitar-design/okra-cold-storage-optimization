"""Database configuration helpers for the okra cold storage API."""

from __future__ import annotations

import os
import time
import logging
import atexit
from dataclasses import dataclass
from urllib.parse import urlparse
from typing import Any

# ── Slow query logging ──────────────────────────────────────────
SLOW_QUERY_MS = int(os.getenv("SLOW_QUERY_MS", "500"))
_db_logger = logging.getLogger("db.slow_query")
_handler = logging.StreamHandler()
_handler.setFormatter(logging.Formatter("%(asctime)s SLOW_QUERY %(message)s"))
_db_logger.addHandler(_handler)
_db_logger.setLevel(logging.WARNING)


@dataclass(frozen=True)
class DatabaseConfig:
    database_url: str
    dialect: str
    has_credentials: bool
    host: str
    port: int | None
    database_name: str


def get_database_url() -> str:
    return os.environ.get("OKRA_DATABASE_URL", "").strip()


def normalize_database_url(database_url: str) -> str:
    return database_url.replace("postgresql+psycopg://", "postgresql://", 1)


def get_database_config() -> DatabaseConfig:
    database_url = get_database_url()
    parsed = urlparse(database_url)
    host = parsed.hostname or "localhost"
    port = parsed.port
    database_name = parsed.path.lstrip("/") or ""
    return DatabaseConfig(
        database_url=database_url,
        dialect=parsed.scheme,
        has_credentials=bool(parsed.username or parsed.password),
        host=host,
        port=port,
        database_name=database_name,
    )


def is_database_enabled() -> bool:
    url = get_database_url()
    return bool(url)


def psycopg_available() -> bool:
    try:
        import psycopg  # noqa: F401
    except ImportError:
        return False
    return True


def get_psycopg() -> Any:
    import psycopg
    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool

    return psycopg, dict_row, ConnectionPool


# ── Connection pool (singleton) ──────────────────────────────────
_pool: Any = None

def get_pool(min_size: int = 2, max_size: int = 8) -> Any:
    global _pool
    if _pool is None:
        _psycopg, dict_row, ConnectionPool = get_psycopg()
        url = get_database_url()
        if url:
            _pool = ConnectionPool(
                normalize_database_url(url),
                min_size=min_size,
                max_size=max_size,
                open=False,
                kwargs={"row_factory": dict_row},
            )
            _pool.open()
    return _pool


def close_pool():
    global _pool
    if _pool:
        _pool.close()
        _pool = None


atexit.register(close_pool)


def probe_database_connection(timeout_seconds: int = 2) -> dict[str, object]:
    cfg = get_database_config()
    enabled = is_database_enabled()
    driver_available = psycopg_available()
    probe: dict[str, object] = {
        "probe_attempted": False,
        "probe_ok": False,
        "probe_error": None,
        "probe_current_database": None,
        "probe_current_user": None,
        "probe_elapsed_ms": None,
    }
    if not enabled:
        probe["probe_error"] = "OKRA_DATABASE_URL is not configured."
        return probe
    if not driver_available:
        probe["probe_error"] = "psycopg is not installed."
        return probe

    psycopg, dict_row, _ConnectionPool = get_psycopg()
    database_url = normalize_database_url(cfg.database_url)
    started = time.perf_counter()
    probe["probe_attempted"] = True
    try:
        with psycopg.connect(database_url, row_factory=dict_row, connect_timeout=timeout_seconds) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "select current_database() as current_database, current_user as current_user"
                )
                row = cur.fetchone() or {}
        probe["probe_ok"] = True
        probe["probe_current_database"] = row.get("current_database")
        probe["probe_current_user"] = row.get("current_user")
    except Exception as exc:
        probe["probe_error"] = str(exc)
    finally:
        probe["probe_elapsed_ms"] = round((time.perf_counter() - started) * 1000.0, 2)
    return probe


def database_status_payload() -> dict[str, object]:
    cfg = get_database_config()
    enabled = is_database_enabled()
    driver_available = psycopg_available()
    probe = probe_database_connection(timeout_seconds=2)
    query_ready = bool(enabled and driver_available and probe.get("probe_ok"))
    return {
        "enabled": enabled,
        "dialect": cfg.dialect,
        "host": cfg.host,
        "port": cfg.port,
        "database_name": cfg.database_name,
        "has_credentials": cfg.has_credentials,
        "database_url_configured": enabled,
        "driver": "psycopg",
        "driver_available": driver_available,
        "probe_attempted": probe.get("probe_attempted"),
        "probe_ok": probe.get("probe_ok"),
        "probe_error": probe.get("probe_error"),
        "probe_current_database": probe.get("probe_current_database"),
        "probe_current_user": probe.get("probe_current_user"),
        "probe_elapsed_ms": probe.get("probe_elapsed_ms"),
        "query_ready": query_ready,
        "fallback_reason": None if query_ready else probe.get("probe_error"),
    }
