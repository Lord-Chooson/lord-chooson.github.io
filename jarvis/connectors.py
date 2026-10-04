"""Free data sources for Jarvis.

Each connector returns (online: bool, detail: str, data). Nothing here can send,
post or delete anything — the only write is an optional IMAP draft.
"""
import datetime as dt
import email
import email.header
import email.utils
import imaplib
import json
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

from config import resolve

UA = {"User-Agent": "Mozilla/5.0 (J.A.R.V.I.S. personal assistant)"}


def local_tz(cfg):
    name = cfg.get("me", {}).get("timezone") or ""
    if name:
        return ZoneInfo(name)
    return dt.datetime.now().astimezone().tzinfo


def http_get(url, timeout=15, attempts=2):
    req = urllib.request.Request(url, headers=UA)
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except OSError:
            if attempt == attempts - 1:
                raise
            time.sleep(1.5)


# --------------------------------------------------------------------------- weather

WMO = {
    0: "clear skies", 1: "mainly clear", 2: "partly cloudy", 3: "overcast",
    45: "fog", 48: "freezing fog", 51: "light drizzle", 53: "drizzle", 55: "heavy drizzle",
    56: "freezing drizzle", 57: "freezing drizzle", 61: "light rain", 63: "rain",
    65: "heavy rain", 66: "freezing rain", 67: "freezing rain", 71: "light snow",
    73: "snow", 75: "heavy snow", 77: "snow grains", 80: "light showers", 81: "showers",
    82: "violent showers", 85: "snow showers", 86: "heavy snow showers",
    95: "thunderstorms", 96: "thunderstorms with hail", 99: "thunderstorms with hail",
}


def weather(cfg):
    loc = cfg.get("location", {})
    lat, lon, city = loc.get("latitude") or 0, loc.get("longitude") or 0, loc.get("city", "")
    try:
        if not (lat or lon):
            q = urllib.parse.quote(city)
            geo = json.loads(http_get(f"https://geocoding-api.open-meteo.com/v1/search?name={q}&count=1"))
            hit = geo["results"][0]
            lat, lon, city = hit["latitude"], hit["longitude"], hit["name"]
        url = (
            "https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}&timezone=auto&forecast_days=1"
            "&current=temperature_2m,weather_code,wind_speed_10m"
            "&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max"
        )
        w = json.loads(http_get(url))
        cur, day = w["current"], w["daily"]
        data = {
            "city": city,
            "latitude": lat,
            "longitude": lon,
            "temp": round(cur["temperature_2m"]),
            "condition": WMO.get(cur["weather_code"], "unsettled"),
            "high": round(day["temperature_2m_max"][0]),
            "low": round(day["temperature_2m_min"][0]),
            "rain": day["precipitation_probability_max"][0] or 0,
            "wind": round(cur["wind_speed_10m"]),
        }
        return True, f"{data['temp']}°C {data['condition']}", data
    except Exception as e:  # noqa: BLE001
        return False, f"weather unavailable ({e.__class__.__name__})", None


# --------------------------------------------------------------------------- calendar (iCal)

def _unfold(text):
    out = []
    for line in text.splitlines():
        if line[:1] in (" ", "\t") and out:
            out[-1] += line[1:]
        else:
            out.append(line)
    return out


def _parse_prop(line):
    head, _, value = line.partition(":")
    name, *params = head.split(";")
    p = {}
    for item in params:
        k, _, v = item.partition("=")
        p[k.upper()] = v.strip('"')
    return name.upper(), p, value


def _ics_unescape(s):
    return s.replace("\\n", " ").replace("\\N", " ").replace("\\,", ",").replace("\\;", ";").replace("\\\\", "\\")


