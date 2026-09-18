"""Fixtures partagées : accès PostgreSQL réel et données de base.

Le contrat (§10) exige que les garanties de persistance soient prouvées sur
PostgreSQL : les mocks seuls ne valident ni les verrous, ni les contraintes, ni le
caractère append-only du journal d'audit.
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.decision_engine.models import (
    ControlOutcome,
    Decision,
    DecisionStatus,
    ImpactType,
    PermissionAction,
    ReversibilityLevel,
    RiskLevel,
)
from app.execution.services import fingerprint
from app.identity.models import Agent, Workspace
from app.execution.models import ActionRecord


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    """Session sur la base PostgreSQL de développement, avec nettoyage en sortie.

    Chaque test travaille dans son propre workspace : la suppression finale du
    workspace suffit à nettoyer par cascade toutes les lignes créées.
    """
    engine = create_async_engine(settings.ASYNC_DATABASE_URL, poolclass=None)
    maker = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with maker() as session:
        try:
            yield session
            await session.rollback()
        finally:
            await session.close()
    await engine.dispose()


@pytest_asyncio.fixture
async def workspace_agent(db_session: AsyncSession) -> tuple[Workspace, Agent]:
    """Crée un workspace et un agent persistés, supprimés à la fin du test."""
    workspace = Workspace(
        name="Test workspace",
        slug=f"test-{uuid.uuid4().hex[:12]}",
    )
    db_session.add(workspace)
    await db_session.flush()

    agent = Agent(
        workspace_id=workspace.id,
        name="Test agent",
        role="tester",
        default_autonomy_level=1,
    )
    db_session.add(agent)
    await db_session.flush()

    yield workspace, agent

    # Le journal d'audit est protégé : l'effacement passe par un chemin explicite.
    await db_session.rollback()
    await db_session.execute(text("SET LOCAL rockib.audit_maintenance = 'on'"))
    await db_session.execute(
        Workspace.__table__.delete().where(Workspace.id == workspace.id)
    )
    await db_session.commit()


def make_decision(
    *,
    workspace_id: uuid.UUID,
    agent_id: uuid.UUID,
    outcome: ControlOutcome = ControlOutcome.ALLOW,
    reason_code: str = "POLICY_ALLOWED",
    permission_action: PermissionAction = PermissionAction.READ,
) -> Decision:
    """Décision persistable, autorisée par défaut, au résultat de contrôle explicite."""
    decision = Decision(
        workspace_id=workspace_id,
        agent_id=agent_id,
        objective="Read the authorized document",
        situation="Integration test on PostgreSQL",
        proposed_action="Read document",
        risk_level=RiskLevel.low,
        risk_reversibility=ReversibilityLevel.reversible,
        risk_impact=ImpactType.internal,
        requested_autonomy_level=2,
        applied_autonomy_level=2,
        permission_required=permission_action,
        permission_granted=outcome == ControlOutcome.ALLOW,
        approval_required=False,
        final_action="Read document",
        status=DecisionStatus.pending_approval,
        control_outcome=outcome,
        control_reason=reason_code,
    )
    return decision


def make_action(
    *,
    workspace_id: uuid.UUID,
    agent_id: uuid.UUID,
    decision_id: uuid.UUID | None = None,
    tool: str = "documents",
    operation: str = "read",
    permission_action: PermissionAction = PermissionAction.READ,
    idempotency_scope: str = "test-operation",
) -> ActionRecord:
    """Action structurée dont l'empreinte canonique est calculée par le service."""
    action = ActionRecord(
        workspace_id=workspace_id,
        agent_id=agent_id,
        decision_id=decision_id,
        objective="Read the authorized document",
        tool=tool,
        operation=operation,
        arguments={"document_id": "doc-1"},
        permission_required=permission_action,
        risk_level=RiskLevel.low,
        risk_reversibility=ReversibilityLevel.reversible,
        risk_impact=ImpactType.internal,
        canonical_fingerprint="",
        idempotency_key="",
        version=1,
    )
    action.canonical_fingerprint = fingerprint.compute_fingerprint(
        workspace_id=workspace_id,
        agent_id=agent_id,
        tool=tool,
        operation=operation,
        permission_required=permission_action,
        objective=action.objective,
        arguments=action.arguments,
    )
    action.idempotency_key = fingerprint.compute_idempotency_key(
        workspace_id=workspace_id,
        tool=tool,
        operation=operation,
        idempotency_scope=idempotency_scope,
    )
    return action