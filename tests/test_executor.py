import pytest
from app.execution.services.executor import execute, register_handler, _HANDLERS, ExecutionResult
from app.decision_engine.models import ControlOutcome, Decision, DecisionStatus, PermissionAction
from app.decision_engine.services.control import set_control
import uuid


def _authorized_decision(**overrides) -> Decision:
    """Décision explicitement autorisée par le contrôle serveur."""
    values = dict(
        status=DecisionStatus.pending_approval,
        approval_required=False,
        permission_required=PermissionAction.READ,
        permission_granted=True,
        control_outcome=ControlOutcome.ALLOW,
        control_reason="POLICY_ALLOWED",
        final_action="Read document",
        risk_level="low",
        risk_reversibility="reversible",
        risk_impact="internal",
        requested_autonomy_level=2,
        applied_autonomy_level=2,
    )
    values.update(overrides)
    decision = Decision(**values)
    set_control(decision, ControlOutcome.ALLOW, "POLICY_ALLOWED")
    return decision


@pytest.mark.asyncio
async def test_executor_no_handler():
    _HANDLERS.clear() # Assure que le registre est vide
    d = _authorized_decision()

    res = await execute(d)
    assert res.success is False
    assert "Aucun handler enregistré" in res.error

@pytest.mark.asyncio
async def test_executor_calls_handler():
    _HANDLERS.clear()

    async def mock_handler(decision: Decision) -> ExecutionResult:
        return ExecutionResult(success=True, output="Done", error=None)

    register_handler(PermissionAction.READ, mock_handler)

    d = _authorized_decision()

    res = await execute(d)
    assert res.success is True
    assert res.output == "Done"

@pytest.mark.asyncio
async def test_executor_guard_refusal():
    _HANDLERS.clear()

    # Tentative d'exécution d'une décision rejetée
    d = Decision(status=DecisionStatus.rejected)

    res = await execute(d)
    assert res.success is False
    assert "non exécutable" in res.error


@pytest.mark.asyncio
async def test_executor_refuses_unauthorized_decision():
    """Une décision sans permission serveur n'atteint jamais un handler."""
    _HANDLERS.clear()

    async def mock_handler(decision: Decision) -> ExecutionResult:
        return ExecutionResult(success=True, output="Done", error=None)

    register_handler(PermissionAction.READ, mock_handler)

    d = Decision(
        status=DecisionStatus.pending_approval,
        approval_required=False,
        permission_required=PermissionAction.READ,
        permission_granted=False,
        control_outcome=ControlOutcome.DENY,
        control_reason="EXECUTION_NOT_PREAUTHORIZED",
    )

    res = await execute(d)
    assert res.success is False
    assert "Permission non accordée" in res.error