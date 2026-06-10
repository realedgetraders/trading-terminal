# EdgeLab — Trading Terminal Project Context

## Project Info
- **Name:** EdgeLab
- **Local path:** /Users/tim/trading-terminal
- **GitHub:** github.com/realedgetraders/trading-terminal
- **Deployed:** trading-terminal.streamlit.app
- **Main file:** app.py
- **Stack:** Python, Streamlit multi-page app (`pages/` directory), yfinance, Plotly, Pandas, Requests

## Run Command
```
streamlit run app.py
```

---

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

### Git-Regeln
- **Immer direkt auf main committen**
- **Nach jedem Commit sofort pushen (`git push origin main`) — kein manuelles Triggern nötig**
- **Niemals Pull Requests erstellen**
- Änderungen müssen chirurgisch und gezielt sein
- Keine anderen Module oder Logik anfassen als explizit gefragt

### _shared.py Sync-Regel (IMMER einhalten)
- `_shared.py` ist die **single source of truth** für alle Daten-Funktionen, die Module 7 (Pair Intelligence) nutzt
- Betroffene Funktionen: `fetch_cot_raw`, `get_cot_metrics`, `fetch_pair_history`, `calc_seasonal_curve`, `seasonal_month_stats`, `fetch_calendar`
- **Wenn Fetch-Logik in einem Hauptmodul (1/2/4) geändert wird → `_shared.py` entsprechend aktualisieren**
- Module 7 importiert direkt aus `_shared.py` und übernimmt Änderungen automatisch
- Design-System C-Dict in `_shared.py` muss immer mit den Haupt-Modulen synchron bleiben

### Kommunikation
- Vor jedem größeren Schritt: kurz ankündigen was gemacht wird
- Nach Abschluss: was wurde gemacht, was ist offen
- Bei Unsicherheit: Frage stellen, nicht weiterraten

---

## File Structure
```
trading-terminal/
├── app.py                    → Hub/landing page (EdgeLab branding)
├── _shared.py               → SHARED UTILITIES — single source of truth for COT/seasonality/calendar
├── pages/
│   ├── 1_Seasonality.py     → MODULE 1: COMPLETE ✓
│   ├── 2_COT_Analysis.py    → MODULE 2: COMPLETE ✓
│   ├── 3_Macro_Dashboard.py → MODULE 3: COMPLETE ✓  (also called Economic Bias Engine)
│   ├── 4_Geopolitics.py     → MODULE 4: COMPLETE ✓
│   ├── 5_Market_Regime.py   → MODULE 5: COMPLETE ✓  (Market Phase Scanner)
│   ├── 6_Journal.py         → Coming Soon placeholder (Edge Journal, amber/gold accent)
│   ├── 7_Pair_Intelligence.py → MODULE 7: COMPLETE ✓  (PRO, password-gated)
│   └── 7_Valuation.py       → Valuation Tool: COMPLETE ✓  (rolling-range 0–100 vs 4 macro anchors)
├── scripts/                 → Supabase collectors (data pipeline for the edgelabweb web port)
│   ├── fetch_cot_data.py            → cot_data (19 markets × 3 trader categories)
│   ├── fetch_seasonality_prices.py  → seasonality_prices (56 instruments, daily OHLC ~25y)
│   ├── fetch_vix_history.py         → vix_history (^VIX daily close ~2y)
│   └── fetch_valuation_prices.py    → valuation_prices (45 futures+anchor closes ~3y)
├── requirements.txt
└── CLAUDE.md
```

## Module Status
- Module 1 (Seasonality Tracker): COMPLETE ✓ — DO NOT MODIFY unless explicitly asked
- Module 2 (COT Analysis): COMPLETE ✓ — DO NOT MODIFY unless explicitly asked
- Module 3 (Economic Bias Engine / Macro Dashboard): COMPLETE ✓ — DO NOT MODIFY unless explicitly asked
- Module 4 (Geopolitics & News): COMPLETE ✓ — DO NOT MODIFY unless explicitly asked
- Module 5 (Market Phase Scanner): COMPLETE ✓ — DO NOT MODIFY unless explicitly asked
- Module 6 (Edge Journal): Coming Soon placeholder — amber/gold accent
- Module 7 (Pair Intelligence): COMPLETE ✓ — PRO-gated, password "12345", imports data layer from `_shared.py`
- Valuation Tool (`7_Valuation.py`): COMPLETE ✓ — rolling-range 0–100 (stochastic %K) vs Precious Metals · USD · Bonds · World Equities; futures screener; 38 futures + custom ticker

