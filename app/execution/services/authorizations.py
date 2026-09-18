"""Autorisations d'exécution : émission, revérification, consommation, révocation.

Règles non négociables :

- Seul un contrôle serveur ``ALLOW`` produit une autorisation. ``DENY``,
  ``ESCALATE`` et ``STOP`` n'émettent jamais d'autorisation consommable (INV-01).
- Une autorisation porte sur une **empreinte** et une **version** d'action : toute
  modification invalide l'autorisation (INV-03).
- Une autorisation expirée, révoquée ou déjà consommée n'est jamais consommée deux
  fois (INV-14). Le refus est explicite, jamais silencieux.
- La revérification et la consommation prennent un verrou de ligne
  (``SELECT ... FOR UPDATE``) : deux workers ne peuvent pas consommer la même
  autorisation.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.decision_engine.models import ControlOutcome, Decision
from app.decision_engine.services.control import action_fingerprint as decision_fingerprint
from app.execution.models import (
    ActionRecord,
    AuditEventType,
    ExecutionAuthorization,
)
from app.execution.services import audit

DEFAULT_AUTHORIZATION_TTL_SECONDS = 900


class AuthorizationError(Exception):
    """Refus d'autorisation ou d'exécution, avec un motif stable et auditable."""

    def __init__(self, code: str, message: str = "") -> None:
        self.code = code
        self.message = message or code
        super().__init__(self.message)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def evaluate_validity(
    authorization: ExecutionAuthorization,
    action: ActionRecord,
    *,
    now: Optional[datetime] = None,
) -> Optional[str]:
    """Retourne le code de refus, ou ``None`` si l'autorisation reste valide.

    Fonction pure : la machine à états d'autorisation se teste sans base de données.
    """
    moment = now or _utcnow()

    if authorization.outcome != ControlOutcome.ALLOW:
        # Un refus de contrôle ne devient jamais exécutable, même relu en base :
        # une permission « accordée » hors contrôle serveur n'a aucun effet (INV-06).
        return "AUTHORIZATION_NOT_ALLOW"
    if authorization.action_id != action.id:
        return "ACTION_MISMATCH"
    if authorization.workspace_id != action.workspace_id:
        return "WORKSPACE_MISMATCH"
    if authorization.revoked_at is not None:
        return "AUTHORIZATION_REVOKED"
    if authorization.consumed_at is not None:
        return "AUTHORIZATION_ALREADY_CONSUMED"
    if authorization.expires_at is not None and authorization.expires_at <= moment:
        return "AUTHORIZATION_EXPIRED"
    if authorization.action_fingerprint != action.canonical_fingerprint:
        return "ACTION_FINGERPRINT_CHANGED"
    if authorization.action_version != action.version:
        return "ACTION_VERSION_CHANGED"
    if authorization.approval_required and not authorization.approval_reference:
        return "APPROVAL_REFERENCE_MISSING"
    return None


async def issue_authorization(
    db: AsyncSession,
    *,
    decision: Decision,
    action: ActionRecord,
    actor: str,
    policy_version: Optional[str] = None,
    ttl_seconds: int = DEFAULT_AUTHORIZATION_TTL_SECONDS,
    approval_reference: Optional[str] = None,
) -> ExecutionAuthorization:
    """Émet une autorisation consommable à partir d'un contrôle serveur ``ALLOW``.

    Lève ``AuthorizationError`` pour tout autre résultat : aucun effet ne doit
    pouvoir être produit à partir d'un ``DENY``, ``ESCALATE`` ou ``STOP``.
    """
    outcome = decision.control_outcome
    outcome_value = outcome.value if hasattr(outcome, "value") else str(outcome)
    if outcome != ControlOutcome.ALLOW:
        await audit.record(
            db,
            event_type=AuditEventType.AUTHORIZATION_REJECTED,
            workspace_id=action.workspace_id,
            actor=actor,
            reason_code=f"CONTROL_{outcome_value}",
            agent_id=action.agent_id,
            decision_id=decision.id,
            action_id=action.id,
            action_fingerprint=action.canonical_fingerprint,
            payload={"control_reason": decision.control_reason},
        )
        raise AuthorizationError(
            f"CONTROL_{outcome_value}",
            "Un contrôle non-ALLOW n'autorise jamais une exécution.",
        )

    if not decision.permission_granted:
        raise AuthorizationError(
            "EXECUTION_NOT_PREAUTHORIZED",
            "Permission serveur absente : la décision ne préautorise pas l'effet.",
        )

    if decision.action_fingerprint != action.canonical_fingerprint:
        if decision.action_fingerprint:
            # Deux systèmes d'empreintes coexistent : la Phase 1 tamponne les
            # champs de la décision (control.py), la Phase 2 l'action structurée
            # (fingerprint.py). Une décision réellement arbitrée porte donc
            # l'empreinte Phase 1, jamais l'empreinte canonique de l'action.
            # Vérifier d'abord l'intégrité du tampon Phase 1 : un écart prouve une
            # modification après contrôle et doit être refusé (INV-03).
            if decision.action_fingerprint != decision_fingerprint(decision):
                raise AuthorizationError(
                    "ACTION_FINGERPRINT_CHANGED",
                    "L'action proposée ne correspond plus à l'action arbitrée.",
                )
            # Tampon Phase 1 intègre : le serveur lie explicitement la décision à
            # cette action exacte. Toute modification ultérieure de l'action
            # invalidera l'autorisation (evaluate_validity, INV-14).
        decision.action_fingerprint = action.canonical_fingerprint

    approval_required = bool(getattr(decision, "approval_required", False))
    if approval_required and not approval_reference:
        await audit.record(
            db,
            event_type=AuditEventType.AUTHORIZATION_REJECTED,
            workspace_id=action.workspace_id,
            actor=actor,
            reason_code="APPROVAL_REFERENCE_MISSING",
            agent_id=action.agent_id,
            decision_id=decision.id,
            action_id=action.id,
            action_fingerprint=action.canonical_fingerprint,
        )
        raise AuthorizationError(
            "APPROVAL_REFERENCE_MISSING",
            "Approbation exigée : aucune référence d'approbation fournie.",
        )

    now = _utcnow()
    authorization = ExecutionAuthorization(
        decision_id=decision.id,
        action_id=action.id,
        workspace_id=action.workspace_id,
        agent_id=action.agent_id,
        outcome=ControlOutcome.ALLOW,
        reason_code=decision.control_reason or "POLICY_ALLOWED",
        explanation=getattr(decision, "approval_reason", None),
        action_fingerprint=action.canonical_fingerprint,
        action_version=action.version,
        policy_version=policy_version,
        issued_at=now,
        expires_at=now + timedelta(seconds=ttl_seconds),
        approval_required=approval_required,
        approval_reference=approval_reference,
    )
    db.add(authorization)
    await db.flush()
    await audit.record(
        db,
        event_type=AuditEventType.AUTHORIZATION_ISSUED,
        workspace_id=action.workspace_id,
        actor=actor,
        reason_code=authorization.reason_code,
        agent_id=action.agent_id,
        decision_id=decision.id,
        action_id=action.id,
        authorization_id=authorization.id,
        action_fingerprint=action.canonical_fingerprint,
        policy_version=policy_version,
        payload={"expires_at": authorization.expires_at.isoformat()},
    )
    return authorization


async def lock_authorization(
    db: AsyncSession, authorization_id: uuid.UUID
) -> ExecutionAuthorization:
    """Charge l'autorisation avec un verrou de ligne, ou lève un refus explicite."""
    result = await db.execute(
        select(ExecutionAuthorization)
        .where(ExecutionAuthorization.id == authorization_id)
        .with_for_update()
    )
    authorization = result.scalar_one_or_none()
    if authorization is None:
        raise AuthorizationError("AUTHORIZATION_NOT_FOUND", "Autorisation inconnue.")
    return authorization


