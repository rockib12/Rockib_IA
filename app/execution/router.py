"""Routeur FastAPI pour l'Exécution, les Budgets et la Télémétrie Financière."""
from __future__ import annotations

import uuid
from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel, Field

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_db
from app.core.dependencies import get_current_user, assert_workspace_member
from app.identity.models import User
from app.execution.models import (
    ActionReservation,
    EffectCertainty,
    ReservationStatus,
    ResourceBudget,
)
from app.execution.services import reliable_executor
from app.execution.services.authorizations import AuthorizationError

execution_router = APIRouter(prefix="/execution", tags=["execution"])


class BudgetSummary(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    resource: str
    limit_units: Decimal
    held_units: Decimal
    consumed_units: Decimal
    remaining_units: Decimal
    period: str


class ReservationItem(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    action_id: uuid.UUID
    resource: str
    units: Decimal
    status: str
    idempotency_key: str
    created_at: str


class ReconcileRequest(BaseModel):
    attempt_id: uuid.UUID
    resolved_effect: str = Field(..., pattern="^(confirmed|none)$")
    evidence_reference: str = Field(..., min_length=3)
    settle_reservation: bool = True


@execution_router.get("/budgets", response_model=List[BudgetSummary])
async def list_workspace_budgets(
    workspace_id: uuid.UUID = Query(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Retourne la liste des budgets de quota avec unités tenues (HELD) et consommées (CONSUMED)."""
    await assert_workspace_member(db, current_user, workspace_id)

    budgets_stmt = select(ResourceBudget).where(ResourceBudget.workspace_id == workspace_id)
    budgets = (await db.execute(budgets_stmt)).scalars().all()

    summaries = []
    for b in budgets:
        # Calculer held_units
        held_stmt = select(func.coalesce(func.sum(ActionReservation.units), 0)).where(
            ActionReservation.workspace_id == workspace_id,
            ActionReservation.resource == b.resource,
            ActionReservation.status == ReservationStatus.HELD,
        )
        held_val = Decimal((await db.execute(held_stmt)).scalar_one() or 0)

        # Calculer consumed_units
        consumed_stmt = select(func.coalesce(func.sum(ActionReservation.units), 0)).where(
            ActionReservation.workspace_id == workspace_id,
            ActionReservation.resource == b.resource,
            ActionReservation.status == ReservationStatus.CONSUMED,
        )
        consumed_val = Decimal((await db.execute(consumed_stmt)).scalar_one() or 0)

        remaining_val = max(Decimal("0.0"), b.limit_units - held_val - consumed_val)

        summaries.append(
            BudgetSummary(
                id=b.id,
                workspace_id=b.workspace_id,
                resource=b.resource,
                limit_units=b.limit_units,
                held_units=held_val,
                consumed_units=consumed_val,
                remaining_units=remaining_val,
                period=b.period,
            )
        )

    return summaries


@execution_router.get("/reservations", response_model=List[ReservationItem])
async def list_recent_reservations(
    workspace_id: uuid.UUID = Query(...),
    limit: int = Query(25, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Retourne les réservations d'action récentes (HELD, CONSUMED, RELEASED)."""
    await assert_workspace_member(db, current_user, workspace_id)

    stmt = (
        select(ActionReservation)
        .where(ActionReservation.workspace_id == workspace_id)
        .order_by(ActionReservation.created_at.desc())
        .limit(limit)
    )
    reservations = (await db.execute(stmt)).scalars().all()

    return [
        ReservationItem(
            id=r.id,
            workspace_id=r.workspace_id,
            action_id=r.action_id,
            resource=r.resource,
            units=r.units,
            status=r.status.value if hasattr(r.status, "value") else str(r.status),
            idempotency_key=r.idempotency_key,
            created_at=r.created_at.isoformat() if r.created_at else "",
        )
        for r in reservations
    ]


@execution_router.post("/reconcile")
async def reconcile_attempt(
    req: ReconcileRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Réconcilie une tentative d'exécution en statut UNKNOWN à partir d'une preuve formelle."""
    effect_enum = EffectCertainty.confirmed if req.resolved_effect == "confirmed" else EffectCertainty.none
    actor = f"operator:{current_user.email or current_user.id}"

    try:
        reconciled = await reliable_executor.reconcile_unknown_attempt(
            db,
            attempt_id=req.attempt_id,
            resolved_effect=effect_enum,
            actor=actor,
            evidence_reference=req.evidence_reference,
            settle_reservation=req.settle_reservation,
        )
        await db.commit()
        return {
            "success": True,
            "attempt_id": str(reconciled.id),
            "status": reconciled.status.value if hasattr(reconciled.status, "value") else str(reconciled.status),
            "evidence_reference": req.evidence_reference,
            "message": "Réconciliation enregistrée avec succès.",
        }
    except AuthorizationError as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": e.code, "message": e.message},
        )
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur interne lors de la réconciliation: {str(e)}",
        )


class SandboxRunRequest(BaseModel):
    workspace_id: uuid.UUID
    code: str = Field(..., min_length=1, max_length=64000, description="Code source à compiler et exécuter")
    test_code: str = Field(default="", max_length=64000, description="Suite d'assertions ou tests unitaires")
    language: str = Field(default="python")
    timeout_seconds: float = Field(default=5.0, ge=0.5, le=15.0)


@execution_router.post("/sandbox/run")
async def run_agent_code_in_sandbox(
    req: SandboxRunRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """P3 — Compile, vérifie (SAST/AST) et exécute du code + tests unitaires dans une sandbox isolée."""
    await assert_workspace_member(db, current_user, req.workspace_id)

    from app.connectors.sandbox_connector import execute_in_sandbox

    report = await execute_in_sandbox(
        code=req.code,
        test_code=req.test_code,
        language=req.language,
        timeout_seconds=req.timeout_seconds,
        workspace_id=str(req.workspace_id),
    )

    return {
        "run_id": report.run_id,
        "language": report.language,
        "compile_ok": report.compile_ok,
        "execution_ok": report.execution_ok,
        "tests_passed": report.tests_passed,
        "exit_code": report.exit_code,
        "stdout": report.stdout,
        "stderr": report.stderr,
        "duration_ms": report.duration_ms,
        "security_violations": report.security_violations,
    }

