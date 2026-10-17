import asyncio
import logging
from typing import Optional
from sqlalchemy import select, text
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

logger = logging.getLogger(__name__)

class WakeRunner:
    """Runner autonome minimal pour réveiller les Goals éligibles.
    
    Il poll la base de données et exécute wake_goal() sur les Goals qui peuvent
    avancer. La sécurité (pas de double exécution) est garantie par les verrous
    FOR UPDATE internes à wake_goal().
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
        # L'arbitrator a besoin de la session DB courante
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
                    
                # Backoff : 0.5s si on a travaillé, 5s si idle (aucun Goal ou NO_READY_TASK)
                sleep_time = 0.5 if worked else 5.0
                await asyncio.sleep(sleep_time)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"WakeRunner encountered an unhandled error: {e}", exc_info=True)
                await asyncio.sleep(5.0)

    async def _poll_and_wake(self, db: AsyncSession) -> bool:
        """Cherche les Goals éligibles et appelle wake_goal() sur eux.
        
        Retourne True si au moins un appel à wake_goal a réellement fait progresser
        quelque chose (statut différent de NO_READY_TASK / ACTIVE bloqué).
        """
        worked = False
        
        # Query d'éligibilité : Goals non terminaux (PENDING, PLANNING, ACTIVE)
        # On exclut ceux qui attendent explicitement une preuve externe.
        stmt = (
            select(Goal.id)
            .where(Goal.status.in_([GoalStatus.PENDING, GoalStatus.PLANNING, GoalStatus.ACTIVE]))
            .where(
                (Goal.goal_metadata.op("->>")("proof_pending").is_(None)) |
                (Goal.goal_metadata.op("->>")("proof_pending") != "true")
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
                # wake_goal prend en charge ses propres transactions (rollback/commit)
                result: WakeResult = await wake_goal(
                    db,
                    goal_id=gid,
                    orchestrator_factory=self._orchestrator_factory
                )
                
                # Si le Goal était bloqué par des tâches RUNNING, wake_goal() 
                # va renvoyer status="ACTIVE" et NO_READY_TASK. On ne le compte pas
                # comme "worked" pour ne pas spammer la boucle (on backoff 5s).
                # WakeResult est un pydantic/dataclass ? Il a un attribut status.
                if result.status != "ACTIVE":
                    worked = True
                
            except Exception as e:
                logger.error(f"Error waking goal {gid}: {e}", exc_info=True)
                # On continue avec le prochain Goal
                
        return worked

# Instance globale (Singleton module-level) qui sera attachée au lifespan FastAPI
_runner: Optional[WakeRunner] = None

def get_wake_runner(engine: AsyncEngine) -> WakeRunner:
    global _runner
    if _runner is None:
        _runner = WakeRunner(engine)
    return _runner
