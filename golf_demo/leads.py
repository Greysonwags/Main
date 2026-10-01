"""Outing leads: price estimates, priority, follow-up timing and storage.

A lead is a plain dict so it saves straight to JSON:
    id, created (ISO time), name, email, phone, sms_ok, company, event_type,
    date (ISO date), players, format, food, notes, status, estimate, sent
`status` is new -> booked or lost. `sent` lists every message that went out.
"""

import json
import secrets
import threading
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import config

STATUSES = ("new", "booked", "lost")


class InvalidLead(ValueError):
    pass


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def round_to(amount: float, step: int = 50) -> int:
    return int(round(amount / step) * step)


def estimate(players: int, fmt: str, food: str, event_date: date) -> dict:
    """Price range shown to the guest; `mid` is what the staff dashboard counts."""
    per_player = config.FORMATS[fmt][1] + config.FOOD[food][1]
    total = per_player * players
    weekday = event_date.weekday() < 4
    if weekday:
        total *= 1 - config.WEEKDAY_DISCOUNT
    spread = config.ESTIMATE_SPREAD
    return {
        "low": round_to(total * (1 - spread)),
        "high": round_to(total * (1 + spread)),
        "mid": round_to(total),
        "per_player": per_player,
        "weekday": weekday,
        "shotgun": players >= config.SHOTGUN_MIN_PLAYERS,
    }


def priority(lead: dict, today: date) -> str:
    """Hot leads are big or soon; staff should call those first."""
    days_out = (date.fromisoformat(lead["date"]) - today).days
    return "hot" if lead["estimate"]["mid"] >= 5000 or days_out <= 45 else "warm"


def normalize_phone(raw: str) -> str:
    """US numbers to +1XXXXXXXXXX (the format texting needs); '' if it can't tell."""
    digits = "".join(c for c in raw if c.isdigit())
    if raw.strip().startswith("+") and 8 <= len(digits) <= 15:
        return "+" + digits
    if len(digits) == 10:
        return "+1" + digits
    if len(digits) == 11 and digits[0] == "1":
        return "+" + digits
    return ""


def parse_form(form: dict, today: date) -> dict:
    """Validate the inquiry form and build a new lead. Raises InvalidLead."""
    get = lambda k: (form.get(k) or "").strip()
    name, email, phone = get("name"), get("email"), get("phone")
    if not name:
        raise InvalidLead("Please tell us your name.")
    if "@" not in email:
        raise InvalidLead("Please enter a valid email address.")
    try:
        event_date = date.fromisoformat(get("date"))
    except ValueError:
        raise InvalidLead("Please pick a date for your event.")
    if event_date <= today:
        raise InvalidLead("Please pick a date in the future.")
    try:
        players = int(get("players"))
    except ValueError:
        raise InvalidLead("Please enter how many golfers you expect.")
    if not 8 <= players <= 288:
        raise InvalidLead("Outings are for groups of 8 to 288 golfers.")
    fmt, food = get("format"), get("food")
    if fmt not in config.FORMATS or food not in config.FOOD:
        raise InvalidLead("Please choose a golf format and a food option.")
    phone = normalize_phone(phone)
    if get("phone") and not phone:
        raise InvalidLead("Please enter a valid mobile number, or leave it blank.")
    sms_ok = form.get("sms_ok") == "yes" and bool(phone)
    return {
        "id": secrets.token_hex(4),
        "created": now_utc().isoformat(timespec="seconds"),
        "name": name, "email": email, "phone": phone, "sms_ok": sms_ok,
        "company": get("company"), "event_type": get("event_type") or "Outing",
        "date": event_date.isoformat(), "players": players,
        "format": fmt, "food": food, "notes": get("notes"),
        "status": "new",
        "estimate": estimate(players, fmt, food, event_date),
        "sent": [],
    }


def follow_up_schedule(lead: dict) -> list:
    """(kind, when) for every automatic message this lead can get."""
    created = datetime.fromisoformat(lead["created"])
    steps = [(f"followup_{i}", created + timedelta(days=d))
             for i, d in enumerate(config.FOLLOW_UP_DAYS, start=1)]
    event_day = datetime.combine(date.fromisoformat(lead["date"]), datetime.min.time(),
                                 tzinfo=timezone.utc)
    steps.append(("rebook", event_day + timedelta(days=config.REBOOK_AFTER_DAYS)))
    return steps


def due_message(lead: dict, now: datetime):
    """The one automatic message to send now, or None.

    Follow-ups go only to leads that haven't booked or said no; the rebook
    note goes only to booked ones. If several follow-ups are overdue (the app
    was off), only the latest is sent, so nobody gets three at once.
    """
    sent = {m["kind"] for m in lead["sent"]}
    schedule = follow_up_schedule(lead)
    if lead["status"] == "new":
        followups = schedule[:-1]
        done = max((i for i, (kind, _) in enumerate(followups) if kind in sent), default=-1)
        due = [kind for i, (kind, when) in enumerate(followups) if i > done and when <= now]
        return due[-1] if due else None
    if lead["status"] == "booked":
        kind, when = schedule[-1]
        if when <= now and kind not in sent:
            return kind
    return None


def next_follow_up_kind(lead: dict):
    """The next follow-up in order, ignoring timing (for sending one early in a demo)."""
    sent = {m["kind"] for m in lead["sent"]}
    if lead["status"] == "booked":
        return None if "rebook" in sent else "rebook"
    if lead["status"] != "new":
        return None
    followups = [kind for kind, _ in follow_up_schedule(lead)[:-1]]
    done = max((i for i, kind in enumerate(followups) if kind in sent), default=-1)
    return followups[done + 1] if done + 1 < len(followups) else None


def next_scheduled(lead: dict):
    """(kind, when) of the next automatic message in line (it may be overdue), or None."""
    kind = next_follow_up_kind(lead)
    if kind is None:
        return None
    return kind, dict(follow_up_schedule(lead))[kind]


class LeadStore:
    """Leads in one JSON file. Fine for a demo and for a handful of courses."""

    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.Lock()

    def all(self) -> list:
        with self.lock:
            return self._read()

    def get(self, lead_id: str):
        return next((l for l in self.all() if l["id"] == lead_id), None)

    def add(self, lead: dict):
        with self.lock:
            leads = self._read()
            leads.append(lead)
            self._write(leads)

    def update(self, lead_id: str, fn):
        """Apply fn(lead) under the lock and save. Returns the lead or None."""
        with self.lock:
            leads = self._read()
            lead = next((l for l in leads if l["id"] == lead_id), None)
            if lead is not None:
                fn(lead)
                self._write(leads)
            return lead

    def _read(self) -> list:
        if not self.path.exists():
            return []
        return json.loads(self.path.read_text())

    def _write(self, leads: list):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(leads, indent=2))
        tmp.replace(self.path)
