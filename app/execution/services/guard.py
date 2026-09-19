from dataclasses import dataclass
from typing import Optional

from app.decision_engine.models import Decision, DecisionStatus
from app.decision_engine.services.control import action_fingerprint as decision_fingerprint
from app.execution.models import ActionRecord


@dataclass
class PermissionResult:
    allowed: bool
    reason: str


def evaluate(decision: Decision, action: Optional[ActionRecord] = None) -> PermissionResult:
    """Vérifie si une décision peut être exécutée maintenant.

    Contrôles serveur indépendants de l'orchestrateur (défense en profondeur) :
    statut, approbation, permission accordée et intégrité de l'action autorisée.

    Deux systèmes d'empreintes coexistent, selon l'état de la décision :

    - tampon **Phase 1** : ``decision.action_fingerprint`` = hash des champs de la
      décision (posé par ``set_control``). Vérifiable sans autre objet.
    - liage **Phase 2** : la même colonne porte l'empreinte **canonique de
      l'action** (posée par ``issue_authorization``). Sa revérification exige
      l'objet ``ActionRecord`` — sans lui, le chemin historique ne peut rien
      prouver et doit refuser : l'exécution passe par le chemin fiable, qui
      revérifie l'autorisation sous verrou (INV-14).
    """
    # Refuse si statut final ou bloqué
    if decision.status in [
        DecisionStatus.rejected,
        DecisionStatus.escalated,
        DecisionStatus.expired,
    ]:
        return PermissionResult(False, f"Décision dans un statut final non exécutable: {decision.status}")

    # Refuse si approbation requise mais manquante
    if decision.approval_required and decision.approved_by is None:
        return PermissionResult(False, "Approbation requise mais non enregistrée")

    # Refuse si le contrôle serveur n'a pas explicitement accordé la permission
    if decision.permission_granted is not True:
        return PermissionResult(
            False,
            f"Permission non accordée par le contrôle serveur (outcome={decision.control_outcome})",
        )

    # Aucun tampon : décisions héritées sans contrôle d'intégrité, rien à vérifier.
    if decision.action_fingerprint is None:
        return PermissionResult(True, "Exécution autorisée")

    # Action structurée fournie : vérifier le liage Phase 2 (empreinte canonique).
    if action is not None:
        if action.workspace_id != decision.workspace_id or action.agent_id != decision.agent_id:
            return PermissionResult(False, "Action hors du périmètre de la décision")
        if decision.action_fingerprint != action.canonical_fingerprint:
            return PermissionResult(False, "Empreinte canonique de l'action modifiée après contrôle")
        return PermissionResult(True, "Exécution autorisée")

    # Chemin historique sans action : le tampon correspond-il au contenu décision ?
    if decision.action_fingerprint == decision_fingerprint(decision):
        return PermissionResult(True, "Exécution autorisée")

    # Sinon : action modifiée après contrôle (INV-03) OU décision déjà liée à une
    # action structurée. Sans l'objet action, impossible de trancher — refus dans
    # les deux cas, avec renvoi explicite vers le chemin fiable.
    return PermissionResult(
        False,
        "Empreinte modifiée ou décision liée à une action structurée : "
        "revérification impossible sans l'action (chemin d'exécution fiable requis)",
    )