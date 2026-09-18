"""Tentatives d'exécution : prise en charge exclusive, résultat, réconciliation.

- La prise en charge est un ``UPDATE`` conditionnel ``PENDING -> RUNNING`` : deux
  workers ne peuvent pas exécuter la même tentative (``rowcount`` vérifié).
- Un bail expiré ne prouve pas l'absence d'effet : la tentative passe à ``UNKNOWN``
  et aucune répétition aveugle n'est autorisée (INV-09).
- Un succès est terminal : il n'est pas rejoué (INV-10).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.execution.models import (
    ActionRecord,
    AttemptStatus,
    AuditEventType,
    EffectCertainty,
    ExecutionAttempt,
    ExecutionResultRecord,
)
from app.execution.services import audit
from app.execution.services.authorizations import AuthorizationError

DEFAULT_LEASE_SECONDS = 60

TERMINAL_ATTEMPT_STATUSES = (
    AttemptStatus.SUCCEEDED,
    AttemptStatus.FAILED,
    AttemptStatus.UNKNOWN,
    AttemptStatus.CANCELLED,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def _next_attempt_number(
    db: AsyncSession, *, authorization_id: uuid.UUID
) -> int:
    result = await db.execute(
        select(func.coalesce(func.max(ExecutionAttempt.attempt_number), 0)).where(
            ExecutionAttempt.authorization_id == authorization_id
        )
    )
    return int(result.scalar_one() or 0) + 1


async def claim_attempt(
    db: AsyncSession,
    *,
    action: ActionRecord,
    authorization_id: uuid.UUID,
    idempotency_key: str,
    actor: str,
    lease_owner: str,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
) -> ExecutionAttempt:
    """Enregistre puis prend en charge exclusivement une tentative d'exécution."""
    # Un succès déjà établi interdit toute nouvelle tentative (INV-10).
    succeeded = await db.execute(
        select(ExecutionAttempt.id).where(
            ExecutionAttempt.authorization_id == authorization_id,
            ExecutionAttempt.status == AttemptStatus.SUCCEEDED,
        )
    )
    if succeeded.first() is not None:
        raise AuthorizationError(
            "ATTEMPT_ALREADY_SUCCEEDED",
            "Un effet a déjà été confirmé pour cette autorisation : pas de rejeu.",
        )

    # Un effet incertain interdit toute répétition aveugle : il faut d'abord
    # réconcilier la tentative à effet inconnu (INV-09).
    uncertain = await db.execute(
        select(ExecutionAttempt.id).where(
            ExecutionAttempt.authorization_id == authorization_id,
            ExecutionAttempt.status == AttemptStatus.UNKNOWN,
        )
    )
    if uncertain.first() is not None:
        raise AuthorizationError(
            "EFFECT_UNKNOWN_REQUIRES_RECONCILIATION",
            "Une tentative à effet incertain doit être réconciliée avant tout nouvel essai.",
        )

    # Une exécution en cours avec un bail vivant bloque toute concurrence.
    running = await db.execute(
        select(ExecutionAttempt).where(
            ExecutionAttempt.authorization_id == authorization_id,
            ExecutionAttempt.status == AttemptStatus.RUNNING,
        )
    )
    in_flight = running.scalars().all()
    now = _utcnow()
    for attempt in in_flight:
        if attempt.lease_expires_at is None or attempt.lease_expires_at > now:
            raise AuthorizationError(
                "ATTEMPT_ALREADY_RUNNING",
                "Une tentative est déjà en cours de prise en charge.",
            )
        # Bail expiré : l'effet est incertain, on ne rejoue pas.
        await mark_unknown(
            db,
            attempt=attempt,
            reason="LEASE_EXPIRED",
            actor=actor,
            decision_id=action.decision_id,
        )
    if in_flight:
        raise AuthorizationError(
            "LEASE_EXPIRED_EFFECT_UNKNOWN",
            "Bail expiré : l'effet est incertain et doit être réconcilié avant tout rejeu.",
        )

    attempt = ExecutionAttempt(
        action_id=action.id,
        authorization_id=authorization_id,
        workspace_id=action.workspace_id,
        attempt_number=await _next_attempt_number(db, authorization_id=authorization_id),
        idempotency_key=idempotency_key,
        status=AttemptStatus.PENDING,
    )
    db.add(attempt)
    await db.flush()

    # Transition conditionnelle : seule la première prise en charge réussit.
    claimed = await db.execute(
        update(ExecutionAttempt)
        .where(
            ExecutionAttempt.id == attempt.id,
            ExecutionAttempt.status == AttemptStatus.PENDING,
        )
        .values(
            status=AttemptStatus.RUNNING,
            lease_owner=lease_owner,
            lease_expires_at=now + timedelta(seconds=lease_seconds),
            claimed_at=now,
            started_at=now,
        )
    )
    if claimed.rowcount != 1:
        raise AuthorizationError(
            "ATTEMPT_CLAIM_CONFLICT",
            "Prise en charge refusée : une autre prise en charge a eu lieu.",
        )
    await db.refresh(attempt)
    await audit.record(
        db,
        event_type=AuditEventType.ATTEMPT_CLAIMED,
        workspace_id=action.workspace_id,
        actor=actor,
        reason_code="LEASE_ACQUIRED",
        agent_id=action.agent_id,
        action_id=action.id,
        decision_id=action.decision_id,
        authorization_id=authorization_id,
        attempt_id=attempt.id,
        action_fingerprint=action.canonical_fingerprint,
        payload={"attempt_number": attempt.attempt_number, "lease_owner": lease_owner},
    )
    return attempt


