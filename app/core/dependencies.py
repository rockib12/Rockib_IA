import inspect
import json
import uuid
from pathlib import Path

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_async_db
from app.core.security import decode_access_token
from app.identity.models import User, workspace_memberships

# --- Decision Engine / Intelligence factories (existants) ---------------------

from app.cognitive.services.simulation import CognitiveSimulator
from app.decision_engine.services.domain_classifier import DomainClassifier
from app.decision_engine.services.arbitrator import DeterministicArbitrator
from app.intelligence.services.ai_provider import AIProvider
from app.intelligence.services.providers.groq_provider import GroqProvider
from app.intelligence.services.rational_agent import RationalAgent
from app.intelligence.services.risk_analyst import RiskAnalyst
from app.intelligence.services.intelligence_service import IntelligenceService
from app.decision_engine.models import PermissionAction

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def get_classifier_mapping() -> dict:
    """Charge le mapping de classification depuis un fichier JSON."""
    config_path = Path(__file__).resolve().parents[1] / "decision_engine" / "classifier_config.json"
    if not config_path.exists():
        return {}
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return {k: tuple(v) for k, v in data.items()}
    except Exception:
        return {}


def get_classifier(mapping: dict = Depends(get_classifier_mapping)) -> DomainClassifier:
    """Factory : classifier de domaine."""
    if not isinstance(mapping, dict):
        mapping = get_classifier_mapping()
    return DomainClassifier(mapping=mapping)


def get_arbitrator(db: AsyncSession = Depends(get_async_db)) -> DeterministicArbitrator:
    """Factory : arbitre utilisant la session de la requête pour ses politiques."""
    if not isinstance(db, AsyncSession):
        db = None
    return DeterministicArbitrator(db=db)


def get_ai_provider() -> AIProvider:
    """Factory : fournisseur LLM Groq natif."""
    return GroqProvider()


def get_cognitive_simulator(provider: AIProvider = Depends(get_ai_provider)) -> CognitiveSimulator:
    """Factory : simulateur cognitif qui utilise le provider LLM."""
    if not hasattr(provider, "generate"):
        provider = get_ai_provider()
    return CognitiveSimulator(provider=provider)


def get_intelligence_service(provider: AIProvider = Depends(get_ai_provider)) -> IntelligenceService:
    """Factory : service d'intelligence cognitique complet."""
    if not hasattr(provider, "generate"):
        provider = get_ai_provider()
    return IntelligenceService(
        rational_agent=RationalAgent(provider=provider),
        risk_analyst=RiskAnalyst(provider=provider),
    )


# --- Identity / Auth dependencies (nouveaux) ---------------------------------

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_async_db),
) -> User:
    """Dépendance pour obtenir l'utilisateur courant via JWT."""
    payload = decode_access_token(token)
    user_id: str = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalide : pas de subject.",
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if inspect.isawaitable(user):
        user = await user
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Utilisateur introuvable.",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Utilisateur inactif.",
        )
    return user


async def get_current_workspace_membership(
    workspace_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> None:
    """Vérifie que l'utilisateur est membre du workspace ciblé. Lève 403 sinon."""
    try:
        ws_uuid = uuid.UUID(workspace_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="workspace_id invalide (doit être un UUID).",
        )

    result = await db.execute(
        select(workspace_memberships).where(
            workspace_memberships.c.workspace_id == ws_uuid,
            workspace_memberships.c.user_id == user.id,
        )
    )
    membership = result.first()
    if inspect.isawaitable(membership):
        membership = await membership
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès refusé : vous n'êtes pas membre de cet espace de travail.",
        )


async def get_current_user_id(token: str = Depends(oauth2_scheme)) -> str:
    """Retourne l'identifiant de l'utilisateur courant depuis le JWT."""
    payload = decode_access_token(token)
    user_id: str = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalide : pas de subject.",
        )
    return user_id


# --- Isolation tenant (STEP 6H) ------------------------------------------------

oauth2_scheme_optional = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


async def get_optional_user(
    token: str | None = Depends(oauth2_scheme_optional),
    db: AsyncSession = Depends(get_async_db),
) -> User | None:
    """Utilisateur courant si un Bearer est fourni, sinon None.

    Un token PRÉSENT mais invalide lève 401 (pas de dégradation silencieuse).
    """
    if not token:
        return None
    return await get_current_user(token=token, db=db)


async def get_user_workspace_ids(db: AsyncSession, user: User) -> set[uuid.UUID]:
    """Ensemble des workspaces dont l'utilisateur est membre."""
    result = await db.execute(
        select(workspace_memberships.c.workspace_id).where(
            workspace_memberships.c.user_id == user.id
        )
    )
    return {row[0] for row in result.all()}


async def assert_workspace_member(db: AsyncSession, user: User, workspace_id: uuid.UUID) -> None:
    """Lève 403 si l'utilisateur n'est pas membre du workspace."""
    if workspace_id not in await get_user_workspace_ids(db, user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès refusé : vous n'êtes pas membre de cet espace de travail.",
        )
