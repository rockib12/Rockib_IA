from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.identity.router import router as auth_router
from app.decision_engine.router import router as decision_router
from app.goal_engine.router import router as goal_router

app = FastAPI(
    title=settings.APP_NAME,
    description="Rockib AI — Double Numérique, Mémoire Multi-couche & Système d'Arbitrage Déterministe d'Agents",
    version="0.1.0",
    debug=settings.DEBUG,
)

# Configuration CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # À restreindre en production (ex: Vercel frontend URL)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Authentification & Identity
app.include_router(auth_router)

# API endpoints
app.include_router(decision_router, prefix="/api/v1")
app.include_router(goal_router, prefix="/api/v1")


@app.get("/")
async def root():
    return {
        "status": "online",
        "app_name": settings.APP_NAME,
        "environment": settings.APP_ENV,
        "phase": 0,
        "message": "Félicitations, les fondations de Rockib AI (Phase 0) sont prêtes.",
    }


# Prochaines étapes : Enregistrement des routeurs de chaque couche
# app.include_router(identity_router, prefix="/api/v1/identity", tags=["Identity"])
# app.include_router(memory_router, prefix="/api/v1/memory", tags=["Memory"])
# app.include_router(decision_router, prefix="/api/v1/decision", tags=["Decision Engine"])