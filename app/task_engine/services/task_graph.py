from __future__ import annotations

import heapq
import uuid
from typing import Iterable, Optional

from app.task_engine.exceptions import (
    TaskDependencyValidationError,
    TaskGraphCycleError,
)
from app.task_engine.models import Task, TaskDependency, TaskStatus


class TaskGraph:
    """Représentation et validation déterministe d'un graphe de tâches (DAG).

    Règles & Garanties :
    - Pur déterminisme (sans I/O, sans appel DB, sans appel réseau).
    - Bris d'égalité déterministe par identifiant de tâche (str(task.id)).
    - Non-mutation : les méthodes d'évaluation (ex: get_ready_tasks) ne modifient
      jamais le statut des tâches.
    - Détection stricte de cycles (Algorithme de Kahn).
    - Validation des contraintes d'intégrité en mémoire (pas d'auto-dépendance,
      même goal, même workspace).
    """

    def __init__(
        self,
        tasks: Iterable[Task],
        dependencies: Optional[Iterable[TaskDependency]] = None,
    ) -> None:
        self._tasks: dict[uuid.UUID, Task] = {task.id: task for task in tasks}

        # _adj[u] = ensemble des tâches aval v qui dépendent de u (u -> v)
        self._adj: dict[uuid.UUID, set[uuid.UUID]] = {
            task_id: set() for task_id in self._tasks
        }
        # _dependencies_of[v] = ensemble des tâches amont u dont dépend v
        self._dependencies_of: dict[uuid.UUID, set[uuid.UUID]] = {
            task_id: set() for task_id in self._tasks
        }

        # Chargement des dépendances
        raw_deps: list[tuple[uuid.UUID, uuid.UUID]] = []
        if dependencies is not None:
            for dep in dependencies:
                raw_deps.append((dep.task_id, dep.depends_on_task_id))
        else:
            for task in self._tasks.values():
                if hasattr(task, "dependencies") and task.dependencies:
                    for dep in task.dependencies:
                        raw_deps.append((dep.task_id, dep.depends_on_task_id))

        for task_id, depends_on_id in raw_deps:
            self._register_dependency(task_id, depends_on_id)

    def _register_dependency(
        self, task_id: uuid.UUID, depends_on_task_id: uuid.UUID
    ) -> None:
        """Enregistre et valide une dépendance individuelle."""
        if task_id not in self._tasks:
            raise TaskDependencyValidationError(
                "INVALID_TASK_DEPENDENCY",
                f"La tâche dépendante {task_id} n'appartient pas au graphe.",
            )
        if depends_on_task_id not in self._tasks:
            raise TaskDependencyValidationError(
                "INVALID_TASK_DEPENDENCY",
                f"La tâche prérequise {depends_on_task_id} n'appartient pas au graphe.",
            )
        if task_id == depends_on_task_id:
            raise TaskDependencyValidationError(
                "SELF_DEPENDENCY",
                f"La tâche {task_id} ne peut pas dépendre d'elle-même.",
            )

        t_task = self._tasks[task_id]
        t_dep = self._tasks[depends_on_task_id]

        # Même Goal obligatoire
        if t_task.goal_id != t_dep.goal_id:
            raise TaskDependencyValidationError(
                "CROSS_GOAL_DEPENDENCY",
                f"Dépendance impossible entre tâches de goals distincts "
                f"({t_task.goal_id} != {t_dep.goal_id}).",
            )

        # Même Workspace obligatoire (si accessible via relation Goal ou attribut)
        ws_task = getattr(getattr(t_task, "goal", None), "workspace_id", None)
        ws_dep = getattr(getattr(t_dep, "goal", None), "workspace_id", None)
        if ws_task is not None and ws_dep is not None and ws_task != ws_dep:
            raise TaskDependencyValidationError(
                "CROSS_WORKSPACE_DEPENDENCY",
                f"Dépendance impossible entre tâches de workspaces distincts "
                f"({ws_task} != {ws_dep}).",
            )

        # Enregistrement de l'arc
        self._adj[depends_on_task_id].add(task_id)
        self._dependencies_of[task_id].add(depends_on_task_id)

    def validate(self) -> None:
        """Valide l'intégrité globale du graphe et l'absence de cycle."""
        self.topological_sort()

    def topological_sort(self) -> list[Task]:
        """Retourne les tâches ordonnées topologiquement avec bris d'égalité déterministe.

        Lève TaskGraphCycleError si un cycle est détecté.
        """
        in_degree: dict[uuid.UUID, int] = {
            task_id: len(deps) for task_id, deps in self._dependencies_of.items()
        }

        # Min-heap avec clé (str(task_id), task_id) pour bris d'égalité stable
        heap: list[tuple[str, uuid.UUID]] = [
            (str(task_id), task_id)
            for task_id, deg in in_degree.items()
            if deg == 0
        ]
        heapq.heapify(heap)

        sorted_ids: list[uuid.UUID] = []

        while heap:
            _, u = heapq.heappop(heap)
            sorted_ids.append(u)

            # Pour chaque tâche aval qui attendait u
            for v in self._adj[u]:
                in_degree[v] -= 1
                if in_degree[v] == 0:
                    heapq.heappush(heap, (str(v), v))

        if len(sorted_ids) < len(self._tasks):
            raise TaskGraphCycleError(
                "Un cycle a été détecté dans le graphe de tâches."
            )

        return [self._tasks[task_id] for task_id in sorted_ids]

    def get_ready_tasks(
        self,
        eligible_blocked_task_ids: Optional[Iterable[uuid.UUID]] = None,
    ) -> list[Task]:
        """Retourne la liste déterministe des tâches éligibles au statut READY.

        Règles d'éligibilité :
        1. PENDING dont TOUTES les dépendances amont sont COMPLETED.
        2. BLOCKED dont TOUTES les dépendances amont sont COMPLETED ET dont
           l'identifiant figure explicitement dans eligible_blocked_task_ids
           (preuve externe que la condition bloquante est levée).
        3. Toute dépendance amont non-COMPLETED (ex: FAILED, CANCELLED, RUNNING)
           disqualifie la tâche.
        4. Aucun état terminal (COMPLETED, FAILED, CANCELLED) ni RUNNING n'est éligible.
        5. Aucune mutation de statut n'est effectuée sur les objets Task.
        """
        allowed_blocked = (
            set(eligible_blocked_task_ids)
            if eligible_blocked_task_ids is not None
            else set()
        )

        ready: list[Task] = []

        for task_id, task in self._tasks.items():
            # Détermination de la candidature selon le statut actuel
            if task.status is TaskStatus.PENDING:
                is_candidate = True
            elif task.status is TaskStatus.BLOCKED and task_id in allowed_blocked:
                is_candidate = True
            else:
                is_candidate = False

            if not is_candidate:
                continue

            # Vérification des dépendances amont
            upstream_ids = self._dependencies_of[task_id]
            all_upstream_completed = True
            for up_id in upstream_ids:
                if self._tasks[up_id].status is not TaskStatus.COMPLETED:
                    all_upstream_completed = False
                    break

            if all_upstream_completed:
                ready.append(task)

        # Tri stable déterministe par id
        ready.sort(key=lambda t: str(t.id))
        return ready

    def get_dependencies(self, task_id: uuid.UUID) -> set[uuid.UUID]:
        """Retourne les identifiants des tâches amont dont dépend la tâche."""
        if task_id not in self._tasks:
            raise TaskDependencyValidationError(
                "INVALID_TASK_DEPENDENCY",
                f"La tâche {task_id} n'appartient pas au graphe.",
            )
        return set(self._dependencies_of[task_id])

    def get_dependents(self, task_id: uuid.UUID) -> set[uuid.UUID]:
        """Retourne les identifiants des tâches aval qui attendent cette tâche."""
        if task_id not in self._tasks:
            raise TaskDependencyValidationError(
                "INVALID_TASK_DEPENDENCY",
                f"La tâche {task_id} n'appartient pas au graphe.",
            )
        return set(self._adj[task_id])

    def has_failed_dependency(self, task_id: uuid.UUID) -> bool:
        """Indique si au moins une dépendance amont directe est FAILED ou CANCELLED.

        Fonction d'observation pure : ne modifie aucun statut.
        """
        if task_id not in self._tasks:
            raise TaskDependencyValidationError(
                "INVALID_TASK_DEPENDENCY",
                f"La tâche {task_id} n'appartient pas au graphe.",
            )
        for up_id in self._dependencies_of[task_id]:
            if self._tasks[up_id].status in {
                TaskStatus.FAILED,
                TaskStatus.CANCELLED,
            }:
                return True
        return False
