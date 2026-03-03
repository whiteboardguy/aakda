from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# ---------------------------------------------------------------------------
# Alembic config object — provides access to values in alembic.ini
# ---------------------------------------------------------------------------
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ---------------------------------------------------------------------------
# Import app models so all tables are registered with Base.metadata,
# then override the sqlalchemy.url with the live connection string from
# the app's Settings object.
# ---------------------------------------------------------------------------
import app.utils.models  # noqa: F401 — registers User, Conversation, Session
from app.utils.database import Base, DB_URL

target_metadata = Base.metadata

# Override the placeholder URL in alembic.ini with the real one from app settings.
config.set_main_option("sqlalchemy.url", DB_URL)


# ---------------------------------------------------------------------------
# Migration runners
# ---------------------------------------------------------------------------


def run_migrations_offline() -> None:
    """Run migrations without a live DB connection (emits SQL to stdout)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live DB connection."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
