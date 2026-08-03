import uuid
from datetime import datetime

import pytest
from jose import jwt

from app.config import get_settings
from app.services.auth import AuthService
from app.utils.datetime_compat import UTC, timedelta


@pytest.mark.asyncio
async def test_access_and_refresh_tokens_are_created_and_decoded() -> None:
    user_id = uuid.uuid4()
    access_token, expires_in = AuthService.create_access_token(user_id)
    refresh_token = AuthService.create_refresh_token(user_id)

    decoded_access = AuthService._decode_token(access_token)
    decoded_refresh = AuthService._decode_token(refresh_token)

    assert decoded_access is not None
    assert decoded_access["sub"] == str(user_id)
    assert decoded_access["type"] == "access"
    assert expires_in > 0

    assert decoded_refresh is not None
    assert decoded_refresh["sub"] == str(user_id)
    assert decoded_refresh["type"] == "refresh"


@pytest.mark.asyncio
async def test_refresh_token_validation_checks_redis_storage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = uuid.uuid4()
    refresh_token = AuthService.create_refresh_token(user_id)

    class FakeRedis:
        def __init__(self) -> None:
            self.values = {}

        async def get(self, key: str):
            return self.values.get(key)

        async def set(self, key: str, value: str, ex: int = None) -> None:
            self.values[key] = value

        async def delete(self, key: str) -> None:
            self.values.pop(key, None)

    redis = FakeRedis()
    await AuthService.store_refresh_token(user_id, refresh_token, redis)

    assert await AuthService.validate_refresh_token(refresh_token, redis) == user_id

    redis.values["refresh_token:" + str(user_id)] = "different-token"
    assert await AuthService.validate_refresh_token(refresh_token, redis) is None


@pytest.mark.asyncio
async def test_expired_tokens_are_rejected() -> None:
    user_id = uuid.uuid4()
    settings = get_settings()

    expired_access_payload = {
        "sub": str(user_id),
        "exp": datetime.now(UTC) - timedelta(seconds=60),
        "iat": datetime.now(UTC) - timedelta(seconds=120),
        "type": "access",
    }
    expired_refresh_payload = {
        "sub": str(user_id),
        "exp": datetime.now(UTC) - timedelta(seconds=60),
        "iat": datetime.now(UTC) - timedelta(seconds=120),
        "type": "refresh",
    }

    expired_access_token = jwt.encode(
        expired_access_payload, settings.secret_key, algorithm=settings.jwt_algorithm
    )
    expired_refresh_token = jwt.encode(
        expired_refresh_payload, settings.secret_key, algorithm=settings.jwt_algorithm
    )

    assert AuthService._decode_token(expired_access_token) is None
    assert AuthService._decode_token(expired_refresh_token) is None
