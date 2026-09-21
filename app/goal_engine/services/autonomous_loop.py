"""AutonomousExecutionLoop â€” STEP 5B : boucle autonome contrÃ´lÃ©e (une tÃ¢che par appel).

Composition des composants existants, sans les modifier :

- Phase A â€” admission atomique : ``_admit_one_step()`` (STEP 5C) â€” ``READ COMMITTED``
  Ã©pinglÃ©, ``Goal FOR UPDATE``, ``check_limits()``, readiness DAG filtrÃ©e via
  ``TaskGraph.get_ready_tasks()`` (autoritÃ© DAG, jamais rÃ©implÃ©mentÃ©e),
  claim ``READY -> RUNNING`` sous ``SKIP LOCKED``, rÃ©servation ``current_steps``.
- Phase B â€” dÃ©cision : ``build_decision_request()`` (pure) puis
  ``DecisionOrchestrator.handle_decision(..., task_id=...)``. Toute la chaÃ®ne
  classification â†’ arbitrage â†’ autorisation â†’ dispatch â†’ attempt â†’ handler â†’
  rÃ©sultat reste la responsabilitÃ© de l'orchestrateur (aucune rÃ©implÃ©mentation).
- Phase C â€” clÃ´ture M3 : ``_close_task_with_outcome()``, idempotente, applique la
  table effect/control â†’ ``TaskStatus`` (UNKNOWN jamais auto-tranchÃ©).
- Phase D â€” suite : ``evaluate_dag_stalemate()`` ou ``proof_pending`` si tout est
  COMPLETED (jamais de ``GoalSuccessProof`` fabriquÃ©e, jamais de ``COMPLETED`` direct).

Contrat de verrouillage : aucun verrou DB ne survit Ã  un appel LLM/handler. Les
phases A/C/D sont des transactions courtes ; l'appel orchestrateur (rÃ©seau,
LLM, outil) se fait hors verrou, aprÃ¨s ``expire_all()`` + ``rollback()``.

Exigence d'isolation : ``app/core/database.py`` ne configure aucun
``isolation_level`` (ni engine ni sessionmaker, vÃ©rifiÃ©), donc le niveau effectif
serait le dÃ©faut du serveur/pool â€” modifiable silencieusement. La phase A Ã©pingle
donc explicitement ``SET TRANSACTION ISOLATION LEVEL READ COMMITTED`` en premiÃ¨re
instruction de sa transaction. En ``REPEATABLE READ``, le snapshot serait gelÃ©
avant l'attente du verrou et le ``COUNT`` de ``check_limits()`` resterait aveugle
aux commits concurrents : l'atomicitÃ© de ``max_steps`` casserait sans erreur
visible. L'Ã©pinglage est en dur dans le code, pas en commentaire.

Une seule tÃ¢che par appel, aucune boucle ``while`` : les rÃ©veils rÃ©pÃ©tÃ©s sont la
responsabilitÃ© d'un scheduler externe (hors pÃ©rimÃ¨tre actuel).

FrontiÃ¨res connues, documentÃ©es et testÃ©es comme telles :

- rÃ©essai bornÃ© : NON implÃ©mentÃ© ici â€” la primitive de rÃ©essai n'existe pas dans
  le pÃ©rimÃ¨tre actuel ; la limite de rÃ©essais dÃ©clarÃ©e dans les mÃ©tadonnÃ©es du
  Goal reste donc non appliquÃ©e par cette boucle (garde textuelle :
  ``test_retry_limit_is_declared_but_unenforced``).
- ``_ACTION_HANDLERS`` est vide (Phase 4) : tout ALLOW aboutit Ã 
  ``NO_HANDLER_REGISTERED`` / ``HANDLER_ABSENT`` â†’ ``BLOCKED`` (T3), comportement
  attendu et non contournÃ© par un faux handler.
- rÃ©veils automatiques / scheduler : ABSENT, hors pÃ©rimÃ¨tre STEP 5B.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.decision_engine.models import ControlOutcome
from app.decision_engine.schemas import DecisionRequest, DecisionResponse
from app.execution.models import (
    ActionRecord,
    AttemptStatus,
    EffectCertainty,
    ExecutionAttempt,
)
from app.goal_engine.models import Goal, GoalStatus
from app.goal_engine.services.goal_manager import GoalManager
from app.task_engine.exceptions import InvalidTaskTransitionError
from app.task_engine.models import Task, TaskDependency, TaskStatus
from app.task_engine.services.state_machine import TaskStateMachine
from app.task_engine.services.task_graph import TaskGraph

# GrÃ¢ce au-delÃ  de laquelle une Task RUNNING sans preuve d'activitÃ© est
# considÃ©rÃ©e orpheline et rÃ©cupÃ©rable (M6). ParamÃ¨tre par appel, dÃ©faut 300 s.
DEFAULT_ORPHAN_GRACE_SECONDS = 300

# PrÃ©fixes d'erreur stables Ã©mis AVANT tout effet (orchestrator.py) :
# aucune tentative n'existe alors (execution_attempt_id is None).
_PRE_EFFECT_ERROR_PREFIXES = (
    "NO_HANDLER_REGISTERED",
    "HANDLER_ABSENT",
    "CONTROL_",
    "EXECUTION_NOT_PREAUTHORIZED",
    "APPROVAL_REFERENCE_MISSING",
    "AUTHORIZATION_",
    "ACTION_",
    "ATTEMPT_ALREADY_",
    "LEASE_",
    "EFFECT_UNKNOWN_REQUIRES_",
    "QUOTA_",
    "WORKSPACE_MISMATCH",
)


@dataclass(frozen=True)
class AdmitResult:
    """RÃ©sultat bornÃ© d'une tentative d'admission (un pas max)."""

    admitted: bool
    task_id: uuid.UUID | None = None
    reason: str | None = None
    violations: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class WakeResult:
    """RÃ©sultat bornÃ© d'un rÃ©veil : UNE tÃ¢che max par appel, jamais de boucle."""

    status: str
    task_id: uuid.UUID | None = None
    execution_effect: str | None = None
    violations: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CloseResult:
    """RÃ©sultat de la clÃ´ture d'une tÃ¢che RUNNING (idempotent)."""

    closed: bool
    task_id: uuid.UUID
    to_status: TaskStatus | None = None
    reason: str = ""


