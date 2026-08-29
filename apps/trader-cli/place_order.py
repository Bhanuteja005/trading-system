"""Place a single order by hand, through the same guarded path the executor uses.

    python apps/trader-cli/place_order.py BUY NIFTY02JUN2624000PE NFO 300 MIS

Honours TSYS_MODE: in dry_run (the default) it prints the order and sends
nothing. The kill switch and the idempotency ledger apply here too — this is a
front end onto BrokerClient, not a second way into the broker.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from decimal import Decimal

from tsys.broker import BrokerClient, IdempotencyLedger
from tsys.config import settings
from tsys.core import KillSwitchEngaged, TsysError, client_order_id, configure
from tsys.domain import OrderAction, OrderRequest, Product


def main() -> int:
    p = argparse.ArgumentParser(description="Place one order via OpenAlgo.")
    p.add_argument("action", choices=["BUY", "SELL"], type=str.upper)
    p.add_argument("symbol")
    p.add_argument("exchange", type=str.upper)
    p.add_argument("quantity", type=int)
    p.add_argument("product", nargs="?", default="MIS", choices=["MIS", "NRML"], type=str.upper)
    p.add_argument("--ref", default="manual", help="disambiguates two identical manual orders")
    args = p.parse_args()

    configure(settings.base.log_level)
    settings.assert_startup_safe()

    coid = client_order_id(
        index=args.symbol, side=args.action, entry=Decimal(1),
        stop_loss=Decimal(1), target=Decimal(1),
        session=date.today(), sequence=abs(hash(args.ref)) % 10_000,
    )
    req = OrderRequest(
        client_order_id=coid, symbol=args.symbol, exchange=args.exchange,
        action=OrderAction(args.action), quantity=args.quantity,
        product=Product(args.product),
    )

    client = BrokerClient(
        settings.broker,
        mode=settings.risk.mode,
        kill_switch=settings.risk.kill_switch_file,
        ledger=IdempotencyLedger(settings.base.data_dir / "order_ledger.json"),
    )

    print(f"mode={settings.risk.mode.value}  contacts broker={client.will_contact_broker}")
    try:
        res = client.place_order(req)
    except KillSwitchEngaged as e:
        print(f"BLOCKED: {e}", file=sys.stderr)
        return 2
    except TsysError as e:
        print(f"FAILED: {e}", file=sys.stderr)
        return 1

    if res.deduplicated:
        print(f"DUPLICATE suppressed — existing order {res.broker_order_id}")
    elif res.ok:
        print(f"OK  {args.action} {args.quantity} x {args.symbol} -> {res.broker_order_id}")
    else:
        print(f"REJECTED: {res.error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
