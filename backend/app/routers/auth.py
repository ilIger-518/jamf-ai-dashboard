"""Authentication router: register, login, refresh, logout, me."""

from fastapi import APIRouter, Cookie, HTTPException, Response, status
from sqlalchemy import select

from app.cache import get_redis
from app.dependencies import get_user_permissions
from app.config import get_settings
from app.dependencies import CurrentUser, DBSession
from app.models.role import Role
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from app.services.auth import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE = "refresh_token"
COOKIE_SECURE = get_settings().cookie_secure
COOKIE_HTTPONLY = True
COOKIE_SAMESITE = "lax"


def _user_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        is_admin=user.is_admin,
        is_active=user.is_active,
        role_id=user.role_id,
        role_name=user.role.name if user.role else None,
        permissions=sorted(get_user_permissions(user)),
        created_at=user.created_at,
    )


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user (first user becomes admin; subsequent users require admin auth)",
)
async def register(body: RegisterRequest, db: DBSession) -> UserResponse:
    # First-ever user is automatically an admin (bootstrap)
    is_first_user = (await AuthService.get_user_count(db)) == 0
    if not is_first_user:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Self-registration is disabled after initial setup",
        )

    # Check for duplicate username / email
    existing = await db.execute(
        select(User).where((User.username == body.username) | (User.email == body.email))
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username or email already registered",
        )

    user = User(
        username=body.username,
        email=body.email,
        hashed_password=AuthService.hash_password(body.password),
        is_admin=is_first_user or body.is_admin,
    )
    if is_first_user:
        admin_role = (
            await db.execute(select(Role).where(Role.name == "Administrator"))
        ).scalar_one_or_none()
        if admin_role:
            user.role_id = admin_role.id
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return _user_response(user)


@router.post("/login", response_model=TokenResponse, summary="Obtain access + refresh tokens")
async def login(body: LoginRequest, response: Response, db: DBSession) -> TokenResponse:
    redis = await get_redis()
    user = await AuthService.authenticate(body.username, body.password, db)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled",
        )

    access_token, expires_in = AuthService.create_access_token(user.id)
    refresh_token = AuthService.create_refresh_token(user.id)
    await AuthService.store_refresh_token(user.id, refresh_token, redis)

    # Deliver refresh token as an httpOnly cookie so it never touches JS
    response.set_cookie(
        key=REFRESH_COOKIE,
        value=refresh_token,
        httponly=COOKIE_HTTPONLY,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        max_age=7 * 86400,
        path="/api/v1/auth",
    )

    return TokenResponse(access_token=access_token, expires_in=expires_in)


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Rotate access token using the refresh token cookie",
)
async def refresh_token(
    response: Response,
    refresh_token: str | None = Cookie(default=None),
) -> TokenResponse:
    redis = await get_redis()
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No refresh token cookie",
        )
    user_id = await AuthService.validate_refresh_token(refresh_token, redis)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    access_token, expires_in = AuthService.create_access_token(user_id)
    new_refresh = AuthService.create_refresh_token(user_id)
    await AuthService.store_refresh_token(user_id, new_refresh, redis)

    response.set_cookie(
        key=REFRESH_COOKIE,
        value=new_refresh,
        httponly=COOKIE_HTTPONLY,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        max_age=7 * 86400,
        path="/api/v1/auth",
    )

    return TokenResponse(access_token=access_token, expires_in=expires_in)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="Invalidate refresh token")
async def logout(current_user: CurrentUser, response: Response) -> None:
    redis = await get_redis()
    await AuthService.invalidate_refresh_token(current_user.id, redis)
    response.delete_cookie(key=REFRESH_COOKIE, path="/api/v1/auth")


@router.get("/me", response_model=UserResponse, summary="Return the authenticated user's profile")
async def me(current_user: CurrentUser) -> UserResponse:
    return _user_response(current_user)
