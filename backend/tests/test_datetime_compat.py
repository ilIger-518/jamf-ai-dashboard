from datetime import datetime, timezone

from app.utils.datetime_compat import UTC


def test_utc_alias_matches_timezone_utc() -> None:
    assert UTC == timezone.utc
    assert datetime.now(UTC).tzinfo == timezone.utc
