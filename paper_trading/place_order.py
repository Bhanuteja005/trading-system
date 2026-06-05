"""
Quick order placer for Claude-analyzed trades.
Usage: python place_order.py BUY NIFTY02JUN2624000PE NFO 300 MIS
       python place_order.py SELL NIFTY02JUN2624000PE NFO 300 MIS
"""
import sys, requests, json

OPENALGO_URL = "http://127.0.0.1:5000/api/v1/placeorder"
API_KEY      = "97c565e461be8600e2633bd83e4a9907b96356065a5f485c24b1e966a63a6be3"
STRATEGY     = "ClaudeTrader"

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
