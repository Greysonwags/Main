"""Finds "buy NO on every outcome" arbitrage in mutually exclusive events.

In an event where at most one outcome can resolve YES (e.g. temperature
brackets), buying one NO contract on each of its n markets pays at least
(n - 1) dollars whatever happens, because at most one NO loses. If the NOs
cost less than that, after fees, the difference is locked-in profit.

This only needs the outcomes to be mutually exclusive, not exhaustive, so it
stays safe even if none of them resolves YES (then every NO pays and profit
is bigger). The YES-side version (buy YES on all outcomes) needs exactly one
to win, so it is deliberately not used here.
"""

import math
from dataclasses import dataclass

from .strategy import ask_for_side


def taker_fee_cents(price_cents: int, count: int = 1) -> int:
    """Kalshi's taker fee: 7% x count x P x (1 - P), rounded up to the cent."""
    p = price_cents / 100
    return math.ceil(round(0.07 * count * p * (1 - p) * 100, 6))


@dataclass
class Arb:
    event_ticker: str
    title: str
    legs: list  # [(market ticker, NO ask in cents)]
    cost: int  # cents for one NO on every leg
    fees: int  # cents
    payout: int  # guaranteed minimum, cents

    @property
    def profit(self) -> int:
        return self.payout - self.cost - self.fees


def check_event(event: dict):
    """Return an Arb for one set of NOs if it locks in a profit, else None."""
    if not event.get("mutually_exclusive"):
        return None
    markets = [m for m in event.get("markets", []) if m.get("status") in (None, "active", "open")]
    if len(markets) < 2:
        return None
    legs = []
    for m in markets:
        ask = ask_for_side(m, "no")
        if ask is None or not 1 <= ask <= 99:
            return None  # can't buy every leg, so no guarantee
        legs.append((m["ticker"], ask))
    cost = sum(a for _, a in legs)
    fees = sum(taker_fee_cents(a) for _, a in legs)
    arb = Arb(event.get("event_ticker", "?"), event.get("title", ""), legs, cost, fees,
              payout=(len(legs) - 1) * 100)
    return arb if arb.profit > 0 else None


def near_misses(events: list, limit: int = 5) -> list:
    """Closest non-profitable events, to show how far prices are from an arb."""
    rows = []
    for e in events:
        if not e.get("mutually_exclusive"):
            continue
        markets = [m for m in e.get("markets", []) if m.get("status") in (None, "active", "open")]
        asks = [ask_for_side(m, "no") for m in markets]
        if len(asks) < 2 or any(a is None or not 1 <= a <= 99 for a in asks):
            continue
        profit = (len(asks) - 1) * 100 - sum(asks) - sum(taker_fee_cents(a) for a in asks)
        rows.append((profit, e.get("event_ticker", "?"), e.get("title", ""), len(asks)))
    return sorted(rows, reverse=True)[:limit]


def find_arbs(events: list) -> list:
    return sorted((a for e in events if (a := check_event(e))), key=lambda a: -a.profit)
