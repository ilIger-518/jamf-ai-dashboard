"""Shared FastAPI dependencies."""

import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.authz import ALL_PERMISSIONS
from app.database import get_db
from app.models.user import User
from app.services.auth import AuthService

bearer_scheme = HTTPBearer()


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Validate the JWT Bearer token and return the authenticated user."""
    token_payload = AuthService._decode_token(credentials.credentials)
    if not token_payload or token_payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user_id = uuid.UUID(token_payload["sub"])
    except (ValueError, KeyError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    result = await db.execute(
        select(User).options(selectinload(User.role)).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user account",
        )
    return user


def get_user_permissions(current_user: User) -> set[str]:
    if current_user.role and current_user.role.permissions:
        return set(current_user.role.permissions)
    if current_user.is_admin:
        return set(ALL_PERMISSIONS)
    return set()


def require_permission(permission: str):
    async def dependency(current_user: Annotated[User, Depends(get_current_user)]) -> User:
        if permission not in get_user_permissions(current_user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission required: {permission}",
            )
        return current_user

    return dependency


async def require_admin(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Require the current user to be an admin."""
    if "settings.manage" not in get_user_permissions(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator privileges required",
        )
    return current_user


# Type aliases for cleaner router signatures
CurrentUser = Annotated[User, Depends(get_current_user)]
AdminUser = Annotated[User, Depends(require_admin)]
DBSession = Annotated[AsyncSession, Depends(get_db)]
ManageServersUser = Annotated[User, Depends(require_permission("servers.manage"))]
ManageServerSyncUser = Annotated[User, Depends(require_permission("servers.sync"))]
ManageKnowledgeUser = Annotated[User, Depends(require_permission("knowledge.manage"))]
ManageMigratorUser = Annotated[User, Depends(require_permission("migrator.manage"))]
ManagePackageSyncUser = Annotated[User, Depends(require_permission("package_sync.manage"))]
ManageUsersUser = Annotated[User, Depends(require_permission("users.manage"))]
ManageRolesUser = Annotated[User, Depends(require_permission("roles.manage"))]
