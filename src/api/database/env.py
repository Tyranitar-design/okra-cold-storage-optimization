"""Alembic environment for okra cold-storage schema migrations.

Run examples:
  # Upgrade to latest
  DATABASE_URL=postgresql://... alembic -c src/api/database/alembic.ini upgrade head

  # Generate a new migration
  alembic -c src/api/database/alembic.ini revision --autogenerate -m "description"
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Ensure project root is on sys.path so src.api.* imports resolve.
PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

config = context.config

# Resolve DATABASE_URL from environment; support OKRA_DATABASE_URL as well.
db_url = os.environ.get("DATABASE_URL") or os.environ.get("OKRA_DATABASE_URL", "")
if db_url:
    # Normalise the driver prefix so SQLAlchemy can connect.
    db_url = db_url.replace("postgresql+psycopg://", "postgresql://")
    config.set_main_option("sqlalchemy.url", db_url)

target_metadata = None  # We do NOT use declarative models — raw SQL migrations only.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL to stdout)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live database."""
    url = config.get_main_option("sqlalchemy.url")
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        url=url,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
