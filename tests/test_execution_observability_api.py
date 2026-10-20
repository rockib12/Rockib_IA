"""Tests pour l'Observabilité et l'API d'Exécution (Budgets, Réservations & Réconciliation)."""
from __future__ import annotations

import uuid
from decimal import Decimal
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_db
from app.core.security import create_access_token
from app.decision_engine.models import (
    ControlOutcome,
    ImpactType,
    PermissionAction,
    ReversibilityLevel,
    RiskLevel,
)
from app.execution.models import (
    ActionRecord,
    ActionReservation,
    AttemptStatus,
    EffectCertainty,
    ExecutionAttempt,
    ReservationStatus,
    ResourceBudget,
)
from app.execution.services import authorizations, fingerprint, reliable_executor
from app.identity.models import Agent, User, UserRole, Workspace, workspace_memberships
from app.main import app
from tests.conftest import make_decision


@pytest_asyncio.fixture
async def setup_tenants(db_session: AsyncSession):
    ws_a = Workspace(name="Observability WS A", slug=f"obs-a-{uuid.uuid4().hex[:8]}")
    ws_b = Workspace(name="Observability WS B", slug=f"obs-b-{uuid.uuid4().hex[:8]}")
    db_session.add_all([ws_a, ws_b])
    await db_session.flush()

    user_a = User(email=f"user-a-{uuid.uuid4().hex[:8]}@obs.io", password_hash="hash", is_active=True)
    db_session.add(user_a)
    await db_session.flush()

    await db_session.execute(
        insert(workspace_memberships).values(
            workspace_id=ws_a.id, user_id=user_a.id, role=UserRole.admin
        )
    )
    await db_session.flush()

    agent_a = Agent(workspace_id=ws_a.id, name="Agent Observability", default_autonomy_level=3)
    db_session.add(agent_a)
    await db_session.flush()

    # Budget EUR dans workspace A
    budget_a = ResourceBudget(
        workspace_id=ws_a.id,
        resource="currency:EUR",
        limit_units=Decimal("500.00"),
    )
    db_session.add(budget_a)
    await db_session.flush()

    return {
        "ws_a": ws_a,
        "ws_b": ws_b,
        "user_a": user_a,
        "agent_a": agent_a,
        "budget_a": budget_a,
    }


@pytest.mark.asyncio
async def test_execution_budgets_endpoint_and_multi_tenant_isolation(db_session: AsyncSession, setup_tenants):
    """Vérifie le calcul en direct des quotas (limit, held, consumed, remaining) et l'isolation 403."""
    data = setup_tenants
    ws_a = data["ws_a"]
    ws_b = data["ws_b"]
    user_a = data["user_a"]

    token_a = create_access_token(data={"sub": str(user_a.id), "email": user_a.email, "role": "admin"})

    # Créer un client HTTP avec override de db_session
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_async_db] = override_get_db

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            headers = {"Authorization": f"Bearer {token_a}"}

            # 1. Accès légitime aux budgets de WS A
            resp = await client.get(f"/api/v1/execution/budgets?workspace_id={ws_a.id}", headers=headers)
            assert resp.status_code == 200
            budgets_data = resp.json()
            assert len(budgets_data) == 1
            assert budgets_data[0]["resource"] == "currency:EUR"
            assert float(budgets_data[0]["limit_units"]) == 500.0
            assert float(budgets_data[0]["remaining_units"]) == 500.0

            # 2. Tentative d'intrusion sur WS B (doit renvoyer 403 Forbidden)
            resp_b = await client.get(f"/api/v1/execution/budgets?workspace_id={ws_b.id}", headers=headers)
            assert resp_b.status_code == 403
    finally:
        app.dependency_overrides.pop(get_async_db, None)


@pytest.mark.asyncio
async def test_execution_reservations_and_reconcile_flow(db_session: AsyncSession, setup_tenants):
    """Vérifie la liste des réservations et la réconciliation formelle d'une tentative UNKNOWN."""
    data = setup_tenants
    ws_a = data["ws_a"]
    user_a = data["user_a"]
    agent_a = data["agent_a"]

    token_a = create_access_token(data={"sub": str(user_a.id), "email": user_a.email, "role": "admin"})

    # 1. Créer une tentative UNKNOWN avec une réservation HELD
    dec = make_decision(workspace_id=ws_a.id, agent_id=agent_a.id, outcome=ControlOutcome.ALLOW, permission_action=PermissionAction.SPEND)
    db_session.add(dec)
    await db_session.flush()

    action = ActionRecord(
        id=uuid.uuid4(),
        workspace_id=ws_a.id,
        agent_id=agent_a.id,
        decision_id=dec.id,
        objective="Action test",
        tool="meta_ads",
        operation="create",
        arguments={"amount": "120", "currency": "EUR"},
        permission_required=PermissionAction.SPEND,
        risk_level=RiskLevel.high,
        risk_reversibility=ReversibilityLevel.irreversible,
        risk_impact=ImpactType.financial,
        cost_estimate=Decimal("120"),
        cost_unit="EUR",
        canonical_fingerprint="fp_obs_1",
        idempotency_key=f"idemp_{uuid.uuid4()}",
    )
    db_session.add(action)
    await db_session.flush()

    auth = await authorizations.issue_authorization(db_session, decision=dec, action=action, actor="test")

    # Créer une tentative UNKNOWN
    attempt = ExecutionAttempt(
        id=uuid.uuid4(),
        action_id=action.id,
        authorization_id=auth.id,
        workspace_id=ws_a.id,
        attempt_number=1,
        idempotency_key=f"att_{uuid.uuid4()}",
        status=AttemptStatus.UNKNOWN,
    )
    db_session.add(attempt)

    # Créer une réservation HELD
    reservation = ActionReservation(
        id=uuid.uuid4(),
        workspace_id=ws_a.id,
        action_id=action.id,
        authorization_id=auth.id,
        resource="currency:EUR",
        units=Decimal("120.00"),
        status=ReservationStatus.HELD,
        idempotency_key=f"res_{uuid.uuid4()}",
    )
    db_session.add(reservation)
    await db_session.commit()

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_async_db] = override_get_db

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            headers = {"Authorization": f"Bearer {token_a}"}

            # 2. Vérifier la lecture des réservations
            resp_res = await client.get(f"/api/v1/execution/reservations?workspace_id={ws_a.id}", headers=headers)
            assert resp_res.status_code == 200
            res_list = resp_res.json()
            assert len(res_list) >= 1
            assert res_list[0]["status"] == "HELD"
            assert float(res_list[0]["units"]) == 120.0

            # 3. Réconciliation formelle via POST /api/v1/execution/reconcile
            reconcile_payload = {
                "attempt_id": str(attempt.id),
                "resolved_effect": "confirmed",
                "evidence_reference": "provider_invoice_ref_9876",
                "settle_reservation": True,
            }
            resp_rec = await client.post("/api/v1/execution/reconcile", json=reconcile_payload, headers=headers)
            assert resp_rec.status_code == 200
            rec_data = resp_rec.json()
            assert rec_data["success"] is True
            assert rec_data["status"] == "SUCCEEDED"
            assert rec_data["evidence_reference"] == "provider_invoice_ref_9876"
    finally:
        app.dependency_overrides.pop(get_async_db, None)
