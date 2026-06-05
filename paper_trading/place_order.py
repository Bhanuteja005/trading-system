"""
Quick order placer for Claude-analyzed trades.
Usage: python place_order.py BUY NIFTY02JUN2624000PE NFO 300 MIS
       python place_order.py SELL NIFTY02JUN2624000PE NFO 300 MIS
"""
import sys, os, requests, json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

OPENALGO_URL = "http://127.0.0.1:5000/api/v1/placeorder"
# API key is loaded from local_config.py (gitignored) or the OPENALGO_API_KEY
# environment variable — never hardcode it here.
try:
    from local_config import OPENALGO_API_KEY as API_KEY
except ImportError:
    API_KEY = os.environ.get("OPENALGO_API_KEY", "")
STRATEGY     = "ClaudeTrader"

if not API_KEY:
    print("ERROR: No OpenAlgo API key. Create paper_trading/local_config.py "
          "(copy from local_config.example.py) or set OPENALGO_API_KEY env var.")
    sys.exit(1)

def place(action, symbol, exchange, qty, product="MIS"):
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
        r = requests.post(OPENALGO_URL, json=payload, timeout=5)
        resp = r.json()
        if resp.get("status") == "success":
            print(f"ORDER PLACED: {action} {qty} x {symbol} | Order ID: {resp.get('orderid')}")
        else:
            print(f"ORDER FAILED: {resp}")
        return resp
    except Exception as e:
        print(f"ERROR: {e}")
        return {}

if __name__ == "__main__":
    if len(sys.argv) < 5:
        print("Usage: python place_order.py ACTION SYMBOL EXCHANGE QTY [PRODUCT]")
        print("Example: python place_order.py BUY NIFTY02JUN2624000PE NFO 300 MIS")
        sys.exit(1)
    action   = sys.argv[1]
    symbol   = sys.argv[2]
    exchange = sys.argv[3]
    qty      = int(sys.argv[4])
    product  = sys.argv[5] if len(sys.argv) > 5 else "MIS"
    place(action, symbol, exchange, qty, product)
