from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import create_engine

from alembic import context

from app.database import Base, settings
from app.models import User
# Register every mapped table so Alembic autogeneration sees the complete schema.
from app.models.audit import AuditLog  # noqa: F401
from app.models.medical_record import MedicalRecord  # noqa: F401
from app.models.medication import MedicationReference  # noqa: F401
from app.models.safety import SafetyCheck, SafetyFinding  # noqa: F401


config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_migration_url() -> str:
    return getattr(settings, "resolved_database_url", settings.database_url)


def run_migrations_offline() -> None:
    url = get_migration_url()
    is_sqlite = url.startswith("sqlite")

    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=is_sqlite,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    url = get_migration_url()
    is_sqlite = url.startswith("sqlite")
    connectable = create_engine(
        url,
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=is_sqlite,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
