#!/usr/bin/env python3
"""Morning brief: calendar + inbox + tasks + weather + news -> spoken brief + dashboard data.

    python3 brief.py              # full brief with audio
    python3 brief.py --no-audio   # skip text-to-speech
    python3 brief.py --no-llm     # template brief, no AI model

Writes brief.txt, jarvis_data.js, jarvis_brief.mp3, drafts.md and briefs/<date>.md.
Never sends anything: replies are only ever saved as drafts.
"""
import argparse
import datetime as dt
import json
import time
from concurrent.futures import ThreadPoolExecutor

import connectors as c
import llm
import voice
from config import ROOT, load_config, resolve


def persona(cfg):
    """System prompt: shared rules (CLAUDE.md) + personal profile (me.md)."""
    parts = []
    for name in ("CLAUDE.md", "me.md" if (ROOT / "me.md").exists() else "me.example.md"):
        p = ROOT / name
        if p.exists():
            parts.append("\n".join(l for l in p.read_text(encoding="utf-8").splitlines() if not l.startswith("@")))
    me = cfg.get("me", {})
    parts.append(f"Address the user as \"{me.get('address', 'sir')}\". Their name is {me.get('name', '')}.")
    return "\n\n".join(parts)


def greeting(hour):
    return "Good morning" if hour < 12 else "Good afternoon" if hour < 18 else "Good evening"


def ordinal(n):
    return f"{n}{'th' if 11 <= n % 100 <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def gather(cfg):
    jobs = {
        "Calendar": lambda: c.calendar(cfg),
        "Inbox": lambda: c.inbox(cfg),
        "Tasks": lambda: c.tasks(cfg),
        "Weather": lambda: c.weather(cfg),
        "News": lambda: c.news(cfg),
    }
    with ThreadPoolExecutor(len(jobs)) as pool:
        futures = {name: pool.submit(fn) for name, fn in jobs.items()}
        return {name: f.result() for name, f in futures.items()}


def rank_tasks(tasks):
    def score(t):
        return (not t["overdue"], not t["due_today"], not t["urgent"])

    ranked = sorted(tasks, key=score)  # stable: keeps your file order otherwise
    out = []
    for t in ranked[:3]:
        why = ("overdue since " + t["due"]) if t["overdue"] else "due today" if t["due_today"] else \
            "flagged urgent" if t["urgent"] else (f"next up in {t['section']}" if t["section"] else "next on your list")
        out.append({"title": t["title"], "why": why})
    return out


def template_brief(cfg, ctx):
    """A good brief with zero AI — used when no model is available."""
    me, now = cfg["me"], ctx["now"]
    address = me.get("address", "sir")
    events, mails, tasks, wx = ctx["events"], ctx["mails"], ctx["tasks"], ctx["weather"]
    c.triage_heuristic(mails)
    priorities = rank_tasks(tasks)

    lines = [f"{greeting(now.hour)}, {address}. It's {now:%A} the {ordinal(now.day)} of {now:%B}."]
    if wx:
        rain = f", with a {wx['rain']} percent chance of rain" if wx["rain"] >= 30 else ""
        lines.append(f"In {wx['city']} it's {wx['temp']} degrees and {wx['condition']}, "
                     f"reaching {wx['high']}{rain}.")
    timed = [e for e in events if not e["all_day"]]
    if events:
        first = timed[0] if timed else events[0]
        when = f" at {first['start']}" if first["start"] else ""
        lines.append(f"You have {len(events)} event{'s' * (len(events) != 1)} today. First up, {first['title']}{when}.")
        clash = [e for e in timed if e.get("conflict")]
        if len(clash) >= 2:
            lines.append(f"Careful: {clash[0]['title']} overlaps with {clash[1]['title']}.")
    else:
        lines.append("Your calendar is clear today.")
    reply = [m for m in mails if m["group"] == "reply"]
    if reply:
        lines.append(f"{len(reply)} email{'s need' if len(reply) != 1 else ' needs'} a reply, "
                     f"starting with {reply[0]['from']} about {reply[0]['subject']}.")
    elif mails:
        lines.append(f"{len(mails)} new emails, nothing that needs you urgently.")
    if priorities:
        names = [p["title"] for p in priorities]
        joined = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
        lines.append(f"Your top priorities: {joined}.")

    one = ""
    hot = [t for t in tasks if t["overdue"] or t["due_today"]]
    if hot:
        one = f"{hot[0]['title']} is {'overdue' if hot[0]['overdue'] else 'due today'}."
    elif len([e for e in timed if e.get("conflict")]) >= 2:
        one = "Resolve today's calendar clash."
    elif reply:
        one = f"Reply to {reply[0]['from']}."
    if one:
        lines.append(f"The one thing not to miss: {one}")
    closer = f"What should I handle first, {address}?"
    lines.append(closer)
    return {
        "headline": one or (f"{len(events)} events, {len(reply)} replies, {len(tasks)} tasks" if events or mails or tasks
                            else "All quiet on every front"),
        "spoken": lines,
        "priorities": priorities,
        "one_thing": one,
        "closer": closer,
        "drafts": [],
    }