@dataclass(frozen=True)
class RecoverResult:
    """RÃ©sultat de la rÃ©cupÃ©ration d'au plus UN orphelin (idempotent)."""

    recovered: bool
    task_id: uuid.UUID | None = None
    to_status: TaskStatus | None = None
    reason: str = "NO_ORPHAN"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def build_decision_request(
    *, goal: Goal, task: Task, graph: TaskGraph
) -> DecisionRequest:
    """Factory pure Task â†’ DecisionRequest (M1) : aucun I/O, aucun ORM mutÃ©.

    Champs (contrat rÃ©el ``DecisionRequest`` â€” ``decision_engine/schemas.py``) :
    workspace/agent/objective depuis le Goal (la Task n'a pas de workspace) ;
    proposed_action = Task.description ; situation = snapshot dÃ©terministe
    (statuts, dÃ©pendances amont via le graphe, decision prÃ©cÃ©dente si retry) ;
    requested_autonomy_level = applied du Goal (plafond dÃ©jÃ  calculÃ©).
    """
    upstream = sorted(str(u) for u in graph.get_dependencies(task.id))
    parts = [
        f"goal_status={goal.status.value}",
        f"task_id={task.id}",
        f"task_status={task.status.value}",
        f"upstream_completed={upstream}",
    ]
    if task.decision_id is not None:
        parts.append(f"previous_decision={task.decision_id}")
    parts.append(f"goal_objective={goal.objective}")
    return DecisionRequest(
        workspace_id=goal.workspace_id,
        agent_id=goal.agent_id,
        objective=goal.objective,
        situation=" ".join(parts),
        proposed_action=task.description,
        requested_autonomy_level=goal.applied_autonomy_level,
    )


def decide_task_transition(response: DecisionResponse) -> TaskStatus:
    """Table M3 pure : (control_outcome, execution_effect, execution_error) â†’ Task.

    T1 ALLOW+confirmed â†’ COMPLETED. T2 ALLOW+none post-effet â†’ FAILED.
    Tout le reste (T3 prÃ©-effet incl. HANDLER_ABSENT, T4 unknown, T5 DENY/STOP,
    T6 ESCALATE) â†’ BLOCKED. Jamais de succÃ¨s prÃ©sumÃ©.
    """
    if (
        response.control_outcome == ControlOutcome.ALLOW
        and response.execution_effect == EffectCertainty.confirmed.value
    ):
        return TaskStatus.COMPLETED
    if (
        response.control_outcome == ControlOutcome.ALLOW
        and response.execution_effect == EffectCertainty.none.value
        and response.execution_attempt_id is not None
        and not _is_pre_effect_error(response.execution_error)
    ):
        return TaskStatus.FAILED
    return TaskStatus.BLOCKED


