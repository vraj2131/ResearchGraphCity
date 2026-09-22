from __future__ import annotations

from logging.config import fileConfig

from alembic import context

from app.config import load_settings


config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def metadata():
    from app.db import Base
    from app import models  # noqa: F401

    return Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=load_settings().database_url,
        target_metadata=metadata(),
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    from app.db import create_engine_from_settings

    with create_engine_from_settings().connect() as connection:
        context.configure(connection=connection, target_metadata=metadata())
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
