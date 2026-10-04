"""Loads jarvis.toml (falls back to jarvis.example.toml) and exposes paths."""
import os
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _deep_merge(base, extra):
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
    return base


def load_config():
    example = ROOT / "jarvis.example.toml"
    path = Path(os.environ.get("JARVIS_CONFIG", ROOT / "jarvis.toml"))
    with open(example, "rb") as f:
        cfg = tomllib.load(f)
    if path.exists():
        with open(path, "rb") as f:
            _deep_merge(cfg, tomllib.load(f))
        cfg["_source"] = str(path)
    else:
        cfg["_source"] = str(example)

    # Secrets may come from the environment instead of the file.
    env = {
        ("email", "password"): "JARVIS_EMAIL_PASSWORD",
        ("llm", "api_key"): "JARVIS_LLM_API_KEY",
    }
    for (section, key), var in env.items():
        if os.environ.get(var):
            cfg.setdefault(section, {})[key] = os.environ[var]
    return cfg


def resolve(path_str):
    """Resolve a path from the config relative to the jarvis folder."""
    p = Path(os.path.expanduser(path_str))
    return p if p.is_absolute() else ROOT / p
