"""Empreinte canonique d'action et clé d'idempotence.

L'empreinte est ce qui rend une autorisation non transférable (INV-03) : modifier
un argument, l'outil, l'opération ou le destinataire produit une empreinte
différente, donc l'autorisation précédente ne s'applique plus.

La sérialisation est canonique (clés triées, séparateurs fixes, encodage UTF-8)
pour qu'un même contenu produise toujours la même empreinte, indépendamment de
l'ordre d'insertion des clés ou du formatage JSON du client.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Optional

from app.decision_engine.models import PermissionAction

# Champs couverts par l'empreinte : tout ce qui décrit l'effet réel.
FINGERPRINT_FIELDS = (
    "workspace_id",
    "agent_id",
    "tool",
    "operation",
    "permission_required",
    "objective",
)


def _normalize(value: Any) -> Any:
    """Normalise récursivement une valeur pour une sérialisation stable."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _normalize(value[key]) for key in sorted(value, key=str)}
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    if isinstance(value, (set, frozenset)):
        # Un ensemble n'a pas d'ordre : on trie sa représentation normalisée.
        return sorted((_normalize(item) for item in value), key=lambda item: json.dumps(item, sort_keys=True))
    return str(value)


def canonical_payload(
    *,
    workspace_id: Any,
    agent_id: Any,
    tool: str,
    operation: str,
    permission_required: PermissionAction | str,
    objective: str,
    arguments: Optional[Mapping[str, Any]] = None,
) -> str:
    """Sérialisation canonique des éléments qui déterminent l'effet."""
    permission = (
        permission_required.value
        if isinstance(permission_required, PermissionAction)
        else str(permission_required)
    )
    payload = {
        "workspace_id": str(workspace_id),
        "agent_id": str(agent_id),
        "tool": tool,
        "operation": operation,
        "permission_required": permission,
        "objective": objective,
        "arguments": _normalize(dict(arguments or {})),
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def compute_fingerprint(
    *,
    workspace_id: Any,
    agent_id: Any,
    tool: str,
    operation: str,
    permission_required: PermissionAction | str,
    objective: str,
    arguments: Optional[Mapping[str, Any]] = None,
) -> str:
    """SHA-256 hexadécimal de la charge canonique (64 caractères)."""
    payload = canonical_payload(
        workspace_id=workspace_id,
        agent_id=agent_id,
        tool=tool,
        operation=operation,
        permission_required=permission_required,
        objective=objective,
        arguments=arguments,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def compute_idempotency_key(
    *,
    workspace_id: Any,
    tool: str,
    operation: str,
    idempotency_scope: str,
) -> str:
    """Identifie l'opération logique, indépendamment de la tentative.

    Deux tentatives de la même opération logique partagent cette clé : c'est ce qui
    permet de refuser un doublon (INV-08, §8 « une contrainte durable protège
    l'opération logique contre les doublons »).
    """
    material = "|".join(
        [str(workspace_id), tool, operation, idempotency_scope]
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:128]
