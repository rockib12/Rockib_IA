from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db

router = APIRouter()


@router.get("/workspaces")
def list_workspaces(db: Session = Depends(get_db)):
    """
    Récupère la liste des espaces de travail autorisés pour l'utilisateur actuel.
    """
    return {"message": "Cette route renverra les espaces de travail cloisonnés."}
