# Runbook

## Stop everything, now

```bash
python scripts/stack.py kill on
```

Creates `data/KILL`. Every order path checks it before placing, including an
executor already running. The dashboard's red button does the same thing.

This stops **new orders**. It does not close open positions — square those off in
OpenAlgo or with `apps/trader-cli/place_order.py`.

Release it when you have finished:

```bash
python scripts/stack.py kill off
```

## Daily start

```bash
python scripts/stack.py status          # what is up, what mode, kill switch state
python scripts/stack.py up openalgo     # :5000 — needed for anything but dry_run
python scripts/stack.py up dashboard    # :5050
```

Then launch TradingView Desktop with CDP on port 9222. Confirm the bridge:

```bash
node packages/tradingview-mcp/src/cli/index.js status
```

## Taking a call on an index

```bash
python apps/analyst-cli/main.py analyze NIFTY --timeframe 15
```

Prints the decision in the mandated format, records it to
`data/analyst_calls.jsonl`, and places no order.

To see exactly what would be sent to the model without spending a token:

```bash
python apps/analyst-cli/main.py analyze NIFTY --print-prompt
```

## Running the deterministic executor

```bash
python -m tsys.executor.main --index NIFTY --once            # one cycle
python -m tsys.executor.main --index NIFTY --interval 300    # scan every 5 min
```

It exits on its own past the square-off time.

## Going live

Deliberately awkward. All three are required and the executor refuses to start
otherwise:

```bash
# in .env
TSYS_MODE=live
TSYS_LIVE_CONFIRMED=true
```
```bash
python -m tsys.executor.main --index NIFTY --yes-live
```

Before you do, confirm in this order:

1. `python scripts/stack.py status` shows OpenAlgo running and the kill switch clear
2. The broker is connected in the OpenAlgo dashboard and shows funds
3. `npm test` passes
4. The paper path has been run and scored, and expectancy is positive
5. You know how to reach the kill switch from where you will be sitting

## End of day

The executor squares off at 15:20 IST and stops taking entries after 15:00. If it
was not running, close positions yourself — nothing else will.

```bash
python apps/analyst-cli/main.py score      # resolve the day's calls
python apps/analyst-cli/main.py accuracy   # hit rate and expectancy
```

## When something is wrong

### An order may or may not have gone through

Check the ledger first:

```bash
python -c "import json;print(json.dumps(json.load(open('data/order_ledger.json')),indent=2))"
```

`state: in_flight` means the request left but the outcome is unknown — a timeout.
The id stays claimed, so a retry will report `deduplicated` rather than firing
again. Confirm against the broker's own order book before releasing it by hand.

### The dashboard shows nothing

It reads `data/journal/decisions-<date>.jsonl`. An empty feed means no cycle has
run today, not that the dashboard is broken. Check `/api/status` for what it
thinks the mode and market state are.

### "TradingView is not reachable over CDP"

TradingView Desktop is not running, or not listening on 9222. The analyst refuses
to proceed rather than guessing a price. Restart it with remote debugging enabled.

### Decisions are all `NO_TRADE`

Usually correct behaviour, not a fault. Check the `abstain_reason` in the feed:

| Reason | Meaning |
| --- | --- |
| `low_confidence` | The score did not clear `TSYS_MIN_CONFIDENCE` |
| `insufficient_history` | Fewer bars than `TV_MIN_BARS` |
| `no_structure` | ATR was zero or the range was unmeasurable |
| `reward_risk_too_low` | Tick rounding shaved the ratio below the floor |
| `stale_data` | The snapshot aged past `TV_MAX_QUOTE_AGE_SECONDS` |

A quiet, ranging market should produce abstentions. If everything abstains for
days, look at the threshold before assuming the evaluator is broken.

### A key was committed

1. Rotate it first — OpenAlgo at `http://127.0.0.1:5000/apikey`, ngrok at
   `dashboard.ngrok.com`. Assume anything pushed to a public repo is burned.
2. Remove the literal from the working tree and commit.
3. Purge history with `git filter-repo --replace-text`, then force-push.
4. Rotation is the fix. The purge is cleanup.

The CI secret scan blocks the common shapes, but it is a net, not a guarantee.

## Where things are written

| Path | What | In git |
| --- | --- | --- |
| `data/journal/decisions-<date>.jsonl` | Every decision and its inputs | No |
| `data/analyst_calls.jsonl` | LLM calls and their scores | No |
| `data/order_ledger.json` | Idempotency ledger | No |
| `data/trades.json` | Paper trades | No |
| `data/KILL` | Kill switch | No |

All of `data/` is gitignored. It is the audit trail — back it up, do not commit it.
