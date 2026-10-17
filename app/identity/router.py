import time
from collections import defaultdict, deque
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_db
from app.core.security import hash_password, verify_password, create_access_token
from app.identity.models import User, Workspace, workspace_memberships
from app.identity.schemas import Token, UserCreate, UserLogin, UserRead
from app.core.dependencies import get_current_user

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

# Protection anti-bruteforce par IP (fenêtre glissante de 60s)
_AUTH_WINDOW_SECONDS = 60
_AUTH_MAX_ATTEMPTS = 15
_auth_ip_attempts: dict[str, deque[float]] = defaultdict(deque)
_DUMMY_PASSWORD_HASH = hash_password("rockib-dummy-timing-guard-secret")


def _check_auth_rate_limit(request: Request) -> None:
    client_ip = request.client.host if request.client else "127.0.0.1"
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()

    now = time.time()
    history = _auth_ip_attempts[client_ip]
    while history and now - history[0] > _AUTH_WINDOW_SECONDS:
        history.popleft()

    if len(history) >= _AUTH_MAX_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Trop de tentatives d'authentification. Veuillez réessayer dans une minute.",
            headers={"Retry-After": str(_AUTH_WINDOW_SECONDS)},
        )
    history.append(now)


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register_user(
    user: UserCreate,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
) -> Token:
    """Crée un utilisateur avec mot de passe haché."""
    _check_auth_rate_limit(request)
    normalized_email = str(user.email).strip().lower()
    existing = (await db.execute(select(User).where(User.email == normalized_email))).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=409, detail="Email déjà utilisé.")

    user_record = User(
        email=normalized_email,
        password_hash=hash_password(user.password),
        first_name=user.first_name,
        last_name=user.last_name,
    )
    db.add(user_record)
    await db.flush()
    await db.refresh(user_record)

    # Création d'un workspace personnel pour l'utilisateur
    workspace = Workspace(name=user_record.email, slug=user_record.email[:50])
    db.add(workspace)
    await db.flush()
    await db.execute(
        workspace_memberships.insert().values(
            workspace_id=workspace.id,
            user_id=user_record.id,
        )
    )
    await db.commit()

    token = create_access_token({"sub": str(user_record.id)})
    return Token(access_token=token, token_type="bearer")


@router.post("/login", response_model=Token)
async def login_user(
    credentials: UserLogin,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
) -> Token:
    """Vérifie les identifiants et retourne un token JWT."""
    _check_auth_rate_limit(request)
    normalized_email = str(credentials.email).strip().lower()
    result = await db.execute(select(User).where(User.email == normalized_email))
    user = result.scalar_one_or_none()
    if user is None:
        # Mitigation d'attaque temporelle (timing side-channel)
        verify_password(credentials.password, _DUMMY_PASSWORD_HASH)
        raise HTTPException(status_code=401, detail="Email ou mot de passe incorrect.")
    if not verify_password(credentials.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Email ou mot de passe incorrect.")
    if not user.is_active:
        raise HTTPException(status_code=401, detail="Utilisateur inactif.")

    token = create_access_token({"sub": str(user.id)})
    return Token(access_token=token, token_type="bearer")


@router.get("/me", response_model=UserRead)
async def get_me(
    current_user: User = Depends(get_current_user),
) -> User:
    """Retourne l'utilisateur courant."""
    return current_user

