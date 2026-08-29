"""Did the call work?

Scored against the bars that came after it, in order, so the answer does not
depend on which level looks closer in hindsight. Pure functions: bars in,
verdict out.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from tsys.domain import Bar, Levels, Side


class Outcome(StrEnum):
    TARGET = "target"
    """Target reached before the stop."""

    STOP = "stop"
    """Stop reached before the target."""

    OPEN = "open"
    """Neither level reached in the bars supplied. Not yet a result."""

    AMBIGUOUS = "ambiguous"
    """A single bar spans both levels, so intrabar order is unknowable at this
    resolution. Counted as a loss, because assuming the good fill first is how
    a backtest flatters itself."""


@dataclass(frozen=True, slots=True)
class ScoreCard:
    outcome: Outcome
    resolved_at: datetime | None
    bars_to_resolve: int
    move_points: Decimal
    """Signed, in the direction of the trade. Positive means it went your way."""

    r_multiple: Decimal
    """Result in units of risk. +2.0 means a 1:2 target paid."""

    @property
    def correct(self) -> bool:
        return self.outcome is Outcome.TARGET

    @property
    def resolved(self) -> bool:
        return self.outcome in (Outcome.TARGET, Outcome.STOP, Outcome.AMBIGUOUS)


def score_call(
    *, levels: Levels, side: Side, subsequent: tuple[Bar, ...]
) -> ScoreCard:
    """Walk forward bar by bar and report the first level touched."""
    risk = levels.risk_per_unit(side)
    reward = levels.reward_per_unit(side)

    for i, bar in enumerate(subsequent, start=1):
        if side is Side.LONG:
            hit_target = bar.high >= levels.target
            hit_stop = bar.low <= levels.stop_loss
        else:
            hit_target = bar.low <= levels.target
            hit_stop = bar.high >= levels.stop_loss

        if hit_target and hit_stop:
            return ScoreCard(Outcome.AMBIGUOUS, bar.ts, i, -risk, Decimal(-1))
        if hit_target:
            return ScoreCard(Outcome.TARGET, bar.ts, i, reward, reward / risk)
        if hit_stop:
            return ScoreCard(Outcome.STOP, bar.ts, i, -risk, Decimal(-1))

    if not subsequent:
        return ScoreCard(Outcome.OPEN, None, 0, Decimal(0), Decimal(0))

    last = subsequent[-1].close
    move = last - levels.entry if side is Side.LONG else levels.entry - last
    return ScoreCard(Outcome.OPEN, subsequent[-1].ts, len(subsequent), move, move / risk)


@dataclass(frozen=True, slots=True)
class Summary:
    total: int
    resolved: int
    wins: int
    losses: int
    open: int
    hit_rate: Decimal
    """Wins over resolved calls. Undefined (zero) until something resolves."""

    expectancy_r: Decimal
    """Mean R across resolved calls. The number that decides whether the edge
    is real: a 40% hit rate at 1:2 still compounds, an 80% hit rate at 1:0.2
    does not."""


def summarise(cards: list[ScoreCard]) -> Summary:
    resolved = [c for c in cards if c.resolved]
    wins = [c for c in resolved if c.correct]
    hit_rate = Decimal(len(wins)) / Decimal(len(resolved)) if resolved else Decimal(0)
    expectancy = (
        sum((c.r_multiple for c in resolved), Decimal(0)) / Decimal(len(resolved))
        if resolved
        else Decimal(0)
    )
    return Summary(
        total=len(cards),
        resolved=len(resolved),
        wins=len(wins),
        losses=len(resolved) - len(wins),
        open=len(cards) - len(resolved),
        hit_rate=hit_rate.quantize(Decimal("0.001")),
        expectancy_r=expectancy.quantize(Decimal("0.001")),
    )
