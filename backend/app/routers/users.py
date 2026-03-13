"""User and role management router."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.authz import ALL_PERMISSIONS
from app.database import get_db
from app.dependencies import get_current_user, require_permission
from app.models.role import Role
from app.models.user import User
from app.schemas.users import (
    PERMISSIONS_CATALOG,
    PermissionsCatalogResponse,
    RoleCreateRequest,
    RoleResponse,
    RoleUpdateRequest,
    UserAdminResponse,
    UserCreateRequest,
    UserUpdateRequest,
)
from app.services.auth import AuthService

router = APIRouter(prefix="/users", tags=["users"])


def _user_permissions(user: User) -> list[str]:
    if user.role and user.role.permissions:
        return sorted(set(user.role.permissions))
    if user.is_admin:
        return ALL_PERMISSIONS
    return []


def _user_response(user: User) -> UserAdminResponse:
    return UserAdminResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        is_admin=user.is_admin,
        is_active=user.is_active,
        created_at=user.created_at,
        role=RoleResponse.model_validate(user.role) if user.role else None,
        permissions=_user_permissions(user),
    )


@router.get("", response_model=list[UserAdminResponse])
async def list_users(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(require_permission("users.manage"))],
) -> list[UserAdminResponse]:
    result = await db.execute(select(User).options(selectinload(User.role)).order_by(User.username))
    users = result.scalars().all()
    return [_user_response(user) for user in users]


@router.post("", response_model=UserAdminResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: UserCreateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(require_permission("users.manage"))],
) -> UserAdminResponse:
    existing = await db.execute(
        select(User).where((User.username == body.username) | (User.email == body.email))
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Username or email already registered")

    role = await db.get(Role, body.role_id)
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    user = User(
        username=body.username,
        email=body.email,
        hashed_password=AuthService.hash_password(body.password),
        role_id=role.id,
        is_active=body.is_active,
        is_admin="roles.manage" in role.permissions or "users.manage" in role.permissions,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user, attribute_names=["role"])
    return _user_response(user)


@router.patch("/{user_id}", response_model=UserAdminResponse)
async def update_user(
    user_id: uuid.UUID,
    body: UserUpdateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_permission("users.manage"))],
) -> UserAdminResponse:
    user = await db.get(User, user_id, options=[selectinload(User.role)])
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if body.email is not None:
        duplicate = await db.execute(select(User).where(User.email == body.email, User.id != user_id))
        if duplicate.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="Email already registered")
        user.email = body.email

    if body.password is not None:
        user.hashed_password = AuthService.hash_password(body.password)

    if body.role_id is not None:
        role = await db.get(Role, body.role_id)
        if not role:
            raise HTTPException(status_code=404, detail="Role not found")
        user.role_id = role.id
        user.is_admin = "roles.manage" in role.permissions or "users.manage" in role.permissions

    if body.is_active is not None:
        if user.id == current_user.id and not body.is_active:
            raise HTTPException(status_code=409, detail="You cannot disable your own account")
        user.is_active = body.is_active

    await db.flush()
    await db.refresh(user, attribute_names=["role"])
    return _user_response(user)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_permission("users.manage"))],
) -> None:
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == current_user.id:
        raise HTTPException(status_code=409, detail="You cannot delete your own account")
    await db.delete(user)


@router.get("/roles", response_model=list[RoleResponse])
async def list_roles(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(get_current_user)],
) -> list[RoleResponse]:
    result = await db.execute(select(Role).order_by(Role.is_system.desc(), Role.name.asc()))
    roles = result.scalars().all()
    return [RoleResponse.model_validate(role) for role in roles]


@router.get("/permissions", response_model=PermissionsCatalogResponse)
async def list_permissions(_: Annotated[User, Depends(get_current_user)]) -> PermissionsCatalogResponse:
    return PermissionsCatalogResponse(items=PERMISSIONS_CATALOG)


@router.post("/roles", response_model=RoleResponse, status_code=status.HTTP_201_CREATED)
async def create_role(
    body: RoleCreateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(require_permission("roles.manage"))],
) -> RoleResponse:
    existing = await db.execute(select(Role).where(Role.name == body.name))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Role name already exists")
    role = Role(name=body.name, description=body.description, permissions=body.permissions, is_system=False)
    db.add(role)
    await db.flush()
    await db.refresh(role)
    return RoleResponse.model_validate(role)


@router.patch("/roles/{role_id}", response_model=RoleResponse)
async def update_role(
    role_id: uuid.UUID,
    body: RoleUpdateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(require_permission("roles.manage"))],
) -> RoleResponse:
    role = await db.get(Role, role_id)
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    if role.is_system:
        raise HTTPException(status_code=409, detail="System roles cannot be edited")
    if body.name is not None:
        existing = await db.execute(select(Role).where(Role.name == body.name, Role.id != role_id))
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="Role name already exists")
        role.name = body.name
    if body.description is not None:
        role.description = body.description
    if body.permissions is not None:
        role.permissions = body.permissions
    await db.flush()
    await db.refresh(role)
    return RoleResponse.model_validate(role)


@router.delete("/roles/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_role(
    role_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(require_permission("roles.manage"))],
) -> None:
    role = await db.get(Role, role_id, options=[selectinload(Role.users)])
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    if role.is_system:
        raise HTTPException(status_code=409, detail="System roles cannot be deleted")
    if role.users:
        raise HTTPException(status_code=409, detail="Role is assigned to one or more users")
    await db.delete(role)
