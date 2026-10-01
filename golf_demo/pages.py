"""HTML for every screen. Plain strings, no template engine needed."""

import json
from datetime import date, datetime
from html import escape

from . import config
from .leads import follow_up_schedule, next_scheduled, priority
from .messages import LABELS, follow_up, money, nice_date

CSS = """
:root{--green:#1f4d3a;--green-2:#2f6b52;--cream:#f7f5ef;--card:#fff;--ink:#1d2421;
--muted:#5f6b66;--line:#e2ddd0;--gold:#b8933f;--hot:#b4472f;--ok:#2f7a4f}
*{box-sizing:border-box}
body{margin:0;background:var(--cream);color:var(--ink);
font:16px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
h1,h2,h3{font-family:Georgia,"Times New Roman",serif;font-weight:normal;line-height:1.2;margin:0 0 .5em}
a{color:var(--green-2)}
.wrap{max-width:1040px;margin:0 auto;padding:0 16px}
.top{background:var(--green);color:#fff}
.top .wrap{display:flex;align-items:center;justify-content:space-between;gap:12px;padding-top:14px;padding-bottom:14px}
.brand{font-family:Georgia,serif;font-size:1.3rem;letter-spacing:.02em}
.brand small{display:block;font:12px/1.2 inherit;font-family:inherit;opacity:.75;letter-spacing:.08em;text-transform:uppercase}
.top a{color:#fff;opacity:.85;font-size:.9rem}
.hero{background:linear-gradient(160deg,var(--green) 0%,var(--green-2) 100%);color:#fff;padding:40px 0 90px}
.hero h1{font-size:clamp(1.8rem,4vw,2.6rem)}
.hero p{max-width:560px;opacity:.9;margin:0}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:24px;
box-shadow:0 6px 24px rgba(20,40,30,.06)}
.lift{margin-top:-60px}
.grid{display:grid;gap:16px}
.two{grid-template-columns:1fr 1fr}
.form-layout{display:grid;grid-template-columns:1.6fr 1fr;gap:20px;align-items:start}
label{display:block;font-size:.85rem;font-weight:600;margin-bottom:4px;color:var(--muted)}
input,select,textarea{width:100%;padding:11px 12px;border:1px solid var(--line);border-radius:9px;
font:inherit;background:#fff;color:var(--ink)}
input:focus,select:focus,textarea:focus{outline:2px solid var(--gold);border-color:var(--gold)}
.choices{display:grid;gap:8px}
.choice{display:flex;gap:10px;align-items:center;border:1px solid var(--line);border-radius:9px;
padding:10px 12px;font-weight:normal;color:var(--ink);cursor:pointer;margin:0}
.choice input{width:auto}
.choice:has(input:checked){border-color:var(--green-2);background:#eef5f0}
.choice span.price{margin-left:auto;color:var(--muted);font-size:.85rem}
.consent{display:flex;gap:10px;align-items:flex-start;font-weight:normal;font-size:.85rem}
.consent input{width:auto;margin-top:3px}
.btn{display:inline-block;border:0;border-radius:10px;padding:13px 20px;background:var(--green);
color:#fff;font:600 1rem inherit;font-family:inherit;cursor:pointer;text-decoration:none}
.btn:hover{background:var(--green-2)}
.btn.small{padding:8px 12px;font-size:.85rem}
.btn.ghost{background:#fff;color:var(--green);border:1px solid var(--line)}
.btn.warn{background:#fff;color:var(--hot);border:1px solid var(--line)}
.wide{width:100%}
.estimate{font-family:Georgia,serif;font-size:2rem;color:var(--green)}
.muted{color:var(--muted)}
.small{font-size:.85rem}
.error{background:#fbeae6;color:var(--hot);border-radius:9px;padding:10px 12px;margin-bottom:16px}
.note{background:#fbf6e9;border:1px solid #eadfbf;border-radius:9px;padding:10px 12px;font-size:.9rem}
.sticky{position:sticky;top:16px}
.phone{background:#111;border-radius:30px;padding:12px;max-width:300px;margin:0 auto}
.screen{background:#f2f2f6;border-radius:20px;padding:16px 12px;min-height:260px}
.sender{text-align:center;font-size:.75rem;color:#666;margin-bottom:12px}
.bubble{background:#e5e5ea;color:#111;border-radius:16px;padding:10px 12px;font-size:.88rem;max-width:90%}
.mail{border:1px solid var(--line);border-radius:10px;padding:14px;white-space:pre-wrap;font-size:.9rem;background:#fff}
.status{font-size:.8rem;font-weight:600}
.status.sent{color:var(--ok)}.status.failed{color:var(--hot)}.status.demo,.status.skipped{color:var(--muted)}
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:20px 0}
.stat .num{font-family:Georgia,serif;font-size:1.7rem;color:var(--green)}
.stat .lbl{font-size:.8rem;color:var(--muted);text-transform:uppercase;letter-spacing:.05em}
table{width:100%;border-collapse:collapse;font-size:.92rem}
th{text-align:left;font-size:.75rem;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);
padding:8px;border-bottom:1px solid var(--line)}
td{padding:10px 8px;border-bottom:1px solid var(--line);vertical-align:top}
.tag{display:inline-block;border-radius:99px;padding:2px 9px;font-size:.75rem;font-weight:600}
.tag.hot{background:#fbeae6;color:var(--hot)}.tag.warm{background:#fbf6e9;color:#8a6a1f}
.tag.new{background:#eef1f7;color:#3c4f7a}.tag.booked{background:#e6f3eb;color:var(--ok)}
.tag.lost{background:#eee;color:#777}
.timeline{border-left:2px solid var(--line);padding-left:16px;display:grid;gap:14px}
.row{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.scroll{overflow-x:auto}
footer{padding:30px 0;text-align:center;font-size:.8rem;color:var(--muted)}
@media (max-width:760px){
.form-layout,.two{grid-template-columns:1fr}
.stats{grid-template-columns:1fr 1fr}
.sticky{position:static}
.hide-sm{display:none}
}
"""


