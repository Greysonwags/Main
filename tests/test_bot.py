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


def test_skip_reasons_and_fixed_point_volume():
    from kalshi_bot.strategy import skip_reasons
    markets = [market("LOW", volume_24h=1), market("WIDE", yes_bid=70, yes_ask=90),
               market("FLIP", yes_bid=49, yes_ask=51),
               {"ticker": "FP", "yes_bid": 86, "yes_ask": 88, "volume_24h_fp": "750.00"}]
    assert skip_reasons(markets, StrategyConfig()) == {
        "low volume": 1, "spread too wide": 1, "no side in price range": 1}


def test_order_body_v2_maps_yes_no_onto_single_book():
    from kalshi_bot.client import order_body_v2
    yes = order_body_v2("T", "yes", 5, 88, "id")
    assert (yes["side"], yes["price"], yes["count"]) == ("bid", "0.8800", "5.00")
    no = order_body_v2("T", "no", 5, 91, "id")
    assert (no["side"], no["price"]) == ("ask", "0.0900")
    assert yes["self_trade_prevention_type"] == "taker_at_cross"


def test_run_skips_markets_with_positions_or_resting_orders(capsys):
    import argparse
    from kalshi_bot import __main__ as cli

    placed = []

    class Fake:
        def get_open_markets(self, max_close_ts=None):
            return [market("OWNED", volume_24h=900), market("WAITING", volume_24h=800),
                    market("NEW", volume_24h=700)]
        def get_balance_cents(self):
            return 50_000
        def get_positions(self):
            return [{"ticker": "OWNED", "position_fp": "5.00"}, {"ticker": "CLOSED", "position": 0}]
        def get_resting_orders(self):
            return [{"ticker": "WAITING"}]
        def place_limit_order(self, ticker, side, count, price):
            placed.append(ticker)
            return {"order_id": "x", "status": "resting"}

    args = argparse.Namespace(hours=48, min_volume=500, max_spread=3, min_price=80,
                              max_price=94, place=True)
    cli.cmd_run(Fake(), args)
    assert placed == ["NEW"]
    assert "Skipping 2 market(s)" in capsys.readouterr().out


def test_auto_places_each_round_and_survives_errors(capsys):
    import argparse
    from kalshi_bot import __main__ as cli
    from kalshi_bot.client import KalshiError

    calls = {"markets": 0}
    placed, sleeps = [], []

    class Fake:
        def get_open_markets(self, max_close_ts=None):
            calls["markets"] += 1
            if calls["markets"] == 1:
                raise KalshiError("GET /markets -> 503")
            return [market(f"M{calls['markets']}")]
        def get_balance_cents(self):
            return 50_000
        def get_positions(self):
            return []
        def get_resting_orders(self):
            return []
        def place_limit_order(self, ticker, side, count, price):
            placed.append(ticker)
            return {"order_id": "x"}

    args = argparse.Namespace(hours=48, min_volume=500, max_spread=3, min_price=80,
                              max_price=94, every=30, rounds=3)
    cli.cmd_auto(Fake(), args, sleep=sleeps.append)
    assert placed == ["M2", "M3"]
    assert sleeps == [1800, 1800]
    assert "This round failed" in capsys.readouterr().out


def test_status_home_screen(capsys):
    import argparse
    from kalshi_bot import __main__ as cli
    from kalshi_bot.client import KalshiError

    class Fake:
        def get_balance_cents(self):
            return 8_210
        def get_positions(self):
            return [
                {"ticker": "WIN", "position": 5, "market_exposure": 440},           # YES, bought at 88c
                {"ticker": "NOSIDE", "position_fp": "-5.00", "market_exposure_dollars": "4.5500"},
                {"ticker": "GONE", "position": 3, "market_exposure": 270},
                {"ticker": "OLD", "position": 0},
            ]
        def get_market(self, ticker):
            if ticker == "GONE":
                raise KalshiError("404")
            return {"WIN": {"title": "Will it rain?", "yes_bid": 95, "yes_ask": 97},
                    "NOSIDE": {"yes_bid_dollars": "0.1000", "yes_ask_dollars": "0.1200"}}[ticker]
        def get_resting_orders(self):
            return [{"ticker": "WAIT", "side": "ask", "price_dollars": "0.0900",
                     "remaining_count_fp": "5.00"}]
        def get_settlements(self):
            return [
                {"ticker": "A", "revenue": 500, "yes_total_cost": 450, "no_total_cost": 0},
                {"ticker": "B", "revenue_dollars": "0", "no_total_cost_dollars": "4.1000"},
            ]

    cli.cmd_status(Fake(), argparse.Namespace())
    out = capsys.readouterr().out
    assert "KALSHI DEMO" in out
    assert "Cash balance:   $82.10" in out
    assert "ACTIVE TRADES (3)" in out
    assert "5 YES  cost $4.40  worth now $4.75  (+$0.35)" in out       # 5 x 95c
    assert "5 NO  cost $4.55  worth now $4.40  (-$0.15)" in out        # NO bid = 100 - 12
    assert "worth now ?  (?)" in out
    assert "WAIT: buy 5 NO @ 91c" in out
    assert "Finished bets:  -$3.60   (1 won, 1 lost, 2 total)" in out
    assert "Open bets:      +$0.20" in out
    assert "Total:          -$3.40" in out
    assert "couldn't be priced" in out


