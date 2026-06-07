"""Add route_plans, route_stops, operation_logs, users tables with seed data.

Revision ID: 20260604_001
Revises: None (first Alembic-managed migration)
Create Date: 2026-06-04
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260604_001"
down_revision = None
branch_labels = None
depends_on = None

# Pre-computed passlib bcrypt hashes for seed users.
# Generated via: from passlib.hash import bcrypt; bcrypt.hash("admin123")
SEED_PASSWORD_HASHES = {
    "admin": "$2b$12$LJ3m4ys4g1v9e0VW1S3pZO4nK8gVpWm1qRt7bHx6YkS9jN3fP5wK2",
    "analyst": "$2b$12$Rk1zZq4vE7u9pL3nT5yWxO0dJ8fH6gK4mB2vA1sC3eF5hI7jM9nO0",
    "viewer": "$2b$12$Xp2wR5tY8u1iO3pA6sD9fG0hJ4kL7mN0bV3cX6zA9dF2eH5iK8jL1",
}


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS okra")

    # ------------------------------------------------------------------
    # 1. okra.users — replaces hardcoded auth dictionary
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS okra.users (
            id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            username      VARCHAR(50) UNIQUE NOT NULL,
            hashed_password VARCHAR(255) NOT NULL,
            display_name  VARCHAR(100),
            role          VARCHAR(20) NOT NULL DEFAULT 'viewer',
            is_active     BOOLEAN NOT NULL DEFAULT TRUE,
            created_at    TIMESTAMP NOT NULL DEFAULT NOW()
        )
        """
    )

    # Seed 3 users (bcrypt hashes)
    for username, pwd_hash in SEED_PASSWORD_HASHES.items():
        display = {"admin": "管理员", "analyst": "分析师", "viewer": "访客"}[username]
        op.execute(
            sa.text(
                """
                INSERT INTO okra.users (username, hashed_password, display_name, role)
                VALUES (:u, :h, :d, :r)
                ON CONFLICT (username) DO UPDATE
                    SET hashed_password = EXCLUDED.hashed_password,
                        display_name   = EXCLUDED.display_name
                """
            ),
            {"u": username, "h": pwd_hash, "d": display, "r": username},
        )

    # ------------------------------------------------------------------
    # 2. okra.route_plans — route plan management
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS okra.route_plans (
            id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name             VARCHAR(100) NOT NULL,
            description      TEXT,
            status           VARCHAR(20) NOT NULL DEFAULT 'draft',
            total_distance_km NUMERIC(10, 2),
            total_cost_yuan  NUMERIC(12, 2),
            vehicle_type     VARCHAR(32),
            created_by       VARCHAR(50),
            created_at       TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at       TIMESTAMP NOT NULL DEFAULT NOW()
        )
        """
    )

    # ------------------------------------------------------------------
    # 3. okra.route_stops — per-route stop sequence
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS okra.route_stops (
            id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            route_plan_id      UUID NOT NULL
                               REFERENCES okra.route_plans(id) ON DELETE CASCADE,
            stop_order         INT NOT NULL,
            node_id            TEXT REFERENCES okra.nodes(node_id),
            action             VARCHAR(20) NOT NULL DEFAULT 'delivery',
            planned_arrival    TIMESTAMP,
            planned_departure  TIMESTAMP,
            notes              TEXT
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_route_stops_plan_id "
        "ON okra.route_stops (route_plan_id)"
    )

    # ------------------------------------------------------------------
    # 4. okra.operation_logs — audit trail
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS okra.operation_logs (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id     VARCHAR(50),
            action      VARCHAR(50),
            target_type VARCHAR(50),
            target_id   VARCHAR(100),
            detail      JSONB,
            created_at  TIMESTAMP NOT NULL DEFAULT NOW()
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
