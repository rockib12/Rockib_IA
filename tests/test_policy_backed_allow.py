"""ALLOW de bout en bout sans mock : politique réelle en base (Phase 1 → Phase 2).

Différence avec ``test_execution_reliable.py`` : la décision n'est plus construite
à la main mais produite par l'arbitrate réel, qui charge lui-même sa politique
``DecisionDomainConfig`` depuis PostgreSQL. Le chaînon complet est vérifié :

    politique en base -> arbitrage -> ALLOW/POLICY_ALLOWED
    -> autorisation émise -> exécution fiable -> effet confirmé -> audit corrélé

Le contrat (§10) interdit de valider ce chaînage avec des mocks : la politique
chargée en base est la seule source d'autorisation du test.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.decision_engine.models import (
    ArbitrationRule,
    ControlOutcome,
    DecisionDomainConfig,
    ImpactType,
    PermissionAction,
    ReversibilityLevel,
    RiskLevel,
)
from app.decision_engine.services.arbitrator import DeterministicArbitrator
from app.execution.models import AuditEntry, EffectCertainty, ExecutionAttempt
from app.execution.services import attempts as attempts_service
from app.execution.services import authorizations
from app.execution.services.authorizations import AuthorizationError
from app.execution.services.executor import ExecutionResult
from app.execution.services.reliable_executor import dispatch_authorized_action

from tests.conftest import make_action

pytestmark = pytest.mark.asyncio

ACTOR = "policy-backed-test"

# Champs NUMERIC de Decision remplis en float par l'arbitrate ; asyncpg exige des
# Decimal. Coercition nécessaire jusqu'à correction de l'écart §11
# (« Mélange Decimal/float ») côté arbitre.
_NUMERIC_DECISION_FIELDS = (
    "cognitive_confidence",
    "intelligence_confidence",
    "disagreement",
    "final_confidence",
)


def _coerce_numeric_fields(record) -> None:
    for field in _NUMERIC_DECISION_FIELDS:
        value = getattr(record, field, None)
        if isinstance(value, float):
            setattr(record, field, Decimal(str(value)))


async def test_policy_backed_allow_end_to_end(db_session, workspace_agent):
    """Politique réelle en base -> ALLOW non mocké -> exécution fiable -> audit."""
    workspace, agent = workspace_agent

    # 1. Politique réelle : opt-in explicite d'exécution, plafond d'autonomie 5.
    policy = DecisionDomainConfig(
        workspace_id=workspace.id,
        domain="documents",
        permission_action=PermissionAction.READ,
        execution_enabled=True,
        max_autonomy_level=5,
        arbitration_rule=ArbitrationRule.consensus_required,
        base_risk_level=RiskLevel.low,
        base_reversibility=ReversibilityLevel.reversible,
        base_impact=ImpactType.internal,
        disagreement_threshold=Decimal("0.40"),
    )
    db_session.add(policy)
    await db_session.flush()

    # 2. Arbitrage réel : l'arbitrate charge sa politique depuis la base.
    #    Aucun mock : si la requête échoue, le test échoue (POLICY_MISSING).
    arbitrator = DeterministicArbitrator(db=db_session)
    decision = await arbitrator.arbitrate(
        objective="Read the authorized document",
        situation="Integration test on real policy",
        proposed_action="Read document",
        cognitive_opinion={"action": "Read document", "confidence": 0.9},
        intelligence_opinion={"action": "Read document", "confidence": 0.9},
        domain="documents",
        permission_action=PermissionAction.READ,
        requested_autonomy_level=2,
        workspace_id=str(workspace.id),
        agent_id=str(agent.id),
    )

    # 3. Le contrôle serveur a explicitement autorisé (motif stable, non mocké).
    assert decision.control_outcome is ControlOutcome.ALLOW
    assert decision.control_reason == "POLICY_ALLOWED"
    assert decision.permission_granted is True
    assert decision.action_fingerprint  # empreinte posée par set_control
    # Autonomie appliquée = min(plafond politique, demandé), jamais au-delà.
    assert decision.applied_autonomy_level == 2
    assert decision.applied_autonomy_level <= policy.max_autonomy_level

    # 4. Coercition float -> Decimal (asyncpg refuse un float pour NUMERIC).
    _coerce_numeric_fields(decision)
    db_session.add(decision)
    await db_session.flush()

    # 5. Action structurée alignée sur la décision arbitrée.
    action = make_action(
        workspace_id=workspace.id,
        agent_id=agent.id,
        decision_id=decision.id,
        permission_action=PermissionAction.READ,
        idempotency_scope=f"policy-{uuid.uuid4().hex}",
    )
    db_session.add(action)
    await db_session.flush()

    # 6. Autorisation émise côté serveur, tracée vers la version de politique.
    authorization = await authorizations.issue_authorization(
        db_session,
        decision=decision,
        action=action,
        actor=ACTOR,
        policy_version=f"decision_domain_config:{policy.id}",
    )
    assert authorization.outcome is ControlOutcome.ALLOW
    assert authorization.reason_code == "POLICY_ALLOWED"
    assert authorization.policy_version == f"decision_domain_config:{policy.id}"
    assert authorization.consumed_at is None

    # 7. Exécution fiable : la tentative ne dépend d'aucun mock.
    async def handler(action_record):
        return ExecutionResult(
            success=True,
            output="document read",
            error=None,
            provider_reference="ext-read-1",
            cost_amount=Decimal("0.25"),
            cost_unit="credits",
        )

    outcome = await dispatch_authorized_action(
        db_session,
        action=action,
        authorization_id=authorization.id,
        actor=ACTOR,
        lease_owner="worker-policy-1",
        handler=handler,
    )

    assert outcome.effect is EffectCertainty.confirmed
    assert outcome.success is True

    attempt = await db_session.get(ExecutionAttempt, outcome.attempt_id)
    assert attempt.status is attempts_service.AttemptStatus.SUCCEEDED

    await db_session.refresh(authorization)
    assert authorization.consumed_at is not None

    # 8. Audit durable et corrélé : le motif du contrôle reste lisible en base.
    events = (
        await db_session.execute(
            select(AuditEntry).where(AuditEntry.decision_id == decision.id)
        )
    ).scalars().all()
    event_types = {event.event_type for event in events}
    assert attempts_service.AuditEventType.AUTHORIZATION_ISSUED in event_types
    assert attempts_service.AuditEventType.EFFECT_CONFIRMED in event_types


async def test_missing_policy_never_allows_and_cannot_execute(db_session, workspace_agent):
    """Sans politique en base, l'arbitrate STOP : aucun effet possible."""
    workspace, agent = workspace_agent

    arbitrator = DeterministicArbitrator(db=db_session)
    decision = await arbitrator.arbitrate(
        objective="Read the authorized document",
        situation="No policy registered for this domain",
        proposed_action="Read document",
        cognitive_opinion={"action": "Read document", "confidence": 0.9},
        intelligence_opinion={"action": "Read document", "confidence": 0.9},
        domain="documents",
        permission_action=PermissionAction.READ,
        requested_autonomy_level=2,
        workspace_id=str(workspace.id),
        agent_id=str(agent.id),
    )

    assert decision.control_outcome is ControlOutcome.STOP
    assert decision.control_reason == "POLICY_MISSING"
    assert decision.permission_granted is False

    # Persistée, une décision STOP ne produit jamais d'autorisation (INV-01).
    _coerce_numeric_fields(decision)
    db_session.add(decision)
    await db_session.flush()

    action = make_action(
        workspace_id=workspace.id,
        agent_id=agent.id,
        decision_id=decision.id,
        permission_action=PermissionAction.READ,
        idempotency_scope=f"policy-missing-{uuid.uuid4().hex}",
    )
    db_session.add(action)
    await db_session.flush()

    with pytest.raises(AuthorizationError):
        await authorizations.issue_authorization(
            db_session, decision=decision, action=action, actor=ACTOR
        )

