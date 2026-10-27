import uuid
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import select, or_

from app.core.database import AsyncSessionLocal
from app.execution.models import ActionRecord
from app.execution.services.executor import ExecutionResult
from app.identity.models import Agent, AgentMessage
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
            pgoal = None
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

            # Monotonie budgétaire parent-enfant (FIN-INV-09)
            from app.execution.services.financial_governance import (
                validate_parent_child_ceiling,
                FinancialGovernanceError,
            )
            child_ceiling = args.get("budget_ceiling")
            child_currency = args.get("budget_currency") or "EUR"
            if child_ceiling is not None:
                parent_ceiling = None
                parent_currency = "EUR"
                if pgoal and pgoal.goal_metadata:
                    parent_ceiling = pgoal.goal_metadata.get("budget_ceiling")
                    parent_currency = pgoal.goal_metadata.get("budget_currency", "EUR")
                if parent_ceiling is not None:
                    try:
                        validate_parent_child_ceiling(
                            parent_ceiling_amount=parent_ceiling,
                            parent_ceiling_currency=parent_currency,
                            child_ceiling_amount=child_ceiling,
                            child_ceiling_currency=child_currency,
                        )
                    except FinancialGovernanceError as e:
                        return ExecutionResult(
                            success=False,
                            output=None,
                            error=f"Parent-child budget ceiling violation: {e}",
                            error_code="BUDGET_CEILING_VIOLATION",
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
            await db.flush()
            
            # 2. Création du Goal assigné
            goal_meta = {
                "spawned_by_decision": str(action.decision_id),
                "spawned_by": str(action.agent_id),
                "limits": {"max_steps": 10},
            }
            if child_ceiling is not None:
                goal_meta["budget_ceiling"] = str(child_ceiling)
                goal_meta["budget_currency"] = child_currency

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
                goal_metadata=goal_meta,
            )

            db.add(new_goal)
            await db.flush()
            
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


