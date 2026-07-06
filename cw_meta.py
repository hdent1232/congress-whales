"""Ticker -> sector / industry, free from SEC EDGAR.

SEC assigns every filer a SIC code + description (the "industry"). We map that to a
coarse GICS-like sector for filtering. Keyword matching on the description is more
reliable than raw SIC ranges, with a range fallback.
"""
from __future__ import annotations

import csv
import io
import urllib.parse

from cw_http import fetch, fetch_json

# (sector, keywords) — first match wins. Order matters: more specific first.
_SECTOR_KEYWORDS = [
    ("Technology", ["semiconductor", "computer", "software", "prepackaged",
                    "electronic", "data processing", "internet",
                    "communications equipment", "instruments"]),
    ("Healthcare", ["pharmaceutical", "biological", "medicinal", "medical",
                    "health", "surgical", "dental", "hospital", "diagnostic",
                    "in vitro", "laborator"]),
    ("Financials", ["bank", "insurance", "security broker", "security dealer",
                    "investment", "finance service", "credit", "savings",
                    "asset management", "real estate investment"]),
    ("Energy", ["petroleum", "crude", "oil", "natural gas", "coal", "drilling",
                "energy", "pipeline"]),
    ("Consumer", ["retail", "grocery", "food", "beverage", "apparel",
                  "restaurant", "eating", "consumer", "footwear", "tobacco",
                  "household", "motor vehicle", "auto"]),
    ("Industrials", ["aircraft", "aerospace", "machinery", "industrial",
                     "construction", "transportation", "railroad", "airline",
                     "air transport", "engine", "defense", "ordnance"]),
    ("Materials", ["chemical", "metal", "mining", "steel", "paper", "mineral",
                   "gold", "copper", "cement", "plastics"]),
    ("Utilities", ["electric services", "utilit", "water supply",
                   "gas distribution", "sanitary"]),
    ("Communications", ["telephone", "telecommunication", "broadcast", "media",
                        "advertising", "motion picture", "publishing", "cable"]),
]


def _sector_from_sic(sic: str, desc: str) -> str:
    d = (desc or "").lower()
    for sector, kws in _SECTOR_KEYWORDS:
        if any(k in d for k in kws):
            return sector
    try:
        n = int(sic)
    except (TypeError, ValueError):
        return "Other"
    if 6000 <= n <= 6799:
        return "Financials"
    if 2833 <= n <= 2836 or 8000 <= n <= 8099:
        return "Healthcare"
    if 3570 <= n <= 3579 or 3670 <= n <= 3679 or n == 7372:
        return "Technology"
    if 4900 <= n <= 4999:
        return "Utilities"
    if 5200 <= n <= 5999 or 2000 <= n <= 2199:
        return "Consumer"
    if 1000 <= n <= 1499 or 2800 <= n <= 2899:
        return "Materials"
    if 1300 <= n <= 1399:
        return "Energy"
    if 3400 <= n <= 3999 or 1500 <= n <= 1799:
        return "Industrials"
    if 4800 <= n <= 4899 or 2700 <= n <= 2799:
        return "Communications"
    return "Other"


_ticker_cik: dict[str, str] | None = None
_ticker_name: dict[str, str] | None = None
_meta_cache: dict[str, dict] = {}


def _load_company_tickers() -> None:
    global _ticker_cik, _ticker_name
    data = fetch_json("https://www.sec.gov/files/company_tickers.json",
                      ttl=604800, rate_key="sec")
    _ticker_cik = {r["ticker"].upper(): str(r["cik_str"]).zfill(10)
                   for r in data.values()}
    _ticker_name = {r["ticker"].upper(): r["title"].title() for r in data.values()}


def _ticker_to_cik(ticker: str) -> str | None:
    if _ticker_cik is None:
        _load_company_tickers()
    return _ticker_cik.get(ticker.upper())


def _ticker_title(ticker: str) -> str | None:
    if _ticker_name is None:
        _load_company_tickers()
    return _ticker_name.get(ticker.upper())


def get_sector_industry(ticker: str) -> dict:
    """Return {"sector":..., "industry":..., "sic":...} for a ticker."""
    tk = ticker.upper()
    if tk in _meta_cache:
        return _meta_cache[tk]
    result = {"sector": "Other", "industry": None, "sic": None}
    cik = _ticker_to_cik(tk)
    if cik:
        try:
            sub = fetch_json(f"https://data.sec.gov/submissions/CIK{cik}.json",
                             ttl=604800, rate_key="sec")
            sic = sub.get("sic")
            desc = sub.get("sicDescription")
            result = {"sector": _sector_from_sic(sic, desc), "industry": desc,
                      "sic": sic}
        except Exception:
            pass
    _meta_cache[tk] = result
    return result


# ---------------------------------------------------------------------------
# Index membership (S&P 500 "ES", Nasdaq-100 "NQ") + company profile
# ---------------------------------------------------------------------------

_sp500: dict[str, dict] | None = None
_nasdaq100: set[str] | None = None
_shares_cache: dict[str, int | None] = {}
_wiki_cache: dict[str, str | None] = {}


def _norm_sym(t: str) -> str:
    return t.upper().replace(".", "-")


