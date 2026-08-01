import uuid

import pytest
from redis.asyncio import Redis

from app.services.auth import AuthService


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
async def test_refresh_token_validation_checks_redis_storage(monkeypatch: pytest.MonkeyPatch) -> None:
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
