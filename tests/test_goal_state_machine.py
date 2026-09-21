"""Tests exhaustifs et purs de GoalStateMachine (STEP 4A).

Garanties vérifiées :
1. Les 16 transitions valides autorisées.
2. Les 21 transitions interdites depuis les 3 états terminaux (code: TERMINAL_STATE_IMMUTABLE).
3. Les 12 transitions interdites entre états non-terminaux (code: INVALID_GOAL_TRANSITION).
4. Le refus strict de toutes les auto-transitions (S -> S).
5. L'exactitude de is_terminal() et can_transition().
6. L'application en mémoire via transition(goal, to_status).
7. La préservation stricte de goal.status en cas de transition refusée (intégrité).
8. Le pur déterminisme et l'absence d'effets de bord sur 1000 évaluations répétées.
9. L'exhaustivité complète de la matrice 7x7 (49 combinaisons testées).
"""
from __future__ import annotations

import uuid
import pytest

from app.goal_engine.exceptions import (
    GoalLifecycleError,
    InvalidGoalTransitionError,
)
from app.goal_engine.models import Goal, GoalStatus
from app.goal_engine.services.goal_state_machine import (
    ALLOWED_TRANSITIONS,
    TERMINAL_STATES,
    GoalStateMachine,
)

ALL_STATUSES = list(GoalStatus)
NON_TERMINAL_STATUSES = [s for s in ALL_STATUSES if s not in TERMINAL_STATES]

# Les 16 transitions valides définies par la spécification STEP 4A et docs/architecture.md
VALID_TRANSITIONS = [
    # PENDING -> PLANNING, CANCELLED, FAILED (3)
    (GoalStatus.PENDING, GoalStatus.PLANNING),
    (GoalStatus.PENDING, GoalStatus.CANCELLED),
    (GoalStatus.PENDING, GoalStatus.FAILED),
    # PLANNING -> ACTIVE, PAUSED, FAILED, CANCELLED (4)
    (GoalStatus.PLANNING, GoalStatus.ACTIVE),
    (GoalStatus.PLANNING, GoalStatus.PAUSED),
    (GoalStatus.PLANNING, GoalStatus.FAILED),
    (GoalStatus.PLANNING, GoalStatus.CANCELLED),
    # ACTIVE -> PLANNING, PAUSED, COMPLETED, FAILED, CANCELLED (5)
    (GoalStatus.ACTIVE, GoalStatus.PLANNING),
    (GoalStatus.ACTIVE, GoalStatus.PAUSED),
    (GoalStatus.ACTIVE, GoalStatus.COMPLETED),
    (GoalStatus.ACTIVE, GoalStatus.FAILED),
    (GoalStatus.ACTIVE, GoalStatus.CANCELLED),
    # PAUSED -> PLANNING, ACTIVE, FAILED, CANCELLED (4)
    (GoalStatus.PAUSED, GoalStatus.PLANNING),
    (GoalStatus.PAUSED, GoalStatus.ACTIVE),
    (GoalStatus.PAUSED, GoalStatus.FAILED),
    (GoalStatus.PAUSED, GoalStatus.CANCELLED),
]

# Les 21 transitions interdites depuis les 3 états terminaux (3 * 7 = 21)
TERMINAL_TRANSITIONS = [
    (term, target)
    for term in TERMINAL_STATES
    for target in ALL_STATUSES
]

# Les 12 transitions interdites entre états non-terminaux (4 * 7 - 16 = 12)
INVALID_NON_TERMINAL_TRANSITIONS = [
    (source, target)
    for source in NON_TERMINAL_STATUSES
    for target in ALL_STATUSES
    if target not in ALLOWED_TRANSITIONS[source]
]


def _make_dummy_goal(status: GoalStatus) -> Goal:
    """Crée une instance Goal en mémoire sans base de données."""
    return Goal(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        agent_id=uuid.uuid4(),
        objective="Tester la machine d'état en mémoire",
        requested_autonomy_level=1,
        applied_autonomy_level=1,
        status=status,
    )


# ==============================================================================
# 1. Vérification du décompte exact et exhaustif de la matrice 7x7 (49 combinaisons)
# ==============================================================================

def test_exact_matrix_counts():
    """Vérifie l'exhaustivité de la partition de l'espace 7x7 = 49 transitions."""
    total_valid = sum(len(targets) for targets in ALLOWED_TRANSITIONS.values())
    assert total_valid == 16
    assert len(VALID_TRANSITIONS) == 16
    assert len(TERMINAL_TRANSITIONS) == 21
    assert len(INVALID_NON_TERMINAL_TRANSITIONS) == 12
    # 16 + 21 + 12 = 49 (7 * 7)
    assert len(VALID_TRANSITIONS) + len(TERMINAL_TRANSITIONS) + len(INVALID_NON_TERMINAL_TRANSITIONS) == 49


# ==============================================================================
# 2. Vérification des 16 transitions valides
# ==============================================================================

@pytest.mark.parametrize("from_status, to_status", VALID_TRANSITIONS)
def test_valid_transitions_allowed(from_status: GoalStatus, to_status: GoalStatus):
    """Vérifie que chaque transition valide est autorisée sans lever d'exception."""
    assert GoalStateMachine.can_transition(from_status, to_status) is True

    # validate_transition ne doit lever aucune exception
    GoalStateMachine.validate_transition(from_status, to_status)

    # transition() doit muter l'objet en mémoire et retourner l'instance
    goal = _make_dummy_goal(status=from_status)
    updated = GoalStateMachine.transition(goal, to_status)
    assert updated is goal
    assert updated.status is to_status
    assert goal.status is to_status


