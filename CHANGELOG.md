# Changelog

## 1.0.8
- **Buys & Sells now match All trades** — full per-transaction detail (dates, amounts, party, member, returns), all sortable.
- **Insights, rebuilt** — a "Would copying Congress beat the market?" panel with an **equity-curve chart** ($1k into every disclosed buy vs the same cash in the S&P 500), an **alpha** verdict, a hypothetical projection, **sector performance** (how Congress's buys did by sector), a **who-to-copy** board ranked by Copy Score, biggest copyable winners, and the most-bought tickers.
- **Members** tab gains a sortable **Copy Score**, win-rate, and reporting-lag column.
- **Hover a member's name** for a quick card (party, score, buys/sells, return, win rate, lag) — like the ticker card. Fixed: the stock card no longer appears over member names.

## 1.0.7
- **Rich member profiles:** click any member (in Members or All-trades) for a full profile — bio (party, state, years in Congress), a **Copy Score /100** with a transparent factor breakdown (performance, consistency, reporting speed, track-record size), avg return since their trades go public, win rate, average reporting lag, net flow, buying-by-sector, and each position's entry → current price.
- **Fixed:** hovering a member's name no longer shows the stock tooltip; the ticker card now only appears over an actual ticker. Member names are clickable.

## 1.0.6
- **Android fix:** the app no longer hangs on "loading." It now ships with a starter snapshot so it opens instantly with real data, then refreshes live.
- **Resilience:** a single blocked/slow data source (e.g. an SEC 403) can no longer blank the whole dashboard — it degrades gracefully and keeps showing data.
- Proper email-format User-Agent so SEC doesn't reject requests; friendlier "showing saved data" status when offline.

## 1.0.5
- **In-app settings (⚙):** add or remove your optional Finnhub API key right in the app — no file editing. The key is stored only on your device and never displayed back.

## 1.0.4
- **Members & party:** political party (R/D/I) on every member and trade, party filter, and a Republicans-vs-Democrats comparison.
- **Insights tab:** "who to copy" (members ranked by return *since their trades became public*) and the biggest copyable single trades.
- **"Copyable return":** returns measured from the public filing date, not the member's own entry — a realistic view of what you could have mirrored.
- **Sortable everywhere:** click any column header to sort.
- **Clearer analytics:** sector trends show % change; a collapsible explainer for why "net bias" (by trade count) can disagree with "net $ flow" (by dollars); the sector panel now uses clear Buys/Sells columns.
- **Ticker drawer:** biggest price move near the trade date.
- **Auto-update check** against GitHub Releases, version shown in the header.
- **New-trade notifications:** a desktop alert when a member files a new disclosure.
- **Optional Finnhub news** (date-ranged company news) when an API key is configured; otherwise free Google News.

## 1.0.3
- Members tab with per-member disclosed portfolios; hover profile cards (market cap, index membership, "what it does"); lookback up to 2 years; shareable Windows `.exe`.

## 1.0.2
- Buy **and** sell views; price + return-since-trade columns; sector/industry filters; Overview analytics; per-ticker news drawer.

## 1.0.1
- Initial dashboard: most-bought leaderboard, Congress-vs-hedge-fund 13F overlap, recent trades.
