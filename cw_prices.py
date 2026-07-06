"""Free price data via Yahoo's public chart endpoint (no key).

One call returns the current price plus daily history. We cache the parsed history
per ticker so we can compute the return since *any* trade date (needed for
per-member performance) without refetching.
"""
from __future__ import annotations

import datetime as dt

from cw_http import fetch_json

_YF = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=2y&interval=1d"
_BROWSER_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

# ticker -> {"price":float|None, "currency":str|None, "series":[(date, close)]}
_hist_cache: dict[str, dict] = {}


def _yahoo_symbol(ticker: str) -> str:
    return ticker.upper().replace(".", "-")


def _history(ticker: str) -> dict:
    tk = ticker.upper()
    if tk in _hist_cache:
        return _hist_cache[tk]
    out = {"price": None, "currency": None, "series": []}
    try:
        j = fetch_json(_YF.format(sym=_yahoo_symbol(tk)), ttl=1800, headers=_BROWSER_UA)
        res = j["chart"]["result"][0]
        meta = res["meta"]
        p = meta.get("regularMarketPrice")
        out["price"] = round(p, 2) if p is not None else None
        out["currency"] = meta.get("currency")
        ts = res.get("timestamp") or []
        closes = res["indicators"]["quote"][0].get("close") or []
        out["series"] = [(dt.date.fromtimestamp(t), c)
                         for t, c in zip(ts, closes) if c is not None]
    except Exception:
        pass
    _hist_cache[tk] = out
    return out


def return_since(ticker: str, since_iso: str | None) -> dict:
    """{"price", "return_since_pct", "price_on_date"} — return from a trade date to now."""
    h = _history(ticker)
    out = {"price": h["price"], "return_since_pct": None, "price_on_date": None}
    if since_iso and h["series"] and h["price"]:
        try:
            target = dt.date.fromisoformat(since_iso)
        except ValueError:
            return out
        prior = [c for d, c in h["series"] if d <= target]
        base = prior[-1] if prior else h["series"][0][1]
        if base:
            out["price_on_date"] = round(base, 2)
            out["return_since_pct"] = round((h["price"] - base) / base * 100, 1)
    return out


def biggest_move(ticker: str, around_iso: str | None, window_days: int = 12) -> dict | None:
    """Largest single-day % move within +/- window_days of a trade date.

    Helps answer "did a big price move happen right around the trade?".
    """
    if not around_iso:
        return None
    h = _history(ticker)
    s = h["series"]
    if len(s) < 2:
        return None
    try:
        target = dt.date.fromisoformat(around_iso)
    except ValueError:
        return None
    best = None
    for i in range(1, len(s)):
        d, c = s[i]
        pc = s[i - 1][1]
        if not pc or abs((d - target).days) > window_days:
            continue
        pct = (c - pc) / pc * 100
        if best is None or abs(pct) > abs(best["pct"]):
            best = {"date": d.isoformat(), "pct": round(pct, 1),
                    "days_from_trade": (d - target).days}
    return best


def get_price_info(ticker: str, since_iso: str | None = None) -> dict:
    """Back-compat wrapper: price + currency + return since a date."""
    h = _history(ticker)
    r = return_since(ticker, since_iso)
    return {"price": h["price"], "currency": h["currency"],
            "return_since_pct": r["return_since_pct"], "price_on_date": r["price_on_date"]}
