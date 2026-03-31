"""
Tests for the Zoomin Software documentation platform support in scraper.py.

Covers:
- _detect_zoomin_api_host: regex extraction and fallback
- _try_zoomin_content: known-host fallback when config is absent from HTML
- _fetch_candidate_page: SPA shell skipping for known Zoomin domains and
  link extraction from topic HTML
"""

from unittest.mock import AsyncMock, MagicMock
from urllib.parse import urlparse

import pytest

from app.services.scraper import (
    _ZOOMIN_KNOWN_API_HOSTS,
    _detect_zoomin_api_host,
    _try_zoomin_content,
)

# ---------------------------------------------------------------------------
# _detect_zoomin_api_host
# ---------------------------------------------------------------------------


def test_detect_zoomin_api_host_finds_embedded_config() -> None:
    html = 'window.__APP__={"api":{"host":"learn-be.jamf.com","version":2}}'
    assert _detect_zoomin_api_host(html) == "learn-be.jamf.com"


def test_detect_zoomin_api_host_whitespace_tolerant() -> None:
    html = '"api" : { "host" : "custom-be.example.com" }'
    assert _detect_zoomin_api_host(html) == "custom-be.example.com"


def test_detect_zoomin_api_host_returns_none_when_absent() -> None:
    html = "<html><body>Loading application...</body></html>"
    assert _detect_zoomin_api_host(html) is None


# ---------------------------------------------------------------------------
# _ZOOMIN_KNOWN_API_HOSTS mapping
# ---------------------------------------------------------------------------


def test_known_api_hosts_contains_learn_jamf_com() -> None:
    assert _ZOOMIN_KNOWN_API_HOSTS.get("learn.jamf.com") == "learn-be.jamf.com"


# ---------------------------------------------------------------------------
# _try_zoomin_content
# ---------------------------------------------------------------------------

_SPA_SHELL_HTML = (
    "<html><body>Jamf Learning Hub Loading application... "
    "Your web browser must have JavaScript enabled in order for this "
    "application to display correctly.</body></html>"
)

_MOCK_ARTICLE_HTML = "<article>" + ("X" * 200) + "</article>"

_ZOOMIN_TOPIC_URL = (
    "https://learn.jamf.com/en-US/bundle/jamf-pro-documentation-current"
    "/page/Smart_Groups.html"
)

_ZOOMIN_ROOT_URL = "https://learn.jamf.com/"


@pytest.mark.asyncio
async def test_try_zoomin_content_uses_known_host_fallback() -> None:
    """
    When the SPA shell contains no embedded API config, _try_zoomin_content
    should fall back to the known-host mapping and still retrieve content.
    """
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "topic_html": _MOCK_ARTICLE_HTML,
        "title": "Smart Groups",
    }

    mock_http = AsyncMock()
    mock_http.get = AsyncMock(return_value=mock_response)

    result = await _try_zoomin_content(mock_http, _ZOOMIN_TOPIC_URL, _SPA_SHELL_HTML)

    assert result is not None
    topic_html, title = result
    assert "X" * 200 in topic_html
    assert title == "Smart Groups"

    # Verify the correct API endpoint was called (fallback host)
    called_url = mock_http.get.call_args[0][0]
    assert urlparse(called_url).netloc == "learn-be.jamf.com"
    assert "jamf-pro-documentation-current" in called_url
    assert "Smart_Groups.html" in called_url


@pytest.mark.asyncio
async def test_try_zoomin_content_prefers_embedded_config_over_fallback() -> None:
    """
    When the page HTML contains an embedded API host, that host should be used
    instead of the fallback mapping.
    """
    html_with_config = (
        '<script>window.__CFG__={"api":{"host":"custom-be.example.com"}}</script>'
        "<body>Loading...</body>"
    )

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "topic_html": _MOCK_ARTICLE_HTML,
        "title": "Custom Page",
    }

    mock_http = AsyncMock()
    mock_http.get = AsyncMock(return_value=mock_response)

    result = await _try_zoomin_content(mock_http, _ZOOMIN_TOPIC_URL, html_with_config)

    assert result is not None
    called_url = mock_http.get.call_args[0][0]
    assert urlparse(called_url).netloc == "custom-be.example.com"


@pytest.mark.asyncio
async def test_try_zoomin_content_returns_none_for_non_page_url() -> None:
    """Root URLs do not match the Zoomin page pattern; must return None."""
    mock_http = AsyncMock()
    result = await _try_zoomin_content(mock_http, _ZOOMIN_ROOT_URL, _SPA_SHELL_HTML)
    assert result is None
    mock_http.get.assert_not_called()


