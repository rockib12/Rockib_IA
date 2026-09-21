from __future__ import annotations

from typing import TYPE_CHECKING

from app.task_engine.exceptions import InvalidTaskTransitionError
from app.task_engine.models import TaskStatus

if TYPE_CHECKING:
    from app.task_engine.models import Task

ALLOWED_TRANSITIONS: dict[TaskStatus, frozenset[TaskStatus]] = {
    TaskStatus.PENDING: frozenset({
        TaskStatus.READY,
        TaskStatus.BLOCKED,
        TaskStatus.CANCELLED,
        TaskStatus.FAILED,
    }),
    TaskStatus.READY: frozenset({
        TaskStatus.RUNNING,
        TaskStatus.BLOCKED,
        TaskStatus.CANCELLED,
        TaskStatus.FAILED,
    }),
    TaskStatus.RUNNING: frozenset({
        TaskStatus.COMPLETED,
        TaskStatus.BLOCKED,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
    }),
    TaskStatus.BLOCKED: frozenset({
        TaskStatus.READY,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
    }),
    TaskStatus.COMPLETED: frozenset(),
    TaskStatus.FAILED: frozenset(),
    TaskStatus.CANCELLED: frozenset(),
}

TERMINAL_STATES: frozenset[TaskStatus] = frozenset({
    TaskStatus.COMPLETED,
    TaskStatus.FAILED,
    TaskStatus.CANCELLED,
})


class TaskStateMachine:
    """Machine d'état déterministe pour le cycle de vie d'une Task.

    Garanties :
    - Pur déterminisme (sans I/O, sans persistance, sans dépendance externe).
    - Validation stricte des transitions autorisées.
    - Immutabilité absolue des états terminaux (INV-10).
    """

    @staticmethod
    def is_terminal(status: TaskStatus) -> bool:
        """Indique si un statut est terminal (COMPLETED, FAILED, CANCELLED)."""
        return status in TERMINAL_STATES

    @staticmethod
    def can_transition(from_status: TaskStatus, to_status: TaskStatus) -> bool:
        """Retourne True si la transition de from_status vers to_status est autorisée."""
        if from_status in TERMINAL_STATES:
            return False
        return to_status in ALLOWED_TRANSITIONS.get(from_status, frozenset())

    @classmethod
    def validate_transition(
        cls, from_status: TaskStatus, to_status: TaskStatus
    ) -> None:
        """Valide une transition de statut.

        Lève InvalidTaskTransitionError si la transition est interdite :
        - avec code 'TERMINAL_STATE_IMMUTABLE' si from_status est terminal (INV-10).
        - avec code 'INVALID_TASK_TRANSITION' pour toute autre transition interdite.
        """
        if cls.is_terminal(from_status):
            raise InvalidTaskTransitionError(
                from_status,
                to_status,
                reason=f"L'état terminal {from_status.value} est immuable (INV-10).",
            )
        if not cls.can_transition(from_status, to_status):
            raise InvalidTaskTransitionError(
                from_status,
                to_status,
                reason="Transition non autorisée dans le cycle de vie de la tâche.",
            )

    @classmethod
    def transition(cls, task: Task, to_status: TaskStatus) -> Task:
        """Applique la transition en mémoire sur l'objet Task.

        Si la transition est invalide, lève InvalidTaskTransitionError sans altérer
        le statut actuel de la tâche (garantie d'intégrité).
        """
        cls.validate_transition(task.status, to_status)
        task.status = to_status
        return task
