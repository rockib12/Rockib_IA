"""Tests exhaustifs et purs du service TaskGraph (Étape 3).

Garanties testées :
1. Graphe simple [A].
2. Graphe linéaire A -> B -> C.
3. Graphe parallèle (diamant) avec bris d'égalité déterministe.
4. Détection de cycle direct et indirect (Kahn).
5. Rejet d'auto-dépendance (A -> A).
6. Rejet de dépendance inter-goals (cross-goal).
7. Rejet de dépendance inter-workspaces (cross-workspace).
8. Résolution READY : PENDING avec toutes dépendances COMPLETED.
9. Résolution READY négative : dépendances PENDING, RUNNING, BLOCKED, FAILED, CANCELLED.
10. Tâches racines sans dépendances.
11. Exclusion absolue des états terminaux et RUNNING de get_ready_tasks.
12. Exigence obligatoire : BLOCKED sans preuve externe (eligible_blocked_task_ids) -> jamais READY.
13. Exigence obligatoire : BLOCKED avec identifiant explicitement fourni -> candidat READY si dépendances COMPLETED.
14. Exigence obligatoire : BLOCKED avec preuve mais dépendance manquante -> pas READY.
15. Non-mutation : les calculs de TaskGraph ne modifient jamais les statuts des tâches.
16. Déterminisme strict répété.
17. has_failed_dependency() détecte FAILED et CANCELLED de manière pure.
"""
from __future__ import annotations

import uuid
import pytest

from app.goal_engine.models import Goal
from app.task_engine.exceptions import (
    TaskDependencyValidationError,
    TaskGraphCycleError,
)
from app.task_engine.models import Task, TaskDependency, TaskStatus
from app.task_engine.services.task_graph import TaskGraph


def _create_task(
    goal_id: uuid.UUID,
    status: TaskStatus = TaskStatus.PENDING,
    workspace_id: uuid.UUID | None = None,
    task_id: uuid.UUID | None = None,
) -> Task:
    task = Task(
        id=task_id or uuid.uuid4(),
        goal_id=goal_id,
        description="Tâche de test graphe",
        status=status,
    )
    if workspace_id is not None:
        task.goal = Goal(
            id=goal_id,
            workspace_id=workspace_id,
            agent_id=uuid.uuid4(),
            objective="Goal de test",
            requested_autonomy_level=1,
            applied_autonomy_level=1,
        )
    return task


# ==============================================================================
# 1. Topologie et parcours déterministes
# ==============================================================================

def test_single_task_graph():
    """Un graphe à un seul nœud retourne ce nœud."""
    goal_id = uuid.uuid4()
    t = _create_task(goal_id)
    graph = TaskGraph([t])
    graph.validate()
    assert graph.topological_sort() == [t]


def test_linear_graph_topological_order():
    """Graphe linéaire A -> B -> C ordonné exactement [A, B, C]."""
    goal_id = uuid.uuid4()
    ta = _create_task(goal_id)
    tb = _create_task(goal_id)
    tc = _create_task(goal_id)

    # B dépend de A ; C dépend de B
    dep_ab = TaskDependency(goal_id=goal_id, task_id=tb.id, depends_on_task_id=ta.id)
    dep_bc = TaskDependency(goal_id=goal_id, task_id=tc.id, depends_on_task_id=tb.id)

    graph = TaskGraph([ta, tb, tc], [dep_ab, dep_bc])
    graph.validate()
    ordered = graph.topological_sort()
    assert ordered == [ta, tb, tc]


