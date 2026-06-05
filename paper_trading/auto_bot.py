"""
Automated paper trading bot for BSX260514C74300 (Sensex 74300 CE, 14 May 2026).

Bot: Breakout Momentum — best for near-expiry options (high gamma = amplified breakouts).
Signal source: Live OHLCV from TradingView chart via CDP.
Trade execution: Paper trading API at http://127.0.0.1:5050

Run: python auto_bot.py
"""

import sys, os, json, time, subprocess, requests
from datetime import datetime
import pytz
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'breakout-momentum-bot-main'))

PAPER_API    = "http://127.0.0.1:5050/api"
OHLCV_SCRIPT = os.path.join(os.path.dirname(__file__), "fetch_ohlcv.mjs")
SYMBOL       = "BSX260514C74300"
SCAN_SECS    = 60        # scan every 60 seconds
LOT_QTY      = 1         # 1 lot per trade
MAX_LOSS     = -500.0    # stop bot if daily paper loss hits -500
MAX_PROFIT   = 1000.0    # stop bot if daily paper profit hits +1000
IST          = pytz.timezone("Asia/Kolkata")

_position_open = False   # tracks if we have an open paper position


def now_ist():
    return datetime.now(IST)


def in_market_hours():
    n = now_ist()
    open_  = n.replace(hour=9,  minute=15, second=0, microsecond=0)
    close_ = n.replace(hour=15, minute=25, second=0, microsecond=0)
    return open_ <= n <= close_


def fetch_ohlcv(bars=120) -> pd.DataFrame | None:
    try:
        r = subprocess.run(["node", OHLCV_SCRIPT, str(bars)],
                           capture_output=True, text=True, timeout=8)
        data = json.loads(r.stdout.strip())
        if "error" in data:
            print(f"[bot] OHLCV error: {data['error']}")
            return None
        df = pd.DataFrame(data["bars"])
        df["datetime"] = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_convert("Asia/Kolkata")
        df = df.rename(columns={"open":"open","high":"high","low":"low",
                                 "close":"close","volume":"volume"})
        return df.sort_values("datetime").reset_index(drop=True)
    except Exception as e:
        print(f"[bot] fetch_ohlcv failed: {e}")
        return None


def _load_breakout_signal():
    import importlib.util
    path = os.path.join(os.path.dirname(__file__), '..', 'breakout-momentum-bot-main', 'signal.py')
    spec = importlib.util.spec_from_file_location("bm_signal", os.path.abspath(path))
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

_bm_mod = None

def get_signal(df: pd.DataFrame) -> dict:
    global _bm_mod
    try:
        if _bm_mod is None:
            _bm_mod = _load_breakout_signal()
        return _bm_mod.get_signal(df)
    except Exception as e:
        print(f"[bot] signal error: {e}")
        return {"direction": "NEUTRAL", "confidence": 0.0, "source": "breakout_momentum"}


def get_daily_pnl() -> float:
    try:
        trades = requests.get(f"{PAPER_API}/trades", timeout=3).json()
        today  = now_ist().strftime("%d/%m/%Y")
        return sum(t.get("pnl", 0) or 0 for t in trades
                   if t.get("status") == "CLOSED" and today in t.get("exit_time", ""))
    except Exception:
        return 0.0


def has_open_position() -> bool:
    try:
        trades = requests.get(f"{PAPER_API}/trades", timeout=3).json()
        return any(t.get("status") == "OPEN" and t.get("symbol") == SYMBOL for t in trades)
    except Exception:
        return False


def get_current_price() -> float | None:
    try:
        r = requests.get(f"{PAPER_API}/price", timeout=5).json()
        return r.get("price")
    except Exception:
        return None


def place_buy(price: float, reason: str):
    ts = now_ist().strftime("%d/%m/%Y, %H:%M:%S")
    payload = {"action": "BUY", "price": price, "qty": LOT_QTY,
               "symbol": SYMBOL, "time": ts, "note": reason}
    r = requests.post(f"{PAPER_API}/trades", json=payload, timeout=5).json()
    print(f"[bot] BUY  {SYMBOL} @ {price:.2f}  ({reason})  -> {r.get('status')}")


