from fastapi import APIRouter, HTTPException, Depends, status
from sqlalchemy import select
from typing import List
from app.decision_engine.services.orchestrator import DecisionOrchestrator
from app.decision_engine.schemas import DecisionRequest, DecisionResponse
from app.core.database import get_async_db
from app.core.dependencies import (
    get_intelligence_service, 
    get_classifier,
    get_arbitrator,
    get_cognitive_simulator,
    get_current_user,
    assert_workspace_member,
)
from app.identity.models import User, Agent
from app.intelligence.services.intelligence_service import IntelligenceService
from app.decision_engine.services.domain_classifier import DomainClassifier
from app.decision_engine.services.arbitrator import DeterministicArbitrator
from sqlalchemy.ext.asyncio import AsyncSession
from app.cognitive.services.simulation import CognitiveSimulator

router = APIRouter(prefix="/decisions", tags=["decisions"])

async def get_orchestrator(
    db: AsyncSession = Depends(get_async_db),
    classifier: DomainClassifier = Depends(get_classifier),
    arbitrator: DeterministicArbitrator = Depends(get_arbitrator),
    intelligence_service: IntelligenceService = Depends(get_intelligence_service),
    cognitive_simulator: CognitiveSimulator = Depends(get_cognitive_simulator),
) -> DecisionOrchestrator:
    return DecisionOrchestrator(
        db=db,
        classifier=classifier,
        arbitrator=arbitrator,
        intelligence=intelligence_service,
        cognitive_simulator=cognitive_simulator,
    )

@router.post("/", response_model=DecisionResponse)
async def submit_decision(
    request: DecisionRequest, 
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
    orchestrator: DecisionOrchestrator = Depends(get_orchestrator),
):
    # 1. Vérification d'appartenance au workspace (403 si étranger)
    await assert_workspace_member(db, current_user, request.workspace_id)

    # 2. Vérification que l'agent existe dans ce workspace (404 si introuvable)
    stmt = select(Agent).where(
        Agent.id == request.agent_id,
        Agent.workspace_id == request.workspace_id,
    )
    agent = (await db.execute(stmt)).scalar_one_or_none()
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent introuvable dans cet espace de travail.",
        )

    try:
        return await orchestrator.handle_decision(request)
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logging.getLogger("rockib.decision_router").error(
            "Internal error in submit_decision: %s", e, exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur interne lors du traitement de la décision.",
        )

@router.get("/{decision_id}", response_model=DecisionResponse)
async def get_decision(
    decision_id: str, 
    orchestrator: DecisionOrchestrator = Depends(get_orchestrator)
):
    raise HTTPException(status_code=501, detail="Not implemented")

@router.get("/", response_model=List[DecisionResponse])
async def list_decisions(
    orchestrator: DecisionOrchestrator = Depends(get_orchestrator)
):
    raise HTTPException(status_code=501, detail="Not implemented")
