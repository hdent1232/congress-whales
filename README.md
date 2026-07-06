# congress-whales 🐋 — the "INSANE Claude Trading Hack," but actually free

This is a working rebuild of the setup in that Instagram reel: **connect Claude to
live "smart money" market data and ask it questions in plain English**, e.g.

> *"Pull every stock a member of Congress bought this week. Rank them by how many members bought each."*

> *"Cross-check those tickers with the latest 13F institutional filings. Show me where Congress and the big funds are buying the same names."*

The reel used the **Unusual Whales MCP server**. That server is free software, but it
wraps the Unusual Whales **API, which needs a paid subscription** (their historical/flow
tiers run into the hundreds of dollars a month). So the "FREE" in the reel is doing some
quiet work.

**This project needs no subscription and no API key at all.** It pulls the exact same
kind of data straight from the primary public sources the aggregators repackage:

| Data | Source | Cost |
|------|--------|------|
| House stock trades | `disclosures-clerk.house.gov` (official PTR filings) | Free |
| Senate stock trades | `efdsearch.senate.gov` (official electronic filings) | Free |
| Institutional 13F holdings | SEC EDGAR (`data.sec.gov`) | Free |
| Sector / industry | SEC EDGAR SIC + S&P 500 GICS | Free |
| Prices & returns | Yahoo Finance chart endpoint | Free |
| Market cap / size | SEC shares outstanding × price | Free |
| Company profile ("what it does") | Wikipedia REST summary | Free |
| Index membership (S&P 500 / Nasdaq-100) | S&P 500 constituents + static NDX snapshot | Free |
| Ticker news | Google News RSS | Free |

---

## Download

