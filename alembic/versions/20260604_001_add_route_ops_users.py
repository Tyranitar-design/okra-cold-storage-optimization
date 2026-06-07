"""Add MIS route, audit, and user tables.

Revision ID: 20260604_001
Revises: None
Create Date: 2026-06-04
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260604_001"
down_revision = None
branch_labels = None
depends_on = None


SEED_USERS = {
    "admin": {"password": "admin123", "display_name": "管理员", "role": "admin"},
    "analyst": {"password": "analyst123", "display_name": "分析师", "role": "analyst"},
    "viewer": {"password": "viewer123", "display_name": "访客", "role": "viewer"},
}


def _hash_seed_password(plain: str) -> str:
    try:
        from src.api.routers.deps import hash_password

        return hash_password(plain)
    except Exception:
        return f"PLAIN:{plain}"


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute("CREATE SCHEMA IF NOT EXISTS okra")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS okra.users (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            username VARCHAR(50) UNIQUE NOT NULL,
            hashed_password VARCHAR(255) NOT NULL,
            display_name VARCHAR(100),
            role VARCHAR(20) NOT NULL DEFAULT 'viewer',
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
        """
    )

    conn = op.get_bind()
    for username, meta in SEED_USERS.items():
        conn.execute(
            sa.text(
                """
            INSERT INTO okra.users (username, hashed_password, display_name, role)
            VALUES (:username, :hashed_password, :display_name, :role)
            ON CONFLICT (username) DO UPDATE
                SET hashed_password = EXCLUDED.hashed_password,
                    display_name = EXCLUDED.display_name,
                    role = EXCLUDED.role,
                    is_active = TRUE
            """
            ),
            {
                "username": username,
                "hashed_password": _hash_seed_password(meta["password"]),
                "display_name": meta["display_name"],
                "role": meta["role"],
            },
        )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS okra.route_plans (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name VARCHAR(100) NOT NULL,
            description TEXT,
            status VARCHAR(20) NOT NULL DEFAULT 'draft',
            total_distance_km NUMERIC(10, 2),
            total_cost_yuan NUMERIC(12, 2),
            vehicle_type VARCHAR(32),
            created_by VARCHAR(50),
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS okra.route_stops (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            route_plan_id UUID NOT NULL
                REFERENCES okra.route_plans(id) ON DELETE CASCADE,
            stop_order INT NOT NULL,
            node_id TEXT REFERENCES okra.nodes(node_id),
            action VARCHAR(20) NOT NULL DEFAULT 'delivery',
            planned_arrival TIMESTAMP,
            planned_departure TIMESTAMP,
            notes TEXT
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_route_stops_plan_id "
        "ON okra.route_stops (route_plan_id)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS okra.operation_logs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id VARCHAR(50),
            action VARCHAR(50),
            target_type VARCHAR(50),
            target_id VARCHAR(100),
            detail JSONB,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_operation_logs_user_id "
        "ON okra.operation_logs (user_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_operation_logs_created_at "
        "ON okra.operation_logs (created_at)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS okra.idx_operation_logs_created_at")
    op.execute("DROP INDEX IF EXISTS okra.idx_operation_logs_user_id")
    op.execute("DROP TABLE IF EXISTS okra.operation_logs")
    op.execute("DROP INDEX IF EXISTS okra.idx_route_stops_plan_id")
    op.execute("DROP TABLE IF EXISTS okra.route_stops")
    op.execute("DROP TABLE IF EXISTS okra.route_plans")
    op.execute("DROP TABLE IF EXISTS okra.users")
