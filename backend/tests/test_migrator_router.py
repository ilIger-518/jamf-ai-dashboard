from unittest.mock import AsyncMock, MagicMock

import pytest

from app.routers.migrator import _clear_policy_scope_computers, _ensure_payload_categories_exist


def test_clear_policy_scope_computers_removes_scope_and_exclusion_computers() -> None:
    payload = {
        "scope": {
            "computers": {"computer": [{"id": 10, "name": "Mac-01"}]},
            "exclusions": {
                "computers": {"computer": [{"id": 11, "name": "Mac-02"}]},
            },
        }
    }

    changed = _clear_policy_scope_computers(payload)

    assert changed is True
    assert payload["scope"]["computers"]["computer"] == []
    assert payload["scope"]["exclusions"]["computers"]["computer"] == []


@pytest.mark.asyncio
async def test_ensure_payload_categories_exist_skips_unauthorized_create() -> None:
    client = AsyncMock()

    list_response = MagicMock()
    list_response.status_code = 200
    list_response.json.return_value = {"categories": [{"name": "Existing"}]}

    create_response = MagicMock()
    create_response.status_code = 401

    client.get = AsyncMock(return_value=list_response)
    client.post = AsyncMock(return_value=create_response)

    payload = {"general": {"category": {"name": "Missing"}}}
    created, unauthorized = await _ensure_payload_categories_exist(
        client, "https://target.example", "token", payload
    )

    assert created == []
    assert unauthorized == ["Missing"]
