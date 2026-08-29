"""What we observed in the market, and when.

Every type here is frozen and free of I/O so a snapshot can be serialised to a
fixture, replayed, and compared byte-for-byte in a test.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class Bar:
    ts: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal = Decimal(0)

    @property
    def range(self) -> Decimal:
        return self.high - self.low

    @property
    def body(self) -> Decimal:
        return abs(self.close - self.open)

    @property
    def is_bullish(self) -> bool:
        return self.close > self.open


@dataclass(frozen=True, slots=True)
class Quote:
    symbol: str
    last: Decimal
    ts: datetime
    bid: Decimal | None = None
    ask: Decimal | None = None

    @property
    def spread(self) -> Decimal | None:
        if self.bid is None or self.ask is None:
            return None
        return self.ask - self.bid


@dataclass(frozen=True, slots=True)
class MarketSnapshot:
    """Everything the evaluator is allowed to see. One index, one moment."""

    index: str
    timeframe: str
    quote: Quote
    bars: tuple[Bar, ...]
    captured_at: datetime
    source: str = "tradingview"

    def age_seconds(self, now: datetime | None = None) -> float:
        now = now or datetime.now(UTC)
        return (now - self.captured_at).total_seconds()

    def is_stale(self, max_age_seconds: float, now: datetime | None = None) -> bool:
        return self.age_seconds(now) > max_age_seconds

    def has_enough_history(self, min_bars: int) -> bool:
        return len(self.bars) >= min_bars

    @property
    def closes(self) -> tuple[Decimal, ...]:
        return tuple(b.close for b in self.bars)
