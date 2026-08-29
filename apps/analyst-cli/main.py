"""Ask Claude for a call on an index, paper-trade it, and score it later.

    python apps/analyst-cli/main.py analyze NIFTY
    python apps/analyst-cli/main.py analyze SENSEX --timeframe 15
    python apps/analyst-cli/main.py score
    python apps/analyst-cli/main.py accuracy

analyze fetches live data through the TradingView MCP CLI, renders the
institutional brief, asks Claude Opus 5, validates the answer against the risk
mandate, and records it as a paper trade. It never places a broker order: this
path is paper-only by construction, whatever TSYS_MODE says.
"""

from __future__ import annotations

import argparse
import sys
from decimal import Decimal

from tsys.analyst import (
    Analyst,
    AnalystRejected,
    BriefSpec,
    CallStore,
    Outcome,
    score_call,
    summarise,
)
from tsys.config import LOT_SIZES, settings
from tsys.core import DataUnavailable, StaleData, clock, configure, get_logger
from tsys.domain import Levels, Side
from tsys.tv import TradingViewClient

log = get_logger("tsys.analyst-cli")

BAR = "-" * 74


def _store() -> CallStore:
    return CallStore(settings.base.data_dir / "analyst_calls.jsonl")


def _spec(index: str, timeframe: str) -> BriefSpec:
    lot_size, _ = LOT_SIZES.get(index, (1, ""))
    return BriefSpec(
        instrument=index,
        timeframe=f"{timeframe}-minute",
        capital=settings.risk.capital,
        max_risk=settings.risk.max_risk_rupees,
        min_risk=settings.risk.min_risk_rupees,
        min_reward_ratio=settings.risk.min_reward_ratio,
        lot_size=lot_size,
        min_lots=1,
        max_lots=12,
    )


def cmd_analyze(args: argparse.Namespace) -> int:
    index = args.index.upper()
    if index not in LOT_SIZES:
        print(f"unknown index {index}. known: {', '.join(sorted(LOT_SIZES))}", file=sys.stderr)
        return 2

    market = TradingViewClient(settings.tradingview)
    if not market.health():
        print(
            "TradingView is not reachable over CDP.\n"
            f"  Launch it with CDP enabled on port {settings.tradingview.cdp_port}, "
            "then retry.\n"
            "  No call is made: guessing a price is worse than not trading.",
            file=sys.stderr,
        )
        return 1

    print(f"fetching {index} @ {args.timeframe}m ...")
    try:
        snapshot = market.snapshot(index, timeframe=args.timeframe, bars=args.bars)
    except (DataUnavailable, StaleData) as e:
        print(f"no usable data: {e}", file=sys.stderr)
        return 1

    print(
        f"  last {snapshot.quote.last}  |  {len(snapshot.bars)} bars  "
        f"|  captured {snapshot.captured_at:%H:%M:%S} UTC"
    )

    spec = _spec(index, args.timeframe)
    if args.print_prompt:
        from tsys.analyst import render_user_message

        print(BAR)
        print(render_user_message(snapshot, spec))
        print(BAR)
        return 0

    if not settings.analyst.configured:
        print(
            "ANTHROPIC_API_KEY is not set, so the analyst cannot run.\n"
            "  Add it to .env, or re-run with --print-prompt to get the brief to "
            "paste into a Claude session yourself.",
            file=sys.stderr,
        )
        return 2

    print(
        f"asking {settings.analyst.model} (effort={settings.analyst.effort}, "
        f"web_search={settings.analyst.web_search}) ..."
    )
    try:
        call = Analyst(settings.analyst).call(snapshot, spec)
    except AnalystRejected as e:
        print(f"\ncall REJECTED by the risk mandate: {e}", file=sys.stderr)
        print("nothing recorded. the model must respect the envelope.", file=sys.stderr)
        return 1
    except Exception as e:  # noqa: BLE001 - report cleanly, never half-record
        print(f"\nanalyst failed: {e}", file=sys.stderr)
        return 1

    risk = call.levels.risk_per_unit(call.side) * call.lots * spec.lot_size
    print("\n" + BAR)
    print(call.render())
    print(BAR)
    print(f"entry (market): {call.levels.entry}")
    print(f"risk at {call.lots} lot(s) x {spec.lot_size}: Rs {risk:.2f} (cap Rs {spec.max_risk})")
    if risk > spec.max_risk:
        print("  WARNING: sizing exceeds the cap. Recorded, but do not trade it.")

    call_id = _store().append(call, snapshot, mode="paper")
    print(f"\nrecorded as {call_id} (paper).")
    print("score it later with:  python apps/analyst-cli/main.py score")
    return 0