def _audit_event_for(effect: EffectCertainty) -> AuditEventType:
    if effect == EffectCertainty.confirmed:
        return AuditEventType.EFFECT_CONFIRMED
    if effect == EffectCertainty.none:
        return AuditEventType.EFFECT_FAILED
    return AuditEventType.EFFECT_UNKNOWN


async def record_result(
    db: AsyncSession,
    *,
    attempt: ExecutionAttempt,
    effect: EffectCertainty,
    actor: str,
    success: Optional[bool] = None,
    output_summary: Optional[str] = None,
    error_code: Optional[str] = None,
    error_message: Optional[str] = None,
    provider_reference: Optional[str] = None,
    evidence_reference: Optional[str] = None,
    cost_amount: Optional[Decimal] = None,
    cost_unit: Optional[str] = None,
    action_fingerprint: Optional[str] = None,
    decision_id: Optional[uuid.UUID] = None,
) -> ExecutionResultRecord:
    """Persiste le résultat d'une tentative et ferme son état.

    Un effet ``unknown`` n'est pas une erreur : c'est un état explicite qui exige une
    réconciliation et interdit la répétition aveugle.
    """
    if attempt.status in TERMINAL_ATTEMPT_STATUSES:
        raise AuthorizationError(
            "ATTEMPT_ALREADY_CLOSED",
            "Une tentative terminale n'est pas réécrite : un essai suivant est un nouvel enregistrement.",
        )

    result = ExecutionResultRecord(
        attempt_id=attempt.id,
        effect=effect,
        success=success,
        output_summary=output_summary,
        error_code=error_code,
        error_message=error_message,
        provider_reference=provider_reference,
        evidence_reference=evidence_reference,
        cost_amount=cost_amount,
        cost_unit=cost_unit,
        observed_at=_utcnow(),
    )
    db.add(result)

    if effect == EffectCertainty.confirmed:
        attempt.status = AttemptStatus.SUCCEEDED
    elif effect == EffectCertainty.none:
        attempt.status = AttemptStatus.FAILED
    else:
        attempt.status = AttemptStatus.UNKNOWN
    attempt.finished_at = _utcnow()
    attempt.failure_reason = error_code
    if provider_reference:
        attempt.provider_reference = provider_reference
    await db.flush()

    await audit.record(
        db,
        event_type=_audit_event_for(effect),
        workspace_id=attempt.workspace_id,
        actor=actor,
        reason_code=error_code or effect.value,
        action_id=attempt.action_id,
        decision_id=decision_id,
        authorization_id=attempt.authorization_id,
        attempt_id=attempt.id,
        action_fingerprint=action_fingerprint,
        payload={
            "effect": effect.value,
            "success": success,
            "provider_reference": provider_reference,
            "evidence_reference": evidence_reference,
            "cost_amount": str(cost_amount) if cost_amount is not None else None,
            "cost_unit": cost_unit,
        },
    )
    return result


