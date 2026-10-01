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
from .strategy import StrategyConfig, find_trades, skip_reasons

JOURNAL = "trades.jsonl"


def dollars(cents: int) -> str:
    return f"${cents / 100:,.2f}"


def position_qty(p: dict) -> float:
    """Contracts held (+YES / -NO), accepting the fixed-point field if present."""
    fp = p.get("position_fp")
    return float(fp) if fp not in (None, "") else float(p.get("position") or 0)


def cmd_status(client, args):
    print(f"Demo balance: {dollars(client.get_balance_cents())}")
    positions = [p for p in client.get_positions() if position_qty(p)]
    if not positions:
        print("No open positions.")
    for p in positions:
        qty = position_qty(p)
        side = "YES" if qty > 0 else "NO"
        print(f"  {p['ticker']}: {abs(qty):g} {side}")
    resting = client.get_resting_orders()
    if resting:
        print(f"{len(resting)} order(s) waiting to be filled:")
    for o in resting:
        print(f"  {o.get('ticker')}")


def scan(client, args):
    max_close_ts = time.time() + args.hours * 3600
    markets = client.get_open_markets(max_close_ts=max_close_ts)
    cfg = StrategyConfig(min_price=args.min_price, max_price=args.max_price,
                         max_spread=args.max_spread, min_volume_24h=args.min_volume)
    ideas = find_trades(markets, cfg)
    print(f"Scanned {len(markets)} open markets closing within {args.hours}h; {len(ideas)} match.")
    reasons = skip_reasons(markets, cfg)
    if reasons:
        print("Skipped: " + ", ".join(f"{n} {r}" for r, n in sorted(reasons.items(), key=lambda x: -x[1])))
    return ideas


def cmd_scan(client, args):
    for idea in scan(client, args)[:20]:
        print(f"  {idea.ticker}  BUY {idea.side.upper()} @ {idea.price}c  ({idea.reason})")


def cmd_run(client, args):
    ideas = scan(client, args)
    balance = client.get_balance_cents()
    held = {p["ticker"] for p in client.get_positions() if position_qty(p)}
    # Also skip markets where an earlier order is still waiting, so re-running
    # never doubles up. If this check fails, the error stops the run.
    held |= {o["ticker"] for o in client.get_resting_orders() if o.get("ticker")}
    already = sum(1 for i in ideas if i.ticker in held)
    if already:
        print(f"Skipping {already} market(s) you already hold or have an order waiting in.")
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
    d = StrategyConfig()
    for name, help_text in (("scan", "list markets the strategy likes"),
                            ("run", "size orders and (with --place) submit them")):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("--hours", type=float, default=48, help="only markets closing within N hours")
        p.add_argument("--min-volume", type=int, default=d.min_volume_24h, help="min contracts traded in 24h")
        p.add_argument("--max-spread", type=int, default=d.max_spread, help="max bid/ask gap in cents")
        p.add_argument("--min-price", type=int, default=d.min_price, help="lowest price to buy, in cents")
        p.add_argument("--max-price", type=int, default=d.max_price, help="highest price to buy, in cents")
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
