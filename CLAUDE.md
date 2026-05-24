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
- _calc_raw_score(history) — weighted average across all indicators, returns (indicator_scores, raw_float, monthly_scores)
- calc_all_biases(all_histories) — z-score normalization across all 8 currencies in one pass
  - Computes raw score per currency, then normalizes: (raw - mean) / max(std, 0.1) * 1.2
  - Clamped to [-3, +3]
  - Labels via _label_from_score(): > +0.4 → BULLISH, < -0.4 → BEARISH, else NEUTRAL
- 12M chart: true monthly re-score — for each month filters dated history to date <= month, then scores
  - Rightmost point verified = live score (delta 0.000000)

## Indicator Weights (_IND_WEIGHTS in pages/3_Macro_Dashboard.py ~line 415)
Exact values as in code (verified 2026-05-24):

Tier 1 — CB-critical (directly drives rate decisions & FX moves):
- Interest Rate:        2.0
- CPI YoY:             2.0
- CPI m/m:             2.0
- GDP Growth:          2.0
- Core CPI:            1.8

Tier 2 — activity / labour (swing-relevant, market-moving):
- Unemployment Rate:   1.0
- Employment Change:   1.0
- Wage Growth:         1.0
- Manufacturing PMI:   1.0
- Services PMI:        1.0
- Composite PMI:       1.0
- Trade Balance:       1.0
- Retail Sales:        0.8
- Industrial Production: 0.8
- Current Account:     0.8

Tier 3 — sentiment / structural (low swing relevance):
- Consumer Confidence: 0.5
- Business Confidence: 0.5
- PPI:                 0.4
- M2 Money Supply:     0.4
- Budget Balance:      0.3
- Government Debt:     0.3
- Building Permits:    0.3

Tier-1 share of total weight (USD active set): 43.1% (was 31.2% before)
Verified before/after scores (2026-05-24):
  USD +1.452 → +1.154 | EUR +0.283 → +0.180 | GBP -1.558 → -1.327
  JPY +1.360 → +1.477 | AUD +0.622 → +0.739 | CAD -1.953 → -2.126
  CHF +0.543 → +0.707 | NZD -0.747 → -0.803
  Ranking change: JPY #1, USD #2 (swapped). All others unchanged.

## Data Sources (per currency)
- USD: FRED API (FRED_API_KEY set in file, line ~34) for USD indicators
- EUR: ECB API + Eurostat + Investing.com (11 indicators live)
- GBP/JPY/AUD/CAD/CHF/NZD: Investing.com live + HISTORY_FALLBACK for gaps

## Known remaining gaps
- Consumer Confidence: no live source for most currencies (HISTORY_FALLBACK)
- USD PMI: only 3-4 months depth from Investing.com (calendar too dense for 200-row cap)
- EUR Consumer Confidence: Investing.com importance filter excludes EC survey

## Upcoming Events Calendar (Module 3 — left column, below 12M chart)
- Function: `fetch_upcoming_events()` — `@st.cache_data(ttl=900)` (15 min)
- Source: ForexFactory JSON feeds (`_FF_MACRO_URLS`): ff_calendar_month.json,
  ff_calendar_thisweek.json, ff_calendar_nextweek.json (same headers as fetch_ff_macro_data)
- Filters applied (in order):
  1. actual is null (not yet released)
  2. date > now (future only)
  3. currency in _CAL_CURRENCIES frozenset {"usd","eur","gbp","jpy","aud","cad","chf","nzd"}
  4. impact == "High" only (Medium excluded as too noisy for this panel)
  5. title NOT in _CAL_SKIP_KW: trimmed mean, rate statement, speech, speaks, remarks,
     testimony, minutes, forum, vote count
  6. title matches _CAL_TIER1_KW or _CAL_TIER2_KW — no High-impact fallback
- Tier classification:
  - _CAL_TIER1_KW: interest rate, rate decision, cash rate, policy rate, monetary policy,
    press conference, cpi, core cpi, inflation, gdp, gross domestic, non-farm, nonfarm,
    employment change
  - _CAL_TIER2_KW: pmi, trade balance, unemployment, jobless, wage
