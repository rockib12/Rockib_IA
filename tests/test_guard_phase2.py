"""Guard Phase 2 : distinguer le tampon de décision (Phase 1) du liage d'action (Phase 2).

Après ``issue_authorization``, ``decision.action_fingerprint`` porte l'empreinte
canonique de l'action structurée. Le Guard vérifie alors le liage quand l'action
est fournie, et refuse le chemin historique sinon : sans l'objet action, aucune
revérification d'intégrité n'est possible (l'exécution doit passer par le chemin
fiable, qui revalide l'autorisation sous verrou — INV-14).
"""
import uuid

from app.execution.models import ActionRecord
from app.execution.services.fingerprint import compute_fingerprint
from app.execution.services.guard import evaluate

from tests.test_guard import _base_decision


def _bound_action(decision) -> ActionRecord:
    """Action structurée liée : empreinte canonique calculée comme en production."""
    tool, operation, arguments = "documents", "read", {"document_id": "doc-1"}
    return ActionRecord(
        workspace_id=decision.workspace_id,
        agent_id=decision.agent_id,
        decision_id=decision.id,
        objective=decision.objective,
        tool=tool,
        operation=operation,
        arguments=arguments,
        permission_required=decision.permission_required,
        risk_level=decision.risk_level,
        risk_reversibility=decision.risk_reversibility,
        risk_impact=decision.risk_impact,
        canonical_fingerprint=compute_fingerprint(
            workspace_id=decision.workspace_id,
            agent_id=decision.agent_id,
            tool=tool,
            operation=operation,
            permission_required=decision.permission_required,
            objective=decision.objective,
            arguments=arguments,
        ),
        idempotency_key="idem-bound-1",
        version=1,
    )


def test_guard_accepts_bound_decision_with_matching_action():
    """Décision liée + action fournie et intacte : le Guard autorise."""
    decision = _base_decision(workspace_id=uuid.uuid4(), agent_id=uuid.uuid4())
    action = _bound_action(decision)
    decision.action_fingerprint = action.canonical_fingerprint  # liage serveur

    result = evaluate(decision, action=action)

    assert result.allowed is True
    assert result.reason == "Exécution autorisée"


def test_guard_refuses_action_modified_after_binding():
    """L'action a changé après le contrôle : le liage ne correspond plus (INV-03)."""
    decision = _base_decision(workspace_id=uuid.uuid4(), agent_id=uuid.uuid4())
    action = _bound_action(decision)
    decision.action_fingerprint = action.canonical_fingerprint
    action.canonical_fingerprint = "0" * 64

    result = evaluate(decision, action=action)

    assert result.allowed is False
    assert "canonique" in result.reason


def test_guard_refuses_bound_decision_on_legacy_path():
    """Décision liée exécutée sans l'action (chemin historique) : refus explicite."""
    decision = _base_decision(workspace_id=uuid.uuid4(), agent_id=uuid.uuid4())
    action = _bound_action(decision)
    decision.action_fingerprint = action.canonical_fingerprint

    result = evaluate(decision)

    assert result.allowed is False
    assert "fiable" in result.reason


def test_guard_refuses_workspace_mismatch():
    """Action hors du périmètre de la décision : refus avant toute vérification."""
    decision = _base_decision(workspace_id=uuid.uuid4(), agent_id=uuid.uuid4())
    action = _bound_action(decision)
    decision.action_fingerprint = action.canonical_fingerprint
    action.workspace_id = uuid.uuid4()  # autre workspace

    result = evaluate(decision, action=action)

    assert result.allowed is False
    assert "périmètre" in result.reason