from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_db
from app.core.security import hash_password, verify_password, create_access_token
from app.identity.models import User, Workspace, workspace_memberships
from app.identity.schemas import Token, UserCreate, UserLogin, UserRead
from app.core.dependencies import get_current_user

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])



@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register_user(
    user: UserCreate,
    db: AsyncSession = Depends(get_async_db),
) -> Token:
    """Crée un utilisateur avec mot de passe haché."""
    existing = (await db.execute(select(User).where(User.email == str(user.email)))).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=409, detail="Email déjà utilisé.")

    user_record = User(
        email=str(user.email),
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
    db: AsyncSession = Depends(get_async_db),
) -> Token:
    """Vérifie les identifiants et retourne un token JWT."""
    result = await db.execute(select(User).where(User.email == str(credentials.email)))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(credentials.password, user.password_hash):
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
