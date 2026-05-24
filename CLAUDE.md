# Trading Analytics Terminal — Project Context

## Arbeitsregeln (IMMER einhalten — gilt für alle Sessions)

### Stopp-Bedingungen (sofort anhalten, nicht weiterarbeiten)
- Gleicher Fehler tritt zum 2. Mal auf → stoppen, melden, auf Anweisung warten
- Unklare Anforderung → nachfragen, nicht raten und weitermachen
- Tool-Call schlägt fehl → nicht automatisch wiederholen, erst erklären

### Iterationslimit
- Max. 3 Versuche pro Teilaufgabe
- Danach: Status + Problem beschreiben, auf Input warten

### Keine Eigeninitiative bei
- Datei-Löschungen oder -Überschreibungen
- Installationen von Paketen ohne explizite Freigabe
- Refactoring außerhalb des genannten Scope

### Kommunikation
- Vor jedem größeren Schritt: kurz ankündigen was gemacht wird
- Nach Abschluss: was wurde gemacht, was ist offen
- Bei Unsicherheit: Frage stellen, nicht weiterraten

### Ziel
Lieber kurz pausieren und fragen als Token verschwenden durch falsche Annahmen.

## Run Command
streamlit run app.py

## Stack
Python, Streamlit, yfinance, Plotly, Pandas, Requests
Dark navy theme: background #0a0f1e, accent teal #00c49a
Branding footer: "Built by @realedgetraders" on every page

## File Structure
trading-terminal/
├── app.py                    → Hub/landing page with module cards
├── pages/
│   ├── 1_Seasonality.py     → MODULE 1: COMPLETE ✓
│   ├── 2_COT_Analysis.py    → MODULE 2: COMPLETE ✓
│   ├── 3_Macro_Dashboard.py → MODULE 3: COMPLETE ✓
│   ├── 4_Geopolitics.py     → MODULE 4: COMPLETE ✓
│   └── 5_News_Feed.py       → pending
├── requirements.txt
└── CLAUDE.md

## Module Status
- Module 1 (Seasonality Tracker): COMPLETE ✓ — DO NOT MODIFY
- Module 2 (COT Analysis): COMPLETE ✓ — DO NOT MODIFY
- Module 3 (Economic Bias Engine): COMPLETE ✓ — DO NOT MODIFY unless explicitly asked
- Module 4 (Geopolitics & News): COMPLETE ✓ — DO NOT MODIFY unless explicitly asked
- Module 5 (News Feed): pending

---

## Project
Forex trading terminal — Streamlit, Python, 8 currencies, 28 pairs.
Main file: pages/3_Macro_Dashboard.py

## Bias Scoring System (current state — fully working)
- fetch_currency_history() returns dated pairs: {indicator: [(YYYY-MM, float), ...]}
- All fetchers (FRED, ECB, Investing.com) return dated pairs
- HISTORY_FALLBACK and plain-value sources wrapped with _assign_approximate_dates()
- _strip_dates() converts at main() boundary — all scoring logic receives plain value lists
- _score_indicator(name, vals) — scores one indicator, requires len >= 3
- _calc_raw_score(history) — weighted average across all indicators, returns float
- calc_all_biases(all_histories) — z-score normalization across all 8 currencies in one pass
  - Computes raw score per currency, then normalizes: (raw - mean) / std * 1.2
  - Labels: > +0.4 BULLISH, < -0.4 BEARISH, else NEUTRAL
- 12M chart: true monthly re-score — for each month filters dated history to date <= month, then scores
  - Rightmost point verified = live score (delta 0.000000)

## Indicator Weights (_IND_WEIGHTS in pages/3_Macro_Dashboard.py ~line 415)
Tier 1 — CB-critical (directly drives rate decisions & FX moves):
- Interest Rate: 2.0
- CPI YoY: 2.0
- CPI m/m: 2.0
- GDP Growth: 2.0
- Core CPI: 1.8

Tier 2 — activity / labour (swing-relevant, market-moving):
- Unemployment Rate, Employment Change, Wage Growth: 1.0
- Manufacturing PMI, Services PMI, Composite PMI, Trade Balance: 1.0
- Retail Sales, Industrial Production, Current Account: 0.8

Tier 3 — sentiment / structural (low swing relevance):
- Consumer Confidence, Business Confidence: 0.5
- PPI, M2 Money Supply: 0.4
- Budget Balance, Government Debt, Building Permits: 0.3

Tier-1 share of total weight (USD active set): 43.1% (was 31.2% before)
Verified before/after scores (2026-05-24):
  USD +1.452 → +1.154 | EUR +0.283 → +0.180 | GBP -1.558 → -1.327
  JPY +1.360 → +1.477 | AUD +0.622 → +0.739 | CAD -1.953 → -2.126
  CHF +0.543 → +0.707 | NZD -0.747 → -0.803
  Ranking change: JPY #1, USD #2 (swapped). All others unchanged.

