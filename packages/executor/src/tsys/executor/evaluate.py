"""The decision boundary. One pure function, no network, no clock, no config file.

evaluate() takes a snapshot and an explicit EvalParams and returns a Decision.
Given the same inputs it always returns the same output, so it can be replayed
against recorded fixtures and diffed.

Stops are derived from ATR, never from a fixed number of points: a fixed stop is
too tight in a volatile session and too loose in a quiet one. The target is then
placed at exactly min_reward_ratio times the risk, which makes the RR floor true
by construction rather than something to check afterwards.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from tsys.domain import Abstain, Action, Decision, Levels, MarketSnapshot, Side

from .indicators import atr, ema, rsi, swing_high, swing_low

TICK = Decimal("0.05")


@dataclass(frozen=True, slots=True)
class EvalParams:
    """Every knob the evaluator has. Passed in, never read from the environment."""

    min_confidence: Decimal = Decimal("0.65")
    min_reward_ratio: Decimal = Decimal("2.0")
    atr_period: int = 14
    atr_stop_multiple: Decimal = Decimal("1.5")
    ema_fast: int = 9
    ema_slow: int = 21
    structure_lookback: int = 20
    rsi_period: int = 14
    min_bars: int = 50


def _round_tick(value: Decimal) -> Decimal:
    return (value / TICK).quantize(Decimal(1), rounding=ROUND_HALF_UP) * TICK


def _no(index: str, reason: Abstain, confidence: Decimal, *notes: str) -> Decision:
    return Decision(
        action=Action.NO_TRADE, index=index, confidence=confidence,
        abstain_reason=reason, reasons=notes,
    )


def evaluate(snapshot: MarketSnapshot, params: EvalParams) -> Decision:
    index, bars = snapshot.index, snapshot.bars

    if not snapshot.has_enough_history(params.min_bars):
        return _no(index, Abstain.INSUFFICIENT_HISTORY, Decimal(0),
                   f"{len(bars)} bars, need {params.min_bars}")

    closes = snapshot.closes
    fast = ema(closes, params.ema_fast)
    slow = ema(closes, params.ema_slow)
    volatility = atr(bars, params.atr_period)
    momentum = rsi(closes, params.rsi_period)
    hi = swing_high(bars[:-1], params.structure_lookback)
    lo = swing_low(bars[:-1], params.structure_lookback)

    if fast is None or slow is None or volatility is None or momentum is None:
        return _no(index, Abstain.INSUFFICIENT_HISTORY, Decimal(0), "indicator warmup incomplete")
    if volatility <= 0 or hi is None or lo is None:
        return _no(index, Abstain.NO_STRUCTURE, Decimal(0), "no measurable range")

    last = snapshot.quote.last
    reasons: list[str] = []

    # --- directional evidence, each worth an explicit weight ------------------
    trend_up = fast > slow
    score = Decimal(0)
    side = Side.LONG if trend_up else Side.SHORT
    reasons.append(f"EMA{params.ema_fast} {'>' if trend_up else '<'} EMA{params.ema_slow}")
    score += Decimal("0.30")

    # Break of structure: price beyond the prior swing in the trend direction.
    broke = last > hi if trend_up else last < lo
    if broke:
        score += Decimal("0.25")
        reasons.append(f"BOS beyond {'swing high' if trend_up else 'swing low'}")

    # Momentum agreeing with the trend, without being exhausted.
    if trend_up and Decimal(50) < momentum < Decimal(78):
        score += Decimal("0.20")
        reasons.append(f"RSI {momentum:.1f} supports long")
    elif not trend_up and Decimal(22) < momentum < Decimal(50):
        score += Decimal("0.20")
        reasons.append(f"RSI {momentum:.1f} supports short")
    elif momentum >= Decimal(78) or momentum <= Decimal(22):
        score -= Decimal("0.15")
        reasons.append(f"RSI {momentum:.1f} exhausted")

    # Separation between the EMAs, normalised by ATR, as a conviction proxy.
    separation = abs(fast - slow) / volatility
    if separation > Decimal("0.5"):
        score += Decimal("0.15")
        reasons.append(f"EMA separation {separation:.2f} ATR")

    # Closing in the direction of the trade on the last bar.
    if bars[-1].is_bullish == trend_up:
        score += Decimal("0.10")
        reasons.append("last bar closed with the trend")

    confidence = max(Decimal(0), min(Decimal(1), score))

    if confidence < params.min_confidence:
        return _no(index, Abstain.LOW_CONFIDENCE, confidence,
                   f"score {confidence:.2f} below {params.min_confidence}", *reasons)

    # --- levels, derived from volatility --------------------------------------
    entry = _round_tick(last)
    stop_distance = volatility * params.atr_stop_multiple
    if stop_distance <= 0:
        return _no(index, Abstain.NO_STRUCTURE, confidence, "non-positive stop distance")

    if side is Side.LONG:
        stop = _round_tick(entry - stop_distance)
        target = _round_tick(entry + stop_distance * params.min_reward_ratio)
    else:
        stop = _round_tick(entry + stop_distance)
        target = _round_tick(entry - stop_distance * params.min_reward_ratio)

    if stop <= 0 or target <= 0:
        return _no(index, Abstain.NO_STRUCTURE, confidence, "levels collapsed to zero")

    levels = Levels(entry=entry, stop_loss=stop, target=target)
    achieved = levels.reward_risk(side)
    if achieved < params.min_reward_ratio:
        # Tick rounding can shave the ratio; refuse rather than take a worse trade.
        return _no(index, Abstain.REWARD_RISK_TOO_LOW, confidence,
                   f"RR {achieved:.2f} below {params.min_reward_ratio}")

    reasons.append(f"stop {params.atr_stop_multiple}x ATR({volatility:.2f}) = {stop_distance:.2f}")
    reasons.append(f"RR {achieved:.2f}")
    return Decision(
        action=Action.ENTER, index=index, confidence=confidence,
        side=side, levels=levels, reasons=tuple(reasons),
    )
