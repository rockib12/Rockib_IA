"""Tâches Celery pour le Goal Engine et l'Exécution Autonome (STEP 5B/5C).

Conforme au contrat d'architecture :
- Pas de boucle while interne dans le serveur web FastAPI.
- dispatch_active_goals est appelé périodiquement par Celery Beat.
- Chaque wake_goal_task(goal_id) exécute exactement UN appel atomique à wake_goal().
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, Dict, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.celery_app import celery_app
from app.core.database import async_engine, AsyncSessionLocal
from app.core.dependencies import (
    get_arbitrator,
    get_classifier,
    get_cognitive_simulator,
    get_intelligence_service,
)
from app.decision_engine.services.orchestrator import DecisionOrchestrator
from app.goal_engine.models import Goal, GoalStatus
from app.goal_engine.services.autonomous_loop import WakeResult, wake_goal
from app.execution.services.system_handlers import install_production_handlers

logger = logging.getLogger(__name__)

# Enregistre tous les handlers de production dans le worker Celery
install_production_handlers()


async def _dispatch_active_goals_async() -> List[str]:
    """Interroge les Goals au statut ACTIVE sans bloquer l'Event Loop."""
    async with AsyncSessionLocal() as session:
        try:
            stmt = (
                select(Goal.id)
                .where(
                    Goal.status == GoalStatus.ACTIVE,
                    Goal.objective != "STEP 5C concurrency probe",
                )
                .order_by(Goal.priority.desc(), Goal.created_at.asc())
            )
            result = await session.execute(stmt)
            return [str(gid) for gid in result.scalars().all()]
        finally:
            await session.rollback()


_worker_loop: Optional[asyncio.AbstractEventLoop] = None


def _get_worker_loop() -> asyncio.AbstractEventLoop:
    global _worker_loop
    if _worker_loop is None or _worker_loop.is_closed():
        _worker_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_worker_loop)
    return _worker_loop


def _run_async(coro):
    loop = _get_worker_loop()
    return loop.run_until_complete(coro)


@celery_app.task(name="app.goal_engine.tasks.dispatch_active_goals")
def dispatch_active_goals() -> str:
    """Tâche périodique Celery Beat.
    
    Liste tous les Goals ACTIVE et planifie une tâche wake_goal_task individuelle
    par Goal dans la queue Celery (Redis).
    """
    try:
        goal_ids = _run_async(_dispatch_active_goals_async())
        for gid in goal_ids:
            wake_goal_task.delay(gid)
        return f"Dispatched wake task for {len(goal_ids)} active goal(s)."
    except Exception as exc:
        logger.error(f"Error in dispatch_active_goals: {exc}", exc_info=True)
        raise exc


async def _wake_single_goal_async(goal_id_str: str) -> Dict[str, Any]:
    """Exécute une seule admission / étape de wake_goal() pour un goal donné."""
    goal_id = uuid.UUID(goal_id_str)
    async with AsyncSessionLocal() as session:
        classifier = get_classifier()
        cog_sim = get_cognitive_simulator()
        intel_svc = get_intelligence_service()

        def orchestrator_factory(s: AsyncSession) -> DecisionOrchestrator:
            return DecisionOrchestrator(
                db=s,
                classifier=classifier,
                arbitrator=get_arbitrator(db=s),
                intelligence=intel_svc,
                cognitive_simulator=cog_sim,
            )

        res: WakeResult = await wake_goal(
            session,
            goal_id=goal_id,
            orchestrator_factory=orchestrator_factory,
        )
        return {
            "status": res.status,
            "task_id": str(res.task_id) if res.task_id else None,
            "execution_effect": res.execution_effect,
            "execution_output": res.execution_output,
            "violations": res.violations,
        }


@celery_app.task(name="app.goal_engine.tasks.wake_goal_task", bind=True, max_retries=3)
def wake_goal_task(self, goal_id: str) -> Dict[str, Any]:
    """Tâche exécutée par les workers Celery.
    
    Exécute strictement UN cycle d'admission / transition pour le Goal spécifié,
    sans aucune boucle while. Si un crash survient (SIGKILL / OOM), le mécanisme M6
    d'orphelin prendra le relais au cycle suivant.
    """
    try:
        return _run_async(_wake_single_goal_async(goal_id))
    except Exception as exc:
        logger.error(f"Error executing wake_goal_task for goal {goal_id}: {exc}", exc_info=True)
        raise exc
