import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# --- IMPORTS DES MODÈLES — nécessaires à l'autogénération -----------------------
from app.core.config import settings
from app.core.database import Base  # re-export de Base pour l'autogénération
from app.identity.models import Workspace, User, Agent  # noqa: F401
from app.memory.models import Memory  # noqa: F401
from app.goal_engine.models import Goal  # noqa: F401
from app.task_engine.models import Task, TaskDependency  # noqa: F401
from app.decision_engine.models import (  # noqa: F401
    DecisionDomainConfig,
    Decision,
    DecisionOutcome,
)
from app.execution.models import (  # noqa: F401
    ActionRecord,
    ActionReservation,
    AuditEntry,
    ExecutionAttempt,
    ExecutionAuthorization,
    ExecutionResultRecord,
    ResourceBudget,
)

# This is the Alembic Config object, which provides access to the values
# within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Set the target metadata for autogenerate support
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL (synchronous) and not an Engine.
    Offline mode renders SQL to stdout — the driver prefix doesn't matter here.
    """
    url = settings.DATABASE_URL  # URL synchrone suffisante pour offline
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Fonction synchrone exécutée dans le thread de migration.

    Elle configure le contexte Alembic avec la connexion fournie et lance
    les migrations. Appelée via ``connection.run_sync`` depuis le moteur async.
    """
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,        # détecte les changements de type en autogénération
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations in 'online' mode using an async engine.

    Pattern asynchrone correct avec asyncpg :
    1. Crée un moteur asynchrone (``postgresql+asyncpg://``)
    2. Ouvre une connexion asynchrone
    3. Exécute ``do_run_migrations`` (synchrone) via ``run_sync``
    """
    # Construction du moteur asynchrone directement depuis l'URL async
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        url=settings.ASYNC_DATABASE_URL,  # postgresql+asyncpg://...
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        # run_sync exécute la fonction synchrone dans le bon thread
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
