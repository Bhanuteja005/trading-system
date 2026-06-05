"""
Claude Institutional Trader — Auto Order Manager
Places entry order, monitors price, auto-exits on SL or target.

Usage:
  python auto_trade.py --symbol NIFTY02JUN2624000PE --exchange NFO \
    --direction LONG --lots 4 --sl 148.5 --target 166.5

Arguments:
  --symbol     OpenAlgo symbol (e.g. NIFTY02JUN2624000PE)
  --exchange   NFO or BFO
  --direction  LONG or SHORT
  --lots       Number of lots (NIFTY lot = 75, SENSEX lot = 10)
  --sl         Stop loss premium level
  --target     Target premium level
  --lot-size   Qty per lot (default 75 for NIFTY)
  --product    MIS (default, intraday) or NRML (overnight)
"""

import argparse, time, json, sys, os, subprocess
from datetime import datetime
import requests
import pytz

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

OPENALGO_URL = "http://127.0.0.1:5000"
# API key is loaded from local_config.py (gitignored) or the OPENALGO_API_KEY
# environment variable — never hardcode it here.
try:
    from local_config import OPENALGO_API_KEY as API_KEY
except ImportError:
    API_KEY = os.environ.get("OPENALGO_API_KEY", "")
STRATEGY     = "ClaudeTrader"

if not API_KEY:
    sys.exit("ERROR: No OpenAlgo API key. Create paper_trading/local_config.py "
             "(copy from local_config.example.py) or set OPENALGO_API_KEY env var.")
IST          = pytz.timezone("Asia/Kolkata")
LOG_FILE     = os.path.join(os.path.dirname(__file__), "trade_log.json")
FETCH_MJS    = os.path.join(os.path.dirname(__file__), "fetch_price.mjs")
POLL_SECS    = 20   # price check interval


def now_ist():
    return datetime.now(IST)


def log(msg):
    ts = now_ist().strftime("%Y-%m-%d %H:%M:%S IST")
    print(f"[{ts}] {msg}")


def save_trade(record):
    records = []
    if os.path.exists(LOG_FILE):
        try:
            records = json.load(open(LOG_FILE))
        except Exception:
            pass
    records.append(record)
    json.dump(records, open(LOG_FILE, "w"), indent=2)


def place_order(action, symbol, exchange, qty, product="MIS"):
    payload = {
        "apikey":    API_KEY,
        "strategy":  STRATEGY,
        "symbol":    symbol,
        "action":    action.upper(),
        "exchange":  exchange.upper(),
        "pricetype": "MARKET",
        "product":   product.upper(),
        "quantity":  str(qty),
    }
    try:
        r = requests.post(f"{OPENALGO_URL}/api/v1/placeorder", json=payload, timeout=8)
        resp = r.json()
        if resp.get("status") == "success":
            log(f"ORDER OK: {action} {qty}x{symbol} | OrderID={resp.get('orderid')}")
            return resp.get("orderid"), True
        else:
            log(f"ORDER FAILED: {resp}")
            return None, False
    except Exception as e:
        log(f"ORDER ERROR: {e}")
        return None, False


def get_ltp_openalgo(symbol, exchange):
    try:
        payload = {"apikey": API_KEY, "symbol": symbol, "exchange": exchange}
        r = requests.post(f"{OPENALGO_URL}/api/v1/quotes", json=payload, timeout=5)
        data = r.json()
        ltp = data.get("ltp") or data.get("data", {}).get("ltp")
        if ltp:
            return float(ltp)
    except Exception:
        pass
    return None


def get_ltp_cdp():
    try:
        r = subprocess.run(["node", FETCH_MJS],
                           capture_output=True, text=True, timeout=8)
        data = json.loads(r.stdout.strip())
        return data.get("price") or data.get("ltp")
    except Exception:
        pass
    return None


def get_ltp(symbol, exchange):
    price = get_ltp_openalgo(symbol, exchange)
    if price:
        return price
    return get_ltp_cdp()


def eod_squareoff_needed():
    n = now_ist()
    return n.hour == 15 and n.minute >= 20