def layout(title: str, body: str, nav: str = "") -> str:
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(title)}</title><style>{CSS}</style></head>
<body>
<div class="top"><div class="wrap">
<div class="brand">{escape(config.COURSE_NAME)}<small>{escape(config.COURSE_CITY)}</small></div>
<div>{nav}</div></div></div>
{body}
<footer>Powered by {escape(config.BUSINESS_NAME)}</footer>
</body></html>"""


def status_html(status: str) -> str:
    cls = status.split(":")[0]
    text = {"sent": "Sent", "demo": "Demo mode (not sent)"}.get(status, status.capitalize())
    return f'<span class="status {escape(cls)}">{escape(text)}</span>'


def inquiry_page(values=None, error=None) -> str:
    v = {k: escape(str(x)) for k, x in (values or {}).items()}
    sel = lambda name, key: " checked" if (values or {}).get(name, "") == key else ""
    fmt_default = (values or {}).get("format") or "18"
    food_default = (values or {}).get("food") or "buffet"
    formats = "".join(
        f'<label class="choice"><input type="radio" name="format" value="{k}"'
        f'{" checked" if k == fmt_default else ""}>{escape(lbl)}'
        f'<span class="price">${p}/golfer</span></label>'
        for k, (lbl, p) in config.FORMATS.items())
    foods = "".join(
        f'<option value="{k}"{" selected" if k == food_default else ""}>'
        f'{escape(lbl)}{f" (+${p}/golfer)" if p else ""}</option>'
        for k, (lbl, p) in config.FOOD.items())
    events = "".join(
        f'<option{" selected" if (values or {}).get("event_type") == e else ""}>{e}</option>'
        for e in ("Corporate outing", "Charity tournament", "Birthday or bachelor party",
                  "League or association", "Other"))
    prices = json.dumps({
        "formats": {k: p for k, (_, p) in config.FORMATS.items()},
        "food": {k: p for k, (_, p) in config.FOOD.items()},
        "weekday": config.WEEKDAY_DISCOUNT, "spread": config.ESTIMATE_SPREAD,
    })
    err = f'<div class="error">{escape(error)}</div>' if error else ""
    body = f"""