BRIEF_PROMPT = """You are writing today's morning brief. Data (JSON):
{data}

Do the following and reply with ONLY a JSON object:
1. CALENDAR: note today's events; flag conflicts or anything needing prep.
2. INBOX: group every email id into "reply", "fyi" or "ignore". Draft a short reply in the user's tone
   for each "reply" email (drafts are never sent automatically).
3. PRIORITIES: pick the top 3 for today from the tasks (and urgent emails/events), with a one-line why.
4. ONE THING: the single deadline or signal not to miss today.
5. SPOKEN: 6-8 short spoken lines in the voice of J.A.R.V.I.S. (dry, warm, British butler). Start with a
   greeting addressing the user as "{address}", end with exactly: "{closer}". No markdown, no emoji.

JSON shape:
{{"headline": "max 8 words", "spoken": ["..."], "priorities": [{{"title": "...", "why": "..."}}],
  "one_thing": "...", "inbox": [{{"id": 0, "group": "reply"}}], "drafts": [{{"id": 0, "body": "..."}}]}}"""


def ai_brief(cfg, ctx):
    address = cfg["me"].get("address", "sir")
    closer = f"What should I handle first, {address}?"
    payload = {
        "now": ctx["now"].strftime("%A %d %B %Y, %H:%M"),
        "weather": ctx["weather"],
        "events": ctx["events"],
        "emails": [{k: m[k] for k in ("id", "from", "subject", "snippet", "unread", "list")} for m in ctx["mails"]],
        "tasks": ctx["tasks"][:25],
    }
    prompt = BRIEF_PROMPT.format(data=json.dumps(payload, ensure_ascii=False), address=address, closer=closer)
    out = llm.parse_json(llm.chat(cfg, persona(cfg), [{"role": "user", "content": prompt}], json_mode=True))
    if not out or not out.get("spoken"):
        return None
    groups = {g.get("id"): g.get("group") for g in out.get("inbox", []) if isinstance(g, dict)}
    c.triage_heuristic(ctx["mails"])
    for m in ctx["mails"]:
        if groups.get(m["id"]) in ("reply", "fyi", "ignore"):
            m["group"] = groups[m["id"]]
    spoken = [str(s) for s in out["spoken"]][:9]
    if spoken[-1].strip() != closer:
        spoken.append(closer)
    return {
        "headline": str(out.get("headline", ""))[:80],
        "spoken": spoken,
        "priorities": [p for p in out.get("priorities", []) if isinstance(p, dict)][:3] or rank_tasks(ctx["tasks"]),
        "one_thing": str(out.get("one_thing", "")),
        "closer": closer,
        "drafts": [d for d in out.get("drafts", []) if isinstance(d, dict)],
    }


def booked_hours(events):
    total = 0.0
    for e in events:
        if e["all_day"] or not e["start"] or not e["end"]:
            continue
        s, f = (dt.datetime.strptime(x, "%H:%M") for x in (e["start"], e["end"]))
        total += max(0.0, (f - s).total_seconds() / 3600)
    return round(total, 1)


def build_data(cfg, ctx, brief, results, audio_name, voice_failed=False):
    me, now, wx = cfg["me"], ctx["now"], ctx["weather"]
    mails, tasks, events = ctx["mails"], ctx["tasks"], ctx["events"]
    reply = [m for m in mails if m.get("group") == "reply"]
    unread = sum(m["unread"] for m in mails)
    connectors = [{"name": n.upper(), "online": r[0], "detail": r[1]} for n, r in results.items()]
    connectors += [
        {"name": "BRAIN", "online": llm.provider(cfg) != "none", "detail": llm.describe(cfg)},
        {"name": "VOICE", "online": not voice_failed,
         "detail": voice.engine(cfg) + (" failed — browser fallback" if voice_failed else "")},
    ]
    log = [f"{n.upper():<9}▸ {r[1]}" for n, r in results.items()]
    log += [f"BRAIN    ▸ composed with {llm.describe(cfg)}", f"PRIORITY ▸ {len(brief['priorities'])} selected",
            "BRIEF    ▸ ready" + (" · audio rendered" if audio_name else "")]
    ticker = [f"{e['start'] or 'ALL DAY'} · {e['title']}" for e in events] + ctx["news"]
    return {
        "name": me.get("name", ""),
        "address": me.get("address", "sir"),
        "greeting": f"{greeting(now.hour)}, {me.get('address', 'sir')}",
        "generated": now.isoformat(timespec="seconds"),
        "headline": brief["headline"],
        "closer": brief["closer"],
        "alert": {"label": "DON'T MISS", "text": brief["one_thing"]} if brief["one_thing"] else None,
        "connectors": connectors,
        "stats": [
            {"label": "INBOX · UNREAD", "value": unread, "max": max(len(mails), 1)},
            {"label": "TASKS · URGENT", "value": sum(t["urgent"] or t["overdue"] for t in tasks), "max": max(len(tasks), 1)},
            {"label": "DAY · BOOKED HRS", "value": booked_hours(events), "max": 9},
            {"label": "RAIN CHANCE %", "value": wx["rain"] if wx else 0, "max": 100},
        ],
        "figures": [
            {"label": "EVENTS", "value": len(events)},
            {"label": "NEEDS REPLY", "value": len(reply)},
            {"label": "OPEN TASKS", "value": len(tasks)},
            {"label": wx["city"].upper() if wx else "WEATHER", "value": f"{wx['temp']}°" if wx else "--"},
        ],
        "priorities": brief["priorities"],
        "schedule": [{"time": e["start"] or "ALL DAY", "title": e["title"], "conflict": bool(e.get("conflict"))}
                     for e in events],
        "inbox": [{"from": m["from"], "subject": m["subject"], "group": m.get("group", "fyi")}
                  for m in mails if m.get("group") != "ignore"][:8],
        "weather": wx,
        "log": log,
        "ticker": ticker or ["All systems nominal"],
        "spoken": brief["spoken"],
        "brief_text": " ".join(brief["spoken"]),
        "audio": f"{audio_name}?v={int(time.time())}" if audio_name else None,
    }


