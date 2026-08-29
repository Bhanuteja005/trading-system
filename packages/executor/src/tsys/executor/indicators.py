"""Indicators over Decimal bars. Pure functions, no state, no I/O."""

from __future__ import annotations

from decimal import Decimal

from tsys.domain import Bar

TWO = Decimal(2)


def ema(values: tuple[Decimal, ...], period: int) -> Decimal | None:
    if len(values) < period:
        return None
    k = TWO / Decimal(period + 1)
    seed = sum(values[:period], Decimal(0)) / Decimal(period)
    out = seed
    for v in values[period:]:
        out = (v - out) * k + out
    return out


def atr(bars: tuple[Bar, ...], period: int = 14) -> Decimal | None:
    """Wilder's true range average. The volatility unit stops are measured in."""
    if len(bars) < period + 1:
        return None
    trs: list[Decimal] = []
    for prev, cur in zip(bars[:-1], bars[1:], strict=True):
        trs.append(max(cur.high - cur.low, abs(cur.high - prev.close), abs(cur.low - prev.close)))
    window = trs[-period:]
    return sum(window, Decimal(0)) / Decimal(period)


def swing_high(bars: tuple[Bar, ...], lookback: int) -> Decimal | None:
    return max((b.high for b in bars[-lookback:]), default=None)


def swing_low(bars: tuple[Bar, ...], lookback: int) -> Decimal | None:
    return min((b.low for b in bars[-lookback:]), default=None)


def rsi(values: tuple[Decimal, ...], period: int = 14) -> Decimal | None:
    if len(values) < period + 1:
        return None
    gains, losses = Decimal(0), Decimal(0)
    for a, b in zip(values[-period - 1 : -1], values[-period:], strict=True):
        delta = b - a
        if delta >= 0:
            gains += delta
        else:
            losses -= delta
    if losses == 0:
        return Decimal(100)
    rs = (gains / Decimal(period)) / (losses / Decimal(period))
    return Decimal(100) - (Decimal(100) / (Decimal(1) + rs))
