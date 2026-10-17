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

import uuid
from typing import Optional
from fastapi import Query
from sqlalchemy import desc
from app.decision_engine.models import Decision
from app.core.dependencies import get_user_workspace_ids


def _map_decision_to_response(d: Decision) -> DecisionResponse:
    dom_src = d.dominant_source.value if hasattr(d.dominant_source, "value") else (str(d.dominant_source) if d.dominant_source else "none")
    risk_val = d.risk_level.value if hasattr(d.risk_level, "value") else str(d.risk_level)
    return DecisionResponse(
        decision_id=str(d.id),
        dominant_source=dom_src,
        final_action=d.final_action or d.proposed_action,
        risk_level=risk_val,
        approval_required=bool(d.approval_required),
        control_outcome=d.control_outcome,
        control_reason=d.control_reason,
        permission_granted=bool(d.permission_granted),
    )


@router.get("/{decision_id}", response_model=DecisionResponse)
async def get_decision(
    decision_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Récupère une décision par son identifiant avec isolation multi-tenant anti-énumération (404)."""
    decision = (
        await db.execute(select(Decision).where(Decision.id == decision_id))
    ).scalar_one_or_none()
    if not decision:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Décision introuvable.")

    user_ws_ids = await get_user_workspace_ids(db, current_user)
    if decision.workspace_id not in user_ws_ids:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Décision introuvable.")

    return _map_decision_to_response(decision)


@router.get("/", response_model=List[DecisionResponse])
async def list_decisions(
    workspace_id: Optional[uuid.UUID] = None,
    limit: int = Query(default=50, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Liste les décisions des workspaces de l'utilisateur courant."""
    user_ws_ids = await get_user_workspace_ids(db, current_user)
    if workspace_id:
        if workspace_id not in user_ws_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Accès refusé : vous n'êtes pas membre de cet espace de travail.",
            )
        target_ws_ids = {workspace_id}
    else:
        target_ws_ids = user_ws_ids

    if not target_ws_ids:
        return []

    stmt = (
        select(Decision)
        .where(Decision.workspace_id.in_(target_ws_ids))
        .order_by(desc(Decision.created_at))
        .limit(limit)
    )
    decisions = (await db.execute(stmt)).scalars().all()
    return [_map_decision_to_response(d) for d in decisions]