## Data Sources (per currency)
- USD: FRED API (11 indicators live) + Investing.com (PMI only)
- EUR: ECB API + Eurostat + Investing.com (11 indicators live)
- GBP/JPY/AUD/CAD/CHF/NZD: Investing.com live + HISTORY_FALLBACK for gaps

## Known remaining gaps
- Consumer Confidence: no live source for most currencies (HISTORY_FALLBACK)
- USD PMI: only 3-4 months depth from Investing.com (calendar too dense for 200-row cap)
- EUR Consumer Confidence: Investing.com importance filter excludes EC survey

## Upcoming Events Calendar (lower-left panel)
- Function: fetch_upcoming_events() — @st.cache_data(ttl=900)
- Source: ForexFactory JSON feeds (nfs.faireconomy.media) — same _FF_MACRO_URLS/headers already in use
- Filters: actual==null (not yet released), date in future, currency in 8 majors, impact High/Medium
- Tier classification: keyword match on title (_CAL_TIER1_KW / _CAL_TIER2_KW); High-impact fallback → T2
- Returns up to 7 events sorted by date; deduplicates by (currency, title[:20], date)
- Render: render_upcoming_calendar(events) → HTML card, dark-theme, date-grouped rows
- Fallback: empty list → "⚠ Calendar unavailable" message, no crash
- Placement: col_rank (left column), below "All Currencies — Bias Ranking"
- Known edge case: "Official Cash Rate" (NZD) classifies as T2 instead of T1 — title doesn't match
  "interest rate" / "rate decision" keywords; cosmetic only (tag colour), no scoring impact

## Cache
- fetch_currency_history: TTL=3600s
- fetch_upcoming_events: TTL=900s (15 min)
- Manual refresh button clears all caches
- Auto-rerun every 300s (hits cache unless TTL expired)

## Last commits
- (pending): tiered indicator weight rebalancing
- 4ee439b: disclaimer moved to full-width row below gauge bar
- 90e5b09: simplify bias labels to 3 levels (BULLISH/NEUTRAL/BEARISH)
- fbdc7b3: true monthly re-score chart rebuild
- 25aca03: z-score normalization across 8 currencies

---

## Module 1 — Seasonality Tracker (COMPLETE)
pages/1_Seasonality.py — DO NOT BREAK THIS FILE

Layout:
- Title row: st.columns([2,5,2]) — "← Back to Hub" left | "Seasonality Tracker" centered | empty right
- Controls row: ASSET dropdown | HISTORICAL DATA buttons (5y/10y/15y/20y/25y) | PATTERN WINDOW (START/END date pickers)
- START date default: today | END date default: today + 1 month
- Info line: "{asset} · {X}-Year Analysis · {n} Trading Days · {date range} · Data: Yahoo Finance"
- Main chart: seasonal trend line, mean-normalized to 100, rolling(3) smooth
- Slider below chart: date range selector synced with date pickers, colored green/gray
- Pattern Analysis section: donut chart (Long % green / Short % red), stats cards (Ann.Return, Win Rate, Avg Return, Median Return, Sharpe), additional stats (Gains, Losses, Best Trade, Worst Trade, Std Dev, Streak), year-by-year table
- Seasonality Radar: best-pattern finder per asset, 10Y fixed history, Forex/Index split, Extreme/Watch/Bias signals, dynamic window scanner (start offsets -3..+7 days, lengths 14/21/30d), WINDOW + DAYS columns

Assets: all major/minor Forex pairs + indices + commodities via yfinance
History: 5y/10y/15y/20y/25y (Radar always uses 10Y)
Sharpe: avg_return / std_return (no annualization factor), rf=0

### Data Layer — fetch_data()
- Forex cross-pairs (GBPAUD, EURJPY, etc.): synthetic calculation via USD major legs
  → GBPAUD = GBPUSD / AUDUSD — gives 20+ years history
  → SYNTHETIC_CROSSES dict maps all 21 cross-pairs to their USD leg tickers
  → USD_YF dict maps leg keys to yfinance tickers (CAD=X, CHF=X, JPY=X for inverted pairs)
- yfinance -1 day index shift applied to all forex tickers (=X suffix) to correct UTC offset
- Non-forex (indices GC=F ^GSPC etc.): direct yfinance, no shift
- Cache: @st.cache_data(ttl=3600)