def _is_pre_effect_error(execution_error: str | None) -> bool:
    if not execution_error:
        return False
    return execution_error.startswith(_PRE_EFFECT_ERROR_PREFIXES)


async def _admit_one_step(db: AsyncSession, *, goal_id: uuid.UUID) -> AdmitResult:
    """Admet UNE tÃ¢che ``READY`` sous verrou Goal (Tx courte, ``READ COMMITTED``).

    SÃ©quence (tout sous le mÃªme ``FOR UPDATE`` sur le Goal, mÃªme session,
    mÃªme transaction) :

    1. Recalage de frontiÃ¨re (``rollback()``) puis Ã©pinglage explicite
       ``SET TRANSACTION ISOLATION LEVEL READ COMMITTED`` â€” DOIT rester la
       premiÃ¨re instruction de la transaction (Postgres l'exige).
    2. ``SELECT Goal ... FOR UPDATE`` (via ``GoalManager.get_goal``) :
       sÃ©rialise tous les workers concurrents sur ce goal.
    3. ``check_limits()`` TEL QUEL dans la mÃªme tx : le ``COUNT`` voit tous
       les commits antÃ©rieurs au verrou (2e worker bloquÃ© puis rÃ©veillÃ©).
    4. Claim d'UNE tÃ¢che ``READY`` : candidats DAG (``TaskGraph``) âˆ© statut DB
       ``READY``, tri dÃ©terministe, puis ``FOR UPDATE`` bloquant sur l'id choisi.
       Pas de ``SKIP LOCKED`` ici : les admissions d'un mÃªme goal sont dÃ©jÃ 
       sÃ©rialisÃ©es par le verrou Goal, et sauter la ligne choisie produirait un
       faux ``NO_READY_TASK`` au lieu d'attendre un Ã©tat stable.
    5. Transition ``READY -> RUNNING`` + rÃ©servation pessimiste
       ``usage.current_steps += 1`` (read-modify-write sous verrou).
    6. ``commit()`` immÃ©diat : libÃ¨re goal + tÃ¢che (< 50 ms, jamais de LLM
       sous verrou).

    L'appelant DOIT fournir une session dont l'Ã©tat non committÃ© peut Ãªtre
    Ã©cartÃ© (le ``rollback()`` initial y veille) : la fonction prend
    possession de la frontiÃ¨re de transaction.
    """
    # 1. FrontiÃ¨re propre + Ã©pinglage explicite de l'isolation.
    #    Sans rollback prÃ©alable, un statement antÃ©rieur sur cette session
    #    rendrait le SET TRANSACTION illÃ©gal (Postgres : must be first).
    await db.rollback()
    await db.execute(text("SET TRANSACTION ISOLATION LEVEL READ COMMITTED"))

    manager = GoalManager(db)
    try:
        # 2. Verrou ligne sur le Goal â€” sÃ©rialise check + claim.
        goal: Goal = await manager.get_goal(goal_id, for_update=True)

        # Garde-fou statutaire ATOMIQUE : check_limits() ne verifie PAS le
        # statut ; sans ce test, un Goal CANCELLED/PAUSED entre la phase A0 et
        # l'admission admettrait encore une tache (course volee sous le
        # verrou, meme machine d'etat que GoalManager, aucune logique dupliquee).
        if goal.status is not GoalStatus.ACTIVE:
            await db.commit()  # libere le verrou, rien n'est consomme
            return AdmitResult(admitted=False, reason="GOAL_NOT_EXECUTABLE")

        # 3. Lecture des limites DANS la tx verrouillÃ©e (rÃ©utilisÃ© tel quel).
        limits = await manager.check_limits(goal_id, raise_on_violation=False)
        if not limits.ok:
            await db.commit()  # libÃ¨re le verrou, rien n'est consommÃ©
            return AdmitResult(
                admitted=False,
                reason="LIMIT_HIT",
                violations=list(limits.violations),
            )

        # 4. Claim d'une seule tÃ¢che READY selon le DAG (CRITICAL-1) :
        #    TaskGraph est l'autoritÃ© (pas de duplication). get_ready_tasks()
        #    n'est Ã©ligible que pour PENDING (+BLOCKED avec preuve), JAMAIS
        #    pour une tÃ¢che dÃ©jÃ  READY en DB. Donc : intersection entre
        #    (a) les tÃ¢ches DB au statut READY et (b) les candidates DAG dont
        #    TOUS les amonts sont COMPLETED â€” le DAG borne, la DB dispose.
        stmt_tasks = select(Task).where(Task.goal_id == goal.id)
        tasks = list((await db.execute(stmt_tasks)).scalars().all())
        stmt_deps = select(TaskDependency).where(TaskDependency.goal_id == goal.id)
        deps = list((await db.execute(stmt_deps)).scalars().all())
        graph = TaskGraph(tasks, deps)
        by_id = {t.id: t for t in tasks}
        # Candidates DAG = PENDING/BLOCKED-par-preuve aux amonts COMPLETED
        # (get_ready_tasks, pur, sans I/O) ; on y ajoute les READY-DB dont
        # les amonts sont tous COMPLETED (mÃªme rÃ¨gle de dÃ©pendances).
        dag_candidate_ids = {t.id for t in graph.get_ready_tasks()}
        dag_ok_ids = set(dag_candidate_ids)
        for t in tasks:
            if t.status is TaskStatus.READY and t.id not in dag_ok_ids:
                upstream = graph.get_dependencies(t.id)
                if all(
                    by_id[u].status is TaskStatus.COMPLETED
                    for u in upstream
                    if u in by_id
                ):
                    dag_ok_ids.add(t.id)
        db_ready_ids = {t.id for t in tasks if t.status is TaskStatus.READY}
        eligible_ids = sorted(dag_ok_ids & db_ready_ids, key=str)
        if not eligible_ids:
            await db.commit()  # libÃ¨re le verrou ; M6/M4 traitÃ©s par wake_goal()
            return AdmitResult(admitted=False, reason="NO_READY_TASK")
        stmt_task = (
            select(Task)
            .where(Task.id == eligible_ids[0], Task.status == TaskStatus.READY)
            .with_for_update()
        )
        task = (await db.execute(stmt_task)).scalars().first()
        if task is None:
            # Course : la tÃ¢che a changÃ© entre le calcul graphe et le verrou
            # (ou elle est verrouillÃ©e par un worker concurrent â€” le FOR UPDATE
            # sur le Goal sÃ©rialise dÃ©jÃ  les admissions de ce goal, donc ici
            # c'est un vrai changement d'Ã©tat, pas un simple skip).
            await db.commit()
            return AdmitResult(admitted=False, reason="NO_READY_TASK")

        # 5. Transition + rÃ©servation pessimiste sous verrou.
        TaskStateMachine.transition(task, TaskStatus.RUNNING)
        metadata = dict(goal.goal_metadata or {})
        usage = dict(metadata.get("usage", {}))
        usage["current_steps"] = int(usage.get("current_steps", 0)) + 1
        metadata["usage"] = usage
        goal.goal_metadata = metadata
        flag_modified(goal, "goal_metadata")

        # 6. Commit court : publie RUNNING + rÃ©servation, libÃ¨re les verrous.
        await db.commit()
        return AdmitResult(admitted=True, task_id=task.id)
    except Exception:
        await db.rollback()
        raise


