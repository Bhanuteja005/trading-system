"""Portfolio-level limits, checked after sizing and before any order.

Everything here answers one question: given what is already open and what has
already happened today, may this trade be added? A rejection is final.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from tsys.config import RiskSettings
from tsys.core import clock
from tsys.domain import Position


@dataclass(frozen=True, slots=True)
class PortfolioState:
    open_positions: tuple[Position, ...] = ()
    realised_pnl_today: Decimal = Decimal(0)

    @property
    def open_risk(self) -> Decimal:
        return sum((p.risk_rupees for p in self.open_positions), Decimal(0))


def check(
    *,
    settings: RiskSettings,
    state: PortfolioState,
    new_risk: Decimal,
    index: str,
    now: datetime | None = None,
) -> str | None:
    """Return a rejection reason, or None if the trade may proceed."""
    now = now or clock.now_ist()

    if settings.kill_switch_file.exists():
        return f"kill switch engaged ({settings.kill_switch_file})"

    if clock.past_square_off(settings.no_new_entries_after, now):
        return f"past {settings.no_new_entries_after:%H:%M} — no new entries"

    if not clock.is_market_open(now):
        return "market is closed"

    if state.realised_pnl_today <= -settings.daily_loss_limit:
        return (
            f"daily loss limit hit ({state.realised_pnl_today:.2f} "
            f"vs -{settings.daily_loss_limit:.2f})"
        )

    if state.realised_pnl_today >= settings.daily_profit_target:
        return (
            f"daily profit target reached ({state.realised_pnl_today:.2f}); "
            "stopping while ahead"
        )

    if len(state.open_positions) >= settings.max_open_positions:
        return (
            f"already holding {len(state.open_positions)} positions "
            f"(max {settings.max_open_positions})"
        )

    if any(p.symbol.startswith(index) for p in state.open_positions):
        return f"already exposed to {index}"

    ceiling = settings.capital * settings.max_total_risk_pct
    if state.open_risk + new_risk > ceiling:
        return (
            f"total risk {state.open_risk + new_risk:.2f} would exceed "
            f"the {ceiling:.2f} portfolio ceiling"
        )

    if new_risk > settings.max_risk_rupees:
        return f"trade risk {new_risk:.2f} above per-trade cap {settings.max_risk_rupees:.2f}"

    return None