def test_diamond_parallel_graph_deterministic_order():
    """Graphe en diamant : A -> B, A -> C, (B, C) -> D avec bris d'égalité stable."""
    goal_id = uuid.uuid4()
    ta = _create_task(goal_id)
    tb = _create_task(goal_id)
    tc = _create_task(goal_id)
    td = _create_task(goal_id)

    deps = [
        TaskDependency(goal_id=goal_id, task_id=tb.id, depends_on_task_id=ta.id),
        TaskDependency(goal_id=goal_id, task_id=tc.id, depends_on_task_id=ta.id),
        TaskDependency(goal_id=goal_id, task_id=td.id, depends_on_task_id=tb.id),
        TaskDependency(goal_id=goal_id, task_id=td.id, depends_on_task_id=tc.id),
    ]

    graph = TaskGraph([ta, tb, tc, td], deps)
    graph.validate()
    ordered = graph.topological_sort()

    assert ordered[0] == ta
    assert ordered[-1] == td
    assert set(ordered[1:3]) == {tb, tc}
    # Bris d'égalité stable : la tâche avec le plus petit str(id) doit venir en premier
    expected_middle = sorted([tb, tc], key=lambda t: str(t.id))
    assert ordered[1:3] == expected_middle


# ==============================================================================
# 2. Rejet des cycles et dépendances invalides
# ==============================================================================

def test_cycle_detection_rejected():
    """Un cycle (A -> B -> C -> A) doit être rejeté par TaskGraphCycleError."""
    goal_id = uuid.uuid4()
    ta = _create_task(goal_id)
    tb = _create_task(goal_id)
    tc = _create_task(goal_id)

    # B dépend de A, C dépend de B, A dépend de C
    deps = [
        TaskDependency(goal_id=goal_id, task_id=tb.id, depends_on_task_id=ta.id),
        TaskDependency(goal_id=goal_id, task_id=tc.id, depends_on_task_id=tb.id),
        TaskDependency(goal_id=goal_id, task_id=ta.id, depends_on_task_id=tc.id),
    ]

    graph = TaskGraph([ta, tb, tc], deps)
    with pytest.raises(TaskGraphCycleError) as exc_info:
        graph.validate()
    assert exc_info.value.code == "TASK_GRAPH_CYCLE"


def test_self_dependency_rejected():
    """Une tâche ne peut pas dépendre d'elle-même."""
    goal_id = uuid.uuid4()
    ta = _create_task(goal_id)
    dep = TaskDependency(goal_id=goal_id, task_id=ta.id, depends_on_task_id=ta.id)

    with pytest.raises(TaskDependencyValidationError) as exc_info:
        TaskGraph([ta], [dep])
    assert exc_info.value.code == "SELF_DEPENDENCY"


def test_cross_goal_dependency_rejected():
    """Une dépendance entre deux goals distincts doit être rejetée."""
    goal_1 = uuid.uuid4()
    goal_2 = uuid.uuid4()
    t1 = _create_task(goal_1)
    t2 = _create_task(goal_2)

    dep = TaskDependency(goal_id=goal_1, task_id=t1.id, depends_on_task_id=t2.id)
    with pytest.raises(TaskDependencyValidationError) as exc_info:
        TaskGraph([t1, t2], [dep])
    assert exc_info.value.code == "CROSS_GOAL_DEPENDENCY"


def test_cross_workspace_dependency_rejected():
    """Deux tâches avec le même goal_id mais des workspaces distincts sont rejetées."""
    goal_id = uuid.uuid4()
    ws_1 = uuid.uuid4()
    ws_2 = uuid.uuid4()

    t1 = _create_task(goal_id, workspace_id=ws_1)
    t2 = _create_task(goal_id, workspace_id=ws_2)

    dep = TaskDependency(goal_id=goal_id, task_id=t1.id, depends_on_task_id=t2.id)
    with pytest.raises(TaskDependencyValidationError) as exc_info:
        TaskGraph([t1, t2], [dep])
    assert exc_info.value.code == "CROSS_WORKSPACE_DEPENDENCY"


# ==============================================================================
# 3. Résolution des tâches READY (get_ready_tasks)
# ==============================================================================

def test_ready_resolution_nominal_all_completed():
    """Une tâche PENDING dont toutes les dépendances sont COMPLETED devient candidate READY."""
    goal_id = uuid.uuid4()
    ta = _create_task(goal_id, status=TaskStatus.COMPLETED)
    tb = _create_task(goal_id, status=TaskStatus.COMPLETED)
    tc = _create_task(goal_id, status=TaskStatus.PENDING)

    deps = [
        TaskDependency(goal_id=goal_id, task_id=tc.id, depends_on_task_id=ta.id),
        TaskDependency(goal_id=goal_id, task_id=tc.id, depends_on_task_id=tb.id),
    ]

    graph = TaskGraph([ta, tb, tc], deps)
    ready = graph.get_ready_tasks()
    assert ready == [tc]