def _timestamp_interpretation_skew() -> timedelta:
    """DÃ©calage des ``updated_at`` NAÃFS Ã‰CRITS EN DB puis RELUS.

    MesurÃ© le 2026-09-20 (pas supposÃ©), DB ``TimeZone=UTC``, process UTC+1 :
        db now                 = 2026-09-20 15:52:11.606123+00:00
        datetime.utcnow()      = 2026-09-20 15:52:11.613342
        offset local (process) = 1:00:00
        ``Task.updated_at`` relu en DB pour une ligne Ã©crite Ã  l'instant :
            brut    : ``moment - updated â‰ˆ +3600 s`` (la ligne paraÃ®t vieille d'1 h)
            compensÃ©: ``moment - updated â‰ˆ +0.08 s`` (Ã¢ge rÃ©el)

    Cause : ``Task.updated_at`` utilise ``datetime.utcnow`` (naÃ¯f â€” dette LOCKED)
    et la valeur naÃ¯f est interprÃ©tÃ©e en heure locale Ã  l'Ã©criture, donc
    ``stockÃ© = vrai - offset_local``.

    RÃ¨gle appliquÃ©e (cf. ``_recover_one_orphan``) :
      * valeur NAÃVE  â†’ vient de l'instance Python (``utcnow``) â†’ instant DÃ‰JÃ€
        correct, aucune compensation (compenser la pousserait 1 h dans le futur
        et l'orphelin ne serait JAMAIS rÃ©cupÃ©rÃ©) ;
      * valeur AWARE  â†’ vient de la DB â†’ compenser par ``+offset_local``.

    On renvoie l'offset SIGNÃ‰ (jamais ``abs``) : pour un process UTC-5 le
    stockage vaut ``vrai + 5 h`` et la compensation doit donc Ãªtre ``-5 h``.
    """

    return datetime.now(timezone.utc).astimezone().utcoffset() or timedelta(0)


