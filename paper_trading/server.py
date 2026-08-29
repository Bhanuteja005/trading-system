"""
Paper trading server — fetches live price from TradingView via CDP,
stores trades in trades.json, serves the dashboard on http://127.0.0.1:5050
"""

from flask import Flask, jsonify, request, send_from_directory
import json, os, sys, time, threading, requests as req

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

app = Flask(__name__, static_folder=".")

TRADES_FILE   = os.path.join(os.path.dirname(__file__), "trades.json")
FETCHER_PATH  = os.path.join(os.path.dirname(__file__), "fetch_price.mjs")

# OpenAlgo live price (accurate Angel One feed)
# The API key is loaded from local_config.py (gitignored) or the OPENALGO_API_KEY
# environment variable — never hardcode it here.
OPENALGO_HOST = os.environ.get("OPENALGO_URL", "http://127.0.0.1:5000")
try:
    from local_config import OPENALGO_API_KEY as OPENALGO_KEY
except ImportError:
    OPENALGO_KEY = os.environ.get("OPENALGO_API_KEY", "")
PAPER_SYMBOL  = os.environ.get("PAPER_SYMBOL", "SENSEX14MAY2574700CE")
PAPER_EXCHANGE = os.environ.get("PAPER_EXCHANGE", "BFO")   # BSE F&O

if not OPENALGO_KEY:
    print("WARNING: No OpenAlgo API key (local_config.py / OPENALGO_API_KEY). "
          "Falling back to the TradingView CDP price feed.", file=sys.stderr)

_price_cache = {"price": None, "symbol": None, "ts": 0}
_lock = threading.Lock()


def fetch_from_openalgo() -> dict:
    """Fetch live quote from Angel One via OpenAlgo — accurate BSE options price."""
    if not OPENALGO_KEY:
        return {}
    try:
        from openalgo import api
        client = api(api_key=OPENALGO_KEY, host=OPENALGO_HOST)
        result = client.quotes(symbol=PAPER_SYMBOL, exchange=PAPER_EXCHANGE)
        if isinstance(result, dict) and result.get("status") == "success":
            ltp = result["data"].get("ltp") or result["data"].get("last_price")
            return {"price": float(ltp), "symbol": PAPER_SYMBOL, "source": "openalgo"}
    except Exception as e:
        pass
    return {}


def fetch_from_tradingview() -> dict:
    """Fallback: fetch price from TradingView page title via CDP."""
    try:
        import subprocess
        result = subprocess.run(["node", FETCHER_PATH],
                                capture_output=True, text=True, timeout=6)
        return json.loads(result.stdout.strip())
    except Exception:
        return {}


def fetch_live_price() -> dict:
    with _lock:
        if time.time() - _price_cache["ts"] < 3:
            return dict(_price_cache)

    # Try OpenAlgo first (accurate), fall back to TradingView CDP
    data = fetch_from_openalgo()
    if not data.get("price"):
        data = fetch_from_tradingview()
    if not data.get("price"):
        data = {"price": None, "symbol": PAPER_SYMBOL, "error": "both sources failed"}

    with _lock:
        _price_cache.update({**data, "ts": time.time()})

    return data


# ── Trades persistence ─────────────────────────────────────────────────────────

def load_trades() -> list:
    if os.path.exists(TRADES_FILE):
        with open(TRADES_FILE) as f:
            return json.load(f)
    return []


def save_trades(trades: list):
    with open(TRADES_FILE, "w") as f:
        json.dump(trades, f, indent=2)


# ── API routes ─────────────────────────────────────────────────────────────────

@app.route("/api/price")
def api_price():
    result = {}
    def _fetch():
        result.update(fetch_live_price())
    t = threading.Thread(target=_fetch, daemon=True)
    t.start()
    t.join(timeout=4)
    if not result:
        result = {"price": None, "symbol": "BSX260514C74300", "error": "CDP timeout"}
    return jsonify(result)


@app.route("/api/trades", methods=["GET"])
def get_trades():
    return jsonify(load_trades())


@app.route("/api/trades", methods=["POST"])
def add_trade():
    data   = request.json
    trades = load_trades()

    # Resolve open trade if SELL matches an open BUY
    if data["action"] == "SELL":
        for t in trades:
            if t.get("status") == "OPEN" and t.get("symbol") == data.get("symbol"):
                t["status"]    = "CLOSED"
                t["exit_price"] = data["price"]
                t["exit_time"]  = data["time"]
                t["qty"]        = data.get("qty", t.get("qty", 1))
                t["pnl"]        = round((data["price"] - t["entry_price"]) * t["qty"], 2)
                save_trades(trades)
                return jsonify({"status": "closed", "trade": t})

    # New BUY trade
    trade = {
        "id":          len(trades) + 1,
        "symbol":      data.get("symbol", "BSX260514C74300"),
        "action":      data["action"],
        "entry_price": data["price"],
        "exit_price":  None,
        "entry_time":  data["time"],
        "exit_time":   None,
        "qty":         data.get("qty", 1),
        "pnl":         None,
        "status":      "OPEN",
        "note":        data.get("note", ""),
    }
    trades.append(trade)
    save_trades(trades)
    return jsonify({"status": "opened", "trade": trade})


@app.route("/api/trades/<int:trade_id>", methods=["DELETE"])
def delete_trade(trade_id):
    trades = [t for t in load_trades() if t["id"] != trade_id]
    save_trades(trades)
    return jsonify({"status": "deleted"})


@app.route("/")
def index():
    return send_from_directory(".", "index.html")


if __name__ == "__main__":
    print("Paper Trading Dashboard -> http://127.0.0.1:5050")
    app.run(host="127.0.0.1", port=5050, debug=False)
