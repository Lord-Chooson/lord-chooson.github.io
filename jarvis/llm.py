"""The brain: one `chat()` over several LLM backends.

claude  - Claude Code CLI (`claude -p`) on your existing Claude subscription (default)
ollama  - local models, free and offline
openai  - any OpenAI-compatible API with a free tier (Groq, Gemini, OpenRouter :free)
none    - no model; callers fall back to templates
"""
import json
import os
import shutil
import subprocess
import urllib.error
import urllib.request

from config import ROOT

_cache = {}


def _post(url, payload, headers=None, timeout=120):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(), method="POST",
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def _ollama_up(lc):
    try:
        with urllib.request.urlopen(lc.get("ollama_url", "http://localhost:11434") + "/api/tags", timeout=2):
            return True
    except Exception:  # noqa: BLE001
        return False


def provider(cfg):
    lc = cfg.get("llm", {})
    choice = lc.get("provider", "auto")
    if choice == "claude" and not shutil.which("claude"):
        choice = "auto"  # Claude Code not installed: use whatever fallback is available
    if choice != "auto":
        return choice
    if "auto" not in _cache:
        if shutil.which("claude"):
            _cache["auto"] = "claude"
        elif _ollama_up(lc):
            _cache["auto"] = "ollama"
        elif lc.get("api_key"):
            _cache["auto"] = "openai"
        else:
            _cache["auto"] = "none"
    return _cache["auto"]


def describe(cfg):
    lc, p = cfg.get("llm", {}), provider(cfg)
    return {
        "ollama": f"Ollama · {lc.get('ollama_model')}",
        "openai": f"{lc.get('model')}",
        "claude": "Claude" + (f" · {lc['claude_model']}" if lc.get("claude_model") else ""),
        "none": "offline templates",
    }.get(p, p)


def chat(cfg, system, messages, json_mode=False):
    """messages: [{"role": "user"|"assistant", "content": str}]. Returns text or None."""
    lc, p = cfg.get("llm", {}), provider(cfg)
    timeout = int(lc.get("timeout", 120))
    try:
        if p == "ollama":
            body = {
                "model": lc.get("ollama_model", "llama3.2"),
                "messages": [{"role": "system", "content": system}, *messages],
                "stream": False,
            }
            if json_mode:
                body["format"] = "json"
            out = _post(lc.get("ollama_url", "http://localhost:11434") + "/api/chat", body, timeout=timeout)
            return out["message"]["content"].strip()

        if p == "openai":
            body = {"model": lc["model"], "messages": [{"role": "system", "content": system}, *messages]}
            if json_mode:
                body["response_format"] = {"type": "json_object"}
            out = _post(lc["base_url"].rstrip("/") + "/chat/completions", body,
                        headers={"Authorization": f"Bearer {lc.get('api_key', '')}"}, timeout=timeout)
            return out["choices"][0]["message"]["content"].strip()

        if p == "claude":
            transcript = "\n\n".join(
                ("User: " if m["role"] == "user" else "Jarvis: ") + m["content"] for m in messages
            )
            if len(messages) > 1:
                transcript += "\n\nReply as Jarvis to the last user message."
            cmd = ["claude", "-p", "--output-format", "text", "--append-system-prompt", system]
            if lc.get("claude_model"):
                cmd += ["--model", lc["claude_model"]]
            env = dict(os.environ)
            if lc.get("use_subscription", True):
                # An API key in the environment would bill the pay-per-use API instead of your plan.
                env.pop("ANTHROPIC_API_KEY", None)
                env.pop("ANTHROPIC_AUTH_TOKEN", None)
            # No tools are pre-approved, so in -p mode Claude can only talk, never act.
            res = subprocess.run(cmd, input=transcript, capture_output=True, text=True,
                                 timeout=timeout, cwd=ROOT, env=env)
            return res.stdout.strip() or None
    except (urllib.error.URLError, KeyError, IndexError, subprocess.SubprocessError, OSError, ValueError) as e:
        print(f"[jarvis] LLM ({p}) failed: {e}")
    return None


def parse_json(text):
    """Pull the first JSON object out of a model reply."""
    if not text:
        return None
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None
