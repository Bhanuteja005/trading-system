# Architecture

## The shape

One request travels in one direction:

```
index name
   -> tvclient      fetch a snapshot (Python shells out to the Node tv CLI)
   -> evaluate      pure function: snapshot + params -> Decision
   -> sizing        risk budget decides quantity
   -> risk          portfolio limits: may this be added?
   -> broker        idempotent placement, three gates in front
   -> journal       the decision and its inputs, on disk
```

Every stage may stop the cycle. Nothing downstream runs if an earlier stage said
no, and the reason is always recorded.

## Why the boundaries sit where they do

### Only `packages/config` reads the environment

Scattered `os.environ` lookups are how a service ends up live when someone
believed it was in dry-run. One frozen `Settings` object is built once per
process and handed down. `scripts/check_env_boundary.py` walks the AST of every
Python file and fails CI on a violation, so the rule cannot rot.

The launcher (`scripts/stack.py`) is the one documented exemption: it composes
`PYTHONPATH` for child processes, holds no config and reads no secrets.

### `evaluate()` takes no config and does no I/O

It receives an explicit `EvalParams`. That makes it a pure function of its
inputs, which is what lets the decision boundary be tested against recorded
fixtures and diffed when it changes. A function that reached for `settings`
would behave differently on two machines with the same snapshot.

### The broker client is the only route to OpenAlgo

Not a convention — a structural fact. `place_order` is the sole write path, and
three gates sit in front of it in order:

1. **Kill switch.** A file at `data/KILL`. Checked before anything else.
2. **Mode gate.** `dry_run` returns a synthetic id and issues no HTTP call.
3. **Ledger.** The `client_order_id` is claimed before the request is sent.

`apps/trader-cli/place_order.py` is a thin front end onto the same client rather
than a second, unguarded way in.

### Idempotency is derived, not assigned

A `client_order_id` is a hash of the decision's own content: index, side, the
three levels, and the session date. Identical intent collapses to one id; any
level change produces a new one. This is what makes a retry safe.

The ledger is written **before** the request leaves, so a crash mid-flight still
records that the id was used, and it is replaced atomically so a crash mid-write
cannot truncate it.

On timeout the reservation is deliberately **kept**. A timeout is exactly the
case where we do not know whether the order landed, so a retry reports
`deduplicated` rather than firing again. A definitive 4xx rejection releases the
id, since nothing was consumed and a corrected retry should be allowed.

### Python calls Node through a subprocess

`packages/tvclient` shells out to the `tv` CLI that `packages/tradingview-mcp`
already exposes as a bin, and parses JSON. The alternative — reimplementing the
CDP protocol in Python — would mean two implementations drifting apart. This is
also the pattern the repo already used before the restructure.

The seam is a byte stream, so `parse.py` is pure and every branch (CLI error
envelope, non-JSON response, unparseable price, empty bar array) is covered by a
fixture test with nothing running.

### Freshness is enforced at the source

`TradingViewClient.snapshot()` raises rather than returning stale or thin data.
The evaluator can only ever see a fresh, complete snapshot, so it does not need
to defend against `None` prices — and a `None` price cannot reach sizing, where
it would silently become a position.

## Two decision makers, one risk layer

| | Executor | Analyst |
| --- | --- | --- |
| Decides by | Deterministic scoring | Claude Opus 5 |
| Reproducible | Yes, exactly | No |
| Stops from | ATR × multiple | Model's levels, re-validated |
| Reaches the broker | Yes, when live | Never |
| Tested against | Fixtures | Mandate validation |

They share sizing, the risk limits, the journal and the kill switch. The analyst
path is paper-only by construction: it never constructs a `BrokerClient`.

The analyst treats the model as a participant, not an authority. `schema.validate`
recomputes reward:risk from the levels rather than trusting the model's own
figure, checks both levels against the correct side of the last price, and
rejects a call that breaks the mandate instead of nudging it into range. "Wait"
is not representable in the response schema.

## Money is `Decimal`, time is timezone-aware

Every price, level and rupee figure is a `Decimal`. Floats accumulate error and
this code multiplies prices by quantities.

Every datetime carries a `tzinfo`. `to_ist()` refuses a naive datetime rather
than guessing. `session_date()` is computed in IST, so a 22:00 UTC instant
correctly belongs to the next trading session.

## What is deliberately not here

- **No database.** JSONL journals and a JSON ledger. One process writes them and
  the volumes are small; a database would be infrastructure without a problem.
- **No exchange holiday calendar.** `is_market_open` handles weekends and hours
  only. A holiday still needs the kill switch.
- **No position reconciliation against the broker.** `PortfolioState` is passed
  in. Wiring it to a live positions feed is the obvious next step before live
  trading with more than one open position.
- **No modification of `packages/openalgo`.** It is vendored third-party code
  with its own `pyproject.toml` and `.venv`, excluded from the uv workspace so
  its dependencies cannot conflict with ours.
