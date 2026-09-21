"""Tests exhaustifs et purs de la TaskStateMachine (Étape 2).

Garanties vérifiées :
1. Les 15 transitions valides autorisées.
2. Les 21 transitions interdites depuis les 3 états terminaux (code: TERMINAL_STATE_IMMUTABLE).
3. Les transitions interdites entre états non-terminaux (code: INVALID_TASK_TRANSITION).
4. Le refus strict de toutes les auto-transitions (S -> S).
5. L'exactitude de is_terminal() et can_transition().
6. L'application en mémoire via transition(task, to_status).
7. La préservation stricte de task.status en cas de transition refusée (intégrité).
8. Le pur déterminisme et l'absence d'effets de bord sur 1000 évaluations répétées.
"""
from __future__ import annotations

import uuid
import pytest

from app.task_engine.exceptions import InvalidTaskTransitionError, TaskStateError
from app.task_engine.models import Task, TaskStatus
from app.task_engine.services.state_machine import (
    ALLOWED_TRANSITIONS,
    TERMINAL_STATES,
    TaskStateMachine,
)

ALL_STATUSES = list(TaskStatus)
NON_TERMINAL_STATUSES = [s for s in ALL_STATUSES if s not in TERMINAL_STATES]

# Les 15 transitions valides définies par le contrat
VALID_TRANSITIONS = [
    (TaskStatus.PENDING, TaskStatus.READY),
    (TaskStatus.PENDING, TaskStatus.BLOCKED),
    (TaskStatus.PENDING, TaskStatus.CANCELLED),
    (TaskStatus.PENDING, TaskStatus.FAILED),
    (TaskStatus.READY, TaskStatus.RUNNING),
    (TaskStatus.READY, TaskStatus.BLOCKED),
    (TaskStatus.READY, TaskStatus.CANCELLED),
    (TaskStatus.READY, TaskStatus.FAILED),
    (TaskStatus.RUNNING, TaskStatus.COMPLETED),
    (TaskStatus.RUNNING, TaskStatus.BLOCKED),
    (TaskStatus.RUNNING, TaskStatus.FAILED),
    (TaskStatus.RUNNING, TaskStatus.CANCELLED),
    (TaskStatus.BLOCKED, TaskStatus.READY),
    (TaskStatus.BLOCKED, TaskStatus.FAILED),
    (TaskStatus.BLOCKED, TaskStatus.CANCELLED),
]


def _make_dummy_task(status: TaskStatus) -> Task:
    """Crée une instance Task en mémoire sans base de données."""
    return Task(
        id=uuid.uuid4(),
        goal_id=uuid.uuid4(),
        description="Tâche de test en mémoire",
        status=status,
    )


# ==============================================================================
# 1. Vérification des 15 transitions valides
# ==============================================================================

def test_exact_count_of_valid_transitions():
    """Vérifie que la matrice compte exactement 15 transitions valides."""
    total_valid = sum(len(targets) for targets in ALLOWED_TRANSITIONS.values())
    assert total_valid == 15
    assert len(VALID_TRANSITIONS) == 15


@pytest.mark.parametrize("from_status, to_status", VALID_TRANSITIONS)
def test_valid_transitions_allowed(from_status: TaskStatus, to_status: TaskStatus):
    """Vérifie que chaque transition valide est autorisée sans exception."""
    assert TaskStateMachine.can_transition(from_status, to_status) is True

    # validate_transition ne doit lever aucune exception
    TaskStateMachine.validate_transition(from_status, to_status)

    # transition() doit muter l'objet et renvoyer la tâche
    task = _make_dummy_task(status=from_status)
    updated_task = TaskStateMachine.transition(task, to_status)
    assert updated_task.status is to_status
    assert task.status is to_status


# ==============================================================================
# 2. Vérification des 21 transitions interdites depuis les états terminaux
# ==============================================================================

TERMINAL_TRANSITIONS = [
    (term, target)
    for term in TERMINAL_STATES
    for target in ALL_STATUSES
]


def test_exact_count_of_terminal_transitions():
    """3 états terminaux * 7 cibles possibles = 21 transitions testées."""
    assert len(TERMINAL_TRANSITIONS) == 21


@pytest.mark.parametrize("from_status, to_status", TERMINAL_TRANSITIONS)
def test_terminal_states_immutable(from_status: TaskStatus, to_status: TaskStatus):
    """Toute transition depuis un état terminal doit échouer avec TERMINAL_STATE_IMMUTABLE."""
    assert TaskStateMachine.is_terminal(from_status) is True
    assert TaskStateMachine.can_transition(from_status, to_status) is False

    with pytest.raises(InvalidTaskTransitionError) as exc_info:
        TaskStateMachine.validate_transition(from_status, to_status)

    assert exc_info.value.code == "TERMINAL_STATE_IMMUTABLE"
    assert exc_info.value.from_status == from_status
    assert exc_info.value.to_status == to_status

    # Vérification sur l'objet Task : statut inchangé
    task = _make_dummy_task(status=from_status)
    with pytest.raises(InvalidTaskTransitionError):
        TaskStateMachine.transition(task, to_status)
    assert task.status is from_status


