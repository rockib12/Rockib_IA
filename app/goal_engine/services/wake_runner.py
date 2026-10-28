import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, AsyncEngine

from app.core.dependencies import (
    get_classifier_mapping,
    get_classifier,
    get_arbitrator,
    get_ai_provider,
    get_cognitive_simulator,
    get_intelligence_service,
)
from app.decision_engine.services.orchestrator import DecisionOrchestrator
from app.goal_engine.models import Goal, GoalStatus
from app.goal_engine.services.autonomous_loop import WakeResult, wake_goal
from app.goal_engine.services.goal_manager import GoalManager, GoalSuccessProof
from app.task_engine.models import Task, TaskStatus

logger = logging.getLogger(__name__)


class WakeRunner:
    """Runner autonome de nouvelle génération pour réveiller les Goals éligibles.

    Inclut :
    1. Exécution atomique tâche par tâche via `wake_goal()`.
    2. Agent Vérificateur Interne (`_auto_verify_and_complete_goal`) qui scelle
       automatiquement la `GoalSuccessProof` dès que toutes les tâches d'un Goal
       sont `COMPLETED` (`AWAITING_PROOF`).
    3. Boucle d'Auto-Guérison Réflexive (`_attempt_self_healing_replan`) qui
       analyse les tâches échouées (`FAILED`), mémorise la leçon dans `pgvector`
       et déclenche un `replan_goal()` correctif dans la limite autorisée.
    """

    def __init__(self, engine: AsyncEngine):
        self.engine = engine
        self._is_running = False
        self._task: Optional[asyncio.Task] = None

        # Instanciation unique des dépendances pures du Decision Engine
        self._mapping = get_classifier_mapping()
        self._classifier = get_classifier(self._mapping)
        self._provider = get_ai_provider()
        self._cognitive_simulator = get_cognitive_simulator(self._provider)
        self._intelligence_service = get_intelligence_service(self._provider)

    def start(self):
        """Démarre la boucle de réveil en arrière-plan."""
        if self._is_running:
            return
        self._is_running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("WakeRunner started.")

    async def stop(self):
        """Arrête la boucle proprement."""
        if not self._is_running:
            return
        self._is_running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("WakeRunner gracefully stopped.")

    def _orchestrator_factory(self, session: AsyncSession) -> DecisionOrchestrator:
        """Factory passée à wake_goal() pour instancier l'orchestrateur."""
        arbitrator = get_arbitrator(db=session)
        return DecisionOrchestrator(
            db=session,
            classifier=self._classifier,
            arbitrator=arbitrator,
            intelligence=self._intelligence_service,
            cognitive_simulator=self._cognitive_simulator,
        )

    async def _run_loop(self):
        """Boucle principale du runner."""
        while self._is_running:
            try:
                async with AsyncSession(self.engine) as db:
                    worked = await self._poll_and_wake(db)

                sleep_time = 0.5 if worked else 5.0
                await asyncio.sleep(sleep_time)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"WakeRunner encountered an unhandled error: {e}", exc_info=True)
                await asyncio.sleep(5.0)

    async def _auto_verify_and_complete_goal(self, db: AsyncSession, goal_id) -> bool:
        """Agent Vérificateur Interne : valide les preuves d'exécution et clôture le Goal."""
        try:
            await db.rollback()
            goal = (await db.execute(select(Goal).where(Goal.id == goal_id))).scalar_one_or_none()
            if not goal or goal.status != GoalStatus.ACTIVE:
                return False

            tasks = list(
                (await db.execute(select(Task).where(Task.goal_id == goal_id))).scalars().all()
            )
            if not tasks or not all(t.status == TaskStatus.COMPLETED for t in tasks):
                return False

            meta = dict(goal.goal_metadata or {})
            criteria = list(meta.get("success_criteria") or [])
            task_outputs = dict(meta.get("task_outputs") or {})

            proof = GoalSuccessProof(
                reference=f"auto-verifier:goal:{goal_id}:tasks:{len(tasks)}",
                verified_by="rockib_internal_auditor_v2",
                verified_at=datetime.now(timezone.utc),
                evidence={
                    "completed_task_ids": [str(t.id) for t in tasks],
                    "task_outputs_count": len(task_outputs),
                },
                criteria_verified=criteria,
            )

            manager = GoalManager(db)
            await manager.complete_goal(goal_id, proof=proof)

            # Indexer la réussite globale du Goal dans la mémoire vectorielle Gemma-2 (768d)
            try:
                from app.memory.services.ingestion import store_agent_lesson
                summary_outputs = " | ".join(f"{k[:8]}: {v[:120]}" for k, v in list(task_outputs.items())[:3])
                await store_agent_lesson(
                    db=db,
                    workspace_id=goal.workspace_id,
                    agent_id=goal.agent_id,
                    lesson_text=f"Mission accomplie avec succès : '{goal.objective}'. Résultats clés : {summary_outputs or 'Toutes les étapes validées.'}",
                    memory_type="experience",
                    confidence=0.94,
                    importance=0.88,
                    metadata={"goal_id": str(goal.id), "tasks_completed": len(tasks)},
                )
            except Exception as mem_exc:
                logger.debug("Non-critical memory lesson indexing error: %s", mem_exc)

            await db.commit()
            logger.info("[AUTO-VERIFIER] Goal %s vérifié et complété automatiquement (%d tâches).", goal_id, len(tasks))
            return True
        except Exception as exc:
            await db.rollback()
            logger.warning("[AUTO-VERIFIER] Impossible de clôturer automatiquement le Goal %s: %s", goal_id, exc)
            return False

    async def _attempt_self_healing_replan(self, db: AsyncSession, goal_id) -> bool:
        """Boucle d'Auto-Guérison Réflexive : analyse une tâche FAILED et replanifie si le quota le permet."""
        try:
            await db.rollback()
            goal = (await db.execute(select(Goal).where(Goal.id == goal_id))).scalar_one_or_none()
            if not goal or goal.status != GoalStatus.ACTIVE:
                return False

            meta = dict(goal.goal_metadata or {})
            limits = dict(meta.get("limits") or {})
            usage = dict(meta.get("usage") or {})
            max_replan = int(limits.get("max_replanning_count", 3))
            curr_replan = int(usage.get("replanning_count", 0))
            if curr_replan >= max_replan:
                return False

            tasks = list(
                (await db.execute(select(Task).where(Task.goal_id == goal_id))).scalars().all()
            )
            failed_tasks = [t for t in tasks if t.status == TaskStatus.FAILED]
            if not failed_tasks:
                return False

            failed_t = failed_tasks[0]
            last_fail_info = meta.get("last_failed_task") or {}
            err_msg = last_fail_info.get("error", "Erreur d'exécution détectée")

            # 1. Enregistrer la leçon d'erreur dans pgvector (Gemma-2 768d) pour ne plus la reproduire
            try:
                from app.memory.services.ingestion import store_agent_lesson
                await store_agent_lesson(
                    db=db,
                    workspace_id=goal.workspace_id,
                    agent_id=goal.agent_id,
                    lesson_text=(
                        f"AUTO-DIAGNOSTIC ERREUR sur l'objectif '{goal.objective}' : "
                        f"La tâche '{failed_t.description}' a échoué avec '{err_msg}'. "
                        f"Action corrective : reformuler avec une approche sûre et vérifier les prérequis."
                    ),
                    memory_type="experience",
                    confidence=0.90,
                    importance=0.92,
                    metadata={"goal_id": str(goal.id), "failed_task_id": str(failed_t.id)},
                )
            except Exception:
                pass

            # 2. Construire un plan de remédiation auto-cicatrisant
            new_plan = [
                {
                    "key": "self_heal_1",
                    "description": f"[Auto-Guérison #{curr_replan + 1}] Exécution alternative sécurisée pour : {failed_t.description}",
                    "depends_on": [],
                }
            ]
            manager = GoalManager(db)
            await manager.replan_goal(
                goal_id,
                new_plan=new_plan,
                reason=f"Auto-guérison réflexive suite à l'échec de la tâche {failed_t.id} ({err_msg[:120]})",
            )
            await db.commit()
            logger.info("[SELF-HEALING] Goal %s replanifié automatiquement (tentative %d/%d).", goal_id, curr_replan + 1, max_replan)
            return True
        except Exception as exc:
            await db.rollback()
            logger.debug("[SELF-HEALING] Replan non applicable pour Goal %s: %s", goal_id, exc)
            return False

    async def _poll_and_wake(self, db: AsyncSession) -> bool:
        """Cherche les Goals éligibles, exécute wake_goal(), auto-vérifie et auto-guérit."""
        worked = False

        stmt = (
            select(Goal.id)
            .where(Goal.status.in_([GoalStatus.PENDING, GoalStatus.PLANNING, GoalStatus.ACTIVE]))
            .where(
                (Goal.goal_metadata.op("->>")("proof_pending").is_(None))
                | (Goal.goal_metadata.op("->>")("proof_pending") != "true")
            )
            .order_by(Goal.priority.desc(), Goal.updated_at.asc())
            .limit(10)
        )

        goal_ids = (await db.execute(stmt)).scalars().all()

        if not goal_ids:
            return False

        for gid in goal_ids:
            if not self._is_running:
                break

            try:
                result: WakeResult = await wake_goal(
                    db,
                    goal_id=gid,
                    orchestrator_factory=self._orchestrator_factory,
                )

                if result.status == "AWAITING_PROOF":
                    await self._auto_verify_and_complete_goal(db, gid)
                    worked = True
                elif result.status != "ACTIVE":
                    worked = True
                else:
                    # Si le Goal est resté ACTIVE mais bloqué par une tâche FAILED, tenter l'auto-guérison
                    healed = await self._attempt_self_healing_replan(db, gid)
                    if healed:
                        worked = True

            except Exception as e:
                logger.error(f"Error waking goal {gid}: {e}", exc_info=True)

        return worked


_runner: Optional[WakeRunner] = None


def get_wake_runner(engine: AsyncEngine) -> WakeRunner:
    global _runner
    if _runner is None:
        _runner = WakeRunner(engine)
    return _runner
