"""Congressional stock trades from the primary, free, official sources.

House  : disclosures-clerk.house.gov publishes an annual ZIP index of every filing
         (FinancialDisclosure XML). Periodic Transaction Reports (FilingType "P")
         each have a machine-readable, e-filed PDF containing the actual trades.

Senate : efdsearch.senate.gov exposes a JSON search endpoint (after accepting the
         standard access agreement) and renders each electronic PTR as an HTML
         table of transactions.

No API key, no subscription. This is exactly the data commercial aggregators repackage.
"""
from __future__ import annotations

import datetime as dt
import http.cookiejar
import io
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from concurrent.futures import ThreadPoolExecutor

from pypdf import PdfReader

from cw_http import UA, fetch

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

# Asset-type codes we treat as "stocks" for the reel's "every stock" question.
# ST = common stock. (Options=OP, corporate bonds=CS, treasuries=GS, etc. are
# excluded by default; pass include_all=True to keep everything.)
STOCK_CODES = {"ST"}

_AMOUNT_RE = re.compile(r"\$([\d,]+)\s*-\s*\$([\d,]+)")


def today_iso() -> str:
    return dt.date.today().isoformat()


def _parse_amount(text: str):
    m = _AMOUNT_RE.search(text)
    if not m:
        return None, None
    return int(m.group(1).replace(",", "")), int(m.group(2).replace(",", ""))


def _action(type_token: str) -> str:
    t = type_token.strip().upper()
    if t.startswith("P"):
        return "purchase"
    if t.startswith("E"):
        return "exchange"
    return "sale"


# ---------------------------------------------------------------------------
# House
# ---------------------------------------------------------------------------

_HOUSE_ZIP = "https://disclosures-clerk.house.gov/public_disc/financial-pdfs/{y}FD.ZIP"
_HOUSE_PDF = "https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/{y}/{doc}.pdf"

# Ticker in parentheses, immediately followed by a bracketed asset-type code, then
# the transaction type (P / S / S (partial) / E) and the transaction date.
_HOUSE_TRADE_RE = re.compile(
    r"\(([A-Z][A-Z0-9.\-]{0,5})\)\s*"        # 1: ticker
    r"\[([A-Z]{2})\]\s*"                       # 2: asset-type code
    r"(P|S \(partial\)|S|E)\s*"                # 3: transaction type
    r"(\d{2}/\d{2}/\d{4})",                    # 4: transaction date
    re.S,
)


def _house_filings(year: int) -> list[dict]:
    raw = fetch(_HOUSE_ZIP.format(y=year), ttl=1800, binary=True)
    z = zipfile.ZipFile(io.BytesIO(raw))
    root = ET.fromstring(z.read(f"{year}FD.xml").decode("utf-8-sig"))
    out = []
    for m in root.findall("Member"):
        if (m.findtext("FilingType") or "") != "P":
            continue
        try:
            fd = dt.datetime.strptime(m.findtext("FilingDate") or "", "%m/%d/%Y").date()
        except ValueError:
            continue
        name = " ".join(p for p in (m.findtext("First"), m.findtext("Last"),
                                    m.findtext("Suffix")) if p)
        out.append({
            "chamber": "House",
            "member": name,
            "state": m.findtext("StateDst") or "",
            "filing_date": fd,
            "doc_id": m.findtext("DocID") or "",
            "year": year,
        })
    return out


def _parse_house_pdf(raw: bytes) -> list[dict]:
    reader = PdfReader(io.BytesIO(raw))
    text = "\n".join((p.extract_text() or "") for p in reader.pages)
    trades = []
    for m in _HOUSE_TRADE_RE.finditer(text):
        ticker, code, typ, tdate = m.groups()
        amin, amax = _parse_amount(text[m.end():m.end() + 90])
        trades.append({
            "ticker": ticker.upper(),
            "asset_code": code.upper(),
            "action": _action(typ),
            "txn_date": tdate,
            "amount_min": amin,
            "amount_max": amax,
        })
    return trades