@pytest.mark.parametrize("bad_status", [
    TaskStatus.PENDING,
    TaskStatus.READY,
    TaskStatus.RUNNING,
    TaskStatus.BLOCKED,
    TaskStatus.FAILED,
    TaskStatus.CANCELLED,
])
def test_ready_resolution_unmet_dependency(bad_status: TaskStatus):
    """Si une seule dépendance n'est pas COMPLETED, la tâche dépendante n'est PAS ready."""
    goal_id = uuid.uuid4()
    ta = _create_task(goal_id, status=bad_status)
    tb = _create_task(goal_id, status=TaskStatus.PENDING)

    dep = TaskDependency(goal_id=goal_id, task_id=tb.id, depends_on_task_id=ta.id)
    graph = TaskGraph([ta, tb], [dep])

    ready = graph.get_ready_tasks()
    assert tb not in ready


def test_root_tasks_without_dependencies_are_ready():
    """Les tâches PENDING sans dépendances sont immédiatement éligibles à READY."""
    goal_id = uuid.uuid4()
    t1 = _create_task(goal_id, status=TaskStatus.PENDING)
    t2 = _create_task(goal_id, status=TaskStatus.PENDING)

    graph = TaskGraph([t1, t2])
    ready = graph.get_ready_tasks()
    assert set(ready) == {t1, t2}


@pytest.mark.parametrize("terminal_status", [
    TaskStatus.COMPLETED,
    TaskStatus.FAILED,
    TaskStatus.CANCELLED,
    TaskStatus.RUNNING,
])
def test_terminal_and_running_tasks_never_ready(terminal_status: TaskStatus):
    """Les tâches en état terminal ou déjà RUNNING ne sont jamais candidates READY."""
    goal_id = uuid.uuid4()
    t = _create_task(goal_id, status=terminal_status)
    graph = TaskGraph([t])
    assert graph.get_ready_tasks() == []


# ==============================================================================
# 4. Exigences spécifiques : BLOCKED -> READY
# ==============================================================================

def test_blocked_task_without_proof_is_never_ready():
    """Une tâche BLOCKED sans identifiant dans eligible_blocked_task_ids n'est JAMAIS ready."""
    goal_id = uuid.uuid4()
    ta = _create_task(goal_id, status=TaskStatus.COMPLETED)
    tb = _create_task(goal_id, status=TaskStatus.BLOCKED)

    dep = TaskDependency(goal_id=goal_id, task_id=tb.id, depends_on_task_id=ta.id)
    graph = TaskGraph([ta, tb], [dep])

    # Sans fournir d'éligibilité externe pour tb
    assert graph.get_ready_tasks() == []
    assert graph.get_ready_tasks(eligible_blocked_task_ids=[]) == []


def test_blocked_task_with_external_proof_is_ready_if_dependencies_completed():
    """Une tâche BLOCKED avec preuve explicite devient READY si ses dépendances sont COMPLETED."""
    goal_id = uuid.uuid4()
    ta = _create_task(goal_id, status=TaskStatus.COMPLETED)
    tb = _create_task(goal_id, status=TaskStatus.BLOCKED)

    dep = TaskDependency(goal_id=goal_id, task_id=tb.id, depends_on_task_id=ta.id)
    graph = TaskGraph([ta, tb], [dep])

    # tb est explicitement autorisée avec preuve de déblocage
    ready = graph.get_ready_tasks(eligible_blocked_task_ids=[tb.id])
    assert ready == [tb]


def test_blocked_task_with_external_proof_fails_if_dependencies_unmet():
    """Une tâche BLOCKED avec preuve externe reste NON READY si une dépendance n'est pas COMPLETED."""
    goal_id = uuid.uuid4()
    ta = _create_task(goal_id, status=TaskStatus.RUNNING)
    tb = _create_task(goal_id, status=TaskStatus.BLOCKED)

    dep = TaskDependency(goal_id=goal_id, task_id=tb.id, depends_on_task_id=ta.id)
    graph = TaskGraph([ta, tb], [dep])

    ready = graph.get_ready_tasks(eligible_blocked_task_ids=[tb.id])
    assert ready == []


