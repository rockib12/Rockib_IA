"""Guard checks: status, approval, server-granted permission, payload integrity."""
import uuid

from app.decision_engine.models import ControlOutcome, Decision, DecisionStatus
from app.decision_engine.services.control import set_control
from app.execution.services.guard import evaluate


def _base_decision(**overrides) -> Decision:
    values = dict(
        status=DecisionStatus.pending_approval,
        approval_required=False,
        permission_granted=True,
        control_outcome=ControlOutcome.ALLOW,
        control_reason="POLICY_ALLOWED",
        final_action="Read document",
        permission_required="READ",
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


def test_guard_refuses_rejected_or_escalated():
    # Test Rejected
    d_rej = Decision(status=DecisionStatus.rejected)
    res_rej = evaluate(d_rej)
    assert res_rej.allowed is False
    assert "non exécutable" in res_rej.reason

    # Test Escalated
    d_esc = Decision(status=DecisionStatus.escalated)
    res_esc = evaluate(d_esc)
    assert res_esc.allowed is False
    assert "non exécutable" in res_esc.reason


def test_guard_refuses_expired():
    d = Decision(status=DecisionStatus.expired)
    res = evaluate(d)
    assert res.allowed is False
    assert "non exécutable" in res.reason


def test_guard_refuses_missing_approval():
    d = Decision(status=DecisionStatus.pending_approval, approval_required=True, approved_by=None)
    res = evaluate(d)
    assert res.allowed is False
    assert "Approbation requise" in res.reason


def test_guard_refuses_missing_server_permission():
    d = _base_decision(permission_granted=False, control_outcome=ControlOutcome.DENY)
    set_control(d, ControlOutcome.DENY, "EXECUTION_NOT_PREAUTHORIZED")
    res = evaluate(d)
    assert res.allowed is False
    assert "Permission non accordée" in res.reason


def test_guard_refuses_modified_action():
    d = _base_decision()
    assert evaluate(d).allowed is True
    d.final_action = "Delete everything"
    res = evaluate(d)
    assert res.allowed is False
    assert "modifiée" in res.reason


def test_guard_authorizes_valid():
    # Cas simple : pending, pas d'approbation requise, permission accordée
    d = _base_decision()
    res = evaluate(d)
    assert res.allowed is True

    # Cas simple : pending, approbation requise et présente
    d_app = _base_decision(approval_required=True, approved_by=uuid.uuid4())
    res_app = evaluate(d_app)
    assert res_app.allowed is True