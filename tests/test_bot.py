import base64

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from kalshi_bot.client import KalshiClient, price_cents, sign_request
from kalshi_bot.risk import RiskConfig, size_orders
from kalshi_bot.strategy import StrategyConfig, TradeIdea, evaluate, find_trades


def market(ticker="T", yes_bid=86, yes_ask=88, volume_24h=1000, **extra):
    return {"ticker": ticker, "title": ticker, "yes_bid": yes_bid, "yes_ask": yes_ask,
            "volume_24h": volume_24h, **extra}


def test_signature_verifies_and_ignores_query_string():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    sig = sign_request(key, "1700000000000", "get", "/trade-api/v2/markets?limit=5")
    key.public_key().verify(
        base64.b64decode(sig),
        b"1700000000000GET/trade-api/v2/markets",
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
        hashes.SHA256(),
    )


def test_request_signs_full_path_and_sends_headers():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    calls = []

    class FakeResp:
        status_code, content = 200, b"{}"
        def json(self):
            return {"balance": 12345}

    class FakeSession:
        def request(self, method, url, **kw):
            calls.append((method, url, kw["headers"]))
            return FakeResp()

    client = KalshiClient("key-id", key, session=FakeSession())
    assert client.get_balance_cents() == 12345
    method, url, headers = calls[0]
    assert url == "https://demo-api.kalshi.co/trade-api/v2/portfolio/balance"
    assert headers["KALSHI-ACCESS-KEY"] == "key-id"
    ts = headers["KALSHI-ACCESS-TIMESTAMP"]
    key.public_key().verify(
        base64.b64decode(headers["KALSHI-ACCESS-SIGNATURE"]),
        f"{ts}GET/trade-api/v2/portfolio/balance".encode(),
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
        hashes.SHA256(),
    )


def test_price_cents_accepts_dollar_strings():
    assert price_cents({"yes_bid_dollars": "0.5600"}, "yes_bid") == 56
    assert price_cents({"yes_bid": 56}, "yes_bid") == 56
    assert price_cents({}, "yes_bid") is None


def test_buys_yes_favorite():
    idea = evaluate(market(), StrategyConfig())
    assert (idea.side, idea.price) == ("yes", 88)


def test_buys_no_favorite_using_implied_ask():
    idea = evaluate(market(yes_bid=10, yes_ask=12), StrategyConfig())
    assert (idea.side, idea.price) == ("no", 90)


def test_skips_illiquid_wide_or_coinflip_markets():
    cfg = StrategyConfig()
    assert evaluate(market(volume_24h=10), cfg) is None
    assert evaluate(market(yes_bid=80, yes_ask=88), cfg) is None
    assert evaluate(market(yes_bid=49, yes_ask=51), cfg) is None
    assert evaluate(market(yes_bid=0, yes_ask=0), cfg) is None


def test_find_trades_sorted_by_volume():
    ideas = find_trades([market("A", volume_24h=600), market("B", volume_24h=5000)], StrategyConfig())
    assert [i.ticker for i in ideas] == ["B", "A"]


def idea(ticker, price=90):
    return TradeIdea(ticker, ticker, "yes", price, "")


def test_risk_limits():
    cfg = RiskConfig(contracts_per_order=5, max_cost_per_order=500, max_cost_per_run=1000,
                     max_orders_per_run=5, min_balance_after=1000)
    orders = size_orders([idea("HELD"), idea("A"), idea("B"), idea("C")], 100_000, {"HELD"}, cfg)
    # 500 // 90 = 5 contracts at 450c each; third order would exceed the $10 run cap.
    assert [(o.idea.ticker, o.count, o.cost) for o in orders] == [("A", 5, 450), ("B", 5, 450)]


def test_risk_keeps_minimum_balance():
    assert size_orders([idea("A")], 1200, set(), RiskConfig()) == []
