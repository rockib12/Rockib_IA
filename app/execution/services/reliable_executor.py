"""Enchaînement fiable d'une action autorisée (Phase 2, §8 du contrat).

Ordre imposé :

1. revérifier l'autorisation et ses conditions mutables sous verrou ;
2. réserver le quota (avant l'effet) ;
3. consommer l'autorisation ;
4. prendre en charge la tentative de façon exclusive ;
5. appeler l'outil ;
6. persister le résultat, le coût et les transitions, puis libérer ou consommer la
   réservation.

Un échec avant l'appel ne produit aucun effet. Une incertitude pendant l'appel
produit ``UNKNOWN`` : l'effet n'est jamais rejoué à l'aveugle (INV-09).
"""
from __future__ import annotations

import asyncio
import inspect
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Awaitable, Callable, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.execution.models import (
    ActionRecord,
    ActionReservation,
    AttemptStatus,
    EffectCertainty,
    ExecutionAttempt,
    ReservationStatus,
)
from app.execution.services import attempts as attempts_service
from app.execution.services import audit, authorizations, reservations
from app.execution.services.authorizations import AuthorizationError
from app.execution.services.executor import ExecutionResult

ActionHandler = Callable[[ActionRecord], Awaitable[ExecutionResult]]

# Registre outil/opération -> handler. Un couple absent n'exécute rien.
_ACTION_HANDLERS: dict[tuple[str, str], ActionHandler] = {}


def register_action_handler(
    tool: str,
    operation: str,
    handler: ActionHandler,
    *,
    replace: bool = False,
) -> None:
    """Enregistre de manière déterministe un handler pour un couple (tool, operation)."""
    if not isinstance(tool, str):
        raise TypeError(f"tool must be a str, got {type(tool).__name__}")
    if not tool.strip():
        raise ValueError("tool must be a non-empty string")

    if not isinstance(operation, str):
        raise TypeError(f"operation must be a str, got {type(operation).__name__}")
    if not operation.strip():
        raise ValueError("operation must be a non-empty string")

    if not callable(handler):
        raise TypeError(f"handler must be callable, got {type(handler).__name__}")

    is_async = inspect.iscoroutinefunction(handler) or (
        callable(handler) and inspect.iscoroutinefunction(getattr(handler, "__call__", None))
    )
    if not is_async:
        raise TypeError("handler must be an async coroutine function")

    key = (tool, operation)
    existing = _ACTION_HANDLERS.get(key)
    if existing is not None:
        if existing is handler:
            return
        if not replace:
            raise ValueError(f"Handler already registered for {tool}.{operation}")

    _ACTION_HANDLERS[key] = handler


def get_action_handler(tool: str, operation: str) -> Optional[ActionHandler]:
    return _ACTION_HANDLERS.get((tool, operation))


def clear_action_handlers() -> None:
    """Réinitialise complètement le registre des handlers (usage tests/isolation)."""
    _ACTION_HANDLERS.clear()


@dataclass
class ExecutionOutcome:
    """Résultat persistant d'une exécution fiable."""

    action_id: uuid.UUID
    authorization_id: uuid.UUID
    attempt_id: uuid.UUID
    attempt_status: AttemptStatus
    effect: EffectCertainty
    output: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    provider_reference: Optional[str] = None
    reservation_id: Optional[uuid.UUID] = None

    @property
    def success(self) -> bool:
        return self.effect == EffectCertainty.confirmed


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _classify(result: ExecutionResult) -> EffectCertainty:
    if result.effect_unknown:
        return EffectCertainty.unknown
    return EffectCertainty.confirmed if result.success else EffectCertainty.none