def get_house_trades(days: int = 7, max_filings: int = 1500) -> list[dict]:
    cutoff = dt.date.today() - dt.timedelta(days=days)
    filings = []
    for year in range(cutoff.year, dt.date.today().year + 1):
        try:
            filings += _house_filings(year)
        except Exception:
            continue
    filings = [f for f in filings if f["filing_date"] >= cutoff]
    filings.sort(key=lambda f: f["filing_date"], reverse=True)
    filings = filings[:max_filings]

    def fetch_one(f):
        try:
            raw = fetch(_HOUSE_PDF.format(y=f["year"], doc=f["doc_id"]),
                        ttl=86400, binary=True)
        except Exception:
            return []  # paper filing / missing PDF
        return [{**t, "chamber": "House", "member": f["member"], "state": f["state"],
                 "filing_date": f["filing_date"].isoformat(), "doc_id": f["doc_id"]}
                for t in _parse_house_pdf(raw)]

    trades = []
    with ThreadPoolExecutor(max_workers=10) as ex:
        for res in ex.map(fetch_one, filings):
            trades.extend(res)
    return trades


# ---------------------------------------------------------------------------
# Senate
# ---------------------------------------------------------------------------

_SEN_BASE = "https://efdsearch.senate.gov"


def _senate_session():
    cj = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    op.addheaders = [("User-Agent", UA)]
    home = op.open(_SEN_BASE + "/search/", timeout=30).read().decode("utf-8", "replace")
    csrf = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', home).group(1)
    data = urllib.parse.urlencode({"prohibition_agreement": "1",
                                   "csrfmiddlewaretoken": csrf}).encode()
    op.open(urllib.request.Request(_SEN_BASE + "/search/home/", data=data,
            headers={"Referer": _SEN_BASE + "/search/"}), timeout=30).read()
    token = next(c.value for c in cj if c.name == "csrftoken")
    cookie = "; ".join(f"{c.name}={c.value}" for c in cj)
    return op, token, cookie


def _senate_filings(op, token, days: int) -> list[dict]:
    start = (dt.date.today() - dt.timedelta(days=days)).strftime("%m/%d/%Y 00:00:00")
    payload = urllib.parse.urlencode({
        "start": "0", "length": "400", "report_types": "[11]", "filer_types": "[]",
        "submitted_start_date": start, "submitted_end_date": "",
        "candidate_state": "", "senator_state": "", "office_id": "",
        "first_name": "", "last_name": "", "csrfmiddlewaretoken": token,
    }).encode()
    req = urllib.request.Request(_SEN_BASE + "/search/report/data/", data=payload,
        headers={"Referer": _SEN_BASE + "/search/", "X-Requested-With": "XMLHttpRequest"})
    import json as _json
    rows = _json.loads(op.open(req, timeout=30).read().decode()).get("data", [])
    out = []
    for row in rows:
        link = re.search(r'href="(/search/view/ptr/([0-9a-f\-]+)/)"', row[3])
        if not link:
            continue  # paper filing (scanned PDF) - skipped in the free path
        try:
            fd = dt.datetime.strptime(row[4], "%m/%d/%Y").date()
        except ValueError:
            continue
        out.append({"member": f"{row[0]} {row[1]}".strip(),
                    "url": _SEN_BASE + link.group(1),
                    "doc_id": link.group(2), "filing_date": fd})
    return out