def run(symbol, exchange, direction, lots, lot_size, sl, target, product):
    qty = lots * lot_size
    action = "BUY" if direction.upper() == "LONG" else "SELL"
    exit_action = "SELL" if action == "BUY" else "BUY"

    log(f"=== Claude Institutional Trader ===")
    log(f"Symbol   : {symbol} ({exchange})")
    log(f"Direction: {direction}  |  Lots: {lots}  |  Qty: {qty}")
    log(f"SL       : {sl}  |  Target: {target}")
    log(f"Product  : {product}")

    # Place entry order
    log("Placing ENTRY order...")
    order_id, ok = place_order(action, symbol, exchange, qty, product)
    if not ok:
        log("Entry order failed — aborting.")
        sys.exit(1)

    # Get fill price
    time.sleep(2)
    entry_price = get_ltp(symbol, exchange)
    if not entry_price:
        entry_price = (sl + target) / 2  # fallback estimate
    log(f"Entry price (approx): {entry_price:.2f}")

    trade_record = {
        "symbol": symbol, "exchange": exchange,
        "direction": direction, "lots": lots, "qty": qty,
        "entry_price": entry_price, "sl": sl, "target": target,
        "entry_order_id": order_id,
        "entry_time": now_ist().isoformat(),
        "status": "OPEN"
    }

    # Monitor loop
    log(f"Monitoring — SL={sl}  TARGET={target}  (checking every {POLL_SECS}s)")
    while True:
        time.sleep(POLL_SECS)
        price = get_ltp(symbol, exchange)
        if price is None:
            log("Price fetch failed, retrying...")
            continue

        # EOD force-exit
        if eod_squareoff_needed():
            log(f"EOD 15:20 — force squaring off at {price:.2f}")
            exit_id, _ = place_order(exit_action, symbol, exchange, qty, product)
            trade_record.update({"exit_price": price, "exit_reason": "EOD",
                                  "exit_order_id": exit_id, "exit_time": now_ist().isoformat(),
                                  "status": "CLOSED"})
            pnl = (price - entry_price) * qty * (1 if action == "BUY" else -1)
            trade_record["pnl"] = round(pnl, 2)
            save_trade(trade_record)
            log(f"EOD Exit | P&L = Rs{pnl:.2f}")
            break

        log(f"LTP={price:.2f}  |  SL={sl}  TARGET={target}")

        # SL hit
        sl_hit = (price <= sl) if action == "BUY" else (price >= sl)
        if sl_hit:
            log(f"STOP LOSS HIT at {price:.2f}")
            exit_id, _ = place_order(exit_action, symbol, exchange, qty, product)
            pnl = (price - entry_price) * qty * (1 if action == "BUY" else -1)
            trade_record.update({"exit_price": price, "exit_reason": "SL",
                                  "exit_order_id": exit_id, "exit_time": now_ist().isoformat(),
                                  "status": "CLOSED", "pnl": round(pnl, 2)})
            save_trade(trade_record)
            log(f"SL Exit | P&L = Rs{pnl:.2f}")
            break

        # Target hit
        target_hit = (price >= target) if action == "BUY" else (price <= target)
        if target_hit:
            log(f"TARGET HIT at {price:.2f}")
            exit_id, _ = place_order(exit_action, symbol, exchange, qty, product)
            pnl = (price - entry_price) * qty * (1 if action == "BUY" else -1)
            trade_record.update({"exit_price": price, "exit_reason": "TARGET",
                                  "exit_order_id": exit_id, "exit_time": now_ist().isoformat(),
                                  "status": "CLOSED", "pnl": round(pnl, 2)})
            save_trade(trade_record)
            log(f"TARGET Exit | P&L = Rs{pnl:.2f}")
            break


def main():
    parser = argparse.ArgumentParser(description="Claude Auto Trade Manager")
    parser.add_argument("--symbol",    required=True)
    parser.add_argument("--exchange",  required=True)
    parser.add_argument("--direction", required=True, choices=["LONG", "SHORT"])
    parser.add_argument("--lots",      required=True, type=int)
    parser.add_argument("--sl",        required=True, type=float)
    parser.add_argument("--target",    required=True, type=float)
    parser.add_argument("--lot-size",  type=int, default=75)
    parser.add_argument("--product",   default="MIS")
    args = parser.parse_args()

    run(
        symbol=args.symbol, exchange=args.exchange,
        direction=args.direction, lots=args.lots,
        lot_size=args.lot_size, sl=args.sl, target=args.target,
        product=args.product
    )


if __name__ == "__main__":
    main()
