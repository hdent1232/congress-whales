"""Tiny config loader for secrets/settings that must NOT be committed.

Precedence: environment variable > config.json (in the cache dir, then next to the
source). config.json is git-ignored so an API key never ends up in the public repo.
Create it from config.example.json.
"""
from __future__ import annotations

import json
import os

_cfg: dict | None = None


def _load() -> dict:
    global _cfg
    if _cfg is None:
        _cfg = {}
        seen = set()
        for base in (os.environ.get("CW_CACHE_DIR"),
                     os.path.dirname(os.path.abspath(__file__))):
            if not base or base in seen:
                continue
            seen.add(base)
            p = os.path.join(base, "config.json")
            if os.path.exists(p):
                try:
                    with open(p, encoding="utf-8") as fh:
                        _cfg.update(json.load(fh))
                except Exception:
                    pass
    return _cfg


def get(key: str, default=None):
    v = os.environ.get(key)
    if v:
        return v
    v = _load().get(key)
    return v if v not in (None, "") else default


def config_path() -> str:
    """Where config.json is written (matches the first location get() reads)."""
    base = os.environ.get("CW_CACHE_DIR") or os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "config.json")


def set_value(key: str, value: str) -> None:
    """Persist (or clear, if value is falsy) a config value to config.json."""
    global _cfg
    p = config_path()
    data = {}
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception:
            data = {}
    if value:
        data[key] = value
    else:
        data.pop(key, None)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
    _cfg = None  # force reload on next get()
