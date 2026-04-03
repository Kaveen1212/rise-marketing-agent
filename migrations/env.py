"""
migrations/env.py
─────────────────────────────────────────────────────────────────────────────
Alembic migration environment.

Key design decisions:
  • Database URL is loaded from environment variables — never hardcoded
  • SSL mode=require is enforced on every connection (via settings.sync_database_url)
  • All 4 app models are imported so autogenerate detects schema changes
  • include_schemas=True enables Alembic to track the auth schema (Supabase users)
    but we only autogenerate for the public schema
─────────────────────────────────────────────────────────────────────────────
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

# Load app settings — this reads the .env file
from app.config import settings

# Import Base AND all models so metadata is populated for autogenerate
from app.database import Base
import app.models  # noqa: F401 — side-effect import registers all models

# Alembic Config object (provides access to values in alembic.ini)
config = context.config

# ── Inject the database URL from environment (not from alembic.ini) ──────────
# settings.sync_database_url always includes sslmode=require
config.set_main_option("sqlalchemy.url", settings.sync_database_url)

# Set up Python logging from the alembic.ini [loggers] section
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# The metadata object that Alembic uses for autogenerate (--autogenerate flag)
target_metadata = Base.metadata


# ─────────────────────────────────────────────────────────────────────────────
# Offline migrations (generate SQL script without connecting to DB)
# ─────────────────────────────────────────────────────────────────────────────

def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode.

    Generates a SQL script that can be reviewed and executed manually.
    Useful for production deployments where you want to inspect SQL before
    applying it.

    Usage:
        alembic upgrade head --sql > migration.sql
        # Review migration.sql, then apply manually
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # Render ENUM type changes as ALTER TYPE statements
        render_as_batch=False,
        # Include all schemas in metadata comparison
        include_schemas=False,
        # Compare server defaults to detect changes
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


# ─────────────────────────────────────────────────────────────────────────────
# Online migrations (connect to DB and apply directly)
# ─────────────────────────────────────────────────────────────────────────────

def run_migrations_online() -> None:
    """
    Run migrations in 'online' mode — connects to the database and applies
    migrations directly.

    Used for: local development, CI/CD pipeline, automated deployments.
    """
    connectable = create_engine(
        settings.sync_database_url,
        poolclass=pool.NullPool,
        connect_args={"channel_binding": "prefer", "connect_timeout": 15},
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # Detect column type changes (e.g. VARCHAR(100) → VARCHAR(200))
            compare_type=True,
            # Detect server default changes
            compare_server_default=True,
            # Include ENUM type definitions in autogenerate output
            render_as_batch=False,
        )

        with context.begin_transaction():
            context.run_migrations()


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
