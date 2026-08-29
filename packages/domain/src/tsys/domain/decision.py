"""The evaluator's output: trade or don't, and exactly why.

A Decision is the audit record. It carries the reasoning and the levels, so an
order can be reconstructed later from the decision alone.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum


class Side(StrEnum):
    LONG = "LONG"
    SHORT = "SHORT"


class Action(StrEnum):
    ENTER = "ENTER"
    NO_TRADE = "NO_TRADE"


class Abstain(StrEnum):
    """Why the evaluator declined. Never silently absent."""

    STALE_DATA = "stale_data"
    INSUFFICIENT_HISTORY = "insufficient_history"
    LOW_CONFIDENCE = "low_confidence"
    REWARD_RISK_TOO_LOW = "reward_risk_too_low"
    NO_STRUCTURE = "no_structure"
    OUTSIDE_SESSION = "outside_session"


@dataclass(frozen=True, slots=True)
class Levels:
    entry: Decimal
    stop_loss: Decimal
    target: Decimal

    def __post_init__(self) -> None:
        if self.entry <= 0 or self.stop_loss <= 0 or self.target <= 0:
            raise ValueError("levels must be positive")

    def risk_per_unit(self, side: Side) -> Decimal:
        d = self.entry - self.stop_loss if side is Side.LONG else self.stop_loss - self.entry
        if d <= 0:
            raise ValueError(f"stop_loss is on the wrong side of entry for {side}")
        return d

    def reward_per_unit(self, side: Side) -> Decimal:
        d = self.target - self.entry if side is Side.LONG else self.entry - self.target
        if d <= 0:
            raise ValueError(f"target is on the wrong side of entry for {side}")
        return d

    def reward_risk(self, side: Side) -> Decimal:
        return self.reward_per_unit(side) / self.risk_per_unit(side)


@dataclass(frozen=True, slots=True)
class Decision:
    action: Action
    index: str
    confidence: Decimal
    side: Side | None = None
    levels: Levels | None = None
    abstain_reason: Abstain | None = None
    reasons: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.action is Action.ENTER:
            if self.side is None or self.levels is None:
                raise ValueError("ENTER requires both side and levels")
        elif self.abstain_reason is None:
            raise ValueError("NO_TRADE requires an abstain_reason")

    @property
    def is_actionable(self) -> bool:
        return self.action is Action.ENTER
