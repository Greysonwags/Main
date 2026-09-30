"""Command line: python -m kalshi_bot {status,scan,run} [--place]

`run` is a dry run unless --place is given. Orders only ever go to the demo
environment, which uses fake money.
"""

import argparse
import json
import time
from datetime import datetime, timezone

from .client import KalshiClient, KalshiError
from .risk import RiskConfig, size_orders
from .strategy import StrategyConfig, find_trades

JOURNAL = "trades.jsonl"


def dollars(cents: int) -> str:
    return f"${cents / 100:,.2f}"


def cmd_status(client, args):
    print(f"Demo balance: {dollars(client.get_balance_cents())}")
    positions = [p for p in client.get_positions() if p.get("position")]
    if not positions:
        print("No open positions.")
    for p in positions:
        qty = p["position"]
        side = "YES" if qty > 0 else "NO"
        print(f"  {p['ticker']}: {abs(qty)} {side}")


def scan(client, args):
    max_close_ts = time.time() + args.hours * 3600
    markets = client.get_open_markets(max_close_ts=max_close_ts)
    ideas = find_trades(markets, StrategyConfig())
    print(f"Scanned {len(markets)} open markets closing within {args.hours}h; {len(ideas)} match.")
    return ideas


def cmd_scan(client, args):
    for idea in scan(client, args)[:20]:
        print(f"  {idea.ticker}  BUY {idea.side.upper()} @ {idea.price}c  ({idea.reason})")


def cmd_run(client, args):
    ideas = scan(client, args)
    balance = client.get_balance_cents()
    held = {p["ticker"] for p in client.get_positions() if p.get("position")}
    orders = size_orders(ideas, balance, held, RiskConfig())
    print(f"Balance {dollars(balance)}; {len(orders)} order(s) pass risk limits.")

    for o in orders:
        i = o.idea
        line = f"BUY {o.count} {i.side.upper()} {i.ticker} @ {i.price}c (cost {dollars(o.cost)})"
        if not args.place:
            print(f"  [dry run] {line}")
            continue
        try:
            result = client.place_limit_order(i.ticker, i.side, o.count, i.price)
            print(f"  [placed] {line} -> {result.get('status', 'submitted')}")
        except KalshiError as e:
            print(f"  [failed] {line}: {e}")
            continue
        with open(JOURNAL, "a") as f:
            f.write(json.dumps({
                "time": datetime.now(timezone.utc).isoformat(),
                "ticker": i.ticker, "side": i.side, "count": o.count,
                "price": i.price, "order_id": result.get("order_id"), "reason": i.reason,
            }) + "\n")

    if orders and not args.place:
        print("Dry run only. Re-run with --place to send these to the demo exchange.")


def main():
    parser = argparse.ArgumentParser(prog="kalshi_bot", description="Kalshi demo trading bot")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status", help="show demo balance and positions")
    for name, help_text in (("scan", "list markets the strategy likes"),
                            ("run", "size orders and (with --place) submit them")):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("--hours", type=float, default=48, help="only markets closing within N hours")
        if name == "run":
            p.add_argument("--place", action="store_true", help="actually submit orders to demo")
    args = parser.parse_args()

    try:
        client = KalshiClient.from_env()
        {"status": cmd_status, "scan": cmd_scan, "run": cmd_run}[args.command](client, args)
    except KalshiError as e:
        raise SystemExit(f"Error: {e}")


if __name__ == "__main__":
    main()
