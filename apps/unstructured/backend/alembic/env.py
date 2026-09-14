from logging.config import fileConfig
from sqlalchemy import engine_from_config, text
from sqlalchemy import pool
from alembic import context
import os
import sys

# Add the src directory to the Python path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from primedata.db.database import Base
from primedata.core.settings import get_settings

# Import all models so they are registered with Base.metadata
import primedata.db.models

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def get_url():
    """Get database URL from environment variables."""
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        user = os.environ.get("POSTGRES_USER")
        password = os.environ.get("POSTGRES_PASSWORD")
        host = os.environ.get("POSTGRES_HOST", "localhost")
        port = os.environ.get("POSTGRES_PORT", "5432")
        db = os.environ.get("POSTGRES_DB")
        if not all([user, password, host, port, db]):
            raise RuntimeError("Missing one or more required database environment variables.")
        db_url = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db}"
    print(f"[Alembic] Using database URL: {db_url}")
    return db_url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def repair_missing_revision(connectable) -> None:
    """Repair database if it references a missing migration revision.

    This can happen in Kubernetes when migrations are deleted or
    database state is out of sync with deployed code.
    """
    from alembic.script import ScriptDirectory

    try:
        with connectable.connect() as conn:
            result = conn.execute(text("SELECT version_num FROM alembic_version"))
            db_revisions = [row[0] for row in result.fetchall()]

            # Get all valid revision IDs from migration files
            script_dir = ScriptDirectory.from_config(config)
            valid_revisions = {rev.revision for rev in script_dir.walk_revisions()}

            # Find missing revisions
            missing = [rev for rev in db_revisions if rev not in valid_revisions]

            if missing:
                print(f"[Alembic] WARNING: Found missing revisions in database: {missing}")
                print(f"[Alembic] Valid revisions available: {valid_revisions}")

                # Get the latest head revision
                heads = script_dir.get_heads()
                if heads:
                    latest_head = heads[0]
                    print(f"[Alembic] Auto-repairing: setting database to latest head: {latest_head}")

                    # Clear and set to latest head
                    conn.execute(text("DELETE FROM alembic_version"))
                    conn.execute(text(f"INSERT INTO alembic_version (version_num) VALUES ('{latest_head}')"))
                    conn.commit()
                    print(f"[Alembic] Successfully repaired database migration state")
    except Exception as e:
        print(f"[Alembic] Could not repair migrations: {e}")
        # Don't fail - let the normal migration process continue


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    configuration = config.get_section(config.config_ini_section)
    configuration["sqlalchemy.url"] = get_url()
    print(configuration["sqlalchemy.url"])
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    # Repair any missing revisions before running migrations
    repair_missing_revision(connectable)

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
