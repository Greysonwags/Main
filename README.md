# Kalshi demo trading bot

A small bot that scans Kalshi markets and places practice orders on the
**demo exchange** (fake money). It cannot reach your real-money account.

## Setup

1. Create a demo account at https://demo.kalshi.co and generate an API key
   (Account → API Keys). Save the downloaded private key file somewhere safe,
   outside this repo.
2. Install dependencies: `pip install -r requirements.txt`
3. Set credentials in your shell (never commit them):

   ```sh
   export KALSHI_API_KEY_ID="your-key-id"
   export KALSHI_PRIVATE_KEY_PATH="$HOME/kalshi-demo.pem"
   # or KALSHI_PRIVATE_KEY="-----BEGIN RSA PRIVATE KEY-----..." (e.g. as an environment secret)
   ```

## Usage

```sh
python -m kalshi_bot status            # demo balance and open positions
python -m kalshi_bot scan              # markets the strategy likes (closing within 48h)
python -m kalshi_bot run               # dry run: shows the orders it would place
python -m kalshi_bot run --place       # sends those orders to the demo exchange
python -m kalshi_bot scan --hours 12   # narrow the window
python -m kalshi_bot scan --min-volume 10 --max-spread 10   # loosen filters (demo has little trading)
```

Placed orders are logged to `trades.jsonl`.

## Strategy (`kalshi_bot/strategy.py`)

Buys the heavy favorite (YES or NO priced 80–94¢) in markets with at least
500 contracts of 24h volume and a bid/ask spread of 3¢ or less. It's an
example to learn the mechanics, not a proven edge: favorites win often but
pay little, and one upset wipes out several wins. Tune `StrategyConfig` or
write your own `evaluate()`.

## Risk limits (`kalshi_bot/risk.py`)

Per run: at most 5 orders, 5 contracts and $5 per order, $20 total, never
drops the balance below $10, and skips markets you already hold.

## Tests

`python -m pytest`
