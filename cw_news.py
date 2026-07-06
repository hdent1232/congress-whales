"""Free ticker news via Google News RSS, aligned to a trade date when possible.

Google News RSS returns dated headlines covering roughly the last few weeks, which
lines up with the recency of congressional filings. When a trade date is given we
label each headline by how many days before/after the trade it was published, so you
can see what broke around a member's buy or sell.

Honest limit: this is public web news, not a curated market-news feed, and it only
reaches back a few weeks — good for recent trades, blind to old ones. Drop in a
FINNHUB_API_KEY later if you want deeper, strictly date-ranged company news.
"""
from __future__ import annotations

import datetime as dt
import email.utils
import html
import json
import re
import urllib.parse

import cw_config
from cw_http import fetch

_RSS = ("https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en")


def _clean(s: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", s or "")).strip()


def _finnhub_news(ticker: str, around_iso: str | None, window_days: int,
                  limit: int, key: str) -> list[dict]:
    """Date-ranged company news from Finnhub (needs a free API key)."""
    if around_iso:
        center = dt.date.fromisoformat(around_iso)
    else:
        center = dt.date.today()
    frm = (center - dt.timedelta(days=window_days)).isoformat()
    to = (center + dt.timedelta(days=window_days)).isoformat()
    url = (f"https://finnhub.io/api/v1/company-news?symbol={ticker.upper()}"
           f"&from={frm}&to={to}&token={key}")
    data = json.loads(fetch(url, ttl=1800).decode("utf-8", "replace"))
    items = []
    for a in data:
        try:
            d = dt.datetime.utcfromtimestamp(a["datetime"]).date()
        except Exception:
            continue
        it = {"headline": a.get("headline", ""), "url": a.get("url", ""),
              "date": d.isoformat(), "source": a.get("source", ""),
              "days_from_trade": (d - center).days if around_iso else None}
        items.append(it)
    if around_iso:
        items.sort(key=lambda it: abs(it["days_from_trade"]))
    else:
        items.sort(key=lambda it: it["date"], reverse=True)
    return items[:limit]


def get_news(ticker: str, company: str | None = None, around_iso: str | None = None,
             window_days: int = 10, limit: int = 8) -> list[dict]:
    # Prefer Finnhub (true date-ranged company news) when a key is configured.
    key = cw_config.get("FINNHUB_API_KEY")
    if key:
        try:
            hits = _finnhub_news(ticker, around_iso, window_days, limit, key)
            if hits:
                return hits
        except Exception:
            pass  # fall back to free Google News
    terms = f'"{company}" {ticker} stock' if company else f"{ticker} stock"
    url = _RSS.format(q=urllib.parse.quote(terms))
    try:
        xml = fetch(url, ttl=1800).decode("utf-8", "replace")
    except Exception:
        return []

    items = []
    seen = set()
    for block in re.findall(r"<item>(.*?)</item>", xml, re.S):
        title = re.search(r"<title>(.*?)</title>", block, re.S)
        link = re.search(r"<link>(.*?)</link>", block, re.S)
        pub = re.search(r"<pubDate>(.*?)</pubDate>", block, re.S)
        src = re.search(r"<source[^>]*>(.*?)</source>", block, re.S)
        if not title or not pub:
            continue
        try:
            pub_dt = email.utils.parsedate_to_datetime(pub.group(1).strip()).date()
        except Exception:
            continue
        headline = _clean(title.group(1))
        dedup_key = re.sub(r"\s*-\s*[^-]+$", "", headline).lower()[:60]
        if dedup_key in seen:
            continue
        seen.add(dedup_key)
        items.append({
            "headline": headline,
            "url": _clean(link.group(1)) if link else "",
            "date": pub_dt.isoformat(),
            "source": _clean(src.group(1)) if src else "",
            "days_from_trade": None,
        })

    if around_iso:
        trade = dt.date.fromisoformat(around_iso)
        near = []
        for it in items:
            delta = (dt.date.fromisoformat(it["date"]) - trade).days
            if abs(delta) <= window_days:
                it["days_from_trade"] = delta
                near.append(it)
        near.sort(key=lambda it: abs(it["days_from_trade"]))
        if near:
            return near[:limit]
        # nothing in-window -> fall through to the latest headlines

    items.sort(key=lambda it: it["date"], reverse=True)
    return items[:limit]
