import uuid
from fastapi import Header, HTTPException, status


async def get_current_workspace_id(
    x_workspace_id: str = Header(..., description="ID de l'espace de travail ciblé")
) -> uuid.UUID:
    """
    Dependency Injection FastAPI pour forcer la sélection et l'isolation du Workspace actuel.
    Toutes les requêtes d'un agent ou utilisateur doivent passer par cet ID validé.
    """
    try:
        return uuid.UUID(x_workspace_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Header X-Workspace-ID invalide (doit être un UUID valide).",
        )