def _senate_trades_from(url: str, cookie: str) -> list[dict]:
    html = fetch(url, ttl=86400, headers={"Cookie": cookie,
                 "Referer": _SEN_BASE + "/search/"}).decode("utf-8", "replace")
    body = html.split("<tbody>")[-1]
    trades = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", body, re.S):
        cells = [re.sub(r"<[^>]+>", "", c).strip()
                 for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
        # columns: #, txn date, owner, ticker, asset name, asset type, type, amount, comment
        if len(cells) < 8:
            continue
        ticker = cells[3]
        if ticker in ("--", "", "&nbsp;"):
            continue
        amin, amax = _parse_amount(cells[7])
        trades.append({
            "ticker": ticker.upper(),
            "asset_code": "ST" if "stock" in cells[5].lower() else cells[5][:2].upper(),
            "action": _action(cells[6]),
            "txn_date": cells[1],
            "amount_min": amin,
            "amount_max": amax,
        })
    return trades


def get_senate_trades(days: int = 7, max_filings: int = 1500) -> list[dict]:
    try:
        op, token, cookie = _senate_session()
        filings = _senate_filings(op, token, days)
    except Exception:
        return []  # Senate site occasionally rate-limits; degrade to House-only.
    filings.sort(key=lambda f: f["filing_date"], reverse=True)
    filings = filings[:max_filings]

    def fetch_one(f):
        try:
            ts = _senate_trades_from(f["url"], cookie)
        except Exception:
            return []
        return [{**t, "chamber": "Senate", "member": f["member"], "state": "",
                 "filing_date": f["filing_date"].isoformat(), "doc_id": f["doc_id"]}
                for t in ts]

    trades = []
    with ThreadPoolExecutor(max_workers=6) as ex:
        for res in ex.map(fetch_one, filings):
            trades.extend(res)
    return trades


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def get_congress_trades(days: int = 7, chamber: str = "all") -> list[dict]:
    chamber = (chamber or "all").lower()
    trades = []
    if chamber in ("all", "house"):
        trades += get_house_trades(days)
    if chamber in ("all", "senate"):
        trades += get_senate_trades(days)
    return trades


def leaderboard_from(trades: list[dict], action: str = "purchase", top: int = 25,
                     include_all: bool = False) -> list[dict]:
    """Rank tickers by distinct members trading them, for a given action.

    Lets callers (e.g. the desktop dashboard) fetch disclosures once and derive
    the buy leaderboard, the sell leaderboard, and the raw-trade view without
    hitting the network more than once.
    """
    codes = None if include_all else STOCK_CODES
    buckets: dict[str, dict] = {}
    for t in trades:
        if t["action"] != action:
            continue
        if codes is not None and t["asset_code"] not in codes:
            continue
        b = buckets.setdefault(t["ticker"], {"members": set(), "n": 0,
                                             "min": 0, "max": 0})
        b["members"].add((t["chamber"], t["member"]))
        b["n"] += 1
        b["min"] += t["amount_min"] or 0
        b["max"] += t["amount_max"] or 0
    rows = [{
        "ticker": tk,
        "distinct_members": len(b["members"]),
        "transactions": b["n"],
        "members": sorted(m[1] for m in b["members"]),
        "est_amount_usd": [b["min"], b["max"]],
    } for tk, b in buckets.items()]
    rows.sort(key=lambda r: (r["distinct_members"], r["transactions"]), reverse=True)
    return rows[:top]


def most_bought_from(trades: list[dict], top: int = 25,
                     include_all: bool = False) -> list[dict]:
    """Buy leaderboard (kept for the MCP server); adds legacy `buy_transactions`."""
    rows = leaderboard_from(trades, "purchase", top=top, include_all=include_all)
    for r in rows:
        r["buy_transactions"] = r["transactions"]
    return rows


def most_bought(days: int = 7, chamber: str = "all", top: int = 25,
                include_all: bool = False) -> list[dict]:
    codes = None if include_all else STOCK_CODES
    buckets: dict[str, dict] = {}
    for t in get_congress_trades(days, chamber):
        if t["action"] != "purchase":
            continue
        if codes is not None and t["asset_code"] not in codes:
            continue
        b = buckets.setdefault(t["ticker"], {"members": set(), "buys": 0,
                                             "min": 0, "max": 0})
        b["members"].add((t["chamber"], t["member"]))
        b["buys"] += 1
        b["min"] += t["amount_min"] or 0
        b["max"] += t["amount_max"] or 0
    rows = [{
        "ticker": tk,
        "distinct_members": len(b["members"]),
        "buy_transactions": b["buys"],
        "members": sorted(m[1] for m in b["members"]),
        "est_amount_usd": [b["min"], b["max"]],
    } for tk, b in buckets.items()]
    rows.sort(key=lambda r: (r["distinct_members"], r["buy_transactions"]), reverse=True)
    return rows[:top]