### Seasonal Curve — calc_seasonal_curve()
- Method: Month/Day grouping (matches Seasonax exactly)
  1. Exclude current calendar year (incomplete)
  2. Normalize each year to 100 at first trading day
  3. Forward-fill to all calendar dates (weekends included)
  4. Group by (month, day), average across years (≥2 obs)
  5. Re-normalize: curve_mean → 100 (Seasonax re-normalization)
  6. Apply rolling(3, center=True, min_periods=1) smooth
  7. Map to _REF_YEAR=2023 (non-leap) for x-axis Timestamps
- Returns: (mean_df, year_paths) — year_paths no longer plotted
- x-axis: actual date Timestamps (Plotly type="date"), month ticks from first trading day of each month

### Pattern Analysis — calc_pattern_analysis()
- Entry price: Close on entry date (first trading day on/after window start)
- Exit price: Close on exit date (last trading day on/before window end)
- Excludes: current year (≥ current_year) + years where entry < data_start (strictly less than)
  NOTE: entry == data_start IS included (fixes first-year exclusion bug, verified vs Seasonax)
- Annualized Return: (1 + avg_ret/100)^(365/calendar_days) - 1
- Sharpe: avg_ret / std_ret (no sqrt annualization)
- Handles cross-year patterns (e.g. Nov → Feb)

Radar assets (RADAR_ASSETS dict):
- Forex Majors: EUR/USD, GBP/USD, USD/JPY, USD/CHF, AUD/USD, NZD/USD, USD/CAD
- Forex Crosses: EUR/JPY, EUR/GBP, EUR/AUD, EUR/CAD, GBP/JPY, AUD/JPY
- Commodities: Gold (GC=F), Silver (SI=F), Oil WTI (CL=F)
- Indices: S&P 500 (^GSPC), Nasdaq (^IXIC), Dow (^DJI)

Radar signal logic:
- Extreme (⚡): qualified window found (Long % ≥70 or ≤30, ≥7 occurrences) → teal/red row
- Watch (⚠): no qualifying extreme window, shown up to fill 15 total → amber row
- Bias (📊): Index/Commodity category — always structural long bias, separate sub-section
- Forex Extreme + Watch shown in primary table; Index/Commodity in sub-section below

### Key Constants
- _REF_YEAR = 2023 (non-leap reference year for x-axis date mapping)
- SYNTHETIC_CROSSES: 21 cross-pairs → (num_leg, den_leg) tuples
- _USD_YF: maps leg keys to yfinance tickers

## Module 2 — COT Analysis (COMPLETE)
pages/2_COT_Analysis.py — DO NOT BREAK THIS FILE

Data source: CFTC Legacy COT — https://www.cftc.gov/files/dea/history/deacot{YEAR}.zip
Years loaded: 2001 to current year (annual ZIPs, cached with @st.cache_data)
Column format: Legacy COT CSV inside annual.txt (129 columns, space-separated names)

Groups & Colors:
- Commercials:     blue  #3B82F6
- Non-Commercials: gray  #6B7280
- Non-Reportable:  yellow #EAB308

Markets:
- Forex:       EUR / GBP / JPY / CHF / CAD / AUD / NZD
- Commodities: Gold / Silver / Oil (WTI — multi-name OR lookup for pre/post 2022 rename)
- Indices:     S&P 500 / Nasdaq-100 / Dow Jones / Russell 2000
- Bonds:       10Y T-Note / 30Y T-Bond / 2Y T-Note / 5Y T-Note

Charts (in order):
1. COT Index — 26-week min-max normalization per group, range [-2, 105]
2. Long vs Short Donuts — 3 side-by-side donuts (make_subplots), latest report week
3. Net Positioning — dual Y-axis (Non-Reportable on right), 3-year default window
4. COT Divergence Screener — table of all markets sorted by Comm vs NRept divergence (covers all categories including Commodities)

Signal cards: below controls, show COT Index value + Bullish/Bearish/Neutral label per group
No inversion logic — raw CFTC numbers only for all markets

## Module 3 — Economic Bias Engine (COMPLETE)
pages/3_Macro_Dashboard.py — DO NOT BREAK THIS FILE unless explicitly asked

### Overview
Currency-filtered macro scanner for 8 major FX currencies (USD EUR GBP JPY AUD CAD CHF NZD).
Combines static indicator data, live FRED API data, ForexFactory calendar, and
a bias engine into a single dashboard.

### Layout (top to bottom)
1. Title row: "← Back to Hub" left | "ECONOMIC BIAS ENGINE" centered | refresh controls right
2. Currency selector: 8-button radio row (pill style, teal = selected)
3. Bias panel: overall bias gauge (±3.0 scale) + D1/D2/D3/D4 grid + collapsible indicator breakdown
4. Two-column layout: indicators table (left) | calendar only (right)
5. Footer: "Built by @realedgetraders"

