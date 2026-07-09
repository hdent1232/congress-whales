"""Member -> political party / state, free from the unitedstates congress-legislators dataset.

Used for the R-vs-D filter and to label members. Matching congressional trade names
(e.g. "Gilbert Cisneros", "David J. Taylor") to the legislator roster is done on a
normalized first+last key with a last-name fallback.
"""
from __future__ import annotations

import re

from cw_http import fetch_json

_CURRENT = "https://unitedstates.github.io/congress-legislators/legislators-current.json"
_HISTORICAL = "https://unitedstates.github.io/congress-legislators/legislators-historical.json"

_PARTY = {"Democrat": "D", "Republican": "R", "Independent": "I",
          "Independent Democrat": "I", "Libertarian": "L"}

_by_fullname: dict[str, dict] | None = None
_by_lastname: dict[str, list] | None = None


def _norm(s: str) -> str:
    s = re.sub(r"[^A-Za-z ]", " ", (s or "")).upper()
    # drop common suffixes / middle initials handled by token filtering
    return " ".join(s.split())


def _tokens(name: str) -> list[str]:
    drop = {"JR", "SR", "II", "III", "IV", "HON", "MR", "MRS", "MS", "DR"}
    return [t for t in _norm(name).split() if t not in drop and len(t) > 1]


def _load() -> None:
    global _by_fullname, _by_lastname
    full, last = {}, {}
    for url in (_CURRENT, _HISTORICAL):
        is_current = url == _CURRENT
        try:
            data = fetch_json(url, ttl=604800)
        except Exception:
            continue
        for p in data:
            terms = p.get("terms") or []
            if not terms:
                continue
            t = terms[-1]
            starts = [tm.get("start", "") for tm in terms if tm.get("start")]
            since = min(starts)[:4] if starts else None
            info = {"party": _PARTY.get(t.get("party"), t.get("party") or "?"),
                    "state": t.get("state"), "chamber": t.get("type"), "since": since}
            nm = p.get("name", {})
            first = nm.get("first") or ""
            lastn = nm.get("last") or ""
            keys = {f"{first} {lastn}"}
            if nm.get("official_full"):
                keys.add(nm["official_full"])
            if nm.get("nickname"):
                keys.add(f"{nm['nickname']} {lastn}")
            for k in keys:
                fk = " ".join(_tokens(k))
                if fk and fk not in full:  # current wins over historical (loaded first)
                    full[fk] = info
            lk = _norm(lastn)
            if lk and is_current:  # fallback only against current members (mostly unique)
                last.setdefault(lk, []).append(info)
    _by_fullname, _by_lastname = full, last


def lookup(name: str) -> dict:
    """Return {"party","state","chamber"} for a member name (best-effort)."""
    if _by_fullname is None:
        _load()
    toks = _tokens(name)
    if not toks:
        return {"party": "?", "state": None, "chamber": None, "since": None}
    # try first+last
    fk = f"{toks[0]} {toks[-1]}"
    if fk in _by_fullname:
        return _by_fullname[fk]
    # try full normalized
    full = " ".join(toks)
    if full in _by_fullname:
        return _by_fullname[full]
    # last-name fallback only if unambiguous
    cand = _by_lastname.get(toks[-1], [])
    if len(cand) == 1:
        return cand[0]
    return {"party": "?", "state": None, "chamber": None, "since": None}
