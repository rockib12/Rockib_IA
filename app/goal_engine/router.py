"""Router FastAPI pour les Goals, Tâches, Agents et Exécution Autonome (STEP 5C / Cockpit 3D)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cognitive.services.simulation import CognitiveSimulator
from app.core.database import get_async_db
from app.core.dependencies import (
    get_arbitrator,
    get_classifier,
    get_cognitive_simulator,
    get_intelligence_service,
)
from app.decision_engine.models import Decision
from app.decision_engine.services.arbitrator import DeterministicArbitrator
from app.decision_engine.services.domain_classifier import DomainClassifier
from app.decision_engine.services.orchestrator import DecisionOrchestrator
from app.execution.models import ExecutionAttempt, ExecutionResultRecord
from app.execution.services.system_handlers import install_production_handlers
from app.goal_engine.models import Goal, GoalStatus
from app.goal_engine.services.autonomous_loop import WakeResult, wake_goal
from app.goal_engine.services.goal_manager import GoalManager
from app.identity.models import Agent, Workspace
from app.intelligence.services.intelligence_service import IntelligenceService
from app.task_engine.models import Task, TaskDependency, TaskStatus

router = APIRouter(prefix="", tags=["goals-and-agents"])

# S'assurer que le premier handler production (system.read) est enregistré
install_production_handlers()


# --- Pydantic Schemas ---


class CreateAgentRequest(BaseModel):
    workspace_id: uuid.UUID
    name: str
    role: Optional[str] = "Worker"
    default_autonomy_level: int = Field(default=2, ge=0, le=5)
    parent_agent_id: Optional[uuid.UUID] = None


class AgentResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    role: Optional[str]
    is_active: bool
    default_autonomy_level: int
    parent_agent_id: Optional[uuid.UUID] = None
    created_at: datetime
    active_goals_count: int = 0
    total_tasks_count: int = 0
    completed_tasks_count: int = 0
    current_status: str = "READY"
    current_action: Optional[str] = None


class TaskSummary(BaseModel):
    id: uuid.UUID
    goal_id: uuid.UUID
    decision_id: Optional[uuid.UUID]
    description: str
    status: str
    dependencies: List[uuid.UUID] = []
    created_at: datetime
    updated_at: datetime


class GoalSummary(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    agent_id: uuid.UUID
    agent_name: Optional[str] = None
    objective: str
    status: str
    priority: int
    requested_autonomy_level: int
    applied_autonomy_level: int
    parent_goal_id: Optional[uuid.UUID]
    created_at: datetime
    updated_at: datetime
    tasks_count: int = 0
    completed_tasks_count: int = 0
    running_tasks_count: int = 0


class CreateGoalRequest(BaseModel):
    workspace_id: uuid.UUID
    agent_id: uuid.UUID
    objective: str
    priority: int = 1
    requested_autonomy_level: int = Field(default=2, ge=0, le=5)
    parent_goal_id: Optional[uuid.UUID] = None
    initial_tasks: Optional[List[str]] = None


class WakeGoalResponse(BaseModel):
    status: str
    task_id: Optional[uuid.UUID] = None
    execution_effect: Optional[str] = None
    violations: List[str] = []


class TelemetryEvent(BaseModel):
    id: str
    timestamp: datetime
    type: str  # "decision", "execution", "agent_spawn", "task_update"
    agent_name: str
    summary: str
    details: dict = {}


# --- Endpoints ---


@router.get("/agents", response_model=List[AgentResponse])
async def list_agents(
    workspace_id: Optional[uuid.UUID] = None,
    db: AsyncSession = Depends(get_async_db),
):
    """Liste tous les agents avec leurs statistiques et état pour le rendu 3D."""
    query = select(Agent)
    if workspace_id:
        query = query.where(Agent.workspace_id == workspace_id)
    agents = (await db.execute(query)).scalars().all()

    result: List[AgentResponse] = []
    for ag in agents:
        # Récupérer les stats des goals de cet agent
        stmt_goals = select(Goal).where(Goal.agent_id == ag.id)
        goals = (await db.execute(stmt_goals)).scalars().all()
        active_goals = [g for g in goals if g.status in (GoalStatus.ACTIVE, GoalStatus.PLANNING, GoalStatus.PENDING)]

        # Tâches
        goal_ids = [g.id for g in goals]
        total_tasks = 0
        completed_tasks = 0
        running_task_desc = None
        has_running = False

        if goal_ids:
            tasks_stmt = select(Task).where(Task.goal_id.in_(goal_ids))
            all_tasks = (await db.execute(tasks_stmt)).scalars().all()
            total_tasks = len(all_tasks)
            completed_tasks = sum(1 for t in all_tasks if t.status == TaskStatus.COMPLETED)
            running_tasks = [t for t in all_tasks if t.status == TaskStatus.RUNNING]
            if running_tasks:
                has_running = True
                running_task_desc = running_tasks[0].description

        # Déduire le statut courant pour le halo 3D
        current_status = "RUNNING" if has_running else ("READY" if active_goals else "IDLE")

        # Parent agent éventuel (via parent_goal ou métadonnées)
        parent_agent_id = None
        for g in goals:
            if g.parent_goal_id:
                p_goal = (await db.execute(select(Goal).where(Goal.id == g.parent_goal_id))).scalar_one_or_none()
                if p_goal and p_goal.agent_id != ag.id:
                    parent_agent_id = p_goal.agent_id
                    break

        result.append(
            AgentResponse(
                id=ag.id,
                workspace_id=ag.workspace_id,
                name=ag.name,
                role=ag.role,
                is_active=ag.is_active,
                default_autonomy_level=ag.default_autonomy_level,
                parent_agent_id=parent_agent_id,
                created_at=ag.created_at,
                active_goals_count=len(active_goals),
                total_tasks_count=total_tasks,
                completed_tasks_count=completed_tasks,
                current_status=current_status,
                current_action=running_task_desc or (f"Supervise {len(active_goals)} objectif(s)" if active_goals else "En veille orbitale"),
            )
        )
    return result


@router.post("/agents", response_model=AgentResponse)
async def create_agent(
    payload: CreateAgentRequest,
    db: AsyncSession = Depends(get_async_db),
):
    """Crée un nouvel agent (ex: sous-agent spawné) pour peupler la matrice 3D."""
    new_agent = Agent(
        id=uuid.uuid4(),
        workspace_id=payload.workspace_id,
        name=payload.name,
        role=payload.role,
        is_active=True,
        default_autonomy_level=payload.default_autonomy_level,
    )
    db.add(new_agent)
    await db.commit()
    await db.refresh(new_agent)

    return AgentResponse(
        id=new_agent.id,
        workspace_id=new_agent.workspace_id,
        name=new_agent.name,
        role=new_agent.role,
        is_active=new_agent.is_active,
        default_autonomy_level=new_agent.default_autonomy_level,
        parent_agent_id=payload.parent_agent_id,
        created_at=new_agent.created_at,
        active_goals_count=0,
        total_tasks_count=0,
        completed_tasks_count=0,
        current_status="READY",
        current_action="Initialisation du pod agentique",
    )


@router.get("/goals", response_model=List[GoalSummary])
async def list_goals(
    workspace_id: Optional[uuid.UUID] = None,
    agent_id: Optional[uuid.UUID] = None,
    db: AsyncSession = Depends(get_async_db),
):
    """Liste tous les Goals avec métriques d'avancement."""
    query = select(Goal)
    if workspace_id:
        query = query.where(Goal.workspace_id == workspace_id)
    if agent_id:
        query = query.where(Goal.agent_id == agent_id)
    query = query.order_by(desc(Goal.created_at))

    goals = (await db.execute(query)).scalars().all()
    summaries: List[GoalSummary] = []

    for g in goals:
        agent = (await db.execute(select(Agent).where(Agent.id == g.agent_id))).scalar_one_or_none()
        tasks = (await db.execute(select(Task).where(Task.goal_id == g.id))).scalars().all()

        summaries.append(
            GoalSummary(
                id=g.id,
                workspace_id=g.workspace_id,
                agent_id=g.agent_id,
                agent_name=agent.name if agent else "Unknown Agent",
                objective=g.objective,
                status=g.status.value,
                priority=g.priority,
                requested_autonomy_level=g.requested_autonomy_level,
                applied_autonomy_level=g.applied_autonomy_level,
                parent_goal_id=g.parent_goal_id,
                created_at=g.created_at,
                updated_at=g.updated_at,
                tasks_count=len(tasks),
                completed_tasks_count=sum(1 for t in tasks if t.status == TaskStatus.COMPLETED),
                running_tasks_count=sum(1 for t in tasks if t.status == TaskStatus.RUNNING),
            )
        )
    return summaries


