"""congress-whales — a free MCP server that gives Claude live "smart money" market data.

Reproduces the two queries from the reel, using free official sources instead of a
paid Unusual Whales subscription:

  1. congress_most_bought          -> "Pull every stock a member of Congress bought
                                        this week. Rank them by how many members."
  2. cross_check_congress_vs_funds -> "Cross-check those tickers with the latest 13F
                                        institutional filings. Show me where Congress
                                        and the big funds are buying the same names."

Run as an MCP server (stdio):   python server.py
Prove it works end-to-end:      python server.py --selftest
"""
from __future__ import annotations

import sys

from mcp.server.fastmcp import FastMCP

import cw_congress
import cw_institutions

mcp = FastMCP("congress-whales")


@mcp.tool()
def congress_most_bought(days: int = 7, chamber: str = "all", top: int = 25,
                         include_all_asset_types: bool = False) -> dict:
    """Rank the stocks most bought by members of Congress recently.

    Returns tickers ranked by the number of distinct members who reported a
    purchase in the last `days` (by filing date), with member names and the
    estimated aggregate dollar range. This is the "what is smart money in
    Congress buying" leaderboard.

    Args:
        days: look-back window over filing dates (7 = "this week").
        chamber: "all", "house", or "senate".
        top: max tickers to return.
        include_all_asset_types: include options/bonds/etc. (default False = common stock only).
    """
    rows = cw_congress.most_bought(days=days, chamber=chamber, top=top,
                                   include_all=include_all_asset_types)
    return {"as_of": cw_congress.today_iso(), "window_days": days,
            "chamber": chamber, "count": len(rows), "results": rows}


@mcp.tool()
def congress_recent_trades(days: int = 7, chamber: str = "all",
                           action: str = "all", ticker: str = "") -> dict:
    """List individual congressional stock trades (the raw disclosures).

    Args:
        days: look-back window over filing dates.
        chamber: "all", "house", or "senate".
        action: "all", "purchase", or "sale".
        ticker: optional ticker filter, e.g. "NVDA".
    """
    trades = cw_congress.get_congress_trades(days=days, chamber=chamber)
    if action != "all":
        trades = [t for t in trades if t["action"] == action]
    if ticker:
        trades = [t for t in trades if t["ticker"] == ticker.upper()]
    trades.sort(key=lambda t: t["filing_date"], reverse=True)
    return {"as_of": cw_congress.today_iso(), "window_days": days,
            "count": len(trades), "trades": trades}


@mcp.tool()
def institutional_holdings(ticker: str) -> dict:
    """Which marquee hedge funds hold a given ticker, per their latest 13F filing.

    Args:
        ticker: e.g. "AAPL".
    """
    hits = cw_institutions.funds_holding_ticker(ticker)
    return {"ticker": ticker.upper(),
            "company": cw_institutions.ticker_to_name(ticker),
            "held_by_count": len(hits), "held_by": hits}


@mcp.tool()
def cross_check_congress_vs_funds(days: int = 30, chamber: str = "all",
                                  top: int = 25) -> dict:
    """Find names that BOTH Congress and marquee hedge funds are in — the overlap.

    Takes the tickers most bought by Congress in the window and checks which of
    them also appear in the latest 13F holdings of marquee institutions. Ranked
    by number of funds holding, then by number of Congress members buying.

    Args:
        days: congressional look-back window (default 30 to catch a fuller picture).
        chamber: "all", "house", or "senate".
        top: how many top congressional tickers to check.
    """
    leaderboard = cw_congress.most_bought(days=days, chamber=chamber, top=top)
    fund_holdings = cw_institutions.load_marquee_holdings()
    overlap = []
    for row in leaderboard:
        hits = cw_institutions.funds_holding_ticker(row["ticker"], fund_holdings)
        if hits:
            overlap.append({
                "ticker": row["ticker"],
                "company": cw_institutions.ticker_to_name(row["ticker"]),
                "congress_members": row["distinct_members"],
                "member_names": row["members"],
                "funds_holding": [h["fund"] for h in hits],
                "fund_count": len(hits),
            })
    overlap.sort(key=lambda r: (r["fund_count"], r["congress_members"]), reverse=True)
    return {"as_of": cw_congress.today_iso(), "window_days": days,
            "funds_scanned": len(fund_holdings), "count": len(overlap),
            "results": overlap}


@mcp.tool()
def list_marquee_funds() -> dict:
    """List the marquee institutions whose 13F holdings power the cross-check."""
    holdings = cw_institutions.load_marquee_holdings()
    return {"count": len(holdings),
            "funds": [{"fund": name, "latest_13f": info["filing_date"],
                       "positions": len(info["holdings"])}
                      for name, info in holdings.items()]}


# ---------------------------------------------------------------------------
# Self-test: proves the whole pipeline against live data without an MCP client.
# ---------------------------------------------------------------------------

def _selftest() -> int:
    import json
    print("== congress-whales self-test (live data) ==\n")

    print("[1/4] congress_most_bought(days=30) ...")
    mb = congress_most_bought(days=30, top=10)
    print(f"      {mb['count']} tickers. top 5:")
    for r in mb["results"][:5]:
        print(f"        {r['ticker']:6s} members={r['distinct_members']} "
              f"buys={r['buy_transactions']} {r['members'][:3]}")

    print("\n[2/4] congress_recent_trades(days=30, action=purchase) ...")
    rt = congress_recent_trades(days=30, action="purchase")
    print(f"      {rt['count']} purchase disclosures")
    for t in rt["trades"][:3]:
        print(f"        {t['chamber']:6s} {t['member']:22s} {t['ticker']:6s} "
              f"{t['txn_date']} ${t['amount_min']}-{t['amount_max']}")

    print("\n[3/4] list_marquee_funds() (loads live 13F filings) ...")
    lf = list_marquee_funds()
    print(f"      {lf['count']} funds loaded")
    for f in lf["funds"][:5]:
        print(f"        {f['fund']:40s} 13F {f['latest_13f']} "
              f"({f['positions']} positions)")

    print("\n[4/4] cross_check_congress_vs_funds(days=45) ...")
    cc = cross_check_congress_vs_funds(days=45, top=25)
    print(f"      {cc['count']} overlapping names (Congress AND funds):")
    for r in cc["results"][:8]:
        print(f"        {r['ticker']:6s} {(r['company'] or '')[:26]:26s} "
              f"congress={r['congress_members']} funds={r['fund_count']}")

    ok = mb["count"] > 0 and lf["count"] > 0
    print("\nRESULT:", "PASS" if ok else "FAIL (no data returned)")
    return 0 if ok else 1


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    mcp.run()
