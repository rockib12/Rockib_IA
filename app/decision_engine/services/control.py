"""Phase-one control helpers. No tool dispatch or privilege assignment from AI."""
import hashlib
import json

from app.decision_engine.models import ControlOutcome, Decision


def action_fingerprint(decision: Decision) -> str:
    """Detect changes to the authorized payload, including scope and permission.

    This is an integrity check, not a signature or a substitute for access control.
    Only trusted server code may create/update authorization records.
    """
    fields = (
        "workspace_id", "agent_id", "domain_config_id", "objective", "situation",
        "final_action", "permission_required", "risk_level", "risk_reversibility",
        "risk_impact", "requested_autonomy_level", "applied_autonomy_level",
    )
    payload = {}
    for field in fields:
        value = getattr(decision, field)
        payload[field] = str(getattr(value, "value", value))
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def set_control(decision: Decision, outcome: ControlOutcome, reason: str) -> None:
    """Update the server-derived authorization atomically on the in-memory object."""
    decision.control_outcome = outcome
    decision.control_reason = reason
    decision.permission_granted = outcome == ControlOutcome.ALLOW
    if outcome == ControlOutcome.ESCALATE:
        decision.approval_required = True
        decision.approval_reason = reason
    decision.action_fingerprint = action_fingerprint(decision)