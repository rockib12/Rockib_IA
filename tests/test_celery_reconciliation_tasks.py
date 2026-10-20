"""Tests unitaires et d'intégration pour les tâches Celery de Réconciliation Automatique."""
from __future__ import annotations

import uuid
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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
    ExecutionResultRecord,
    ReservationStatus,
    ResourceBudget,
)
from app.execution.services import authorizations
from app.execution.tasks import (
    reconcile_pending_attempts,
    reconcile_attempt_task,
    _reconcile_single_attempt_async,
)
from app.identity.models import Agent, Workspace
from tests.conftest import make_decision


def test_reconcile_pending_attempts_dispatches_delay():
    """Vérifie que la tâche Celery Beat planifie un message reconcile_attempt_task par tentative UNKNOWN."""
    att_1 = str(uuid.uuid4())
    att_2 = str(uuid.uuid4())

    with patch("app.execution.tasks._find_unknown_attempts_async", return_value=[att_1, att_2]):
        with patch("app.execution.tasks.reconcile_attempt_task.delay") as mock_delay:
            res = reconcile_pending_attempts()
            assert "2 unknown attempt(s)" in res
            assert mock_delay.call_count == 2
            mock_delay.assert_any_call(att_1)
            mock_delay.assert_any_call(att_2)


@pytest.mark.asyncio
async def test_reconcile_attempt_task_fs_inspector_confirmed(db_session: AsyncSession, tmp_path: Path):
    """Vérifie que l'inspecteur fs détecte la présence du fichier, confirme l'effet et consomme la réservation."""
    ws = Workspace(name="Test Reconcile WS", slug=f"rec-ws-{uuid.uuid4().hex[:8]}")
    db_session.add(ws)
    await db_session.flush()

    ag = Agent(workspace_id=ws.id, name="Test Agent", default_autonomy_level=3)
    db_session.add(ag)
    await db_session.flush()

    # Créer le fichier sur le disque
    target_file = tmp_path / "test_artifact.txt"
    target_file.write_text("Données critiques persistées")

    dec = make_decision(workspace_id=ws.id, agent_id=ag.id, outcome=ControlOutcome.ALLOW, permission_action=PermissionAction.CREATE)
    db_session.add(dec)
    await db_session.flush()

    action = ActionRecord(
        id=uuid.uuid4(),
        workspace_id=ws.id,
        agent_id=ag.id,
        decision_id=dec.id,
        objective="Écriture fichier",
        tool="fs",
        operation="write",
        arguments={"path": str(target_file)},
        permission_required=PermissionAction.CREATE,
        risk_level=RiskLevel.low,
        risk_reversibility=ReversibilityLevel.reversible,
        risk_impact=ImpactType.internal,
        canonical_fingerprint="fp_fs_1",
        idempotency_key=f"idemp_{uuid.uuid4()}",
    )
    db_session.add(action)
    await db_session.flush()

    auth = await authorizations.issue_authorization(db_session, decision=dec, action=action, actor="test")

    attempt = ExecutionAttempt(
        id=uuid.uuid4(),
        action_id=action.id,
        authorization_id=auth.id,
        workspace_id=ws.id,
        attempt_number=1,
        idempotency_key=f"att_{uuid.uuid4()}",
        status=AttemptStatus.UNKNOWN,
    )
    db_session.add(attempt)

    reservation = ActionReservation(
        id=uuid.uuid4(),
        workspace_id=ws.id,
        action_id=action.id,
        authorization_id=auth.id,
        resource="disk_quota:bytes",
        units=Decimal("100"),
        status=ReservationStatus.HELD,
        idempotency_key=f"res_{uuid.uuid4()}",
    )
    db_session.add(reservation)
    await db_session.commit()

    # Exécution de l'inspection automatique
    res = await _reconcile_single_attempt_async(str(attempt.id), db=db_session)
    assert res["status"] == "RECONCILED"
    assert res["effect"] == EffectCertainty.confirmed.value
    assert "fs_stat" in res["evidence"]

    # Vérification en base
    assert reservation.status == ReservationStatus.CONSUMED


