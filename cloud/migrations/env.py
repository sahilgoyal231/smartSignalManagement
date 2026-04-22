"""
Alembic migration environment — configured for async SQLAlchemy + PostgreSQL.
Reads DB URL from environment variable to avoid hardcoding credentials.
"""
import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# Import all models so Alembic can detect them
from cloud.shared.db_models import Base  # noqa: F401

# ─────────────────────────────────────────────
# Alembic Config
# ─────────────────────────────────────────────
config = context.config

# Use the DATABASE_URL env var (overrides alembic.ini sqlalchemy.url)
db_url = os.environ.get(
    "DATABASE_URL",
    f"postgresql+asyncpg://"
    f"{os.environ.get('POSTGRES_USER','ss_admin')}:"
    f"{os.environ.get('POSTGRES_PASSWORD','password')}@"
    f"{os.environ.get('POSTGRES_HOST','localhost')}:"
    f"{os.environ.get('POSTGRES_PORT','5432')}/"
    f"{os.environ.get('POSTGRES_DB','smart_signal')}"
)
config.set_main_option("sqlalchemy.url", db_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Target metadata — all models must be imported above
target_metadata = Base.metadata


# ─────────────────────────────────────────────
# Offline mode (generate SQL without connecting)
# ─────────────────────────────────────────────
def run_migrations_offline() -> None:
    context.configure(
        url=db_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


# ─────────────────────────────────────────────
# Online mode (async)
# ─────────────────────────────────────────────
def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


# ─────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
