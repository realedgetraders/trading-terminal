# Trading Analytics Terminal — Project Context

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
│   ├── 4_Correlation.py     → pending
│   └── 5_News_Feed.py       → pending
├── requirements.txt
└── CLAUDE.md

## Module Status
- Module 1 (Seasonality Tracker): COMPLETE ✓ — DO NOT MODIFY
- Module 2 (COT Analysis): COMPLETE ✓ — DO NOT MODIFY
- Module 3 (Macro Dashboard): COMPLETE ✓ — DO NOT MODIFY unless explicitly asked
- Module 4 (Correlation Scanner): pending
- Module 5 (News Feed): pending

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

## Module 3 — Macro Dashboard (COMPLETE)
pages/3_Macro_Dashboard.py — DO NOT BREAK THIS FILE

### Overview
Currency-filtered macro scanner for 8 major FX currencies (USD EUR GBP JPY AUD CAD CHF NZD).
Combines static indicator data, live FRED API data, ForexFactory calendar, RSS news, and
a 4-Dimensional bias engine into a single dashboard.

### Layout (top to bottom)
1. Title row: "← Back to Hub" left | "Macro Fundamentals Dashboard" centered | refresh controls right
2. Currency selector: 8-button radio row (pill style, teal = selected)
3. Bias panel: overall bias gauge (±3.0 scale) + D1/D2/D3/D4 grid + collapsible indicator breakdown
4. Two-column layout: indicators table (left) | calendar + news (right)
5. Footer: "Built by @realedgetraders"

### Data Sources
- Live: FRED API (FRED_API_KEY set in file, line ~33) for USD indicators
- Live: ECB Data Portal for EUR indicators
- Live: ForexFactory calendar (JSON + XML fallback, Windows NT UA)
- Live: Google News RSS via feedparser for D3/D4 news signals
- Static: hardcoded indicator tables for all 8 currencies (lines ~100–576)
- Cache TTLs: indicators 1h, calendar 30min, news 5min, D3/D4 news 10min

### Scoring Architecture — Two-Layer Approach

**Layer 1: `calc_bias_score()` (lines ~1507–1770)**
Internal 4-dimensional scorer. Returns dict with keys: `total` ∈ [-1,+1], `d1`-`d4` aggregates, `scores` list.
Used only as input to Layer 2 (d3/d4 aggregates reused as D2 of the 4D engine).

Dimensions (all ∈ [-1,+1], impact-weighted where stated):
- D1 Absolute Level (15%): currency-specific neutral zones, equal-weighted avg
- D2 Forecast Quality (10%): 50% absolute quality + 50% directional vs previous
- D3 Beat/Miss (40%): actual vs forecast, impact-weighted (High=5×, Med=2×, Low=0.5×)
- D4 Trend/Momentum (35%): actual vs previous, impact-weighted same
- Final = (D1×0.15 + D2×0.10 + D3×0.40 + D4×0.35) × 1.4, clamped [-1,+1]

_sdiff() thresholds: 7-level mapping (±1.0/±0.5/±0.3/0.0) using per-indicator _SLT/_STR dicts.
IN LINE band = ±(slt×0.5), weak tier = ±(slt→slt×0.5).

**Layer 2: `calc_4d_bias()` (lines ~2483–2609)**
The display-facing 4-Dimensional engine. Each dimension ∈ [-3,+3], final = simple average.
Returns: `total`, `level`, `level_color`, `dim1`–`dim4`.

```
D1 (25%) — Current values vs fundamental benchmarks (_d1_bench helper)
           Impact weights: High=0.8, Med=0.6, Low=0.3, Critical=1.0
           Per-indicator linear/piecewise mapping to [-3,+3]

D2 (25%) — Beat/miss + trend momentum
           = (bias_old["d3"] + bias_old["d4"]) / 2.0 × 3.0
           Reuses Layer 1 d3/d4 aggregates scaled to [-3,+3]

D3 (25%) — Next CB action pricing + same-day web news adjustment
           = _D3_BASE[ccy] + fetch_d3_d4_news()["d3"][ccy]
           _D3_BASE hardcoded (EUR=+2.5, JPY=+1.5, AUD=+0.8, USD=+0.3,
                               CAD=0.0, GBP=-0.3, CHF=-0.5, NZD=-1.0)
           Web adjustment ∈ {-1.0,-0.5,0.0,+0.5,+1.0} via hawk/dove keyword scan

D4 (25%) — Rate differential + macro structure + live news adjustment (NO geo)
           = _D4_STRUCTURAL[ccy] + fetch_d3_d4_news()["d4"][ccy]
           _D4_STRUCTURAL: USD=+0.7, GBP=+0.5, AUD=+0.4, CAD=+0.1,
                           NZD=0.0, EUR=-0.1, CHF=-0.8, JPY=-1.5
           Geo constants (_GEO_QUERY, _GEO_CCY_IMPACT etc.) kept in file — reserved for Module 4

Final = (D1+D2+D3+D4) / 4  clamped [-3,+3]
```