@pytest.mark.asyncio
async def test_reconcile_attempt_task_fs_inspector_none_releases_reservation(db_session: AsyncSession, tmp_path: Path):
    """Vérifie que l'absence de fichier conclut à l'absence d'effet et libère la réservation HELD."""
    ws = Workspace(name="Test Reconcile WS 2", slug=f"rec-ws-{uuid.uuid4().hex[:8]}")
    db_session.add(ws)
    await db_session.flush()

    ag = Agent(workspace_id=ws.id, name="Test Agent", default_autonomy_level=3)
    db_session.add(ag)
    await db_session.flush()

    # Fichier inexistant
    missing_file = tmp_path / "never_created.txt"

    dec = make_decision(workspace_id=ws.id, agent_id=ag.id, outcome=ControlOutcome.ALLOW, permission_action=PermissionAction.CREATE)
    db_session.add(dec)
    await db_session.flush()

    action = ActionRecord(
        id=uuid.uuid4(),
        workspace_id=ws.id,
        agent_id=ag.id,
        decision_id=dec.id,
        objective="Écriture fichier manqué",
        tool="fs",
        operation="write",
        arguments={"path": str(missing_file)},
        permission_required=PermissionAction.CREATE,
        risk_level=RiskLevel.low,
        risk_reversibility=ReversibilityLevel.reversible,
        risk_impact=ImpactType.internal,
        canonical_fingerprint="fp_fs_2",
        idempotency_key=f"idemp_{uuid.uuid4()}",
    )
    db_session.add(action)
    await db_session.flush()

    auth = await authorizations.issue_authorization(db_session, decision=dec, action=action, actor="test")

    attempt = ExecutionAttempt(
        id=uuid.uuid4(),
        action_id=action.id,
        authorization_id=auth.id,
        workspace_id=ws.id,
        attempt_number=1,
        idempotency_key=f"att_{uuid.uuid4()}",
        status=AttemptStatus.UNKNOWN,
    )
    db_session.add(attempt)

    reservation = ActionReservation(
        id=uuid.uuid4(),
        workspace_id=ws.id,
        action_id=action.id,
        authorization_id=auth.id,
        resource="disk_quota:bytes",
        units=Decimal("100"),
        status=ReservationStatus.HELD,
        idempotency_key=f"res_{uuid.uuid4()}",
    )
    db_session.add(reservation)
    await db_session.commit()

    # Exécution de l'inspection
    res = await _reconcile_single_attempt_async(str(attempt.id), db=db_session)
    assert res["status"] == "RECONCILED"
    assert res["effect"] == EffectCertainty.none.value
    assert "fs_missing" in res["evidence"]

    # La réservation doit être libérée (RELEASED)
    assert reservation.status == ReservationStatus.RELEASED


@pytest.mark.asyncio
async def test_reconcile_attempt_inconclusive_remains_held(db_session: AsyncSession):
    """Vérifie que sans preuve concluante, la tentative reste UNKNOWN et la réservation HELD (fail-closed)."""
    ws = Workspace(name="Test Reconcile WS 3", slug=f"rec-ws-{uuid.uuid4().hex[:8]}")
    db_session.add(ws)
    await db_session.flush()

    ag = Agent(workspace_id=ws.id, name="Test Agent", default_autonomy_level=3)
    db_session.add(ag)
    await db_session.flush()

    dec = make_decision(workspace_id=ws.id, agent_id=ag.id, outcome=ControlOutcome.ALLOW, permission_action=PermissionAction.SPEND)
    db_session.add(dec)
    await db_session.flush()

    # Action avec tool inconnu / sans inspecteur concluant
    action = ActionRecord(
        id=uuid.uuid4(),
        workspace_id=ws.id,
        agent_id=ag.id,
        decision_id=dec.id,
        objective="Action nébuleuse",
        tool="custom_third_party",
        operation="do_something",
        arguments={},
        permission_required=PermissionAction.SPEND,
        risk_level=RiskLevel.high,
        risk_reversibility=ReversibilityLevel.irreversible,
        risk_impact=ImpactType.financial,
        canonical_fingerprint="fp_custom_1",
        idempotency_key=f"idemp_{uuid.uuid4()}",
    )
    db_session.add(action)
    await db_session.flush()

    auth = await authorizations.issue_authorization(db_session, decision=dec, action=action, actor="test")

    attempt = ExecutionAttempt(
        id=uuid.uuid4(),
        action_id=action.id,
        authorization_id=auth.id,
        workspace_id=ws.id,
        attempt_number=1,
        idempotency_key=f"att_{uuid.uuid4()}",
        status=AttemptStatus.UNKNOWN,
    )
    db_session.add(attempt)

    reservation = ActionReservation(
        id=uuid.uuid4(),
        workspace_id=ws.id,
        action_id=action.id,
        authorization_id=auth.id,
        resource="currency:EUR",
        units=Decimal("50.00"),
        status=ReservationStatus.HELD,
        idempotency_key=f"res_{uuid.uuid4()}",
    )
    db_session.add(reservation)
    await db_session.commit()

    res = await _reconcile_single_attempt_async(str(attempt.id), db=db_session)
    assert res["status"] == "NO_INSPECTOR_REGISTERED"

    # La réservation DOIT impérativement rester HELD
    assert reservation.status == ReservationStatus.HELD
