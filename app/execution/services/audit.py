"""Audit durable (INV-11) : écriture append-only, corrélée et filtrée des secrets.

Le journal est un objet de persistance, pas un simple log : chaque événement de
contrôle, de tentative et d'effet est écrit dans ``audit_entries`` avec les
identifiants corrélés et la version de politique. Un logger ``INFO`` reste émis en
complément, mais il ne garantit pas la durabilité et ne remplace pas la table.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Mapping, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.execution.models import AuditEntry, AuditEventType

logger = logging.getLogger("rockib.audit")

# Fragments de noms de champs qui ne doivent jamais atteindre le journal.
_SECRET_MARKERS = (
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "authorization",
    "credential",
    "private_key",
)

_REDACTED = "[REDACTED]"
_MAX_DEPTH = 6


def redact(payload: Any, _depth: int = 0) -> Any:
    """Retire récursivement toute valeur dont la clé évoque un secret."""
    if _depth >= _MAX_DEPTH:
        return "[TRUNCATED]"
    if isinstance(payload, Mapping):
        cleaned: dict[str, Any] = {}
        for key, value in payload.items():
            key_str = str(key)
            if any(marker in key_str.lower() for marker in _SECRET_MARKERS):
                cleaned[key_str] = _REDACTED
            else:
                cleaned[key_str] = redact(value, _depth + 1)
        return cleaned
    if isinstance(payload, (list, tuple)):
        return [redact(item, _depth + 1) for item in payload]
    return payload


def build_entry(
    *,
    event_type: AuditEventType,
    workspace_id: uuid.UUID,
    actor: str,
    agent_id: Optional[uuid.UUID] = None,
    decision_id: Optional[uuid.UUID] = None,
    action_id: Optional[uuid.UUID] = None,
    authorization_id: Optional[uuid.UUID] = None,
    attempt_id: Optional[uuid.UUID] = None,
    reason_code: Optional[str] = None,
    action_fingerprint: Optional[str] = None,
    policy_version: Optional[str] = None,
    payload: Optional[Mapping[str, Any]] = None,
) -> AuditEntry:
    """Construit l'entrée d'audit sans l'ajouter à la session."""
    return AuditEntry(
        event_type=event_type,
        workspace_id=workspace_id,
        agent_id=agent_id,
        decision_id=decision_id,
        action_id=action_id,
        authorization_id=authorization_id,
        attempt_id=attempt_id,
        reason_code=reason_code,
        action_fingerprint=action_fingerprint,
        policy_version=policy_version,
        actor=actor,
        payload=redact(dict(payload or {})),
    )


async def record(
    db: AsyncSession,
    *,
    event_type: AuditEventType,
    workspace_id: uuid.UUID,
    actor: str,
    payload: Optional[Mapping[str, Any]] = None,
    **correlation: Any,
) -> AuditEntry:
    """Écrit un événement d'audit dans la transaction courante.

    L'appelant décide du ``commit`` : l'audit doit être committé avec la
    transition qu'il décrit, jamais séparément d'elle.
    """
    entry = build_entry(
        event_type=event_type,
        workspace_id=workspace_id,
        actor=actor,
        payload=payload,
        **correlation,
    )
    db.add(entry)
    await db.flush()
    logger.info(
        "audit event=%s workspace=%s action=%s attempt=%s reason=%s",
        entry.event_type.value if hasattr(entry.event_type, "value") else entry.event_type,
        workspace_id,
        correlation.get("action_id"),
        correlation.get("attempt_id"),
        correlation.get("reason_code"),
    )
    return entry
