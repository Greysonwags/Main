"""Sends texts (Twilio) and emails (any SMTP account, e.g. Gmail).

With no credentials set, nothing is sent: each message is recorded as
"demo" so the screens still show exactly what would have gone out.

Environment variables (put them in your shell, never in the repo):
    TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM   texting
    SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD        email
    SMTP_FROM        address emails come from (defaults to SMTP_USER)
    STAFF_EMAIL, STAFF_PHONE   where hot-lead alerts go
"""

import base64
import os
import smtplib
import urllib.error
import urllib.parse
import urllib.request
from email.message import EmailMessage

from . import config
from .leads import now_utc


class Sender:
    def __init__(self, env=None):
        env = os.environ if env is None else env
        self.twilio = (env.get("TWILIO_ACCOUNT_SID"), env.get("TWILIO_AUTH_TOKEN"),
                       env.get("TWILIO_FROM"))
        self.smtp = {k: env.get(f"SMTP_{k}") for k in ("HOST", "PORT", "USER", "PASSWORD", "FROM")}
        self.staff_email = env.get("STAFF_EMAIL")
        self.staff_phone = env.get("STAFF_PHONE")

    @property
    def can_text(self) -> bool:
        return all(self.twilio)

    @property
    def can_email(self) -> bool:
        return bool(self.smtp["HOST"] and self.smtp["USER"] and self.smtp["PASSWORD"])

    def to_guest(self, lead: dict, kind: str, msg: dict) -> dict:
        """Email the guest, and text them if they agreed to texts. Returns the log entry."""
        entry = {"kind": kind, "at": now_utc().isoformat(timespec="seconds"),
                 "subject": msg["subject"], "email": msg["email"], "sms": msg["sms"]}
        entry["email_status"] = self.send_email(lead["email"], msg["subject"], msg["email"])
        entry["sms_status"] = (self.send_sms(lead["phone"], msg["sms"]) if lead["sms_ok"]
                               else "skipped: no permission to text")
        return entry

    def to_staff(self, msg: dict) -> dict:
        entry = {"kind": "staff_alert", "at": now_utc().isoformat(timespec="seconds"),
                 "subject": msg["subject"], "email": msg["email"], "sms": msg["sms"]}
        entry["email_status"] = (self.send_email(self.staff_email, msg["subject"], msg["email"])
                                 if self.staff_email else "demo")
        entry["sms_status"] = (self.send_sms(self.staff_phone, msg["sms"])
                               if self.staff_phone else "demo")
        return entry

    def send_sms(self, to: str, body: str) -> str:
        if not self.can_text:
            return "demo"
        sid, token, sender = self.twilio
        req = urllib.request.Request(
            f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
            data=urllib.parse.urlencode({"To": to, "From": sender, "Body": body}).encode(),
            headers={"Authorization": "Basic " + base64.b64encode(f"{sid}:{token}".encode()).decode()},
        )
        try:
            with urllib.request.urlopen(req, timeout=15):
                return "sent"
        except urllib.error.HTTPError as e:
            return f"failed: Twilio said {e.code} {e.read().decode(errors='replace')[:200]}"
        except OSError as e:
            return f"failed: {e}"

    def send_email(self, to: str, subject: str, body: str) -> str:
        if not self.can_email:
            return "demo"
        s = self.smtp
        msg = EmailMessage()
        msg["From"] = f"{config.COURSE_NAME} <{s['FROM'] or s['USER']}>"
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body)
        port = int(s["PORT"] or 587)
        try:
            if port == 465:
                server = smtplib.SMTP_SSL(s["HOST"], port, timeout=15)
            else:
                server = smtplib.SMTP(s["HOST"], port, timeout=15)
                server.starttls()
            with server:
                server.login(s["USER"], s["PASSWORD"])
                server.send_message(msg)
            return "sent"
        except (smtplib.SMTPException, OSError) as e:
            return f"failed: {e}"
