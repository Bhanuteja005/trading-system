"""index name -> snapshot -> decision -> risk -> order -> journal.

The single path from an index name to an order. Every stage records its verdict,
and any stage may stop the cycle; nothing downstream runs if an earlier stage
said no.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime

from tsys.broker import BrokerClient
from tsys.config import LOT_SIZES, Settings
from tsys.core import (
    DataUnavailable,
    KillSwitchEngaged,
    StaleData,
    client_order_id,
    clock,
    get_logger,
    log_event,
)
from tsys.domain import (
    Action,
    Decision,
    OrderAction,
    OrderRequest,
    OrderResult,
    Side,
)
from tsys.journal import Journal, JournalEntry
from tsys.tv import TradingViewClient

from . import risk as risk_rules
from .evaluate import EvalParams, evaluate
from .sizing import size_position

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class CycleResult:
    cycle_id: str
    index: str
    decision: Decision | None
    order: OrderResult | None
    rejected_by: str | None
    error: str | None = None

    @property
    def placed(self) -> bool:
        return self.order is not None and self.order.ok


class Pipeline:
    def __init__(
        self,
        *,
        settings: Settings,
        market: TradingViewClient,
        broker: BrokerClient,
        journal: Journal,
        params: EvalParams | None = None,
    ) -> None:
        self._s = settings
        self._market = market
        self._broker = broker
        self._journal = journal
        self._params = params or EvalParams(
            min_confidence=settings.risk.min_confidence,
            min_reward_ratio=settings.risk.min_reward_ratio,
            min_bars=settings.tradingview.min_bars,
        )

    def run_once(
        self,
        index: str,
        *,
        state: risk_rules.PortfolioState,
        timeframe: str = "5",
        now: datetime | None = None,
    ) -> CycleResult:
        cycle_id = uuid.uuid4().hex[:12]
        now = now or clock.now_ist()
        index = index.upper()

        # 1. Data. A failure here ends the cycle; we never guess a price.
        try:
            snapshot = self._market.snapshot(index, timeframe=timeframe)
        except (DataUnavailable, StaleData) as e:
            log_event(log, logging.WARNING, "cycle.no_data", cycle_id=cycle_id,
                      index=index, error=str(e))
            return CycleResult(cycle_id, index, None, None, None, error=str(e))

        # 2. Evaluate. Pure: same snapshot, same verdict, every time.
        decision = evaluate(snapshot, self._params)

        if decision.action is not Action.ENTER:
            self._record(cycle_id, index, decision, snapshot, None, None)
            return CycleResult(cycle_id, index, decision, None, None)

        # 3. Size from risk, then check the portfolio.
        rejection = self._size_and_check(decision, index, state, now)
        if isinstance(rejection, str):
            self._record(cycle_id, index, decision, snapshot, None, rejection)
            log_event(log, logging.INFO, "cycle.rejected", cycle_id=cycle_id,
                      index=index, reason=rejection)
            return CycleResult(cycle_id, index, decision, None, rejection)

        sizing, lot_size, exchange = rejection

        # 4. Place. Idempotent by construction.
        assert decision.levels is not None and decision.side is not None
        coid = client_order_id(
            index=index, side=decision.side.value,
            entry=decision.levels.entry, stop_loss=decision.levels.stop_loss,
            target=decision.levels.target, session=clock.session_date(now),
        )
        request = OrderRequest(
            client_order_id=coid,
            symbol=index,
            exchange=exchange,
            action=OrderAction.BUY if decision.side is Side.LONG else OrderAction.SELL,
            quantity=sizing.quantity,
        )
        try:
            order = self._broker.place_order(request)
        except KillSwitchEngaged as e:
            self._record(cycle_id, index, decision, snapshot, None, str(e))
            return CycleResult(cycle_id, index, decision, None, str(e))
        except Exception as e:  # noqa: BLE001 - the cycle must not take the loop down
            log_event(log, logging.ERROR, "cycle.order_failed", cycle_id=cycle_id,
                      index=index, error=str(e))
            self._record(cycle_id, index, decision, snapshot, None, f"order error: {e}")
            return CycleResult(cycle_id, index, decision, None, None, error=str(e))

        self._record(cycle_id, index, decision, snapshot, order, None)
        return CycleResult(cycle_id, index, decision, order, None)

    # ---- internals ----------------------------------------------------------

    def _size_and_check(self, decision, index, state, now):
        lot_size, exchange = LOT_SIZES.get(index, (0, ""))
        if lot_size <= 0:
            return f"unknown index {index}; add it to LOT_SIZES"

        sized = size_position(
            levels=decision.levels, side=decision.side, lot_size=lot_size,
            max_risk_rupees=self._s.risk.max_risk_rupees,
            min_risk_rupees=self._s.risk.min_risk_rupees,
        )
        if isinstance(sized, str):
            return sized

        veto = risk_rules.check(
            settings=self._s.risk, state=state,
            new_risk=sized.risk_rupees, index=index, now=now,
        )
        if veto:
            return veto
        return sized, lot_size, exchange

    def _record(self, cycle_id, index, decision, snapshot, order, rejected_by) -> None:
        self._journal.append(
            JournalEntry(
                cycle_id=cycle_id, index=index, mode=self._s.risk.mode.value,
                decision=decision, snapshot=snapshot, order=order, rejected_by=rejected_by,
            )
        )
