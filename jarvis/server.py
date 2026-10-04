#!/usr/bin/env python3
"""Local Jarvis server: dashboard + talk-and-listen voice loop. Standard library only.

    python3 server.py            # http://localhost:8765
    python3 server.py --brief    # run the morning brief first

Endpoints
  GET  /api/status   which brain / voice / ears are available
  POST /api/ask      {"text": "...", "history": [...]} -> {"reply": "...", "audio": url|null}
  POST /api/brief    re-run the morning brief, returns the new dashboard data
  POST /api/tts      {"text": "..."} -> audio
  POST /api/stt      raw audio body -> {"text": "..."} (needs faster-whisper)
"""
import argparse
import itertools
import json
import re
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import brief
import llm
import voice
from config import ROOT, load_config, resolve

CACHE = ROOT / ".cache"
PRIVATE = {"jarvis.toml", "me.md", "drafts.md", ".mcp.json"}
_counter = itertools.count()
_brief_lock = threading.Lock()

ASK_RULES = """
You are speaking out loud through the J.A.R.V.I.S. dashboard. Reply in 1-3 short spoken sentences:
no markdown, no lists, no emoji. You cannot send, post, buy or delete anything; if asked, offer a draft
or tell the user what to do. Today's dashboard data (JSON) follows — use it to answer questions about
the day:
"""


def today_data(cfg):
    path = resolve(cfg.get("output", {}).get("data_js", "jarvis_data.js"))
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    try:
        return json.loads(text[text.index("{"):text.rindex("}") + 1])
    except ValueError:
        return {}


def speak_to_file(cfg, text):
    if voice.engine(cfg) == "browser":
        return None
    CACHE.mkdir(exist_ok=True)
    n = next(_counter)
    out = voice.synthesize(cfg, text, CACHE / f"reply-{n % 20}.mp3")
    return f".cache/{out.name}?n={n}" if out else None


class Handler(SimpleHTTPRequestHandler):
    cfg = None

    def log_message(self, fmt, *args):
        if "/api/" in self.path:
            super().log_message(fmt, *args)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def _json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        return self.rfile.read(int(self.headers.get("Content-Length") or 0))

    def do_GET(self):
        name = Path(self.path.split("?")[0]).name
        if name in PRIVATE or name.endswith(".toml"):
            return self.send_error(404)
        if self.path.startswith("/api/status"):
            return self._json({
                "server": True,
                "brain": llm.provider(self.cfg),
                "brain_detail": llm.describe(self.cfg),
                "voice": voice.engine(self.cfg),
                "stt": voice.stt_available(),
            })
        return super().do_GET()

    def do_POST(self):
        cfg = self.cfg
        try:
            if self.path == "/api/ask":
                req = json.loads(self._body() or b"{}")
                text = str(req.get("text", "")).strip()[:2000]
                if not text:
                    return self._json({"reply": None})
                if re.search(r"\b(refresh|update|rerun|re-run|regenerate)\b.*\bbrief", text, re.I):
                    with _brief_lock:
                        data = brief.run(cfg)
                    return self._json({"reply": data["spoken"][0] + " Your brief is refreshed.",
                                       "action": "reload", "audio": None})
                if llm.provider(cfg) == "none":
                    return self._json({"reply": None})
                history = [m for m in req.get("history", [])[-10:]
                           if isinstance(m, dict) and m.get("role") in ("user", "assistant")]
                system = brief.persona(cfg) + ASK_RULES + json.dumps(today_data(cfg), ensure_ascii=False)[:12000]
                reply = llm.chat(cfg, system, history + [{"role": "user", "content": text}])
                if not reply:
                    return self._json({"reply": None, "error": "brain offline"})
                reply = re.sub(r"[*_#`]+", "", reply)
                return self._json({"reply": reply, "audio": speak_to_file(cfg, reply)})

            if self.path == "/api/brief":
                with _brief_lock:
                    return self._json(brief.run(cfg))

            if self.path == "/api/tts":
                text = str(json.loads(self._body() or b"{}").get("text", ""))[:5000]
                url = speak_to_file(cfg, text) if text else None
                return self._json({"audio": url})

            if self.path == "/api/stt":
                if not voice.stt_available():
                    return self._json({"error": "pip install faster-whisper"}, 501)
                ctype = self.headers.get("Content-Type", "audio/webm")
                suffix = ".ogg" if "ogg" in ctype else ".mp4" if "mp4" in ctype else ".wav" if "wav" in ctype else ".webm"
                return self._json({"text": voice.transcribe(cfg, self._body(), suffix)})
        except Exception as e:  # noqa: BLE001
            print(f"[jarvis] {self.path} failed: {e}")
            return self._json({"error": str(e)}, 500)
        self.send_error(404)


def main():
    ap = argparse.ArgumentParser(description="J.A.R.V.I.S. local server")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--host", default="127.0.0.1", help="use 0.0.0.0 to reach it from your phone on the same Wi-Fi")
    ap.add_argument("--brief", action="store_true", help="run the morning brief before serving")
    args = ap.parse_args()

    Handler.cfg = load_config()
    if args.brief or not resolve(Handler.cfg["output"].get("data_js", "jarvis_data.js")).exists():
        print("Composing your brief...")
        brief.run(Handler.cfg)
    print(f"J.A.R.V.I.S. online  ·  brain: {llm.describe(Handler.cfg)}  ·  voice: {voice.engine(Handler.cfg)}")
    print(f"Open http://localhost:{args.port}  (config: {Handler.cfg['_source']})")
    server = ThreadingHTTPServer((args.host, args.port), partial(Handler, directory=str(ROOT)))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
