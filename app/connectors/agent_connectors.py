import uuid
import logging
from decimal import Decimal

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.execution.models import ActionRecord
from app.execution.services.executor import ExecutionResult
from app.identity.models import Agent
from app.goal_engine.models import Goal, GoalStatus
from app.task_engine.models import Task, TaskStatus, TaskDependency

logger = logging.getLogger(__name__)

async def agent_spawn_handler(action: ActionRecord) -> ExecutionResult:
    """Connecteur 'agent.spawn' pour l'Inception (création de sous-agents)."""
    args = action.arguments or {}
    name = args.get("name")
    role = args.get("role", "Sub-Agent Worker")
    objective = args.get("objective")
    
    if not name or not objective:
        return ExecutionResult(
            success=False, 
            output=None, 
            error="Missing 'name' or 'objective' arguments",
            error_code="MISSING_ARGS"
        )
        
    try:
        # Ouvrir une session autonome pour créer l'agent
        async with AsyncSessionLocal() as db:
            # 0. Récupération du contexte parent pour borner l'autonomie
            parent_autonomy = None
            if action.agent_id:
                stmt_pagent = select(Agent).where(Agent.id == action.agent_id)
                res_agent = await db.execute(stmt_pagent)
                parent_agent = res_agent.scalar_one_or_none() if hasattr(res_agent, "scalar_one_or_none") else None
                if parent_agent and hasattr(parent_agent, "default_autonomy_level") and isinstance(parent_agent.default_autonomy_level, int):
                    parent_autonomy = parent_agent.default_autonomy_level

            parent_goal_id = None
            parent_goal_autonomy = None
            if action.task_id:
                stmt_ptask = select(Task).where(Task.id == action.task_id)
                res_task = await db.execute(stmt_ptask)
                ptask = res_task.scalar_one_or_none() if hasattr(res_task, "scalar_one_or_none") else None
                if ptask and hasattr(ptask, "goal_id") and ptask.goal_id:
                    parent_goal_id = ptask.goal_id
                    stmt_pgoal = select(Goal).where(Goal.id == ptask.goal_id)
                    res_goal = await db.execute(stmt_pgoal)
                    pgoal = res_goal.scalar_one_or_none() if hasattr(res_goal, "scalar_one_or_none") else None
                    if pgoal and hasattr(pgoal, "applied_autonomy_level") and isinstance(pgoal.applied_autonomy_level, int):
                        parent_goal_autonomy = pgoal.applied_autonomy_level

            caps = [c for c in (parent_goal_autonomy, parent_autonomy) if c is not None]
            effective_parent_cap = min(caps) if caps else None

            req_autonomy = int(args.get("requested_autonomy_level", 2))
            child_default = int(args.get("default_autonomy_level", 2))
            if effective_parent_cap is not None:
                child_default = min(child_default, effective_parent_cap)

            from app.goal_engine.services.goal_manager import GoalManager

            child_applied_autonomy = GoalManager.calculate_applied_autonomy(
                requested_autonomy_level=req_autonomy,
                agent_default_autonomy=child_default,
                parent_applied_autonomy=effective_parent_cap,
            )

            # 1. Création de l'Agent
            new_agent = Agent(
                id=uuid.uuid4(),
                workspace_id=action.workspace_id,
                name=name,
                role=role,
                is_active=True,
                default_autonomy_level=child_default,
            )
            db.add(new_agent)
            
            # 2. Création du Goal assigné
            new_goal = Goal(
                id=uuid.uuid4(),
                workspace_id=action.workspace_id,
                agent_id=new_agent.id,
                objective=objective,
                status=GoalStatus.ACTIVE,
                priority=1,
                requested_autonomy_level=req_autonomy,
                applied_autonomy_level=child_applied_autonomy,
                parent_goal_id=parent_goal_id,
                goal_metadata={"spawned_by_decision": str(action.decision_id), "spawned_by": str(action.agent_id), "limits": {"max_steps": 10}},
            )

            db.add(new_goal)
            
            # 3. Première tâche minimale pour l'agent
            t = Task(
                id=uuid.uuid4(),
                goal_id=new_goal.id,
                description=f"Analyse initiale et cartographie de l'objectif : {objective}",
                status=TaskStatus.READY,
            )
            db.add(t)
            
            await db.commit()
            
            output = f"Successfully spawned sub-agent '{name}' (ID: {new_agent.id}) with objective '{objective}'. Goal ID: {new_goal.id}."
            logger.info(f"[AGENT SPAWN] {output}")
            
            return ExecutionResult(success=True, output=output, error=None, cost_amount=Decimal("0.0"), cost_unit="credits")
            
    except Exception as e:
        logger.error(f"[AGENT SPAWN] Error: {e}")
        return ExecutionResult(success=False, output=None, error=str(e), error_code="SPAWN_ERROR")
