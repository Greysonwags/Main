"""The words of every message the system sends.

Each function returns {"subject", "email", "sms"}; the sms is kept short
enough for one or two texts. Edit the wording here.
"""

from datetime import date

from . import config


def money(n: int) -> str:
    return f"${n:,}"


def nice_date(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{d:%A, %B} {d.day}, {d.year}"


def first_name(lead: dict) -> str:
    return lead["name"].split()[0]


def price_range(lead: dict) -> str:
    e = lead["estimate"]
    return f"{money(e['low'])} to {money(e['high'])}"


def summary_lines(lead: dict) -> str:
    e = lead["estimate"]
    lines = [
        f"Date: {nice_date(lead['date'])}",
        f"Golfers: {lead['players']}",
        f"Golf: {config.FORMATS[lead['format']][0]}",
        f"Food: {config.FOOD[lead['food']][0]}",
        f"Estimated total: {price_range(lead)} (about {money(e['per_player'])} per golfer"
        + (", weekday rate" if e["weekday"] else "") + ")",
    ]
    if e["shotgun"]:
        lines.append("A group your size gets the whole course with a shotgun start.")
    return "\n".join(lines)


def guest_confirmation(lead: dict) -> dict:
    name = first_name(lead)
    return {
        "subject": f"Your outing at {config.COURSE_NAME}: estimate inside",
        "email": (
            f"Hi {name},\n\n"
            f"Thanks for thinking of {config.COURSE_NAME} for your {lead['event_type'].lower()}. "
            f"Here's what we put together from your request:\n\n"
            f"{summary_lines(lead)}\n\n"
            f"{nice_date(lead['date'])} is open right now, but popular dates go fast. "
            f"Reply to this email or call {config.COURSE_PHONE} and we'll hold it for you "
            f"while we finalize the details.\n\n"
            f"{config.EVENTS_CONTACT}\n{config.COURSE_NAME}"
        ),
        "sms": (
            f"Hi {name}, it's {config.COURSE_NAME}! Thanks for your outing request for "
            f"{lead['players']} golfers on {nice_date(lead['date'])}. Estimated "
            f"{price_range(lead)}. Full details are in your email. Reply here with any "
            f"questions or to hold the date. Reply STOP to opt out."
        ),
    }


def staff_alert(lead: dict, priority: str) -> dict:
    tag = "HOT LEAD" if priority == "hot" else "New lead"
    who = lead["name"] + (f" ({lead['company']})" if lead["company"] else "")
    return {
        "subject": f"{tag}: {lead['players']}-golfer outing, about {money(lead['estimate']['mid'])}",
        "email": (
            f"{tag}: {who}\n\n"
            f"Event: {lead['event_type']}\n{summary_lines(lead)}\n\n"
            f"Email: {lead['email']}\nPhone: {lead['phone'] or 'not given'}\n"
            f"Notes: {lead['notes'] or 'none'}\n\n"
            f"They already have their estimate. Call them today: the first course "
            f"to call back usually wins the booking."
        ),
        "sms": (
            f"{tag}: {who}, {lead['players']} golfers on {nice_date(lead['date'])}, "
            f"about {money(lead['estimate']['mid'])}. Phone: {lead['phone'] or lead['email']}"
        ),
    }


def follow_up(lead: dict, kind: str) -> dict:
    name, when = first_name(lead), nice_date(lead["date"])
    course = config.COURSE_NAME
    texts = {
        "followup_1": (
            f"Checking in on your outing",
            f"Hi {name}, just making sure our estimate for {when} reached you. "
            f"Any questions I can answer? Happy to walk you through the options.",
        ),
        "followup_2": (
            f"Still holding {when} for you?",
            f"Hi {name}, {when} is still open at {course}, but we've had other groups "
            f"asking about that week. Want me to pencil you in? No commitment yet.",
        ),
        "followup_3": (
            f"Should I close out your request?",
            f"Hi {name}, I haven't heard back, so I'll assume the timing isn't right and "
            f"release {when}. If you still want it, just reply and it's yours.",
        ),
        "rebook": (
            f"Let's lock in next year's outing",
            f"Hi {name}, thanks again for bringing your group to {course} last year! "
            f"Want first pick of dates for this year's outing before we open the calendar up?",
        ),
    }
    subject, body = texts[kind]
    return {
        "subject": subject,
        "email": f"{body}\n\n{config.EVENTS_CONTACT}\n{course}\n{config.COURSE_PHONE}",
        "sms": f"{body} - {course}. Reply STOP to opt out.",
    }


LABELS = {
    "confirmation": "Instant reply with estimate",
    "staff_alert": "Alert to course staff",
    "followup_1": f"Follow-up 1 (day {config.FOLLOW_UP_DAYS[0]})",
    "followup_2": f"Follow-up 2 (day {config.FOLLOW_UP_DAYS[1]})",
    "followup_3": f"Follow-up 3 (day {config.FOLLOW_UP_DAYS[2]})",
    "rebook": "Rebook for next year",
}
