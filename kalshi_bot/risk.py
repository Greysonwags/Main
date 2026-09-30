"""Risk limits applied to every order before it is sent."""

from dataclasses import dataclass


@dataclass
class RiskConfig:
    contracts_per_order: int = 5
    max_cost_per_order: int = 500  # cents ($5)
    max_cost_per_run: int = 2000  # cents ($20)
    max_orders_per_run: int = 5
    min_balance_after: int = 1000  # cents; never spend the balance below $10


@dataclass
class ApprovedOrder:
    idea: object
    count: int
    cost: int  # cents


def size_orders(ideas, balance: int, held_tickers: set, cfg: RiskConfig) -> list:
    """Pick which ideas to act on and how many contracts, within the limits."""
    approved, spent = [], 0
    for idea in ideas:
        if len(approved) >= cfg.max_orders_per_run:
            break
        if idea.ticker in held_tickers:
            continue
        count = min(cfg.contracts_per_order, cfg.max_cost_per_order // idea.price)
        cost = count * idea.price
        if count <= 0:
            continue
        if spent + cost > cfg.max_cost_per_run:
            continue
        if balance - spent - cost < cfg.min_balance_after:
            continue
        approved.append(ApprovedOrder(idea, count, cost))
        spent += cost
    return approved
