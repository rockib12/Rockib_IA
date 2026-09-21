"""Tests d'authentification et d'isolation du workspace (Identity).

Couvre :
- Hachage/vérification de mot de passe (unitaires, sans DB)
- Création/décodage de JWT (unitaires, sans DB)
- 401 sur token expiré/invalide (unitaires, sans DB)
- Appartenance workspace : 403 pour non-membre, accès normal pour membre (intégration DB)
- Utilisateur courant récupéré via JWT (intégration DB)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.dependencies import get_current_user, get_current_workspace_membership
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.identity.models import User, workspace_memberships
from app.identity.schemas import UserCreate, UserLogin

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Section 1 : Hachage / vérification de mot de passe (unitaires)
# ---------------------------------------------------------------------------

def test_hash_and_verify_password():
    """hash_password produit un hash vérifiable ; mauvais mot de passe rejeté."""
    password = "SuperSecret123!"
    password_hash = hash_password(password)

    assert verify_password(password, password_hash) is True
    assert verify_password("WrongPassword", password_hash) is False


def test_hash_password_is_not_reversible():
    """Le hash ne doit jamais être égal au mot de passe clair."""
    password = "SomePassword"
    password_hash = hash_password(password)
    assert password_hash != password
    assert len(password_hash) > 0


# ---------------------------------------------------------------------------
# Section 2 : JWT — création et décodage (unitaires)
# ---------------------------------------------------------------------------

def test_create_and_decode_access_token():
    """Un token créé avec create_access_token se décode correctement."""
    user_id = str(uuid.uuid4())
    token = create_access_token({"sub": user_id})
    payload = decode_access_token(token)
    assert payload["sub"] == user_id


def test_create_access_token_with_custom_expiry():
    """Un token avec un delta d'expiration personnalisé expire après le bon délai."""
    user_id = str(uuid.uuid4())
    delta = timedelta(minutes=5)
    token = create_access_token({"sub": user_id}, expires_delta=delta)
    payload = decode_access_token(token)
    assert payload["sub"] == user_id
    assert "exp" in payload


def test_decode_access_token_raises_on_invalid_token():
    """Un token invalide lève HTTPException 401."""
    with pytest.raises(Exception) as exc_info:
        decode_access_token("invalid.token.value")
    assert exc_info.value.status_code == 401


def test_decode_access_token_raises_on_expired_token():
    """Un token expiré lève HTTPException 401."""
    user_id = str(uuid.uuid4())
    # Créer un token expiré dans le passé
    payload = {"sub": user_id, "exp": datetime.now(timezone.utc) - timedelta(hours=1)}
    import jose
    token = jose.jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

    with pytest.raises(Exception) as exc_info:
        decode_access_token(token)
    assert exc_info.value.status_code == 401


# ---------------------------------------------------------------------------
# Section 3 : get_current_user — 401 sur token invalide (avec mock DB)
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_user() -> User:
    return User(
        id=uuid.uuid4(),
        email="test@example.com",
        password_hash=hash_password("testpass"),
        is_active=True,
    )


async def test_get_current_user_rejects_expired_token():
    """Un token expiré lève 401 avant même d'interroger la DB."""
    import jose
    from fastapi import HTTPException

    user_id = str(uuid.uuid4())
    payload = {"sub": user_id, "exp": datetime.now(timezone.utc) - timedelta(hours=1)}
    token = jose.jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=AsyncMock(scalar_one_or_none=AsyncMock(return_value=None)))

    with patch("app.core.dependencies.get_async_db", return_value=mock_db):
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(token=token, db=mock_db)
        assert exc_info.value.status_code == 401


async def test_get_current_user_rejects_invalid_token():
    """Un token malformé lève 401."""
    from fastapi import HTTPException

    mock_db = AsyncMock()

    with patch("app.core.dependencies.get_async_db", return_value=mock_db):
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(token="not.a.valid.jwt", db=mock_db)
        assert exc_info.value.status_code == 401


async def test_get_current_user_returns_user_when_valid():
    """Un token valide avec un utilisateur actif retourne l'utilisateur."""
    import jose
    from fastapi import HTTPException

    user_id = uuid.uuid4()
    user = User(id=user_id, email="test@example.com", password_hash=hash_password("pass"), is_active=True)
    token = create_access_token({"sub": str(user_id)})

    mock_result = AsyncMock()
    mock_result.scalar_one_or_none = AsyncMock(return_value=user)
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)

    with patch("app.core.dependencies.get_async_db", return_value=mock_db):
        result = await get_current_user(token=token, db=mock_db)
        assert result.id == user_id
        assert result.is_active is True


