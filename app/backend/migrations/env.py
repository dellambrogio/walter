from logging.config import fileConfig
from typing import Literal

from alembic import context
from sqlalchemy import engine_from_config, pool, text
from sqlalchemy.sql.schema import SchemaItem

import walter.models  # noqa: F401  (register tables for autogenerate)
from walter.db import Base
from walter.settings import settings

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url)
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# PostGIS/tiger tables are managed by the extension, not by our migrations. The postgis image puts the
# tiger schemas on the search_path, so they reflect as if they were in public: only compare tables that
# really live in public (filled in from the connection in online mode).
IGNORED_TABLES = {"spatial_ref_sys"}
public_tables: set[str] | None = None


ObjectType = Literal[
    "schema", "table", "column", "index", "unique_constraint", "foreign_key_constraint", "check_constraint"
]


def include_object(
    obj: SchemaItem, name: str | None, type_: ObjectType, reflected: bool, compare_to: SchemaItem | None
) -> bool:
    table = name if type_ == "table" else getattr(getattr(obj, "table", None), "name", None)
    if table in IGNORED_TABLES:
        return False
    if reflected and public_tables is not None and table is not None and table not in public_tables:
        return False
    return True


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}), prefix="sqlalchemy.", poolclass=pool.NullPool
    )
    with connectable.connect() as connection:
        global public_tables
        public_tables = (
            set(
                connection.execute(
                    text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
                ).scalars()
            )
            - IGNORED_TABLES
        )
        connection.commit()  # end the implicit transaction, or Alembic's changes are rolled back on close
        context.configure(
            connection=connection, target_metadata=target_metadata, include_object=include_object
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
