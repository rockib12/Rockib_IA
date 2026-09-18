from dataclasses import dataclass
from app.decision_engine.models import Decision, DecisionStatus
from app.decision_engine.services.control import action_fingerprint

@dataclass
class PermissionResult:
    allowed: bool
    reason: str

def evaluate(decision: Decision) -> PermissionResult:
    """Vérifie si une décision peut être exécutée maintenant.

    Contrôles serveur indépendants de l'orchestrateur (défense en profondeur) :
    statut, approbation, permission accordée et intégrité de l'action autorisée.
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

    # Refuse si l'action autorisée a été modifiée après le contrôle
    if decision.action_fingerprint and action_fingerprint(decision) != decision.action_fingerprint:
        return PermissionResult(False, "Empreinte de l'action autorisée modifiée après contrôle")

    return PermissionResult(True, "Exécution autorisée")