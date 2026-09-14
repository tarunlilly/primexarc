"""Alembic async env for the history DB.

Reads the connection URL from `config.settings.history_db_url` (the same
URL the runtime app uses) so migrations and runtime cannot drift on which
DB they target.
"""
from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from config import settings
from db.schema import Base

# Alembic Config object — provides access to alembic.ini values.
config = context.config

# Configure Python logging from alembic.ini if present.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Inject the runtime URL. Done at import time so both online and offline
# migration paths see it.
if not settings.history_db_url:
    raise RuntimeError(
        "history_db_url is empty — set DB_HOST/PORT/NAME/USER/PASSWORD in .env "
        "before running alembic."
    )
config.set_main_option("sqlalchemy.url", settings.history_db_url.replace("%", "%%"))

target_metadata = Base.metadata


def _include_object(obj, name, type_, reflected, compare_to):
    """Limit autogenerate to objects in the configured schema only."""
    if type_ == "table":
        return obj.schema == settings.history_db_schema
    return True


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode — emit SQL without a live connection.

    Useful for `alembic upgrade head --sql > out.sql` to hand a DBA a script.
    """
    context.configure(
        url=settings.history_db_url,
        target_metadata=target_metadata,
        version_table_schema=settings.history_db_schema,
        include_schemas=True,
        include_object=_include_object,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        version_table_schema=settings.history_db_schema,
        include_schemas=True,
        include_object=_include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