## Data pipeline (collectors → Supabase → edgelabweb web port)

### Single source of truth — the asset registry
The canonical asset registry lives in **edgelabweb** (`lib/assets.ts`) and is served
as JSON at **`/api/assets`** (deployed: `https://edgelabweb.vercel.app/api/assets`).
- **856 assets** across categories `fx` / `commodity` / `index` / `rate` / `crypto` / `stock`.
- Each asset carries `symbol`, `name`, `category`, `yfinanceTicker`, capability
  `modules` (seasonality/screener/correlation/valuation/cot), a `seasonality`
  resolution block, plus `sector` (stocks) and `popular` (curated core vs long-tail).
- **44 COT-eligible** markets (`modules.cot` true ⇔ a `cotMarketName` is set —
  CFTC-covered futures + CME crypto only, never individual stocks).
- Curated entries (`a(...)`, `popular: true`) vs expanded long-tail (`tail(...)`,
  `popular: false`). Registry edits happen in edgelabweb, NOT here.

### Collectors (`scripts/`) — feed-driven, incremental
Standalone scripts fetch source data and upsert into Supabase (read by the Next.js
app). **Feed-driven:** the work-list comes from `/api/assets` via `_assets_feed.py`
(caches each good response to `scripts/.assets_cache.json`; on a network failure it
falls back to that cache, never runs on no data). All idempotent (upsert on natural
key). Credentials from env / `.env` (`SUPABASE_URL`, `SUPABASE_SECRET_KEY`).

- `fetch_cot_data.py`           → `cot_data` (44 markets × 3 trader categories, raw long/short from 2001; MICRO/ULTRA look-alikes excluded)
- `fetch_seasonality_prices.py` → `seasonality_prices` (feed seasonality universe, daily OHLC ~25y; synthetic forex crosses, corrected leg orientation)
- `fetch_vix_history.py`        → `vix_history` (^VIX daily close ~2y)
- `fetch_valuation_prices.py`   → `valuation_prices` (feed valuation universe + macro-anchor tickers, adjusted close ~3y)
- `fetch_macro_data.py`         → `macro_data` (8 currencies × 4 core indicators from DBnomics)

### Modes — `_incremental.py` (`--mode auto|backfill|incremental`, env `COLLECTOR_MODE`, default `auto`)
- **auto** (scheduled default): per series, full **backfill** if it has no stored data,
  else a **tail** update from `last stored date − 5d overlap` forward. Tail output is
  **byte-identical** to a full pull for any given date (same logic + idempotent upsert).
- **backfill** forces full history (re-seed); **incremental** forces tail-only.
- **"Latest stored date"** is read with one **per-series indexed query** over the
  `(key, date)` composite index (`WHERE key=… ORDER BY date DESC LIMIT 1`) — a single
  grouped `max(date)` is NOT used because **PostgREST aggregate functions are disabled
  on this Supabase project** (and the big tables have no standalone `date` index).
- Preserved exactly: fx_spot `−1` day shift, synthetic crosses (leg cache), retry-once,
  skip-on-failure, pacing, `auto_adjust`, `Close ≤ 0` drop. Seasonality bulk-downloads
  direct tickers **grouped by per-symbol start date**; valuation stays **per-symbol**
  (its `auto_adjust=True` factor differs in batched vs single download).

### Scheduling — GitHub Actions (schedule + `workflow_dispatch` only; never push/PR)
- **`daily-prices.yml`** — cron `30 23 * * 1-5` (weekdays **23:30 UTC**, after US close):
  seasonality → valuation → vix, `COLLECTOR_MODE=auto`, 30-min timeout.
