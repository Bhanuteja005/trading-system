# Trading System

An automated Indian F&O trading stack. You name an index; the system pulls live
data from a TradingView chart, decides whether a trade is worth taking, sizes it
from a fixed risk budget, and — only when you have explicitly opted in — places
the order through OpenAlgo.

It is a polyglot monorepo: Python for the trading logic, Node for the TradingView
bridge. Neither is ported to the other.

**Nothing trades by default.** `TSYS_MODE` is `dry_run` until you change it, and
live trading needs three independent switches. See [Trading modes](#trading-modes).

## Prerequisites

- Python `3.12+` and [`uv`](https://docs.astral.sh/uv/)
- Node `20+`
- TradingView Desktop, launched with Chrome DevTools Protocol enabled (port `9222`)
- An OpenAlgo account with a broker connected, for anything past dry-run

## Quick Start

Install both ecosystems from the repo root:

```bash
npm install          # Node workspace + turbo
uv sync --all-packages   # Python workspace
cp .env.example .env     # then fill it in
```

Check what is running:

```bash
python scripts/stack.py status
```

Start the pieces you need:

```bash
python scripts/stack.py up openalgo     # broker gateway on :5000
python scripts/stack.py up dashboard    # UI on :5050
```

Ask for a call on an index:

```bash
python apps/analyst-cli/main.py analyze NIFTY
```

Open <http://127.0.0.1:5050> for the dashboard.

## Service URLs

| Service | URL | Runtime |
| --- | --- | --- |
| Dashboard | `http://127.0.0.1:5050` | Local Flask |
| OpenAlgo | `http://127.0.0.1:5000` | Local Flask (vendored) |
| OpenAlgo websocket | `ws://127.0.0.1:8765` | Local |
| TradingView CDP | `http://127.0.0.1:9222` | TradingView Desktop |

## Layout

`packages/` holds both shared libraries and long-running services; `apps/` holds
the user-facing surfaces. Only `packages/config` reads the environment — CI fails
the build if anything else does.

```
packages/
  config/           the single env boundary (pydantic-settings)
  domain/           pure types: Bar, Quote, Decision, Levels, Order, Position
  core/             logging, IST clock, deterministic ids, retry, errors
  broker/           the only code that talks to OpenAlgo
  tvclient/         Python bridge to the Node TradingView CLI
  journal/          append-only decision log
  executor/         the deterministic signal-to-order pipeline
  analyst/          the LLM desk call, and accuracy scoring
  tradingview-mcp/  Node: MCP server + `tv` CLI driving TradingView over CDP
  openalgo/         vendored third-party broker gateway, unmodified

apps/
  dashboard/        the :5050 UI
  analyst-cli/      analyze / score / accuracy
  trader-cli/       manual order entry and the legacy monitor loop

scripts/            operator CLI and CI checks
docs/               architecture, runbook, decision records
data/               journals, ledgers, the kill switch (gitignored)
```

## Two ways a trade gets decided

The stack has two independent decision makers. They share the same risk layer,
sizing, journal and kill switch, and differ only in how the call is made.

**The executor** (`packages/executor`) is deterministic. `evaluate()` is a pure
function: a market snapshot and an explicit `EvalParams` in, a `Decision` out,
identical every time. It scores trend, break of structure, momentum, EMA
separation and close direction against one threshold. Stops come from ATR, never
a fixed point count, and the target is placed at exactly `min_reward_ratio` times
the risk — so the 1:2 floor is true by construction rather than checked after.

```bash
python -m tsys.executor.main --index NIFTY --once
```

**The analyst** (`packages/analyst`) asks Claude Opus 5 for a discretionary
institutional call, with web search enabled because the brief demands current
macro and geopolitical context that cannot come from model memory. The model is a
participant, not an authority: every number it returns is re-derived before
anything is recorded — reward:risk recomputed from the levels, stop and target
checked against the correct side of the last price, lots checked against the
range. A call that breaks the mandate is rejected outright, not nudged into range.

```bash
python apps/analyst-cli/main.py analyze NIFTY --timeframe 15
python apps/analyst-cli/main.py analyze NIFTY --print-prompt   # no API call
```

This path is paper-only by construction — it has no route to the broker at all.

## Measuring whether the calls are any good

Every call is recorded with the snapshot that produced it. Scoring walks the bars
that came after, in order:

```bash
python apps/analyst-cli/main.py score      # resolve open calls
python apps/analyst-cli/main.py accuracy   # hit rate and expectancy
```

A bar that spans both the stop and the target is counted as a **loss**: intrabar
order is unknowable at that resolution, and assuming the good fill first is how a
backtest flatters itself.

Read expectancy, not hit rate. A 40% hit rate at 1:2 compounds; an 80% hit rate at
1:0.2 does not.

## Trading modes

| `TSYS_MODE` | What happens |
| --- | --- |
| `dry_run` *(default)* | Decides and journals. Issues no HTTP call to the broker at all. |
| `paper` | Routes to the paper dashboard. No real money. |
| `live` | Real orders. Requires two further switches. |

Live trading requires **all three**, and the executor refuses to start otherwise:

```bash
TSYS_MODE=live TSYS_LIVE_CONFIRMED=true \
  python -m tsys.executor.main --index NIFTY --yes-live
```

### Kill switch

Creates a file that every order path checks before placing. While it exists,
nothing trades — including a running executor.

```bash
python scripts/stack.py kill on
python scripts/stack.py kill off
```

The dashboard has the same control, and both act on the same `data/KILL` path.

## Risk mandate

Defaults live in `packages/config/src/tsys/config/risk.py` and are overridable
from `.env`. They are limits, not suggestions: the risk layer rejects anything
that breaches one, and a rejection is final.

| Limit | Default |
| --- | --- |
| Capital (fixed, does not compound) | ₹3,00,000 |
| Max risk per trade | 1% — ₹3,000 |
| Min risk per trade | 0.25% — ₹750 |
| Min reward:risk | 1:2 |
| Max open positions | 2 |
| Max total open risk | 2% of capital |
| Daily loss limit / profit target | ₹6,000 / ₹9,000 |
| No new entries after | 15:00 IST |
| Square off | 15:20 IST |

Lot sizes: NIFTY 75 (NFO), BANKNIFTY 35 (NFO), SENSEX 10 (BFO), GOLDM 10 (MCX).

## Commands

```bash
npm test          # both suites: turbo (Node, 29) + pytest (Python, 93)
npm run test:node # Node only, cached by turbo
npm run test:py   # Python only
npm run lint      # ruff
npm run check     # lint + env boundary + both suites
```

Turbo caches the Node suite, so a repeat run of an unchanged package is ~60ms
instead of ~15s. The Python suite runs directly under pytest — at 93 tests in
about two seconds it has nothing to gain from a task graph.

## Safety properties, and the tests that hold them

These are the behaviours worth breaking the build over:

| Property | Where |
| --- | --- |
| A retry after a timeout cannot double-fill | `packages/broker/tests/test_client.py` |
| The ledger survives a crash and restart | same |
| Dry-run issues no HTTP call whatsoever | same, and `test_pipeline.py` |
| The kill switch stops an order mid-pipeline | `packages/executor/tests/test_pipeline.py` |
| A data failure ends the cycle rather than guessing a price | same |
| Stale or thin data is refused, not traded | `packages/tvclient/tests/test_parse.py` |
| Sizing floors lots and never rounds up past the cap | `packages/executor/tests/test_sizing_and_risk.py` |
| Two legal trades cannot stack past the portfolio ceiling | same |
| An LLM call breaking the mandate is rejected, not repaired | `packages/analyst/tests/test_schema.py` |
| Config resolves `data/` and the kill switch to the repo root | `packages/config/tests/test_paths.py` |

## Configuration

Every setting is read once, at the boundary, and handed down as a frozen object.
No module outside `packages/config` reads `os.environ`; `scripts/check_env_boundary.py`
enforces it by AST walk and runs in CI.

```python
from tsys.config import settings

settings.risk.max_risk_rupees   # Decimal("3000.00")
settings.broker.api_key         # SecretStr — cannot leak through a repr or log
```

Copy `.env.example` to `.env` and fill it in. `.env` is gitignored; never commit
a key, and never inline one in a source file or in `CLAUDE.md`.

## Troubleshooting

**"TradingView is not reachable over CDP"** — TradingView Desktop must be running
with remote debugging on port 9222. The analyst refuses to run without it rather
than guessing a price.

**"No usable data" / stale snapshot** — the chart returned fewer than `TV_MIN_BARS`
bars, or a quote older than `TV_MAX_QUOTE_AGE_SECONDS`. Both are refusals by
design; widen them in `.env` only if you understand what you are trading on.

**Orders silently do nothing** — check the mode. `dry_run` returns a synthetic
`DRYRUN-` order id and never contacts the broker. `python scripts/stack.py status`
shows the mode and the kill switch together.

**`ModuleNotFoundError: tsys.*`** — run through `scripts/stack.py`, or `uv run`,
so the workspace packages are on the path.

## Docs

- `docs/architecture.md` — how the pieces fit, and why the boundaries sit where they do
- `docs/runbook.md` — starting, stopping, and what to do when something is wrong
- `docs/adr/` — decisions worth their own record
- `CLAUDE.md` — the operating brief for Claude Code in this repo
