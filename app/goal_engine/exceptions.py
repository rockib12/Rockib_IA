from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.goal_engine.models import GoalStatus


class GoalLifecycleError(Exception):
    """Exception racine pour les erreurs du cycle de vie des Goals."""

    def __init__(self, code: str, message: str = "") -> None:
        self.code = code
        self.message = message or code
        super().__init__(self.message)


class InvalidGoalTransitionError(GoalLifecycleError):
    """Levée lors d'une transition interdite ou depuis un état terminal de Goal."""

    def __init__(
        self,
        from_status: GoalStatus,
        to_status: GoalStatus,
        reason: str = "",
    ) -> None:
        self.from_status = from_status
        self.to_status = to_status
        from app.goal_engine.models import GoalStatus

        is_terminal = from_status in {
            GoalStatus.COMPLETED,
            GoalStatus.FAILED,
            GoalStatus.CANCELLED,
        }
        code = "TERMINAL_STATE_IMMUTABLE" if is_terminal else "INVALID_GOAL_TRANSITION"
        msg = (
            f"Transition interdite du Goal de {from_status.value} vers "
            f"{to_status.value}"
        )
        if reason:
            msg += f" : {reason}"
        super().__init__(code=code, message=msg)


class GoalNotFoundError(GoalLifecycleError):
    """Levée lorsqu'un Goal spécifié n'existe pas."""

    def __init__(self, goal_id: object, message: str = "") -> None:
        super().__init__(
            code="GOAL_NOT_FOUND",
            message=message or f"Goal {goal_id} introuvable.",
        )


class GoalAutonomyLevelInvalidError(GoalLifecycleError):
    """Levée lorsqu'un niveau d'autonomie est hors bornes [0, 5] ou invalide."""

    def __init__(self, level: object, message: str = "") -> None:
        super().__init__(
            code="INVALID_AUTONOMY_LEVEL",
            message=message
            or f"Niveau d'autonomie invalide ({level}). Doit être entre 0 et 5.",
        )


class GoalWorkspaceMismatchError(GoalLifecycleError):
    """Levée lors d'une incohérence de Workspace (agent ou parent)."""

    def __init__(self, message: str) -> None:
        super().__init__(code="WORKSPACE_MISMATCH", message=message)


class GoalParentNotFoundError(GoalLifecycleError):
    """Levée lorsque le parent_goal_id spécifié n'existe pas."""

    def __init__(self, parent_id: object) -> None:
        super().__init__(
            code="PARENT_GOAL_NOT_FOUND",
            message=f"Parent Goal {parent_id} introuvable.",
        )


class GoalParentCycleError(GoalLifecycleError):
    """Levée lors de la détection d'un cycle dans la chaîne de parenté des Goals."""

    def __init__(
        self, message: str = "Cycle détecté dans la chaîne parentale du Goal."
    ) -> None:
        super().__init__(code="PARENT_CYCLE_DETECTED", message=message)


class GoalParentTerminalError(GoalLifecycleError):
    """Levée lorsqu'un Goal tente de référencer un parent déjà terminal."""

    def __init__(self, parent_status: object) -> None:
        super().__init__(
            code="PARENT_GOAL_TERMINAL",
            message=f"Parent Goal terminal ({parent_status}) non liant.",
        )


class GoalTimezoneNaiveError(GoalLifecycleError):
    """Levée lorsqu'une deadline ou un horodatage est naïf (sans fuseau horaire)."""

    def __init__(
        self,
        message: str = "L'horodatage doit être conscient du fuseau (UTC).",
    ) -> None:
        super().__init__(code="TIMEZONE_NAIVE_DATETIME", message=message)


class GoalDeadlineInvalidError(GoalLifecycleError):
    """Levée lorsqu'une deadline est déjà expirée au moment de sa définition."""

    def __init__(
        self, message: str = "La deadline spécifiée est déjà expirée."
    ) -> None:
        super().__init__(code="DEADLINE_ALREADY_EXPIRED", message=message)


