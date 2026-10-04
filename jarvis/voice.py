"""Free voice: edge-tts (online neural), Piper (offline neural) or the browser.

Replaces the paid Fish Audio API. `synthesize()` returns the written file path,
or None when the dashboard should fall back to the browser's speechSynthesis.
"""
import asyncio
import shutil
import subprocess
import tempfile
from pathlib import Path

from config import resolve


def engine(cfg):
    name = cfg.get("voice", {}).get("engine", "edge")
    if name == "edge":
        try:
            import edge_tts  # noqa: F401
            return "edge"
        except ImportError:
            return "edge-cli" if shutil.which("edge-tts") else "browser"
    if name == "piper":
        model = cfg["voice"].get("piper_model", "")
        return "piper" if shutil.which("piper") and model and resolve(model).exists() else "browser"
    return "browser"


def synthesize(cfg, text, out_path):
    """Writes speech for `text` to out_path (.mp3 for edge, .wav for piper)."""
    vc, eng = cfg.get("voice", {}), engine(cfg)
    out_path = Path(out_path)
    voice = vc.get("edge_voice", "en-GB-RyanNeural")
    rate, pitch = vc.get("edge_rate", "+0%"), vc.get("edge_pitch", "+0Hz")
    try:
        if eng == "edge":
            import edge_tts

            async def run():
                await edge_tts.Communicate(text, voice, rate=rate, pitch=pitch).save(str(out_path))

            asyncio.run(run())
            return out_path
        if eng == "edge-cli":
            subprocess.run(["edge-tts", "--voice", voice, f"--rate={rate}", f"--pitch={pitch}",
                            "--text", text, "--write-media", str(out_path)], check=True, timeout=120)
            return out_path
        if eng == "piper":
            wav = out_path.with_suffix(".wav")
            subprocess.run(["piper", "--model", str(resolve(vc["piper_model"])), "--output_file", str(wav)],
                           input=text, text=True, check=True, timeout=120)
            return wav
    except Exception as e:  # noqa: BLE001
        print(f"[jarvis] TTS ({eng}) failed: {e}")
    for leftover in (out_path, out_path.with_suffix(".wav")):
        if leftover.exists() and leftover.stat().st_size == 0:
            leftover.unlink()
    return None


_whisper = {}


def stt_available():
    try:
        import faster_whisper  # noqa: F401
        return True
    except ImportError:
        return False


def transcribe(cfg, audio_bytes, suffix=".webm"):
    """Local, free speech-to-text with faster-whisper (optional dependency)."""
    from faster_whisper import WhisperModel

    name = cfg.get("voice", {}).get("whisper_model", "base.en")
    if name not in _whisper:
        _whisper[name] = WhisperModel(name, device="cpu", compute_type="int8")
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=True) as f:
        f.write(audio_bytes)
        f.flush()
        segments, _ = _whisper[name].transcribe(f.name, vad_filter=True)
        return " ".join(s.text.strip() for s in segments).strip()
