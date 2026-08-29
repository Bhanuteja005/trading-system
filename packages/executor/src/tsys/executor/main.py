"""Executor entry point.

    tsys-executor --index NIFTY --once
    tsys-executor --index NIFTY --index SENSEX --interval 300

Dry-run is the default and is stated on every run. Live requires TSYS_MODE=live,
TSYS_LIVE_CONFIRMED=true, and --yes-live typed at the command line.
"""

from __future__ import annotations

import argparse
import sys
import time

from tsys.broker import BrokerClient, IdempotencyLedger
from tsys.config import Mode, settings
from tsys.core import clock, configure, get_logger
from tsys.journal import Journal
from tsys.tv import TradingViewClient

from .pipeline import Pipeline
from .risk import PortfolioState

log = get_logger("tsys.executor")


def build_pipeline() -> Pipeline:
    return Pipeline(
        settings=settings,
        market=TradingViewClient(settings.tradingview),
        broker=BrokerClient(
            settings.broker,
            mode=settings.risk.mode,
            kill_switch=settings.risk.kill_switch_file,
            ledger=IdempotencyLedger(settings.base.data_dir / "order_ledger.json"),
        ),
        journal=Journal(settings.base.data_dir / "journal"),
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Signal-to-order executor.")
    p.add_argument("--index", action="append", required=True,
                   help="repeatable, e.g. --index NIFTY --index SENSEX")
    p.add_argument("--timeframe", default="5")
    p.add_argument("--interval", type=int, default=300, help="seconds between scans")
    p.add_argument("--once", action="store_true", help="run a single cycle and exit")
    p.add_argument("--yes-live", action="store_true",
                   help="third and final confirmation required for live trading")
    args = p.parse_args(argv)

    configure(settings.base.log_level)
    try:
        settings.assert_startup_safe()
    except RuntimeError as e:
        print(f"REFUSING TO START: {e}", file=sys.stderr)
        return 2

    if settings.risk.is_live and not args.yes_live:
        print(
            "REFUSING TO START: mode is live but --yes-live was not passed.\n"
            "Live trading needs all three: TSYS_MODE=live, TSYS_LIVE_CONFIRMED=true, "
            "and --yes-live on the command line.",
            file=sys.stderr,
        )
        return 2

    banner = "LIVE - REAL MONEY" if settings.risk.is_live else settings.risk.mode.value.upper()
    print(f"executor starting | mode={banner} | indices={','.join(args.index)}")
    print(f"kill switch: create {settings.risk.kill_switch_file} to halt all orders")

    pipeline = build_pipeline()
    state = PortfolioState()

    while True:
        for index in args.index:
            result = pipeline.run_once(index, state=state, timeframe=args.timeframe)
            if result.error:
                print(f"  {index}: no decision ({result.error})")
            elif result.rejected_by:
                print(f"  {index}: rejected - {result.rejected_by}")
            elif result.decision and not result.decision.is_actionable:
                print(f"  {index}: no trade - {result.decision.abstain_reason} "
                      f"(confidence {result.decision.confidence:.2f})")
            elif result.placed:
                print(f"  {index}: ORDER {result.order.broker_order_id} "
                      f"{result.decision.side} @ {result.decision.levels.entry}")

        if args.once:
            return 0
        if clock.past_square_off(settings.risk.square_off_time):
            print("past square-off; exiting")
            return 0
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