<section class="hero"><div class="wrap">
<h1>Host your next outing at {escape(config.COURSE_NAME)}</h1>
<p>Corporate days, charity tournaments and group events for 8 to 288 golfers.
Tell us about your group and get a price estimate instantly.</p>
</div></section>
<div class="wrap"><form method="post" action="/inquire" class="form-layout lift">
<div class="card grid">
{err}
<h2>Plan your event</h2>
<div class="grid two">
<div><label for="name">Your name</label><input id="name" name="name" required value="{v.get('name','')}"></div>
<div><label for="company">Company or organization</label><input id="company" name="company" value="{v.get('company','')}"></div>
<div><label for="email">Email</label><input id="email" name="email" type="email" required value="{v.get('email','')}"></div>
<div><label for="phone">Mobile phone</label><input id="phone" name="phone" type="tel" placeholder="+1 555 555 0123" value="{v.get('phone','')}"></div>
<div><label for="event_type">Type of event</label><select id="event_type" name="event_type">{events}</select></div>
<div><label for="date">Preferred date</label><input id="date" name="date" type="date" required value="{v.get('date','')}"></div>
<div><label for="players">Number of golfers</label><input id="players" name="players" type="number" min="8" max="288" required value="{v.get('players','')}" placeholder="e.g. 48"></div>
<div><label for="food">Food and drink</label><select id="food" name="food">{foods}</select></div>
</div>
<div><label>Golf format</label><div class="choices">{formats}</div></div>
<div><label for="notes">Anything else? (optional)</label>
<textarea id="notes" name="notes" rows="3" placeholder="Sponsorships, prizes, rain date, special requests...">{v.get('notes','')}</textarea></div>
<label class="consent"><input type="checkbox" name="sms_ok" value="yes"{sel('sms_ok','yes')}>
<span>Yes, text me about my request. Message and data rates may apply. Reply STOP to opt out.</span></label>
</div>
<div class="card sticky grid">
<div><div class="muted small">Your estimate</div>
<div class="estimate" id="est">Enter your group size</div>
<div class="muted small" id="est-note">Final pricing confirmed by our events team.</div></div>
<button class="btn wide" type="submit">Get my estimate and hold my date</button>
<div class="muted small">We'll email your estimate right away, and reach out within one business day.</div>
</div>
</form></div>
<script>
const P={prices};
const f=document.querySelector("form");
function round50(x){{return Math.round(x/50)*50}}
function money(x){{return "$"+x.toLocaleString()}}
function update(){{
  const n=parseInt(f.players.value,10), fmt=(f.querySelector("input[name=format]:checked")||{{}}).value;
  const est=document.getElementById("est"), note=document.getElementById("est-note");
  if(!n||n<8||!fmt){{est.textContent="Enter your group size";return}}
  let per=P.formats[fmt]+P.food[f.food.value], total=per*n, wk=false;
  if(f.date.value){{const d=new Date(f.date.value+"T12:00:00").getDay(); wk=d>=1&&d<=4; if(wk) total*=1-P.weekday}}
  est.textContent=money(round50(total*(1-P.spread)))+" to "+money(round50(total*(1+P.spread)));
  note.textContent="About "+money(per)+" per golfer"+(wk?", with our weekday discount":"")+". Final pricing confirmed by our events team.";
}}
f.addEventListener("input",update); update();
</script>"""
    return layout(f"Outings at {config.COURSE_NAME}", body)


def phone_preview(sms: str, status: str) -> str:
    return f"""<div class="phone"><div class="screen">
<div class="sender">{escape(config.COURSE_NAME)} &middot; now</div>
<div class="bubble">{escape(sms)}</div></div></div>
<div style="text-align:center;margin-top:8px">{status_html(status)}</div>"""


def thanks_page(lead: dict, entry: dict) -> str:
    e = lead["estimate"]
    text_part = (phone_preview(entry["sms"], entry["sms_status"]) if lead["sms_ok"] else
                 '<p class="muted">No text sent: you didn\'t ask for texts.</p>')
    body = f"""