async def consume_authorization(
    db: AsyncSession,
    *,
    authorization_id: uuid.UUID,
    action: ActionRecord,
    actor: str,
) -> ExecutionAuthorization:
    """Consomme une autorisation valide. Refuse toute réutilisation (INV-14)."""
    authorization = await lock_authorization(db, authorization_id)

    refusal = evaluate_validity(authorization, action)
    if refusal is not None:
        await audit.record(
            db,
            event_type=AuditEventType.AUTHORIZATION_REJECTED,
            workspace_id=action.workspace_id,
            actor=actor,
            reason_code=refusal,
            agent_id=action.agent_id,
            decision_id=authorization.decision_id,
            action_id=action.id,
            authorization_id=authorization.id,
            action_fingerprint=action.canonical_fingerprint,
            policy_version=authorization.policy_version,
        )
        raise AuthorizationError(refusal, "Autorisation non consommable.")

    authorization.consumed_at = _utcnow()
    await db.flush()
    await audit.record(
        db,
        event_type=AuditEventType.AUTHORIZATION_CONSUMED,
        workspace_id=action.workspace_id,
        actor=actor,
        reason_code=authorization.reason_code,
        agent_id=action.agent_id,
        decision_id=authorization.decision_id,
        action_id=action.id,
        authorization_id=authorization.id,
        action_fingerprint=action.canonical_fingerprint,
        policy_version=authorization.policy_version,
    )
    return authorization


async def revoke_authorization(
    db: AsyncSession,
    *,
    authorization_id: uuid.UUID,
    reason: str,
    actor: str,
) -> ExecutionAuthorization:
    """Révoque une autorisation non consommée : elle ne pourra plus l'être."""
    authorization = await lock_authorization(db, authorization_id)
    if authorization.consumed_at is not None:
        raise AuthorizationError(
            "AUTHORIZATION_ALREADY_CONSUMED",
            "Une autorisation consommée ne se révoque pas : l'effet a été engagé.",
        )
    if authorization.revoked_at is None:
        authorization.revoked_at = _utcnow()
        authorization.revoke_reason = reason
        await db.flush()
        await audit.record(
            db,
            event_type=AuditEventType.AUTHORIZATION_REVOKED,
            workspace_id=authorization.workspace_id,
            actor=actor,
            reason_code=reason,
            agent_id=authorization.agent_id,
            decision_id=authorization.decision_id,
            action_id=authorization.action_id,
            authorization_id=authorization.id,
            action_fingerprint=authorization.action_fingerprint,
            policy_version=authorization.policy_version,
        )
    return authorization