async def mark_unknown(
    db: AsyncSession,
    *,
    attempt: ExecutionAttempt,
    reason: str,
    actor: str,
    action_fingerprint: Optional[str] = None,
    decision_id: Optional[uuid.UUID] = None,
) -> ExecutionAttempt:
    """Marque une tentative comme à effet incertain, sans conclure.

    Ni succès ni échec : l'effet est peut-être survenu et ne se résout que par
    réconciliation (INV-09).
    """
    if attempt.status in TERMINAL_ATTEMPT_STATUSES:
        return attempt
    attempt.status = AttemptStatus.UNKNOWN
    attempt.failure_reason = reason
    attempt.finished_at = _utcnow()
    await db.flush()
    await audit.record(
        db,
        event_type=AuditEventType.EFFECT_UNKNOWN,
        workspace_id=attempt.workspace_id,
        actor=actor,
        reason_code=reason,
        action_id=attempt.action_id,
        decision_id=decision_id,
        authorization_id=attempt.authorization_id,
        attempt_id=attempt.id,
        action_fingerprint=action_fingerprint,
        payload={"lease_owner": attempt.lease_owner},
    )
    return attempt


async def reconcile_attempt(
    db: AsyncSession,
    *,
    attempt_id: uuid.UUID,
    resolved_effect: EffectCertainty,
    actor: str,
    evidence_reference: str,
    provider_reference: Optional[str] = None,
    cost_amount: Optional[Decimal] = None,
    cost_unit: Optional[str] = None,
    decision_id: Optional[uuid.UUID] = None,
) -> ExecutionAttempt:
    """Résout une tentative ``UNKNOWN`` à partir de preuves de réconciliation.

    Sans référence de preuve, la réconciliation est refusée : une déclaration ne
    remplace pas une observation.
    """
    if resolved_effect == EffectCertainty.unknown:
        raise AuthorizationError(
            "RECONCILIATION_INCONCLUSIVE",
            "Une réconciliation doit conclure : effet confirmé ou absence d'effet.",
        )
    if not evidence_reference:
        raise AuthorizationError(
            "RECONCILIATION_EVIDENCE_MISSING",
            "Aucune preuve fournie : l'incertitude reste ouverte.",
        )

    attempt = await db.get(ExecutionAttempt, attempt_id)
    if attempt is None:
        raise AuthorizationError("ATTEMPT_NOT_FOUND", "Tentative inconnue.")
    if attempt.status != AttemptStatus.UNKNOWN:
        raise AuthorizationError(
            "ATTEMPT_NOT_UNKNOWN",
            "Seule une tentative à effet incertain se réconcilie.",
        )

    if resolved_effect == EffectCertainty.confirmed:
        attempt.status = AttemptStatus.SUCCEEDED
    else:
        attempt.status = AttemptStatus.FAILED
    await db.flush()

    db.add(
        ExecutionResultRecord(
            attempt_id=attempt.id,
            effect=resolved_effect,
            success=resolved_effect == EffectCertainty.confirmed,
            evidence_reference=evidence_reference,
            provider_reference=provider_reference,
            cost_amount=cost_amount,
            cost_unit=cost_unit,
            observed_at=_utcnow(),
        )
    )
    await db.flush()
    await audit.record(
        db,
        event_type=AuditEventType.EFFECT_RECONCILED,
        workspace_id=attempt.workspace_id,
        actor=actor,
        reason_code=resolved_effect.value,
        action_id=attempt.action_id,
        decision_id=decision_id,
        authorization_id=attempt.authorization_id,
        attempt_id=attempt.id,
        payload={"evidence_reference": evidence_reference},
    )
    return attempt