class GoalParentDeadlineExpiredError(GoalLifecycleError):
    """Levée lorsque la deadline du parent est déjà expirée."""

    def __init__(
        self, message: str = "La deadline du Goal parent est déjà expirée."
    ) -> None:
        super().__init__(code="PARENT_DEADLINE_EXPIRED", message=message)


class GoalDeadlineExceededError(GoalLifecycleError):
    """Levée lorsque la deadline d'un Goal est dépassée lors de l'exécution."""

    def __init__(self, message: str = "La deadline du Goal est dépassée.") -> None:
        super().__init__(code="DEADLINE_EXCEEDED", message=message)


class GoalStepLimitExceededError(GoalLifecycleError):
    """Levée lorsque le nombre maximum de steps (max_steps) est atteint."""

    def __init__(self, current_steps: int, max_steps: int) -> None:
        super().__init__(
            code="STEP_LIMIT_EXCEEDED",
            message=f"Limite de steps atteinte ({current_steps}/{max_steps}).",
        )


class GoalReplanningLimitExceededError(GoalLifecycleError):
    """Levée lorsque le quota de replanification est épuisé."""

    def __init__(self, current: int, max_count: int) -> None:
        super().__init__(
            code="REPLANNING_LIMIT_EXCEEDED",
            message=f"Limite de replanification atteinte ({current}/{max_count}).",
        )


class GoalBudgetExceededError(GoalLifecycleError):
    """Levée lorsque le budget alloué au Goal est dépassé."""

    def __init__(self, consumed: object, limit: object) -> None:
        super().__init__(
            code="BUDGET_LIMIT_EXCEEDED",
            message=f"Budget limite dépassé ({consumed} >= {limit}).",
        )


class GoalPlanEmptyError(GoalLifecycleError):
    """Levée lorsque le plan d'un Goal ne contient aucune tâche valide."""

    def __init__(
        self, message: str = "Le plan du Goal ne contient aucune tâche valide."
    ) -> None:
        super().__init__(code="EMPTY_GOAL_PLAN", message=message)


class GoalIncompleteTasksError(GoalLifecycleError):
    """Levée lors d'une tentative d'achèvement alors que des tâches sont inachevées."""

    def __init__(self, incomplete_count: int) -> None:
        super().__init__(
            code="INCOMPLETE_TASKS",
            message=f"{incomplete_count} tâche(s) ne sont pas COMPLETED.",
        )


class GoalMissingSuccessProofError(GoalLifecycleError):
    """Levée lorsqu'aucune preuve externe de succès n'est fournie."""

    def __init__(
        self, message: str = "Preuve externe valide (GoalSuccessProof) requise."
    ) -> None:
        super().__init__(code="MISSING_SUCCESS_PROOF", message=message)


class GoalSuccessCriteriaNotMetError(GoalLifecycleError):
    """Levée lorsque la preuve de succès ne valide pas tous les critères requis."""

    def __init__(self, missing_criteria: list[str]) -> None:
        super().__init__(
            code="SUCCESS_CRITERIA_NOT_MET",
            message=f"Critères non vérifiés : {', '.join(missing_criteria)}.",
        )


class GoalMissingReasonError(GoalLifecycleError):
    """Levée lorsqu'un motif obligatoire est manquant."""

    def __init__(self, action: str) -> None:
        super().__init__(
            code="MISSING_REASON",
            message=f"Un motif explicite est obligatoire pour '{action}'.",
        )


class GoalRunningTasksActiveError(GoalLifecycleError):
    """Levée lorsqu'une replanification est tentée alors que des tâches sont RUNNING."""

    def __init__(self, running_count: int) -> None:
        super().__init__(
            code="RUNNING_TASKS_ACTIVE",
            message=f"Replanification impossible : {running_count} tâche(s) RUNNING.",
        )


class GoalAlreadyTerminalError(GoalLifecycleError):
    """Levée lors d'une tentative de mutation sur un Goal déjà terminal."""

    def __init__(self, status: object) -> None:
        super().__init__(
            code="TERMINAL_STATE_IMMUTABLE",
            message=f"Le Goal est déjà dans l'état terminal {status}.",
        )
