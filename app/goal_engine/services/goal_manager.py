"""GoalManager — autorité métier du cycle de vie des Goals et de leur gouvernance.

Garanties & Invariants (STEP 4D) :
- Pure délégation de transition à GoalStateMachine (INV-10).
- Pure délégation du DAG à TaskGraph.
- Autonomie bornée : min(requested, agent_cap, parent_cap), 0 <= level <= 5.
- Intégrité parent/enfant : même workspace, parent non-terminal, détection cycles.
- Deadlines strictes : timezone-aware UTC, enfant <= parent, rejet des expirées.
- Limites déterministes : max_steps, max_replanning_count, budget_limit.
- Current steps : source de vérité = ExecutionAttempt quittant PENDING.
- Budget : source de vérité = somme des ExecutionResultRecord.cost_amount.
- Concurrence : SELECT ... FOR UPDATE sur Goal, règle first-terminal-commit-wins.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.execution.models import (
    ActionRecord,
    AttemptStatus,
    ExecutionAttempt,
    ExecutionResultRecord,
)
from app.goal_engine.exceptions import (
    GoalAlreadyTerminalError,
    GoalAutonomyLevelInvalidError,
    GoalBudgetExceededError,
    GoalDeadlineExceededError,
    GoalDeadlineInvalidError,
    GoalIncompleteTasksError,
    GoalMissingReasonError,
    GoalMissingSuccessProofError,
    GoalNotFoundError,
    GoalParentCycleError,
    GoalParentDeadlineExpiredError,
    GoalParentNotFoundError,
    GoalParentTerminalError,
    GoalPlanEmptyError,
    GoalReplanningLimitExceededError,
    GoalRunningTasksActiveError,
    GoalStepLimitExceededError,
    GoalSuccessCriteriaNotMetError,
    GoalTimezoneNaiveError,
    GoalWorkspaceMismatchError,
    InvalidGoalTransitionError,
)
from app.goal_engine.models import Goal, GoalStatus
from app.goal_engine.services.goal_state_machine import GoalStateMachine
from app.identity.models import Agent
from app.task_engine.models import Task, TaskDependency, TaskStatus
from app.task_engine.services.task_graph import TaskGraph


def _utcnow() -> datetime:
    """Retourne l'horodatage courant conscient du fuseau (UTC strict)."""
    return datetime.now(timezone.utc)


def _ensure_utc(dt: Optional[datetime], name: str = "datetime") -> Optional[datetime]:
    """Valide qu'un horodatage est timezone-aware UTC."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        raise GoalTimezoneNaiveError(
            f"L'horodatage '{name}' doit être conscient du fuseau (timezone-aware UTC)."
        )
    return dt.astimezone(timezone.utc)


@dataclass(frozen=True)
class GoalSuccessProof:
    """Preuve externe de succès d'un Goal (INV-10)."""

    reference: str
    verified_by: str
    verified_at: datetime
    evidence: dict[str, Any] = field(default_factory=dict)
    criteria_verified: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.reference or not self.reference.strip():
            raise GoalMissingSuccessProofError(
                "La référence de preuve (reference) ne peut être vide."
            )
        if not self.verified_by or not self.verified_by.strip():
            raise GoalMissingSuccessProofError(
                "L'émetteur (verified_by) ne peut être vide."
            )
        _ensure_utc(self.verified_at, name="verified_at")


@dataclass(frozen=True)
class GoalLimitsCheckResult:
    """Résultat du contrôle déterministe des limites d'un Goal."""

    ok: bool
    deadline_ok: bool
    steps_ok: bool
    replanning_ok: bool
    budget_ok: bool
    current_steps: int
    max_steps: int
    current_replanning: int
    max_replanning_count: int
    consumed_budget: Decimal
    budget_limit: Optional[Decimal]
    violations: list[str] = field(default_factory=list)


