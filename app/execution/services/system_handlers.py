"""Handlers d'action système de production (STEP 5C.4).

Implémente le handler de diagnostic interne déterministe pour (tool="system", operation="read").
Aucun accès réseau, aucun accès fichier arbitraire, aucune commande shell, aucune mutation DB.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal

from app.execution.models import ActionRecord
from app.execution.services.executor import ExecutionResult
from app.execution.services.reliable_executor import register_action_handler


async def system_read_handler(action: ActionRecord) -> ExecutionResult:
    """Handler déterministe de diagnostic interne pour (system, read)."""
    if action.tool != "system":
        raise ValueError(
            f"Invalid tool for system_read_handler: expected 'system', got '{action.tool}'"
        )

    if action.operation != "read":
        raise ValueError(
            f"Invalid operation for system_read_handler: expected 'read', got '{action.operation}'"
        )

    if action.workspace_id is None:
        raise ValueError("ActionRecord must have a non-null workspace_id")

    diagnostics = {
        "status": "operational",
        "tool": action.tool,
        "operation": action.operation,
        "workspace_id": str(action.workspace_id),
        "agent_id": str(action.agent_id),
        "action_id": str(action.id),
        "task_id": str(action.task_id) if action.task_id else None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    return ExecutionResult(
        success=True,
        output=json.dumps(diagnostics, separators=(",", ":")),
        error=None,
        error_code=None,
        provider_reference="system:diagnostics",
        cost_amount=Decimal("0.0"),
        cost_unit="credits",
        effect_unknown=False,
    )


def install_production_handlers() -> None:
    """Enregistre les handlers de production dans le registre officiel."""
    register_action_handler("system", "read", system_read_handler)
