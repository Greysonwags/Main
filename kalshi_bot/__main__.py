"""Command line: python -m kalshi_bot {status,scan,run,auto,arb} [--place]

`run` is a dry run unless --place is given; `auto` repeats `run --place` on a
timer. Orders only ever go to the demo environment, which uses fake money.
`arb` reads real Kalshi prices read-only (no key, no orders) to look for
locked-in-profit opportunities.
"""

import argparse
import json
import subprocess
import time
from datetime import datetime, timezone

import requests

from . import arb, report
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
    positions = [p for p in client.get_positions() if position_qty(p)]
    markets = {}
    for p in positions:
        try:
            markets[p["ticker"]] = client.get_market(p["ticker"])
        except KalshiError:
            pass  # shown as "?" rather than failing the whole screen
    parts = dict(
        balance=client.get_balance_cents(),
        trades=report.active_trades(positions, markets),
        resting=client.get_resting_orders(),
        settled=report.settled_results(client.get_settlements()),
    )
    print(report.render(**parts))
    if getattr(args, "copy", False):
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        copy_to_clipboard(json.dumps(report.snapshot(now=now, **parts)))


def copy_to_clipboard(text: str):
    try:
        subprocess.run(["pbcopy"], input=text.encode(), check=True)
        print("\nCopied! Open Home Base and click 'Paste update' in the Kalshi panel.")
    except (OSError, subprocess.CalledProcessError):
        print("\nCouldn't reach the clipboard. Copy everything on the next line instead:")
        print(text)


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


def cmd_auto(client, args, sleep=time.sleep):
    """Run `run --place` every args.every minutes until Ctrl+C (or args.rounds)."""
    args.place = True
    print(f"Auto-trading every {args.every:g} minutes on the demo exchange. Press Ctrl+C to stop.")
    round_no = 0
    try:
        while True:
            round_no += 1
            print(f"\n--- Round {round_no} at {datetime.now().strftime('%Y-%m-%d %H:%M')} ---")
            try:
                cmd_run(client, args)
            except (KalshiError, requests.RequestException) as e:
                # One bad round (Kalshi hiccup, Wi-Fi drop) shouldn't stop the robot.
                print(f"This round failed, will try again next time: {e}")
            if args.rounds and round_no >= args.rounds:
                break
            print(f"Sleeping {args.every:g} minutes...")
            sleep(args.every * 60)
    except KeyboardInterrupt:
        print("\nStopped.")


ARB_LOG = "arbs.jsonl"


def scan_arbs(client) -> list:
    print("Downloading open events...", end="", flush=True)
    events = client.get_events_with_markets(
        progress=lambda n: print(f"\rDownloading open events... {n} so far", end="", flush=True))
    print()
    exclusive = sum(1 for e in events if e.get("mutually_exclusive"))
    found = arb.find_arbs(events)
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    print(f"[{stamp}] Checked {len(events)} open events ({exclusive} with one-winner outcomes); "
          f"{len(found)} locked-in profit opportunit{'y' if len(found) == 1 else 'ies'}.")
    for a in found:
        print(f"  {a.event_ticker}  {a.title}")
        print(f"    Buy 1 NO on each of {len(a.legs)} outcomes: cost {dollars(a.cost)} + fees "
              f"{dollars(a.fees)}, guaranteed back at least {dollars(a.payout)} "
              f"-> profit {dollars(a.profit)} per set")
        for ticker, ask in a.legs:
            print(f"      NO {ticker} @ {ask}c")
        with open(ARB_LOG, "a") as f:
            f.write(json.dumps({"time": stamp, "event": a.event_ticker, "profit": a.profit,
                                "legs": a.legs}) + "\n")
    if not found:
        close = arb.near_misses(events)
        if close:
            print("  Closest ones (negative = would lose money):")
            for profit, ticker, title, n in close:
                print(f"    {dollars(profit):>8} per set  {ticker} ({n} outcomes) {title}")
    return found


def cmd_arb(client, args, sleep=time.sleep):
    """Look for arbitrage once, or every args.every minutes until Ctrl+C."""
    try:
        while True:
            try:
                scan_arbs(client)
            except (KalshiError, requests.RequestException) as e:
                if not args.every:
                    raise
                print(f"\nThis check failed, will try again next time: {e}")
            if not args.every:
                break
            sleep(args.every * 60)
    except KeyboardInterrupt:
        print("\nStopped.")


def main():
    parser = argparse.ArgumentParser(prog="kalshi_bot", description="Kalshi demo trading bot")
    sub = parser.add_subparsers(dest="command", required=True)
    st = sub.add_parser("status", help="home screen: balance, active trades, profit/loss")
    st.add_argument("--copy", action="store_true", help="also copy a snapshot for the Home Base dashboard")
    d = StrategyConfig()
    for name, help_text in (("scan", "list markets the strategy likes"),
                            ("run", "size orders and (with --place) submit them"),
                            ("auto", "repeat run --place on a timer until Ctrl+C")):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("--hours", type=float, default=48, help="only markets closing within N hours")
        p.add_argument("--min-volume", type=int, default=d.min_volume_24h, help="min contracts traded in 24h")
        p.add_argument("--max-spread", type=int, default=d.max_spread, help="max bid/ask gap in cents")
        p.add_argument("--min-price", type=int, default=d.min_price, help="lowest price to buy, in cents")
        p.add_argument("--max-price", type=int, default=d.max_price, help="highest price to buy, in cents")
        if name == "run":
            p.add_argument("--place", action="store_true", help="actually submit orders to demo")
        if name == "auto":
            p.add_argument("--every", type=float, default=60, help="minutes between rounds")
            p.add_argument("--rounds", type=int, default=0, help="stop after N rounds (0 = forever)")
    a = sub.add_parser("arb", help="look for locked-in profit on real prices (read-only)")
    a.add_argument("--demo", action="store_true", help="check demo prices instead of real ones")
    a.add_argument("--every", type=float, default=0, help="re-check every N minutes until Ctrl+C")
    args = parser.parse_args()

    try:
        if args.command == "arb":
            if args.demo:
                return cmd_arb(KalshiClient.from_env(), args)
            print("Reading real Kalshi prices (read-only: no login, no orders).")
            return cmd_arb(KalshiClient.public(), args)
        client = KalshiClient.from_env()
        {"status": cmd_status, "scan": cmd_scan, "run": cmd_run, "auto": cmd_auto}[args.command](client, args)
    except KalshiError as e:
        raise SystemExit(f"Error: {e}")


if __name__ == "__main__":
    main()