def test_snapshot_for_dashboard():
    import json
    from kalshi_bot import report
    trades = [{"ticker": "A", "title": "", "side": "yes", "contracts": 5, "cost": 440, "value": 475, "pnl": 35},
              {"ticker": "B", "title": "", "side": "no", "contracts": 3, "cost": 270, "value": None, "pnl": None}]
    snap = report.snapshot(8210, trades, [{"ticker": "W", "side": "bid", "price_dollars": "0.88"}],
                           {"count": 2, "wins": 1, "losses": 1, "pnl": -360}, "2026-10-01T15:00:00+00:00")
    assert snap["kind"] == "kalshi-status" and snap["balance"] == 8210
    assert snap["waiting"] == ["W: buy YES @ 88c"]
    assert (snap["open_pnl"], snap["total_pnl"]) == (35, -325)
    json.dumps(snap)


def test_taker_fee():
    from kalshi_bot.arb import taker_fee_cents
    assert taker_fee_cents(50) == 2      # 0.07 x .5 x .5 = 1.75c -> 2c
    assert taker_fee_cents(90) == 1      # 0.63c -> 1c
    assert taker_fee_cents(90, 10) == 7  # 6.3c -> 7c


def test_finds_no_side_arbitrage():
    from kalshi_bot.arb import find_arbs, near_misses
    def mk(t, yes_bid):
        return {"ticker": t, "status": "active", "yes_bid": yes_bid, "yes_ask": yes_bid + 1}
    # NO asks = 100 - yes_bid: 70 + 70 + 70 = 210 for a guaranteed 200 -> loses
    fair = {"event_ticker": "FAIR", "mutually_exclusive": True,
            "markets": [mk("A", 30), mk("B", 30), mk("C", 30)]}
    # NO asks 60 + 60 + 60 = 180 + 3 x 2c fees = 186 for a guaranteed 200 -> +14c
    cheap = {"event_ticker": "CHEAP", "mutually_exclusive": True,
             "markets": [mk("A", 40), mk("B", 40), mk("C", 40)]}
    not_exclusive = dict(cheap, event_ticker="NX", mutually_exclusive=False)
    missing_leg = {"event_ticker": "GAP", "mutually_exclusive": True,
                   "markets": [mk("A", 40), {"ticker": "B", "status": "active"}]}
    arbs = find_arbs([fair, cheap, not_exclusive, missing_leg])
    assert [a.event_ticker for a in arbs] == ["CHEAP"]
    assert (arbs[0].cost, arbs[0].fees, arbs[0].payout, arbs[0].profit) == (180, 6, 200, 14)
    assert [r[1] for r in near_misses([fair, cheap])] == ["CHEAP", "FAIR"]


def test_public_client_is_read_only():
    import pytest
    from kalshi_bot.client import KalshiClient, KalshiError, REAL_BASE_URL

    class NoNetwork:
        def request(self, *a, **k):
            raise AssertionError("should not reach the network")

    real = KalshiClient.public(session=NoNetwork())
    assert real.base_url == REAL_BASE_URL
    with pytest.raises(KalshiError):
        real.place_limit_order("T", "yes", 1, 50)
    with pytest.raises(KalshiError):
        real._request("POST", "/portfolio/events/orders", json={})


def test_public_get_sends_no_auth_headers():
    from kalshi_bot.client import KalshiClient
    seen = {}

    class Resp:
        status_code, content = 200, b"{}"
        def json(self):
            return {"events": [], "cursor": ""}

    class Sess:
        def request(self, method, url, **kw):
            seen.update(url=url, headers=kw["headers"], params=kw["params"])
            return Resp()

    KalshiClient.public(session=Sess()).get_events_with_markets()
    assert seen["url"] == "https://external-api.kalshi.com/trade-api/v2/events"
    assert not any(h.startswith("KALSHI-") for h in seen["headers"])
    assert seen["params"]["with_nested_markets"] == "true"


def test_event_download_follows_cursor_and_flags_truncation():
    import pytest
    from kalshi_bot.client import KalshiClient, KalshiError

    class Resp:
        status_code, content = 200, b"x"
        def __init__(self, data):
            self.data = data
        def json(self):
            return self.data

    class Sess:
        def __init__(self, pages):
            self.pages = pages
        def request(self, method, url, **kw):
            return Resp(self.pages.pop(0))

    pages = [{"events": [{"event_ticker": str(i)}], "cursor": f"c{i}"} for i in range(24)]
    pages.append({"events": [{"event_ticker": "last"}], "cursor": ""})
    assert len(KalshiClient.public(session=Sess(pages)).get_events_with_markets()) == 25

    endless = [{"events": [{}], "cursor": "more"} for _ in range(3)]
    with pytest.raises(KalshiError, match="incomplete"):
        KalshiClient.public(session=Sess(endless)).get_events_with_markets(max_pages=3)