async def _recount_db_steps(db: AsyncSession, *, goal_id: uuid.UUID) -> int:
    """Recompte SQL des steps consommÃ©s (source de vÃ©ritÃ©, cf. check_limits)."""
    stmt = (
        select(func.count(ExecutionAttempt.id))
        .join(ActionRecord, ExecutionAttempt.action_id == ActionRecord.id)
        .join(Task, ActionRecord.task_id == Task.id)
        .where(
            Task.goal_id == goal_id,
            ExecutionAttempt.status != AttemptStatus.PENDING,
            ExecutionAttempt.status != AttemptStatus.CANCELLED,
        )
    )
    return int((await db.execute(stmt)).scalar_one() or 0)


async def _heal_step_counter(
    db: AsyncSession, *, goal: Goal, goal_id: uuid.UUID
) -> int:
    """GuÃ©rison M4/M5 : ``usage.current_steps = max(cached, recount_db)``."""
    metadata = dict(goal.goal_metadata or {})
    usage = dict(metadata.get("usage", {}))
    cached = int(usage.get("current_steps", 0))
    recount = await _recount_db_steps(db, goal_id=goal_id)
    healed = max(cached, recount)
    if healed != cached:
        usage["current_steps"] = healed
        metadata["usage"] = usage
        goal.goal_metadata = metadata
        flag_modified(goal, "goal_metadata")
    return healed


def _audit_orphan(goal: Goal, task_id: uuid.UUID, kind: str) -> None:
    """Trace la rÃ©cupÃ©ration dans goal_metadata (Task n'a pas de metadata)."""
    metadata = dict(goal.goal_metadata or {})
    trail = list(metadata.get("orphan_recovery_trail", []))
    entry = {"task_id": str(task_id), "kind": kind, "at": _utcnow().isoformat()}
    trail.append(entry)
    metadata["orphan_recovery_trail"] = trail[-50:]
    metadata["last_orphan_recovery"] = entry
    goal.goal_metadata = metadata
    flag_modified(goal, "goal_metadata")


