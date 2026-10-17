from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.identity.router import router as auth_router
from app.decision_engine.router import router as decision_router
from app.goal_engine.router import router as goal_router
from app.inbound.router import router as inbound_router

from contextlib import asynccontextmanager

from app.execution.services.system_handlers import install_production_handlers

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 0. Contrôle de sécurité Zero-Trust au démarrage (Fail-Fast)
    DEFAULT_INSECURE_JWT_SECRET = "supersecretkeythatisatleast32characterslongforsecurity"
    if not settings.CREDENTIAL_VAULT_KEY and settings.JWT_SECRET_KEY == DEFAULT_INSECURE_JWT_SECRET:
        raise RuntimeError(
            "FATAL SECURITY CONFIGURATION ERROR: Refusing to start Rockib AI. "
            "CREDENTIAL_VAULT_KEY is not defined and JWT_SECRET_KEY is using the insecure hardcoded default. "
            "Please configure an explicit CREDENTIAL_VAULT_KEY or a secure non-default JWT_SECRET_KEY in your environment."
        )

    # Enregistrement des handlers d'exécution système (fs, web, api, social)
    install_production_handlers()
    # Seeding automatique des skills fondamentaux
    try:
        from app.core.database import AsyncSessionLocal
        from app.skills.catalog import seed_default_skills
        from app.skills.services.registry import SkillRegistryError
        async with AsyncSessionLocal() as session:
            await seed_default_skills(session)
            await session.commit()
    except SkillRegistryError as e:
        import logging
        logging.getLogger("rockib.startup").critical(
            "CRITICAL: Integrity failure while seeding default skills: %s", e, exc_info=True
        )
        raise
    except Exception as e:
        import logging
        logging.getLogger("rockib.startup").warning(
            "Warning: Non-critical failure during default skills seeding: %s", e
        )
    # Démarrage du polling Telegram si configuré
    polling_task = None
    stop_event = None
    if settings.TELEGRAM_BOT_TOKEN and settings.TELEGRAM_ADMIN_CHAT_ID:
        import asyncio
        from app.telegram.services.polling import run_telegram_polling_loop
        stop_event = asyncio.Event()
        polling_task = asyncio.create_task(run_telegram_polling_loop(stop_event=stop_event))

    yield

    if polling_task and stop_event:
        stop_event.set()
        polling_task.cancel()
        try:
            await polling_task
        except Exception:
            pass

    try:
        from app.core.database import async_engine
        await async_engine.dispose()
    except Exception:
        pass


app = FastAPI(
    title=settings.APP_NAME,
    description="Rockib AI — Double Numérique, Mémoire Multi-couche & Système d'Arbitrage Déterministe d'Agents",
    version="0.1.0",
    debug=settings.DEBUG,
    lifespan=lifespan,
)

# Configuration CORS sécurisée (liste blanche d'origines)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

import re
import uuid
from fastapi import Depends, Request, Response
from sqlalchemy import text
from app.core.database import AsyncSessionLocal, get_async_db

_SAFE_REQUEST_ID_RE = re.compile(r"^[a-zA-Z0-9._-]{1,64}$")


@app.middleware("http")
async def add_request_id_header(request: Request, call_next):
    incoming_id = request.headers.get("x-request-id", "")
    req_id = incoming_id if _SAFE_REQUEST_ID_RE.match(incoming_id) else str(uuid.uuid4())
    request.state.request_id = req_id
    response: Response = await call_next(request)
    response.headers["X-Request-ID"] = req_id
    return response


# Authentification & Identity
app.include_router(auth_router)

# API endpoints
app.include_router(decision_router, prefix="/api/v1")
app.include_router(goal_router, prefix="/api/v1")
app.include_router(inbound_router, prefix="/api/v1")


@app.get("/")
async def root():
    return {
        "status": "online",
        "app_name": settings.APP_NAME,
        "environment": settings.APP_ENV,
        "phase": 0,
        "message": "Félicitations, les fondations de Rockib AI (Phase 0) sont prêtes.",
    }


@app.get("/api/v1/health")
async def api_health_check(db=Depends(get_async_db)):
    """Sonde de santé profonde vérifiant la connectivité PostgreSQL et Redis."""
    db_ok = False
    try:
        await db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False

    redis_ok = False
    try:
        import redis.asyncio as aioredis
        r_client = aioredis.from_url(settings.REDIS_URL, socket_connect_timeout=1.5)
        try:
            redis_ok = bool(await r_client.ping())
        finally:
            await r_client.aclose()
    except Exception:
        redis_ok = False

    return {
        "status": "healthy" if (db_ok and redis_ok) else "degraded",
        "app_name": settings.APP_NAME,
        "environment": settings.APP_ENV,
        "components": {
            "database": "up" if db_ok else "down",
            "redis": "up" if redis_ok else "down",
        },
    }