"""Router FastAPI pour les Goals, Tâches, Agents et Exécution Autonome (STEP 5C / Cockpit 3D)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, List, Optional

import json
import mimetypes
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings

from app.cognitive.services.simulation import CognitiveSimulator
from app.core.database import get_async_db
from app.core.dependencies import (
    assert_workspace_member,
    get_arbitrator,
    get_classifier,
    get_cognitive_simulator,
    get_current_user,
    get_current_workspace_membership,
    get_intelligence_service,
    get_optional_user,
    get_user_workspace_ids,
)
from app.core.signed_urls import sign_preview_links, verify_preview
from app.decision_engine.models import Decision, ControlOutcome
from app.decision_engine.schemas import DecisionRequest
from app.decision_engine.services.arbitrator import DeterministicArbitrator

from app.decision_engine.services.domain_classifier import DomainClassifier
from app.decision_engine.services.orchestrator import DecisionOrchestrator
from app.execution.models import ActionRecord, ExecutionAttempt, ExecutionResultRecord, AuditEntry
from app.execution.services.system_handlers import install_production_handlers
from app.goal_engine.models import Goal, GoalStatus
from app.goal_engine.services.autonomous_loop import WakeResult, wake_goal
from app.goal_engine.services.goal_manager import GoalManager
from app.identity.models import Agent, Workspace, User
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
    result_summary: Optional[str] = None
    tool: Optional[str] = None



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


class AgentLogItem(BaseModel):
    id: str
    timestamp: datetime
    type: str  # "decision", "execution", "audit", "voice", "state"
    level: str  # "INFO", "WARNING", "ALLOW", "DENY", "ESCALATE", "SUCCESS", "FAILED"
    title: str
    summary: str
    details: dict[str, Any] = Field(default_factory=dict)


class AgentLogsResponse(BaseModel):
    agent_id: uuid.UUID
    agent_name: str
    role: str
    total_logs: int
    logs: List[AgentLogItem]


# --- Endpoints ---


@router.get("/agents", response_model=List[AgentResponse])
async def list_agents(
    workspace_id: Optional[uuid.UUID] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Liste tous les agents avec leurs statistiques et état pour le rendu 3D."""
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

    query = select(Agent).where(Agent.workspace_id.in_(target_ws_ids))
    agents = (await db.execute(query)).scalars().all()
    if not agents:
        return []

    agent_ids = [ag.id for ag in agents]
    all_goals = (
        await db.execute(select(Goal).where(Goal.agent_id.in_(agent_ids)))
    ).scalars().all()

    goals_by_id: dict[uuid.UUID, Goal] = {g.id: g for g in all_goals}
    missing_parent_ids = {
        g.parent_goal_id
        for g in all_goals
        if g.parent_goal_id and g.parent_goal_id not in goals_by_id
    }
    if missing_parent_ids:
        parent_goals = (
            await db.execute(select(Goal).where(Goal.id.in_(missing_parent_ids)))
        ).scalars().all()
        for pg in parent_goals:
            goals_by_id[pg.id] = pg

    goals_by_agent: dict[uuid.UUID, list[Goal]] = {}
    for g in all_goals:
        goals_by_agent.setdefault(g.agent_id, []).append(g)

    all_goal_ids = [g.id for g in all_goals]
    tasks_by_goal: dict[uuid.UUID, list[Task]] = {}
    if all_goal_ids:
        all_tasks_rows = (
            await db.execute(select(Task).where(Task.goal_id.in_(all_goal_ids)))
        ).scalars().all()
        for t in all_tasks_rows:
            tasks_by_goal.setdefault(t.goal_id, []).append(t)

    result: List[AgentResponse] = []
    for ag in agents:
        goals = goals_by_agent.get(ag.id, [])
        active_goals = [
            g for g in goals
            if g.status in (GoalStatus.ACTIVE, GoalStatus.PLANNING, GoalStatus.PENDING)
        ]

        all_tasks = [t for g in goals for t in tasks_by_goal.get(g.id, [])]
        total_tasks = len(all_tasks)
        completed_tasks = sum(1 for t in all_tasks if t.status == TaskStatus.COMPLETED)
        running_tasks = [t for t in all_tasks if t.status == TaskStatus.RUNNING]
        has_running = bool(running_tasks)
        running_task_desc = running_tasks[0].description if running_tasks else None

        # Déduire le statut courant pour le halo 3D
        current_status = "RUNNING" if has_running else ("READY" if active_goals else "IDLE")

        # Parent agent éventuel (via parent_goal ou métadonnées)
        parent_agent_id = None
        for g in goals:
            if g.parent_goal_id:
                p_goal = goals_by_id.get(g.parent_goal_id)
                if p_goal and p_goal.agent_id != ag.id:
                    parent_agent_id = p_goal.agent_id
                    break
            if not parent_agent_id and g.goal_metadata:
                spawned = g.goal_metadata.get("spawned_by") or g.goal_metadata.get("parent_agent_id")
                if spawned and str(spawned) != str(ag.id):
                    try:
                        parent_agent_id = uuid.UUID(str(spawned))
                        break
                    except (ValueError, TypeError):
                        pass

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