# ==============================================================================
# 5. Pureté, non-mutation et déterminisme
# ==============================================================================

def test_get_ready_tasks_does_not_mutate_task_status():
    """get_ready_tasks observe mais ne modifie JAMAIS le statut des tâches en mémoire."""
    goal_id = uuid.uuid4()
    ta = _create_task(goal_id, status=TaskStatus.COMPLETED)
    tb = _create_task(goal_id, status=TaskStatus.PENDING)
    tc = _create_task(goal_id, status=TaskStatus.BLOCKED)

    dep1 = TaskDependency(goal_id=goal_id, task_id=tb.id, depends_on_task_id=ta.id)
    dep2 = TaskDependency(goal_id=goal_id, task_id=tc.id, depends_on_task_id=ta.id)
    graph = TaskGraph([ta, tb, tc], [dep1, dep2])

    ready = graph.get_ready_tasks(eligible_blocked_task_ids=[tc.id])
    assert set(ready) == {tb, tc}

    # Les statuts restent strictement intacts
    assert ta.status is TaskStatus.COMPLETED
    assert tb.status is TaskStatus.PENDING
    assert tc.status is TaskStatus.BLOCKED


def test_strict_determinism_repeated():
    """Sur 100 répétitions, topological_sort et get_ready_tasks retournent le même ordre."""
    goal_id = uuid.uuid4()
    tasks = [_create_task(goal_id, status=TaskStatus.PENDING) for _ in range(5)]
    graph = TaskGraph(tasks)

    ref_sort = [t.id for t in graph.topological_sort()]
    ref_ready = [t.id for t in graph.get_ready_tasks()]

    for _ in range(100):
        assert [t.id for t in graph.topological_sort()] == ref_sort
        assert [t.id for t in graph.get_ready_tasks()] == ref_ready


# ==============================================================================
# 6. Observation has_failed_dependency()
# ==============================================================================

def test_has_failed_dependency():
    """Détecte si une dépendance directe est FAILED ou CANCELLED sans mutation."""
    goal_id = uuid.uuid4()
    ta = _create_task(goal_id, status=TaskStatus.COMPLETED)
    tb = _create_task(goal_id, status=TaskStatus.FAILED)
    tc = _create_task(goal_id, status=TaskStatus.CANCELLED)
    td = _create_task(goal_id, status=TaskStatus.PENDING)
    te = _create_task(goal_id, status=TaskStatus.PENDING)

    # td dépend de ta (COMPLETED)
    # te dépend de tb (FAILED) et tc (CANCELLED)
    dep_ad = TaskDependency(goal_id=goal_id, task_id=td.id, depends_on_task_id=ta.id)
    dep_be = TaskDependency(goal_id=goal_id, task_id=te.id, depends_on_task_id=tb.id)
    dep_ce = TaskDependency(goal_id=goal_id, task_id=te.id, depends_on_task_id=tc.id)

    graph = TaskGraph([ta, tb, tc, td, te], [dep_ad, dep_be, dep_ce])

    assert graph.has_failed_dependency(td.id) is False
    assert graph.has_failed_dependency(te.id) is True
    # Pas de modification des tâches
    assert td.status is TaskStatus.PENDING
    assert te.status is TaskStatus.PENDING


def test_get_dependencies_and_dependents():
    """Vérifie get_dependencies et get_dependents."""
    goal_id = uuid.uuid4()
    ta = _create_task(goal_id)
    tb = _create_task(goal_id)

    dep = TaskDependency(goal_id=goal_id, task_id=tb.id, depends_on_task_id=ta.id)
    graph = TaskGraph([ta, tb], [dep])

    assert graph.get_dependencies(tb.id) == {ta.id}
    assert graph.get_dependencies(ta.id) == set()

    assert graph.get_dependents(ta.id) == {tb.id}
    assert graph.get_dependents(tb.id) == set()