- Returns up to 7 events sorted chronologically; deduplicates by (currency, title[:20], date_str)
- Render: `render_upcoming_calendar(events)` → HTML card, dark-theme, date-grouped rows
  - Badge labels: HIGH (red #ef4444) = Tier 1, MEDIUM (orange #f97316) = Tier 2,
    LOW (yellow #eab308) = fallback (not currently assigned)
- Fallback: empty list → "⚠ Calendar unavailable" message, no crash
- Placement: inside `render_economic_charts()` col1, directly after `st.plotly_chart(fig1)`
- Known edge case: "Official Cash Rate" (NZD) → classifies as Tier 2 (title doesn't contain
  "interest rate"/"rate decision"); cosmetic only, no scoring impact

## Cache (Module 3)
- fetch_currency_history: TTL=3600s
- fetch_upcoming_events: TTL=900s (15 min)
- fetch_ff_macro_data: TTL=1800s (30 min)
- Manual refresh button clears all caches
- Auto-rerun every 300s (hits cache unless TTL expired)

## Last commits
- 911046d fix(geopolitics): improve economic calendar — relaxed filter, time column, noise KW list
- 127c774 feat(news): sort feeds newest-first and add ↗ Read more links
- ece9538 fix(ui): hide misaligned Streamlit radio indicator in currency pill selector
- 9af8576 fix(calendar): replace T1/T2 badges with HIGH/MEDIUM/LOW impact labels
- ed6397e fix(calendar): tighten upcoming events filter to High-impact bias-relevant events only
- 8cdc8c2 feat(calendar): add upcoming economic events mini-calendar below 12M chart
- 5063b2b feat(scoring): rebalance indicator weights to 3-tier swing-trading model
- 4ee439b fix(ui): move disclaimer to full-width row below gauge bar

---

## ⚠ Open Items (as of 2026-05-24)

1. **Economic Calendar (Module 4) — filter/coverage still not final**
   - Current state: High + Medium + Low impact, noise KW filter, time column added
   - Problem: still fewer events visible than Investing.com shows — likely FF feed coverage
     or Low-impact events being too sparse in the feed
   - Next step: compare live FF feed content against Investing.com for a specific currency,
     identify which event types are missing, adjust filter or add static fallback rows

2. **Divergence Pair Table (Module 3) — not verified against new calc_all_biases**
   - The pair divergence table (shows strongest bullish vs. bearish pairs) was built before
     the z-score normalization refactor in calc_all_biases()
   - Not confirmed whether it correctly reads from the new session state format
     (macro_scores_{CCY} dict with keys: score, label, label_color, indicator_scores,
     monthly_scores, n_indicators)
   - Next step: read the divergence table rendering code and verify it uses `score` key
     from the new format, not any legacy key

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
4. Two-column layout [left: 12M chart + upcoming calendar | right: indicator bar chart]
5. Full-width indicators table + All Currencies ranking
6. Footer: "Built by @realedgetraders"

### Data Sources
- Live: FRED API (FRED_API_KEY set in file, line ~34) for USD indicators
- Live: ECB Data Portal for EUR indicators
- Live: Investing.com economic calendar for PMI, GDP, CPI, Industrial Production across all currencies
- Live: ForexFactory calendar (JSON feeds, Windows NT UA) for upcoming events + live macro values
- Static: HISTORY_FALLBACK hardcoded indicator tables for all 8 currencies
- Cache TTLs: fetch_currency_history=3600s, fetch_upcoming_events=900s, fetch_ff_macro_data=1800s

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
3-level labels via _label_from_score(): > +0.4 BULLISH, < -0.4 BEARISH, else NEUTRAL.

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
- `macro_scores_{CCY}`: dict with keys score, label, label_color, indicator_scores,
  monthly_scores, n_indicators
- `macro_last_rerun`: timestamp for 5-min auto-rerun timer
- `macro_currency`: selected currency radio value

## Module 4 — Geopolitics & News (COMPLETE)
pages/4_Geopolitics.py — DO NOT BREAK THIS FILE unless explicitly asked

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
   - Right: Tab switcher ["🌍 Geo Events" | "📰 Financial News" | "📅 Economic Calendar"]
5. Footer: sources + auto-refresh note

### Data Sources
- Geo: Google News RSS via feedparser — 2 geo-specific queries per currency
- Geo secondary: Reuters, BBC World, Al Jazeera direct RSS feeds
- Financial: FXStreet, ForexLive, CNBC, Bloomberg, MarketWatch, Investing.com
- Economic Calendar: ForexFactory JSON + XML CDN endpoints (same FF feeds as Module 3)
- Cache TTLs: per-currency geo=300s (TTL_CCY), global geo=600s (TTL_GLOBAL),
  financial=300s (TTL_FIN), calendar=1800s (TTL_CAL)

### Key Constants
- _CCY_GEO_QUERIES: 2 geo-only RSS queries per currency
- _DIRECT_FEEDS: Reuters, BBC, Al Jazeera RSS URLs
- _FIN_FEEDS: FXStreet, ForexLive, CNBC, Bloomberg, MarketWatch, Investing
- _ECON_SKIP_KW: economic noise filter for geo feeds
- _CATEGORIES: Conflict / Sanctions / Political / Diplomatic / Trade War / Energy
- _CAL_NOISE_KW_M4: bond/treasury/bill/note/JGB/BTP auction noise filter for calendar

### Currency Resolver Fix (commit 911046d)
`_resolve_calendar_ccy_m4(country, title)` — resolution order:
1. COUNTRY_TO_CURRENCY_M4 dict — English names ("Euro Zone", "Japan", etc.)
2. `c.upper()` match against `_SUPPORTED_CCY_M4` list — handles FF lowercase codes
   ("usd" → "USD", "eur" → "EUR") — this was the critical missing step
3. Keyword fallback — only reached for unusual/composite country strings
Bug: FF JSON sends lowercase 3-letter codes; original code only had title-case dict and
uppercase list, so both checks always failed → keyword fallback always used → "us" substring
in keyword list matched "Australian"/"business"/"surplus" → AUD/GBP events mis-tagged as USD.
Fix: added `.upper()` normalisation as step 2; removed "us" and "uk" from keyword lists.

### News Feed (commit 127c774)
- All three feeds sorted newest-first:
  - `fetch_ccy_news()`: `articles.sort(key=lambda a: a["_pub_dt"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)`
  - `fetch_global_news()`: same sort on _pub_dt
  - `fetch_financial_news()`: sort on `published` field
- `_get_pub_dt(entry)` helper: extracts timezone-aware UTC datetime from feedparser entry
- `↗ Read more` link appended to every article card in all three renderers
  (_news_card, render_global_feed, render_financial_feed)

### Economic Calendar — current state (commit 911046d)
- FF endpoints: thisweek.json + nextweek.json + month.json (JSON) +
  thisweek.xml + nextweek.xml (XML CDN fallback) — `_FF_ENDPOINTS_M4`
- Time window (`build_calendar_view_m4`):
  - Start: Monday of current week → `now - pd.Timedelta(days=now.dayofweek)`
  - End: `now + pd.Timedelta(weeks=14)`
  - Covers full Mon–Sun of current calendar week, not just from today
- Impact filter: High, Medium, Low — only "Holiday" excluded
- Noise filter (`_CAL_NOISE_KW_M4`): bond auction, treasury auction, bill auction,
  note auction, gbond auction, btp auction, jgb auction, linker auction,
  t-bill, t-note auction, t-bond auction — skipped regardless of impact
- Time column: first column in table, HH:MM extracted from FF datetime field;
  "—" if time component is 00:00 (date-only event)
- Static fallback: `_STATIC_CALENDAR_M4` — hard-coded High/Medium events for all
  8 currencies through ~Jul 2026, used when FF feeds are unreachable
- Sort order: descending (newest/most-recent first within the window)
- ⚠ Known issue: calendar still shows fewer events than Investing.com — FF Low-impact
  CB speeches/minutes appear in feeds but sparsely; coverage gap not yet resolved

### Radio Button CSS Fix (commit ece9538)
Streamlit's radio indicator div (outer colored circle + inner white dot) uses pseudo-elements
that break under `display:inline`. Fix uses `:has(p)` selector to target only the text wrapper:
```css
div[data-testid="stRadio"] label > div:not(:has(p)) { display:none !important; }
div[data-testid="stRadio"] label > div:has(p),
div[data-testid="stRadio"] label > div:has(p) > p {
    display:inline !important; font-family:monospace !important; ...
}
```

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
