"""The web app: the course's inquiry form plus the staff dashboard.

Routes:
    GET  /                               inquiry form (what golfers see)
    POST /inquire                        save lead, reply instantly, alert staff
    GET  /dashboard                      staff view of every lead
    GET  /dashboard/lead/<id>            one lead, its messages and what's next
    POST /dashboard/lead/<id>/status     mark booked or lost
    POST /dashboard/lead/<id>/send-next  send the next follow-up now (for demos)
    POST /dashboard/run-followups        send every follow-up that is due
"""

import re
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, unquote, urlparse

from . import messages, pages
from .leads import (InvalidLead, LeadStore, due_message, next_follow_up_kind, now_utc,
                    parse_form, priority)
from .notify import Sender

LEAD_PATH = re.compile(r"^/dashboard/lead/([0-9a-f]+)(/status|/send-next)?$")


def handle_inquiry(store: LeadStore, sender: Sender, form: dict, today: date):
    """Save the lead, send the instant reply and staff alert. Returns (lead, guest entry)."""
    lead = parse_form(form, today)
    guest = sender.to_guest(lead, "confirmation", messages.guest_confirmation(lead))
    staff = sender.to_staff(messages.staff_alert(lead, priority(lead, today)))
    lead["sent"] += [guest, staff]
    store.add(lead)
    return lead, guest


def send_follow_up(store: LeadStore, sender: Sender, lead_id: str, kind: str):
    def record(lead):
        lead["sent"].append(sender.to_guest(lead, kind, messages.follow_up(lead, kind)))
    return store.update(lead_id, record)


def run_due_follow_ups(store: LeadStore, sender: Sender, now=None) -> int:
    """Send every follow-up whose time has come. Safe to run as often as you like."""
    now = now or now_utc()
    count = 0
    for lead in store.all():
        kind = due_message(lead, now)
        if kind:
            send_follow_up(store, sender, lead["id"], kind)
            count += 1
    return count


def set_status(store: LeadStore, lead_id: str, status: str):
    if status not in ("booked", "lost"):
        return None

    def apply(lead):
        if lead["status"] == "new":
            lead["status"] = status
            if status == "booked":
                lead["booked_at"] = now_utc().isoformat(timespec="seconds")
    return store.update(lead_id, apply)


def make_handler(store: LeadStore, sender: Sender):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            url = urlparse(self.path)
            flash = unquote(parse_qs(url.query).get("msg", [""])[0])
            today = date.today()
            if url.path == "/":
                return self.html(pages.inquiry_page())
            if url.path == "/dashboard":
                return self.html(pages.dashboard_page(store.all(), sender, today, flash))
            m = LEAD_PATH.match(url.path)
            if m and not m.group(2):
                lead = store.get(m.group(1))
                if lead:
                    return self.html(pages.lead_page(lead, today, flash))
            self.html(pages.not_found(), 404)

        def do_POST(self):
            path = urlparse(self.path).path
            form = self.form()
            if path == "/inquire":
                try:
                    lead, guest = handle_inquiry(store, sender, form, date.today())
                except InvalidLead as e:
                    return self.html(pages.inquiry_page(form, str(e)), 400)
                return self.html(pages.thanks_page(lead, guest))
            if path == "/dashboard/run-followups":
                n = run_due_follow_ups(store, sender)
                return self.redirect("/dashboard", f"Sent {n} follow-up{'s' if n != 1 else ''}.")
            m = LEAD_PATH.match(path)
            if m and m.group(2) == "/status":
                set_status(store, m.group(1), form.get("status", ""))
                return self.redirect(f"/dashboard/lead/{m.group(1)}", "Status updated. Follow-ups adjusted.")
            if m and m.group(2) == "/send-next":
                lead = store.get(m.group(1))
                kind = lead and next_follow_up_kind(lead)
                if kind:
                    send_follow_up(store, sender, lead["id"], kind)
                    return self.redirect(f"/dashboard/lead/{lead['id']}", f"Sent: {messages.LABELS[kind]}.")
            self.html(pages.not_found(), 404)

        def form(self) -> dict:
            length = min(int(self.headers.get("Content-Length") or 0), 100_000)
            raw = self.rfile.read(length).decode("utf-8", errors="replace")
            return {k: v[0] for k, v in parse_qs(raw).items()}

        def html(self, body: str, code: int = 200):
            data = body.encode()
            self.send_response(code)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def redirect(self, location: str, msg: str = ""):
            self.send_response(303)
            self.send_header("Location", location + (f"?msg={quote(msg)}" if msg else ""))
            self.end_headers()

        def log_message(self, fmt, *args):
            pass  # keep the terminal quiet during demos

    return Handler


def serve(store: LeadStore, sender: Sender, host: str, port: int) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), make_handler(store, sender))