Level thresholds: ≥2.0=STRONG BULLISH, ≥0.8=SLIGHT BULLISH, ≥-0.7=NEUTRAL,
                  ≥-2.0=SLIGHT BEARISH, else=STRONG BEARISH

### `fetch_d3_d4_news()` (line ~2433)
@st.cache_data(ttl=600). Fetches Google News RSS for D3 (CB queries) + D4 (fundamental queries).
_hawk_dove() counts hawk/dove keywords across up to 6 articles per currency.
net score: ≥+2→+1.0, +1→+0.5, 0→0.0, -1→-0.5, ≤-2→-1.0.

### Bias Panel UI — `render_bias_panel()` (line ~2005)
- Gauge: ±3.0 → 0–100% via (score+3.0)/6.0×100. Pure CSS multi-layer gradient (no position:absolute).
- D1/D2/D3/D4 grid: 4-column CSS grid, each cell shows label + large score number.
- Collapsible indicator breakdown: `<details>` toggle "Show indicator breakdown ▼"
- Score scale labels: STR.BEARISH | SLT.BEARISH | NEUTRAL | SLT.BULLISH | STR.BULLISH

### Indicators Table UI — `render_indicators_table()` (line ~2108)
- Columns: Indicator | Actual | Prev | Forecast | Beat/Miss | Trend | Date | Imp
- D1 level pill below indicator name, D2 expectation pill below forecast value
- Beat/Miss + Trend cells: arrow (13px) + score badge [±X.X] only — no text label
- Impact: HIGH=red pill, MEDIUM=yellow pill, LOW=single dot (no pill)
- Row alternating background (odd rows: C["dim"])
- Left color border: green if _rc>0.3, yellow if _rc>-0.3, else red
- max-height: 520px with overflow-y:auto scroll
- Padding: 12px vertical on all body tds

### Calendar error (if ForexFactory unavailable)
Shows: "⚠ Calendar unavailable — all sources blocked" (no raw HTTP codes)

### Session State Keys
- `macro_scores_{CCY}`: dict with keys total, level, dim1–dim4, currency, fmt="4d"
- `macro_last_rerun`: timestamp for 5-min auto-rerun timer
- `macro_currency`: selected currency radio value

### Constants (lines ~359–415)
- _D3_BASE, _D4_STRUCTURAL, _D3_CB_QUERIES, _D4_NEWS_QUERIES
- _CB_HAWK_KW, _CB_DOVE_KW — keyword tuples for hawk/dove detection
- FRED_API_KEY — hardcoded, enables live USD data from FRED
- _CY / _NY — current year / next year (computed at import time, used in f-string queries)
- BOE_RATE_URL — FY/TY computed dynamically from datetime.today().year (rolling 2-year window)
- _GEO_QUERY, _GEO_CCY_IMPACT, _GEO_BULL_KW, _GEO_BEAR_KW — geo constants retained, reserved for Module 4

## Hub (app.py)
- Dark navy landing page
- Module cards grid — Seasonality + COT Analysis + Macro Dashboard are LIVE/active, others "Coming Soon"
- Navigation via st.switch_page()
- Footer: "Built by @realedgetraders"
- Hub is always editable — add new modules here as they are completed

## Design Rules
- Never change completed modules unless explicitly asked
- Keep dark navy theme (#0a0f1e) consistent across all pages
- All new modules follow same layout pattern as existing modules
- "← Back to Hub" button on every module page, top left, same row as title
- Max 3 fix attempts per problem, then report and wait
- No package installs without explicit permission