async def test_get_current_user_raises_401_for_inactive():
    """Un utilisateur inactif lève 401 même avec un token valide."""
    import jose
    from fastapi import HTTPException

    user_id = uuid.uuid4()
    user = User(id=user_id, email="test@example.com", password_hash=hash_password("pass"), is_active=False)
    token = create_access_token({"sub": str(user_id)})

    mock_result = AsyncMock()
    mock_result.scalar_one_or_none = AsyncMock(return_value=user)
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)

    with patch("app.core.dependencies.get_async_db", return_value=mock_db):
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(token=token, db=mock_db)
        assert exc_info.value.status_code == 401


# ---------------------------------------------------------------------------
# Section 4 : get_current_workspace_membership — 403 pour non-membre (intégration DB)
# ---------------------------------------------------------------------------

@pytest.fixture
async def user_and_workspace(db_session: AsyncSession):
    """Crée un utilisateur, un workspace et une membership."""
    from app.identity.models import Workspace

    workspace = Workspace(name="Test Workspace", slug="test-workspace")
    db_session.add(workspace)
    await db_session.flush()

    user = User(
        email="member@example.com",
        password_hash=hash_password("memberpass"),
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()

    membership = workspace_memberships(
        workspace_id=workspace.id,
        user_id=user.id,
    )
    db_session.add(membership)
    await db_session.commit()
    await db_session.refresh(user)
    await db_session.refresh(workspace)

    return user, workspace, db_session


async def test_get_current_workspace_membership_allows_member(user_and_workspace):
    """Un utilisateur membre du workspace accède normalement (retourne None = pas d'erreur)."""
    from fastapi import HTTPException
    import uuid

    user, workspace, db_session = user_and_workspace

    result = await get_current_workspace_membership(
        workspace_id=str(workspace.id),
        user=user,
        db=db_session,
    )
    # Si on arrive ici sans exception, le test passe
    assert result is None


async def test_get_current_workspace_membership_refuses_non_member(db_session: AsyncSession):
    """Un utilisateur non membre du workspace se voit refuser l'accès (403)."""
    from fastapi import HTTPException
    from app.identity.models import Workspace

    workspace = Workspace(name="Other Workspace", slug="other-workspace")
    db_session.add(workspace)
    await db_session.flush()

    user = User(
        email="nonmember@example.com",
        password_hash=hash_password("somepass"),
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.commit()
    await db_session.refresh(user)
    await db_session.refresh(workspace)

    with pytest.raises(HTTPException) as exc_info:
        await get_current_workspace_membership(
            workspace_id=str(workspace.id),
            user=user,
            db=db_session,
        )
    assert exc_info.value.status_code == 403
    assert "non membre" in exc_info.value.detail.lower()


async def test_get_current_workspace_membership_refuses_invalid_workspace_id():
    """Un workspace_id invalide lève 400."""
    from fastapi import HTTPException
    from app.identity.models import User

    user = User(
        email="test@example.com",
        password_hash=hash_password("pass"),
        is_active=True,
    )
    mock_db = AsyncMock()

    with pytest.raises(HTTPException) as exc_info:
        await get_current_workspace_membership(
            workspace_id="not-a-uuid",
            user=user,
            db=mock_db,
        )
    assert exc_info.value.status_code == 400
    assert "UUID" in exc_info.value.detail


async def test_get_current_workspace_membership_refuses_deleted_user(db_session: AsyncSession):
    """Si l'utilisateur est supprimé du workspace, 403."""
    from fastapi import HTTPException
    from app.identity.models import Workspace

    workspace = Workspace(name="Test Workspace", slug="test-workspace")
    db_session.add(workspace)
    await db_session.flush()

    user = User(
        email="deleted@example.com",
        password_hash=hash_password("pass"),
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.commit()
    await db_session.refresh(user)
    await db_session.refresh(workspace)

    # L'utilisateur n'a pas de membership
    with pytest.raises(HTTPException) as exc_info:
        await get_current_workspace_membership(
            workspace_id=str(workspace.id),
            user=user,
            db=db_session,
        )
    assert exc_info.value.status_code == 403
