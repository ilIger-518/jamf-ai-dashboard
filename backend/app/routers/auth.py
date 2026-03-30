"""Authentication router: register, login, refresh, logout, me."""

import uuid
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Cookie, HTTPException, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select

from app.cache import get_redis
from app.config import get_settings
from app.dependencies import CurrentUser, DBSession, get_user_permissions
from app.models.role import Role
from app.models.user import User
from app.schemas.auth import (
    ChangePasswordRequest,
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
SSO_STATE_PREFIX = "microsoft_sso_state:"


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


def _make_sso_username(email: str) -> str:
    local_part = email.split("@", 1)[0].strip().lower().replace(".", "_")
    base = "".join(ch for ch in local_part if ch.isalnum() or ch in {"_", "-"})
    return (base or "ms_sso_user")[:64]


def _sso_error_redirect(detail: str) -> RedirectResponse:
    settings = get_settings()
    target = f"{settings.frontend_base_url.rstrip('/')}/login?{urlencode({'sso_error': detail})}"
    return RedirectResponse(url=target, status_code=status.HTTP_302_FOUND)


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


@router.post(
    "/change-password",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Change current user's password",
)
async def change_password(
    body: ChangePasswordRequest, current_user: CurrentUser, db: DBSession
) -> None:
    if not AuthService.verify_password(body.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )
    if body.current_password == body.new_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be different from current password",
        )

    current_user.hashed_password = AuthService.hash_password(body.new_password)
    await db.commit()

    # Force refresh-token re-auth after password rotation.
    redis = await get_redis()
    await AuthService.invalidate_refresh_token(current_user.id, redis)


@router.get("/sso/microsoft/start", summary="Start Microsoft SSO login")
async def microsoft_sso_start() -> RedirectResponse:
    settings = get_settings()
    if (
        not settings.microsoft_sso_enabled
        or not settings.microsoft_client_id
        or not settings.microsoft_client_secret
    ):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Microsoft SSO is not configured",
        )

    redis = await get_redis()
    state = str(uuid.uuid4())
    await redis.set(f"{SSO_STATE_PREFIX}{state}", "1", ex=600)

    tenant = settings.microsoft_tenant_id
    auth_url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize"
    params = {
        "client_id": settings.microsoft_client_id,
        "response_type": "code",
        "redirect_uri": settings.microsoft_redirect_uri,
        "response_mode": "query",
        "scope": "openid profile email",
        "state": state,
    }
    return RedirectResponse(
        url=f"{auth_url}?{urlencode(params)}", status_code=status.HTTP_302_FOUND
    )


@router.get("/sso/microsoft/callback", summary="Microsoft SSO callback")
async def microsoft_sso_callback(
    db: DBSession,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    settings = get_settings()
    if error:
        return _sso_error_redirect("Microsoft authentication was cancelled or denied")
    if not code or not state:
        return _sso_error_redirect("Missing SSO callback data")

    redis = await get_redis()
    state_key = f"{SSO_STATE_PREFIX}{state}"
    state_exists = await redis.get(state_key)
    if not state_exists:
        return _sso_error_redirect("Invalid or expired SSO state")
    await redis.delete(state_key)

    token_url = (
        f"https://login.microsoftonline.com/{settings.microsoft_tenant_id}/oauth2/v2.0/token"
    )
    async with httpx.AsyncClient(timeout=30) as client:
        token_resp = await client.post(
            token_url,
            data={
                "grant_type": "authorization_code",
                "client_id": settings.microsoft_client_id,
                "client_secret": settings.microsoft_client_secret,
                "code": code,
                "redirect_uri": settings.microsoft_redirect_uri,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if token_resp.status_code != 200:
            return _sso_error_redirect("Failed to exchange Microsoft auth code")

        token_payload = token_resp.json()
        access_token = token_payload.get("access_token")
        if not access_token:
            return _sso_error_redirect("Missing Microsoft access token")

        userinfo_resp = await client.get(
            "https://graph.microsoft.com/oidc/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if userinfo_resp.status_code != 200:
            return _sso_error_redirect("Unable to fetch Microsoft user profile")
        claims = userinfo_resp.json()

    email = (claims.get("email") or claims.get("preferred_username") or "").strip().lower()
    if not email:
        return _sso_error_redirect("Microsoft account has no email claim")

    user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if user is None:
        candidate = _make_sso_username(email)
        username = candidate
        i = 1
        while (
            await db.execute(select(User).where(User.username == username))
        ).scalar_one_or_none() is not None:
            suffix = f"_{i}"
            username = f"{candidate[: max(1, 64 - len(suffix))]}{suffix}"
            i += 1

        user = User(
            username=username,
            email=email,
            hashed_password=AuthService.hash_password(f"SSO-{uuid.uuid4()}A1"),
            is_admin=False,
            is_active=True,
        )
        viewer_role = (
            await db.execute(select(Role).where(Role.name == "Viewer"))
        ).scalar_one_or_none()
        if viewer_role:
            user.role_id = viewer_role.id
        db.add(user)
        await db.flush()
    elif not user.is_active:
        return _sso_error_redirect("Account is disabled")

    await db.commit()
    await db.refresh(user)

    refresh_token = AuthService.create_refresh_token(user.id)
    await AuthService.store_refresh_token(user.id, refresh_token, redis)

    redirect_to = f"{settings.frontend_base_url.rstrip('/')}/sso/callback?status=success"
    out = RedirectResponse(url=redirect_to, status_code=status.HTTP_302_FOUND)
    out.set_cookie(
        key=REFRESH_COOKIE,
        value=refresh_token,
        httponly=COOKIE_HTTPONLY,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        max_age=7 * 86400,
        path="/api/v1/auth",
    )
    return out
