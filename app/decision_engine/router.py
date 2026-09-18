from fastapi import APIRouter, HTTPException, Depends
from typing import List
from app.decision_engine.services.orchestrator import DecisionOrchestrator
from app.decision_engine.schemas import DecisionRequest, DecisionResponse
from app.core.database import get_async_db
from app.core.dependencies import (
    get_intelligence_service, 
    get_classifier,
    get_arbitrator,
    get_cognitive_simulator,
)
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
    orchestrator: DecisionOrchestrator = Depends(get_orchestrator)
):
    try:
        return await orchestrator.handle_decision(request)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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