@pytest.mark.asyncio
async def test_try_zoomin_content_returns_none_for_unknown_domain() -> None:
    """Unknown domains without an embedded config must return None."""
    url = "https://docs.example.com/bundle/mylib/page/topic.html"
    mock_http = AsyncMock()
    result = await _try_zoomin_content(mock_http, url, _SPA_SHELL_HTML)
    assert result is None
    mock_http.get.assert_not_called()


@pytest.mark.asyncio
async def test_try_zoomin_content_returns_none_on_api_error() -> None:
    """Network/HTTP errors from the Zoomin API should result in None."""
    mock_http = AsyncMock()
    mock_http.get = AsyncMock(side_effect=Exception("connection refused"))

    result = await _try_zoomin_content(mock_http, _ZOOMIN_TOPIC_URL, _SPA_SHELL_HTML)
    assert result is None


@pytest.mark.asyncio
async def test_try_zoomin_content_returns_none_on_non_200() -> None:
    mock_response = MagicMock()
    mock_response.status_code = 404

    mock_http = AsyncMock()
    mock_http.get = AsyncMock(return_value=mock_response)

    result = await _try_zoomin_content(mock_http, _ZOOMIN_TOPIC_URL, _SPA_SHELL_HTML)
    assert result is None


@pytest.mark.asyncio
async def test_try_zoomin_content_returns_none_for_short_topic_html() -> None:
    """topic_html with raw HTML shorter than 100 chars should be treated as empty."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"topic_html": "<p>short</p>", "title": "T"}

    mock_http = AsyncMock()
    mock_http.get = AsyncMock(return_value=mock_response)

    result = await _try_zoomin_content(mock_http, _ZOOMIN_TOPIC_URL, _SPA_SHELL_HTML)
    assert result is None


# ---------------------------------------------------------------------------
# _fetch_candidate_page integration: SPA shell skip + link extraction
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_candidate_page_skips_spa_shell_on_known_zoomin_domain() -> None:
    """
    A URL from learn.jamf.com that does not match the Zoomin page pattern
    (e.g. the root page) and yields only the SPA loading text must be skipped.
    """
    from app.services.scraper import _fetch_candidate_page

    spa_text = (
        "Jamf Learning Hub Loading application... "
        "Your web browser must have JavaScript enabled in order for this "
        "application to display correctly."
    )
    spa_html = f"<html><body>{spa_text}</body></html>"

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.url = _ZOOMIN_ROOT_URL
    mock_resp.headers = {"content-type": "text/html; charset=utf-8"}
    mock_resp.text = spa_html

    mock_http = AsyncMock()
    mock_http.get = AsyncMock(return_value=mock_resp)

    result = await _fetch_candidate_page(mock_http, _ZOOMIN_ROOT_URL, "learn.jamf.com")

    assert result["status"] == "skip"
    assert "Zoomin" in result["reason"]


@pytest.mark.asyncio
async def test_fetch_candidate_page_uses_topic_html_for_links() -> None:
    """
    When a Zoomin topic page is successfully fetched via the API, the links
    returned should be extracted from the topic HTML (not the SPA shell).
    """
    from app.services.scraper import _fetch_candidate_page

    topic_html = (
        "<article>"
        '<a href="/en-US/bundle/jamf-pro-documentation-current/page/Policies.html">'
        "Policies</a>"
        + ("Content " * 50)
        + "</article>"
    )
    api_json = {"topic_html": topic_html, "title": "Smart Groups"}

    # First call: return the SPA shell for the page URL
    spa_resp = MagicMock()
    spa_resp.status_code = 200
    spa_resp.url = _ZOOMIN_TOPIC_URL
    spa_resp.headers = {"content-type": "text/html; charset=utf-8"}
    spa_resp.text = _SPA_SHELL_HTML

    # Second call: return the Zoomin API JSON
    api_resp = MagicMock()
    api_resp.status_code = 200
    api_resp.json = MagicMock(return_value=api_json)

    mock_http = AsyncMock()
    mock_http.get = AsyncMock(side_effect=[spa_resp, api_resp])

    result = await _fetch_candidate_page(mock_http, _ZOOMIN_TOPIC_URL, "learn.jamf.com")

    assert result["status"] == "ok"
    assert result["zoomin_title"] == "Smart Groups"
    # The Policies link from topic_html must appear in the discovered links
    assert any("Policies.html" in link for link in result["links"])
