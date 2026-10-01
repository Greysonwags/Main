"""Minimal Kalshi Trade API v2 client with RSA-PSS request signing.

Only talks to the demo environment (fake money). Docs:
https://docs.kalshi.com/getting_started/api_keys
"""

import base64
import os
import time
import uuid
from urllib.parse import urlparse

import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

DEMO_BASE_URL = "https://demo-api.kalshi.co/trade-api/v2"


class KalshiError(Exception):
    pass


def load_private_key(pem: str):
    return serialization.load_pem_private_key(pem.encode(), password=None)


def sign_request(private_key, timestamp_ms: str, method: str, path: str) -> str:
    """Kalshi signs `timestamp + METHOD + path` (path without query string)."""
    message = f"{timestamp_ms}{method.upper()}{path.split('?')[0]}".encode()
    signature = private_key.sign(
        message,
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
        hashes.SHA256(),
    )
    return base64.b64encode(signature).decode()


def price_cents(market: dict, field: str):
    """Read a price field in cents, accepting either the legacy integer-cents
    field (`yes_bid`) or the newer dollar-string field (`yes_bid_dollars`)."""
    dollars = market.get(f"{field}_dollars")
    if dollars not in (None, ""):
        return round(float(dollars) * 100)
    value = market.get(field)
    return int(value) if value is not None else None


class KalshiClient:
    def __init__(self, key_id: str, private_key, base_url: str = DEMO_BASE_URL, session=None):
        self.key_id = key_id
        self.private_key = private_key
        self.base_url = base_url.rstrip("/")
        self.base_path = urlparse(self.base_url).path
        self.session = session or requests.Session()

    @classmethod
    def from_env(cls):
        key_id = os.environ.get("KALSHI_API_KEY_ID")
        pem = os.environ.get("KALSHI_PRIVATE_KEY")
        key_path = os.environ.get("KALSHI_PRIVATE_KEY_PATH")
        if not pem and key_path:
            try:
                with open(os.path.expanduser(key_path)) as f:
                    pem = f.read()
            except FileNotFoundError:
                raise KalshiError(
                    f"Can't find your private key file at {key_path}. Move the key file "
                    "you downloaded from Kalshi there, or point KALSHI_PRIVATE_KEY_PATH at it."
                )
        if not key_id or not pem:
            raise KalshiError(
                "Set KALSHI_API_KEY_ID and either KALSHI_PRIVATE_KEY (PEM contents) "
                "or KALSHI_PRIVATE_KEY_PATH. Create a key at https://demo.kalshi.co/account/profile"
            )
        return cls(key_id, load_private_key(pem))

    def _request(self, method: str, path: str, params=None, json=None):
        timestamp = str(int(time.time() * 1000))
        headers = {
            "KALSHI-ACCESS-KEY": self.key_id,
            "KALSHI-ACCESS-TIMESTAMP": timestamp,
            "KALSHI-ACCESS-SIGNATURE": sign_request(
                self.private_key, timestamp, method, self.base_path + path
            ),
            "Content-Type": "application/json",
        }
        resp = self.session.request(
            method, self.base_url + path, params=params, json=json, headers=headers, timeout=20
        )
        if resp.status_code >= 400:
            raise KalshiError(f"{method} {path} -> {resp.status_code}: {resp.text[:500]}")
        return resp.json() if resp.content else {}

    def get_balance_cents(self) -> int:
        return int(self._request("GET", "/portfolio/balance")["balance"])

    def get_positions(self) -> list:
        return self._request("GET", "/portfolio/positions").get("market_positions", [])

    def get_resting_orders(self, max_pages: int = 10) -> list:
        """Orders still waiting on the book (placed but not yet filled)."""
        orders, cursor = [], None
        for _ in range(max_pages):
            params = {"status": "resting", "limit": 200}
            if cursor:
                params["cursor"] = cursor
            data = self._request("GET", "/portfolio/orders", params=params)
            orders.extend(data.get("orders", []))
            cursor = data.get("cursor")
            if not cursor:
                break
        return orders

    def get_open_markets(self, max_close_ts=None, max_pages: int = 5, page_size: int = 200) -> list:
        markets, cursor = [], None
        for _ in range(max_pages):
            params = {"status": "open", "limit": page_size}
            if max_close_ts:
                params["max_close_ts"] = int(max_close_ts)
            if cursor:
                params["cursor"] = cursor
            data = self._request("GET", "/markets", params=params)
            markets.extend(data.get("markets", []))
            cursor = data.get("cursor")
            if not cursor:
                break
        return markets

    def place_limit_order(self, ticker: str, side: str, count: int, price_cents: int) -> dict:
        """Buy `count` YES or NO contracts at `price_cents` or better."""
        data = self._request("POST", "/portfolio/events/orders", json=order_body_v2(
            ticker, side, count, price_cents, str(uuid.uuid4())))
        return data.get("order", data)


def order_body_v2(ticker: str, side: str, count: int, price_cents: int, client_order_id: str) -> dict:
    """Build a V2 order. V2 has a single YES book: buying YES at p is a bid at p,
    and buying NO at p is an ask (sell YES) at 100 - p. Prices are dollar strings
    and counts are fixed-point strings."""
    if side not in ("yes", "no"):
        raise ValueError(f"side must be 'yes' or 'no', got {side!r}")
    yes_price = price_cents if side == "yes" else 100 - price_cents
    return {
        "ticker": ticker,
        "client_order_id": client_order_id,
        "side": "bid" if side == "yes" else "ask",
        "count": f"{count}.00",
        "price": f"{yes_price / 100:.4f}",
        "time_in_force": "good_till_canceled",
        # Required by V2: if this order would match one of our own resting
        # orders, cancel the incoming (taker) side instead of self-trading.
        "self_trade_prevention_type": "taker_at_cross",
    }