@router.get("/goals/{goal_id}")
async def get_goal_details(
    goal_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_db),
):
    """Retourne les détails complets d'un Goal avec son DAG de tâches et dépendances."""
    goal = (await db.execute(select(Goal).where(Goal.id == goal_id))).scalar_one_or_none()
    if not goal:
        raise HTTPException(status_code=404, detail="Goal non trouvé.")

    agent = (await db.execute(select(Agent).where(Agent.id == goal.agent_id))).scalar_one_or_none()
    tasks = (await db.execute(select(Task).where(Task.goal_id == goal_id).order_by(Task.created_at))).scalars().all()
    deps = (await db.execute(select(TaskDependency).where(TaskDependency.goal_id == goal_id))).scalars().all()

    # Dictionnaire des dépendances par tâche
    deps_by_task: dict[uuid.UUID, list[uuid.UUID]] = {}
    for d in deps:
        deps_by_task.setdefault(d.task_id, []).append(d.depends_on_task_id)

    task_summaries = [
        TaskSummary(
            id=t.id,
            goal_id=t.goal_id,
            decision_id=t.decision_id,
            description=t.description,
            status=t.status.value,
            dependencies=deps_by_task.get(t.id, []),
            created_at=t.created_at,
            updated_at=t.updated_at,
        )
        for t in tasks
    ]

    return {
        "id": goal.id,
        "workspace_id": goal.workspace_id,
        "agent_id": goal.agent_id,
        "agent_name": agent.name if agent else "Unknown Agent",
        "agent_role": agent.role if agent else "Worker",
        "objective": goal.objective,
        "status": goal.status.value,
        "priority": goal.priority,
        "requested_autonomy_level": goal.requested_autonomy_level,
        "applied_autonomy_level": goal.applied_autonomy_level,
        "parent_goal_id": goal.parent_goal_id,
        "goal_metadata": goal.goal_metadata,
        "created_at": goal.created_at,
        "updated_at": goal.updated_at,
        "tasks": task_summaries,
    }


