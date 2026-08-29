"""Time, always explicit about its zone.

Indian markets run on IST. Naive datetimes are a bug, so nothing here returns one.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

MARKET_OPEN = time(9, 15)
MARKET_CLOSE = time(15, 30)


def now_ist() -> datetime:
    return datetime.now(IST)


def now_utc() -> datetime:
    return datetime.now(UTC)


def to_ist(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        raise ValueError("refusing to localise a naive datetime; attach a tzinfo first")
    return dt.astimezone(IST)


def session_date(dt: datetime | None = None) -> date:
    """The trading date an instant belongs to, in IST."""
    return (dt.astimezone(IST) if dt else now_ist()).date()


def is_market_open(dt: datetime | None = None) -> bool:
    d = dt.astimezone(IST) if dt else now_ist()
    if d.weekday() >= 5:  # Sat/Sun. Exchange holidays are not modelled here.
        return False
    return MARKET_OPEN <= d.time() <= MARKET_CLOSE


def past_square_off(square_off: time, dt: datetime | None = None) -> bool:
    d = dt.astimezone(IST) if dt else now_ist()
    return d.time() >= square_off
