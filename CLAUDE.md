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

### Kommunikation
- Vor jedem größeren Schritt: kurz ankündigen was gemacht wird
- Nach Abschluss: was wurde gemacht, was ist offen
- Bei Unsicherheit: Frage stellen, nicht weiterraten

---

## File Structure
```
trading-terminal/
├── app.py                    → Hub/landing page (EdgeLab branding)
├── pages/
│   ├── 1_Seasonality.py     → MODULE 1: COMPLETE ✓
│   ├── 2_COT_Analysis.py    → MODULE 2: COMPLETE ✓
│   ├── 3_Macro_Dashboard.py → MODULE 3: COMPLETE ✓  (also called Economic Bias Engine)
│   ├── 4_Geopolitics.py     → MODULE 4: COMPLETE ✓
│   ├── 5_Market_Regime.py   → MODULE 5: COMPLETE ✓  (Market Phase Scanner)
│   └── 6_Journal.py         → Coming Soon placeholder (Edge Journal, amber/gold accent)
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
- Main chart: seasonal trend line (blue), mean-normalized to 100, rolling(3) smooth
- Pattern Analysis: donut (Long % green / Short % red), stats cards, year-by-year table
- Seasonality Radar: "Top 10 Seasonal Setups — Next 30 Days"

### Radar Logic
- Scans all 13 forex pairs (7 majors + 6 crosses), 10Y history
- Top 10 by distance from 50% (strongest seasonal bias), sorted _qualified first
- Extreme (⚡): Long % ≥70 or ≤30, ≥7 years data → green/red row
- Watch (⚠): directional bias, below threshold → amber row
- Indices & Commodities: collapsed `st.expander` with amber disclaimer (structural trend bias)

### Data Layer
- Forex cross-pairs: synthetic via USD legs (GBPAUD = GBPUSD / AUDUSD)
- yfinance -1 day index shift for forex tickers (=X suffix) to correct UTC offset
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

### Scoring Architecture
- `_score_indicator(name, vals)` — scores one indicator (len >= 3 required)
- `_calc_raw_score(history)` — weighted average, returns (indicator_scores, raw_float, monthly_scores)
- `calc_all_biases(all_histories)` — z-score normalization across all 8 currencies
  - Formula: `(raw - mean) / max(std, 0.1) * 1.2`, clamped `[-3, +3]`
  - Labels: > +0.4 BULLISH, < -0.4 BEARISH, else NEUTRAL
- 12M chart: true monthly re-score per month

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
- 1ca4eef fix(journal): rename subtitle label from Edge Journal to Journal Suite
- 36f9d96 feat(journal): rename header to Edge Journal + add tagline
- 0ed8469 feat(journal): restructure hub to 3 cards — Trade Log, Performance Stats, Trader Profile
- 9b748ed feat(journal): build amber-themed journal hub with feature card grid
- 217932e feat(theme): add .streamlit/config.toml with dark theme and blue primaryColor
- df502b1 feat(hub): rename analysis section title to Real Edge Terminal + tagline