def _ics_time(value, params, tz, keep_tz=False):
    """Returns (datetime_or_date, all_day). keep_tz keeps the event's own zone (for recurrences)."""
    if params.get("VALUE") == "DATE" or re.fullmatch(r"\d{8}", value):
        return dt.datetime.strptime(value[:8], "%Y%m%d").date(), True
    if value.endswith("Z"):
        t = dt.datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=dt.timezone.utc)
    else:
        t = dt.datetime.strptime(value[:15], "%Y%m%dT%H%M%S")
        try:
            t = t.replace(tzinfo=ZoneInfo(params["TZID"])) if "TZID" in params else t.replace(tzinfo=tz)
        except Exception:  # unknown Windows-style TZID
            t = t.replace(tzinfo=tz)
    return (t if keep_tz else t.astimezone(tz)), False


def _occurs_on(ev, day):
    """Best-effort RRULE check (DAILY/WEEKLY/MONTHLY/YEARLY, INTERVAL, BYDAY, UNTIL, COUNT)."""
    start = ev["start"] if isinstance(ev["start"], dt.date) and not isinstance(ev["start"], dt.datetime) else ev["start"].date()
    if day in ev["exdates"]:
        return False
    rule = ev.get("rrule")
    if not rule:
        end = ev["end"]
        end_d = end if not isinstance(end, dt.datetime) else end.date()
        if ev["all_day"]:
            return start <= day < max(end_d, start + dt.timedelta(days=1))
        return start <= day <= end_d
    if day < start:
        return False
    r = dict(part.split("=", 1) for part in rule.split(";") if "=" in part)
    interval = int(r.get("INTERVAL", 1))
    if "UNTIL" in r and day > dt.datetime.strptime(r["UNTIL"][:8], "%Y%m%d").date():
        return False
    freq = r.get("FREQ")
    delta = (day - start).days
    days = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]
    if freq == "DAILY":
        n, ok = delta // interval, delta % interval == 0
    elif freq == "WEEKLY":
        byday = [d[-2:] for d in r.get("BYDAY", days[start.weekday()]).split(",")]
        week = (day - (start - dt.timedelta(days=start.weekday()))).days // 7
        ok = days[day.weekday()] in byday and week % interval == 0
        n = week * len(byday)
    elif freq == "MONTHLY":
        months = (day.year - start.year) * 12 + day.month - start.month
        ok, n = day.day == start.day and months % interval == 0, months // interval
    elif freq == "YEARLY":
        ok = (day.month, day.day) == (start.month, start.day) and (day.year - start.year) % interval == 0
        n = day.year - start.year
    else:
        return False
    if ok and "COUNT" in r and n >= int(r["COUNT"]):
        return False
    return ok


def parse_ics(text, tz):
    events, cur = [], None
    for line in _unfold(text):
        if line == "BEGIN:VEVENT":
            cur = {"exdates": set(), "rrule": None, "summary": "(busy)", "location": "", "recurrence_id": None}
        elif line == "END:VEVENT" and cur is not None:
            if "start" in cur:
                cur.setdefault("end", cur["start"])
                events.append(cur)
            cur = None
        elif cur is not None:
            name, params, value = _parse_prop(line)
            if name == "DTSTART":
                cur["start"], cur["all_day"] = _ics_time(value, params, tz)
                cur["start_raw"], _ = _ics_time(value, params, tz, keep_tz=True)
            elif name == "DTEND":
                cur["end"], _ = _ics_time(value, params, tz)
                cur["end_raw"], _ = _ics_time(value, params, tz, keep_tz=True)
            elif name == "SUMMARY":
                cur["summary"] = _ics_unescape(value)
            elif name == "LOCATION":
                cur["location"] = _ics_unescape(value)
            elif name == "RRULE":
                cur["rrule"] = value
            elif name == "EXDATE":
                for v in value.split(","):
                    d, _ = _ics_time(v, params, tz)
                    cur["exdates"].add(d if not isinstance(d, dt.datetime) else d.date())
            elif name == "RECURRENCE-ID":
                cur["recurrence_id"] = value
            elif name == "STATUS" and value.upper() == "CANCELLED":
                cur["cancelled"] = True
    return events