- **`weekly-collectors.yml`** — cron `0 12 * * 6` (**Sat 12:00 UTC**, after Fri CFTC release):
  cot → macro, `COLLECTOR_MODE=auto`, 15-min timeout.
- Repo secrets (by NAME only): **`SUPABASE_URL`**, **`SUPABASE_SECRET_KEY`** (optional
  `ASSETS_URL` feed override; no FRED key needed). Later steps use `if: always()` so one
  failing collector never blocks the others.

### Supabase
On the **Pro** plan (**8 GB** disk).

Modules ported to edgelabweb so far: COT (M2), Seasonality (M1), Market Phase (M5), Valuation. M3 (Economic Bias) and M4 (Geopolitics) pending.

---

## Hub Structure (app.py)

### Branding
- App name: **EdgeLab**
- Landing title: "Welcome to EdgeLab"
- Tagline: "A Place Where Traders Build Their Edge"
- Footer: "Built by @realedgetraders" on every page

### Landing Page (section = None)
Two large clickable cards side by side — NO separate "Open" buttons, cards themselves are clickable:
- **Left card — Real Edge Terminal** (blue accent `#4f8ef7`, class `ret-landing-analysis`)
  - 5 Live Modules: Seasonality · COT Analysis · Macro Bias · Geopolitics · Market Phase Scanner
- **Right card — Edge Journal** (amber/gold accent `#f0b429`, class `ret-landing-journal`)
  - PRO badge, Coming Soon status
- Cards: `height:340px`, invisible overlay button `margin-top:-356px`, `opacity:0`
- Hover glow via CSS `:has(.ret-landing-analysis):has(+ div:hover)`

### Analysis Section (section = "analysis")
- Header: `▸ ANALYSIS SUITE` / **Real Edge Terminal** / tagline "A Place Where Traders Analyze Their Assets"
- `st.columns(2, gap="large")`
- Active module cards: `height:160px;overflow:hidden`, class `ret-module-active`
- Invisible overlay button: `margin-top:-176px`, `margin-bottom:20px`, `height:160px`, `opacity:0`
- Hover glow: blue `rgba(79,142,247,0.18/0.07)`

### Journal Section (section = "journal")
- Header: `▸ JOURNAL SUITE` / **Edge Journal** / tagline "A Place Where Traders Journal and Improve Their Performance"
- 3 amber-themed feature cards (2 + 1 centred layout):
  - 📝 **Trade Log** — enter & save trades
  - 📊 **Performance Stats** — full analysis, Live/Backtest switch, CSV export for AI
  - 👤 **Trader Profile** — placeholder, content TBD
- Cards: `height:160px`, class `ret-journal-card`, amber border `rgba(240,180,41,0.28)`
- Hover glow: amber `rgba(240,180,41,0.22)`, overlay buttons `disabled=True` (no page yet)
- Auth notice banner at top: "🔒 Authentication required · Launching soon"

### Session State Navigation
- `st.session_state.section`: `None` (landing hub) / `"analysis"` (module grid) / `"journal"` (journal)
- `st.switch_page("pages/X_Name.py")` to navigate into individual modules
- Sidebar switch button toggles between analysis ↔ journal sections

### Streamlit Theme
- `.streamlit/config.toml` sets `primaryColor = "#4f8ef7"` — fixes default red slider fill
- Full dark theme: `backgroundColor="#0d0d0d"`, `secondaryBackgroundColor="#141414"`, `textColor="#e8e8e8"`

---

## Design System

### Color Palette (ALL files)
```python
C = {
    "bg":       "#0d0d0d",
    "card":     "#141414",
    "border":   "#252525",
    "panel":    "#111111",
    "dim":      "#171717",
    "text":     "#e8e8e8",
    "muted":    "#909090",   # secondary text — high enough contrast
    "teal":     "#4f8ef7",   # UI accent — blue (NOT green)
    "teal_bg":  "rgba(79,142,247,0.14)",
    "teal_dim": "rgba(79,142,247,0.06)",
    "green":    "#1a9b6a",   # financial signals ONLY (Long/Short, gains, win rate)
    "green_bg": "rgba(26,155,106,0.09)",
    "red":      "#f05262",
    "red_bg":   "rgba(240,82,98,0.09)",
    "yellow":   "#f0b429",   # amber (Watch signals, Journal accent)
    "blue":     "#4f8ef7",
}
```
Journal page (6_Journal.py) uses `"teal": "#f0b429"` (amber) — its Back button glows amber.

