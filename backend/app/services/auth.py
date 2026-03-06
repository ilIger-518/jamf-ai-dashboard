"""Authentication service: password hashing, JWT issuance/validation, token refresh."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt as _bcrypt
from jose import JWTError, jwt
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.user import User

REFRESH_TOKEN_PREFIX = "refresh_token:"


class AuthService:
    # ── Passwords ────────────────────────────────────────────────

    @staticmethod
    def hash_password(plain: str) -> str:
        return _bcrypt.hashpw(plain.encode(), _bcrypt.gensalt()).decode()

    @staticmethod
    def verify_password(plain: str, hashed: str) -> bool:
        return _bcrypt.checkpw(plain.encode(), hashed.encode())

    # ── JWT ──────────────────────────────────────────────────────

    @staticmethod
    def create_access_token(user_id: uuid.UUID) -> tuple[str, int]:
        """Return (encoded_jwt, expires_in_seconds)."""
        settings = get_settings()
        expires_in = settings.access_token_expire_minutes * 60
        expire = datetime.now(UTC) + timedelta(seconds=expires_in)
        payload: dict[str, Any] = {
            "sub": str(user_id),
            "exp": expire,
            "iat": datetime.now(UTC),
            "type": "access",
        }
        token = jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)
        return token, expires_in

    @staticmethod
    def create_refresh_token(user_id: uuid.UUID) -> str:
        settings = get_settings()
        expire = datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days)
        payload: dict[str, Any] = {
            "sub": str(user_id),
            "exp": expire,
            "iat": datetime.now(UTC),
            "type": "refresh",
            "jti": str(uuid.uuid4()),
        }
        return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)

    @staticmethod
    def _decode_token(token: str) -> dict[str, Any] | None:
        settings = get_settings()
        try:
            return jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
        except JWTError:
            return None

    # ── Redis refresh-token store ────────────────────────────────

    @staticmethod
    async def store_refresh_token(user_id: uuid.UUID, refresh_token: str, redis: Redis) -> None:
        settings = get_settings()
        ttl = settings.refresh_token_expire_days * 86400
        key = f"{REFRESH_TOKEN_PREFIX}{user_id}"
        await redis.set(key, refresh_token, ex=ttl)

    @staticmethod
    async def invalidate_refresh_token(user_id: uuid.UUID, redis: Redis) -> None:
        key = f"{REFRESH_TOKEN_PREFIX}{user_id}"
        await redis.delete(key)

    @staticmethod
    async def validate_refresh_token(refresh_token: str, redis: Redis) -> uuid.UUID | None:
        payload = AuthService._decode_token(refresh_token)
        if not payload or payload.get("type") != "refresh":
            return None
        user_id = uuid.UUID(payload["sub"])
        stored = await redis.get(f"{REFRESH_TOKEN_PREFIX}{user_id}")
        if stored != refresh_token:
            return None
        return user_id

    # ── User lookup ──────────────────────────────────────────────

    @staticmethod
    async def get_user_from_token(token: str, db: AsyncSession, redis: Redis) -> User | None:
        payload = AuthService._decode_token(token)
        if not payload or payload.get("type") != "access":
            return None
        try:
            user_id = uuid.UUID(payload["sub"])
        except (ValueError, KeyError):
            return None
        result = await db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def authenticate(username: str, password: str, db: AsyncSession) -> User | None:
        result = await db.execute(select(User).where(User.username == username))
        user = result.scalar_one_or_none()
        if user is None or not AuthService.verify_password(password, user.hashed_password):
            return None
        return user

    @staticmethod
    async def get_user_count(db: AsyncSession) -> int:
        from sqlalchemy import func, select

        result = await db.execute(select(func.count()).select_from(User))
        return result.scalar_one()
