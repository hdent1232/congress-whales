"""Shared HTTP layer: polite User-Agent, gzip, on-disk caching, gentle SEC rate limit.

Everything here uses the Python standard library only (urllib) so the server has
as few moving parts as possible. The only third-party dependencies in the whole
project are `mcp` (the server framework) and `pypdf` (to read House PTR PDFs).
"""
from __future__ import annotations

import gzip
import hashlib
import io
import json
import os
import time
import threading
import urllib.error
import urllib.request

# SEC and the House Clerk both ask automated clients to identify themselves with a
# contact address. Set CW_CONTACT_EMAIL so they can reach you if your traffic looks
# off; it keeps you on the right side of their fair-access policies.
CONTACT = os.environ.get("CW_CONTACT_EMAIL", "anonymous@example.com")
UA = f"congress-whales-mcp/0.1 (contact: {CONTACT})"

# Cache root: honour CW_CACHE_DIR (set when running as a packaged .exe, where the
# script dir is a temp extraction folder), otherwise a .cache next to the source.
CACHE_DIR = os.path.join(os.environ.get("CW_CACHE_DIR")
                         or os.path.dirname(os.path.abspath(__file__)), ".cache")
os.makedirs(CACHE_DIR, exist_ok=True)

# SEC asks for <= 10 requests/second. We keep a comfortable margin.
_SEC_MIN_INTERVAL = 0.15
_last_hit: dict[str, float] = {}
_rate_lock = threading.Lock()


def _cache_path(url: str) -> str:
    return os.path.join(CACHE_DIR, hashlib.sha256(url.encode()).hexdigest()[:32])


def _rate_limit(rate_key: str | None) -> None:
    if not rate_key:
        return
    # Serialize across threads so concurrent enrichment never bursts past SEC's
    # 10 req/s fair-access limit.
    with _rate_lock:
        wait = _SEC_MIN_INTERVAL - (time.monotonic() - _last_hit.get(rate_key, 0.0))
        if wait > 0:
            time.sleep(wait)
        _last_hit[rate_key] = time.monotonic()


def fetch(url: str, *, ttl: int = 3600, binary: bool = False,
          rate_key: str | None = None, headers: dict | None = None,
          timeout: int = 60) -> bytes:
    """GET `url` with disk caching. Returns raw bytes.

    ttl<=0 disables the cache for this call.
    """
    cp = _cache_path(url)
    if ttl > 0 and os.path.exists(cp) and (time.time() - os.path.getmtime(cp)) < ttl:
        with open(cp, "rb") as fh:
            return fh.read()

    _rate_limit(rate_key)
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Accept-Encoding": "gzip",
                                               **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
        if resp.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)

    if ttl > 0:
        tmp = cp + ".tmp"
        with open(tmp, "wb") as fh:
            fh.write(raw)
        os.replace(tmp, cp)
    return raw


def fetch_json(url: str, **kw):
    return json.loads(fetch(url, **kw).decode("utf-8", "replace"))
