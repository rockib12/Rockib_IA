from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.task_engine.models import TaskStatus


class TaskStateError(Exception):
    """Exception racine pour les erreurs d'état du Task Engine."""

    def __init__(self, code: str, message: str = "") -> None:
        self.code = code
        self.message = message or code
        super().__init__(self.message)


class InvalidTaskTransitionError(TaskStateError):
    """Levée lors d'une tentative de transition interdite ou depuis un état terminal."""

    def __init__(
        self,
        from_status: TaskStatus,
        to_status: TaskStatus,
        reason: str = "",
    ) -> None:
        self.from_status = from_status
        self.to_status = to_status
        from app.task_engine.models import TaskStatus

        is_terminal = from_status in {
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
        }
        code = (
            "TERMINAL_STATE_IMMUTABLE" if is_terminal else "INVALID_TASK_TRANSITION"
        )
        msg = f"Transition interdite de {from_status.value} vers {to_status.value}"
        if reason:
            msg += f" : {reason}"
        super().__init__(code=code, message=msg)


class TaskGraphError(TaskStateError):
    """Exception racine pour les erreurs liées au TaskGraph."""

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(code=code, message=message)


class TaskGraphCycleError(TaskGraphError):
    """Levée lorsqu'un cycle est détecté dans le graphe de tâches."""

    def __init__(
        self,
        message: str = "Un cycle a été détecté dans le graphe de tâches.",
    ) -> None:
        super().__init__(code="TASK_GRAPH_CYCLE", message=message)


class TaskDependencyValidationError(TaskGraphError):
    """Levée lorsqu'une dépendance viole une règle d'intégrité métier en mémoire."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(code=code, message=message)