### Color Semantic Rules — NEVER BREAK THESE
- `C["teal"]` = `#4f8ef7` blue → ALL UI accents: buttons, radio pills, borders, chart lines
- `C["green"]` = `#1a9b6a` → ONLY financial signal values: Long %, gains, win rate, positive returns
- `C["yellow"]` = `#f0b429` → Watch signals, Journal section, amber accents
- **NEVER** use green for UI chrome; **NEVER** use blue for directional trade signals
- **NO decorative red** anywhere in the app — red is reserved for bearish/short signals only

### Button Hover Glow (all module pages)
Every `button[kind="secondary"]` has:
```css
transition: border-color 0.22s ease, color 0.22s ease, box-shadow 0.22s ease;
/* hover: */
border-color: {C['teal']}70;
color: {C['teal']};
box-shadow: 0 0 12px rgba(79,142,247,0.14);
```
Journal uses amber equivalent: `rgba(240,180,41,0.14)`.

### Clickable Card Overlay Technique (app.py)
- HTML card rendered as `st.markdown` with CSS class
- Invisible `st.button(" ")` rendered immediately after with `use_container_width=True`
- CSS pulls overlay up via negative `margin-top` to exactly cover the card
- Hover detected via CSS `:has(.card-class):has(+ div:hover)` — fires glow on card
- Module cards: card height 160px → `margin-top: -176px`
- Landing cards: card height 340px → `margin-top: -356px`

### Landing Page Header Divider
```css
width:56px; height:2px; background:#c8c8c8;
box-shadow: 0 0 8px rgba(255,255,255,0.55), 0 0 18px rgba(255,255,255,0.25);
```

---

## Module 1 — Seasonality Tracker (COMPLETE)
pages/1_Seasonality.py — DO NOT MODIFY unless explicitly asked

### Theme
- `C["teal"]` = `#4f8ef7` (blue UI accents: radio pills, chart line, borders)
- `C["green"]` = `#1a9b6a` (signal colors: donut Long slice, win rate, gains, returns)
- `C["muted"]` = `#909090` — all secondary text
- Table header/cell font sizes: 11px

### Layout
- Title row: `st.columns([2,5,2])` — "← Back to Hub" left | "Seasonality Tracker" centered
- Controls: ASSET dropdown | HISTORICAL DATA radio (5y/10y/15y/20y/25y) | PATTERN WINDOW date pickers
- Main chart: seasonal trend line (blue), Seasonax return-cumulation curve — starts at 100, raw daily texture (no smoothing). See **Seasonal Curve Method**.
- Pattern Analysis: donut (Long % green / Short % red), stats cards, year-by-year table
- Seasonality Radar: "Top 10 Seasonal Setups — Next 30 Days"