# ==============================================================================
# 3. Transitions interdites entre états non terminaux
# ==============================================================================

INVALID_NON_TERMINAL_TRANSITIONS = [
    (src, dst)
    for src in NON_TERMINAL_STATUSES
    for dst in ALL_STATUSES
    if dst not in ALLOWED_TRANSITIONS[src]
]


@pytest.mark.parametrize("from_status, to_status", INVALID_NON_TERMINAL_TRANSITIONS)
def test_invalid_non_terminal_transitions_rejected(
    from_status: TaskStatus, to_status: TaskStatus
):
    """Toute transition interdite depuis un état non-terminal échoue avec INVALID_TASK_TRANSITION."""
    assert TaskStateMachine.can_transition(from_status, to_status) is False

    with pytest.raises(InvalidTaskTransitionError) as exc_info:
        TaskStateMachine.validate_transition(from_status, to_status)

    assert exc_info.value.code == "INVALID_TASK_TRANSITION"
    assert exc_info.value.from_status == from_status
    assert exc_info.value.to_status == to_status

    # Vérification que le statut de l'objet Task n'est pas modifié
    task = _make_dummy_task(status=from_status)
    with pytest.raises(InvalidTaskTransitionError):
        TaskStateMachine.transition(task, to_status)
    assert task.status is from_status


# ==============================================================================
# 4. Auto-transitions (S -> S)
# ==============================================================================

@pytest.mark.parametrize("status", ALL_STATUSES)
def test_self_transitions_rejected(status: TaskStatus):
    """Une tâche ne peut pas transitionner vers son état actuel (S -> S est interdit)."""
    assert TaskStateMachine.can_transition(status, status) is False

    with pytest.raises(InvalidTaskTransitionError) as exc_info:
        TaskStateMachine.validate_transition(status, status)

    expected_code = (
        "TERMINAL_STATE_IMMUTABLE"
        if status in TERMINAL_STATES
        else "INVALID_TASK_TRANSITION"
    )
    assert exc_info.value.code == expected_code


# ==============================================================================
# 5. Helper is_terminal()
# ==============================================================================

@pytest.mark.parametrize("status", ALL_STATUSES)
def test_is_terminal_predicate(status: TaskStatus):
    """is_terminal retourne True exactement pour COMPLETED, FAILED, CANCELLED."""
    if status in {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED}:
        assert TaskStateMachine.is_terminal(status) is True
    else:
        assert TaskStateMachine.is_terminal(status) is False


# ==============================================================================
# 6. Intégrité de l'objet Task lors d'une transition
# ==============================================================================

def test_task_status_mutation_and_preservation():
    """Vérifie la mutation correcte sur transition valide et préservation sur erreur."""
    task = _make_dummy_task(status=TaskStatus.PENDING)

    # 1. PENDING -> READY (valide)
    TaskStateMachine.transition(task, TaskStatus.READY)
    assert task.status is TaskStatus.READY

    # 2. READY -> COMPLETED (invalide : doit passer par RUNNING)
    with pytest.raises(InvalidTaskTransitionError):
        TaskStateMachine.transition(task, TaskStatus.COMPLETED)
    # L'état reste strictement READY
    assert task.status is TaskStatus.READY

    # 3. READY -> RUNNING (valide)
    TaskStateMachine.transition(task, TaskStatus.RUNNING)
    assert task.status is TaskStatus.RUNNING

    # 4. RUNNING -> COMPLETED (valide)
    TaskStateMachine.transition(task, TaskStatus.COMPLETED)
    assert task.status is TaskStatus.COMPLETED

    # 5. COMPLETED -> READY (invalide car terminal)
    with pytest.raises(InvalidTaskTransitionError):
        TaskStateMachine.transition(task, TaskStatus.READY)
    assert task.status is TaskStatus.COMPLETED


# ==============================================================================
# 7. Déterminisme et pureté sur 1000 itérations
# ==============================================================================

def test_repeatable_determinism():
    """Sur 1000 itérations, la machine produit des résultats rigoureusement identiques."""
    for _ in range(1000):
        # Vérification transition valide
        assert TaskStateMachine.can_transition(TaskStatus.PENDING, TaskStatus.READY) is True
        assert TaskStateMachine.can_transition(TaskStatus.RUNNING, TaskStatus.COMPLETED) is True

        # Vérification transition invalide
        assert TaskStateMachine.can_transition(TaskStatus.PENDING, TaskStatus.RUNNING) is False
        assert TaskStateMachine.can_transition(TaskStatus.COMPLETED, TaskStatus.READY) is False

        # Vérification prédicat terminal
        assert TaskStateMachine.is_terminal(TaskStatus.FAILED) is True
        assert TaskStateMachine.is_terminal(TaskStatus.BLOCKED) is False
