from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from tsys.domain import Bar, MarketSnapshot, Quote


def make_bars(closes: list[str], *, start: datetime | None = None, spread: str = "5") -> tuple[Bar, ...]:
    t0 = start or datetime(2026, 8, 28, 4, 0, tzinfo=UTC)
    s = Decimal(spread)
    out = []
    for i, c in enumerate(closes):
        close = Decimal(c)
        open_ = Decimal(closes[i - 1]) if i else close
        out.append(
            Bar(ts=t0 + timedelta(minutes=5 * i), open=open_,
                high=max(open_, close) + s, low=min(open_, close) - s,
                close=close, volume=Decimal(1000))
        )
    return tuple(out)


def make_snapshot(closes: list[str], *, index: str = "NIFTY", last: str | None = None) -> MarketSnapshot:
    bars = make_bars(closes)
    now = datetime.now(UTC)
    return MarketSnapshot(
        index=index, timeframe="5",
        quote=Quote(symbol=index, last=Decimal(last or closes[-1]), ts=now),
        bars=bars, captured_at=now,
    )


@pytest.fixture
def uptrend() -> MarketSnapshot:
    """A clean, accelerating uptrend that breaks the prior swing high."""
    closes = [str(100 + i * 0.4) for i in range(60)] + [str(124 + i * 3) for i in range(20)]
    return make_snapshot(closes, last=str(124 + 19 * 3 + 4))


@pytest.fixture
def chop() -> MarketSnapshot:
    """Sideways noise: no trend, no break of structure."""
    closes = [str(100 + (1 if i % 2 else -1) * 0.3) for i in range(80)]
    return make_snapshot(closes)
