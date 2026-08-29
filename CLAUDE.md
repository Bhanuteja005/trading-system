# Trading System — operating brief

An automated Indian F&O stack. Python for trading logic, Node for the TradingView
bridge. Read `README.md` for the layout and `docs/architecture.md` for why the
boundaries sit where they do.

## Before anything else

**Nothing trades by default.** `TSYS_MODE` is `dry_run`. Live needs three
independent switches (`TSYS_MODE=live`, `TSYS_LIVE_CONFIRMED=true`, `--yes-live`).
Never set any of them on the user's behalf, and never suggest removing a guard to
make something work.

**Never inline a secret.** Not in source, not in this file, not in a commit
message, not in an example command. Config comes from `.env` through
`packages/config`. A key was committed here once and the repo is public; the CI
secret scan exists because of it.

## When the user asks to analyze or trade an index

Do not hand-run the TradingView MCP tools and improvise a call. That path already
exists, is tested, and records what it did:

```bash
python apps/analyst-cli/main.py analyze NIFTY --timeframe 15
```

It fetches live data, renders the institutional brief, asks Claude Opus 5 with web
search, validates the answer against the risk mandate, and records it as a paper
trade. `--print-prompt` shows the exact brief without spending a token.

For the deterministic path instead:

```bash
python -m tsys.executor.main --index NIFTY --once
```

Use the MCP tools directly only for exploration the CLI does not cover — reading a
custom indicator, taking a screenshot, driving the chart UI.

## Rules that hold everywhere in this repo

**Only `packages/config` reads the environment.** `scripts/check_env_boundary.py`
enforces it by AST walk in CI. If you need a setting somewhere, add it to config
and pass the object down.

**`evaluate()` stays pure.** No config, no clock, no I/O — an explicit
`EvalParams` in, a `Decision` out. It is the one function whose behaviour must be
reproducible from a fixture.

**All money is `Decimal`, all datetimes carry `tzinfo`.** Floats accumulate error
and this code multiplies prices by quantities. `to_ist()` refuses naive datetimes
rather than guessing.

**One route to the broker.** `packages/broker` is it. Do not add a second place
that posts to OpenAlgo, however convenient — the kill switch, the mode gate and
the idempotency ledger all live behind that one door.

**Order placement must stay idempotent.** `client_order_id` is a hash of the
decision's content. If you change what goes into it, a retry can double-fill.

**Failures are refusals, not guesses.** Stale data, a dead CDP connection, a
missing price: raise and record. Never substitute a fallback price and trade on it.

## Risk mandate

Defaults in `packages/config/src/tsys/config/risk.py`, overridable from `.env`.
These are limits, not suggestions — the risk layer rejects breaches and a
rejection is final.

- Capital ₹3,00,000, fixed, does not compound
- Risk per trade: max 1% (₹3,000), min 0.25% (₹750)
- Minimum reward:risk 1:2
- Max 2 open positions, max 2% total open risk, one position per index
- Daily loss limit ₹6,000, profit target ₹9,000 — both halt new entries
- No new entries after 15:00 IST, square off at 15:20 IST

Lot sizes: NIFTY 75 (NFO), BANKNIFTY 35 (NFO), SENSEX 10 (BFO), GOLDM 10 (MCX).

## Kill switch

`data/KILL`. While the file exists, every order path refuses.

```bash
python scripts/stack.py kill on
python scripts/stack.py kill off
```

## Verifying a change

```bash
npm run check    # ruff + env boundary + Node suite (29) + Python suite (93)
```

The safety tests are the ones that matter — double-fill on retry, dry-run
silence, the kill switch stopping an order mid-pipeline, stale data being
refused. If a change makes one of those fail, the change is wrong, not the test.

## Conventions

- `git mv` for moves, so history survives
- One logical change per commit; the message says *why*, not *what*
- Comments explain the reasoning that is not visible in the code — the non-obvious
  constraint, the failure mode being defended against. Not narration.
- New shared code goes in `packages/`; user-facing surfaces go in `apps/`
- `packages/openalgo` is vendored third-party code. Do not refactor its internals.

## Model note

Claude Opus 5 (`claude-opus-5`) is the current model and the analyst default.
Model IDs are complete as written — never append a date suffix.
