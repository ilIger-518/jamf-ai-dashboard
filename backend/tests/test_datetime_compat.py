from datetime import UTC, datetime

from app.utils.datetime_compat import UTC as UTC_COMPAT


def test_utc_alias_matches_timezone_utc() -> None:
    assert UTC_COMPAT == UTC
    assert datetime.now(UTC_COMPAT).tzinfo == UTC