### Data Sources
- Live: FRED API (FRED_API_KEY set in file, line ~34) for USD indicators
- Live: ECB Data Portal for EUR indicators
- Live: Investing.com economic calendar for PMI, GDP, CPI, Industrial Production across all currencies
- Live: ForexFactory calendar (JSON + XML fallback, Windows NT UA)
- Static: HISTORY_FALLBACK hardcoded indicator tables for all 8 currencies
- Cache TTLs: fetch_currency_history=3600s, calendar=30min

### Scoring Architecture

**`_score_indicator(name, vals)`**
Scores one indicator from its plain value list (len >= 3 required).
Handles special cases: Business Confidence ZEW vs IFO/OECD scale auto-detection,
CPI deflation floor, Trade Balance trend cap ±15B, GDP QoQ vs annualized auto-detection.

**`_calc_raw_score(history)`**
Weighted average of per-indicator scores. Returns (indicator_scores, raw_float, monthly_scores).

**`calc_all_biases(all_histories)`**
Z-score normalization across all 8 currencies in one pass.
Formula: (raw - mean) / max(std, 0.1) * 1.2, clamped [-3, +3].
Labels: ≥+1.5 STRONG BULLISH, ≥+0.4 SLIGHT BULLISH, ≥-0.4 NEUTRAL,
        ≥-1.5 SLIGHT BEARISH, else STRONG BEARISH.

**`fetch_currency_history(currency, fred_api_key)`**
Returns dict[str, list[tuple[str, float]]] — dated pairs.
CB plain-value fetchers (BOE, RBA, BOC, SNB, TE) wrapped with _assign_approximate_dates().
HISTORY_FALLBACK similarly wrapped.

**`_assign_approximate_dates(plain_history)`**
Assigns synthetic YYYY-MM dates counting backwards from today.

**`_strip_dates(dated_history)`**
Strips dates at main() boundary. All scoring functions receive plain value lists.

### 12M Economic Strength Chart
True monthly re-score: for each of last 12 months, filters each indicator's dated list
to date <= month_str, calls _calc_raw_score() on filtered subset.
Rightmost point verified to match live score exactly (delta = 0.000000).

### Session State Keys
- `macro_scores_{CCY}`: dict with keys total, level, currency, fmt="indicator_12m"
- `macro_last_rerun`: timestamp for 5-min auto-rerun timer
- `macro_currency`: selected currency radio value

## Module 4 — Geopolitics & News (COMPLETE)
pages/4_Geopolitics.py — DO NOT BREAK THIS FILE

### Overview
Currency-filtered geo news reader for 8 major FX currencies.
NO directional trade signals — shows geopolitical headlines per selected currency plus a static
geo-sensitivity profile. Strictly geo/political content only.

### Layout (top to bottom)
1. Title row: "← Back to Hub" left | "GEOPOLITICAL INTELLIGENCE" centered | "🔄 Refresh" right
2. Live pulse dot + tag line
3. Currency selector: 8 radio pills with flag emoji
4. Two-column layout [2:5]:
   - Left: Currency geo profile card + Global Geo Events panel (Reuters / BBC / Al Jazeera)
   - Right: Tab switcher ["🌍 Geo Events" | "📰 Financial News"]
5. Footer: sources + auto-refresh note

### Data Sources
- Geo: Google News RSS via feedparser — 2 geo-specific queries per currency
- Geo secondary: Reuters, BBC World, Al Jazeera direct RSS feeds
- Financial: FXStreet, ForexLive, CNBC, Bloomberg, MarketWatch, Investing.com
- Cache TTLs: per-currency geo=300s, global geo=600s, financial=300s

### Key Constants
- _CCY_GEO_QUERIES: 2 geo-only RSS queries per currency
- _DIRECT_FEEDS: Reuters, BBC, Al Jazeera RSS URLs
- _FIN_FEEDS: FXStreet, ForexLive, CNBC, Bloomberg, MarketWatch, Investing
- _ECON_SKIP_KW: economic noise filter for geo feeds
- _CATEGORIES: Conflict / Sanctions / Political / Diplomatic / Trade War / Energy

## Hub (app.py)
- Dark navy landing page
- Module cards grid — Seasonality + COT Analysis + Macro Dashboard + Geopolitics are LIVE/active
- Module 5 (News Feed): Coming Soon
- Navigation via st.switch_page()
- Footer: "Built by @realedgetraders"

## Design Rules
- Never change completed modules unless explicitly asked
- Keep dark navy theme (#0a0f1e) consistent across all pages
- All new modules follow same layout pattern as existing modules
- "← Back to Hub" button on every module page, top left, same row as title
- Max 3 fix attempts per problem, then report and wait
- No package installs without explicit permission