@router.post("/goals", response_model=GoalSummary)
async def create_goal(
    payload: CreateGoalRequest,
    db: AsyncSession = Depends(get_async_db),
):
    """Crée un nouvel objectif (Goal) et peuple automatiquement ses premières tâches."""
    agent = (await db.execute(select(Agent).where(Agent.id == payload.agent_id))).scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent spécifié introuvable.")

    # Calcul de l'autonomie appliquée déterministe
    applied_autonomy = GoalManager.calculate_applied_autonomy(
        requested_autonomy_level=payload.requested_autonomy_level,
        agent_default_autonomy=agent.default_autonomy_level,
    )

    new_goal = Goal(
        id=uuid.uuid4(),
        workspace_id=payload.workspace_id,
        agent_id=payload.agent_id,
        objective=payload.objective,
        status=GoalStatus.ACTIVE,
        priority=payload.priority,
        requested_autonomy_level=payload.requested_autonomy_level,
        applied_autonomy_level=applied_autonomy,
        parent_goal_id=payload.parent_goal_id,
        goal_metadata={"limits": {"max_steps": 25, "max_replanning_count": 3}},
    )
    db.add(new_goal)
    await db.flush()

    task_descriptions = payload.initial_tasks or [
        f"Analyse initiale et cartographie de l'objectif : {payload.objective}",
        "Diagnostic d'intégrité système (system.read)",
        "Synthèse et rapport d'exécution déterministe",
    ]

    created_tasks: list[Task] = []
    for idx, desc_text in enumerate(task_descriptions):
        t = Task(
            id=uuid.uuid4(),
            goal_id=new_goal.id,
            description=desc_text,
            status=TaskStatus.READY if idx == 0 else TaskStatus.PENDING,
        )
        db.add(t)
        created_tasks.append(t)

    await db.flush()

    # Dépendance linéaire séquentielle
    for i in range(1, len(created_tasks)):
        dep = TaskDependency(
            id=uuid.uuid4(),
            goal_id=new_goal.id,
            task_id=created_tasks[i].id,
            depends_on_task_id=created_tasks[i - 1].id,
        )
        db.add(dep)

    await db.commit()
    await db.refresh(new_goal)

    return GoalSummary(
        id=new_goal.id,
        workspace_id=new_goal.workspace_id,
        agent_id=new_goal.agent_id,
        agent_name=agent.name,
        objective=new_goal.objective,
        status=new_goal.status.value,
        priority=new_goal.priority,
        requested_autonomy_level=new_goal.requested_autonomy_level,
        applied_autonomy_level=new_goal.applied_autonomy_level,
        parent_goal_id=new_goal.parent_goal_id,
        created_at=new_goal.created_at,
        updated_at=new_goal.updated_at,
        tasks_count=len(created_tasks),
        completed_tasks_count=0,
        running_tasks_count=0,
    )