def calendar(cfg, day=None):
    urls = cfg.get("calendar", {}).get("ics_urls") or []
    if not urls:
        return False, "no iCal link configured", []
    tz = local_tz(cfg)
    day = day or dt.datetime.now(tz).date()
    out, errors = [], 0
    for url in urls:
        try:
            if url.startswith("webcal://"):
                url = "https://" + url[len("webcal://"):]
            text = http_get(url, timeout=20).decode("utf-8", "replace")
            for ev in parse_ics(text, tz):
                if ev.get("cancelled") or not _occurs_on(ev, day):
                    continue
                if ev["all_day"]:
                    start_t, end_t = None, None
                else:
                    # move the occurrence to the target day in the event's own zone, then to local
                    # time, so recurring events stay correct across daylight-saving changes
                    raw, raw_end = ev["start_raw"], ev.get("end_raw", ev["start_raw"])
                    length = raw_end - raw if isinstance(raw_end, dt.datetime) else dt.timedelta(0)
                    start_t = raw.replace(year=day.year, month=day.month, day=day.day).astimezone(tz)
                    end_t = start_t + length if length else None
                out.append({
                    "title": ev["summary"],
                    "location": ev["location"],
                    "all_day": ev["all_day"],
                    "start": start_t.strftime("%H:%M") if start_t else "",
                    "end": end_t.strftime("%H:%M") if end_t else "",
                })
        except Exception:  # noqa: BLE001
            errors += 1
    # de-duplicate (overridden recurrences can appear twice) and sort
    seen, events = set(), []
    for e in sorted(out, key=lambda e: (not e["all_day"], e["start"])):
        key = (e["title"], e["start"])
        if key not in seen:
            seen.add(key)
            events.append(e)
    timed = [e for e in events if not e["all_day"] and e["start"] and e["end"]]
    for i, a in enumerate(timed):
        for b in timed[i + 1:]:
            if b["start"] < a["end"] and a["start"] < b["end"]:
                a["conflict"] = b["conflict"] = True
    online = errors < len(urls)
    detail = f"{len(events)} events today" if online else "could not fetch calendar"
    return online, detail, events


# --------------------------------------------------------------------------- email (IMAP, read-only)

def _decode(value):
    if not value:
        return ""
    parts = []
    for text, charset in email.header.decode_header(value):
        if isinstance(text, bytes):
            text = text.decode(charset or "utf-8", "replace")
        parts.append(text)
    return " ".join("".join(parts).split())


def _snippet(msg, limit=400):
    for part in msg.walk() if msg.is_multipart() else [msg]:
        ctype = part.get_content_type()
        if ctype in ("text/plain", "text/html"):
            try:
                payload = part.get_payload(decode=True) or b""
                text = payload.decode(part.get_content_charset() or "utf-8", "replace")
            except Exception:  # noqa: BLE001
                continue
            if ctype == "text/html":
                text = re.sub(r"<(style|script)[^>]*>.*?</\1>", " ", text, flags=re.S | re.I)
                text = re.sub(r"<[^>]+>", " ", text)
            text = " ".join(text.split())
            if text:
                return text[:limit]
    return ""


def _imap(cfg):
    ec = cfg["email"]
    conn = imaplib.IMAP4_SSL(ec.get("imap_host", "imap.gmail.com"), int(ec.get("imap_port", 993)))
    conn.login(ec["username"], ec["password"])
    return conn