def cmd_score(args: argparse.Namespace) -> int:
    """Walk each open call forward against fresh bars."""
    store = _store()
    pending = store.unscored()
    if not pending:
        print("no unscored calls.")
        return 0

    market = TradingViewClient(settings.tradingview)
    if not market.health():
        print("TradingView unreachable; cannot fetch bars to score against.", file=sys.stderr)
        return 1

    for record in pending:
        index = record["index"]
        try:
            snapshot = market.snapshot(
                index, timeframe=record.get("timeframe", "5"), bars=args.bars
            )
        except (DataUnavailable, StaleData) as e:
            print(f"{record['call_id']}: skipped ({e})")
            continue

        call_at = record["snapshot_captured_at"]
        after = tuple(b for b in snapshot.bars if b.ts.isoformat() > call_at)
        levels = Levels(
            entry=Decimal(record["entry"]),
            stop_loss=Decimal(record["stop_loss"]),
            target=Decimal(record["target"]),
        )
        card = score_call(levels=levels, side=Side(record["side"]), subsequent=after)
        mark = {
            Outcome.TARGET: "WIN ",
            Outcome.STOP: "LOSS",
            Outcome.AMBIGUOUS: "AMBI",
            Outcome.OPEN: "open",
        }[card.outcome]
        print(
            f"{mark} {record['call_id']:<28} {record['side']:<5} "
            f"{card.r_multiple:+.2f}R  ({len(after)} bars since)"
        )
        if card.resolved:
            store.record_outcome(record["call_id"], card.outcome.value, card.r_multiple)
    return 0


def cmd_accuracy(_: argparse.Namespace) -> int:
    """Summarise every scored call."""
    rows = [r for r in _store().read() if r.get("outcome")]
    if not rows:
        print("nothing scored yet. run:  python apps/analyst-cli/main.py score")
        return 0

    from tsys.analyst.accuracy import ScoreCard

    cards = [
        ScoreCard(
            outcome=Outcome(r["outcome"]),
            resolved_at=None,
            bars_to_resolve=0,
            move_points=Decimal(0),
            r_multiple=Decimal(r.get("r_multiple", "0")),
        )
        for r in rows
    ]
    s = summarise(cards)
    print(BAR)
    print(f"calls scored   {s.resolved}")
    print(f"wins / losses  {s.wins} / {s.losses}")
    print(f"hit rate       {s.hit_rate * 100:.1f}%")
    print(f"expectancy     {s.expectancy_r:+.3f}R per call")
    print(BAR)
    print("Expectancy is the number that matters: a 40% hit rate at 1:2 compounds,")
    print("an 80% hit rate at 1:0.2 does not.")

    by_index: dict[str, list[str]] = {}
    for r in rows:
        by_index.setdefault(r["index"], []).append(r["outcome"])
    print("\nby index:")
    for index, outcomes in sorted(by_index.items()):
        wins = outcomes.count("target")
        print(f"  {index:<11} {wins}/{len(outcomes)} won")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="analyst", description="LLM analyst, paper-only.")
    sub = p.add_subparsers(dest="command", required=True)

    a = sub.add_parser("analyze", help="get a call on an index")
    a.add_argument("index")
    a.add_argument("--timeframe", default="15")
    a.add_argument("--bars", type=int, default=200)
    a.add_argument(
        "--print-prompt",
        action="store_true",
        help="print the brief instead of calling the model",
    )
    a.set_defaults(fn=cmd_analyze)

    s = sub.add_parser("score", help="score open calls against fresh bars")
    s.add_argument("--bars", type=int, default=300)
    s.set_defaults(fn=cmd_score)

    sub.add_parser("accuracy", help="summarise scored calls").set_defaults(fn=cmd_accuracy)

    args = p.parse_args(argv)
    configure(settings.base.log_level)
    print(
        f"mode={settings.risk.mode.value} | paper-only path | "
        f"{clock.now_ist():%Y-%m-%d %H:%M} IST"
    )
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
