"""Build a database connectivity diagnosis report for the MIS evidence layer."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESULTS_ROOT = PROJECT_ROOT / "results"
SYSTEM_PG_HBA_PATH = Path("D:/PostgreSQL/data/pg_hba.conf")
LOCAL_PG_LOG_PATH = PROJECT_ROOT / "logs" / "local_postgres_55432.log"
LEGACY_LOCAL_PG_LOG_PATH = PROJECT_ROOT / "logs" / "local_postgres.log"
DATABASE_CONNECTIVITY_JSON_PATH = RESULTS_ROOT / "database_connectivity_report.json"
DATABASE_CONNECTIVITY_MD_PATH = RESULTS_ROOT / "database_connectivity_report.md"


def _read_tail(path: Path, max_chars: int = 2400) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    return text[-max_chars:]


def _contains_any(text: str, patterns: list[str]) -> bool:
    lowered = text.lower()
    return any(pattern.lower() in lowered for pattern in patterns)


def build_database_connectivity_report(db_status: Dict[str, Any]) -> Dict[str, Any]:
    """Create a safe report that explains current PostgreSQL connectivity.

    The report intentionally avoids returning a full database URL or passwords.
    It only records host, port, database name, booleans, and sanitized evidence.
    """

    system_hba = _read_tail(SYSTEM_PG_HBA_PATH)
    local_log = _read_tail(LOCAL_PG_LOG_PATH) or _read_tail(LEGACY_LOCAL_PG_LOG_PATH)
    system_requires_password = _contains_any(system_hba, ["scram-sha-256", "md5"])
    local_bind_denied = _contains_any(local_log, ["could not bind", "permission denied", "could not create any tcp/ip sockets"])
    auth_failed = _contains_any(str(db_status.get("probe_error") or ""), ["password", "authentication", "认证失败"])
    probe_ok = bool(db_status.get("probe_ok"))
    query_ready = bool(db_status.get("query_ready"))

    checks = [
        {
            "id": "driver_available",
            "name": "psycopg 驱动",
            "state": "ready" if db_status.get("driver_available") else "needs_attention",
            "detail": f"driver={db_status.get('driver')}, available={db_status.get('driver_available')}",
            "boundary": "Driver availability is necessary but not sufficient for live database connectivity.",
        },
        {
            "id": "system_postgres_probe",
            "name": "系统 PostgreSQL 探测",
            "state": "runtime_verified" if probe_ok else "needs_attention",
            "detail": (
                f"host={db_status.get('host')}, port={db_status.get('port')}, "
                f"database={db_status.get('database_name')}, probe_ok={probe_ok}"
            ),
            "boundary": "Only probe_ok=true proves that the configured role/database can be queried.",
        },
        {
            "id": "system_auth_policy",
            "name": "系统 PostgreSQL 认证策略",
            "state": "needs_credentials" if system_requires_password else "ready",
            "detail": f"pg_hba_password_auth={system_requires_password}",
            "boundary": "SCRAM/password auth requires a valid role password; scripts must not guess or bypass it.",
        },
        {
            "id": "project_local_postgres",
            "name": "项目本地 PostgreSQL 实例",
            "state": "blocked_by_local_bind" if local_bind_denied else "unknown",
            "detail": f"local_bind_denied={local_bind_denied}",
            "boundary": "Project-local PostgreSQL cannot be claimed ready until it can bind a local port and accept queries.",
        },
        {
            "id": "seed_apply_gate",
            "name": "真实写库门槛",
            "state": "runtime_verified" if query_ready else "blocked_until_probe_ok",
            "detail": f"query_ready={query_ready}, auth_failed={auth_failed}",
            "boundary": "`--apply --init-schema` should run only after query_ready=true on a known project database.",
        },
    ]

    ready_count = sum(1 for item in checks if item["state"] in {"ready", "runtime_verified"})
    return {
        "source_name": "database connectivity report",
        "result_paths": {
            "json": str(DATABASE_CONNECTIVITY_JSON_PATH),
            "md": str(DATABASE_CONNECTIVITY_MD_PATH),
        },
        "summary": {
            "check_count": len(checks),
            "ready_count": ready_count,
            "probe_ok": probe_ok,
            "query_ready": query_ready,
            "auth_failed": auth_failed,
            "system_requires_password": system_requires_password,
            "project_local_bind_denied": local_bind_denied,
            "can_apply_seed": bool(query_ready),
        },
        "safe_connection": {
            "dialect": db_status.get("dialect"),
            "host": db_status.get("host"),
            "port": db_status.get("port"),
            "database_name": db_status.get("database_name"),
            "has_credentials": db_status.get("has_credentials"),
            "database_url_configured": db_status.get("database_url_configured"),
        },
        "checks": checks,
        "next_actions": [
            "Provide a valid OKRA_DATABASE_URL for an existing project role/database, or create the role/database via a known PostgreSQL administrator account.",
            "After probe_ok=true, run seed preview, then `python scripts/seed_postgres_from_current_files.py --apply --init-schema`.",
            "Do not claim PostgreSQL-backed MIS until `/api/v1/db/probe` returns query_ready=true and repository endpoints report source_backend=database.",
        ],
        "research_boundary": (
            "This report diagnoses database connectivity without exposing passwords or changing PostgreSQL authentication rules. "
            "It records why current execution remains file-fallback instead of live PostgreSQL-backed MIS."
        ),
    }


def write_database_connectivity_report(report: Dict[str, Any], out_dir: Path | None = None) -> Dict[str, str]:
    destination = out_dir or RESULTS_ROOT
    destination.mkdir(parents=True, exist_ok=True)
    json_path = destination / "database_connectivity_report.json"
    md_path = destination / "database_connectivity_report.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(
        "\n".join(
            [
                "# Database Connectivity Report",
                "",
                "## Summary",
                "",
                *[f"- {key}: {value}" for key, value in report.get("summary", {}).items()],
                "",
                "## Checks",
                "",
                *[
                    f"- {item.get('id', '')}: state={item.get('state', '')}, detail={item.get('detail', '')}"
                    for item in report.get("checks", [])
                ],
                "",
                "## Next Actions",
                "",
                *[f"- {item}" for item in report.get("next_actions", [])],
                "",
                "## Boundary",
                "",
                str(report.get("research_boundary", "")),
                "",
            ]
        ),
        encoding="utf-8",
    )
    return {"json_path": str(json_path), "md_path": str(md_path)}