def inbox(cfg):
    ec = cfg.get("email", {})
    if not ec.get("enabled") or not ec.get("username") or not ec.get("password"):
        return False, "email not configured", []
    try:
        conn = _imap(cfg)
        conn.select("INBOX", readonly=True)  # read-only: never marks anything as read
        since = (dt.datetime.now() - dt.timedelta(hours=int(ec.get("lookback_hours", 24)))).strftime("%d-%b-%Y")
        _, ids = conn.search(None, "SINCE", since)
        ids = ids[0].split()[-int(ec.get("max_messages", 30)):]
        mails = []
        for mid in reversed(ids):
            _, data = conn.fetch(mid, "(FLAGS BODY.PEEK[HEADER] BODY.PEEK[TEXT]<0.6000>)")
            flags, header, body = b"", b"", b""
            for item in data:
                if isinstance(item, tuple):
                    if b"HEADER" in item[0]:
                        header = item[1]
                    elif b"TEXT" in item[0]:
                        body = item[1]
                    flags += item[0]
                elif isinstance(item, bytes):
                    flags += item  # some servers send FLAGS after the body
            msg = email.message_from_bytes(header + b"\r\n" + body)
            name, addr = email.utils.parseaddr(_decode(msg.get("From")))
            mails.append({
                "id": len(mails),
                "from": name or addr,
                "address": addr,
                "subject": _decode(msg.get("Subject")) or "(no subject)",
                "message_id": msg.get("Message-ID", ""),
                "unread": b"\\Seen" not in flags,
                "list": bool(msg.get("List-Unsubscribe") or msg.get("List-Id")),
                "snippet": _snippet(msg),
            })
        conn.logout()
        unread = sum(m["unread"] for m in mails)
        return True, f"{len(mails)} mails, {unread} unread", mails
    except Exception as e:  # noqa: BLE001
        return False, f"IMAP failed ({e.__class__.__name__})", []


def triage_heuristic(mails):
    """Fallback grouping when no LLM is available."""
    noise = re.compile(r"no-?reply|newsletter|notification|digest|promo|marketing|mailer", re.I)
    for m in mails:
        if m["list"] or noise.search(m["address"]):
            m["group"] = "ignore"
        elif "?" in (m["subject"] + m["snippet"][:200]) and m["unread"]:
            m["group"] = "reply"
        else:
            m["group"] = "fyi"
    return mails


def save_draft(cfg, to_addr, subject, body, in_reply_to=""):
    """Stores a reply in the Drafts folder. It is NEVER sent."""
    from email.message import EmailMessage

    ec = cfg["email"]
    msg = EmailMessage()
    msg["From"] = ec["username"]
    msg["To"] = to_addr
    msg["Subject"] = subject if subject.lower().startswith("re:") else f"Re: {subject}"
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = in_reply_to
    msg.set_content(body)
    conn = _imap(cfg)
    conn.append(ec.get("drafts_folder", "[Gmail]/Drafts"), "(\\Draft)",
                imaplib.Time2Internaldate(time.time()), msg.as_bytes())
    conn.logout()


# --------------------------------------------------------------------------- tasks (markdown)

DUE = re.compile(r"\b(?:due[:\s]+|📅\s*)(\d{4}-\d{2}-\d{2})")


def tasks(cfg, today=None):
    path = resolve(cfg.get("tasks", {}).get("file", "tasks.md"))
    if not path.exists():
        return False, f"{path.name} not found", []
    today = today or dt.datetime.now(local_tz(cfg)).date()
    section, items = "", []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("#"):
            section = line.lstrip("#").strip()
            continue
        m = re.match(r"\s*[-*]\s*\[( |x|X)\]\s*(.+)", line)
        if not m or m.group(1).lower() == "x":
            continue
        text = m.group(2).strip()
        due = DUE.search(text)
        due_date = dt.date.fromisoformat(due.group(1)) if due else None
        items.append({
            "title": DUE.sub("", text).replace("!", "").strip(" -"),
            "section": section,
            "urgent": "!" in text,
            "due": due_date.isoformat() if due_date else "",
            "overdue": bool(due_date and due_date < today),
            "due_today": due_date == today,
        })
    return True, f"{len(items)} open tasks", items


# --------------------------------------------------------------------------- news (RSS / Atom)

def news(cfg):
    nc = cfg.get("news", {})
    feeds, per = nc.get("feeds") or [], int(nc.get("items_per_feed", 3))
    if not feeds:
        return False, "no feeds", []
    out, ok = [], 0
    for url in feeds:
        try:
            root = ET.fromstring(http_get(url))
            ok += 1
            titles = []
            for entry in root.iter():
                if entry.tag.split("}")[-1] in ("item", "entry"):
                    title = next((c.text for c in entry if c.tag.split("}")[-1] == "title" and c.text), None)
                    if title:
                        titles.append(" ".join(title.split()))
            out.extend(titles[:per])
        except Exception:  # noqa: BLE001
            continue
    return ok > 0, f"{len(out)} headlines", out
