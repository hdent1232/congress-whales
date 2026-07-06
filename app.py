"""Local dashboard server for congress-whales.

Tabs: Overview (KPIs + trends), Buys, Sells, All-trades (filterable), Members
(leaderboards + search + per-member portfolio), Fund overlap. Hovering a ticker
shows a profile card; clicking opens a drawer with price, news and (for members)
a disclosed-portfolio breakdown.

Heavy data is fetched once per window and cached to .cache/dashboard.json so the
window opens instantly on the last snapshot, then refreshes to the newest data.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

import cw_congress
import cw_institutions
import cw_members
import cw_meta
import cw_news
import cw_prices
from cw_http import fetch_json
from version import RELEASES_API, RELEASES_PAGE, VERSION

HOST = "127.0.0.1"
PORT = int(os.environ.get("CW_PORT", "8787"))
CACHE_DIR = os.path.join(os.environ.get("CW_CACHE_DIR")
                         or os.path.dirname(os.path.abspath(__file__)), ".cache")
_compute_lock = threading.Lock()
STOCK = cw_congress.STOCK_CODES


def _midpoint(t: dict) -> float:
    a, b = t.get("amount_min") or 0, t.get("amount_max") or 0
    return (a + b) / 2 if (a or b) else 0.0


def _iso(mdy: str) -> str | None:
    try:
        return dt.datetime.strptime(mdy, "%m/%d/%Y").date().isoformat()
    except Exception:
        return None


def _avg(xs):
    xs = [x for x in xs if x is not None]
    return round(sum(xs) / len(xs), 1) if xs else None


# ---------------------------------------------------------------------------

def compute(days: int = 30, top: int = 40) -> dict:
    trades = cw_congress.get_congress_trades(days=days, chamber="all")
    stock = [t for t in trades if t["asset_code"] in STOCK]

    buys = cw_congress.leaderboard_from(trades, "purchase", top=top)
    sells = cw_congress.leaderboard_from(trades, "sale", top=top)

    last_date: dict[str, str] = {}
    for t in stock:
        d = _iso(t["txn_date"])
        if d and d > last_date.get(t["ticker"], ""):
            last_date[t["ticker"]] = d

    all_tickers = list(dict.fromkeys(t["ticker"] for t in stock))[:250]

    def warm(tk):
        info = dict(cw_meta.get_sector_industry(tk))
        info.update(cw_prices.get_price_info(tk, last_date.get(tk)))  # warms history cache
        return tk, info

    enriched: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        for tk, info in ex.map(warm, all_tickers):
            enriched[tk] = info

    for r in buys + sells:
        r.update(enriched.get(r["ticker"], {}))

    def tret(t):  # per-trade return since that trade's own date (the member's timing)
        d = _iso(t["txn_date"])
        return cw_prices.return_since(t["ticker"], d)["return_since_pct"] if d else None

    def cret(t):  # "copyable" return: since the FILING date, when the public could act
        return cw_prices.return_since(t["ticker"], t["filing_date"])["return_since_pct"]

    _party: dict[str, dict] = {}

    def party(name):
        if name not in _party:
            _party[name] = cw_members.lookup(name)
        return _party[name]

    # rich profiles (name / summary / market cap / indices) for the shown tickers
    shown = list(dict.fromkeys([r["ticker"] for r in buys] + [r["ticker"] for r in sells]))[:60]

    def prof(tk):
        return tk, cw_meta.get_ticker_profile(tk, price=enriched.get(tk, {}).get("price"))

    profiles: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        for tk, p in ex.map(prof, shown):
            profiles[tk] = p

    basic = {tk: {"company": cw_meta._ticker_title(tk), "sector": e.get("sector"),
                  "industry": e.get("industry")} for tk, e in enriched.items()}

    # overlap
    fund_holdings = cw_institutions.load_marquee_holdings()
    overlap = []
    for row in buys:
        hits = cw_institutions.funds_holding_ticker(row["ticker"], fund_holdings)
        if hits:
            e = enriched.get(row["ticker"], {})
            overlap.append({
                "ticker": row["ticker"], "company": cw_institutions.ticker_to_name(row["ticker"]),
                "sector": e.get("sector"), "price": e.get("price"),
                "return_since_pct": e.get("return_since_pct"),
                "congress_members": row["distinct_members"], "member_names": row["members"],
                "funds_holding": [h["fund"] for h in hits], "fund_count": len(hits)})
    overlap.sort(key=lambda r: (r["fund_count"], r["congress_members"]), reverse=True)

    # analytics
    n_buys = sum(t["action"] == "purchase" for t in stock)
    n_sells = sum(t["action"] == "sale" for t in stock)
    buy_vol = sum(_midpoint(t) for t in stock if t["action"] == "purchase")
    sell_vol = sum(_midpoint(t) for t in stock if t["action"] == "sale")

    mid = (dt.date.today() - dt.timedelta(days=days // 2)).isoformat()
    by_sector, members, weekly = {}, {}, {}
    sec_recent, sec_older = Counter(), Counter()
    for t in stock:
        sec = enriched.get(t["ticker"], {}).get("sector") or "Other"
        is_buy = t["action"] == "purchase"
        s = by_sector.setdefault(sec, {"sector": sec, "buys": 0, "sells": 0})
        s["buys" if is_buy else "sells"] += 1
        if is_buy:
            (sec_recent if t["filing_date"] >= mid else sec_older)[sec] += 1
        mk = (t["member"], t["chamber"])
        m = members.setdefault(mk, {"member": t["member"], "chamber": t["chamber"],
                                    "buys": 0, "sells": 0, "buy_vol": 0, "sell_vol": 0,
                                    "tickers": set(), "sectors": Counter(), "rets": [], "crets": []})
        m["tickers"].add(t["ticker"])
        m["sectors"][sec] += 1
        m["buy_vol" if is_buy else "sell_vol"] += _midpoint(t)
        m["buys" if is_buy else "sells"] += 1
        if is_buy:
            m["rets"].append(tret(t))
            m["crets"].append(cret(t))
        iso = _iso(t["txn_date"])
        if iso:
            wd = dt.date.fromisoformat(iso)
            wk = (wd - dt.timedelta(days=wd.weekday())).isoformat()
            w = weekly.setdefault(wk, {"week": wk, "buys": 0, "sells": 0})
            w["buys" if is_buy else "sells"] += 1

    member_rows = []
    for m in members.values():
        pinfo = party(m["member"])
        member_rows.append({
            "member": m["member"], "chamber": m["chamber"],
            "party": pinfo["party"], "state": pinfo.get("state"),
            "buys": m["buys"], "sells": m["sells"], "trades": m["buys"] + m["sells"],
            "buy_vol": round(m["buy_vol"]), "sell_vol": round(m["sell_vol"]),
            "tickers": len(m["tickers"]),
            "top_sector": (m["sectors"].most_common(1) or [("", 0)])[0][0],
            "est_return": _avg(m["rets"]), "return_samples": len([r for r in m["rets"] if r is not None]),
            "copy_return": _avg(m["crets"]), "copy_samples": len([r for r in m["crets"] if r is not None]),
        })

    # sector momentum (trends)
    momentum = []
    for sec in set(sec_recent) | set(sec_older):
        r, o = sec_recent[sec], sec_older[sec]
        momentum.append({"sector": sec, "recent": r, "older": o, "delta": r - o,
                         "pct": round((r - o) / o * 100) if o else (None if r == 0 else 100)})
    momentum.sort(key=lambda x: x["delta"], reverse=True)

    trades_out = []
    for t in sorted(stock, key=lambda t: t["filing_date"], reverse=True)[:600]:
        e = enriched.get(t["ticker"], {})
        trades_out.append({
            "chamber": t["chamber"], "member": t["member"], "party": party(t["member"])["party"],
            "ticker": t["ticker"], "action": t["action"], "txn_date": t["txn_date"],
            "filing_date": t["filing_date"], "sector": e.get("sector") or "Other",
            "amount_min": t["amount_min"], "amount_max": t["amount_max"],
            "ret": tret(t), "cret": cret(t)})

    # ---- Insights: who to copy + biggest copyable winners --------------------
    # "copyable" = return since the filing became public (what you could realistically
    # have made mirroring the trade AFTER disclosure, not at the member's own price).
    copy_leaders = sorted([m for m in member_rows if m["copy_samples"] >= 5
                           and m["copy_return"] is not None],
                          key=lambda m: m["copy_return"], reverse=True)[:8]
    top_trades = sorted([t for t in trades_out if t["action"] == "purchase"
                         and t["cret"] is not None],
                        key=lambda t: t["cret"], reverse=True)[:12]
    by_party: dict[str, dict] = {}
    for m in member_rows:
        p = m["party"] if m["party"] in ("D", "R", "I") else "Other"
        d = by_party.setdefault(p, {"party": p, "members": 0, "buys": 0, "sells": 0, "rets": []})
        d["members"] += 1
        d["buys"] += m["buys"]
        d["sells"] += m["sells"]
        if m["copy_return"] is not None and m["copy_samples"] >= 3:
            d["rets"].append(m["copy_return"])
    party_rows = [{"party": d["party"], "members": d["members"], "buys": d["buys"],
                   "sells": d["sells"], "avg_copy_return": _avg(d["rets"])}
                  for d in by_party.values() if d["party"] in ("D", "R", "I")]
    party_rows.sort(key=lambda d: d["members"], reverse=True)
    insights = {"copy_leaders": copy_leaders, "top_trades": top_trades, "by_party": party_rows}

    return {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "window_days": days,
        "summary": {"buys": n_buys, "sells": n_sells, "buy_vol": round(buy_vol),
                    "sell_vol": round(sell_vol), "net_by_count": n_buys - n_sells,
                    "net_by_dollar": round(buy_vol - sell_vol), "unique_tickers": len(all_tickers),
                    "members": len(member_rows)},
        "by_sector": sorted(by_sector.values(), key=lambda s: s["buys"] + s["sells"], reverse=True),
        "momentum": momentum, "weekly": sorted(weekly.values(), key=lambda w: w["week"])[-12:],
        "members": member_rows, "buys": buys, "sells": sells, "overlap": overlap,
        "trades": trades_out, "profiles": profiles, "basic": basic, "insights": insights,
        "sectors": sorted({s["sector"] for s in by_sector.values()}),
        "funds": [{"fund": n, "latest_13f": i["filing_date"], "positions": len(i["holdings"])}
                  for n, i in fund_holdings.items()],
        "counts": {"trades": len(stock), "buys": n_buys, "sells": n_sells, "funds": len(fund_holdings)},
    }


def _vtuple(v: str):
    return tuple(int(x) for x in re.findall(r"\d+", v)[:3])


def version_info() -> dict:
    """Current version + whether a newer GitHub release exists."""
    info = {"current": VERSION, "latest": VERSION, "update_available": False,
            "url": RELEASES_PAGE}
    try:
        rel = fetch_json(RELEASES_API, ttl=3600,
                         headers={"Accept": "application/vnd.github+json"})
        latest = (rel.get("tag_name") or "").lstrip("v")
        if latest:
            info["latest"] = latest
            info["update_available"] = _vtuple(latest) > _vtuple(VERSION)
            info["url"] = rel.get("html_url") or RELEASES_PAGE
    except Exception:
        pass
    return info


def ticker_detail(ticker: str, date: str | None) -> dict:
    price = cw_prices.get_price_info(ticker, date)
    profile = cw_meta.get_ticker_profile(ticker, price=price.get("price"))
    news = cw_news.get_news(ticker, company=profile.get("company"), around_iso=date)
    move = cw_prices.biggest_move(ticker, date)
    return {"ticker": ticker.upper(), "profile": profile, "price": price,
            "news": news, "biggest_move": move}


def member_detail(name: str, chamber: str, days: int) -> dict:
    trades = [t for t in cw_congress.get_congress_trades(days=days, chamber="all")
              if t["member"] == name and t["asset_code"] in STOCK]
    pos: dict[str, dict] = {}
    for t in trades:
        p = pos.setdefault(t["ticker"], {"ticker": t["ticker"], "buys": 0, "sells": 0,
                                         "buy_usd": 0, "sell_usd": 0, "last": t["txn_date"]})
        if t["action"] == "purchase":
            p["buys"] += 1
            p["buy_usd"] += _midpoint(t)
        elif t["action"] == "sale":
            p["sells"] += 1
            p["sell_usd"] += _midpoint(t)
        d = _iso(t["txn_date"])
        if d and (d > (_iso(p["last"]) or "")):
            p["last"] = t["txn_date"]
    rows = []
    for p in pos.values():
        r = cw_prices.return_since(p["ticker"], _iso(p["last"]))
        net = "Accumulating" if p["buys"] > p["sells"] else ("Reducing" if p["sells"] > p["buys"] else "Mixed")
        rows.append({**p, "company": cw_meta._ticker_title(p["ticker"]),
                     "sector": cw_meta.get_sector_industry(p["ticker"])["sector"],
                     "net": net, "net_usd": round(p["buy_usd"] - p["sell_usd"]),
                     "price": r["price"], "return_since_pct": r["return_since_pct"]})
    rows.sort(key=lambda r: abs(r["net_usd"]), reverse=True)
    buy_rets = [cw_prices.return_since(p["ticker"], _iso(p["last"]))["return_since_pct"]
                for p in pos.values() if p["buys"] > p["sells"]]
    pinfo = cw_members.lookup(name)
    return {"member": name, "chamber": chamber, "party": pinfo["party"], "state": pinfo.get("state"),
            "window_days": days, "positions": rows, "est_return": _avg(buy_rets),
            "totals": {"tickers": len(rows), "buys": sum(p["buys"] for p in pos.values()),
                       "sells": sum(p["sells"] for p in pos.values())}}


# --------------------------------------------------------------------------- cache/http

def _cache_file(days: int) -> str:
    return os.path.join(CACHE_DIR, f"dash_{days}.json")


def get_data(days: int, refresh: bool) -> dict:
    cf = _cache_file(days)
    if not refresh and os.path.exists(cf):
        try:
            with open(cf, encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            pass
    with _compute_lock:
        if not refresh and os.path.exists(cf):
            try:
                with open(cf, encoding="utf-8") as fh:
                    return json.load(fh)
            except Exception:
                pass
        payload = compute(days=days)
        os.makedirs(CACHE_DIR, exist_ok=True)
        tmp = cf + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh)
        os.replace(tmp, cf)
        return payload


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        try:
            if u.path in ("/", "/index.html"):
                body = PAGE.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif u.path == "/api/data":
                self._json(get_data(int(q.get("days", ["30"])[0]),
                                    q.get("refresh", ["0"])[0] == "1"))
            elif u.path == "/api/ticker":
                self._json(ticker_detail(q.get("ticker", [""])[0], q.get("date", [None])[0]))
            elif u.path == "/api/member":
                self._json(member_detail(q.get("name", [""])[0], q.get("chamber", [""])[0],
                                         int(q.get("days", ["30"])[0])))
            elif u.path == "/api/version":
                self._json(version_info())
            else:
                self.send_response(404)
                self.end_headers()
        except Exception as e:
            self._json({"error": str(e)}, 500)


def make_server(port: int | None = None) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((HOST, port or PORT), Handler)


def _load_page():
    import sys
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(base, "dashboard.html"), encoding="utf-8") as fh:
        return fh.read()


PAGE = _load_page()


if __name__ == "__main__":
    srv = make_server()
    print(f"congress-whales dashboard: http://{HOST}:{PORT}")
    srv.serve_forever()
