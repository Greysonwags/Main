import threading
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone

import pytest

from golf_demo import messages
from golf_demo.leads import (InvalidLead, LeadStore, due_message, estimate, next_follow_up_kind,
                             next_scheduled, normalize_phone, parse_form, priority)
from golf_demo.notify import Sender
from golf_demo.server import run_due_follow_ups, serve, set_status

TODAY = date(2026, 10, 1)


def form(**extra):
    return {"name": "Jamie Cole", "email": "jamie@example.com", "phone": "(555) 201-3344",
            "sms_ok": "yes", "company": "Acme", "event_type": "Corporate outing",
            "date": "2027-05-15", "players": "48", "format": "18", "food": "buffet", **extra}


def test_estimate_weekend_vs_weekday():
    saturday = estimate(48, "18", "buffet", date(2027, 5, 15))
    assert saturday["mid"] == 4800 and not saturday["weekday"]  # (65 + 35) * 48
    assert (saturday["low"], saturday["high"]) == (4300, 5300)
    tuesday = estimate(48, "18", "buffet", date(2027, 5, 11))
    assert tuesday["weekday"] and tuesday["mid"] == 4100  # 15% off, to the nearest $50
    assert estimate(72, "9", "none", date(2027, 5, 15))["shotgun"]


def test_parse_form_builds_lead_and_normalizes_phone():
    lead = parse_form(form(), TODAY)
    assert lead["phone"] == "+15552013344" and lead["sms_ok"]
    assert lead["status"] == "new" and lead["estimate"]["mid"] == 4800
    assert not parse_form(form(sms_ok=""), TODAY)["sms_ok"]
    assert not parse_form(form(phone=""), TODAY)["sms_ok"]


@pytest.mark.parametrize("bad", [
    {"name": ""}, {"email": "nope"}, {"date": "2026-09-01"}, {"date": ""},
    {"players": "4"}, {"players": "lots"}, {"format": "36"}, {"phone": "12"},
])
def test_parse_form_rejects_bad_input(bad):
    with pytest.raises(InvalidLead):
        parse_form(form(**bad), TODAY)


def test_normalize_phone():
    assert normalize_phone("555-201-3344") == "+15552013344"
    assert normalize_phone("1 555 201 3344") == "+15552013344"
    assert normalize_phone("+44 20 7946 0958") == "+442079460958"
    assert normalize_phone("201-3344") == ""


def test_priority_hot_when_big_or_soon():
    lead = parse_form(form(), TODAY)
    assert priority(lead, TODAY) == "warm"
    assert priority(parse_form(form(players="100"), TODAY), TODAY) == "hot"
    assert priority(parse_form(form(date="2026-10-20"), TODAY), TODAY) == "hot"


def at(lead, days):
    return datetime.fromisoformat(lead["created"]) + timedelta(days=days, minutes=1)


def sent(lead, kind):
    lead["sent"].append({"kind": kind})


def test_follow_ups_go_out_in_order_and_stop_when_booked():
    lead = parse_form(form(), TODAY)
    assert due_message(lead, at(lead, 1)) is None
    assert due_message(lead, at(lead, 2)) == "followup_1"
    sent(lead, "followup_1")
    assert due_message(lead, at(lead, 3)) is None
    assert due_message(lead, at(lead, 5)) == "followup_2"
    lead["status"] = "booked"
    assert due_message(lead, at(lead, 10)) is None
    assert next_scheduled(lead)[0] == "rebook"


def test_overdue_follow_ups_send_only_the_latest():
    lead = parse_form(form(), TODAY)
    assert due_message(lead, at(lead, 11)) == "followup_3"
    sent(lead, "followup_3")
    assert due_message(lead, at(lead, 11)) is None
    assert next_follow_up_kind(lead) is None