@router.post("/goals/{goal_id}/wake", response_model=WakeGoalResponse)
async def wake_goal_step(
    goal_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_db),
    classifier: DomainClassifier = Depends(get_classifier),
    arbitrator: DeterministicArbitrator = Depends(get_arbitrator),
    intelligence_service: IntelligenceService = Depends(get_intelligence_service),
    cognitive_simulator: CognitiveSimulator = Depends(get_cognitive_simulator),
):
    """Déclenche 1 cycle autonome atomique (wake_goal) sur l'objectif désigné."""
    install_production_handlers()

    def _orchestrator_factory(session: AsyncSession) -> DecisionOrchestrator:
        return DecisionOrchestrator(
            db=session,
            classifier=classifier,
            arbitrator=arbitrator,
            intelligence=intelligence_service,
            cognitive_simulator=cognitive_simulator,
        )

    result: WakeResult = await wake_goal(
        db,
        goal_id=goal_id,
        orchestrator_factory=_orchestrator_factory,
    )

    return WakeGoalResponse(
        status=result.status,
        task_id=result.task_id,
        execution_effect=result.execution_effect,
        violations=list(result.violations or []),
    )


@router.get("/telemetry", response_model=List[TelemetryEvent])
async def get_telemetry_events(
    limit: int = Query(default=30, le=100),
    db: AsyncSession = Depends(get_async_db),
):
    """Retourne les flux de décisions et exécutions récentes pour le HUD holographique."""
    events: List[TelemetryEvent] = []

    # Dernières décisions
    stmt_decisions = select(Decision).order_by(desc(Decision.created_at)).limit(limit)
    decisions = (await db.execute(stmt_decisions)).scalars().all()

    for d in decisions:
        agent = (await db.execute(select(Agent).where(Agent.id == d.agent_id))).scalar_one_or_none()
        outcome_val = d.control_outcome.value if hasattr(d.control_outcome, "value") else str(d.control_outcome)
        risk_val = d.risk_level.value if hasattr(d.risk_level, "value") else str(d.risk_level)
        events.append(
            TelemetryEvent(
                id=f"dec-{d.id}",
                timestamp=d.created_at,
                type="decision",
                agent_name=agent.name if agent else "Agent",
                summary=f"Arbitrage [{outcome_val}] pour action '{d.proposed_action[:40]}' (Risque: {risk_val})",
                details={
                    "outcome": outcome_val,
                    "risk_level": risk_val,
                    "reason": d.control_reason,
                    "fingerprint": d.action_fingerprint[:16] if d.action_fingerprint else None,
                },
            )
        )

    # Dernières exécutions
    stmt_execs = select(ExecutionResultRecord).order_by(desc(ExecutionResultRecord.created_at)).limit(limit)
    exec_results = (await db.execute(stmt_execs)).scalars().all()

    for ex in exec_results:
        events.append(
            TelemetryEvent(
                id=f"exec-{ex.id}",
                timestamp=ex.created_at,
                type="execution",
                agent_name="Executor",
                summary=f"Exécution {ex.provider_reference} — Réussite: {ex.success} (Coût: {ex.cost_amount} {ex.cost_unit})",
                details={
                    "provider": ex.provider_reference,
                    "success": ex.success,
                    "cost": f"{ex.cost_amount} {ex.cost_unit}",
                    "output_preview": (ex.output or "")[:120],
                },
            )
        )

    # Trier par timestamp descendant
    events.sort(key=lambda x: x.timestamp, reverse=True)
    return events[:limit]
