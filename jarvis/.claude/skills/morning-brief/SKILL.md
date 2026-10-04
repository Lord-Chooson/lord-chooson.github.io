---
name: morning-brief
description: Runs my J.A.R.V.I.S. morning brief. Use when I say "run my morning brief", "brief me", "good morning Jarvis", or ask what's on today.
---

# Morning brief

1. Run `python3 brief.py` in this folder. It pulls calendar (iCal), inbox (IMAP, read-only), tasks
   (`tasks.md`), weather (Open-Meteo) and news (RSS), writes `brief.txt`, `jarvis_data.js`,
   `jarvis_brief.mp3` and `briefs/<today>.md`, and prints each source as ● online / ○ offline.
2. Read `brief.txt` and `drafts.md` (if present).
3. Reply with:
   - the spoken brief (6-8 lines, as written),
   - any source that is offline and the one-line fix (see README "Troubleshooting"),
   - the draft replies, clearly labelled **not sent**.
4. End with: "What should I handle first?"

Rules: never send, post or delete anything. If I approve a draft, tell me it's in my Drafts folder
(when `save_drafts = true`) or show me the text to paste — do not send it yourself.