def write_outputs(cfg, data, brief, mails):
    oc = cfg.get("output", {})
    resolve(oc.get("data_js", "jarvis_data.js")).write_text(
        "// Generated by brief.py — do not edit by hand.\nwindow.JARVIS_DATA = "
        + json.dumps(data, ensure_ascii=False, indent=2) + ";\n", encoding="utf-8")
    resolve(oc.get("brief_txt", "brief.txt")).write_text("\n".join(brief["spoken"]) + "\n", encoding="utf-8")

    by_id = {m["id"]: m for m in mails}
    drafts = [(by_id[d.get("id")], str(d.get("body", ""))) for d in brief["drafts"] if d.get("id") in by_id and d.get("body")]
    if drafts:
        md = ["# Draft replies (not sent)\n"]
        md += [f"## To {m['from']} <{m['address']}> — Re: {m['subject']}\n\n{body}\n" for m, body in drafts]
        (ROOT / "drafts.md").write_text("\n".join(md), encoding="utf-8")
        if cfg.get("email", {}).get("save_drafts"):
            for m, body in drafts:
                try:
                    c.save_draft(cfg, m["address"], m["subject"], body, m.get("message_id", ""))
                except Exception as e:  # noqa: BLE001
                    print(f"[jarvis] could not save draft: {e}")

    archive = resolve(oc.get("archive_dir", "briefs"))
    archive.mkdir(exist_ok=True)
    day = data["generated"][:10]
    md = [f"# Brief — {day}", "", f"**{data['headline']}**", "", *brief["spoken"], "", "## Priorities"]
    md += [f"{i}. **{p.get('title', '')}** — {p.get('why', '')}" for i, p in enumerate(brief["priorities"], 1)]
    md += ["", "## Schedule"] + [f"- {s['time']} {s['title']}{' ⚠ conflict' if s['conflict'] else ''}" for s in data["schedule"]]
    md += ["", "## Inbox"] + [f"- [{m['group']}] {m['from']}: {m['subject']}" for m in data["inbox"]]
    (archive / f"{day}.md").write_text("\n".join(md) + "\n", encoding="utf-8")


def run(cfg=None, audio=True, use_llm=True):
    cfg = cfg or load_config()
    now = dt.datetime.now(c.local_tz(cfg))
    results = gather(cfg)
    ctx = {
        "now": now,
        "events": results["Calendar"][2],
        "mails": results["Inbox"][2],
        "tasks": results["Tasks"][2],
        "weather": results["Weather"][2],
        "news": results["News"][2],
    }
    brief = (use_llm and llm.provider(cfg) != "none" and ai_brief(cfg, ctx)) or template_brief(cfg, ctx)

    audio_name, voice_failed = None, False
    if audio and voice.engine(cfg) != "browser":
        out = voice.synthesize(cfg, " ".join(brief["spoken"]), resolve(cfg["output"].get("audio", "jarvis_brief.mp3")))
        audio_name, voice_failed = (out.name if out else None), out is None

    data = build_data(cfg, ctx, brief, results, audio_name, voice_failed)
    write_outputs(cfg, data, brief, ctx["mails"])
    return data


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--no-audio", action="store_true", help="skip text-to-speech")
    ap.add_argument("--no-llm", action="store_true", help="use the built-in template instead of an AI model")
    args = ap.parse_args()
    result = run(audio=not args.no_audio, use_llm=not args.no_llm)
    print("\n".join(result["spoken"]))
    for conn in result["connectors"]:
        print(f"  {'●' if conn['online'] else '○'} {conn['name']:<9} {conn['detail']}")
