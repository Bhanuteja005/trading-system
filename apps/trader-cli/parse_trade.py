"""
Parses a Claude trade-decision block and executes auto_trade.py.

Usage:
  python parse_trade.py --symbol NIFTY23800CE02JUN26 --exchange NFO < trade_text.txt
  python parse_trade.py --symbol NIFTY23800CE02JUN26 --exchange NFO --text "TRADE DECISION..."
  python parse_trade.py --symbol NIFTY23800CE02JUN26 --exchange NFO  # reads stdin
"""

import argparse
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

def parse(text):
    result = {}

    # Direction: LONG or SHORT
    m = re.search(r'TRADE DECISION\s*:\s*(LONG|SHORT)', text, re.IGNORECASE)
    if m:
        result["direction"] = m.group(1).upper()

    # Stop loss: first number after STOP LOSS
    m = re.search(r'STOP LOSS\s*:.*?(\d+\.?\d*)', text, re.IGNORECASE)
    if m:
        result["sl"] = float(m.group(1))

    # Target: first number after TARGET
    m = re.search(r'TARGET\s*:.*?(\d+\.?\d*)', text, re.IGNORECASE)
    if m:
        result["target"] = float(m.group(1))

    # Lots: first integer after LOTS
    m = re.search(r'LOTS\s*:\s*(\d+)', text, re.IGNORECASE)
    if m:
        result["lots"] = int(m.group(1))

    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol",   required=True, help="e.g. NIFTY23800CE02JUN26")
    parser.add_argument("--exchange", default="NFO",  help="NFO or BFO")
    parser.add_argument("--lot-size", type=int, default=75)
    parser.add_argument("--product",  default="MIS")
    parser.add_argument("--text",     default=None,   help="Trade text inline (else reads stdin)")
    args = parser.parse_args()

    text = args.text if args.text else sys.stdin.read()
    t = parse(text)

    missing = [k for k in ("direction","sl","target","lots") if k not in t]
    if missing:
        print(f"ERROR: Could not parse: {missing}")
        print("Parsed so far:", t)
        sys.exit(1)

    print("\n=== PARSED TRADE ===")
    print(f"Symbol   : {args.symbol} ({args.exchange})")
    print(f"Direction: {t['direction']}")
    print(f"SL       : {t['sl']}")
    print(f"Target   : {t['target']}")
    print(f"Lots     : {t['lots']}  (qty = {t['lots'] * args.lot_size})")
    print(f"Product  : {args.product}")

    cmd = [
        sys.executable,
        os.path.join(HERE, "auto_trade.py"),
        "--symbol",    args.symbol,
        "--exchange",  args.exchange,
        "--direction", t["direction"],
        "--lots",      str(t["lots"]),
        "--sl",        str(t["sl"]),
        "--target",    str(t["target"]),
        "--lot-size",  str(args.lot_size),
        "--product",   args.product,
    ]
    print("\nExecuting:", " ".join(cmd[1:]))
    print("="*40)
    subprocess.run(cmd)


if __name__ == "__main__":
    main()
