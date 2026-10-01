"""Builds the `status` home screen: balance, active trades and profit/loss.

Kalshi has been moving fields from integer cents/counts (`revenue`,
`position`) to strings (`revenue_dollars`, `position_fp`), so every read here
accepts either form.
"""

from .client import price_cents


def dollars(cents) -> str:
    sign = "-" if cents < 0 else ""
    return f"{sign}${abs(cents) / 100:,.2f}"


def signed(cents) -> str:
    return ("+" if cents > 0 else "") + dollars(cents)


def count_of(d: dict, field: str) -> float:
    fp = d.get(f"{field}_fp")
    return float(fp) if fp not in (None, "") else float(d.get(field) or 0)


def bid_for_side(market: dict, side: str):
    """What you could sell a contract for right now, in cents."""
    bid = price_cents(market, f"{side}_bid")
    if bid is None:
        other_ask = price_cents(market, f"{'no' if side == 'yes' else 'yes'}_ask")
        bid = 100 - other_ask if other_ask is not None else None
    return bid


def active_trades(positions: list, markets: dict) -> list:
    """One row per open position, valued at the current bid.
    `markets` maps ticker -> market dict (missing if the lookup failed)."""
    rows = []
    for p in positions:
        qty = count_of(p, "position")
        if not qty:
            continue
        side = "yes" if qty > 0 else "no"
        contracts = abs(qty)
        cost = price_cents(p, "market_exposure") or 0
        market = markets.get(p["ticker"])
        bid = bid_for_side(market, side) if market else None
        value = round(contracts * bid) if bid is not None else None
        rows.append({
            "ticker": p["ticker"],
            "title": (market or {}).get("title", ""),
            "side": side,
            "contracts": contracts,
            "cost": cost,
            "value": value,
            "pnl": value - cost if value is not None else None,
        })
    return rows


def settled_results(settlements: list) -> dict:
    """Wins, losses and profit from markets that already paid out."""
    wins = losses = pnl = 0
    for s in settlements:
        cost = (price_cents(s, "yes_total_cost") or 0) + (price_cents(s, "no_total_cost") or 0)
        result = (price_cents(s, "revenue") or 0) - cost - (price_cents(s, "fee_cost") or 0)
        pnl += result
        if result > 0:
            wins += 1
        elif result < 0:
            losses += 1
    return {"count": len(settlements), "wins": wins, "losses": losses, "pnl": pnl}


def describe_order(o: dict) -> str:
    """One line for a waiting order, from either the V1 or V2 order shape."""
    remaining = count_of(o, "remaining_count")
    side = o.get("side", "")
    if side in ("bid", "ask"):  # V2 single YES book
        yes_price = price_cents(o, "price")
        what = "YES" if side == "bid" else "NO"
        price = yes_price if side == "bid" else (100 - yes_price if yes_price is not None else None)
    else:
        what = side.upper() or "?"
        price = price_cents(o, f"{side}_price") if side else None
    price_txt = f" @ {price}c" if price is not None else ""
    qty_txt = f"{remaining:g} " if remaining else ""
    return f"{o.get('ticker', '?')}: buy {qty_txt}{what}{price_txt}"


def snapshot(balance: int, trades: list, resting: list, settled: dict, now: str) -> dict:
    """Compact, JSON-ready status for pasting into the Home Base dashboard.
    Money is in cents."""
    open_pnl = sum(t["pnl"] for t in trades if t["pnl"] is not None)
    return {
        "kind": "kalshi-status",
        "v": 1,
        "at": now,
        "balance": balance,
        "trades": trades,
        "waiting": [describe_order(o) for o in resting],
        "settled": settled,
        "open_pnl": open_pnl,
        "total_pnl": settled["pnl"] + open_pnl,
    }


def render(balance: int, trades: list, resting: list, settled: dict) -> str:
    lines = ["=" * 50, " KALSHI DEMO  (practice account, fake money)", "=" * 50,
             f"Cash balance:   {dollars(balance)}", ""]

    lines.append(f"ACTIVE TRADES ({len(trades)})")
    if not trades:
        lines.append("  none")
    for t in trades:
        value = dollars(t["value"]) if t["value"] is not None else "?"
        pnl = signed(t["pnl"]) if t["pnl"] is not None else "?"
        lines.append(f"  {t['ticker']}")
        if t["title"]:
            lines.append(f"    {t['title']}")
        lines.append(f"    {t['contracts']:g} {t['side'].upper()}  cost {dollars(t['cost'])}"
                     f"  worth now {value}  ({pnl})")
    lines.append("")

    lines.append(f"WAITING ORDERS ({len(resting)})")
    if not resting:
        lines.append("  none")
    for o in resting:
        lines.append(f"  {describe_order(o)}")
    lines.append("")

    open_pnl = sum(t["pnl"] for t in trades if t["pnl"] is not None)
    lines += [
        "PROFIT / LOSS",
        f"  Finished bets:  {signed(settled['pnl'])}   "
        f"({settled['wins']} won, {settled['losses']} lost, {settled['count']} total)",
        f"  Open bets:      {signed(open_pnl)}   (if sold at today's prices)",
        f"  Total:          {signed(settled['pnl'] + open_pnl)}",
    ]
    if any(t["pnl"] is None for t in trades):
        lines.append("  (some open bets couldn't be priced and aren't counted)")
    return "\n".join(lines)
