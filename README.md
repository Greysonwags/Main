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
python -m kalshi_bot status            # home screen: balance, active trades, profit/loss
python -m kalshi_bot status --copy     # also copy a snapshot to paste into the Home Base dashboard
python -m kalshi_bot scan              # markets the strategy likes (closing within 48h)
python -m kalshi_bot run               # dry run: shows the orders it would place
python -m kalshi_bot run --place       # sends those orders to the demo exchange
python -m kalshi_bot scan --hours 12   # narrow the window
python -m kalshi_bot scan --min-volume 10 --max-spread 10   # loosen filters (demo has little trading)
```

Placed orders are logged to `trades.jsonl`.

### Auto-run

```sh
python -m kalshi_bot auto --min-volume 10 --max-spread 10             # every 60 min until Ctrl+C
python -m kalshi_bot auto --every 30 --rounds 4                       # every 30 min, 4 times
caffeinate -i python -m kalshi_bot auto --min-volume 10 --max-spread 10  # macOS: stay awake
```

Each round is a `run --place`. A failed round is reported and retried next
round. It only runs while the Terminal window stays open and the computer is
awake.

## Arbitrage scanner (`kalshi_bot/arb.py`)

```sh
python -m kalshi_bot arb              # check real Kalshi prices once (no key needed)
python -m kalshi_bot arb --every 5    # re-check every 5 minutes, log finds to arbs.jsonl
python -m kalshi_bot arb --demo       # check demo prices instead
```

Looks for events where only one outcome can win and buying NO on every
outcome costs less, after fees, than the minimum it must pay back. Real prices
are read through a read-only connection that sends no key and refuses orders.
It only reports; it never trades.

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

---

# Golf outing demo (`golf_demo/`)

A working sales demo for golf courses: an outing inquiry page that gives the
golfer an instant price estimate, texts and emails them within seconds,
alerts course staff, follows up automatically on day 2, 5 and 10, and asks
last year's groups to rebook. The staff dashboard shows the open pipeline and
what got booked.

Nothing to install beyond Python 3.10+.

```sh
python -m golf_demo                 # then open http://localhost:8000
python -m golf_demo --port 9000     # use another port
python -m golf_demo followups       # send follow-ups that are due (run hourly once live)
```

- **Inquiry form** (what golfers see): http://localhost:8000/
- **Staff dashboard** (what the course sees): http://localhost:8000/dashboard

Leads are saved in `golf_demo_data/leads.json` (not committed). Delete that
file to start a demo fresh.

## Make it yours

Edit `golf_demo/config.py`: your company name, the course name, prices per
golfer, the weekday discount and the follow-up days. Message wording lives in
`golf_demo/messages.py`.

## Demo mode vs. real messages

With no accounts connected, every message is shown on screen and marked
"Demo mode (not sent)". To actually send them, set these in your terminal
before starting (never put them in the repo):

```sh
# Email, e.g. a Gmail account with an app password (Google Account > Security > App passwords)
export SMTP_HOST=smtp.gmail.com SMTP_PORT=587
export SMTP_USER=you@gmail.com SMTP_PASSWORD="your-app-password"

# Texts, from a Twilio account (twilio.com > Console)
export TWILIO_ACCOUNT_SID=AC... TWILIO_AUTH_TOKEN=... TWILIO_FROM=+15551234567

# Where hot-lead alerts go (use your own phone/email for demos)
export STAFF_EMAIL=you@gmail.com STAFF_PHONE=+15557654321
```

Texting notes:
- A Twilio **trial** account can only text numbers you have verified in the
  Twilio console, so for live demos either verify your own phone and hand it
  to the prospect, or upgrade the account.
- Before texting real customers in the US, the sending number must be
  registered for business texting (A2P 10DLC, done in the Twilio console),
  and people must opt in. The form's consent checkbox handles opt-in; texts
  are only sent when it's ticked, and every text says "Reply STOP to opt out".

## Running the demo on a sales call (about 5 minutes)

1. Share your screen on the inquiry form. "This is what a company sees when
   they want to book an outing at your course."
2. Ask the prospect for a realistic group: size, date, food. Type it in and
   point out the estimate updating live.
3. Use their email and phone (with real sending connected) and submit. Their
   phone buzzes within seconds. Pause and let that land.
4. Open the dashboard: "Here's what your staff gets: a hot lead, the
   estimated value, and the follow-ups already lined up."
5. Open the lead and click **Send next message now** to show a follow-up
   arriving. "If they go quiet, this keeps working so your staff doesn't
   have to remember."
6. Mark it booked: the follow-ups stop and the booked revenue shows up. "At
   the end of each month you'd see exactly what this brought in."
7. Close: "One extra outing pays for a year of this. Want me to set it up
   with your real prices?"