<section class="hero"><div class="wrap">
<h1>Thanks, {escape(lead['name'].split()[0])}. Your date is on our radar.</h1>
<p>Your estimate is below, and it's already in your inbox. Our events team will be in touch shortly.</p>
</div></section>
<div class="wrap grid lift">
<div class="card">
<div class="muted small">Estimated total for {lead['players']} golfers on {escape(nice_date(lead['date']))}</div>
<div class="estimate">{money(e['low'])} to {money(e['high'])}</div>
<div class="muted small">About {money(e['per_player'])} per golfer{", including our weekday discount" if e['weekday'] else ""}.
{"Your group gets the whole course with a shotgun start." if e['shotgun'] else ""}</div>
</div>
<div class="grid two">
<div class="card"><h3>The text we just sent you</h3>{text_part}</div>
<div class="card"><h3>The email we just sent you</h3>
<div class="small muted">Subject: {escape(entry['subject'])}</div>
<div class="mail">{escape(entry['email'])}</div>
<div style="margin-top:8px">{status_html(entry['email_status'])}</div></div>
</div>
<p class="small muted">Demo: <a href="/dashboard/lead/{lead['id']}">see what the course staff sees</a>.</p>
</div>"""
    return layout("Your outing estimate", body)


def _month(iso: str) -> str:
    return iso[:7]


def dashboard_page(leads: list, sender, today: date, flash: str = "") -> str:
    this_month = today.isoformat()[:7]
    month_leads = [l for l in leads if _month(l["created"]) == this_month]
    open_value = sum(l["estimate"]["mid"] for l in leads if l["status"] == "new")
    booked = [l for l in leads if l["status"] == "booked" and _month(l.get("booked_at", "")) == this_month]
    booked_value = sum(l["estimate"]["mid"] for l in booked)
    after_followup = sum(1 for l in booked if any(m["kind"].startswith("followup") for m in l["sent"]))

    mode = []
    if not sender.can_email:
        mode.append("email")
    if not sender.can_text:
        mode.append("texting")
    banner = (f'<div class="note">Demo mode for {" and ".join(mode)}: messages are shown but not sent. '
              f'See the README to connect real accounts.</div>' if mode else "")
    flash_html = f'<div class="note">{escape(flash)}</div>' if flash else ""

    rows = []
    for l in sorted(leads, key=lambda l: l["created"], reverse=True):
        nxt = next_scheduled(l)
        nxt_txt = f"{LABELS[nxt[0]]}<br><span class='muted small'>{nxt[1]:%b %d}</span>" if nxt else "<span class='muted'>Done</span>"
        pr = priority(l, today)
        rows.append(f"""<tr>
<td><a href="/dashboard/lead/{l['id']}"><strong>{escape(l['name'])}</strong></a>
<div class="muted small">{escape(l['company'] or l['event_type'])}</div></td>
<td>{escape(nice_date(l['date']))}<div class="muted small">{l['players']} golfers</div></td>
<td>{money(l['estimate']['mid'])}</td>
<td><span class="tag {pr}">{pr}</span> <span class="tag {l['status']}">{l['status']}</span></td>
<td class="hide-sm small">{nxt_txt}</td></tr>""")
    table = ("".join(rows) if rows else
             '<tr><td colspan="5" class="muted">No inquiries yet. <a href="/">Fill out the form</a> to see one arrive.</td></tr>')

    body = f"""<div class="wrap" style="padding-top:24px">
<div class="row" style="justify-content:space-between">
<h1>Outing leads</h1>
<form method="post" action="/dashboard/run-followups"><button class="btn small ghost">Send follow-ups that are due</button></form>
</div>
{banner}{flash_html}
<div class="stats">
<div class="card stat"><div class="num">{len(month_leads)}</div><div class="lbl">Inquiries this month</div></div>
<div class="card stat"><div class="num">{money(open_value)}</div><div class="lbl">Open pipeline</div></div>
<div class="card stat"><div class="num">{money(booked_value)}</div><div class="lbl">Booked this month</div></div>
<div class="card stat"><div class="num">{after_followup}</div><div class="lbl">Booked after a follow-up</div></div>
</div>
<div class="card scroll"><table>
<tr><th>Contact</th><th>Event</th><th>Est. value</th><th>Status</th><th class="hide-sm">Next message</th></tr>
{table}</table></div>
<p class="muted small">Every inquiry got an instant reply. Follow-ups stop automatically when a lead is marked booked or lost.</p>
</div>"""
    nav = '<a href="/">Inquiry form</a>'
    return layout("Outing leads", body, nav)


def lead_page(lead: dict, today: date, flash: str = "") -> str:
    pr = priority(lead, today)
    sent_kinds = {m["kind"] for m in lead["sent"]}
    sent_html = "".join(f"""<div><strong>{escape(LABELS.get(m['kind'], m['kind']))}</strong>