### Seasonal Curve Method (calc_seasonal_curve) — real Seasonax method
- Average daily **log returns** `log(Close / Close.shift(1))` per `(month, day)` across the available years (≥2 obs/DOY); first trading day per year = anchor (return 0).
- Cumulate in chronological DOY order and index from 100: `index(t) = 100 * exp(cumsum(mean log return))` → curve **starts at 100** at the window start.
- **NO** full-year re-centering to the curve mean (old bug — removed; it made the curve not start at 100).
- **NO** smoothing of the averaged curve (3-day rolling removed) — raw daily texture = Seasonax look; the ~10Y per-DOY average is the only noise control.
- `year_paths` (per-year normalized price LEVELS, 100 at each year's first trading day) unchanged — for a single year identical to the cumulated return curve.

### Asset Categories (shared `SCREENER_CATEGORIES` config — screener + detail selector)
- Forex (28 pairs + Custom in the detail selector) · Commodities · Agriculture · Indices · Bonds · **Crypto** (BTC-USD, ETH-USD)
- One shared mapping/config drives BOTH the radar screener and the top detail selector — no duplicate list. Default category = Forex.
- Crypto trades 7 days/week — handled correctly (per-DOY averaging over available years; weekends contribute naturally, no distortion).

### Radar Logic
- Category filter (pill row, default Forex): Forex scans 13 pairs (7 majors + 6 crosses); other categories scan their `SCREENER_CATEGORIES` tickers — 10Y history
- Top 10 by distance from 50% (strongest seasonal bias), sorted _qualified first
- Extreme (⚡): Long % ≥70 or ≤30, ≥7 years data → green/red row
- Watch (⚠): directional bias, below threshold → amber row
- Non-Forex categories: amber "interpret with caution" banner above the table (structural trend bias)

### Data Layer
- Forex cross-pairs: synthetic via USD legs (GBPAUD = GBPUSD / AUDUSD)
- yfinance -1 day index shift for forex tickers (=X suffix) to correct UTC offset
- **Guard:** `fetch_data` drops rows with `Close <= 0` before any calc (instrument-agnostic; protects normalization/returns). Triggered by WTI Crude's negative 2020-04-20 print — affects only Crude; Forex untouched.
- Data caveats: Platinum (PL=F) has gaps before ~2010 → only relevant at lookback >16Y; Natural Gas (NG=F) inherently volatile (continuous-contract roll noise) — accepted caveat.
- `@st.cache_data(ttl=3600)`

---

## Module 2 — COT Analysis (COMPLETE)
pages/2_COT_Analysis.py — DO NOT MODIFY unless explicitly asked

### Theme
- `C["teal"]` = `#4f8ef7`, `teal_bg` = `rgba(79,142,247,0.14)`, `teal_dim` = `rgba(79,142,247,0.06)`

### Data
- CFTC Legacy COT: `https://www.cftc.gov/files/dea/history/deacot{YEAR}.zip`
- Years 2001 → current, annual ZIPs, `@st.cache_data`

### Groups & Defaults
- Commercials: blue `#3B82F6`
- Non-Commercials: gray `#6B7280` — **OFF by default** (multiselect default = [Commercials, Non-Reportable])
- Non-Reportable: yellow `#EAB308`

### Charts
1. COT Index — 26-week min-max normalization, range [-2, 105]
2. Long vs Short Donuts — plain `go.Figure()` (NO make_subplots), explicit domain per trace
   - x_domains: n=1: `[(0.20,0.80)]`, n=2: `[(0.02,0.46),(0.54,0.98)]`, n=3: `[(0.01,0.31),(0.35,0.65),(0.69,0.99)]`
   - `Y_DOM = (0.18, 0.88)` — donut floats centered
   - `ANN_Y = 0.10` — "Long: X · Short: X" annotation directly below donut bottom
   - Title annotations at y=0.92; margin t=30, b=50, height=310
3. Net Positioning — dual Y-axis, 3-year default window
4. COT Divergence Screener — filtered table, max 10 rows

### COT Divergence Screener
- Filter: show row if `divergence > 70` OR `Comm ≥75/≤25` OR `NRept ≥75/≤25`
- Max 10 rows, sorted by divergence descending
- val_color thresholds: green ≥75, red ≤25
- 5 columns: Market / Cat / Commercials COT / Non-Reportable COT / Divergence (Signal column removed)
- Row tint: green `rgba(26,155,106,0.05)` if either ≥75; red `rgba(240,82,98,0.05)` if either ≤25

---

## Module 3 — Economic Bias Engine (COMPLETE)
pages/3_Macro_Dashboard.py — DO NOT MODIFY unless explicitly asked

### Overview
Currency-filtered macro scanner for 8 major FX currencies (USD EUR GBP JPY AUD CAD CHF NZD).

### Layout
1. Title row: "← Back to Hub" | "ECONOMIC BIAS ENGINE" | refresh controls
2. Currency selector: 8-button radio row (pill style, blue = selected)
3. Bias panel: overall bias gauge (±3.0 scale) + D1/D2/D3/D4 grid + collapsible indicator breakdown
4. Two-column layout [left: 12M chart + upcoming calendar | right: indicator bar chart]
5. Full-width indicators table + All Currencies ranking
6. Footer

### Scoring Architecture (current — NO z-score / NO `calc_all_biases`)
Each currency is scored **fully independently** — there is no cross-currency
normalization. (An older z-score `calc_all_biases` design is gone.)
- Sub-scores: `_score(v, t0,t1,t2,t3, invert=)` → one of `{-1, -0.5, 0, +0.5, +1}`;
  `_score_surprise(actual, forecast)` → beat/miss vs consensus (None when no consensus).
- 5 dimensions, each = `_mean(...)` of its sub-scores (`_mean` skips None sub-scores).
  D1 Monetary · D2 Inflation+Growth · D3 Labour+Activity · D4 Surprises · D5 Proxies.
- `_compute_currency_scores(ccy, ff_df)` builds the composite:
  - **Active-dimension divisor:** average ONLY over dimensions that carry data.
    A dimension is "empty" when none of its `rows` holds a numeric sub-score
    (e.g. D4 when no release in the FF window has a consensus). Empty dims are
    dropped from numerator AND divisor; a dim that HAS data but nets to 0.0 still
    counts. `composite = sum(active_scores) / len(active_scores)` (≥1 in practice —
    D1/D2/D3/D5 always populated via static fallbacks).
  - `final = max(-1.0, min(1.0, composite * 1.3))` — fixed 1.3 gain + clamp `[-1,+1]`.
- Labels: `_level(final)` with fixed thresholds — STRONG/SLIGHT/MILD BULLISH (>0.60/0.30/0.10),
  NEUTRAL (`[-0.10, +0.10]`), MILD/SLIGHT/STRONG BEARISH.
- All-currencies ranking sorts by the independent `total` (`final`) — no relative scaling.
- 12M chart: true monthly re-score per month.

### Session State Keys
- `macro_scores_{CCY}`: dict with keys `total` (float score), `level` (label string e.g. "BULLISH"), `currency` (str), `fmt` ("indicator_12m")
- `last_refresh_ts`: float timestamp for 5-min auto-rerun timer (NOT `macro_last_rerun`)
- `macro_currency`: selected currency radio value

### Indicator Weights (_IND_WEIGHTS)
Tier 1 (CB-critical, weight 2.0–1.8): Interest Rate, CPI YoY, CPI m/m, GDP Growth, Core CPI
Tier 2 (activity/labour, weight 1.0–0.8): Unemployment, Employment Change, Wage Growth, PMIs, Trade Balance, Retail Sales, Industrial Production, Current Account
Tier 3 (sentiment/structural, weight 0.5–0.3): Consumer/Business Confidence, PPI, M2, Budget Balance, Gov Debt, Building Permits

### Data Sources
- USD: FRED API (FRED_API_KEY set in file ~line 34)
- EUR: ECB API + Eurostat + Investing.com (11 indicators live)
- GBP/JPY/AUD/CAD/CHF/NZD: Investing.com live + HISTORY_FALLBACK
- Cache TTLs: fetch_currency_history=3600s, fetch_upcoming_events=900s, fetch_ff_macro_data=1800s

---

## Module 4 — Geopolitics & News (COMPLETE)
pages/4_Geopolitics.py — DO NOT MODIFY unless explicitly asked

### Overview
Currency-filtered geo news reader for 8 major FX currencies. No directional trade signals.

### Layout
1. Title row: "← Back to Hub" | "GEOPOLITICAL INTELLIGENCE" | "🔄 Refresh"
2. Live pulse dot + tag line
3. Currency selector: 8 radio pills with flag emoji
4. Two-column layout [2:5]: Left (geo profile + global events) | Right (tabs: Geo / Financial / Calendar)
5. Footer

### Economic Calendar
- FF endpoints: thisweek.json + nextweek.json + month.json (JSON) + XML CDN fallback
- Day-grouped rows, chronological sort, past events dimmed
- Impact filter: High, Medium, Low (Holiday excluded)
- Noise filter: bond/treasury/bill/note/JGB/BTP auctions excluded

---

## Module 5 — Market Phase Scanner (COMPLETE)
pages/5_Market_Regime.py — DO NOT MODIFY unless explicitly asked

- Previously called "Market Regime" — renamed everywhere to "Market Phase Scanner"
- VIX-based volatility percentile rank vs. 12-month history
- VIX line color: `#a8b0bc` (neutral silver-grey), fill `rgba(168,176,188,0.06)`
- Metric card label: "Phase"
- `C["teal"]` = `#4f8ef7`

---

## Module 6 — Edge Journal (Coming Soon placeholder)
pages/6_Journal.py

- Amber/gold accent: `C["teal"]` = `#f0b429`, `C["amber"]` = `#f0b429`
- Back button hover glows amber: `rgba(240,180,41,0.14)`
- PRO badge, 📓 icon, "Coming Soon" / "In Development" status

---

## Module 7 — Pair Intelligence (COMPLETE)
pages/7_Pair_Intelligence.py — DO NOT MODIFY unless explicitly asked

### Overview
PRO-gated (password `12345`) cross-signal aggregator for any selected forex pair.
Combines COT + Seasonality + Economic Bias + Calendar into one view.

### Password Gate
- `_PASSWORD = "12345"`, session key `"pair_intel_auth"`
- Centered PRO ACCESS badge + password input on lock screen

### Data Architecture — imports from `_shared.py`
- **All fetch/compute functions imported from `_shared.py`** (project root)
- Economic Bias: reads `macro_scores_{CCY}` from `st.session_state` (set by Module 3)
- `_filter_calendar()` — pair-specific 14-day window filter, defined locally

### Sections
1. **COT Positioning** — Commercials COT Index bar + net positions + 4-week trend
   - USD pairs show only the non-USD leg; cross pairs show both if CFTC data available
2. **Seasonal Pattern** — 10Y Seasonax curve, current-month band highlight, month stats
3. **Economic Bias** — base/quote bias cards + derived pair bias (base score − quote score)
   - Shows info message if Module 3 hasn't been visited yet (session state empty)
4. **Upcoming Events** — FF calendar, next 14 days, base + quote currencies

### Pairs
28 major forex pairs: 7 majors + 21 crosses. Custom pair text input overrides dropdown.

### _shared.py Sync
When `_shared.py` is updated, Module 7 picks up changes automatically on next Streamlit run.

---

## Planned Next Phases

### Phase 1 — Railway Migration
- Docker containerisation
- Custom domain
- Secrets management

### Phase 2 — Supabase Integration
- Auth: login / register
- PostgreSQL schema: users, profiles, trades
- Session-based access control

### Phase 3 — Edge Journal (Full Build)
- Trade entry form
- Profiles: Live / Backtest / Paper
- Stats: Win Rate, Risk-Reward, P&L, Drawdown
- Equity curve visualisation

### Phase 4 — Stripe Paywall
- Free tier: Module 1 (Seasonality) only
- Pro tier: All modules + Edge Journal

---

## Known Open Items (as of 2026-05-25)

1. **Economic Calendar (Module 4)** — still fewer events than Investing.com; FF feed coverage gaps not fully resolved
2. **Divergence Pair Table (Module 3)** — not verified against current `calc_all_biases` session state format (`macro_scores_{CCY}` dict with key `total`, not `score`)

---

## Last Commits
- b64fcd8 feat(scripts): valuation prices collector — futures + macro anchors to Supabase
- 09da11c feat(scripts): VIX history collector — daily ^VIX close to Supabase
- e8ced4d feat(scripts): seasonality OHLC collector — 56 instruments, ~25y, to Supabase
- aaacd18 fix(scripts): exclude MICRO/ULTRA look-alikes in COT market match
- 2ef2ddd feat(scripts): COT collector writes all 19 markets, 3 categories, raw long/short from 2001
- 3f845c9 fix(scripts): COT collector uses Commercials net (match Module 2/7)