@router.get("/agents/{agent_id}/logs", response_model=AgentLogsResponse)
async def get_agent_logs(
    agent_id: uuid.UUID,
    limit: int = Query(default=50, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Retourne l'historique complet, auditable et ordonné des logs d'un agent."""
    agent = (await db.execute(select(Agent).where(Agent.id == agent_id))).scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent non trouvé.")

    user_ws_ids = await get_user_workspace_ids(db, current_user)
    if agent.workspace_id not in user_ws_ids:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent non trouvé.")

    logs: List[AgentLogItem] = []

    # 1. Décisions d'arbitrage
    stmt_dec = select(Decision).where(Decision.agent_id == agent_id).order_by(desc(Decision.created_at)).limit(limit)
    decisions = (await db.execute(stmt_dec)).scalars().all()
    for d in decisions:
        outcome_str = d.control_outcome.value if hasattr(d.control_outcome, "value") else str(d.control_outcome)
        risk_str = d.risk_level.value if hasattr(d.risk_level, "value") else str(d.risk_level)
        logs.append(
            AgentLogItem(
                id=f"dec-{d.id}",
                timestamp=d.created_at,
                type="decision",
                level=outcome_str,
                title=f"Arbitrage [{outcome_str}] - Risque {risk_str}",
                summary=f"Action proposée: '{d.proposed_action[:60]}' | Motif: {d.control_reason or 'Nominal'}",
                details={
                    "proposed_action": d.proposed_action,
                    "final_action": d.final_action,
                    "risk_level": risk_str,
                    "control_outcome": outcome_str,
                    "control_reason": d.control_reason,
                    "fingerprint": d.action_fingerprint,
                }
            )
        )

    # 2. Événements d'audit forensique (AuditEntry)
    stmt_audit = select(AuditEntry).where(AuditEntry.agent_id == agent_id).order_by(desc(AuditEntry.created_at)).limit(limit)
    audit_entries = (await db.execute(stmt_audit)).scalars().all()
    for a in audit_entries:
        ev_type = a.event_type.value if hasattr(a.event_type, "value") else str(a.event_type)
        logs.append(
            AgentLogItem(
                id=f"audit-{a.id}",
                timestamp=a.created_at,
                type="audit",
                level="INFO",
                title=f"Audit: {ev_type}",
                summary=f"Motif: {a.reason_code or 'Système'} | Empreinte: {(a.action_fingerprint or '')[:16]}",
                details={
                    "event_type": ev_type,
                    "reason_code": a.reason_code,
                    "policy_version": a.policy_version,
                    "payload": a.payload or {},
                }
            )
        )

    # 3. Actions réelles exécutées par cet agent
    stmt_actions = select(ActionRecord).where(ActionRecord.agent_id == agent_id).order_by(desc(ActionRecord.created_at)).limit(limit)
    actions = (await db.execute(stmt_actions)).scalars().all()
    for act in actions:
        perm_str = act.permission_required.value if hasattr(act.permission_required, "value") else str(act.permission_required)
        risk_str = act.risk_level.value if hasattr(act.risk_level, "value") else str(act.risk_level)
        logs.append(
            AgentLogItem(
                id=f"act-{act.id}",
                timestamp=act.created_at,
                type="action",
                level="INFO",
                title=f"Action: {act.tool}.{act.operation} ({perm_str})",
                summary=f"Empreinte: {act.canonical_fingerprint[:16]} | Arguments: {str(act.arguments)[:80]}",
                details={
                    "tool": act.tool,
                    "operation": act.operation,
                    "permission_required": perm_str,
                    "arguments": act.arguments,
                    "risk_level": risk_str,
                    "objective": act.objective,
                }
            )
        )

    # 4. Agent Concierge Portfolio : Log des écoutes actives
    if "concierge" in agent.name.lower() or "portfolio" in agent.name.lower():
        logs.append(
            AgentLogItem(
                id="voice-inbound-listener",
                timestamp=datetime.now(timezone.utc),
                type="voice",
                level="SUCCESS",
                title="Service Vocal Web Speech Actif",
                summary="Passerelle vocale en ligne : écoute active des visiteurs sur le portfolio.",
                details={"gateway": "POST /api/v1/inbound/portfolio/voice/turn", "status": "ONLINE"}
            )
        )

    logs.sort(key=lambda x: x.timestamp, reverse=True)

    return AgentLogsResponse(
        agent_id=agent.id,
        agent_name=agent.name,
        role=agent.role or "Worker",
        total_logs=len(logs),
        logs=logs[:limit]
    )


@router.post("/agents", response_model=AgentResponse)
async def create_agent(
    payload: CreateAgentRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
    classifier: DomainClassifier = Depends(get_classifier),
    cognitive_simulator: CognitiveSimulator = Depends(get_cognitive_simulator),
    intelligence_service: IntelligenceService = Depends(get_intelligence_service),
):
    """Crée un nouvel agent via le pipeline d'arbitrage déterministe (DecisionOrchestrator)."""
    # 0. Vérifier l'appartenance de l'utilisateur authentifié au workspace ciblé (Option A)
    await get_current_workspace_membership(
        workspace_id=str(payload.workspace_id),
        user=current_user,
        db=db,
    )

    # 1. Validation stricte du parent_agent_id (aucun fallback / devinette sur un autre agent)
    if not payload.parent_agent_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="parent_agent_id is required to establish provenance and audit lineage.",
        )

    caller_agent = (
        await db.execute(
            select(Agent).where(
                Agent.id == payload.parent_agent_id,
                Agent.workspace_id == payload.workspace_id,
            )
        )
    ).scalar_one_or_none()

    if not caller_agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Parent agent not found in the specified workspace.",
        )



    # Plafonnement strict enfant <= parent : un sous-agent ne peut jamais avoir
    # une autonomie demandée supérieure à celle de l'agent qui le crée (règle enfant <= parent),
    # même si aucune politique n'autorise encore ce domaine à ce jour. Le plafond doit être dans le code.
    effective_autonomy = min(payload.default_autonomy_level, caller_agent.default_autonomy_level)

    # 2. Préparer l'intention sous forme d'action JSON structurée
    action_args = json.dumps({
        "name": payload.name,
        "role": payload.role or "Worker",
        "default_autonomy_level": effective_autonomy,
        "objective": f"Mission initiale pour {payload.name}",
    })

    # 3. Construire la DecisionRequest officielle
    decision_req = DecisionRequest(
        workspace_id=payload.workspace_id,
        agent_id=caller_agent.id,
        objective=f"Spawn sub-agent '{payload.name}'",
        situation="Agent creation requested via API/Cockpit",
        proposed_action=f"spawn agent {action_args}",
        requested_autonomy_level=effective_autonomy,
    )


    # 4. Traitement par l'orchestrateur de décision
    arbitrator = get_arbitrator(db=db)
    orchestrator = DecisionOrchestrator(
        db=db,
        classifier=classifier,
        arbitrator=arbitrator,
        intelligence=intelligence_service,
        cognitive_simulator=cognitive_simulator,
    )
    decision_resp = await orchestrator.handle_decision(decision_req)

    # 5. Garde-fou strict : si approbation requise ou refus/escalade (cas sans config decision_domain_config)
    if (
        decision_resp.approval_required
        or not decision_resp.permission_granted
        or decision_resp.control_outcome != ControlOutcome.ALLOW
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "message": "Agent creation requires human approval. Decision escalated.",
                "decision_id": decision_resp.decision_id,
                "control_outcome": decision_resp.control_outcome.value,
                "control_reason": decision_resp.control_reason,
            },
        )

    # 6. Si autorisé (ALLOW via politique explicite), l'action a été exécutée par reliable_executor
    created_agent = (
        await db.execute(
            select(Agent)
            .where(
                Agent.name == payload.name,
                Agent.workspace_id == payload.workspace_id,
            )
            .order_by(Agent.created_at.desc())
        )
    ).scalars().first()

    if not created_agent:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Agent was authorized but creation failed in executor.",
        )

    return AgentResponse(
        id=created_agent.id,
        workspace_id=created_agent.workspace_id,
        name=created_agent.name,
        role=created_agent.role,
        is_active=created_agent.is_active,
        default_autonomy_level=created_agent.default_autonomy_level,
        parent_agent_id=payload.parent_agent_id,
        created_at=created_agent.created_at,
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
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Liste tous les Goals avec métriques d'avancement."""
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

    query = select(Goal).where(Goal.workspace_id.in_(target_ws_ids))
    if agent_id:
        query = query.where(Goal.agent_id == agent_id)
    query = query.order_by(desc(Goal.created_at))

    goals = (await db.execute(query)).scalars().all()
    if not goals:
        return []

    goal_agent_ids = {g.agent_id for g in goals}
    agents_rows = (
        await db.execute(select(Agent).where(Agent.id.in_(goal_agent_ids)))
    ).scalars().all()
    agents_by_id: dict[uuid.UUID, Agent] = {a.id: a for a in agents_rows}

    goal_ids = [g.id for g in goals]
    tasks_rows = (
        await db.execute(select(Task).where(Task.goal_id.in_(goal_ids)))
    ).scalars().all()
    tasks_by_goal: dict[uuid.UUID, list[Task]] = {}
    for t in tasks_rows:
        tasks_by_goal.setdefault(t.goal_id, []).append(t)

    summaries: List[GoalSummary] = []
    for g in goals:
        agent = agents_by_id.get(g.agent_id)
        tasks = tasks_by_goal.get(g.id, [])

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
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Retourne les détails complets d'un Goal avec son DAG de tâches et dépendances."""
    goal = (await db.execute(select(Goal).where(Goal.id == goal_id))).scalar_one_or_none()
    if not goal:
        raise HTTPException(status_code=404, detail="Goal non trouvé.")

    user_ws_ids = await get_user_workspace_ids(db, current_user)
    if goal.workspace_id not in user_ws_ids:
        raise HTTPException(status_code=404, detail="Goal non trouvé.")

    agent = (await db.execute(select(Agent).where(Agent.id == goal.agent_id))).scalar_one_or_none()
    tasks = (await db.execute(select(Task).where(Task.goal_id == goal_id).order_by(Task.created_at))).scalars().all()
    deps = (await db.execute(select(TaskDependency).where(TaskDependency.goal_id == goal_id))).scalars().all()

    # Dictionnaire des dépendances par tâche
    deps_by_task: dict[uuid.UUID, list[uuid.UUID]] = {}
    for d in deps:
        deps_by_task.setdefault(d.task_id, []).append(d.depends_on_task_id)

    task_ids = [t.id for t in tasks]
    latest_action_by_task: dict[uuid.UUID, tuple[Optional[str], Optional[str]]] = {}
    if task_ids:
        action_rows = (
            await db.execute(
                select(
                    ActionRecord.task_id,
                    ActionRecord.tool,
                    ExecutionResultRecord.output_summary,
                )
                .outerjoin(ExecutionAttempt, ExecutionAttempt.action_id == ActionRecord.id)
                .outerjoin(ExecutionResultRecord, ExecutionResultRecord.attempt_id == ExecutionAttempt.id)
                .where(ActionRecord.task_id.in_(task_ids))
                .order_by(desc(ExecutionResultRecord.created_at))
            )
        ).all()
        for row_task_id, row_tool, row_summary in action_rows:
            if row_task_id not in latest_action_by_task:
                latest_action_by_task[row_task_id] = (row_tool, row_summary)

    task_summaries = []
    for t in tasks:
        action_res = latest_action_by_task.get(t.id)
        result_text = None
        tool_name = None
        if action_res:
            tool_name = action_res[0]
            result_text = sign_preview_links(action_res[1])

        task_summaries.append(
            TaskSummary(
                id=t.id,
                goal_id=t.goal_id,
                decision_id=t.decision_id,
                description=t.description,
                status=t.status.value,
                dependencies=deps_by_task.get(t.id, []),
                created_at=t.created_at,
                updated_at=t.updated_at,
                result_summary=result_text,
                tool=tool_name,
            )
        )


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
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Crée un nouvel objectif (Goal) et peuple automatiquement ses premières tâches."""
    # 0. Vérifier l'appartenance de l'utilisateur au workspace ciblé
    await assert_workspace_member(db, current_user, payload.workspace_id)

    # 1. Vérifier que l'agent existe ET appartient au même workspace
    agent = (
        await db.execute(
            select(Agent).where(
                Agent.id == payload.agent_id,
                Agent.workspace_id == payload.workspace_id,
            )
        )
    ).scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent spécifié introuvable dans ce workspace.")

    parent_applied_autonomy = None
    if payload.parent_goal_id is not None:
        stmt_parent = select(Goal).where(
            Goal.id == payload.parent_goal_id,
            Goal.workspace_id == payload.workspace_id,
        )
        parent_goal = (await db.execute(stmt_parent)).scalar_one_or_none()
        if parent_goal is None:
            raise HTTPException(status_code=404, detail=f"Objectif parent '{payload.parent_goal_id}' introuvable.")
        parent_applied_autonomy = parent_goal.applied_autonomy_level

    # Calcul de l'autonomie appliquée déterministe
    applied_autonomy = GoalManager.calculate_applied_autonomy(
        requested_autonomy_level=payload.requested_autonomy_level,
        agent_default_autonomy=agent.default_autonomy_level,
        parent_applied_autonomy=parent_applied_autonomy,
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

    is_generic_task = (
        payload.initial_tasks
        and len(payload.initial_tasks) == 1
        and any(
            payload.initial_tasks[0].lower().startswith(prefix)
            for prefix in ("analyse et exécution", "exécuter mission", "mission:")
        )
    )

    if payload.initial_tasks and not is_generic_task:
        task_descriptions = payload.initial_tasks
    else:
        obj_lower = payload.objective.lower()
        creation_keywords = (
            "crée", "créer", "création", "génère", "générer", "génération",
            "développe", "développer", "site", "web", "page", "système",
            "systeme", "code", "coder", "build", "frontend", "interface"
        )
        if any(kw in obj_lower for kw in creation_keywords):
            task_descriptions = [
                f"Génération du code source et création des fichiers : {payload.objective}",
                "Vérification du système et rapport de livraison (system.read)",
            ]
        elif any(kw in obj_lower for kw in ("cherche", "recherche", "actus", "news", "veille", "trouve")):
            task_descriptions = [
                f"Recherche et veille informationnelle : {payload.objective}",
                "Synthèse et rapport d'exécution déterministe",
            ]
        else:
            task_descriptions = [
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
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
    classifier: DomainClassifier = Depends(get_classifier),
    arbitrator: DeterministicArbitrator = Depends(get_arbitrator),
    intelligence_service: IntelligenceService = Depends(get_intelligence_service),
    cognitive_simulator: CognitiveSimulator = Depends(get_cognitive_simulator),
):
    """Déclenche 1 cycle autonome atomique (wake_goal) sur l'objectif désigné."""
    goal = (await db.execute(select(Goal).where(Goal.id == goal_id))).scalar_one_or_none()
    if not goal:
        raise HTTPException(status_code=404, detail="Goal non trouvé.")

    user_ws_ids = await get_user_workspace_ids(db, current_user)
    if goal.workspace_id not in user_ws_ids:
        raise HTTPException(status_code=404, detail="Goal non trouvé.")

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

class WebhookTriggerRequest(BaseModel):
    workspace_id: uuid.UUID
    agent_id: uuid.UUID
    objective: str
    priority: int = 1
    api_key: str = Field(..., description="Clé de sécurité basique")

@router.post("/webhooks/trigger", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def webhook_trigger(
    payload: WebhookTriggerRequest,
):
    """Endpoint neutralisé pour remédiation de sécurité.
    
    L'authentification par clé statique en clair est révoquée.
    Utiliser les endpoints Inbound gouvernés avec signature HMAC.
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Endpoint disabled for security remediation (hardcoded key revoked). Use governed inbound endpoints.",
    )



@router.get("/telemetry", response_model=List[TelemetryEvent])
async def get_telemetry_events(
    limit: int = Query(default=30, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Retourne les flux de décisions et exécutions récentes pour le HUD holographique."""
    events: List[TelemetryEvent] = []

    user_ws_ids = await get_user_workspace_ids(db, current_user)
    if not user_ws_ids:
        return []

    # Dernières décisions
    stmt_decisions = (
        select(Decision)
        .where(Decision.workspace_id.in_(user_ws_ids))
        .order_by(desc(Decision.created_at))
        .limit(limit)
    )
    decisions = (await db.execute(stmt_decisions)).scalars().all()

    dec_agent_ids = {d.agent_id for d in decisions}
    agents_by_id: dict[uuid.UUID, Agent] = {}
    if dec_agent_ids:
        agents_rows = (
            await db.execute(select(Agent).where(Agent.id.in_(dec_agent_ids)))
        ).scalars().all()
        agents_by_id = {a.id: a for a in agents_rows}

    for d in decisions:
        agent = agents_by_id.get(d.agent_id)
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
    stmt_execs = (
        select(ExecutionResultRecord)
        .join(ExecutionAttempt, ExecutionResultRecord.attempt_id == ExecutionAttempt.id)
        .where(ExecutionAttempt.workspace_id.in_(user_ws_ids))
        .order_by(desc(ExecutionResultRecord.created_at))
        .limit(limit)
    )
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
                    "output_preview": (ex.output_summary or "")[:120],
                },
            )
        )

    # Trier par timestamp descendant
    events.sort(key=lambda x: x.timestamp, reverse=True)
    return events[:limit]