# ==============================================================================
# 3. Vérification des 21 transitions interdites depuis les états terminaux
# ==============================================================================

@pytest.mark.parametrize("from_status, to_status", TERMINAL_TRANSITIONS)
def test_terminal_transitions_forbidden(from_status: GoalStatus, to_status: GoalStatus):
    """Vérifie que toute transition depuis un état terminal est rejetée avec TERMINAL_STATE_IMMUTABLE."""
    assert GoalStateMachine.is_terminal(from_status) is True
    assert GoalStateMachine.can_transition(from_status, to_status) is False

    with pytest.raises(InvalidGoalTransitionError) as exc_info:
        GoalStateMachine.validate_transition(from_status, to_status)

    err = exc_info.value
    assert err.code == "TERMINAL_STATE_IMMUTABLE"
    assert err.from_status == from_status
    assert err.to_status == to_status
    assert "immuable" in str(err)

    # Vérification d'intégrité en mémoire : le statut ne doit PAS muter
    goal = _make_dummy_goal(status=from_status)
    with pytest.raises(InvalidGoalTransitionError):
        GoalStateMachine.transition(goal, to_status)

    assert goal.status is from_status


# ==============================================================================
# 4. Vérification des 12 transitions invalides entre états non-terminaux
# ==============================================================================

@pytest.mark.parametrize("from_status, to_status", INVALID_NON_TERMINAL_TRANSITIONS)
def test_invalid_non_terminal_transitions_forbidden(
    from_status: GoalStatus, to_status: GoalStatus
):
    """Vérifie que toute transition interdite entre états non-terminaux lève INVALID_GOAL_TRANSITION."""
    assert GoalStateMachine.is_terminal(from_status) is False
    assert GoalStateMachine.can_transition(from_status, to_status) is False

    with pytest.raises(InvalidGoalTransitionError) as exc_info:
        GoalStateMachine.validate_transition(from_status, to_status)

    err = exc_info.value
    assert err.code == "INVALID_GOAL_TRANSITION"
    assert err.from_status == from_status
    assert err.to_status == to_status

    # Vérification d'intégrité en mémoire : le statut ne doit PAS muter
    goal = _make_dummy_goal(status=from_status)
    with pytest.raises(InvalidGoalTransitionError):
        GoalStateMachine.transition(goal, to_status)

    assert goal.status is from_status


# ==============================================================================
# 5. Vérification du refus de toutes les auto-transitions (S -> S)
# ==============================================================================

@pytest.mark.parametrize("status", ALL_STATUSES)
def test_self_transitions_forbidden(status: GoalStatus):
    """Vérifie qu'aucune auto-transition (status -> status) n'est jamais autorisée."""
    assert GoalStateMachine.can_transition(status, status) is False

    with pytest.raises(InvalidGoalTransitionError) as exc_info:
        GoalStateMachine.validate_transition(status, status)

    expected_code = (
        "TERMINAL_STATE_IMMUTABLE"
        if status in TERMINAL_STATES
        else "INVALID_GOAL_TRANSITION"
    )
    assert exc_info.value.code == expected_code


# ==============================================================================
# 6. Vérification de is_terminal()
# ==============================================================================

def test_is_terminal_exactness():
    """Vérifie que is_terminal est True uniquement pour COMPLETED, FAILED, CANCELLED."""
    expected_terminals = {
        GoalStatus.COMPLETED,
        GoalStatus.FAILED,
        GoalStatus.CANCELLED,
    }
    for status in ALL_STATUSES:
        if status in expected_terminals:
            assert GoalStateMachine.is_terminal(status) is True
        else:
            assert GoalStateMachine.is_terminal(status) is False


# ==============================================================================
# 7. Vérification de la hiérarchie d'exceptions
# ==============================================================================

def test_exception_hierarchy():
    """Vérifie la conformité de l'arborescence des exceptions."""
    err = InvalidGoalTransitionError(GoalStatus.PENDING, GoalStatus.COMPLETED)
    assert isinstance(err, GoalLifecycleError)
    assert isinstance(err, Exception)
    assert err.code == "INVALID_GOAL_TRANSITION"
    assert err.from_status == GoalStatus.PENDING
    assert err.to_status == GoalStatus.COMPLETED

    err_term = InvalidGoalTransitionError(GoalStatus.COMPLETED, GoalStatus.ACTIVE)
    assert err_term.code == "TERMINAL_STATE_IMMUTABLE"


# ==============================================================================
# 8. Pureté, déterminisme et 1000 itérations sans effets de bord
# ==============================================================================

def test_determinism_and_repeatability_1000_runs():
    """Vérifie qu'aucun état partagé ou aléa n'altère le comportement sur 1000 runs."""
    for _ in range(1000):
        # Valide
        assert GoalStateMachine.can_transition(GoalStatus.PENDING, GoalStatus.PLANNING) is True
        assert GoalStateMachine.can_transition(GoalStatus.ACTIVE, GoalStatus.COMPLETED) is True
        assert GoalStateMachine.can_transition(GoalStatus.PAUSED, GoalStatus.ACTIVE) is True

        # Invalide
        assert GoalStateMachine.can_transition(GoalStatus.PENDING, GoalStatus.ACTIVE) is False
        assert GoalStateMachine.can_transition(GoalStatus.COMPLETED, GoalStatus.PLANNING) is False
        assert GoalStateMachine.can_transition(GoalStatus.FAILED, GoalStatus.PENDING) is False

        # Terminal
        assert GoalStateMachine.is_terminal(GoalStatus.COMPLETED) is True
        assert GoalStateMachine.is_terminal(GoalStatus.ACTIVE) is False
