"""Risk limits and the trading-mode gate.

Defaults come from CLAUDE.md's risk mandate. Every number here is a limit, not
a suggestion: the risk manager rejects anything that breaches one.
"""

from __future__ import annotations

from datetime import time
from decimal import Decimal
from pathlib import Path

from pydantic import Field, field_validator

from .base import REPO_ROOT, Mode, _Base


class RiskSettings(_Base):
    # --- Mode gate -----------------------------------------------------------
    mode: Mode = Field(default=Mode.DRY_RUN, alias="TSYS_MODE")
    """Never defaults to live. Promotion to LIVE also requires live_confirmed."""

    live_confirmed: bool = Field(default=False, alias="TSYS_LIVE_CONFIRMED")
    """Second, per-session switch. LIVE without this is refused at startup."""

    kill_switch_file: Path = Field(default=REPO_ROOT / "data" / "KILL", alias="TSYS_KILL_FILE")
    """If this file exists, every order path refuses. Checked before each placement."""

    # --- Capital and sizing --------------------------------------------------
    capital: Decimal = Field(default=Decimal("300000"), alias="TSYS_CAPITAL")
    max_risk_pct: Decimal = Field(default=Decimal("0.01"), alias="TSYS_MAX_RISK_PCT")
    min_risk_pct: Decimal = Field(default=Decimal("0.0025"), alias="TSYS_MIN_RISK_PCT")
    min_reward_ratio: Decimal = Field(default=Decimal("2.0"), alias="TSYS_MIN_RR")

    # --- Exposure ------------------------------------------------------------
    max_open_positions: int = Field(default=2, alias="TSYS_MAX_OPEN_POSITIONS")
    max_total_risk_pct: Decimal = Field(default=Decimal("0.02"), alias="TSYS_MAX_TOTAL_RISK_PCT")
    """Ceiling on summed open risk, so N positions cannot stack into a blow-up."""

    daily_loss_limit: Decimal = Field(default=Decimal("6000"), alias="TSYS_DAILY_LOSS_LIMIT")
    daily_profit_target: Decimal = Field(default=Decimal("9000"), alias="TSYS_DAILY_PROFIT_TARGET")
    """Both halt new entries for the day once breached. Carried over from auto_bot.py."""

    # --- Decision threshold --------------------------------------------------
    min_confidence: Decimal = Field(default=Decimal("0.65"), alias="TSYS_MIN_CONFIDENCE")
    """Below this the evaluator returns NO_TRADE. The decision boundary."""

    # --- Session -------------------------------------------------------------
    square_off_time: time = Field(default=time(15, 20), alias="TSYS_SQUARE_OFF_TIME")
    no_new_entries_after: time = Field(default=time(15, 0), alias="TSYS_NO_ENTRY_AFTER")

    @field_validator("max_risk_pct", "min_risk_pct", "max_total_risk_pct")
    @classmethod
    def _sane_fraction(cls, v: Decimal) -> Decimal:
        if not (Decimal("0") < v <= Decimal("0.1")):
            raise ValueError(f"risk fraction {v} outside (0, 0.10]; refusing to run")
        return v

    @property
    def max_risk_rupees(self) -> Decimal:
        return (self.capital * self.max_risk_pct).quantize(Decimal("0.01"))

    @property
    def min_risk_rupees(self) -> Decimal:
        return (self.capital * self.min_risk_pct).quantize(Decimal("0.01"))

    @property
    def is_live(self) -> bool:
        return self.mode is Mode.LIVE and self.live_confirmed


LOT_SIZES: dict[str, tuple[int, str]] = {
    "NIFTY": (75, "NFO"),
    "BANKNIFTY": (35, "NFO"),
    "SENSEX": (10, "BFO"),
    "GOLDM": (10, "MCX"),
}
"""index -> (contracts per lot, exchange). From CLAUDE.md."""