def place_sell(price: float, reason: str):
    ts = now_ist().strftime("%d/%m/%Y, %H:%M:%S")
    payload = {"action": "SELL", "price": price, "qty": LOT_QTY,
               "symbol": SYMBOL, "time": ts, "note": reason}
    r = requests.post(f"{PAPER_API}/trades", json=payload, timeout=5).json()
    pnl = r.get("trade", {}).get("pnl", "?")
    print(f"[bot] SELL {SYMBOL} @ {price:.2f}  ({reason})  P&L=Rs{pnl}")


def banner():
    print("\n" + "="*58)
    print(f"  Breakout Bot  |  {now_ist().strftime('%Y-%m-%d %H:%M:%S IST')}")
    print("="*58)


def scan():
    global _position_open
    banner()

    if not in_market_hours():
        print("[bot] outside market hours — waiting")
        return

    # Daily circuit breakers
    pnl = get_daily_pnl()
    print(f"[bot] daily P&L = Rs{pnl:.2f}")
    if pnl <= MAX_LOSS:
        print(f"[bot] LOSS LIMIT hit (Rs{MAX_LOSS}) — no new trades today")
        return
    if pnl >= MAX_PROFIT:
        print(f"[bot] PROFIT TARGET hit (Rs{MAX_PROFIT}) — locking gains, no new trades")
        return

    # Fetch live data
    df = fetch_ohlcv(120)
    if df is None or len(df) < 30:
        print("[bot] not enough bars yet")
        return
    print(f"[bot] {len(df)} bars fetched, last close = {df['close'].iloc[-1]:.2f}")

    # Get signal
    sig = get_signal(df)
    direction  = sig["direction"]
    confidence = sig["confidence"]
    print(f"[bot] signal: {direction:7s}  confidence={confidence:.2f}  ({sig.get('reason','')}{sig.get('source','')})")

    # Get live price
    price = get_current_price() or float(df["close"].iloc[-1])

    open_pos = has_open_position()

    # Entry logic — BUY on BULL breakout (we hold a CE, profits when market goes up)
    if direction == "BULL" and confidence >= 0.55 and not open_pos:
        place_buy(price, f"breakout BULL conf={confidence:.2f}")

    # Exit logic — SELL when BEAR signal or confidence drops
    elif direction == "BEAR" and confidence >= 0.50 and open_pos:
        place_sell(price, f"breakout BEAR conf={confidence:.2f}")

    # Stop-loss exit — if NEUTRAL with low confidence and we're in a trade
    elif direction == "NEUTRAL" and open_pos:
        # check if trade is losing more than 15% from entry
        try:
            trades = requests.get(f"{PAPER_API}/trades", timeout=3).json()
            for t in trades:
                if t.get("status") == "OPEN" and t.get("symbol") == SYMBOL:
                    entry = t.get("entry_price", price)
                    loss_pct = (price - entry) / entry
                    if loss_pct < -0.15:
                        place_sell(price, f"stop-loss {loss_pct:.1%}")
        except Exception:
            pass
    else:
        print(f"[bot] no action — {'holding position' if open_pos else 'waiting for signal'}")


def squareoff_end_of_day():
    if has_open_position():
        price = get_current_price()
        if price:
            place_sell(price, "EOD square-off 15:25")


def main():
    print(f"[bot] Breakout Momentum AutoBot starting")
    print(f"[bot] Symbol  : {SYMBOL}")
    print(f"[bot] Max Loss : Rs{abs(MAX_LOSS)}  |  Profit Target: Rs{MAX_PROFIT}")
    print(f"[bot] Scan     : every {SCAN_SECS}s during market hours")
    print(f"[bot] Dashboard: http://127.0.0.1:5050\n")

    while True:
        try:
            n = now_ist()
            # Force square off at 15:25 IST
            if n.hour == 15 and n.minute >= 25:
                squareoff_end_of_day()
                print("[bot] market closed — sleeping until next session")
                time.sleep(3600)
                continue
            scan()
        except KeyboardInterrupt:
            print("\n[bot] stopped by user")
            break
        except Exception as e:
            print(f"[bot] error in scan: {e}")
        time.sleep(SCAN_SECS)


if __name__ == "__main__":
    main()