async def dispatch_authorized_action(
    db: AsyncSession,
    *,
    action: ActionRecord,
    authorization_id: uuid.UUID,
    actor: str,
    lease_owner: str,
    caller_workspace_id: Optional[uuid.UUID] = None,
    resource: Optional[str] = None,
    units: Optional[Decimal] = None,
    timeout_seconds: Optional[float] = None,
    lease_seconds: int = attempts_service.DEFAULT_LEASE_SECONDS,
    handler: Optional[ActionHandler] = None,
) -> ExecutionOutcome:
    """Exécute une action strictement à partir d'une autorisation serveur valide.

    ``caller_workspace_id`` isole le workspace (INV-02) : un appelant d'un autre
    workspace est refusé avant tout accès à l'outil.
    """
    if caller_workspace_id is not None and caller_workspace_id != action.workspace_id:
        raise AuthorizationError(
            "WORKSPACE_MISMATCH",
            "Action hors du workspace de l'appelant.",
        )

    # 1. Revérification des conditions mutables sous verrou (révocation, expiration,
    #    empreinte, version) : dernier contrôle avant l'effet.
    authorization = await authorizations.lock_authorization(db, authorization_id)
    refusal = authorizations.evaluate_validity(authorization, action)
    if refusal is not None:
        raise AuthorizationError(refusal, "Autorisation non valide au moment de l'effet.")

    resolved_handler = handler or get_action_handler(action.tool, action.operation)
    if resolved_handler is None:
        raise AuthorizationError(
            "NO_HANDLER_REGISTERED",
            f"Aucun handler pour {action.tool}.{action.operation}.",
        )

    # 2. Réservation avant l'effet : un quota insuffisant n'engage rien.
    reservation = None
    if resource is not None:
        reservation = await reservations.reserve_quota(
            db,
            action=action,
            authorization_id=authorization.id,
            resource=resource,
            units=Decimal(units if units is not None else 0),
            idempotency_key=action.idempotency_key,
            actor=actor,
        )

    # 3. Consommation : l'autorisation ne peut pas servir deux fois.
    await authorizations.consume_authorization(
        db, authorization_id=authorization.id, action=action, actor=actor
    )

    # 4. Prise en charge exclusive de la tentative.
    attempt = await attempts_service.claim_attempt(
        db,
        action=action,
        authorization_id=authorization.id,
        idempotency_key=action.idempotency_key,
        actor=actor,
        lease_owner=lease_owner,
        lease_seconds=lease_seconds,
    )

    # 5. Appel de l'outil : toute incertitude devient un état explicite.
    try:
        if timeout_seconds is not None:
            result = await asyncio.wait_for(
                resolved_handler(action), timeout=timeout_seconds
            )
        else:
            result = await resolved_handler(action)
    except asyncio.TimeoutError:
        result = ExecutionResult(
            success=False,
            output=None,
            error="Timeout ambigu : l'effet peut avoir eu lieu.",
            error_code="TIMEOUT_AMBIGUOUS",
            effect_unknown=True,
        )
    except Exception as exc:  # noqa: BLE001 — l'incertitude doit être persistée
        result = ExecutionResult(
            success=False,
            output=None,
            error=f"{type(exc).__name__}: {exc}",
            error_code="HANDLER_EXCEPTION",
            effect_unknown=True,
        )

    effect = _classify(result)

    # 6. Persistance du résultat et des transitions.
    await attempts_service.record_result(
        db,
        attempt=attempt,
        effect=effect,
        actor=actor,
        success=result.success if effect != EffectCertainty.unknown else None,
        output_summary=result.output,
        error_code=result.error_code,
        error_message=result.error,
        provider_reference=result.provider_reference,
        cost_amount=result.cost_amount,
        cost_unit=result.cost_unit,
        action_fingerprint=action.canonical_fingerprint,
        decision_id=action.decision_id,
    )

    if reservation is not None:
        if effect == EffectCertainty.confirmed:
            await reservations.consume_reservation(
                db, reservation_id=reservation.id, actor=actor
            )
        elif effect == EffectCertainty.none:
            await reservations.release_reservation(
                db,
                reservation_id=reservation.id,
                reason="EFFECT_NOT_PRODUCED",
                actor=actor,
            )
        # Effet incertain : la réservation reste tenue jusqu'à réconciliation, car
        # l'effet peut avoir eu lieu et le solde ne doit pas être réutilisé à tort.

    return ExecutionOutcome(
        action_id=action.id,
        authorization_id=authorization.id,
        attempt_id=attempt.id,
        attempt_status=attempt.status,
        effect=effect,
        output=result.output,
        error_code=result.error_code,
        error_message=result.error,
        provider_reference=result.provider_reference,
        reservation_id=reservation.id if reservation is not None else None,
    )


async def reconcile_unknown_attempt(
    db: AsyncSession,
    *,
    attempt_id: uuid.UUID,
    resolved_effect: EffectCertainty,
    actor: str,
    evidence_reference: str,
    settle_reservation: bool = True,
) -> ExecutionAttempt:
    """Réconcilie une tentative ``UNKNOWN`` et solde la réservation associée.

    Si l'effet est confirmé, l'engagement devient une dépense ; s'il est écarté, il
    est libéré. Rien n'est décidé sans preuve.
    """
    attempt = await attempts_service.reconcile_attempt(
        db,
        attempt_id=attempt_id,
        resolved_effect=resolved_effect,
        actor=actor,
        evidence_reference=evidence_reference,
    )

    if settle_reservation:
        held = await db.execute(
            select(ActionReservation).where(
                ActionReservation.action_id == attempt.action_id,
                ActionReservation.status == ReservationStatus.HELD,
            )
        )
        for reservation in held.scalars().all():
            if resolved_effect == EffectCertainty.confirmed:
                await reservations.consume_reservation(
                    db, reservation_id=reservation.id, actor=actor
                )
            else:
                await reservations.release_reservation(
                    db,
                    reservation_id=reservation.id,
                    reason="RECONCILED_NO_EFFECT",
                    actor=actor,
                )
    return attempt