@router.get("/workspaces/{workspace_id}/preview/{filepath:path}")
async def preview_workspace_file(
    workspace_id: uuid.UUID,
    filepath: str,
    exp: Optional[int] = Query(default=None),
    sig: Optional[str] = Query(default=None),
    current_user: Optional[User] = Depends(get_optional_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Sert un fichier généré dans le workspace pour prévisualisation directe (HTML, CSS, JS, etc.).

    Accès accordé si (a) une signature HMAC valide (exp, sig) est fournie, ou
    (b) l'appelant est authentifié ET membre du workspace. Sinon 401/403.
    """
    if sig is not None or exp is not None:
        if not verify_preview(workspace_id, filepath, exp, sig):
            raise HTTPException(status_code=403, detail="Lien de prévisualisation invalide ou expiré.")
    elif current_user is not None:
        await assert_workspace_member(db, current_user, workspace_id)
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentification requise.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    workspace_dir = (Path(settings.WORKSPACES_ROOT) / str(workspace_id)).resolve()
    target_path = (workspace_dir / filepath).resolve()

    try:
        target_path.relative_to(workspace_dir)
    except ValueError:
        raise HTTPException(status_code=403, detail="Accès non autorisé hors des limites du workspace.")

    if not target_path.exists() or not target_path.is_file():
        raise HTTPException(status_code=404, detail=f"Fichier '{filepath}' introuvable dans le workspace.")

    mime_type, _ = mimetypes.guess_type(str(target_path))
    return FileResponse(
        path=str(target_path),
        media_type=mime_type or "text/plain",
        filename=target_path.name,
        headers={
            "Content-Security-Policy": "sandbox allow-scripts; default-src 'self' 'unsafe-inline' https: data:",
            "X-Content-Type-Options": "nosniff",
        },
    )

