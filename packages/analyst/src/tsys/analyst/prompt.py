"""Render the institutional-desk brief from a live snapshot.

Pure: a snapshot and a spec in, strings out. No network, no clock beyond the
snapshot's own timestamp, so the exact bytes sent to the model can be asserted
in a test and stored in the journal.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from tsys.domain import MarketSnapshot

SYSTEM = """You are a professional institutional-level trader running an intraday book.

Act decisively. You are given live market data and must return a trade now. \
"Wait and watch" is not an available answer, and neither is hedging language.

Absolute constraints, which override any view you hold:
- Risk per trade is capped. Never propose a stop that risks more than the stated maximum.
- Never propose a stop that risks less than the stated minimum; it is not worth the slippage.
- Reward:risk must meet or exceed the stated minimum. Compute it and check before answering.
- Stop loss and target must sit on the correct sides of the current price for your direction.
- Lots must fall inside the stated range and must follow from the risk arithmetic, not intuition.

Your edge comes from combining two things and saying so explicitly:

1. Technical structure. Trend and market structure (BOS, CHoCH), supply and demand zones and
   order blocks, liquidity (equal highs and lows, stop hunts), support and resistance, volume
   and momentum where visible, candle behaviour, imbalances and fair value gaps, and a precise
   entry rationale.
2. Macro and geopolitics. Interest rates, inflation, currency strength, central bank posture,
   and live geopolitical conditions. Use the search tool for anything time-sensitive rather than
   recalling it. State the developments you expect and how smart money is positioned for them.

Be concrete about levels. Do not restate the input back as analysis."""


@dataclass(frozen=True, slots=True)
class BriefSpec:
    """The trading envelope the model must respect. Mirrors the risk mandate."""

    instrument: str
    timeframe: str
    capital: Decimal
    max_risk: Decimal
    min_risk: Decimal
    min_reward_ratio: Decimal
    lot_size: int
    min_lots: int
    max_lots: int
    tick_value: Decimal = Decimal(1)
    allow_overnight: bool = False


def _fmt(value: Decimal, places: str = "0.01") -> str:
    return str(value.quantize(Decimal(places)))


def render_bars(snapshot: MarketSnapshot, count: int = 40) -> str:
    """The recent tape as a compact table. Recent bars only: the model reasons
    about structure, and 200 rows crowd out the reasoning without adding any."""
    rows = ["time_utc            open      high      low       close     volume"]
    for b in snapshot.bars[-count:]:
        rows.append(
            f"{b.ts:%Y-%m-%d %H:%M}  {_fmt(b.open):>9} {_fmt(b.high):>9} "
            f"{_fmt(b.low):>9} {_fmt(b.close):>9} {_fmt(b.volume, '1'):>9}"
        )
    return "\n".join(rows)


def render_user_message(snapshot: MarketSnapshot, spec: BriefSpec) -> str:
    q = snapshot.quote
    bid_ask = (
        f"bid {_fmt(q.bid)} / ask {_fmt(q.ask)}"
        if q.bid is not None and q.ask is not None
        else "bid/ask unavailable"
    )
    highs = max(b.high for b in snapshot.bars)
    lows = min(b.low for b in snapshot.bars)
    overnight = "Holding overnight is allowed." if spec.allow_overnight else (
        "Intraday only. The position is squared off before the close."
    )

    return f"""TRADING ENVIRONMENT
Instrument: {spec.instrument}
Timeframe: {spec.timeframe}
Capital: Rs {_fmt(spec.capital, '1')} (fixed; profits and losses do not compound)
Tick value: Rs {_fmt(spec.tick_value)} per 1 point move
Lot size: {spec.lot_size} units per lot
Lots allowed: {spec.min_lots} to {spec.max_lots}
{overnight}

RISK MANDATE (hard limits)
Maximum risk per trade: Rs {_fmt(spec.max_risk)}
Minimum risk per trade: Rs {_fmt(spec.min_risk)}
Minimum reward:risk: {spec.min_reward_ratio}

LIVE MARKET DATA
Captured: {snapshot.captured_at:%Y-%m-%d %H:%M:%S} UTC
Last traded price: {_fmt(q.last)}
Quote: {bid_ask}
Session range across the {len(snapshot.bars)} bars supplied: {_fmt(lows)} to {_fmt(highs)}

RECENT PRICE ACTION ({spec.timeframe} bars, most recent last)
{render_bars(snapshot)}

Give your call on {spec.instrument} now, at the last traded price of {_fmt(q.last)}.
There is no entry price to choose: entry is immediate, at market, in the direction you pick.
Size the position from the risk arithmetic, and state the reward:risk you calculated."""