Grab the latest from **[Releases](https://github.com/hdent1232/congress-whales/releases/latest)**:

| Platform | File | Install |
|----------|------|---------|
| **Windows** | `Congress Whales (Windows).exe` (~41 MB) | Double-click. SmartScreen may warn (unsigned) → *More info → Run anyway*. |
| **Android** | `Congress Whales (Android).apk` (~36 MB) | Copy to your phone, tap it, allow "install from unknown sources". |

Both are self-contained — no Python, no setup. The app checks GitHub for newer versions on launch and shows an in-app **Update** button when one exists. (The Android app runs the same Python engine on-device via Chaquopy inside a WebView; the APK is built automatically by GitHub Actions on every release.)

## Optional: richer news (Finnhub)

By default the app uses free Google News. For deeper, strictly date-ranged company
news, get a free key at [finnhub.io/register](https://finnhub.io/register), copy
`config.example.json` to **`config.json`**, and paste the key. `config.json` is
git-ignored so it never ends up in the repo.

## Two ways to use it

**A) Desktop app** — a standalone dashboard, no Claude needed. Two ways to launch:
- **`Congress Whales.exe`** on your Desktop — a single shareable file (~41 MB, no Python
  needed). Just double-click, or send it to a friend. *(First launch is slow while it
  builds the first snapshot; Windows SmartScreen may warn because it's unsigned — click
  "More info → Run anyway". Needs an internet connection.)*
- The **Congress Whales** shortcut / `Congress Whales.bat` — runs from source (for when
  you've edited the code). Rebuild the exe with `build_exe.bat`.

A compact, tabbed window opens, refreshed to the newest filings each time. **Every table
sorts** — click any column header. Tabs:

- **Overview** — KPIs, an expandable **"how to read this"** explainer (auto-opens when
  *net bias* by transaction count disagrees with *net $ flow* by dollars), **Sector trends**
  with a measurable **% change** (newer half of the window vs older half — e.g. "Healthcare
  buying up +61%"), a weekly chart, a clear sector buys/sells breakdown, a **💡 biggest
  copyable winners** teaser, and a **Republicans vs Democrats** comparison.
- **Buys** / **Sells** — leaderboards; each row shows sector, price, and return since the
  trade. Filter by sector or search.
- **All trades** — every disclosure, filterable by **buy/sell, sector, chamber, and
  party**, showing return since the trade *and* since it became public.
- **Members** — every trading member with **party**, sortable by any column (buys, sells,
  est. return, copyable return, volume…), filter by **party**, and search a specific
  member. Click one for their disclosed portfolio.
- **Insights** — **🏆 who to copy** (members with the best return *since their trades went
  public*) and **💡 biggest copyable winners** (individual disclosed buys, e.g. a PANW buy
  up ~67% since it was disclosed).
- **Fund overlap** — tickers Congress bought that marquee hedge funds also hold (13F).

**Hover any ticker** for a profile card (company, what it does, sector/industry, market-cap
size, **S&P 500 = ES / Nasdaq-100 = NQ**). **Click a ticker** for a drawer with price,
return-since-trade, the **biggest price move near the trade date**, the business summary,
and **news aligned to the trade** (amber = before, teal = after).

Lookback windows run **7 days → 2 years**. Opens instantly on the last snapshot, then
updates in the background.

### Copyable return — the "what could a regular person do" number
Members can file a trade up to ~45 days after making it, so you can't buy at their price.
The app therefore also computes **return since the filing became public** ("copy return")
— what you could realistically have made mirroring the trade *after* seeing the disclosure.
That's what powers the Insights tab. **Ideas, not advice.**

### Honest caveats (you asked for these)
- **"Portfolio" = disclosed trading activity, not a verified holdings statement.** Filings
  give dollar *ranges*, not share counts or cost basis — so net values are estimates.
- **"Est. return"** is unrealized mark-to-market since each disclosed buy.
- **Realized profit and net worth are deliberately not shown** — they can't be derived
  reliably from transaction reports (no lots, only ranges).
- **Only Congress is included.** House + Senate are the *only* U.S. bodies with a clean,
  transaction-level public feed (the STOCK Act). Executive-branch officials and federal
  judges file **annual holdings** disclosures (broad ranges, no clean transaction feed), so
  they can't be added here without a big drop in data quality.
- **Party** is matched by name to the congress-legislators roster (~98% hit rate; a rare
  member may show "?"). **Index membership** is a static ~2026 snapshot.

If the shortcut ever goes missing, recreate it by right-clicking `create_shortcut.ps1`
→ *Run with PowerShell*. For troubleshooting, run `Congress Whales (debug).bat` (same
app, but with a console that shows errors).

**B) Inside Claude** — the same data as MCP tools you can ask about in plain English.

## What Claude can do once it's connected

Five tools show up in Claude:

- **`congress_most_bought`** — the leaderboard: stocks ranked by how many members of
  Congress bought them recently. *(Reel prompt #1.)*
- **`cross_check_congress_vs_funds`** — the overlap of what Congress is buying and what
  marquee hedge funds hold in their latest 13F. *(Reel prompt #2.)*
- **`congress_recent_trades`** — the raw individual disclosures (filter by chamber,
  buy/sell, ticker).
- **`institutional_holdings`** — which marquee funds hold a given ticker.
- **`list_marquee_funds`** — the institutions behind the cross-check (Berkshire, Citadel,
  Pershing Square, Renaissance, Point72, Tiger Global, Scion/Burry, and more).

Then you just talk to Claude:

> *"Use congress_most_bought for the last two weeks, then cross-check the top names against the funds and tell me which 3 have the strongest combined conviction."*

---

## Setup

### 1. Install dependencies
```bash
pip install -r requirements.txt
```
(Only two packages: `mcp` and `pypdf`.)

### 2. Prove it works (no Claude needed)
```bash
python server.py --selftest
```
You should see a live congressional buy leaderboard, real 13F filing dates, and a
Congress-vs-funds overlap table. If that prints `RESULT: PASS`, the data pipeline works.

### 3. Connect it to Claude

**Claude Code** — a ready-to-use `.mcp.json` is already in this folder. Open Claude Code
with this directory as the working folder and it loads automatically. To register it
globally instead:
```bash
claude mcp add congress-whales -- "C:\Users\flami\AppData\Local\Programs\Python\Python312\python.exe" "C:\Users\flami\Desktop\congress-whales-mcp\server.py"
```

**Claude Desktop** — copy the `congress-whales` block from
`claude_desktop_config.example.json` into your Claude Desktop config
(`%APPDATA%\Claude\claude_desktop_config.json`) and restart Claude Desktop.

---

## Want the exact reel parity (both chambers, options flow, dark pool)?

Add the **official Unusual Whales MCP** *alongside* this one — get a key at
`unusualwhales.com/settings/api-dashboard`, then follow their guide at
`unusualwhales.com/public-api/mcp`. This free server and the paid one can coexist; Claude
will use whichever tool fits the question.

---

## Honest limitations (so you trust the output)

- **Windows.** Only actual buys/sells reported; `congress_most_bought` defaults to
  common stock (`include_all_asset_types=True` adds options/bonds).
- **"This week" = filing date.** Members can legally file a Periodic Transaction Report up
  to ~45 days after the trade, so a fresh filing may describe an older trade. The trade's
  own date is included in every result.
- **13F is quarterly and lagged** (up to ~45 days). A holding in the latest 13F means
  "held as of quarter-end," not necessarily "bought this quarter." Treat the cross-check
  as *conviction overlap*, not a real-time signal.
- **Cross-check matches by company name** (13F reports CUSIP + issuer name, not tickers).
  The matcher is deliberately strict to avoid false positives, so it can occasionally miss
  an unusual name.
- **Senate** depends on `efdsearch.senate.gov` being reachable; if it rate-limits, the
  server degrades gracefully to House-only rather than failing.
- Paper (non-electronic) filings are skipped — they're scanned images without machine-
  readable trade data.

## Not financial advice
This is a data tool. Members of Congress and 13F filers disclose *after* the fact. Do your
own research.