async def _recover_one_orphan(
    db: AsyncSession,
    *,
    goal_id: uuid.UUID,
    now: datetime | None = None,
    orphan_grace_seconds: int = DEFAULT_ORPHAN_GRACE_SECONDS,
) -> RecoverResult:
    """RÃ©cupÃ¨re AU PLUS un orphelin RUNNING (M6, Tx courte, READ COMMITTED).

    W1 (aucune ActionRecord + grÃ¢ce dÃ©passÃ©e) â†’ FAILED, jamais READY
    (RUNNINGâ†’READY interdit). W2 (tentative, bail expirÃ©) â†’ mark UNKNOWN
    puis SUCCEEDEDâ†’COMPLETED, FAILEDâ†’FAILED, UNKNOWNâ†’BLOCKED (INV-09).
    Bail vivant / grÃ¢ce non dÃ©passÃ©e â†’ NO_ORPHAN (pas de vol).
    Terminale â†’ NO_ORPHAN idempotent.
    """
    from app.execution.services import attempts as attempts_service

    moment = now or _utcnow()
    await db.rollback()
    await db.execute(text("SET TRANSACTION ISOLATION LEVEL READ COMMITTED"))
    try:
        goal = await GoalManager(db).get_goal(goal_id, for_update=True)
        stmt_task = (
            select(Task)
            .where(Task.goal_id == goal.id, Task.status == TaskStatus.RUNNING)
            .order_by(Task.updated_at, Task.id)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        task = (await db.execute(stmt_task)).scalars().first()
        if task is None:
            await db.commit()
            return RecoverResult(recovered=False, reason="NO_ORPHAN")
        stmt_action = select(ActionRecord).where(ActionRecord.task_id == task.id)
        actions = list((await db.execute(stmt_action)).scalars().all())
        if not actions:
            # Ã‚ge de l'orphelin W1. Deux origines distinctes (cf. docstring de
            # _timestamp_interpretation_skew, mesures du 2026-09-20) :
            #   * naÃ¯f  â†’ valeur Python (utcnow) en identity map : DÃ‰JÃ€ correcte ;
            #   * aware â†’ relue en DB : dÃ©calÃ©e de -offset_local Ã  l'Ã©criture.
            updated = task.updated_at
            if updated is None:
                updated = moment
            elif updated.tzinfo is None:
                updated = updated.replace(tzinfo=timezone.utc)
            else:
                updated = updated + _timestamp_interpretation_skew()
            if updated > moment - timedelta(seconds=orphan_grace_seconds):
                await db.commit()
                return RecoverResult(recovered=False, reason="GRACE_NOT_EXPIRED")
            try:
                TaskStateMachine.transition(task, TaskStatus.FAILED)
            except InvalidTaskTransitionError:
                await db.commit()
                return RecoverResult(recovered=False, reason="ALREADY_TERMINAL")
            _audit_orphan(goal, task.id, "W1_NO_ACTION")
            await db.commit()
            return RecoverResult(
                recovered=True, task_id=task.id, to_status=TaskStatus.FAILED,
                reason="W1_NO_ACTION",
            )
        action_ids = [a.id for a in actions]
        stmt_attempt = (
            select(ExecutionAttempt)
            .where(ExecutionAttempt.action_id.in_(action_ids))
            .order_by(
                ExecutionAttempt.attempt_number.desc(), ExecutionAttempt.id.desc()
            )
            .limit(1)
        )
        attempt = (await db.execute(stmt_attempt)).scalars().first()
        if attempt is None:
            await db.commit()
            return RecoverResult(recovered=False, reason="NO_ORPHAN")
        lease_exp = attempt.lease_expires_at
        if lease_exp is not None and lease_exp.tzinfo is None:
            lease_exp = lease_exp.replace(tzinfo=timezone.utc)
        if attempt.status == AttemptStatus.RUNNING and (
            lease_exp is None or lease_exp > moment
        ):
            await db.commit()
            return RecoverResult(recovered=False, reason="LEASE_ALIVE")
        if attempt.status == AttemptStatus.RUNNING:
            await attempts_service.mark_unknown(
                db, attempt=attempt, reason="LEASE_EXPIRED",
                actor="autonomous_loop",
            )
            await db.refresh(attempt)
        if attempt.status == AttemptStatus.SUCCEEDED:
            target = TaskStatus.COMPLETED
        elif attempt.status == AttemptStatus.FAILED:
            target = TaskStatus.FAILED
        else:
            target = TaskStatus.BLOCKED
        try:
            TaskStateMachine.transition(task, target)
        except InvalidTaskTransitionError:
            await db.commit()
            return RecoverResult(recovered=False, reason="ALREADY_TERMINAL")
        latest = next(
            (a for a in actions if a.id == attempt.action_id), actions[0]
        )
        if latest.decision_id is not None:
            task.decision_id = latest.decision_id
        _audit_orphan(goal, task.id, f"W2_{attempt.status.value}")
        await db.commit()
        return RecoverResult(
            recovered=True, task_id=task.id, to_status=target,
            reason=f"W2_{attempt.status.value}",
        )
    except Exception:
        await db.rollback()
        raise


async def _close_task_with_outcome(
    db: AsyncSession, *, task_id: uuid.UUID, response: DecisionResponse
) -> CloseResult:
    """ClÃ´ture M3 d'une tÃ¢che RUNNING (Tx courte, idempotente).

    Applique decide_task_transition(), trace task.decision_id, guÃ©rit
    max(cached, recount). Terminale existante â†’ NO-OP (jamais rouverte).
    """
    await db.rollback()
    await db.execute(text("SET TRANSACTION ISOLATION LEVEL READ COMMITTED"))
    try:
        # Ordre de verrou uniforme Goal -> Task (regle projet, cf. audit PHASE 22) :
        # lecture non verrouillee du goal_id, verrou Goal, puis verrou Task.
        task_goal_id = (
            await db.execute(select(Task.goal_id).where(Task.id == task_id))
        ).scalar_one_or_none()
        if task_goal_id is None:
            await db.rollback()
            return CloseResult(closed=False, task_id=task_id, reason="TASK_NOT_FOUND")
        goal = await GoalManager(db).get_goal(task_goal_id, for_update=True)
        task = (
            await db.execute(
                select(Task).where(Task.id == task_id).with_for_update()
            )
        ).scalar_one_or_none()
        if task is None:
            await db.rollback()
            return CloseResult(closed=False, task_id=task_id, reason="TASK_NOT_FOUND")
        if TaskStateMachine.is_terminal(task.status):
            await db.commit()
            return CloseResult(
                closed=False, task_id=task_id, to_status=task.status,
                reason="ALREADY_TERMINAL",
            )
        target = decide_task_transition(response)
        try:
            TaskStateMachine.transition(task, target)
        except InvalidTaskTransitionError:
            await db.commit()
            return CloseResult(
                closed=False, task_id=task_id, to_status=task.status,
                reason="ALREADY_TERMINAL",
            )
        try:
            decision_uuid = uuid.UUID(str(response.decision_id))
        except (ValueError, AttributeError, TypeError):
            decision_uuid = None
        if decision_uuid is not None:
            task.decision_id = decision_uuid
        await _heal_step_counter(db, goal=goal, goal_id=task_goal_id)
        await db.commit()
        return CloseResult(
            closed=True, task_id=task_id, to_status=target, reason="CLOSED"
        )
    except Exception:
        await db.rollback()
        raise


async def wake_goal(
    db: AsyncSession,
    *,
    goal_id: uuid.UUID,
    orchestrator_factory=None,
    orphan_grace_seconds: int = DEFAULT_ORPHAN_GRACE_SECONDS,
) -> WakeResult:
    """RÃ©veille un Goal et fait progresser AU PLUS une tÃ¢che (jamais de boucle).

    Phase A (Tx courte) : garde-fous statut (terminal/PAUSED â†’ refus) puis
    ``_admit_one_step()`` ; si NO_READY_TASK, tente ``_recover_one_orphan()``
    (1 max) puis Ã©value le stalemate. Phase B (hors verrou) : factory pure +
    ``handle_decision(task_id=...)``. Phase C (Tx courte) : clÃ´ture M3.
    Phase D (Tx sÃ©parÃ©e) : ``evaluate_dag_stalemate()`` direct, ou
    ``proof_pending`` si tout est COMPLETED (jamais de preuve fabriquÃ©e,
    jamais de COMPLETED direct).
    """
    # Phase A0 â€” garde-fous statut (lecture seule, PK capturÃ©es avant rollback :
    # toucher probe.status aprÃ¨s rollback dÃ©clencherait un lazy-load expirÃ©).
    await db.rollback()
    probe = (
        await db.execute(select(Goal).where(Goal.id == goal_id))
    ).scalar_one_or_none()
    if probe is None:
        await db.rollback()
        return WakeResult(status="GOAL_NOT_FOUND")
    probe_status = probe.status
    await db.rollback()
    if probe_status in (
        GoalStatus.COMPLETED, GoalStatus.FAILED, GoalStatus.CANCELLED,
    ):
        return WakeResult(status="GOAL_TERMINAL")
    if probe_status == GoalStatus.PAUSED:
        return WakeResult(status="GOAL_PAUSED")

    # Phase A â€” admission atomique (Tx courte interne Ã  _admit_one_step).
    admit = await _admit_one_step(db, goal_id=goal_id)
    if not admit.admitted:
        if admit.reason == "LIMIT_HIT":
            return WakeResult(status="LIMIT_HIT", violations=list(admit.violations))
        # Course A0â†’admission : le statut a change sous le verrou (PAUSED/
        # CANCELLED/terminal). Aucune recuperation n'est tentee : un Goal non
        # executables ne doit subir AUCUN effet de bord (pas de transition de
        # tache depuis un orphelin pendant une pause). GoalManager reste
        # l'autorite du cycle de vie, aucune machine d'etat dupliquee.
        if admit.reason == "GOAL_NOT_EXECUTABLE":
            return WakeResult(status="GOAL_NOT_EXECUTABLE")
        recovered = await _recover_one_orphan(
            db, goal_id=goal_id, orphan_grace_seconds=orphan_grace_seconds
        )
        manager = GoalManager(db)
        try:
            await db.rollback()
            status = await manager.evaluate_dag_stalemate(goal_id)
            await db.commit()
        except Exception:
            await db.rollback()
            raise
        if recovered.recovered:
            return WakeResult(status=status.value, task_id=recovered.task_id)
        return WakeResult(status=status.value)

    assert admit.task_id is not None
    task_id = admit.task_id

    # Phase B â€” snapshot hors verrou pour la factory pure, puis dÃ©cision.
    # Tout accÃ¨s ORM se fait AVANT le dÃ©tachement ; aprÃ¨s expire_all/rollback
    # on ne touche plus que des copies dÃ©tachÃ©es (sinon MissingGreenlet).
    await db.rollback()
    _g = (await db.execute(select(Goal).where(Goal.id == goal_id))).scalar_one()
    _t = (await db.execute(select(Task).where(Task.id == task_id))).scalar_one()
    _tasks = list(
        (await db.execute(select(Task).where(Task.goal_id == goal_id))).scalars().all()
    )
    _deps = list(
        (
            await db.execute(
                select(TaskDependency).where(TaskDependency.goal_id == goal_id)
            )
        ).scalars().all()
    )
    snap_goal = Goal(
        id=_g.id, workspace_id=_g.workspace_id, agent_id=_g.agent_id,
        objective=_g.objective, status=_g.status,
        priority=_g.priority,
        requested_autonomy_level=_g.requested_autonomy_level,
        applied_autonomy_level=_g.applied_autonomy_level,
        parent_goal_id=_g.parent_goal_id, goal_metadata=dict(_g.goal_metadata or {}),
    )
    snap_task = Task(
        id=_t.id, goal_id=_t.goal_id, decision_id=_t.decision_id,
        description=_t.description, status=_t.status,
    )
    # Copies TRANSITOIRES (jamais rattachees a la session) : une instance
    # persistante expiree (expire_all/commit) declencherait un lazy-load
    # synchrone -> MissingGreenlet (observÃ© : task_graph.py:32 apres expire_all).
    snap_tasks = [
        Task(
            id=x.id, goal_id=x.goal_id, decision_id=x.decision_id,
            description=x.description, status=x.status,
        )
        for x in _tasks
    ]
    snap_deps = [
        TaskDependency(
            id=d.id, goal_id=d.goal_id, task_id=d.task_id,
            depends_on_task_id=d.depends_on_task_id,
        )
        for d in _deps
    ]
    snap_goal_id = snap_goal.id
    snap_task_id = snap_task.id
    # Graphe + requete construits AVANT toute expiration de session.
    graph = TaskGraph(snap_tasks, snap_deps)
    request = build_decision_request(goal=snap_goal, task=snap_task, graph=graph)
    db.expire_all()
    await db.rollback()
    if orchestrator_factory is None:
        return WakeResult(status="ADMITTED_NO_ORCHESTRATOR", task_id=snap_task_id)
    orchestrator = orchestrator_factory(db)
    response = await orchestrator.handle_decision(request, task_id=snap_task_id)

    # Phase C â€” clÃ´ture M3 (Tx courte interne).
    await _close_task_with_outcome(db, task_id=snap_task_id, response=response)

    # Phase D â€” stalemate direct ou proof_pending si tout est COMPLETED.
    await db.rollback()
    # Select colonne seule : aucune instance ORM persistante -> aucun lazy-load
    # (l'expiration par rollback rendrait tout acces attribut non greenlet-safe).
    all_statuses = list(
        (
            await db.execute(
                select(Task.status).where(Task.goal_id == snap_goal_id)
            )
        ).scalars().all()
    )
    await db.rollback()
    if all_statuses and all(s is TaskStatus.COMPLETED for s in all_statuses):
        await db.rollback()
        await db.execute(text("SET TRANSACTION ISOLATION LEVEL READ COMMITTED"))
        try:
            locked_goal = await GoalManager(db).get_goal(snap_goal_id, for_update=True)
            metadata = dict(locked_goal.goal_metadata or {})
            metadata["proof_pending"] = True
            locked_goal.goal_metadata = metadata
            flag_modified(locked_goal, "goal_metadata")
            await db.commit()
        except Exception:
            await db.rollback()
            raise
        return WakeResult(
            status="AWAITING_PROOF", task_id=snap_task_id,
            execution_effect=response.execution_effect,
        )
    manager = GoalManager(db)
    try:
        await db.rollback()
        status = await manager.evaluate_dag_stalemate(snap_goal_id)
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return WakeResult(
        status=status.value, task_id=snap_task_id,
        execution_effect=response.execution_effect,
    )

