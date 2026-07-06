"""Marquee hedge-fund / institutional holdings from SEC EDGAR 13F filings (free).

13F-HR reports are filed quarterly by institutions managing > $100M. They list
holdings by CUSIP + issuer name (not ticker), so to cross-check against a
congressional ticker we resolve the ticker to its official company name via SEC's
free company_tickers.json and match on the normalized issuer name.

Caveat worth stating plainly: 13F is quarterly and lagged up to ~45 days, and a
holding appearing in the latest 13F means "held as of quarter-end", not
necessarily "bought this quarter". That is an honest limitation of free 13F data.
"""
from __future__ import annotations

import re

from cw_http import fetch, fetch_json

# name -> CIK (verified against EDGAR). Loader validates each has a real 13F-HR and
# silently drops any that don't, so a stale CIK degrades gracefully.
MARQUEE_FUNDS = {
    "Berkshire Hathaway (Buffett)": "0001067983",
    "Scion Asset Management (Burry)": "0001649339",
    "Pershing Square (Ackman)": "0001336528",
    "Citadel Advisors": "0001423053",
    "Renaissance Technologies": "0001037389",
    "Bridgewater Associates": "0001350694",
    "Point72 (Cohen)": "0001603466",
    "Tiger Global Management": "0001167483",
    "Coatue Management": "0001135730",
    "Appaloosa (Tepper)": "0001656456",
    "Duquesne Family Office (Druckenmiller)": "0001536411",
    "Baupost Group (Klarman)": "0001054420",
    "Third Point (Loeb)": "0001040273",
    "Greenlight Capital (Einhorn)": "0001079114",
    "Lone Pine Capital": "0001061165",
}

_STOP = {"INC", "CORP", "CORPORATION", "CO", "COMPANY", "LTD", "LLC", "PLC", "LP",
         "THE", "CLASS", "COM", "COMMON", "STOCK", "HOLDINGS", "HOLDING", "GROUP",
         "SA", "NV", "AG", "TRUST", "FUND", "NEW", "CL", "A", "B", "C"}


def _norm(name: str) -> str:
    name = re.sub(r"[^A-Z0-9 ]", " ", name.upper())
    toks = [w for w in name.split() if w and w not in _STOP]
    return " ".join(toks)


# ---------------------------------------------------------------------------
# Ticker -> company name (SEC free dataset)
# ---------------------------------------------------------------------------

_ticker_names: dict[str, str] | None = None


def ticker_to_name(ticker: str) -> str | None:
    global _ticker_names
    if _ticker_names is None:
        data = fetch_json("https://www.sec.gov/files/company_tickers.json",
                          ttl=604800, rate_key="sec")
        _ticker_names = {row["ticker"].upper(): row["title"].upper()
                         for row in data.values()}
    return _ticker_names.get(ticker.upper())


# ---------------------------------------------------------------------------
# 13F holdings
# ---------------------------------------------------------------------------

_INFO_BLOCK_RE = re.compile(r"<(?:\w+:)?infoTable\b(.*?)</(?:\w+:)?infoTable>", re.S)
_ISSUER_RE = re.compile(r"<(?:\w+:)?nameOfIssuer>(.*?)</", re.S)
_VALUE_RE = re.compile(r"<(?:\w+:)?value>(.*?)</", re.S)


def _parse_infotable(raw: bytes) -> dict[str, int]:
    text = raw.decode("utf-8", "replace")
    holdings: dict[str, int] = {}
    for blk in _INFO_BLOCK_RE.findall(text):
        im = _ISSUER_RE.search(blk)
        if not im:
            continue
        issuer = _norm(im.group(1))
        if not issuer:
            continue
        vm = _VALUE_RE.search(blk)
        val = int(re.sub(r"[^\d]", "", vm.group(1))) if vm else 0
        holdings[issuer] = holdings.get(issuer, 0) + val
    return holdings


def _latest_13f_holdings(cik: str):
    """Return (filing_date, {normalized_issuer: value}) for the newest 13F-HR, or None."""
    cik_num = str(int(cik))
    sub = fetch_json(f"https://data.sec.gov/submissions/CIK{cik.zfill(10)}.json",
                     ttl=43200, rate_key="sec")
    rec = sub["filings"]["recent"]
    idx = next((i for i, f in enumerate(rec["form"]) if f == "13F-HR"), None)
    if idx is None:
        return None
    acc = rec["accessionNumber"][idx].replace("-", "")
    fdate = rec["filingDate"][idx]
    base = f"https://www.sec.gov/Archives/edgar/data/{cik_num}/{acc}"
    index = fetch_json(base + "/index.json", ttl=43200, rate_key="sec")
    xml_name = None
    for item in index["directory"]["item"]:
        n = item["name"].lower()
        if n.endswith(".xml") and "primary_doc" not in n:
            xml_name = item["name"]
            if "table" in n or "13f" in n:  # prefer the information table
                break
    if not xml_name:
        return None
    raw = fetch(base + "/" + xml_name, ttl=43200, binary=True, rate_key="sec")
    return fdate, _parse_infotable(raw)


_fund_cache: dict[str, tuple] | None = None


def load_marquee_holdings(funds: dict | None = None) -> dict[str, dict]:
    """Return {fund_name: {"filing_date":.., "holdings": {issuer:value}}} for valid funds."""
    global _fund_cache
    if _fund_cache is not None and funds is None:
        return _fund_cache
    src = funds or MARQUEE_FUNDS
    out = {}
    for name, cik in src.items():
        try:
            res = _latest_13f_holdings(cik)
        except Exception:
            res = None
        if not res or not res[1]:
            continue
        out[name] = {"filing_date": res[0], "holdings": res[1]}
    if funds is None:
        _fund_cache = out
    return out


def _name_matches(issuer: str, target: str) -> bool:
    """Strict-ish match between a normalized 13F issuer name and a company name.

    Requires an exact match or a full-token prefix relationship (to tolerate
    share-class / suffix differences like "META PLATFORMS" vs "META PLATFORMS A").
    Deliberately avoids loose single-token containment, which produced false
    positives (e.g. SPCX -> anything containing "SPACE").
    """
    if not issuer or not target:
        return False
    return (issuer == target
            or issuer.startswith(target + " ")
            or target.startswith(issuer + " "))


def funds_holding_ticker(ticker: str, funds_holdings: dict | None = None) -> list[dict]:
    """Which marquee funds hold `ticker` (matched by normalized company name)."""
    funds_holdings = funds_holdings or load_marquee_holdings()
    title = ticker_to_name(ticker)
    if not title:
        return []
    target = _norm(title)
    if not target:
        return []
    hits = []
    for fund, info in funds_holdings.items():
        for issuer, value in info["holdings"].items():
            if _name_matches(issuer, target):
                hits.append({"fund": fund, "as_of": info["filing_date"],
                             "value_reported": value})
                break
    hits.sort(key=lambda h: h["value_reported"], reverse=True)
    return hits
