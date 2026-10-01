"""Example strategy: buy the heavy favorite in liquid markets that close soon.

This is a starting point to learn the mechanics, not a proven edge. Favorites
win often but pay little, and one upset can erase many small wins.
"""

from dataclasses import dataclass

from .client import price_cents


@dataclass
class StrategyConfig:
    min_price: int = 80  # cents; only buy a side priced at least this high
    max_price: int = 94  # cents; above this the payout is too small to bother
    max_spread: int = 3  # cents between best bid and ask
    min_volume_24h: int = 500  # contracts traded in the last 24h


@dataclass
class TradeIdea:
    ticker: str
    title: str
    side: str  # "yes" or "no"
    price: int  # limit price in cents
    reason: str


def ask_for_side(market: dict, side: str):
    """Best ask for a side in cents. NO ask is implied by 100 - YES bid if absent."""
    ask = price_cents(market, f"{side}_ask")
    if ask is None:
        other_bid = price_cents(market, f"{'no' if side == 'yes' else 'yes'}_bid")
        ask = 100 - other_bid if other_bid is not None else None
    return ask


def volume_24h(market: dict) -> int:
    """24h volume, accepting the newer fixed-point string field if present."""
    fp = market.get("volume_24h_fp")
    if fp not in (None, ""):
        return int(float(fp))
    return int(market.get("volume_24h") or 0)


def check(market: dict, cfg: StrategyConfig):
    """Return (TradeIdea, None) if the market qualifies, else (None, reason)."""
    volume = volume_24h(market)
    if volume < cfg.min_volume_24h:
        return None, "low volume"

    yes_bid, yes_ask = price_cents(market, "yes_bid"), price_cents(market, "yes_ask")
    if not yes_bid or not yes_ask:
        return None, "no bids/asks"
    if yes_ask - yes_bid > cfg.max_spread:
        return None, "spread too wide"

    for side in ("yes", "no"):
        ask = ask_for_side(market, side)
        if ask is not None and cfg.min_price <= ask <= cfg.max_price:
            return TradeIdea(
                ticker=market["ticker"],
                title=market.get("title", ""),
                side=side,
                price=ask,
                reason=f"{side.upper()} favorite at {ask}c, spread {yes_ask - yes_bid}c, 24h vol {volume}",
            ), None
    return None, "no side in price range"


def evaluate(market: dict, cfg: StrategyConfig):
    """Return a TradeIdea for the market, or None if it doesn't qualify."""
    return check(market, cfg)[0]


def skip_reasons(markets: list, cfg: StrategyConfig) -> dict:
    """Count why markets were rejected, e.g. {"low volume": 120}."""
    counts = {}
    for m in markets:
        reason = check(m, cfg)[1]
        if reason:
            counts[reason] = counts.get(reason, 0) + 1
    return counts


def find_trades(markets: list, cfg: StrategyConfig) -> list:
    ideas = [idea for m in markets if (idea := evaluate(m, cfg))]
    # Prefer the most liquid markets first.
    volume = {m["ticker"]: volume_24h(m) for m in markets}
    return sorted(ideas, key=lambda i: volume[i.ticker], reverse=True)