class GoalManager:
    """Autorité applicative pour le cycle de vie et les limites des Goals."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # =========================================================================
    # 1. CALCUL PUR DE L'AUTONOMIE
    # =========================================================================

    @staticmethod
    def calculate_applied_autonomy(
        requested_autonomy_level: int,
        agent_default_autonomy: int,
        parent_applied_autonomy: Optional[int] = None,
    ) -> int:
        """Calcule le niveau d'autonomie appliquée selon la formule validée.

        applied = min(requested, agent_default, parent_applied)
        Contraintes : 0 <= level <= 5.
        """
        for name, val in (
            ("requested_autonomy_level", requested_autonomy_level),
            ("agent_default_autonomy", agent_default_autonomy),
        ):
            if not isinstance(val, int) or isinstance(val, bool) or not (0 <= val <= 5):
                raise GoalAutonomyLevelInvalidError(
                    val, f"{name} doit être un entier strict entre 0 et 5."
                )

        cap = min(requested_autonomy_level, agent_default_autonomy)

        if parent_applied_autonomy is not None:
            if (
                not isinstance(parent_applied_autonomy, int)
                or isinstance(parent_applied_autonomy, bool)
                or not (0 <= parent_applied_autonomy <= 5)
            ):
                raise GoalAutonomyLevelInvalidError(
                    parent_applied_autonomy,
                    "parent_applied_autonomy doit être un entier strict entre 0 et 5.",
                )
            cap = min(cap, parent_applied_autonomy)

        return cap

    # =========================================================================
    # 2. VALIDATION DU PARENT ET DE LA CHAÎNE PARENTALE
    # =========================================================================

    async def validate_parent_hierarchy(
        self,
        *,
        goal_id: Optional[uuid.UUID],
        workspace_id: uuid.UUID,
        parent_goal_id: Optional[uuid.UUID],
        agent_id: Optional[uuid.UUID] = None,
    ) -> Optional[Goal]:
        """Vérifie l'intégrité de la hiérarchie parent/enfant.

        - Cohérence workspace Goal <-> Agent
        - Existence du parent
        - Cohérence workspace Goal <-> Parent
        - Parent non terminal
        - Absence de cycles (ex: A -> B -> C -> A)
        """
        # Vérification de l'agent si fourni
        if agent_id is not None:
            stmt_agent = select(Agent).where(Agent.id == agent_id)
            agent = (await self.session.execute(stmt_agent)).scalar_one_or_none()
            if agent is not None and agent.workspace_id != workspace_id:
                raise GoalWorkspaceMismatchError(
                    f"L'agent {agent_id} appartient au workspace {agent.workspace_id}, "
                    f"différent du workspace du goal ({workspace_id})."
                )

        if parent_goal_id is None:
            return None

        # Auto-parentage direct
        if goal_id is not None and parent_goal_id == goal_id:
            raise GoalParentCycleError(
                f"Un Goal ne peut pas être son propre parent ({goal_id})."
            )

        # Récupération du parent direct
        stmt_parent = select(Goal).where(Goal.id == parent_goal_id)
        parent = (await self.session.execute(stmt_parent)).scalar_one_or_none()
        if parent is None:
            raise GoalParentNotFoundError(parent_goal_id)

        # Cohérence de workspace
        if parent.workspace_id != workspace_id:
            raise GoalWorkspaceMismatchError(
                f"Parent {parent_goal_id} (workspace {parent.workspace_id}) "
                f"!= child ({workspace_id})."
            )

        # Parent non terminal
        if GoalStateMachine.is_terminal(parent.status):
            raise GoalParentTerminalError(parent.status.value)

        # Détection de cycles sur toute la chaîne ascendante
        visited_ids: set[uuid.UUID] = {parent.id}
        if goal_id is not None:
            visited_ids.add(goal_id)

        curr = parent
        depth = 0
        max_depth = 50

        while curr.parent_goal_id is not None:
            depth += 1
            if depth > max_depth:
                raise GoalParentCycleError(
                    f"Profondeur maximale ({max_depth}) dépassée ou cycle détecté."
                )

            next_id = curr.parent_goal_id
            if next_id in visited_ids:
                raise GoalParentCycleError(
                    f"Cycle hiérarchique détecté impliquant le Goal {next_id}."
                )
            visited_ids.add(next_id)

            stmt_next = select(Goal).where(Goal.id == next_id)
            curr = (await self.session.execute(stmt_next)).scalar_one_or_none()
            if curr is None:
                break

        return parent

    # =========================================================================
    # 3. GESTION DES DEADLINES
    # =========================================================================

    @staticmethod
    def resolve_child_deadline(
        requested_child_deadline: Optional[datetime],
        parent_deadline: Optional[datetime],
        *,
        now: Optional[datetime] = None,
    ) -> Optional[datetime]:
        """Calcule la deadline effective d'un Goal enfant selon le contrat temporel.

        Règle :
        - child_deadline = min(requested, parent) si les deux existent.
        - hérite de parent_deadline si child sans deadline.
        - prend requested si parent sans deadline.
        - rejette tout datetime naïf ou déjà expiré.
        """
        current_time = _ensure_utc(now) or _utcnow()
        req_utc = _ensure_utc(requested_child_deadline, name="requested_child_deadline")
        par_utc = _ensure_utc(parent_deadline, name="parent_deadline")

        if par_utc is not None and par_utc <= current_time:
            raise GoalParentDeadlineExpiredError()

        if req_utc is not None and req_utc <= current_time:
            raise GoalDeadlineInvalidError(
                f"Deadline demandée ({req_utc}) <= instant présent ({current_time})."
            )

        if par_utc is not None and req_utc is not None:
            return min(req_utc, par_utc)
        if par_utc is not None:
            return par_utc
        return req_utc

    # =========================================================================
    # 4. RÉCUPÉRATION ET VERROUILLAGE D'UN GOAL
    # =========================================================================

    async def get_goal(self, goal_id: uuid.UUID, *, for_update: bool = False) -> Goal:
        """Récupère un Goal par son id, avec verrou optionnel (FOR UPDATE)."""
        stmt = select(Goal).where(Goal.id == goal_id)
        if for_update:
            stmt = stmt.with_for_update()

        result = await self.session.execute(stmt)
        goal = result.scalar_one_or_none()
        if goal is None:
            raise GoalNotFoundError(goal_id)
        return goal

    # =========================================================================
    # 5. CONTRÔLE DÉTERMINISTE DES LIMITES (check_limits)
    # =========================================================================

    async def check_limits(
        self,
        goal_id: uuid.UUID,
        *,
        now: Optional[datetime] = None,
        raise_on_violation: bool = True,
    ) -> GoalLimitsCheckResult:
        """Vérifie déterministement les limites du Goal sans modifier son état.

        Limites contrôlées :
        - deadline : now <= deadline
        - current_steps : < max_steps
        - replanning_count : <= max_replanning_count
        - budget : consumed_budget < budget_limit (si limite définie)
        """
        goal = await self.get_goal(goal_id, for_update=False)
        current_time = _ensure_utc(now) or _utcnow()

        limits = (
            dict(goal.goal_metadata.get("limits", {})) if goal.goal_metadata else {}
        )
        usage = dict(goal.goal_metadata.get("usage", {})) if goal.goal_metadata else {}

        # 1. Deadline
        raw_deadline = goal.goal_metadata.get("deadline") or limits.get("deadline")
        deadline_dt: Optional[datetime] = None
        if raw_deadline:
            if isinstance(raw_deadline, str):
                deadline_dt = datetime.fromisoformat(raw_deadline)
            elif isinstance(raw_deadline, datetime):
                deadline_dt = raw_deadline
            deadline_dt = _ensure_utc(deadline_dt, name="deadline")

        deadline_ok = True
        if deadline_dt is not None and current_time > deadline_dt:
            deadline_ok = False

        # 2. Steps (source primaire = ExecutionAttempt non PENDING et non CANCELLED)
        max_steps = int(limits.get("max_steps", 100))

        stmt_steps = (
            select(func.count(ExecutionAttempt.id))
            .join(ActionRecord, ExecutionAttempt.action_id == ActionRecord.id)
            .join(Task, ActionRecord.task_id == Task.id)
            .where(
                Task.goal_id == goal.id,
                ExecutionAttempt.status != AttemptStatus.PENDING,
                ExecutionAttempt.status != AttemptStatus.CANCELLED,
            )
        )
        db_steps = (await self.session.execute(stmt_steps)).scalar_one() or 0
        cached_steps = int(usage.get("current_steps", 0))
        current_steps = max(db_steps, cached_steps)

        steps_ok = current_steps < max_steps

        # 3. Replanning count
        max_replanning = int(limits.get("max_replanning_count", 3))
        current_replanning = int(usage.get("replanning_count", 0))
        replanning_ok = current_replanning <= max_replanning

        # 4. Budget (source primaire = ExecutionResultRecord.cost_amount)
        raw_budget_limit = limits.get("budget_limit")
        budget_limit = (
            Decimal(str(raw_budget_limit)) if raw_budget_limit is not None else None
        )

        stmt_budget = (
            select(
                func.coalesce(func.sum(ExecutionResultRecord.cost_amount), Decimal(0))
            )
            .join(
                ExecutionAttempt,
                ExecutionResultRecord.attempt_id == ExecutionAttempt.id,
            )
            .join(ActionRecord, ExecutionAttempt.action_id == ActionRecord.id)
            .join(Task, ActionRecord.task_id == Task.id)
            .where(Task.goal_id == goal.id)
        )
        db_budget = (await self.session.execute(stmt_budget)).scalar_one() or Decimal(0)
        cached_budget = Decimal(str(usage.get("budget_consumed", 0)))
        consumed_budget = max(db_budget, cached_budget)

        budget_ok = True
        if budget_limit is not None and consumed_budget >= budget_limit:
            budget_ok = False

        violations: list[str] = []
        if not deadline_ok:
            violations.append(
                f"DEADLINE_EXCEEDED (now={current_time} > deadline={deadline_dt})"
            )
        if not steps_ok:
            violations.append(f"STEP_LIMIT_EXCEEDED ({current_steps}/{max_steps})")
        if not replanning_ok:
            violations.append(
                f"REPLANNING_LIMIT_EXCEEDED ({current_replanning}/{max_replanning})"
            )
        if not budget_ok:
            violations.append(
                f"BUDGET_LIMIT_EXCEEDED ({consumed_budget}/{budget_limit})"
            )

        is_ok = len(violations) == 0

        if raise_on_violation and not is_ok:
            if not deadline_ok:
                raise GoalDeadlineExceededError()
            if not steps_ok:
                raise GoalStepLimitExceededError(current_steps, max_steps)
            if not replanning_ok:
                raise GoalReplanningLimitExceededError(
                    current_replanning, max_replanning
                )
            if not budget_ok:
                raise GoalBudgetExceededError(consumed_budget, budget_limit)

        return GoalLimitsCheckResult(
            ok=is_ok,
            deadline_ok=deadline_ok,
            steps_ok=steps_ok,
            replanning_ok=replanning_ok,
            budget_ok=budget_ok,
            current_steps=current_steps,
            max_steps=max_steps,
            current_replanning=current_replanning,
            max_replanning_count=max_replanning,
            consumed_budget=consumed_budget,
            budget_limit=budget_limit,
            violations=violations,
        )

    # =========================================================================
    # 6. CYCLE DE VIE : start_planning
    # =========================================================================

    async def start_planning(self, goal_id: uuid.UUID) -> Goal:
        """Démarre la planification du Goal (PENDING -> PLANNING)."""
        goal = await self.get_goal(goal_id, for_update=True)

        # Vérification des limites de base (ex: deadline non dépassée)
        await self.check_limits(goal.id, raise_on_violation=True)

        # Transition via la GoalStateMachine pure
        GoalStateMachine.transition(goal, GoalStatus.PLANNING)
        goal.completed_at = None
        await self.session.flush()
        return goal

    # =========================================================================
    # 7. CYCLE DE VIE : activate_plan
    # =========================================================================

    async def activate_plan(self, goal_id: uuid.UUID) -> Goal:
        """Valide le plan de tâches (DAG) et active le Goal (PLANNING -> ACTIVE).

        Exige :
        - Au moins 1 tâche associée
        - Graphe acyclique valide (TaskGraph)
        - Au moins une tâche initiale éligible READY
        - Compteurs existants non réinitialisés en cas de reprise
        """
        goal = await self.get_goal(goal_id, for_update=True)

        # Contrôle des limites
        await self.check_limits(goal.id, raise_on_violation=True)

        # Chargement des tâches et dépendances
        stmt_tasks = select(Task).where(Task.goal_id == goal.id)
        tasks = list((await self.session.execute(stmt_tasks)).scalars().all())

        if not tasks:
            raise GoalPlanEmptyError("Le Goal ne contient aucune tâche dans son plan.")

        stmt_deps = select(TaskDependency).where(TaskDependency.goal_id == goal.id)
        deps = list((await self.session.execute(stmt_deps)).scalars().all())

        # Validation DAG stricte via TaskGraph
        graph = TaskGraph(tasks, deps)
        graph.validate()

        ready_tasks = graph.get_ready_tasks()
        if not ready_tasks:
            raise GoalPlanEmptyError(
                "Le plan ne contient aucune tâche initiale éligible au statut READY."
            )

        # Transition
        GoalStateMachine.transition(goal, GoalStatus.ACTIVE)
        goal.completed_at = None

        # Initialisation sécurisée des métadonnées (sans écraser l'usage existant)
        metadata = dict(goal.goal_metadata or {})
        limits = dict(metadata.get("limits", {}))
        usage = dict(metadata.get("usage", {}))

        if "max_steps" not in limits:
            limits["max_steps"] = 100
        if "max_replanning_count" not in limits:
            limits["max_replanning_count"] = 3
        if "max_task_retries" not in limits:
            limits["max_task_retries"] = 2

        if "current_steps" not in usage:
            usage["current_steps"] = 0
        if "replanning_count" not in usage:
            usage["replanning_count"] = 0
        if "budget_consumed" not in usage:
            usage["budget_consumed"] = 0.0

        metadata["limits"] = limits
        metadata["usage"] = usage
        goal.goal_metadata = metadata
        flag_modified(goal, "goal_metadata")

        await self.session.flush()
        return goal

    # =========================================================================
    # 8. CYCLE DE VIE : request_replanning
    # =========================================================================

    async def request_replanning(self, goal_id: uuid.UUID, *, reason: str) -> Goal:
        """Demande une replanification (ACTIVE -> PLANNING)."""
        if not reason or not reason.strip():
            raise GoalMissingReasonError("request_replanning")

        goal = await self.get_goal(goal_id, for_update=True)

        # Vérifier qu'aucune tâche du Goal n'est en RUNNING actif
        stmt_running = select(func.count(Task.id)).where(
            Task.goal_id == goal.id,
            Task.status == TaskStatus.RUNNING,
        )
        running_count = (await self.session.execute(stmt_running)).scalar_one() or 0
        if running_count > 0:
            raise GoalRunningTasksActiveError(running_count)

        metadata = dict(goal.goal_metadata or {})
        limits = dict(metadata.get("limits", {}))
        usage = dict(metadata.get("usage", {}))

        max_replanning = int(limits.get("max_replanning_count", 3))
        current_replanning = int(usage.get("replanning_count", 0))

        if current_replanning >= max_replanning:
            raise GoalReplanningLimitExceededError(current_replanning, max_replanning)

        # Transition
        GoalStateMachine.transition(goal, GoalStatus.PLANNING)
        goal.completed_at = None

        # Incrément atomique et traçabilité
        usage["replanning_count"] = current_replanning + 1
        metadata["usage"] = usage

        history = list(metadata.get("replanning_history", []))
        history.append(
            {
                "count": usage["replanning_count"],
                "reason": reason,
                "timestamp": _utcnow().isoformat(),
            }
        )
        metadata["replanning_history"] = history
        goal.goal_metadata = metadata
        flag_modified(goal, "goal_metadata")

        await self.session.flush()
        return goal

    # =========================================================================
    # 9. CYCLE DE VIE : pause_goal / resume_goal
    # =========================================================================

    async def pause_goal(self, goal_id: uuid.UUID, *, reason: str) -> Goal:
        """Met en pause le Goal (PLANNING ou ACTIVE -> PAUSED)."""
        if not reason or not reason.strip():
            raise GoalMissingReasonError("pause_goal")

        goal = await self.get_goal(goal_id, for_update=True)

        GoalStateMachine.transition(goal, GoalStatus.PAUSED)
        goal.completed_at = None

        metadata = dict(goal.goal_metadata or {})
        metadata["pause_reason"] = reason
        metadata["paused_at"] = _utcnow().isoformat()
        goal.goal_metadata = metadata
        flag_modified(goal, "goal_metadata")

        await self.session.flush()
        return goal

    async def resume_goal(self, goal_id: uuid.UUID) -> Goal:
        """Reprend un Goal mis en pause (PAUSED -> ACTIVE ou PLANNING)."""
        goal = await self.get_goal(goal_id, for_update=True)

        if goal.status != GoalStatus.PAUSED:
            raise InvalidGoalTransitionError(
                goal.status,
                GoalStatus.ACTIVE,
                reason="Seul un Goal PAUSED peut être repris.",
            )

        # Vérification des limites
        await self.check_limits(goal.id, raise_on_violation=True)

        # Si plan avec des tâches prêtes existe -> ACTIVE, sinon PLANNING
        stmt_tasks = select(Task).where(Task.goal_id == goal.id)
        tasks = list((await self.session.execute(stmt_tasks)).scalars().all())

        target_status = GoalStatus.PLANNING
        if tasks:
            stmt_deps = select(TaskDependency).where(TaskDependency.goal_id == goal.id)
            deps = list((await self.session.execute(stmt_deps)).scalars().all())
            graph = TaskGraph(tasks, deps)
            ready_tasks = graph.get_ready_tasks()
            if ready_tasks or any(t.status is TaskStatus.COMPLETED for t in tasks):
                target_status = GoalStatus.ACTIVE

        GoalStateMachine.transition(goal, target_status)
        goal.completed_at = None

        metadata = dict(goal.goal_metadata or {})
        metadata.pop("pause_reason", None)
        metadata["resumed_at"] = _utcnow().isoformat()
        goal.goal_metadata = metadata
        flag_modified(goal, "goal_metadata")

        await self.session.flush()
        return goal

    # =========================================================================
    # 10. CYCLE DE VIE : complete_goal
    # =========================================================================

    async def complete_goal(
        self, goal_id: uuid.UUID, *, proof: GoalSuccessProof
    ) -> Goal:
        """Valide et complète le Goal (ACTIVE -> COMPLETED).

        Exige :
        - Preuve externe typée GoalSuccessProof valide
        - 100% des tâches du Goal au statut COMPLETED
        - Validation des critères requis (success_criteria)
        """
        if not isinstance(proof, GoalSuccessProof):
            raise GoalMissingSuccessProofError(
                "La preuve fournie doit être une instance de GoalSuccessProof."
            )

        goal = await self.get_goal(goal_id, for_update=True)

        if GoalStateMachine.is_terminal(goal.status):
            raise GoalAlreadyTerminalError(goal.status.value)

        # Vérification des tâches du Goal : TOUTES doivent être COMPLETED
        stmt_tasks = select(Task).where(Task.goal_id == goal.id)
        tasks = list((await self.session.execute(stmt_tasks)).scalars().all())

        incomplete = [t for t in tasks if t.status is not TaskStatus.COMPLETED]
        if incomplete:
            raise GoalIncompleteTasksError(len(incomplete))

        # Vérification des critères de succès dans les métadonnées
        criteria = goal.goal_metadata.get("success_criteria", [])
        if criteria:
            verified_set = set(proof.criteria_verified)
            missing = [c for c in criteria if c not in verified_set]
            if missing:
                raise GoalSuccessCriteriaNotMetError(missing)

        # Transition
        GoalStateMachine.transition(goal, GoalStatus.COMPLETED)
        goal.completed_at = _utcnow()

        metadata = dict(goal.goal_metadata or {})
        metadata["success_proof"] = {
            "reference": proof.reference,
            "verified_by": proof.verified_by,
            "verified_at": proof.verified_at.isoformat(),
            "evidence": proof.evidence,
            "criteria_verified": proof.criteria_verified,
        }
        goal.goal_metadata = metadata
        flag_modified(goal, "goal_metadata")

        await self.session.flush()
        return goal

    # =========================================================================
    # 11. CYCLE DE VIE : fail_goal / cancel_goal (Terminaux)
    # =========================================================================

    async def fail_goal(self, goal_id: uuid.UUID, *, reason: str) -> Goal:
        """Passe le Goal à l'état terminal FAILED."""
        if not reason or not reason.strip():
            raise GoalMissingReasonError("fail_goal")

        goal = await self.get_goal(goal_id, for_update=True)

        if GoalStateMachine.is_terminal(goal.status):
            raise GoalAlreadyTerminalError(goal.status.value)

        GoalStateMachine.transition(goal, GoalStatus.FAILED)
        goal.completed_at = _utcnow()

        metadata = dict(goal.goal_metadata or {})
        metadata["failure_reason"] = reason
        goal.goal_metadata = metadata
        flag_modified(goal, "goal_metadata")

        await self.session.flush()
        return goal

    async def cancel_goal(self, goal_id: uuid.UUID, *, reason: str) -> Goal:
        """Annule le Goal (état terminal CANCELLED)."""
        if not reason or not reason.strip():
            raise GoalMissingReasonError("cancel_goal")

        goal = await self.get_goal(goal_id, for_update=True)

        if GoalStateMachine.is_terminal(goal.status):
            raise GoalAlreadyTerminalError(goal.status.value)

        GoalStateMachine.transition(goal, GoalStatus.CANCELLED)
        goal.completed_at = _utcnow()

        metadata = dict(goal.goal_metadata or {})
        metadata["cancellation_reason"] = reason
        goal.goal_metadata = metadata
        flag_modified(goal, "goal_metadata")

        await self.session.flush()
        return goal

    # =========================================================================
    # 12. IMPASSE DU DAG (DEADLOCK EVALUATION)
    # =========================================================================

    async def evaluate_dag_stalemate(self, goal_id: uuid.UUID) -> GoalStatus:
        """Évalue l'avancement du graphe et résout une impasse (stale DAG).

        Règle :
        Si aucun Task READY n'existe alors que le Goal n'est pas terminé :
        - si replanning possible -> PLANNING
        - si quota replanning épuisé -> FAILED
        - JAMAIS PAUSED automatique
        """
        goal = await self.get_goal(goal_id, for_update=True)

        if goal.status != GoalStatus.ACTIVE:
            return goal.status

        stmt_tasks = select(Task).where(Task.goal_id == goal.id)
        tasks = list((await self.session.execute(stmt_tasks)).scalars().all())

        if not tasks or all(t.status is TaskStatus.COMPLETED for t in tasks):
            return goal.status

        stmt_deps = select(TaskDependency).where(TaskDependency.goal_id == goal.id)
        deps = list((await self.session.execute(stmt_deps)).scalars().all())

        graph = TaskGraph(tasks, deps)
        ready_tasks = graph.get_ready_tasks()

        # Des tâches sont prêtes ou en cours d'exécution
        if ready_tasks or any(t.status is TaskStatus.RUNNING for t in tasks):
            return goal.status

        # Impasse détectée : aucune tâche READY/RUNNING et Goal inachevé
        metadata = dict(goal.goal_metadata or {})
        limits = dict(metadata.get("limits", {}))
        usage = dict(metadata.get("usage", {}))

        max_replanning = int(limits.get("max_replanning_count", 3))
        current_replanning = int(usage.get("replanning_count", 0))

        if current_replanning < max_replanning:
            await self.request_replanning(
                goal.id, reason="NO_READY_TASKS_STALEMATE"
            )
            return GoalStatus.PLANNING
        else:
            await self.fail_goal(
                goal.id, reason="NO_READY_TASKS_MAX_REPLANNING_EXCEEDED"
            )
            return GoalStatus.FAILED