def test_follow_up_sent_early_is_not_repeated_later():
    lead = parse_form(form(), TODAY)
    assert next_follow_up_kind(lead) == "followup_1"
    sent(lead, "followup_1")
    sent(lead, "followup_2")  # sent early from the dashboard during a demo
    assert due_message(lead, at(lead, 5)) is None
    assert due_message(lead, at(lead, 10)) == "followup_3"


def test_rebook_after_the_event_and_nothing_for_lost_leads():
    lead = parse_form(form(), TODAY)
    lead["status"] = "booked"
    event = datetime(2027, 5, 15, tzinfo=timezone.utc)
    assert due_message(lead, event + timedelta(days=299)) is None
    assert due_message(lead, event + timedelta(days=300)) == "rebook"
    lead["status"] = "lost"
    assert due_message(lead, event + timedelta(days=400)) is None
    assert next_scheduled(lead) is None


def test_messages_mention_the_essentials():
    lead = parse_form(form(), TODAY)
    reply = messages.guest_confirmation(lead)
    assert "$4,300 to $5,300" in reply["email"] and "Saturday, May 15, 2027" in reply["sms"]
    assert "STOP" in reply["sms"]
    assert messages.staff_alert(lead, "hot")["subject"].startswith("HOT LEAD")
    for kind in ("followup_1", "followup_2", "followup_3", "rebook"):
        assert "Jamie" in messages.follow_up(lead, kind)["sms"]


def test_sender_without_credentials_is_demo_mode():
    lead = parse_form(form(), TODAY)
    entry = Sender(env={}).to_guest(lead, "confirmation", messages.guest_confirmation(lead))
    assert entry["email_status"] == "demo" and entry["sms_status"] == "demo"
    lead["sms_ok"] = False
    entry = Sender(env={}).to_guest(lead, "confirmation", messages.guest_confirmation(lead))
    assert entry["sms_status"].startswith("skipped")


def test_run_due_follow_ups_and_status(tmp_path):
    store = LeadStore(tmp_path / "leads.json")
    lead = parse_form(form(), TODAY)
    store.add(lead)
    sender = Sender(env={})
    assert run_due_follow_ups(store, sender, now=at(lead, 2)) == 1
    assert run_due_follow_ups(store, sender, now=at(lead, 2)) == 0
    set_status(store, lead["id"], "booked")
    saved = store.get(lead["id"])
    assert saved["status"] == "booked" and "booked_at" in saved
    assert set_status(store, lead["id"], "bogus") is None


@pytest.fixture
def app(tmp_path):
    store = LeadStore(tmp_path / "leads.json")
    httpd = serve(store, Sender(env={}), "127.0.0.1", 0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}", store
    httpd.shutdown()


def post(url, data):
    body = urllib.parse.urlencode(data).encode()
    with urllib.request.urlopen(urllib.request.Request(url, data=body)) as r:
        return r.status, r.read().decode()


def test_web_flow_end_to_end(app):
    base, store = app
    with urllib.request.urlopen(base + "/") as r:
        assert "Plan your event" in r.read().decode()

    status, page = post(base + "/inquire", form(name="Jamie <b>Cole</b>"))
    assert status == 200 and "$4,300 to $5,300" in page
    assert "<b>Cole</b>" not in page  # user input is escaped
    (lead,) = store.all()
    assert [m["kind"] for m in lead["sent"]] == ["confirmation", "staff_alert"]

    with urllib.request.urlopen(base + "/dashboard") as r:
        assert "$4,800" in r.read().decode()

    status, page = post(f"{base}/dashboard/lead/{lead['id']}/send-next", {})
    assert "Sent: Follow-up 1" in page
    post(f"{base}/dashboard/lead/{lead['id']}/status", {"status": "booked"})
    assert store.get(lead["id"])["status"] == "booked"

    with pytest.raises(urllib.error.HTTPError) as err:
        post(base + "/inquire", form(email="bad"))
    assert err.value.code == 400 and "valid email" in err.value.read().decode()
