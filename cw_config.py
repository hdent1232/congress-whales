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
