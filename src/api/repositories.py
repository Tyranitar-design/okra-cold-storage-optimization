"""Database-first repositories with file-mode friendly failure semantics."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

from src.api.db import get_database_url, get_psycopg, is_database_enabled, normalize_database_url


class RepositoryUnavailable(RuntimeError):
    """Raised when database-backed reads are not available in this environment."""


def _ensure_database_ready() -> None:
    if not is_database_enabled():
        raise RepositoryUnavailable("OKRA_DATABASE_URL is not configured.")


@contextmanager
def db_cursor() -> Iterator[Any]:
    _ensure_database_ready()
    try:
        psycopg, dict_row, _ConnectionPool = get_psycopg()
    except ImportError as exc:
        raise RepositoryUnavailable("psycopg is not installed.") from exc

    database_url = normalize_database_url(get_database_url())
    try:
        with psycopg.connect(database_url, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                yield cur
    except Exception as exc:
        raise RepositoryUnavailable(f"database query failed: {exc}") from exc


def _fetch_all(query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    with db_cursor() as cur:
        cur.execute(query, params)
        return [dict(row) for row in cur.fetchall()]


def _fetch_one(query: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    with db_cursor() as cur:
        cur.execute(query, params)
        row = cur.fetchone()
        return dict(row) if row else None


def list_evidence_sources_from_db(limit: int = 50) -> list[dict[str, Any]]:
    return _fetch_all(
        """
        select
            source_id,
            source_name,
            source_type,
            evidence_level,
            file_path_or_url,
            access_date::text as access_date,
            license_or_permission,
            variables,
            preprocessing,
            limitations,
            used_in
        from okra.data_sources
        order by source_id
        limit %s
        """,
        (limit,),
    )


def count_evidence_sources_from_db() -> int:
    row = _fetch_one("select count(*)::int as count from okra.data_sources")
    return int(row["count"]) if row else 0


def get_evidence_source_from_db(source_id: str) -> dict[str, Any] | None:
    return _fetch_one(
        """
        select
            source_id,
            source_name,
            source_type,
            evidence_level,
            file_path_or_url,
            access_date::text as access_date,
            license_or_permission,
            variables,
            preprocessing,
            limitations,
            used_in
        from okra.data_sources
        where source_id = %s
        """,
        (source_id,),
    )


def list_candidate_storages_from_db() -> list[dict[str, Any]]:
    return _fetch_all(
        """
        select
            n.node_id,
            n.name,
            n.lat::float as lat,
            n.lon::float as lon,
            true as candidate,
            n.okra_production_ton::float as okra_production_ton
        from okra.nodes n
        join okra.candidate_sites c on c.node_id = n.node_id
        order by n.node_id
        """
    )


def get_storage_detail_from_db(storage_id: str) -> dict[str, Any] | None:
    return _fetch_one(
        """
        select
            node_id,
            name,
            level,
            level_name,
            lat::float as lat,
            lon::float as lon,
            okra_production_ton::float as okra_production_ton,
            is_candidate,
            population::float as population,
            road_access,
            source_id
        from okra.nodes
        where node_id = %s
        """,
        (storage_id,),
    )


def list_map_features_from_db() -> list[dict[str, Any]]:
    rows = _fetch_all(
        """
        select
            node_id,
            name,
            lat::float as lat,
            lon::float as lon,
            is_candidate,
            okra_production_ton::float as okra_production_ton
        from okra.nodes
        order by node_id
        """
    )
    return [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [row["lon"], row["lat"]]},
            "properties": {
                "node_id": row["node_id"],
                "name": row["name"],
                "candidate": bool(row["is_candidate"]),
                "okra_production_ton": row["okra_production_ton"],
            },
        }
        for row in rows
    ]


def list_ai_benders_cut_scores_from_db() -> list[dict[str, Any]]:
    return _fetch_all(
        """
        select
            regexp_replace(r.run_key, '^ai_benders_', '') as case_id,
            s.cut_id,
            s.iter_no,
            s.score::float as score,
            s.selected,
            s.features_json,
            s.policy_name
        from okra.ai_benders_cut_scores s
        join okra.optimization_runs r on r.run_id = s.run_id
        order by r.run_key, s.iter_no, s.cut_id
        """
    )
