from __future__ import annotations

from typing import TYPE_CHECKING

from app.goal_engine.exceptions import InvalidGoalTransitionError
from app.goal_engine.models import GoalStatus

if TYPE_CHECKING:
    from app.goal_engine.models import Goal

ALLOWED_TRANSITIONS: dict[GoalStatus, frozenset[GoalStatus]] = {
    GoalStatus.PENDING: frozenset({
        GoalStatus.PLANNING,
        GoalStatus.CANCELLED,
        GoalStatus.FAILED,
    }),
    GoalStatus.PLANNING: frozenset({
        GoalStatus.ACTIVE,
        GoalStatus.PAUSED,
        GoalStatus.FAILED,
        GoalStatus.CANCELLED,
    }),
    GoalStatus.ACTIVE: frozenset({
        GoalStatus.PLANNING,
        GoalStatus.PAUSED,
        GoalStatus.COMPLETED,
        GoalStatus.FAILED,
        GoalStatus.CANCELLED,
    }),
    GoalStatus.PAUSED: frozenset({
        GoalStatus.PLANNING,
        GoalStatus.ACTIVE,
        GoalStatus.FAILED,
        GoalStatus.CANCELLED,
    }),
    GoalStatus.COMPLETED: frozenset(),
    GoalStatus.FAILED: frozenset(),
    GoalStatus.CANCELLED: frozenset(),
}

TERMINAL_STATES: frozenset[GoalStatus] = frozenset({
    GoalStatus.COMPLETED,
    GoalStatus.FAILED,
    GoalStatus.CANCELLED,
})


class GoalStateMachine:
    """Machine d'état déterministe pour le cycle de vie d'un Goal.

    Garanties :
    - Pur déterminisme (sans I/O, sans persistance, sans dépendance externe).
    - Validation stricte des transitions autorisées.
    - Immutabilité absolue des états terminaux (INV-10).
    """

    @staticmethod
    def is_terminal(status: GoalStatus) -> bool:
        """Indique si un statut est terminal (COMPLETED, FAILED, CANCELLED)."""
        return status in TERMINAL_STATES

    @staticmethod
    def can_transition(from_status: GoalStatus, to_status: GoalStatus) -> bool:
        """Retourne True si la transition de from_status vers to_status est autorisée."""
        if from_status in TERMINAL_STATES:
            return False
        return to_status in ALLOWED_TRANSITIONS.get(from_status, frozenset())

    @classmethod
    def validate_transition(
        cls, from_status: GoalStatus, to_status: GoalStatus
    ) -> None:
        """Valide une transition de statut.

        Lève InvalidGoalTransitionError si la transition est interdite :
        - avec code 'TERMINAL_STATE_IMMUTABLE' si from_status est terminal (INV-10).
        - avec code 'INVALID_GOAL_TRANSITION' pour toute autre transition interdite.
        """
        if cls.is_terminal(from_status):
            raise InvalidGoalTransitionError(
                from_status,
                to_status,
                reason=f"L'état terminal {from_status.value} est immuable (INV-10).",
            )
        if not cls.can_transition(from_status, to_status):
            raise InvalidGoalTransitionError(
                from_status,
                to_status,
                reason="Transition non autorisée dans le cycle de vie du goal.",
            )

    @classmethod
    def transition(cls, goal: Goal, to_status: GoalStatus) -> Goal:
        """Applique la transition en mémoire sur l'objet Goal.

        Si la transition est invalide, lève InvalidGoalTransitionError sans altérer
        le statut actuel du goal (garantie d'intégrité).
        """
        cls.validate_transition(goal.status, to_status)
        goal.status = to_status
        return goal
