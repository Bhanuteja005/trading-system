"""Dashboard backend — read-mostly views over the journal, config and broker.

Deliberately thin. It reports what the executor decided and lets an operator
throw the kill switch; it never evaluates or places orders itself, so there is
no second route into the broker.
"""

from __future__ import annotations

import json
import subprocess
import threading
import time
from collections import deque
from decimal import Decimal, InvalidOperation
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory
from tsys.config import LOT_SIZES, settings
from tsys.core import clock, configure, get_logger
from tsys.journal import Journal

configure(settings.base.log_level)
log = get_logger("tsys.dashboard")

HERE = Path(__file__).resolve().parent
DATA = settings.base.data_dir
JOURNAL = Journal(DATA / "journal")
TRADES_FILE = DATA / "trades.json"
LEGACY_FETCHER = (
    settings.base.repo_root
    / "packages" / "tradingview-mcp" / "scripts" / "legacy" / "fetch_price.mjs"
)

app = Flask(__name__, static_folder=str(HERE))

_price_cache: dict = {"price": None, "symbol": None, "ts": 0.0}
_lock = threading.Lock()


# ── helpers ────────────────────────────────────────────────────────────────────

def _dec(value, default="0") -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(default)


def _load_trades() -> list[dict]:
    if not TRADES_FILE.exists():
        return []
    try:
        return json.loads(TRADES_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def _today_entries(limit: int = 200) -> list[dict]:
    return list(deque(JOURNAL.read(clock.session_date()), maxlen=limit))


# ── price feed ─────────────────────────────────────────────────────────────────

def _fetch_price() -> dict:
    with _lock:
        if time.time() - _price_cache["ts"] < 3 and _price_cache["price"]:
            return dict(_price_cache)
    data: dict = {}
    if LEGACY_FETCHER.exists():
        try:
            proc = subprocess.run(
                ["node", str(LEGACY_FETCHER)], capture_output=True, text=True, timeout=6
            )
            data = json.loads(proc.stdout.strip() or "{}")
        except (subprocess.SubprocessError, json.JSONDecodeError, OSError):
            data = {}
    if not data.get("price"):
        data = {"price": None, "error": "price source unavailable"}
    with _lock:
        _price_cache.update({**data, "ts": time.time()})
    return data


# ── API ────────────────────────────────────────────────────────────────────────

@app.get("/api/status")
def api_status():
    """Mode, guards and connectivity. The banner the operator must be able to trust."""
    kill = settings.risk.kill_switch_file
    return jsonify(
        {
            "mode": settings.risk.mode.value,
            "is_live": settings.risk.is_live,
            "live_confirmed": settings.risk.live_confirmed,
            "broker_configured": settings.broker.configured,
            "broker_url": settings.broker.url,
            "kill_switch_engaged": kill.exists(),
            "kill_switch_path": str(kill),
            "market_open": clock.is_market_open(),
            "session_date": clock.session_date().isoformat(),
            "now_ist": clock.now_ist().isoformat(),
            "square_off": settings.risk.square_off_time.strftime("%H:%M"),
            "indices": sorted(LOT_SIZES),
        }
    )


@app.get("/api/metrics")
def api_metrics():
    entries = _today_entries()
    trades = _load_trades()
    today = clock.session_date().strftime("%d/%m/%Y")

    realised = sum(
        _dec(t.get("pnl")) for t in trades
        if t.get("status") == "CLOSED" and today in (t.get("exit_time") or "")
    )
    open_trades = [t for t in trades if t.get("status") == "OPEN"]
    deployed = sum(
        _dec(t.get("entry_price")) * _dec(t.get("qty"), "1") for t in open_trades
    )
    entered = [e for e in entries if e.get("decision", {}).get("action") == "ENTER"]

    return jsonify(
        {
            "realised_pnl": str(realised),
            "open_positions": len(open_trades),
            "decisions_today": len(entries),
            "entries_today": len(entered),
            "capital_deployed": str(deployed),
            "capital": str(settings.risk.capital),
            "max_risk_per_trade": str(settings.risk.max_risk_rupees),
            "daily_loss_limit": str(settings.risk.daily_loss_limit),
            "daily_profit_target": str(settings.risk.daily_profit_target),
        }
    )


@app.get("/api/decisions")
def api_decisions():
    limit = min(int(request.args.get("limit", 40)), 200)
    entries = _today_entries()[-limit:]
    out = []
    for e in reversed(entries):
        d = e.get("decision", {})
        out.append(
            {
                "at": e.get("at"),
                "cycle_id": e.get("cycle_id"),
                "index": e.get("index"),
                "mode": e.get("mode"),
                "action": d.get("action"),
                "side": d.get("side"),
                "confidence": d.get("confidence"),
                "levels": d.get("levels"),
                "abstain_reason": d.get("abstain_reason"),
                "reasons": d.get("reasons") or [],
                "rejected_by": e.get("rejected_by"),
                "order_id": (e.get("order") or {}).get("broker_order_id"),
                "order_ok": (e.get("order") or {}).get("ok"),
            }
        )
    return jsonify(out)


@app.get("/api/positions")
def api_positions():
    return jsonify([t for t in _load_trades() if t.get("status") == "OPEN"])


@app.get("/api/trades")
def api_trades():
    return jsonify(_load_trades())


@app.get("/api/price")
def api_price():
    return jsonify(_fetch_price())


@app.post("/api/kill")
def api_kill():
    """Engage or release the kill switch. The one write this app performs."""
    engage = bool((request.json or {}).get("engage", True))
    kill = settings.risk.kill_switch_file
    if engage:
        kill.parent.mkdir(parents=True, exist_ok=True)
        kill.write_text(f"engaged from dashboard at {clock.now_ist().isoformat()}\n")
        log.warning("kill switch ENGAGED from dashboard")
    else:
        kill.unlink(missing_ok=True)
        log.warning("kill switch RELEASED from dashboard")
    return jsonify({"kill_switch_engaged": kill.exists()})


@app.get("/")
def index():
    return send_from_directory(str(HERE), "index.html")


if __name__ == "__main__":
    print(f"Dashboard -> http://127.0.0.1:5050   (mode={settings.risk.mode.value})")
    app.run(host="127.0.0.1", port=5050, debug=False)
