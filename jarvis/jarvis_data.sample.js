// Demo data shown when no jarvis_data.js exists (e.g. on GitHub Pages).
// Run `python3 brief.py` to generate your real jarvis_data.js (git-ignored).
window.JARVIS_DATA = {
  name: "Tony",
  address: "Your Majesty",
  greeting: "Good morning, Your Majesty",
  generated: new Date().toISOString(),
  headline: "Investor deck is due at five",
  closer: "What should I handle first, Your Majesty?",
  alert: { label: "DON'T MISS", text: "Investor deck v3 is due today at 17:00 — slides 8 to 12 still need numbers." },
  connectors: [
    { name: "CALENDAR", online: true, detail: "4 events today" },
    { name: "INBOX", online: true, detail: "14 mails, 6 unread" },
    { name: "TASKS", online: true, detail: "9 open tasks" },
    { name: "WEATHER", online: true, detail: "17°C partly cloudy" },
    { name: "NEWS", online: true, detail: "6 headlines" },
    { name: "BRAIN", online: true, detail: "Ollama · llama3.2" },
    { name: "VOICE", online: true, detail: "edge" }
  ],
  stats: [
    { label: "INBOX · UNREAD", value: 6, max: 14 },
    { label: "TASKS · URGENT", value: 2, max: 9 },
    { label: "DAY · BOOKED HRS", value: 4.5, max: 9 },
    { label: "RAIN CHANCE %", value: 40, max: 100 }
  ],
  figures: [
    { label: "EVENTS", value: 4 },
    { label: "NEEDS REPLY", value: 3 },
    { label: "OPEN TASKS", value: 9 },
    { label: "LONDON", value: "17°" }
  ],
  priorities: [
    { title: "Finish investor deck v3", why: "due today at 17:00" },
    { title: "Reply to Pepper about the Q4 budget", why: "she's waiting on a yes/no" },
    { title: "Review Happy's security PR", why: "blocks Thursday's release" }
  ],
  schedule: [
    { time: "09:30", title: "Stand-up", conflict: false },
    { time: "11:00", title: "Design review — Mark 85", conflict: true },
    { time: "11:30", title: "Call with Rhodey", conflict: true },
    { time: "15:00", title: "Gym", conflict: false }
  ],
  inbox: [
    { from: "Pepper Potts", subject: "Q4 budget — need your call", group: "reply" },
    { from: "Happy Hogan", subject: "PR #212 ready for review", group: "reply" },
    { from: "Rhodey", subject: "Moving our call?", group: "reply" },
    { from: "GitHub", subject: "Your weekly digest", group: "fyi" }
  ],
  weather: { city: "London", temp: 17, condition: "partly cloudy", high: 19, low: 11, rain: 40, wind: 14 },
  log: [
    "CALENDAR ▸ 4 events today",
    "INBOX    ▸ 14 mails, 6 unread",
    "TASKS    ▸ 9 open tasks",
    "WEATHER  ▸ 17°C partly cloudy",
    "NEWS     ▸ 6 headlines",
    "BRAIN    ▸ composed with Ollama · llama3.2",
    "PRIORITY ▸ 3 selected",
    "BRIEF    ▸ ready"
  ],
  ticker: [
    "09:30 · Stand-up",
    "11:00 · Design review — Mark 85",
    "11:30 · Call with Rhodey",
    "15:00 · Gym",
    "Open-source models close the gap on frontier benchmarks",
    "Edge-TTS adds new British neural voices"
  ],
  spoken: [
    "Good morning, Your Majesty. It's a fine day to be productive.",
    "London is seventeen degrees and partly cloudy, with a forty percent chance of rain later.",
    "You have four events today. Your eleven o'clock design review overlaps with the call with Rhodey, so one of them should move.",
    "Three emails need a reply, starting with Pepper about the Q4 budget. I've drafted answers for your approval.",
    "Your top priorities: the investor deck, Pepper's budget, and Happy's security review.",
    "The one thing not to miss: the investor deck is due at five.",
    "What should I handle first, Your Majesty?"
  ],
  brief_text: "",
  audio: null
};
