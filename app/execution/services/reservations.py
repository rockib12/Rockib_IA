"""Réservations de quota : vérification atomique et prévention du double débit (INV-08).

Le solde n'est jamais lu puis décrémenté : ce schéma autorise deux workers à
dépasser le quota. Ici, la vérification et l'insertion se font sous un verrou
consultatif PostgreSQL portant sur ``(workspace_id, resource)``, et les unités
engagées sont dérivées des réservations (``HELD`` + ``CONSUMED``), jamais d'un
compteur recopié.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.execution.models import (
    ActionRecord,
    ActionReservation,
    AuditEventType,
    ReservationStatus,
    ResourceBudget,
)
from app.execution.services import audit
from app.execution.services.authorizations import AuthorizationError

DEFAULT_RESERVATION_TTL_SECONDS = 900

# Statuts qui immobilisent du solde : une réservation consommée est une dépense,
# une réservation tenue est un engagement en cours.
COMMITTED_STATUSES = (ReservationStatus.HELD, ReservationStatus.CONSUMED)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def evaluate_quota(
    *,
    limit_units: Optional[Decimal],
    committed_units: Decimal,
    requested_units: Decimal,
) -> Optional[str]:
    """Retourne le code de refus, ou ``None`` si la réservation tient dans la borne.

    Fonction pure : le calcul de solde se teste sans base de données.
    """
    if requested_units <= 0:
        return "QUOTA_INVALID_UNITS"
    if limit_units is None:
        # Une ressource sans budget déclaré n'est pas illimitée : une absence de
        # preuve n'est pas une autorisation.
        return "QUOTA_UNKNOWN"
    if committed_units + requested_units > limit_units:
        return "QUOTA_EXCEEDED"
    return None


async def committed_units(
    db: AsyncSession, *, workspace_id: uuid.UUID, resource: str
) -> Decimal:
    """Total des unités déjà engagées pour ce couple (workspace, ressource)."""
    result = await db.execute(
        select(func.coalesce(func.sum(ActionReservation.units), 0)).where(
            ActionReservation.workspace_id == workspace_id,
            ActionReservation.resource == resource,
            ActionReservation.status.in_(
                [status.value for status in COMMITTED_STATUSES]
            ),
        )
    )
    return Decimal(result.scalar_one() or 0)


async def _lock_quota(
    db: AsyncSession, *, workspace_id: uuid.UUID, resource: str
) -> None:
    """Sérialise les réservations concurrentes d'un même quota.

    Le verrou est transactionnel : il se libère au ``commit``/``rollback``, donc
    aucune fuite de verrou en cas d'erreur. Sur un moteur non-PostgreSQL, le verrou
    est ignoré : la garantie forte est PostgreSQL.
    """
    bind = db.get_bind()
    if bind is None or bind.dialect.name != "postgresql":
        return
    key = f"{workspace_id}:{resource}"
    await db.execute(select(func.pg_advisory_xact_lock(func.hashtext(key))))


async def reserve_quota(
    db: AsyncSession,
    *,
    action: ActionRecord,
    authorization_id: uuid.UUID,
    resource: str,
    units: Decimal,
    idempotency_key: str,
    actor: str,
    ttl_seconds: int = DEFAULT_RESERVATION_TTL_SECONDS,
) -> ActionReservation:
    """Réserve ``units`` sur un quota, ou refuse avec un motif stable.

    Rejouer la même opération logique (même ``idempotency_key``) ne consomme pas de
    solde supplémentaire : la réservation existante est retournée telle quelle.
    """
    existing = await db.execute(
        select(ActionReservation).where(
            ActionReservation.workspace_id == action.workspace_id,
            ActionReservation.resource == resource,
            ActionReservation.idempotency_key == idempotency_key,
        )
    )
    reservation = existing.scalar_one_or_none()
    if reservation is not None:
        return reservation

    await _lock_quota(db, workspace_id=action.workspace_id, resource=resource)

    budget_result = await db.execute(
        select(ResourceBudget)
        .where(
            ResourceBudget.workspace_id == action.workspace_id,
            ResourceBudget.resource == resource,
        )
        .with_for_update()
    )
    budget = budget_result.scalar_one_or_none()
    held = await committed_units(
        db, workspace_id=action.workspace_id, resource=resource
    )

    refusal = evaluate_quota(
        limit_units=Decimal(budget.limit_units) if budget is not None else None,
        committed_units=held,
        requested_units=Decimal(units),
    )
    if refusal is not None:
        await audit.record(
            db,
            event_type=AuditEventType.RESERVATION_RELEASED,
            workspace_id=action.workspace_id,
            actor=actor,
            reason_code=refusal,
            agent_id=action.agent_id,
            action_id=action.id,
            authorization_id=authorization_id,
            action_fingerprint=action.canonical_fingerprint,
            payload={
                "resource": resource,
                "requested_units": str(units),
                "committed_units": str(held),
                "limit_units": str(budget.limit_units) if budget is not None else None,
            },
        )
        raise AuthorizationError(refusal, "Réservation de quota refusée.")

    now = _utcnow()
    reservation = ActionReservation(
        workspace_id=action.workspace_id,
        action_id=action.id,
        authorization_id=authorization_id,
        resource=resource,
        units=Decimal(units),
        status=ReservationStatus.HELD,
        idempotency_key=idempotency_key,
        expires_at=now + timedelta(seconds=ttl_seconds),
    )
    db.add(reservation)
    await db.flush()
    await audit.record(
        db,
        event_type=AuditEventType.RESERVATION_HELD,
        workspace_id=action.workspace_id,
        actor=actor,
        reason_code="QUOTA_HELD",
        agent_id=action.agent_id,
        action_id=action.id,
        authorization_id=authorization_id,
        action_fingerprint=action.canonical_fingerprint,
        payload={
            "resource": resource,
            "units": str(units),
            "committed_before": str(held),
        },
    )
    return reservation


async def release_reservation(
    db: AsyncSession,
    *,
    reservation_id: uuid.UUID,
    reason: str,
    actor: str,
) -> ActionReservation:
    """Libère un engagement non dépensé : le solde redevient disponible."""
    reservation = await db.get(ActionReservation, reservation_id)
    if reservation is None:
        raise AuthorizationError("RESERVATION_NOT_FOUND", "Réservation inconnue.")
    if reservation.status == ReservationStatus.CONSUMED:
        raise AuthorizationError(
            "RESERVATION_ALREADY_CONSUMED",
            "Une réservation consommée ne se libère pas : elle correspond à une dépense.",
        )
    if reservation.status != ReservationStatus.RELEASED:
        reservation.status = ReservationStatus.RELEASED
        reservation.released_at = _utcnow()
        reservation.release_reason = reason
        await db.flush()
        await audit.record(
            db,
            event_type=AuditEventType.RESERVATION_RELEASED,
            workspace_id=reservation.workspace_id,
            actor=actor,
            reason_code=reason,
            action_id=reservation.action_id,
            authorization_id=reservation.authorization_id,
            payload={
                "resource": reservation.resource,
                "units": str(reservation.units),
            },
        )
    return reservation


async def consume_reservation(
    db: AsyncSession,
    *,
    reservation_id: uuid.UUID,
    actor: str,
) -> ActionReservation:
    """Transforme un engagement en dépense constatée (après effet confirmé)."""
    reservation = await db.get(ActionReservation, reservation_id)
    if reservation is None:
        raise AuthorizationError("RESERVATION_NOT_FOUND", "Réservation inconnue.")
    if reservation.status == ReservationStatus.RELEASED:
        raise AuthorizationError(
            "RESERVATION_ALREADY_RELEASED",
            "Une réservation libérée ne peut plus être consommée.",
        )
    if reservation.status != ReservationStatus.CONSUMED:
        reservation.status = ReservationStatus.CONSUMED
        reservation.consumed_at = _utcnow()
        await db.flush()
        await audit.record(
            db,
            event_type=AuditEventType.RESERVATION_CONSUMED,
            workspace_id=reservation.workspace_id,
            actor=actor,
            reason_code="QUOTA_CONSUMED",
            action_id=reservation.action_id,
            authorization_id=reservation.authorization_id,
            payload={
                "resource": reservation.resource,
                "units": str(reservation.units),
            },
        )
    return reservation