def sp500_map() -> dict[str, dict]:
    """ticker -> {name, gics_sector, gics_sub, founded}. Empty on failure."""
    global _sp500
    if _sp500 is None:
        built = {}  # build fully before publishing, so concurrent readers never see a partial map
        try:
            raw = fetch("https://raw.githubusercontent.com/datasets/"
                        "s-and-p-500-companies/main/data/constituents.csv",
                        ttl=604800).decode("utf-8", "replace")
            for row in csv.DictReader(io.StringIO(raw)):
                built[_norm_sym(row["Symbol"])] = {
                    "name": row.get("Security"), "gics_sector": row.get("GICS Sector"),
                    "gics_sub": row.get("GICS Sub-Industry"), "founded": row.get("Founded"),
                }
        except Exception:
            pass
        _sp500 = built
    return _sp500


# Static Nasdaq-100 snapshot (~2026). Membership changes only at the annual
# reconstitution plus occasional replacements, so a snapshot is far more reliable
# than scraping a page that changes layout. Labelled as a snapshot in the UI.
_NASDAQ100 = {
    "ADBE", "AMD", "ABNB", "GOOGL", "GOOG", "AMZN", "AEP", "AMGN", "ADI", "ANSS",
    "AAPL", "AMAT", "APP", "ARM", "ASML", "AZN", "TEAM", "ADSK", "ADP", "AXON",
    "BKR", "BIIB", "BKNG", "AVGO", "CDNS", "CDW", "CHTR", "CTAS", "CSCO", "CCEP",
    "CTSH", "CMCSA", "CEG", "CPRT", "CSGP", "COST", "CRWD", "CSX", "DDOG", "DXCM",
    "FANG", "DASH", "EA", "EXC", "FAST", "FTNT", "GEHC", "GILD", "GFS", "HON",
    "IDXX", "INTC", "INTU", "ISRG", "KDP", "KLAC", "KHC", "LRCX", "LIN", "LULU",
    "MAR", "MRVL", "MELI", "META", "MCHP", "MU", "MSFT", "MSTR", "MDLZ", "MNST",
    "NFLX", "NVDA", "NXPI", "ORLY", "ODFL", "ON", "PCAR", "PLTR", "PANW", "PAYX",
    "PYPL", "PDD", "PEP", "QCOM", "REGN", "ROP", "ROST", "SBUX", "SNPS", "TTWO",
    "TMUS", "TSLA", "TXN", "TTD", "VRSK", "VRTX", "WBD", "WDAY", "XEL", "ZS",
}


def nasdaq100_set() -> set[str]:
    """Nasdaq-100 membership (static ~2026 snapshot)."""
    return _NASDAQ100


def shares_outstanding(ticker: str) -> int | None:
    tk = ticker.upper()
    if tk in _shares_cache:
        return _shares_cache[tk]
    val = None
    cik = _ticker_to_cik(tk)
    if cik:
        try:
            j = fetch_json(f"https://data.sec.gov/api/xbrl/companyconcept/CIK{cik}"
                           "/dei/EntityCommonStockSharesOutstanding.json",
                           ttl=604800, rate_key="sec")
            units = j.get("units", {}).get("shares", [])
            if units:
                val = units[-1].get("val")
        except Exception:
            pass
    _shares_cache[tk] = val
    return val


def wiki_summary(name: str | None) -> str | None:
    if not name:
        return None
    if name in _wiki_cache:
        return _wiki_cache[name]
    out = None
    try:
        j = fetch_json("https://en.wikipedia.org/api/rest_v1/page/summary/"
                       + urllib.parse.quote(name), ttl=2592000)
        if j.get("type") != "disambiguation":
            out = j.get("extract")
    except Exception:
        pass
    _wiki_cache[name] = out
    return out


def _size_tier(mcap: float | None) -> str | None:
    if not mcap:
        return None
    b = mcap / 1e9
    if b >= 200:
        return "Mega-cap"
    if b >= 10:
        return "Large-cap"
    if b >= 2:
        return "Mid-cap"
    return "Small-cap"


def get_ticker_profile(ticker: str, price: float | None = None,
                       with_summary: bool = True) -> dict:
    """Rich profile for the hover card / drawer: name, what-it-does, sector, size, indices."""
    tk = ticker.upper()
    sym = _norm_sym(tk)
    base = get_sector_industry(tk)
    sp = sp500_map().get(sym)
    name = (sp or {}).get("name") or _ticker_title(tk)
    indices = []
    if sp:
        indices.append("S&P 500 (ES)")
    if sym in nasdaq100_set():
        indices.append("Nasdaq-100 (NQ)")
    sh = shares_outstanding(tk)
    mcap = sh * price if (sh and price) else None
    return {
        "ticker": tk, "company": name, "sector": base["sector"],
        "industry": (sp or {}).get("gics_sub") or base["industry"],
        "gics_sector": (sp or {}).get("gics_sector"),
        "founded": (sp or {}).get("founded"),
        "market_cap": round(mcap) if mcap else None,
        "size_tier": _size_tier(mcap), "indices": indices,
        "summary": wiki_summary(name) if with_summary else None,
    }
