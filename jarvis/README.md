# J.A.R.V.I.S. — your own Jarvis, built only from free tools

This is a rebuild of [Cindy Zhu's "Build your own Jarvis with Claude"](https://cindyzhu.com.au/guides/build-your-own-jarvis-with-claude)
using the Claude plan you already have as the brain, and free tools for everything else — no new subscriptions. Jarvis reads you a morning brief in a British butler
voice, shows your day on a cinematic Iron Man dashboard, and you can talk to it.

**Live demo (sample data, browser voice):** https://lord-chooson.github.io/jarvis/

## What changed: paid → free

| Part of Jarvis | Original guide | Used here |
|---|---|---|
| Brain | Claude Pro / Max | **Claude, on the plan you already have**, through the Claude Code CLI (`claude -p`). No API key and no extra cost. If Claude is unavailable, Jarvis can fall back to Ollama, a free Groq/Gemini tier, or a built-in template. |
| Voice out | Fish Audio (paid after the trial) | **edge-tts** — free Microsoft neural voices (`en-GB-RyanNeural`). Offline: **Piper**. Zero install: the browser's own voice. |
| Voice in | Claude Code `/voice` | Browser **Web Speech API** (Chrome/Edge), or local **faster-whisper** for other browsers. |
| Calendar | Google Calendar connector | Any calendar's **secret iCal (.ics) link**: Google, Outlook, iCloud. No OAuth. |
| Email | Gmail connector | **IMAP** with a Gmail App Password. Read-only, and replies are only ever saved as drafts. |
| Notes and brief log | Notion | Plain **markdown**: `tasks.md` and `briefs/<date>.md`. Works inside an Obsidian vault. |
| Weather / news | — | **Open-Meteo** (no key) and **RSS** feeds. |
| Dashboard | Claude-built HTML | `index.html`: one self-contained page with the 680-point canvas sphere, HUD, ticker and BRIEF ME button. |
| Browser automation | Claude for Chrome (paid plans) | **Playwright MCP** (`.mcp.json`), free and open source. |
| Social posting | Metricool / Buffer | **Postiz**, self-hosted (free): https://github.com/gitroomhq/postiz-app |
| Scheduled routine | Claude cloud routines | **cron** (macOS/Linux) or **Task Scheduler** (Windows). |
| Revenue / ad spend | RevenueCat, Meta Ads MCP | Not included. They only matter if you already pay for those services. |

## Quick start (about 5 minutes)

You need Python 3.11 or newer and Claude Code signed in to your Claude account
(`npm install -g @anthropic-ai/claude-code`, then run `claude` once and log in).

```bash
git clone https://github.com/lord-chooson/lord-chooson.github.io
cd lord-chooson.github.io/jarvis

cp jarvis.example.toml jarvis.toml   # settings (git-ignored)
cp me.example.md me.md               # who you are, so Jarvis knows you (git-ignored)
cp tasks.example.md tasks.md         # your to-do list (git-ignored)

pip install edge-tts                 # optional: the British butler voice
python3 server.py --brief            # then open http://localhost:8765
```

Click **BRIEF ME** to hear the brief. Press the mic button (or **Space**) and talk to Jarvis, or type in **Ask Jarvis…**.
**SYNC** runs the brief again.

### 1. The brain: your Claude plan

Nothing to set up beyond being signed in to Claude Code: `provider = "claude"` is the default. Jarvis calls
`claude -p` for the brief and for every question, so it runs on your Pro/Max plan. Set `claude_model = "sonnet"`
for faster spoken replies, or `"opus"` for a more thoughtful brief.

Jarvis removes `ANTHROPIC_API_KEY` from Claude's environment (`use_subscription = true`), so a leftover API key
can't quietly switch you to pay-per-use billing.

**Fallbacks (optional):** if you ever want Jarvis to work without Claude, set `provider = "auto"` and install
Ollama (https://ollama.com, `ollama pull llama3.2`), or add a free Groq or Gemini key. You can keep keys and
passwords out of the file with the `JARVIS_LLM_API_KEY` and `JARVIS_EMAIL_PASSWORD` environment variables.

### 2. Connect your calendar (free, no OAuth)

In Google Calendar, go to **Settings → [your calendar] → Integrate calendar → Secret address in iCal format**.
Paste that link into `ics_urls`. Outlook and iCloud have "publish calendar" links that work the same way.

### 3. Connect your inbox (read-only)

For Gmail: turn on 2-Step Verification, create an App Password at https://myaccount.google.com/apppasswords,
and fill in the `[email]` section. Jarvis opens the mailbox **read-only**, so your mail never gets marked as read.
It sorts mail into *reply / FYI / ignore* and writes suggested replies to `drafts.md`. If you set `save_drafts = true`,
the replies are also saved to your Gmail Drafts folder. **Nothing is ever sent.**

### 4. Run the brief every morning

```bash
# macOS / Linux: crontab -e   (weekdays at 07:45)
45 7 * * 1-5 cd /path/to/jarvis && /usr/bin/python3 brief.py >> brief.log 2>&1
```

On Windows, use Task Scheduler with the action `python brief.py` and set "Start in" to the jarvis folder.
Leave `server.py` running, or start it at login, and the dashboard reloads the new brief by itself.

### 5. Talk to it from your phone (optional)

Run `python3 server.py --host 0.0.0.0`, then open `http://<your-computer-ip>:8765` on the same Wi-Fi.
Anyone on that network can see your dashboard, so only do this on a network you trust.

## Files

```
jarvis/
├── index.html              cinematic dashboard (works on its own, on GitHub Pages too)
├── jarvis_data.sample.js   demo data; brief.py writes the real jarvis_data.js
├── brief.py                morning brief: gather → compose → speak → write
├── server.py               localhost server: dashboard + /api/ask, /api/tts, /api/stt, /api/brief
├── connectors.py           iCal, IMAP, tasks.md, Open-Meteo, RSS
├── llm.py                  Claude CLI (default) / Ollama / OpenAI-compatible free tiers / none
├── voice.py                edge-tts / Piper / browser, plus optional faster-whisper
├── jarvis.example.toml     settings template
├── CLAUDE.md               Jarvis's personality and hard rules (imports me.md)
├── me.example.md           your identity file template
├── tasks.example.md        to-do template ("!" = urgent, "due:YYYY-MM-DD")
├── .claude/skills/         morning-brief and customer-support skills for Claude Code
├── .claude/agents/tom.md   example developer sub-agent
└── .mcp.json               free Playwright MCP for browser automation
```

These files are **git-ignored** so your personal data never reaches this public repo: `jarvis.toml`, `me.md`,
`tasks.md`, `drafts.md`, `brief.txt`, `briefs/`, `jarvis_data.js`, and the audio files.

## Using it from Claude Code (optional)

If you open this folder in Claude Code, it reads `CLAUDE.md` and the `morning-brief` skill on its own.
Say "brief me" and it runs `brief.py` and reads you the result. The Playwright MCP in `.mcp.json` gives it a
free browser. The `customer-support` skill drafts replies from your FAQ and refund policy, and `tom` is a
sub-agent for code work.

## Safety: keep a human in the loop

- Email is read-only. Replies are drafts only. Jarvis has no code path that sends mail.
- The `/api/ask` brain can only talk. It cannot send, buy, post or delete anything.
- The server only listens on `127.0.0.1` unless you pass `--host`.
- Jarvis treats email and web content as data, never as instructions (see `CLAUDE.md`).
- Before you give the Playwright MCP a site, keep it on per-action approval, and never use it on banking sites.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `BRAIN offline templates` or replies are empty | Run `claude` in a terminal and make sure you're logged in, then try `claude -p "hello"`. |
| `VOICE edge failed — browser fallback` | Run `pip install edge-tts` and check you're online, or use `engine = "piper"` to stay offline. |
| Mic does nothing | Use Chrome or Edge at `http://localhost` (not `file://`), or `pip install faster-whisper`. |
| `INBOX IMAP failed` | You need an App Password, not your normal password, and IMAP must be enabled in Gmail settings. |
| Calendar shows 0 events | Use the **secret** iCal address. The public one only works if the calendar is public. |
| A recurring event is missing | The built-in iCal parser handles daily, weekly, monthly and yearly repeats. Rarer rules such as "second Tuesday of the month" can be missed. |