<span class="muted small"> {escape(datetime.fromisoformat(m['at']).strftime('%b %d, %I:%M %p'))} UTC</span>
<div class="small">Email: {status_html(m['email_status'])} &nbsp; Text: {status_html(m['sms_status'])}</div>
<details><summary class="small">Show message</summary><div class="mail">{escape(m['email'])}</div></details></div>"""
                        for m in lead["sent"])
    upcoming = []
    for kind, when in follow_up_schedule(lead):
        if kind in sent_kinds or lead["status"] == "lost":
            continue
        if (kind == "rebook") != (lead["status"] == "booked"):
            continue
        upcoming.append(f"""<div><strong>{escape(LABELS[kind])}</strong>
<span class="muted small"> planned for {when:%b %d, %Y}</span>
<div class="bubble small" style="margin-top:6px">{escape(follow_up(lead, kind)['sms'])}</div></div>""")
    upcoming_html = "".join(upcoming) or '<p class="muted">Nothing else planned.</p>'
    flash_html = f'<div class="note" style="margin-bottom:16px">{escape(flash)}</div>' if flash else ""
    actions = ""
    if lead["status"] == "new":
        actions = f"""<form method="post" action="/dashboard/lead/{lead['id']}/status"><input type="hidden" name="status" value="booked"><button class="btn small">Mark booked</button></form>
<form method="post" action="/dashboard/lead/{lead['id']}/status"><input type="hidden" name="status" value="lost"><button class="btn small warn">Mark lost</button></form>"""
    if next_scheduled(lead):
        actions += f"""<form method="post" action="/dashboard/lead/{lead['id']}/send-next"><button class="btn small ghost">Send next message now (demo)</button></form>"""

    body = f"""<div class="wrap" style="padding-top:24px">
<p class="small"><a href="/dashboard">&larr; All leads</a></p>
{flash_html}
<div class="row" style="justify-content:space-between">
<h1>{escape(lead['name'])}</h1>
<div><span class="tag {pr}">{pr}</span> <span class="tag {lead['status']}">{lead['status']}</span></div></div>
<div class="grid two">
<div class="card">
<h3>{escape(lead['event_type'])}{(" for " + escape(lead['company'])) if lead['company'] else ""}</h3>
<div class="estimate">{money(lead['estimate']['mid'])}</div>
<p class="muted small">Estimated value (guest was quoted {money(lead['estimate']['low'])} to {money(lead['estimate']['high'])})</p>
<table>
<tr><td class="muted">Date</td><td>{escape(nice_date(lead['date']))}</td></tr>
<tr><td class="muted">Golfers</td><td>{lead['players']}</td></tr>
<tr><td class="muted">Golf</td><td>{escape(config.FORMATS[lead['format']][0])}</td></tr>
<tr><td class="muted">Food</td><td>{escape(config.FOOD[lead['food']][0])}</td></tr>
<tr><td class="muted">Email</td><td><a href="mailto:{escape(lead['email'])}">{escape(lead['email'])}</a></td></tr>
<tr><td class="muted">Phone</td><td>{escape(lead['phone'] or 'not given')}{" (OK to text)" if lead['sms_ok'] else ""}</td></tr>
<tr><td class="muted">Notes</td><td>{escape(lead['notes'] or 'none')}</td></tr>
</table>
<div class="row" style="margin-top:16px">{actions}</div>
</div>
<div class="grid">
<div class="card"><h3>Sent</h3><div class="timeline">{sent_html or '<p class="muted">Nothing yet.</p>'}</div></div>
<div class="card"><h3>Coming up</h3><div class="timeline">{upcoming_html}</div></div>
</div></div></div>"""
    return layout(lead["name"], body, '<a href="/dashboard">Dashboard</a>')


def not_found() -> str:
    return layout("Not found", '<div class="wrap" style="padding:40px 16px"><h1>Page not found</h1><p><a href="/">Back to the inquiry form</a></p></div>')
