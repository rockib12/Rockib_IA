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
    if (action.tool or "").lower() != "system":
        raise ValueError(
            f"Invalid tool for system_read_handler: expected 'system', got '{action.tool}'"
        )

    if (action.operation or "").lower() != "read":
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
    from app.connectors.fs_connector import fs_read_handler, fs_write_handler
    from app.connectors.social_connectors import (
        facebook_post_handler,
        instagram_post_handler,
        whatsapp_send_handler,
        twitter_post_handler,
        discord_send_handler
    )
    
    from app.connectors.web_connectors import (
        web_search_handler,
        web_fetch_handler
    )
    
    from app.connectors.api_connector import api_call_handler
    from app.connectors.agent_connectors import agent_spawn_handler
    
    register_action_handler("system", "read", system_read_handler)
    register_action_handler("system", "create", fs_write_handler)
    register_action_handler("system", "update", fs_write_handler)
    register_action_handler("system", "write", fs_write_handler)
    register_action_handler("infrastructure", "create", fs_write_handler)
    register_action_handler("infrastructure", "update", fs_write_handler)
    register_action_handler("fs", "read", fs_read_handler)
    register_action_handler("fs", "write", fs_write_handler)
    register_action_handler("fs", "create", fs_write_handler)
    
    # Web Handlers
    register_action_handler("web", "search", web_search_handler)
    register_action_handler("web", "fetch", web_fetch_handler)
    
    # API Handlers
    register_action_handler("api", "call", api_call_handler)
    
    # Agent Handlers
    register_action_handler("agent", "spawn", agent_spawn_handler)
    register_action_handler("agent", "create", agent_spawn_handler)
    
    # Social Network Mock Handlers
    register_action_handler("facebook", "post", facebook_post_handler)
    register_action_handler("instagram", "post", instagram_post_handler)
    register_action_handler("whatsapp", "send", whatsapp_send_handler)
    register_action_handler("twitter", "post", twitter_post_handler)
    register_action_handler("discord", "send", discord_send_handler)

    # Content Handler (rédaction sandboxée, aucun effet externe)
    from app.connectors.content_connector import content_create_handler
    register_action_handler("content", "create", content_create_handler)


# Alias pour compatibilité
register_standard_system_handlers = install_production_handlers

