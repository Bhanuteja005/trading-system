from datetime import UTC, datetime, time

import pytest

from tsys.core import IST, is_market_open, past_square_off, session_date, to_ist


def _ist(y, m, d, hh, mm):
    return datetime(y, m, d, hh, mm, tzinfo=IST)


def test_naive_datetime_is_rejected():
    with pytest.raises(ValueError, match="naive"):
        to_ist(datetime(2026, 8, 29, 10, 0))


def test_market_hours_on_a_weekday():
    assert is_market_open(_ist(2026, 8, 28, 10, 0))       # Friday, open
    assert not is_market_open(_ist(2026, 8, 28, 9, 0))    # before 09:15
    assert not is_market_open(_ist(2026, 8, 28, 15, 45))  # after 15:30


def test_weekend_is_closed():
    assert not is_market_open(_ist(2026, 8, 29, 10, 0))   # Saturday


def test_square_off_boundary_is_inclusive():
    assert past_square_off(time(15, 20), _ist(2026, 8, 28, 15, 20))
    assert not past_square_off(time(15, 20), _ist(2026, 8, 28, 15, 19))


def test_session_date_uses_ist_not_utc():
    """22:00 UTC is already the next day in IST."""
    assert session_date(datetime(2026, 8, 28, 22, 0, tzinfo=UTC)).isoformat() == "2026-08-29"