async def agent_message_handler(action: ActionRecord) -> ExecutionResult:
    """Connecteur P2P 'agent.send' / 'agent.message' permettant aux agents de dialoguer entre eux."""
    args = action.arguments or {}
    recipient_id_raw = args.get("recipient_agent_id") or args.get("to_agent_id") or args.get("target_agent_id")
    recipient_name = args.get("recipient_name") or args.get("to_agent")
    subject = args.get("subject") or "Collaboration P2P Inter-Agents"
    message_text = args.get("message") or args.get("content") or action.objective

    if not message_text:
        return ExecutionResult(
            success=False,
            output=None,
            error="Missing 'message' or 'content' for inter-agent dialogue",
            error_code="MISSING_MESSAGE",
        )

    try:
        async with AsyncSessionLocal() as db:
            sender_agent = (await db.execute(select(Agent).where(Agent.id == action.agent_id))).scalar_one_or_none()
            sender_name = sender_agent.name if sender_agent else "Agent Émetteur"

            recipient_agent: Optional[Agent] = None
            if recipient_id_raw:
                try:
                    rid = uuid.UUID(str(recipient_id_raw))
                    recipient_agent = (
                        await db.execute(
                            select(Agent).where(Agent.id == rid, Agent.workspace_id == action.workspace_id)
                        )
                    ).scalar_one_or_none()
                except (ValueError, TypeError):
                    pass

            if not recipient_agent and recipient_name:
                recipient_agent = (
                    await db.execute(
                        select(Agent).where(
                            Agent.workspace_id == action.workspace_id,
                            or_(
                                Agent.name.ilike(f"%{recipient_name}%"),
                                Agent.role.ilike(f"%{recipient_name}%"),
                            ),
                        )
                    )
                ).scalars().first()

            if not recipient_agent:
                # Reconnaissance vectorielle Gemma-2 : trouver l'agent pair dont le rôle correspond le mieux au besoin
                peer_candidates = list(
                    (
                        await db.execute(
                            select(Agent).where(
                                Agent.workspace_id == action.workspace_id,
                                Agent.id != action.agent_id,
                                Agent.is_active == True,
                            )
                        )
                    ).scalars().all()
                )
                if peer_candidates:
                    try:
                        from app.intelligence.services.gemma_recognition import GemmaRecognitionEngine
                        recipient_agent, _ = await GemmaRecognitionEngine.recognize_best_peer_agent(
                            message_text=message_text,
                            subject=subject,
                            candidate_agents=peer_candidates,
                        )
                    except Exception:
                        recipient_agent = peer_candidates[0]

            if not recipient_agent:
                return ExecutionResult(
                    success=False,
                    output=None,
                    error="No recipient peer agent found in workspace.",
                    error_code="PEER_NOT_FOUND",
                )

            # Génération d'une réponse P2P intelligente du pair (Groq ou synthèse déterministe)
            reply_text = f"Bien reçu {sender_name}. En tant que {recipient_agent.role or recipient_agent.name}, j'intègre ta demande ('{message_text[:80]}') dans mon plan d'exécution et je synchronise le contrat technique."
            try:
                from app.intelligence.services.providers.groq_provider import GroqProvider
                provider = GroqProvider()
                prompt = (
                    f"Tu es l'agent IA '{recipient_agent.name}' (Rôle: {recipient_agent.role}) dans le système Rockib IA.\n"
                    f"Ton collègue '{sender_name}' (Rôle: {sender_agent.role if sender_agent else 'Peer'}) t'envoie ce message P2P :\n"
                    f"Sujet : {subject}\n"
                    f"Message : {message_text}\n\n"
                    "Réponds de façon concise (2-3 phrases max), technique, collaborative et orientée action immédiate."
                )
                llm_reply = await provider.generate(prompt)
                if llm_reply and len(llm_reply.strip()) > 5:
                    reply_text = llm_reply.strip()
            except Exception as llm_exc:
                logger.debug("Fallback déterministe pour réponse P2P: %s", llm_exc)

            # Enregistrer le message P2P dans agent_messages
            msg_record = AgentMessage(
                id=uuid.uuid4(),
                workspace_id=action.workspace_id,
                sender_agent_id=action.agent_id,
                recipient_agent_id=recipient_agent.id,
                subject=subject,
                content=message_text,
                status="REPLIED",
                reply_content=reply_text,
                metadata_json={"decision_id": str(action.decision_id), "task_id": str(action.task_id) if action.task_id else None},
                replied_at=datetime.now(timezone.utc),
            )
            db.add(msg_record)

            # Mémoriser également cet accord inter-agents dans la mémoire vectorielle (P1)
            try:
                from app.memory.services.ingestion import store_agent_lesson
                await store_agent_lesson(
                    db=db,
                    workspace_id=action.workspace_id,
                    agent_id=recipient_agent.id,
                    lesson_text=f"Dialogue P2P [{sender_name} -> {recipient_agent.name}] ({subject}) : {message_text} | Réponse : {reply_text}",
                    memory_type="project_memory",
                    confidence=0.92,
                    importance=0.85,
                    metadata={"p2p_message_id": str(msg_record.id), "sender_id": str(action.agent_id)},
                )
            except Exception as mem_exc:
                logger.warning("Échec non-bloquant d'indexation vectorielle du message P2P: %s", mem_exc)

            await db.commit()

            output_str = f"P2P [{sender_name} -> {recipient_agent.name}]: '{message_text}' | Reply: '{reply_text}'"
            return ExecutionResult(
                success=True,
                output=output_str,
                error=None,
                provider_reference="agent:p2p_dialogue",
                cost_amount=Decimal("0.0"),
                cost_unit="credits",
            )
    except Exception as e:
        logger.error(f"[AGENT P2P] Error: {e}")
        return ExecutionResult(success=False, output=None, error=str(e), error_code="P2P_ERROR")
