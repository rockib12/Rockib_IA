from dataclasses import dataclass
from decimal import Decimal
from typing import Callable, Awaitable
from app.decision_engine.models import Decision, PermissionAction
from app.execution.services.guard import evaluate

@dataclass
class ExecutionResult:
    """Résultat d'un appel d'outil.

    ``effect_unknown`` porte l'incertitude de façon explicite : un timeout ambigu ou
    une exception après engagement ne sont ni un succès ni un échec franc (INV-09).
    """

    success: bool
    output: str | None
    error: str | None
    error_code: str | None = None
    provider_reference: str | None = None
    cost_amount: Decimal | None = None
    cost_unit: str | None = None
    effect_unknown: bool = False

# Registre domaine (basé sur PermissionAction) -> handler
_HANDLERS: dict[PermissionAction, Callable[[Decision], Awaitable[ExecutionResult]]] = {}

def register_handler(action: PermissionAction, handler: Callable[[Decision], Awaitable[ExecutionResult]]) -> None:
    """Enregistre un handler pour une action donnée."""
    _HANDLERS[action] = handler

async def execute(decision: Decision) -> ExecutionResult:
    """Vérifie la permission puis exécute via le handler."""
    permission = evaluate(decision)
    if not permission.allowed:
        return ExecutionResult(success=False, output=None, error=permission.reason)

    handler = _HANDLERS.get(decision.permission_required)
    if handler is None:
        return ExecutionResult(success=False, output=None, error=f"Aucun handler enregistré pour l'action {decision.permission_required}")

    return await handler(decision)
