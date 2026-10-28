"""
P6 — Auto-Swarm Spawner : Décomposition Automatique d'un Goal Complexe en Sous-Agents Spécialisés 3D.

Respecte strictement tous les invariants de gouvernance :
- Monotonie d'autonomie : child_autonomy <= parent_applied_autonomy (SKILL-INV-02 / STEP 6G).
- Chaque sous-agent reçoit son sous-Goal dédié lié par `parent_goal_id`, une tâche READY
  et un message P2P initial de synchronisation avec l'Orchestrateur parent (visible en 3D).
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.goal_engine.models import Goal, GoalStatus
from app.identity.models import Agent, AgentMessage
from app.intelligence.services.gemma_recognition import GemmaRecognitionEngine
from app.task_engine.models import Task, TaskStatus

logger = logging.getLogger(__name__)


SPECIALIST_BLUEPRINTS: List[Dict[str, str]] = [
    {
        "key": "architect",
        "name_prefix": "Architecte Système",
        "role": "Lead System & Database Architect",
        "focus": "Conception de l'architecture, schémas PostgreSQL/pgvector et contrats d'API",
    },
    {
        "key": "builder",
        "name_prefix": "Ingénieur Exécution",
        "role": "Fullstack & Sandbox Code Engineer",
        "focus": "Implémentation du code, compilation en Sandbox isolée (P3) et validation fonctionnelle",
    },
    {
        "key": "secops",
        "name_prefix": "Sentinelle Cyber",
        "role": "Cybersecurity OWASP & Zero-Trust Auditor",
        "focus": "Audit statique SAST, vérification des permissions déterministes et étanchéité multi-tenant",
    },
]


class AutoSwarmSpawner:
    """Déploie automatiquement une escouade de sous-agents 3D spécialisés autour d'un Goal parent."""

    @classmethod
    async def spawn_swarm_for_goal(
        cls,
        db: AsyncSession,
        goal_id: uuid.UUID,
        max_sub_agents: int = 3,
    ) -> Dict[str, Any]:
        parent_goal = (
            await db.execute(select(Goal).where(Goal.id == goal_id))
        ).scalar_one_or_none()
        if not parent_goal:
            raise ValueError(f"Goal '{goal_id}' introuvable.")

        parent_agent = (
            await db.execute(select(Agent).where(Agent.id == parent_goal.agent_id))
        ).scalar_one_or_none()
        if not parent_agent:
            raise ValueError("Agent parent introuvable pour ce Goal.")

        # Invariant monotone strict : child_autonomy <= min(parent_agent.default, parent_goal.applied)
        bounded_autonomy = max(
            0,
            min(
                int(parent_agent.default_autonomy_level or 1),
                int(parent_goal.applied_autonomy_level or 1),
            ),
        )

        # Reconnaissance Gemma-2 du domaine principal de l'objectif
        domain_res, domain_diag = await GemmaRecognitionEngine.recognize_domain(
            proposed_action=parent_goal.objective,
            objective=parent_goal.objective,
        )
        detected_domain = domain_res.domain or "system"

        selected_blueprints = SPECIALIST_BLUEPRINTS[: max(1, min(max_sub_agents, 3))]
        spawned_units: List[Dict[str, Any]] = []
        now_utc = datetime.now(timezone.utc)

        for idx, bp in enumerate(selected_blueprints, start=1):
            sub_agent_id = uuid.uuid4()
            short_tag = str(sub_agent_id)[:4].upper()
            sub_name = f"{bp['name_prefix']} #{short_tag}"

            sub_agent = Agent(
                id=sub_agent_id,
                workspace_id=parent_goal.workspace_id,
                name=sub_name,
                role=bp["role"],
                is_active=True,
                default_autonomy_level=bounded_autonomy,
            )
            db.add(sub_agent)
            await db.flush()

            sub_objective = f"[{bp['name_prefix']}] {bp['focus']} pour : {parent_goal.objective[:140]}"
            sub_goal = Goal(
                id=uuid.uuid4(),
                workspace_id=parent_goal.workspace_id,
                agent_id=sub_agent.id,
                parent_goal_id=parent_goal.id,
                objective=sub_objective,
                status=GoalStatus.ACTIVE,
                priority=parent_goal.priority,
                requested_autonomy_level=bounded_autonomy,
                applied_autonomy_level=bounded_autonomy,
                goal_metadata={
                    "parent_agent_id": str(parent_agent.id),
                    "swarm_role": bp["key"],
                    "detected_domain": detected_domain,
                    "limits": {"max_steps": 10, "max_replanning_count": 2},
                    "usage": {"current_steps": 0, "replanning_count": 0},
                },
            )
            db.add(sub_goal)
            await db.flush()

            sub_task = Task(
                id=uuid.uuid4(),
                goal_id=sub_goal.id,
                description=f"Exécuter le volet {bp['key']} ({bp['focus']}) — Domaine: {detected_domain}",
                status=TaskStatus.READY,
            )
            db.add(sub_task)

            # Créer le contrat synaptique P2P initial entre l'Orchestrateur et le Sous-Agent
            p2p_msg = AgentMessage(
                id=uuid.uuid4(),
                workspace_id=parent_goal.workspace_id,
                sender_agent_id=parent_agent.id,
                recipient_agent_id=sub_agent.id,
                subject=f"[Swarm P6 #{idx}] Délégation {bp['name_prefix']}",
                content=f"Délégation du sous-objectif '{bp['focus']}' sous autonomie bornée niveau {bounded_autonomy}.",
                status="REPLIED",
                reply_content=(
                    f"[{sub_name}] Mission reçue de {parent_agent.name}. "
                    f"J'initialise l'exécution pour le domaine '{detected_domain}' en respectant le plafond d'autonomie {bounded_autonomy}."
                ),
                metadata_json={"swarm_goal_id": str(parent_goal.id), "sub_goal_id": str(sub_goal.id)},
                replied_at=now_utc,
            )
            db.add(p2p_msg)

            spawned_units.append(
                {
                    "agent_id": str(sub_agent.id),
                    "agent_name": sub_agent.name,
                    "role": sub_agent.role,
                    "parent_agent_id": str(parent_agent.id),
                    "sub_goal_id": str(sub_goal.id),
                    "sub_task_id": str(sub_task.id),
                    "applied_autonomy_level": bounded_autonomy,
                    "p2p_message_id": str(p2p_msg.id),
                }
            )

        await db.commit()

        return {
            "parent_goal_id": str(parent_goal.id),
            "parent_agent_id": str(parent_agent.id),
            "parent_agent_name": parent_agent.name,
            "detected_domain": detected_domain,
            "domain_diagnostics": domain_diag,
            "bounded_autonomy_level": bounded_autonomy,
            "spawned_count": len(spawned_units),
            "swarm_units": spawned_units,
        }
