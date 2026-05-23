"""
Trading Analytics Terminal — Module 3: Macro Fundamentals
Currency-filtered macro scanner: indicators, event calendar, news feed
"""

import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests
import streamlit as st

try:
    import feedparser
    _FEEDPARSER = True
except ImportError:
    _FEEDPARSER = False

try:
    from bs4 import BeautifulSoup
    _BS4 = True
except ImportError:
    _BS4 = False

# ╔══════════════════════════════════════════════════════════════════════════════
# ║  DATA SOURCE CONFIG
# ╠══════════════════════════════════════════════════════════════════════════════
# ║  FRED API KEY  (free — takes 30 seconds to create)
# ║  → https://fred.stlouisfed.org/docs/api/api_key.html
# ║  Paste your key below to enable live USD indicator data:
# ╚══════════════════════════════════════════════════════════════════════════════
FRED_API_KEY = "92dba3aead2eb80b8066515b6112958b"

# ── Refresh intervals ─────────────────────────────────────────────────────────
AUTO_RERUN_INTERVAL = 300   # 5 min — auto-rerun timer (seconds)
TTL_INDICATORS      = 3600  # 1 h   — FRED / ECB cache TTL
TTL_NEWS            = 300   # 5 min — RSS news cache TTL

# ── Premium news API keys (optional upgrade) ─────────────────────────────────
# BLOOMBERG_API_KEY = ""  # Bloomberg Terminal API — real-time data when set
# REUTERS_API_KEY   = ""  # Reuters Connect API   — premium news feed when set
# When either key is set above, the corresponding source activates automatically.

# ── Colour palette (matches app.py exactly) ──────────────────────────────────
C = {
    "bg":       "#0a0f1e",
    "card":     "#0d1526",
    "border":   "#1a2540",
    "panel":    "#0f1a2e",
    "dim":      "#192038",
    "text":     "#dde4f0",
    "muted":    "#445066",
    "teal":     "#45c4b0",
    "teal_bg":  "rgba(69,196,176,0.12)",
    "teal_dim": "rgba(69,196,176,0.06)",
    "green":    "#00c48c",
    "red":      "#f05262",
    "yellow":   "#f0b429",
    "blue":     "#4f8ef7",
}

# ── Currency maps ─────────────────────────────────────────────────────────────
COUNTRY_TO_CURRENCY: dict[str, str] = {
    "United States":  "USD", "US":             "USD",
    "Euro Zone":      "EUR", "Eurozone":        "EUR", "European Union": "EUR",
    "United Kingdom": "GBP", "UK":              "GBP",
    "Japan":          "JPY",
    "Australia":      "AUD",
    "Canada":         "CAD",
    "Switzerland":    "CHF",
    "New Zealand":    "NZD",
}
SUPPORTED_CURRENCIES = ["USD", "EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "NZD"]
CURRENCY_FLAG = {
    "USD": "🇺🇸", "EUR": "🇪🇺", "GBP": "🇬🇧", "JPY": "🇯🇵",
    "AUD": "🇦🇺", "CAD": "🇨🇦", "CHF": "🇨🇭", "NZD": "🇳🇿",
}
# ── Indicator normalisation (longest-key-first) ───────────────────────────────
_RAW_IND_MAP: dict[str, str] = {
    "consumer price index":   "CPI m/m",
    "consumer confidence":    "Consumer Confidence",
    "consumer sentiment":     "Consumer Confidence",
    "business confidence":    "Business Confidence",
    "average hourly earnings":"Wage Growth",
    "average earnings":       "Wage Growth",
    "markit manufacturing":   "Manufacturing PMI",
    "markit services":        "Services PMI",
    "manufacturing pmi":      "Manufacturing PMI",
    "ism manufacturing":      "Manufacturing PMI",
    "services pmi":           "Services PMI",
    "ism non-mfg":            "Services PMI",
    "ism services":           "Services PMI",
    "building permits":       "Building Permits",
    "housing starts":         "Building Permits",
    "house price":            "Building Permits",
    "producer price":         "PPI",
    "government debt":        "Government Debt",
    "public sector net debt": "Government Debt",
    "national debt":          "Government Debt",
    "gross domestic":         "GDP Growth",
    "current account":        "Current Account",
    "trade balance":          "Trade Balance",
    "budget balance":         "Budget Balance",
    "retail sales":           "Retail Sales",
    "interest rate":          "Interest Rate",
    "cash rate":              "Interest Rate",
    "overnight rate":         "Interest Rate",
    "policy rate":            "Interest Rate",
    "fed funds":              "Interest Rate",
    "base rate":              "Interest Rate",
    "unemployment":           "Unemployment Rate",
    "claimant count":         "Unemployment Rate",
    "jobless":                "Unemployment Rate",
    "wage growth":            "Wage Growth",
    "labor cost":             "Wage Growth",
    "labour cost":            "Wage Growth",
    "michigan":               "Consumer Confidence",
    "westpac":                "Consumer Confidence",
    "tankan":                 "Business Confidence",
    "ifo":                    "Business Confidence",
    "zew":                    "Business Confidence",
    "gdp":                    "GDP Growth",
    "cpi":                    "CPI m/m",
    "ppi":                    "PPI",
}
INDICATOR_MAP: list[tuple[str, str]] = sorted(
    _RAW_IND_MAP.items(), key=lambda x: len(x[0]), reverse=True
)
LOWER_IS_BETTER: dict[str, bool] = {
    "CPI m/m": False, "Interest Rate": False, "GDP Growth": False,
    "Unemployment Rate": True, "Manufacturing PMI": False, "Services PMI": False,
    "Trade Balance": False, "Retail Sales": False,
    "Current Account": False, "Wage Growth": False, "PPI": False,
    "Consumer Confidence": False, "Government Debt": True, "Budget Balance": False,
    "Building Permits": False, "Business Confidence": False,
    "Core CPI": False, "Employment Change": False, "Industrial Production": False,
    "M2 Money Supply": False,
}
INDICATOR_ORDER = [
    # Core — scored
    "CPI m/m", "Interest Rate", "GDP Growth", "Unemployment Rate",
    "Manufacturing PMI", "Services PMI", "Trade Balance", "Retail Sales",
    "Current Account", "Wage Growth", "PPI", "Consumer Confidence",
    "Government Debt", "Core CPI", "Employment Change", "Industrial Production",
    "M2 Money Supply",
    # Extended — table only
    "Budget Balance", "Building Permits", "Business Confidence",
]

# ── FRED API config ───────────────────────────────────────────────────────────
FRED_BASE   = "https://api.stlouisfed.org/fred/series/observations"
FRED_SERIES = {
    # Core macro — high priority
    "CPI m/m":           ("CPIAUCSL",        "mom"),     # CPI All Items — m/m computed
    "Interest Rate":     ("FEDFUNDS",         "latest"),  # Effective Fed Funds Rate
    "GDP Growth":        ("A191RL1Q225SBEA",  "latest"),  # Real GDP % change QoQ
    "Unemployment Rate": ("UNRATE",           "latest"),  # Civilian unemployment rate
    # Secondary
    "Retail Sales":      ("RSAFS",            "mom"),     # Advance retail sales — m/m computed
    "Trade Balance":     ("BOPGSTB",          "latest"),  # Goods & services trade balance ($B)
    "Wage Growth":       ("CES0500000003",    "yoy"),     # Avg hourly earnings — y/y computed
    # New indicators
    "Core CPI":             ("CPILFESL",        "mom"),
    "Employment Change":    ("PAYEMS",          "mom_abs"),
    "Industrial Production":("INDPRO",          "mom"),
    "M2 Money Supply":      ("M2SL",            "yoy"),
}
# Note: FRED key validity check — reject placeholder strings
_FRED_KEY_VALID = bool(
    FRED_API_KEY
    and FRED_API_KEY.strip()
    and FRED_API_KEY not in ("your_key_here", "your_fred_api_key_here", "")
)

# ── ECB API config ────────────────────────────────────────────────────────────
ECB_BASE         = "https://data-api.ecb.europa.eu/service/data"
ECB_RATE_URL     = "https://data-api.ecb.europa.eu/service/data/FM/B.U2.EUR.RT0.ILM.MR.INP?format=csvdata"
ECB_CPI_URL      = "https://data-api.ecb.europa.eu/service/data/ICP/M.U2.N.000000.4.GPC?format=csvdata"
_BOE_FROM_YEAR  = datetime.today().year - 2
_BOE_TO_YEAR    = datetime.today().year
BOE_RATE_URL    = (
    "https://www.bankofengland.co.uk/boeapps/database/fromshowcolumns.asp"
    "?Travel=NIxSUx&FromSeries=1&ToSeries=50&DAT=RNG"
    f"&FD=1&FM=Jan&FY={_BOE_FROM_YEAR}&TD=31&TM=Dec&TY={_BOE_TO_YEAR}"
    "&VFD=Y&html.x=66&html.y=26&SeriesCodes=IUMABEDR"
    "&UsingCodes=Y&CSVF=TT&Exp=N"
)

# ── Trading Economics scrape config ──────────────────────────────────────────
_TE_URLS: dict[str, str] = {
    "EUR": "https://tradingeconomics.com/euro-area/indicators",
    "GBP": "https://tradingeconomics.com/united-kingdom/indicators",
    "JPY": "https://tradingeconomics.com/japan/indicators",
    "AUD": "https://tradingeconomics.com/australia/indicators",
    "CAD": "https://tradingeconomics.com/canada/indicators",
    "CHF": "https://tradingeconomics.com/switzerland/indicators",
    "NZD": "https://tradingeconomics.com/new-zealand/indicators",
}
_TE_HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer":         "https://www.google.com/",
}
# TE row-name fragments → internal indicator key (case-insensitive substring match)
_TE_ROW_MAP: list[tuple[str, str]] = [
    ("inflation rate",      "CPI m/m"),
    ("cpi",                 "CPI m/m"),
    ("consumer price",      "CPI m/m"),
    ("interest rate",       "Interest Rate"),
    ("gdp growth rate",     "GDP Growth"),
    ("gdp growth",          "GDP Growth"),
    ("unemployment rate",   "Unemployment Rate"),
    ("unemployment",        "Unemployment Rate"),
    ("manufacturing pmi",   "Manufacturing PMI"),
    ("services pmi",        "Services PMI"),
    ("service pmi",         "Services PMI"),
    ("balance of trade",    "Trade Balance"),
    ("trade balance",       "Trade Balance"),
    ("retail sales mom",    "Retail Sales"),
    ("retail sales m/m",    "Retail Sales"),
    ("retail sales",        "Retail Sales"),
    ("current account",     "Current Account"),
    ("wage growth",         "Wage Growth"),
    ("wages",               "Wage Growth"),
]

# ── News context scoring config ───────────────────────────────────────────────
_NEWS_QUERIES: dict[str, str] = {
    "USD": "Federal Reserve rate decision US inflation jobs economy when:2d",
    "EUR": "ECB European Central Bank rate eurozone inflation when:2d",
    "GBP": "Bank of England BOE rate UK inflation employment when:2d",
    "JPY": "Bank of Japan BOJ yen rate inflation deflation when:2d",
    "AUD": "RBA Reserve Bank Australia rate inflation employment when:2d",
    "CAD": "Bank of Canada BOC rate inflation oil economy when:2d",
    "CHF": "SNB Swiss National Bank rate franc inflation when:2d",
    "NZD": "RBNZ Reserve Bank New Zealand rate inflation when:2d",
}
_GEO_QUERY = "Iran war oil energy prices geopolitical risk conflict sanctions when:2d"

# (keyword, weight) — case-insensitive substring match on title + summary
_NEWS_BULL_KW: list[tuple[str, float]] = [
    ("rate hike",            3.0), ("raises rates",         3.0),
    ("hawkish surprise",     2.5), ("upside surprise",      2.5),
    ("beats expectations",   2.0), ("better than expected", 2.0),
    ("above forecast",       2.0), ("strong jobs",          2.0),
    ("strong gdp",           2.0), ("robust growth",        2.0),
    ("record employment",    2.0), ("hawkish",              1.5),
    ("tightening",           1.5), ("inflation above",      1.5),
    ("above target",         1.5), ("wage growth",          1.0),
    ("strong retail",        1.5), ("surplus",              1.0),
    ("resilient economy",    1.5), ("rate unchanged",       0.3),
]
_NEWS_BEAR_KW: list[tuple[str, float]] = [
    ("emergency cut",       -3.0), ("rate cut",            -2.5),
    ("cuts rates",          -2.5), ("dovish surprise",     -2.5),
    ("recession fears",     -2.5), ("recession",           -2.0),
    ("worse than expected", -2.0), ("below expectations",  -2.0),
    ("below forecast",      -2.0), ("downside surprise",   -2.0),
    ("deflation",           -2.0), ("contraction",         -2.0),
    ("weak jobs",           -2.0), ("job losses",          -2.0),
    ("stagflation",         -2.0), ("dovish",              -1.5),
    ("easing",              -1.5), ("slowdown",            -1.0),
    ("trade war",           -1.5), ("banking crisis",      -2.5),
    ("rate pause",          -0.5),
]
# Geopolitical keywords driving risk-off / oil-spike events
_GEO_BULL_KW: list[str] = [
    "iran war", "oil spike", "energy surge", "conflict escalat",
    "sanctions", "military strike", "airstrike", "oil embargo",
]
_GEO_BEAR_KW: list[str] = [
    "ceasefire", "de-escalat", "peace talks", "sanctions lifted",
    "supply normaliz", "oil surplus",
]
# How a risk-off / oil-shock geo event shifts each currency (positive = bullish)
_GEO_CCY_IMPACT: dict[str, float] = {
    "USD":  0.8,   # safe-haven demand
    "CHF":  1.5,   # strongest safe-haven
    "JPY":  1.5,   # strong safe-haven
    "CAD":  1.2,   # oil exporter benefits
    "EUR": -0.5,
    "GBP": -0.3,
    "AUD": -0.8,   # risk-correlated commodity
    "NZD": -1.0,
}

# Reference interest rates used for Layer 2 rate-differential scoring
# Update when a central bank makes a policy change.
_BASE_RATES: dict[str, float] = {
    "USD": 4.50,   # Fed funds rate
    "EUR": 2.40,   # ECB deposit rate
    "GBP": 4.25,   # BoE bank rate
    "JPY": 0.10,   # BoJ policy rate
    "AUD": 4.10,   # RBA cash rate
    "CAD": 2.75,   # BoC overnight rate
    "CHF": 0.25,   # SNB policy rate
    "NZD": 3.25,   # RBNZ OCR
}
# Layer 2 — medium-term fundamental outlook queries (separate from Layer 3 daily news)
_CY = datetime.today().year
_NY = _CY + 1
_FUNDAMENTAL_QUERIES: dict[str, str] = {
    "USD": f"US dollar fundamental outlook Federal Reserve rate path higher longer {_CY} {_NY}",
    "EUR": f"Euro fundamental outlook ECB rate cuts eurozone recession growth {_CY} {_NY}",
    "GBP": f"British pound fundamental Bank of England rate path UK stagflation {_CY} {_NY}",
    "JPY": f"Japanese yen fundamental BOJ policy ultra-loose yen carry trade {_CY} {_NY}",
    "AUD": f"Australian dollar fundamental RBA commodity China risk sentiment {_CY} {_NY}",
    "CAD": f"Canadian dollar fundamental Bank of Canada oil prices CAD outlook {_CY} {_NY}",
    "CHF": f"Swiss franc fundamental SNB policy safe haven demand franc {_CY} {_NY}",
    "NZD": f"New Zealand dollar fundamental RBNZ rate cuts dairy commodity {_CY} {_NY}",
}
# Structural / medium-term bullish keywords (CB stance, rate advantage, macro quality)
_FUND_BULL_KW: list[tuple[str, float]] = [
    ("higher for longer",         2.5), ("rate advantage",           2.0),
    ("hawkish",                   2.0), ("restrictive policy",       2.0),
    ("tightening cycle",          2.0), ("rate hike",                2.0),
    ("current account surplus",   2.0), ("safe haven",               1.5),
    ("strong growth outlook",     2.0), ("outperforming",            1.5),
    ("reserve currency",          1.5), ("carry trade",              1.5),
    ("robust economy",            1.5), ("fiscal surplus",           1.5),
    ("positive real rates",       2.0), ("commodity boom",           1.5),
]
# Structural / medium-term bearish keywords
_FUND_BEAR_KW: list[tuple[str, float]] = [
    ("easing cycle",             -2.5), ("rate cut path",            -2.5),
    ("dovish",                   -2.0), ("ultra-loose",              -2.0),
    ("negative rates",           -2.0), ("yen carry unwind",         -2.0),
    ("recession risk",           -2.0), ("stagflation",              -2.0),
    ("current account deficit",  -1.5), ("currency weakness",        -1.5),
    ("fiscal deficit",           -1.0), ("trade war",                -1.5),
    ("losing reserve",           -2.0), ("weak growth",              -1.5),
    ("rate cuts expected",       -2.0), ("accommodative",            -1.5),
]
TTL_NEWS_CTX    = 600   # 10 min — Layer 3 news cache TTL
TTL_FUNDAMENTAL = 1800  # 30 min — Layer 2 fundamental cache TTL

# ── 4-Dimensional bias engine ─────────────────────────────────────────────────
# D3 — Current central bank action pricing (update when policy changes)
_D3_BASE: dict[str, float] = {
    # Reflects the NEXT expected CB action (positive = hike, negative = cut)
    # Scale: +3.0 = aggressive hike cycle,  -3.0 = aggressive cut cycle
    "USD":  0.5,   # Fed on hold at 4.50%; no cuts in 2026, slight re-hike risk Q3 2027
    "JPY":  1.5,   # BOJ actively hiking; next move +25bp July 2026, ~70% priced
    "AUD":  0.3,   # RBA cut to 3.85%; pause now, but inflation sticky — further cut risk minor
    "GBP": -0.8,   # BOE cutting cycle: 4.25% → 4.00% expected Jun, weak manufacturing
    "CAD": -1.0,   # BOC in clear cut cycle: 2.75% → 2.50% Jun; unemployment rising
    "NZD": -1.2,   # RBNZ cutting: 3.50% → 3.25% expected, weak consumer + CA deficit
    "EUR": -1.5,   # ECB cutting cycle: 2.25% → 2.00% expected Jun; CPI below target
    "CHF": -0.5,   # SNB at 0.00%; hold for now, negative real rates possible
}
# D3 web-search queries — detect same-day CB repricing
_D3_CB_QUERIES: dict[str, str] = {
    "USD": f"Federal Reserve next rate decision hike cut hold {_CY}",
    "EUR": f"ECB European Central Bank next rate cut decision {_CY}",
    "GBP": f"Bank of England BOE next rate cut decision {_CY}",
    "JPY": f"Bank of Japan BOJ next rate hike {_CY}",
    "AUD": f"RBA Reserve Bank Australia next rate decision {_CY}",
    "CAD": f"Bank of Canada BOC next rate cut decision {_CY}",
    "CHF": f"Swiss National Bank SNB next rate decision {_CY}",
    "NZD": f"RBNZ Reserve Bank New Zealand next rate cut decision {_CY}",
}
# D4 — Structural macro baseline: rate differential + CA balance + inflation regime
# NO geopolitical component — geo context reserved for Module 4.
# Rate advantage vs G8 average (~2.7%) is the primary FX driver.
_D4_STRUCTURAL: dict[str, float] = {
    "USD":  1.2,   # highest G8 rate (4.50%), +1.8% above avg, solid GDP, reserve currency premium
    "GBP":  0.6,   # 4.25%, above avg, but stagflation risk and weak manufacturing drag
    "AUD":  0.5,   # 3.85%, commodity exporter, elevated CPI supports rate carry
    "JPY": -0.8,   # 0.50% — far below G8 average, carry trade unwind risk
    "CAD":  0.0,   # 2.75%, near avg, oil CA offsets rising unemployment
    "NZD": -0.2,   # 3.50% but small open economy, CA deficit, high sensitivity to risk-off
    "EUR": -0.5,   # 2.25%, below avg and cutting; trade surplus is structural positive
    "CHF": -1.0,   # 0.00%, very low rate, safe-haven demand offsets rate disadvantage
}
# D4 live news queries — rate & macro developments (no geo)
_D4_NEWS_QUERIES: dict[str, str] = {
    "USD": "Federal Reserve interest rate inflation GDP economic outlook hawkish dovish",
    "EUR": "ECB interest rate eurozone inflation GDP economic outlook hawkish dovish",
    "GBP": "Bank of England interest rate UK inflation GDP economic outlook hawkish dovish",
    "JPY": "Bank of Japan interest rate Japan inflation GDP economic outlook hawkish dovish",
    "AUD": "RBA interest rate Australia inflation GDP economic outlook hawkish dovish",
    "CAD": "Bank of Canada interest rate inflation GDP economic outlook hawkish dovish",
    "CHF": "SNB interest rate Switzerland inflation GDP economic outlook hawkish dovish",
    "NZD": "RBNZ interest rate New Zealand inflation GDP economic outlook hawkish dovish",
}
# CB hawkish / dovish keyword detection used in D3 + D4 web scans
_CB_HAWK_KW: tuple[str, ...] = (
    "rate hike", "hikes rates", "raises rates", "hawkish", "tightening",
    "higher for longer", "upside risk", "inflation above target",
    "beats forecast", "strong jobs", "rate increase",
)
_CB_DOVE_KW: tuple[str, ...] = (
    "rate cut", "cuts rates", "dovish", "easing", "pause",
    "inflation easing", "weaker than expected", "slowing economy",
    "possible cut", "rate reduction", "concern about growth",
)

# ╔══════════════════════════════════════════════════════════════════════════════
# ║  STATIC FALLBACK DATA  (May 2026 — displayed when live fetch fails)
# ╚══════════════════════════════════════════════════════════════════════════════
STATIC_INDICATORS: dict[str, dict[str, dict]] = {
    # ── USD  target score ≈ +5  (SLIGHT BULLISH — high rates, solid growth, wage inflation)
    "USD": {
        "CPI m/m":            {"actual": 0.4,    "previous": 0.3,    "forecast": 0.3,    "date": "2026-05-13", "impact": "High"},
        "Interest Rate":      {"actual": 4.50,   "previous": 4.25,   "forecast": 4.50,   "date": "2026-05-07", "impact": "High"},
        "GDP Growth":         {"actual": 2.8,    "previous": 2.4,    "forecast": 2.6,    "date": "2026-04-30", "impact": "High"},
        "Unemployment Rate":  {"actual": 4.0,    "previous": 4.2,    "forecast": 4.0,    "date": "2026-05-02", "impact": "High"},
        "Manufacturing PMI":  {"actual": 49.8,   "previous": 49.3,   "forecast": 50.0,   "date": "2026-05-01", "impact": "Medium"},
        "Services PMI":       {"actual": 51.2,   "previous": 51.7,   "forecast": 51.5,   "date": "2026-05-05", "impact": "Medium"},
        "Trade Balance":      {"actual": -61.1,  "previous": -64.5,  "forecast": -63.0,  "date": "2026-05-06", "impact": "Medium"},
        "Retail Sales":       {"actual": 0.1,    "previous": -0.2,   "forecast": 0.3,    "date": "2026-05-15", "impact": "High"},
        "Current Account":    {"actual": -3.2,   "previous": -3.5,   "forecast": -3.3,   "date": "2026-03-20", "impact": "Medium"},
        "Wage Growth":        {"actual": 4.5,    "previous": 4.1,    "forecast": 4.0,    "date": "2026-05-02", "impact": "High"},
        "PPI":                {"actual": 3.8,    "previous": 3.4,    "forecast": 3.5,    "date": "2026-05-14", "impact": "Medium"},
        "Consumer Confidence":{"actual": 82.0,   "previous": 77.8,   "forecast": 78.0,   "date": "2026-05-16", "impact": "Medium"},
        "Government Debt":    {"actual": 124.0,  "previous": 121.3,  "forecast": 122.0,  "date": "2026-04-01", "impact": "Low"},
        "Budget Balance":     {"actual": -5.8,   "previous": -6.1,   "forecast": -6.0,   "date": "2026-04-15", "impact": "Low"},
        "Building Permits":   {"actual": 1482.0, "previous": 1465.0, "forecast": 1460.0, "date": "2026-05-16", "impact": "Medium"},
        "Business Confidence":{"actual": 52.3,   "previous": 50.1,   "forecast": 50.5,   "date": "2026-05-15", "impact": "Low"},
        "Core CPI":           {"actual": 0.3,    "previous": 0.4,    "forecast": 0.3,    "date": "2026-05-13", "impact": "High"},
        "Employment Change":  {"actual": 177.0,  "previous": 142.0,  "forecast": 155.0,  "date": "2026-05-02", "impact": "High"},
        "Industrial Production":{"actual": 0.3,  "previous": 0.1,    "forecast": 0.2,    "date": "2026-05-15", "impact": "Medium"},
        "M2 Money Supply":    {"actual": 3.8,    "previous": 3.5,    "forecast": 3.6,    "date": "2026-05-07", "impact": "Low"},
    },
    # ── EUR  target score ≈ -2  (SLIGHT BEARISH — cutting cycle, soft PMI, below-target CPI)
    "EUR": {
        "CPI m/m":            {"actual": 0.2,    "previous": 0.2,    "forecast": 0.2,    "date": "2026-05-06", "impact": "High"},
        "Interest Rate":      {"actual": 2.25,   "previous": 2.50,   "forecast": 2.25,   "date": "2026-04-17", "impact": "High"},
        "GDP Growth":         {"actual": 0.8,    "previous": 0.6,    "forecast": 0.9,    "date": "2026-04-30", "impact": "High"},
        "Unemployment Rate":  {"actual": 6.2,    "previous": 6.3,    "forecast": 6.2,    "date": "2026-04-30", "impact": "Medium"},
        "Manufacturing PMI":  {"actual": 48.1,   "previous": 47.3,   "forecast": 47.9,   "date": "2026-05-02", "impact": "Medium"},
        "Services PMI":       {"actual": 50.4,   "previous": 51.0,   "forecast": 50.5,   "date": "2026-05-05", "impact": "Medium"},
        "Trade Balance":      {"actual": 8.5,    "previous": 6.8,    "forecast": 7.5,    "date": "2026-04-16", "impact": "Medium"},
        "Retail Sales":       {"actual": -0.1,   "previous": 0.3,    "forecast": 0.2,    "date": "2026-05-06", "impact": "Medium"},
        "Current Account":    {"actual": 0.8,    "previous": 0.7,    "forecast": 0.9,    "date": "2026-03-19", "impact": "Medium"},
        "Wage Growth":        {"actual": 3.0,    "previous": 3.3,    "forecast": 3.2,    "date": "2026-05-09", "impact": "Medium"},
        "PPI":                {"actual": 1.2,    "previous": 1.8,    "forecast": 1.6,    "date": "2026-05-08", "impact": "Medium"},
        "Consumer Confidence":{"actual": -14.1,  "previous": -12.3,  "forecast": -12.0,  "date": "2026-05-20", "impact": "Medium"},
        "Government Debt":    {"actual": 91.0,   "previous": 90.2,   "forecast": 90.5,   "date": "2026-04-01", "impact": "Low"},
        "Budget Balance":     {"actual": -3.2,   "previous": -3.5,   "forecast": -3.3,   "date": "2026-04-01", "impact": "Low"},
        "Building Permits":   {"actual": 92.3,   "previous": 95.1,   "forecast": 94.0,   "date": "2026-05-12", "impact": "Low"},
        "Business Confidence":{"actual": 98.5,   "previous": 99.2,   "forecast": 99.5,   "date": "2026-05-20", "impact": "Low"},
        "Core CPI":           {"actual": 0.2,    "previous": 0.2,    "forecast": 0.2,    "date": "2026-05-06", "impact": "High"},
        "Employment Change":  {"actual": 140.0,  "previous": 120.0,  "forecast": 130.0,  "date": "2026-04-30", "impact": "Medium"},
        "Industrial Production":{"actual": -0.2, "previous": 0.1,    "forecast": 0.2,    "date": "2026-04-14", "impact": "Medium"},
        "M2 Money Supply":    {"actual": 2.1,    "previous": 1.9,    "forecast": 2.0,    "date": "2026-04-25", "impact": "Low"},
    },
    # ── GBP  target score ≈ -4  (SLIGHT BEARISH — stagflation, cutting, weak manufacturing)
    "GBP": {
        "CPI m/m":            {"actual": 0.3,    "previous": 0.4,    "forecast": 0.3,    "date": "2026-05-21", "impact": "High"},
        "Interest Rate":      {"actual": 4.25,   "previous": 4.50,   "forecast": 4.25,   "date": "2026-05-08", "impact": "High"},
        "GDP Growth":         {"actual": 1.4,    "previous": 1.1,    "forecast": 1.2,    "date": "2026-05-13", "impact": "High"},
        "Unemployment Rate":  {"actual": 4.7,    "previous": 4.5,    "forecast": 4.5,    "date": "2026-05-13", "impact": "Medium"},
        "Manufacturing PMI":  {"actual": 46.1,   "previous": 44.9,   "forecast": 45.5,   "date": "2026-05-01", "impact": "Medium"},
        "Services PMI":       {"actual": 52.3,   "previous": 53.0,   "forecast": 52.8,   "date": "2026-05-05", "impact": "Medium"},
        "Trade Balance":      {"actual": -5.1,   "previous": -3.7,   "forecast": -4.5,   "date": "2026-05-09", "impact": "Medium"},
        "Retail Sales":       {"actual": -0.3,   "previous": 0.4,    "forecast": 0.2,    "date": "2026-05-23", "impact": "Medium"},
        "Current Account":    {"actual": -3.8,   "previous": -3.5,   "forecast": -3.5,   "date": "2026-03-28", "impact": "Medium"},
        "Wage Growth":        {"actual": 3.5,    "previous": 3.8,    "forecast": 3.7,    "date": "2026-05-13", "impact": "High"},
        "PPI":                {"actual": 2.5,    "previous": 2.3,    "forecast": 2.4,    "date": "2026-05-14", "impact": "Medium"},
        "Consumer Confidence":{"actual": -22.0,  "previous": -20.0,  "forecast": -18.0,  "date": "2026-05-29", "impact": "Medium"},
        "Government Debt":    {"actual": 101.0,  "previous": 98.7,   "forecast": 99.5,   "date": "2026-04-22", "impact": "Low"},
        "Budget Balance":     {"actual": -4.3,   "previous": -4.8,   "forecast": -4.5,   "date": "2026-04-22", "impact": "Low"},
        "Building Permits":   {"actual": 178.0,  "previous": 185.0,  "forecast": 182.0,  "date": "2026-05-12", "impact": "Low"},
        "Business Confidence":{"actual": 48.2,   "previous": 49.1,   "forecast": 49.5,   "date": "2026-05-19", "impact": "Low"},
        "Core CPI":           {"actual": 0.3,    "previous": 0.3,    "forecast": 0.3,    "date": "2026-05-21", "impact": "High"},
        "Employment Change":  {"actual": -5.0,   "previous": 18.0,   "forecast": 10.0,   "date": "2026-05-13", "impact": "Medium"},
        "Industrial Production":{"actual": -0.5, "previous": 0.2,    "forecast": 0.1,    "date": "2026-05-09", "impact": "Medium"},
        "M2 Money Supply":    {"actual": 1.8,    "previous": 1.5,    "forecast": 1.7,    "date": "2026-04-28", "impact": "Low"},
    },
    # ── JPY  target score ≈ 0–1  (NEUTRAL — pause after hike, trade deficit, CA surplus)
    "JPY": {
        "CPI m/m":            {"actual": 0.3,    "previous": 0.3,    "forecast": 0.3,    "date": "2026-04-25", "impact": "High"},
        "Interest Rate":      {"actual": 0.50,   "previous": 0.50,   "forecast": 0.50,   "date": "2026-05-01", "impact": "High"},
        "GDP Growth":         {"actual": -0.1,   "previous": 0.4,    "forecast": 0.2,    "date": "2026-05-15", "impact": "High"},
        "Unemployment Rate":  {"actual": 2.5,    "previous": 2.4,    "forecast": 2.5,    "date": "2026-05-02", "impact": "Low"},
        "Manufacturing PMI":  {"actual": 48.4,   "previous": 48.0,   "forecast": 48.5,   "date": "2026-05-01", "impact": "Low"},
        "Services PMI":       {"actual": 52.1,   "previous": 50.3,   "forecast": 51.0,   "date": "2026-05-09", "impact": "Low"},
        "Trade Balance":      {"actual": -0.8,   "previous": -1.2,   "forecast": -0.5,   "date": "2026-05-21", "impact": "Medium"},
        "Retail Sales":       {"actual": 1.2,    "previous": 0.8,    "forecast": 0.9,    "date": "2026-05-02", "impact": "Medium"},
        "Current Account":    {"actual": 1.5,    "previous": 1.8,    "forecast": 1.6,    "date": "2026-03-10", "impact": "Medium"},
        "Wage Growth":        {"actual": 3.2,    "previous": 2.8,    "forecast": 2.9,    "date": "2026-05-08", "impact": "Medium"},
        "PPI":                {"actual": 3.1,    "previous": 2.5,    "forecast": 2.8,    "date": "2026-05-14", "impact": "Low"},
        "Consumer Confidence":{"actual": 36.4,   "previous": 34.9,   "forecast": 36.0,   "date": "2026-04-28", "impact": "Low"},
        "Government Debt":    {"actual": 255.0,  "previous": 252.0,  "forecast": 253.0,  "date": "2026-04-01", "impact": "Low"},
        "Budget Balance":     {"actual": -5.5,   "previous": -5.8,   "forecast": -5.6,   "date": "2026-04-01", "impact": "Low"},
        "Building Permits":   {"actual": 73.5,   "previous": 71.2,   "forecast": 72.0,   "date": "2026-04-30", "impact": "Low"},
        "Business Confidence":{"actual": 13.0,   "previous": 11.0,   "forecast": 11.0,   "date": "2026-04-01", "impact": "Medium"},
        "Core CPI":           {"actual": 0.2,    "previous": 0.2,    "forecast": 0.2,    "date": "2026-04-25", "impact": "High"},
        "Employment Change":  {"actual": 18.0,   "previous": 22.0,   "forecast": 20.0,   "date": "2026-05-02", "impact": "Low"},
        "Industrial Production":{"actual": 0.2,  "previous": -0.4,   "forecast": 0.3,    "date": "2026-04-30", "impact": "Medium"},
        "M2 Money Supply":    {"actual": 1.2,    "previous": 1.0,    "forecast": 1.1,    "date": "2026-04-28", "impact": "Low"},
    },
    # ── AUD  target score ≈ +3  (SLIGHT BULLISH — trade surplus, rate cycle bottoming)
    "AUD": {
        "CPI m/m":            {"actual": 0.3,    "previous": 0.3,    "forecast": 0.3,    "date": "2026-04-30", "impact": "High"},
        "Interest Rate":      {"actual": 3.85,   "previous": 4.10,   "forecast": 3.85,   "date": "2026-05-06", "impact": "High"},
        "GDP Growth":         {"actual": 1.3,    "previous": 1.5,    "forecast": 1.4,    "date": "2026-06-04", "impact": "High"},
        "Unemployment Rate":  {"actual": 4.2,    "previous": 4.1,    "forecast": 4.2,    "date": "2026-05-15", "impact": "High"},
        "Manufacturing PMI":  {"actual": 51.7,   "previous": 50.3,   "forecast": 51.0,   "date": "2026-05-01", "impact": "Low"},
        "Services PMI":       {"actual": 51.0,   "previous": 51.6,   "forecast": 51.5,   "date": "2026-05-05", "impact": "Low"},
        "Trade Balance":      {"actual": 5.1,    "previous": 4.7,    "forecast": 5.3,    "date": "2026-05-05", "impact": "Medium"},
        "Retail Sales":       {"actual": 0.3,    "previous": 0.2,    "forecast": 0.4,    "date": "2026-05-28", "impact": "Medium"},
        "Current Account":    {"actual": -2.5,   "previous": -2.8,   "forecast": -2.6,   "date": "2026-03-04", "impact": "Medium"},
        "Wage Growth":        {"actual": 3.6,    "previous": 3.3,    "forecast": 3.4,    "date": "2026-05-21", "impact": "High"},
        "PPI":                {"actual": 2.8,    "previous": 2.5,    "forecast": 2.7,    "date": "2026-04-29", "impact": "Low"},
        "Consumer Confidence":{"actual": 102.0,  "previous": 99.0,   "forecast": 99.5,   "date": "2026-05-13", "impact": "Medium"},
        "Government Debt":    {"actual": 52.0,   "previous": 49.5,   "forecast": 50.0,   "date": "2026-04-01", "impact": "Low"},
        "Budget Balance":     {"actual": -0.8,   "previous": -1.2,   "forecast": -1.0,   "date": "2026-04-01", "impact": "Low"},
        "Building Permits":   {"actual": 15.2,   "previous": 14.8,   "forecast": 14.9,   "date": "2026-05-07", "impact": "Low"},
        "Business Confidence":{"actual": 5.0,    "previous": 3.0,    "forecast": 3.5,    "date": "2026-05-12", "impact": "Low"},
        "Core CPI":           {"actual": 0.2,    "previous": 0.3,    "forecast": 0.2,    "date": "2026-04-30", "impact": "High"},
        "Employment Change":  {"actual": 38.0,   "previous": 52.0,   "forecast": 25.0,   "date": "2026-05-15", "impact": "High"},
        "Industrial Production":{"actual": 0.4,  "previous": 0.2,    "forecast": 0.3,    "date": "2026-05-13", "impact": "Low"},
        "M2 Money Supply":    {"actual": 5.2,    "previous": 4.8,    "forecast": 5.0,    "date": "2026-04-28", "impact": "Low"},
    },
    # ── CAD  target score ≈ -4  (SLIGHT BEARISH — cutting, rising unemployment, weak PMI)
    "CAD": {
        "CPI m/m":            {"actual": 0.2,    "previous": 0.2,    "forecast": 0.2,    "date": "2026-05-20", "impact": "High"},
        "Interest Rate":      {"actual": 2.75,   "previous": 3.00,   "forecast": 2.75,   "date": "2026-04-16", "impact": "High"},
        "GDP Growth":         {"actual": 1.5,    "previous": 1.6,    "forecast": 1.6,    "date": "2026-05-29", "impact": "High"},
        "Unemployment Rate":  {"actual": 6.9,    "previous": 6.7,    "forecast": 6.8,    "date": "2026-05-09", "impact": "High"},
        "Manufacturing PMI":  {"actual": 47.8,   "previous": 46.3,   "forecast": 47.0,   "date": "2026-05-01", "impact": "Low"},
        "Services PMI":       {"actual": 49.3,   "previous": 49.7,   "forecast": 49.5,   "date": "2026-05-05", "impact": "Low"},
        "Trade Balance":      {"actual": 0.7,    "previous": -0.4,   "forecast": 0.3,    "date": "2026-05-08", "impact": "Medium"},
        "Retail Sales":       {"actual": 0.5,    "previous": -0.4,   "forecast": 0.2,    "date": "2026-05-22", "impact": "Medium"},
        "Current Account":    {"actual": -2.5,   "previous": -2.2,   "forecast": -2.3,   "date": "2026-03-27", "impact": "Medium"},
        "Wage Growth":        {"actual": 2.8,    "previous": 3.1,    "forecast": 3.0,    "date": "2026-05-09", "impact": "Medium"},
        "PPI":                {"actual": 1.9,    "previous": 2.3,    "forecast": 2.1,    "date": "2026-05-14", "impact": "Low"},
        "Consumer Confidence":{"actual": 55.0,   "previous": 62.0,   "forecast": 60.0,   "date": "2026-05-08", "impact": "Medium"},
        "Government Debt":    {"actual": 107.0,  "previous": 105.3,  "forecast": 106.0,  "date": "2026-04-01", "impact": "Low"},
        "Budget Balance":     {"actual": -1.5,   "previous": -1.8,   "forecast": -1.6,   "date": "2026-04-01", "impact": "Low"},
        "Building Permits":   {"actual": 238.0,  "previous": 253.0,  "forecast": 248.0,  "date": "2026-05-14", "impact": "Medium"},
        "Business Confidence":{"actual": -15.0,  "previous": -12.0,  "forecast": -11.0,  "date": "2026-05-06", "impact": "Low"},
        "Core CPI":           {"actual": 0.2,    "previous": 0.2,    "forecast": 0.2,    "date": "2026-05-20", "impact": "High"},
        "Employment Change":  {"actual": -33.0,  "previous": 32.0,   "forecast": 20.0,   "date": "2026-05-09", "impact": "High"},
        "Industrial Production":{"actual": -0.3, "previous": 0.1,    "forecast": 0.2,    "date": "2026-05-14", "impact": "Medium"},
        "M2 Money Supply":    {"actual": 2.6,    "previous": 2.4,    "forecast": 2.5,    "date": "2026-05-07", "impact": "Low"},
    },
    # ── CHF  target score ≈ +1–2  (NEUTRAL/SLIGHT BULLISH — deflation risk, but large surpluses)
    "CHF": {
        "CPI m/m":            {"actual": 0.1,    "previous": 0.1,    "forecast": 0.1,    "date": "2026-05-05", "impact": "Medium"},
        "Interest Rate":      {"actual": 0.00,   "previous": 0.00,   "forecast": 0.00,   "date": "2026-03-20", "impact": "High"},
        "GDP Growth":         {"actual": 0.5,    "previous": 0.2,    "forecast": 0.4,    "date": "2026-05-28", "impact": "Medium"},
        "Unemployment Rate":  {"actual": 2.8,    "previous": 2.9,    "forecast": 3.0,    "date": "2026-05-07", "impact": "Low"},
        "Manufacturing PMI":  {"actual": 54.5,   "previous": 53.3,   "forecast": 49.0,   "date": "2026-05-01", "impact": "Low"},
        "Services PMI":       {"actual": 52.4,   "previous": 51.6,   "forecast": 52.0,   "date": "2026-05-05", "impact": "Low"},
        "Trade Balance":      {"actual": 4.8,    "previous": 4.2,    "forecast": 4.5,    "date": "2026-05-21", "impact": "Low"},
        "Retail Sales":       {"actual": 0.8,    "previous": 0.4,    "forecast": 0.5,    "date": "2026-04-09", "impact": "Low"},
        "Current Account":    {"actual": 8.5,    "previous": 8.2,    "forecast": 8.3,    "date": "2026-03-16", "impact": "Low"},
        "Wage Growth":        {"actual": 1.5,    "previous": 1.8,    "forecast": 1.7,    "date": "2026-03-26", "impact": "Low"},
        "PPI":                {"actual": -0.2,   "previous": 0.3,    "forecast": 0.2,    "date": "2026-05-14", "impact": "Low"},
        "Consumer Confidence":{"actual": -4.8,   "previous": -4.2,   "forecast": -4.0,   "date": "2026-04-28", "impact": "Low"},
        "Government Debt":    {"actual": 38.0,   "previous": 37.5,   "forecast": 38.0,   "date": "2026-04-01", "impact": "Low"},
        "Budget Balance":     {"actual": 0.3,    "previous": -0.1,   "forecast": 0.0,    "date": "2026-04-01", "impact": "Low"},
        "Building Permits":   {"actual": 2.8,    "previous": 2.9,    "forecast": 3.0,    "date": "2026-04-29", "impact": "Low"},
        "Business Confidence":{"actual": -0.3,   "previous": -0.8,   "forecast": -0.5,   "date": "2026-04-28", "impact": "Low"},
        "Core CPI":           {"actual": 0.1,    "previous": 0.1,    "forecast": 0.1,    "date": "2026-05-05", "impact": "Medium"},
        "Employment Change":  {"actual": 4.0,    "previous": 6.0,    "forecast": 5.0,    "date": "2026-03-10", "impact": "Low"},
        "Industrial Production":{"actual": 0.6,  "previous": 0.3,    "forecast": 0.4,    "date": "2026-05-12", "impact": "Low"},
        "M2 Money Supply":    {"actual": 1.5,    "previous": 1.2,    "forecast": 1.3,    "date": "2026-04-28", "impact": "Low"},
    },
    # ── NZD  target score ≈ -5  (SLIGHT BEARISH — cutting, CA deficit, weak consumer)
    "NZD": {
        "CPI m/m":            {"actual": 0.2,    "previous": 0.2,    "forecast": 0.2,    "date": "2026-04-17", "impact": "High"},
        "Interest Rate":      {"actual": 3.50,   "previous": 3.75,   "forecast": 3.50,   "date": "2026-04-09", "impact": "High"},
        "GDP Growth":         {"actual": 0.7,    "previous": 0.6,    "forecast": 0.8,    "date": "2026-06-18", "impact": "High"},
        "Unemployment Rate":  {"actual": 5.1,    "previous": 5.0,    "forecast": 5.0,    "date": "2026-05-05", "impact": "High"},
        "Manufacturing PMI":  {"actual": 51.9,   "previous": 52.6,   "forecast": 52.0,   "date": "2026-05-15", "impact": "Low"},
        "Services PMI":       {"actual": 49.8,   "previous": 50.4,   "forecast": 50.5,   "date": "2026-05-13", "impact": "Low"},
        "Trade Balance":      {"actual": -0.1,   "previous": -0.4,   "forecast": 0.0,    "date": "2026-05-26", "impact": "Medium"},
        "Retail Sales":       {"actual": 0.2,    "previous": -0.1,   "forecast": 0.3,    "date": "2026-05-20", "impact": "Medium"},
        "Current Account":    {"actual": -3.5,   "previous": -3.2,   "forecast": -3.3,   "date": "2026-03-19", "impact": "Medium"},
        "Wage Growth":        {"actual": 3.0,    "previous": 3.4,    "forecast": 3.3,    "date": "2026-05-06", "impact": "Medium"},
        "PPI":                {"actual": 1.8,    "previous": 2.2,    "forecast": 2.0,    "date": "2026-04-29", "impact": "Low"},
        "Consumer Confidence":{"actual": 93.0,   "previous": 97.0,   "forecast": 97.0,   "date": "2026-04-24", "impact": "Medium"},
        "Government Debt":    {"actual": 48.0,   "previous": 46.5,   "forecast": 47.0,   "date": "2026-04-01", "impact": "Low"},
        "Budget Balance":     {"actual": -3.1,   "previous": -2.8,   "forecast": -2.9,   "date": "2026-04-01", "impact": "Low"},
        "Building Permits":   {"actual": 2.1,    "previous": 2.3,    "forecast": 2.3,    "date": "2026-04-30", "impact": "Low"},
        "Business Confidence":{"actual": 14.5,   "previous": 18.3,   "forecast": 17.0,   "date": "2026-04-23", "impact": "Low"},
        "Core CPI":           {"actual": 0.2,    "previous": 0.2,    "forecast": 0.2,    "date": "2026-04-17", "impact": "High"},
        "Employment Change":  {"actual": -4.0,   "previous": 8.0,    "forecast": 5.0,    "date": "2026-05-05", "impact": "High"},
        "Industrial Production":{"actual": -0.1, "previous": 0.3,    "forecast": 0.2,    "date": "2026-04-28", "impact": "Low"},
        "M2 Money Supply":    {"actual": 2.8,    "previous": 2.5,    "forecast": 2.7,    "date": "2026-04-14", "impact": "Low"},
    },
}


# ╔══════════════════════════════════════════════════════════════════════════════
# ║  6-MONTH STATIC HISTORY  (Dec 2025 → May 2026, index 0=oldest, 5=latest)
# ║  Used for cross-currency G8 relative scoring.
# ║  Latest value (index 5) matches STATIC_INDICATORS "actual".
# ╚══════════════════════════════════════════════════════════════════════════════
STATIC_HISTORY: dict[str, dict[str, list[float]]] = {
    "USD": {
        "CPI m/m":          [0.4, 0.5, 0.2, 0.1, 0.3, 0.4],
        "Interest Rate":    [4.25, 4.25, 4.50, 4.50, 4.50, 4.50],
        "GDP Growth":       [2.4, 2.4, 2.8, 2.8, 2.8, 2.8],
        "Unemployment Rate":[4.2, 4.1, 4.0, 4.1, 4.0, 4.0],
        "Manufacturing PMI":[49.7, 51.2, 52.7, 49.0, 50.2, 49.8],
        "Services PMI":     [56.1, 52.9, 51.0, 54.4, 50.8, 51.2],
        "Retail Sales":     [0.4, -0.9, 0.2, 1.4, -0.2, 0.1],
        "Wage Growth":      [4.1, 4.1, 4.0, 4.0, 4.1, 4.5],
        "Trade Balance":    [-78.9, -131.4, -122.7, -140.5, -64.5, -61.1],
        "Core CPI":         [0.3, 0.4, 0.4, 0.1, 0.3, 0.3],
        "Employment Change":[227, 256, 117, 228, 142, 177],
        "Industrial Production":[-0.1, 0.5, -0.8, -0.3, 0.1, 0.3],
        "M2 Money Supply":  [3.5, 3.5, 3.6, 3.6, 3.8, 3.8],
        "Consumer Confidence":[110.7, 104.1, 98.3, 92.9, 85.7, 82.0],
        "Government Debt":  [122.0, 122.0, 123.0, 123.0, 124.0, 124.0],
        "PPI":              [0.3, 0.5, 0.0, -0.4, -0.5, 0.2],
    },
    "EUR": {
        "CPI m/m":          [0.3, 0.2, -0.1, 0.0, 0.2, 0.2],
        "Interest Rate":    [3.00, 2.75, 2.75, 2.50, 2.50, 2.25],
        "GDP Growth":       [1.2, 1.2, 1.7, 1.7, 1.7, 1.7],
        "Unemployment Rate":[6.3, 6.2, 6.2, 6.1, 6.1, 6.2],
        "Manufacturing PMI":[45.1, 46.6, 47.6, 48.7, 49.0, 49.4],
        "Services PMI":     [51.6, 51.3, 50.6, 51.0, 50.3, 50.1],
        "Retail Sales":     [-0.1, 0.3, 0.0, 0.3, 0.2, 0.1],
        "Wage Growth":      [4.1, 4.2, 3.8, 3.6, 3.3, 3.1],
        "Trade Balance":    [8.5, 16.3, 10.5, 18.0, 20.5, 8.5],
        "Core CPI":         [0.0, 0.3, 0.1, 0.3, 0.3, 0.2],
        "Employment Change":[300, 280, 220, 180, 190, 210],
        "Industrial Production":[-1.1, 0.5, 0.7, -1.8, 0.5, 0.4],
        "M2 Money Supply":  [3.7, 3.8, 4.0, 3.9, 3.9, 4.1],
        "Consumer Confidence":[-14.2, -14.2, -13.3, -16.5, -16.7, -18.0],
        "Government Debt":  [89.5, 89.5, 90.0, 90.0, 90.8, 91.0],
        "PPI":              [0.0, 0.2, 0.0, 0.1, 0.0, 0.1],
    },
    "GBP": {
        "CPI m/m":          [0.3, 0.3, 0.5, 0.2, 0.4, 0.3],
        "Interest Rate":    [4.75, 4.75, 4.50, 4.50, 4.25, 4.25],
        "GDP Growth":       [0.5, 0.5, 1.1, 1.1, 1.6, 1.6],
        "Unemployment Rate":[4.3, 4.4, 4.4, 4.5, 4.5, 4.5],
        "Manufacturing PMI":[47.3, 48.3, 46.9, 44.9, 45.4, 46.0],
        "Services PMI":     [51.1, 51.0, 51.0, 52.5, 49.9, 50.3],
        "Retail Sales":     [-0.6, 0.0, 1.0, -0.4, 0.4, -0.3],
        "Wage Growth":      [6.0, 5.9, 5.8, 5.6, 5.3, 5.0],
        "Trade Balance":    [-5.1, -3.7, -4.5, -3.8, -3.7, -5.1],
        "Core CPI":         [0.5, 0.6, 0.4, 0.5, 0.3, 0.3],
        "Employment Change":[ 76, 73, 27, -25, -50, -72],
        "Industrial Production":[0.5, 0.7, -0.6, 0.2, 0.8, 0.4],
        "M2 Money Supply":  [3.0, 3.1, 3.2, 3.3, 3.2, 3.1],
        "Consumer Confidence":[-17.0, -22.0, -20.0, -18.0, -23.0, -20.0],
        "Government Debt":  [98.5, 99.0, 99.5, 100.0, 100.5, 101.0],
        "PPI":              [0.2, 0.1, 0.2, -0.1, 0.1, 0.2],
    },
    "JPY": {
        "CPI m/m":          [0.4, 0.4, 0.3, 0.2, 0.3, 0.3],
        "Interest Rate":    [0.25, 0.25, 0.50, 0.50, 0.75, 0.75],
        "GDP Growth":       [1.0, 1.0, 1.2, 1.2, 1.2, 1.2],
        "Unemployment Rate":[2.5, 2.4, 2.5, 2.4, 2.5, 2.4],
        "Manufacturing PMI":[49.5, 50.1, 49.0, 48.4, 48.7, 48.5],
        "Services PMI":     [50.6, 53.0, 53.7, 50.0, 52.4, 52.4],
        "Retail Sales":     [-0.3, 0.0, 1.0, -1.1, 0.0, 0.2],
        "Wage Growth":      [3.5, 3.1, 2.8, 3.5, 3.5, 3.2],
        "Trade Balance":    [-0.8, -1.2, -0.5, -0.3, -1.2, -0.8],
        "Core CPI":         [0.3, 0.4, 0.3, 0.2, 0.2, 0.2],
        "Employment Change":[5, -4, 18, 15, 20, 15],
        "Industrial Production":[-2.3, -1.1, 2.2, 0.2, -1.1, 0.5],
        "M2 Money Supply":  [1.0, 1.1, 1.3, 1.4, 1.4, 1.5],
        "Consumer Confidence":[35.0, 36.2, 35.5, 34.2, 33.8, 34.1],
        "Government Debt":  [254.0, 254.0, 255.0, 255.0, 255.0, 255.0],
        "PPI":              [0.1, 0.4, 0.3, 0.5, 0.4, 0.2],
    },
    "AUD": {
        "CPI m/m":          [0.3, 0.3, 0.2, 0.1, 0.2, 0.3],
        "Interest Rate":    [4.35, 4.35, 4.10, 4.10, 3.85, 3.85],
        "GDP Growth":       [1.0, 1.0, 1.3, 1.3, 1.3, 1.3],
        "Unemployment Rate":[4.1, 4.0, 4.1, 4.2, 4.1, 4.2],
        "Manufacturing PMI":[49.0, 50.3, 49.8, 51.0, 50.3, 51.7],
        "Services PMI":     [50.4, 51.6, 50.8, 51.6, 51.6, 51.0],
        "Retail Sales":     [0.4, 0.3, 0.2, 0.3, 0.2, 0.3],
        "Wage Growth":      [3.3, 3.3, 3.4, 3.4, 3.3, 3.6],
        "Trade Balance":    [4.7, 4.7, 5.1, 4.7, 4.7, 5.1],
        "Core CPI":         [0.2, 0.3, 0.2, 0.2, 0.3, 0.2],
        "Employment Change":[56, 90, 53, 90, 52, 38],
        "Industrial Production":[0.2, 0.2, 0.3, 0.4, 0.2, 0.4],
        "M2 Money Supply":  [4.5, 4.7, 4.8, 5.0, 4.8, 5.2],
        "Consumer Confidence":[97.0, 99.0, 101.0, 100.5, 99.0, 102.0],
        "Government Debt":  [50.5, 50.5, 51.0, 51.5, 51.5, 52.0],
        "PPI":              [0.3, 0.2, 0.2, 0.3, 0.2, 0.3],
    },
    "CAD": {
        "CPI m/m":          [0.3, 0.4, 0.1, 0.1, 0.3, 0.2],
        "Interest Rate":    [3.25, 3.00, 3.00, 2.75, 2.75, 2.75],
        "GDP Growth":       [1.6, 1.6, 1.5, 1.5, 1.5, 1.5],
        "Unemployment Rate":[6.7, 6.8, 6.8, 6.9, 6.9, 6.9],
        "Manufacturing PMI":[51.6, 47.8, 47.9, 46.3, 46.5, 46.8],
        "Services PMI":     [47.5, 47.5, 44.6, 48.6, 41.5, 41.9],
        "Retail Sales":     [0.7, 0.4, -0.4, -0.2, -0.4, 0.1],
        "Wage Growth":      [3.3, 3.3, 3.3, 3.5, 3.4, 3.3],
        "Trade Balance":    [0.7, -0.4, 0.3, -0.8, -0.4, 0.7],
        "Core CPI":         [0.4, 0.3, 0.2, 0.1, 0.2, 0.2],
        "Employment Change":[76, 76, -33, -33, -33, 7],
        "Industrial Production":[-0.4, 0.2, 0.3, -0.3, 0.1, 0.2],
        "M2 Money Supply":  [2.5, 2.6, 2.7, 2.7, 2.8, 2.9],
        "Consumer Confidence":[43.6, 43.7, 52.0, 48.8, 50.9, 47.0],
        "Government Debt":  [106.0, 106.5, 106.5, 107.0, 107.0, 107.0],
        "PPI":              [-0.1, 0.1, 0.2, 0.1, 0.1, 0.0],
    },
    "CHF": {
        "CPI m/m":          [0.1, 0.2, -0.1, 0.0, 0.1, 0.1],
        "Interest Rate":    [0.75, 0.50, 0.25, 0.25, 0.25, 0.25],
        "GDP Growth":       [1.5, 1.5, 1.7, 1.7, 2.0, 2.0],
        "Unemployment Rate":[2.5, 2.6, 2.5, 2.5, 2.6, 2.5],
        "Manufacturing PMI":[48.5, 48.4, 49.0, 48.8, 49.1, 48.9],
        "Services PMI":     [50.3, 49.0, 50.5, 49.4, 49.4, 49.1],
        "Retail Sales":     [-0.3, 0.0, 0.3, 0.1, -0.2, 0.2],
        "Wage Growth":      [1.8, 2.0, 1.8, 2.1, 2.0, 1.8],
        "Trade Balance":    [4.8, 4.2, 4.5, 3.5, 4.2, 4.8],
        "Core CPI":         [0.0, 0.1, 0.0, 0.0, 0.1, 0.1],
        "Employment Change":[5, 4, 3, 2, 3, 4],
        "Industrial Production":[-0.3, 0.1, 0.2, 0.0, 0.1, 0.2],
        "M2 Money Supply":  [-1.0, -0.8, -0.5, -0.3, 0.0, 0.2],
        "Consumer Confidence":[-38.3, -30.1, -24.1, -26.3, -24.8, -20.5],
        "Government Debt":  [37.5, 37.5, 38.0, 38.0, 38.0, 38.0],
        "PPI":              [-0.1, 0.0, 0.1, 0.0, -0.1, 0.0],
    },
    "NZD": {
        "CPI m/m":          [0.2, 0.3, 0.1, 0.1, 0.2, 0.2],
        "Interest Rate":    [4.25, 3.75, 3.75, 3.50, 3.50, 3.50],
        "GDP Growth":       [-0.5, -0.5, 0.6, 0.6, 0.7, 0.7],
        "Unemployment Rate":[5.0, 5.1, 5.2, 5.1, 5.3, 5.2],
        "Manufacturing PMI":[46.2, 50.1, 52.7, 53.9, 54.3, 53.5],
        "Services PMI":     [47.8, 49.1, 50.2, 49.1, 50.1, 49.8],
        "Retail Sales":     [0.0, -0.5, 0.7, 0.4, -0.2, 0.0],
        "Wage Growth":      [3.3, 3.3, 2.9, 2.9, 2.9, 3.0],
        "Trade Balance":    [-0.1, -0.4, 0.0, -0.1, -0.4, -0.1],
        "Core CPI":         [0.1, 0.2, 0.1, 0.1, 0.1, 0.2],
        "Employment Change":[ 8, 5, -3, 2, 1, 3],
        "Industrial Production":[0.0, -0.1, 0.2, 0.1, 0.0, 0.1],
        "M2 Money Supply":  [5.0, 5.2, 5.0, 5.1, 5.0, 5.1],
        "Consumer Confidence":[-65.7, -50.4, -47.3, -47.7, -45.3, -43.5],
        "Government Debt":  [46.5, 46.5, 47.0, 47.5, 47.5, 48.0],
        "PPI":              [0.1, 0.2, 0.1, 0.2, 0.1, 0.2],
    },
}


# ╔══════════════════════════════════════════════════════════════════════════════
# ║  HELPERS
# ╚══════════════════════════════════════════════════════════════════════════════

def _fmt(val) -> str:
    try:
        if val is None:
            return f"<span style='color:{C['muted']};'>—</span>"
        f = float(val)
        if f != f:      # NaN check
            return f"<span style='color:{C['muted']};'>—</span>"
        s = f"{f:,.2f}".rstrip("0").rstrip(".")
        return s or "0"
    except Exception:
        return f"<span style='color:{C['muted']};'>—</span>"


def _parse_numeric(val: str | None) -> float | None:
    if not val or not str(val).strip():
        return None
    s = str(val).strip().replace(",", "").replace("$", "").replace(" ", "")
    mult = 1.0
    if s.endswith("%"):
        s = s[:-1]
    if s.upper().endswith("K"):
        mult = 1_000; s = s[:-1]
    elif s.upper().endswith("M"):
        mult = 1_000_000; s = s[:-1]
    elif s.upper().endswith("B"):
        mult = 1_000_000_000; s = s[:-1]
    try:
        return float(s) * mult
    except ValueError:
        return None


def normalize_indicator(title: str) -> str | None:
    t = title.lower()
    for key, canonical in INDICATOR_MAP:
        if key in t:
            return canonical
    return None


def _section_header(text: str) -> str:
    return (
        f"<div style='font-size:11px;color:{C['muted']};font-family:monospace;"
        f"text-transform:uppercase;letter-spacing:1.5px;margin-bottom:10px;"
        f"margin-top:4px;border-left:2px solid {C['teal']};padding-left:8px;'>"
        f"{text}</div>"
    )


def _empty_state(text: str) -> str:
    return (
        f"<div style='padding:24px;text-align:center;color:{C['muted']};"
        f"font-family:monospace;font-size:12px;background:{C['card']};"
        f"border:1px solid {C['border']};border-radius:10px;'>{text}</div>"
    )


def _impact_pill(impact: str) -> str:
    if str(impact or "").strip().lower() == "low":
        return f"<span style='color:{C['dim']};font-size:10px;'>●</span>"
    cfg = {
        "High":   (C["red"],    "rgba(240,82,98,0.15)"),
        "Medium": (C["yellow"], "rgba(240,180,41,0.15)"),
    }
    color, bg = cfg.get(str(impact).capitalize(), (C["muted"], C["dim"]))
    return (
        f"<span style='background:{bg};color:{color};font-size:9px;"
        f"font-family:monospace;font-weight:700;letter-spacing:1px;"
        f"padding:2px 7px;border-radius:4px;text-transform:uppercase;'>{impact}</span>"
    )


def _source_badge(label: str, is_live: bool) -> str:
    color, bg = (C["green"], "rgba(0,196,140,0.10)") if is_live else (C["yellow"], "rgba(240,180,41,0.10)")
    dot = "●" if is_live else "◎"
    return (
        f"<span style='background:{bg};color:{color};font-size:9px;"
        f"font-family:monospace;font-weight:700;letter-spacing:0.5px;"
        f"padding:2px 8px;border-radius:4px;'>{dot} {label}</span>"
    )


def _time_ago(dt: datetime | None) -> str:
    if dt is None:
        return ""
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    secs = int((now - dt).total_seconds())
    if secs < 60:    return "just now"
    if secs < 3600:  return f"{secs // 60}m ago"
    if secs < 86400: return f"{secs // 3600}h ago"
    return f"{secs // 86400}d ago"


# ╔══════════════════════════════════════════════════════════════════════════════
# ║  OFFICIAL API FETCHES
# ╚══════════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_fred_indicators(api_key: str) -> dict:
    """
    Fetch USD indicators from FRED.
    Returns {indicator: {actual, previous, date, source}} or {} if key missing/invalid.
    Set FRED_API_KEY at the top of this file (free at fred.stlouisfed.org).
    """
    if not api_key or api_key.strip() in ("", "your_key_here", "your_fred_api_key_here"):
        return {}

    result: dict = {}
    for indicator, (series_id, mode) in FRED_SERIES.items():
        limit = 14 if mode == "yoy" else 3
        try:
            r = requests.get(
                FRED_BASE,
                params={"series_id": series_id, "api_key": api_key,
                        "sort_order": "desc", "limit": limit, "file_type": "json"},
                timeout=8,
            )
            if r.status_code != 200:
                continue
            obs = [o for o in r.json().get("observations", []) if o.get("value", ".") != "."]
            if not obs:
                continue

            if mode == "latest":
                actual   = float(obs[0]["value"])
                previous = float(obs[1]["value"]) if len(obs) > 1 else None
                result[indicator] = {"actual": actual, "previous": previous,
                                     "date": obs[0]["date"], "source": "FRED"}

            elif mode == "yoy":
                if len(obs) < 13:
                    continue
                latest  = float(obs[0]["value"])
                yr_ago  = float(obs[12]["value"])
                prev_m  = float(obs[1]["value"])
                prev_yr = float(obs[13]["value"]) if len(obs) > 13 else yr_ago
                result[indicator] = {
                    "actual":   round((latest - yr_ago)  / max(abs(yr_ago),  0.001) * 100, 2),
                    "previous": round((prev_m - prev_yr) / max(abs(prev_yr), 0.001) * 100, 2),
                    "date": obs[0]["date"], "source": "FRED",
                }

            elif mode == "mom":
                if len(obs) < 2:
                    continue
                curr = float(obs[0]["value"]); prev = float(obs[1]["value"])
                prev2 = float(obs[2]["value"]) if len(obs) > 2 else prev
                result[indicator] = {
                    "actual":   round((curr - prev)  / max(abs(prev),  0.001) * 100, 2),
                    "previous": round((prev - prev2) / max(abs(prev2), 0.001) * 100, 2),
                    "date": obs[0]["date"], "source": "FRED",
                }

            elif mode == "mom_abs":
                if len(obs) < 2:
                    continue
                curr = float(obs[0]["value"]); prev_v = float(obs[1]["value"])
                prev2 = float(obs[2]["value"]) if len(obs) > 2 else prev_v
                result[indicator] = {
                    "actual":   round(curr - prev_v, 0),
                    "previous": round(prev_v - prev2, 0),
                    "date": obs[0]["date"], "source": "FRED",
                }

        except Exception:
            continue

    return result


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_ecb_rate() -> dict:
    """
    Fetch ECB deposit facility rate from ECB Data Portal CSV (no API key needed).
    Returns {actual, previous, date, source} or {} on failure.
    """
    try:
        r = requests.get(ECB_RATE_URL, timeout=10,
                         headers={"Accept": "text/csv,application/csv,*/*"})
        if r.status_code != 200:
            return {}
        lines = [l for l in r.text.splitlines() if l.strip()]
        header_idx = next(
            (i for i, l in enumerate(lines) if "TIME_PERIOD" in l.upper()), None
        )
        if header_idx is None:
            return {}
        headers = [h.strip().upper() for h in lines[header_idx].split(",")]
        try:
            time_col  = headers.index("TIME_PERIOD")
            value_col = headers.index("OBS_VALUE")
        except ValueError:
            return {}
        pairs: list[tuple[str, float]] = []
        for line in lines[header_idx + 1:]:
            parts = line.split(",")
            if len(parts) <= max(time_col, value_col):
                continue
            try:
                val = float(parts[value_col].strip())
                pairs.append((parts[time_col].strip(), val))
            except (ValueError, IndexError):
                continue
        pairs.sort(key=lambda x: x[0], reverse=True)
        if not pairs:
            return {}
        return {
            "actual":   pairs[0][1],
            "previous": pairs[1][1] if len(pairs) > 1 else None,
            "date":     pairs[0][0],
            "source":   "ECB",
        }
    except Exception:
        return {}


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_ecb_cpi() -> dict:
    """
    Fetch Eurozone HICP CPI m/m from ECB Data Portal CSV — no API key needed.
    Returns {actual, previous, date, source} or {} on failure.
    """
    try:
        r = requests.get(ECB_CPI_URL, timeout=10,
                         headers={"Accept": "text/csv,application/csv,*/*"})
        if r.status_code != 200:
            return {}
        lines = [l for l in r.text.splitlines() if l.strip()]
        # Find header row
        header_idx = next(
            (i for i, l in enumerate(lines) if "TIME_PERIOD" in l.upper()), None
        )
        if header_idx is None:
            return {}
        headers = [h.strip().upper() for h in lines[header_idx].split(",")]
        try:
            time_col  = headers.index("TIME_PERIOD")
            value_col = headers.index("OBS_VALUE")
        except ValueError:
            return {}
        pairs: list[tuple[str, float]] = []
        for line in lines[header_idx + 1:]:
            parts = line.split(",")
            if len(parts) <= max(time_col, value_col):
                continue
            try:
                val = float(parts[value_col].strip())
                pairs.append((parts[time_col].strip(), val))
            except (ValueError, IndexError):
                continue
        pairs.sort(key=lambda x: x[0], reverse=True)
        if not pairs:
            return {}
        return {
            "actual":   pairs[0][1],
            "previous": pairs[1][1] if len(pairs) > 1 else None,
            "date":     pairs[0][0],
            "source":   "ECB",
        }
    except Exception:
        return {}


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_boe_rate() -> dict:
    """
    Fetch Bank of England base rate from BoE database CSV — no API key needed.
    Returns {actual, previous, date, source} or {} on failure.
    """
    try:
        r = requests.get(BOE_RATE_URL, timeout=10,
                         headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200:
            return {}
        lines = [l for l in r.text.splitlines() if l.strip()]
        # BoE CSV: first few rows are metadata, then "Date,IUMABEDR" header
        header_idx = next(
            (i for i, l in enumerate(lines)
             if l.strip().upper().startswith("DATE") or "IUMABEDR" in l.upper()),
            None,
        )
        if header_idx is None:
            return {}
        pairs: list[tuple[str, float]] = []
        for line in lines[header_idx + 1:]:
            parts = line.split(",")
            if len(parts) < 2:
                continue
            try:
                val = float(parts[1].strip())
                pairs.append((parts[0].strip(), val))
            except (ValueError, IndexError):
                continue
        if not pairs:
            return {}
        # Data is chronological — take the last entry as most recent
        pairs_sorted = sorted(pairs, key=lambda x: x[0], reverse=True)
        return {
            "actual":   pairs_sorted[0][1],
            "previous": pairs_sorted[1][1] if len(pairs_sorted) > 1 else None,
            "date":     pairs_sorted[0][0],
            "source":   "BoE",
        }
    except Exception:
        return {}


@st.cache_data(ttl=1800, show_spinner=False)
def fetch_te_indicators(currency: str) -> dict:
    """
    Scrape the Trading Economics indicators page for a given currency.
    Returns {indicator_key: {actual, previous, date, source}} or {} on any failure.
    Cached 30 min.  Never raises — always returns {} on error.
    """
    if not _BS4:
        return {}
    url = _TE_URLS.get(currency)
    if not url:
        return {}
    try:
        r = requests.get(url, headers=_TE_HEADERS, timeout=12)
        if r.status_code != 200:
            return {}
        soup = BeautifulSoup(r.text, "html.parser")

        # TE renders indicators in a <table> — find all rows
        result: dict = {}
        assigned: set[str] = set()

        for row in soup.select("table tr"):
            cells = row.find_all(["td", "th"])
            if len(cells) < 3:
                continue
            row_name = cells[0].get_text(strip=True).lower()
            # Match against our map (first match wins; skip already-assigned keys)
            matched_key: str | None = None
            for fragment, ind_key in _TE_ROW_MAP:
                if fragment in row_name and ind_key not in assigned:
                    matched_key = ind_key
                    break
            if matched_key is None:
                continue

            def _cell_float(cell) -> float | None:
                txt = cell.get_text(strip=True).replace(",", "").replace("%", "").strip()
                try:
                    return float(txt)
                except (ValueError, TypeError):
                    return None

            # TE columns: Name | Last | Previous | Highest | Lowest | Unit | Reference
            actual   = _cell_float(cells[1]) if len(cells) > 1 else None
            previous = _cell_float(cells[2]) if len(cells) > 2 else None
            date_txt = cells[6].get_text(strip=True) if len(cells) > 6 else ""

            if actual is None:
                continue

            result[matched_key] = {
                "actual":   actual,
                "previous": previous,
                "date":     date_txt,
                "source":   "TE",
            }
            assigned.add(matched_key)

        return result
    except Exception:
        return {}


@st.cache_data(ttl=TTL_NEWS_CTX, show_spinner=False)
def fetch_news_context_scores() -> dict[str, float]:
    """
    Fetch Google News RSS headlines for all 8 currencies + one geopolitical query.
    Score each currency -3.0 to +3.0 using keyword sentiment weighting.
    Applies a geopolitical overlay (Iran war / oil shock / risk-off) on top.
    Returns {currency: raw_context_score}.  Falls back to 0.0 per currency silently.
    """
    import urllib.parse

    if not _FEEDPARSER:
        return {c: 0.0 for c in SUPPORTED_CURRENCIES}

    def _fetch(query: str) -> list[str]:
        try:
            url = (
                "https://news.google.com/rss/search?q="
                + urllib.parse.quote_plus(query)
                + "&hl=en-US&gl=US&ceid=US:en"
            )
            feed = feedparser.parse(url)
            texts = []
            for entry in (feed.entries or [])[:8]:
                parts = [
                    getattr(entry, "title",   ""),
                    getattr(entry, "summary", ""),
                ]
                texts.append(" ".join(parts))
            return texts
        except Exception:
            return []

    def _score_texts(texts: list[str]) -> float:
        if not texts:
            return 0.0
        total = 0.0
        for txt in texts:
            t = txt.lower()
            for kw, w in _NEWS_BULL_KW:
                if kw in t:
                    total += w
            for kw, w in _NEWS_BEAR_KW:
                if kw in t:
                    total += w  # w is already negative
        # Normalise to per-article average then clamp
        return max(-3.0, min(3.0, total / len(texts)))

    scores: dict[str, float] = {}
    for ccy, query in _NEWS_QUERIES.items():
        snippets = _fetch(query)
        scores[ccy] = round(_score_texts(snippets), 3)

    # NOTE: Geopolitical overlay removed — geo context is reserved for Module 4.

    return scores


@st.cache_data(ttl=TTL_FUNDAMENTAL, show_spinner=False)
def fetch_fundamental_scores() -> dict[str, float]:
    """
    Layer 2 — Structural fundamental analysis score for all 8 currencies.

    Combines three sub-components:
      A) Interest rate differential vs G8 average  (objective, always available)
      B) Safe-haven structural premium  (CHF/JPY/USD regime-based adjustment)
      C) Web-searched medium-term CB-stance / macro outlook (Google News RSS)
      D) Geopolitical / energy-price overlay (shared with Layer 3 geo query)

    Returns {currency: score ∈ [-3.0, +3.0]}.  Silent 0.0 fallback on errors.
    """
    import urllib.parse

    # A — Rate differential: how far above/below the G8 average rate is this ccy
    avg_rate = sum(_BASE_RATES.values()) / len(_BASE_RATES)
    scores: dict[str, float] = {}
    for ccy, rate in _BASE_RATES.items():
        # ±1.0 per 2 % deviation from average, capped ±2.0
        scores[ccy] = round(max(-2.0, min(2.0, (rate - avg_rate) / 2.0)), 3)

    # NOTE: Safe-haven premium removed — geo/safe-haven context reserved for Module 4.

    if not _FEEDPARSER:
        return {c: round(max(-3.0, min(3.0, scores.get(c, 0.0))), 3)
                for c in SUPPORTED_CURRENCIES}

    def _fetch(query: str) -> list[str]:
        try:
            url = (
                "https://news.google.com/rss/search?q="
                + urllib.parse.quote_plus(query)
                + "&hl=en-US&gl=US&ceid=US:en"
            )
            feed = feedparser.parse(url)
            texts = []
            for entry in (feed.entries or [])[:8]:
                texts.append(
                    getattr(entry, "title", "") + " " + getattr(entry, "summary", "")
                )
            return texts
        except Exception:
            return []

    def _score_texts(texts: list[str]) -> float:
        if not texts:
            return 0.0
        total = 0.0
        for txt in texts:
            t = txt.lower()
            for kw, w in _FUND_BULL_KW:
                if kw in t:
                    total += w
            for kw, w in _FUND_BEAR_KW:
                if kw in t:
                    total += w  # already negative
        return max(-2.0, min(2.0, total / len(texts)))

    # C — Medium-term fundamental outlook per currency
    for ccy, query in _FUNDAMENTAL_QUERIES.items():
        web_score = _score_texts(_fetch(query))
        scores[ccy] = scores.get(ccy, 0.0) + web_score

    # NOTE: Geopolitical overlay removed — geo context is reserved for Module 4.

    return {
        c: round(max(-3.0, min(3.0, scores.get(c, 0.0))), 3)
        for c in SUPPORTED_CURRENCIES
    }




# ╔══════════════════════════════════════════════════════════════════════════════
# ║  DATA BUILDERS
# ╚══════════════════════════════════════════════════════════════════════════════

def build_indicators_table(
    currency: str,
    official: dict | None = None,
) -> tuple[pd.DataFrame, str]:
    """
    Build the indicators table.
    Priority: official API (FRED/ECB/BoE/TE) > static fallback.
    Always returns a complete table — never empty.
    Returns (df, source_label).
    """
    sources_used: set[str] = set()
    result_rows: list[dict] = []

    for ind in INDICATOR_ORDER:
        # Layer 1: static baseline
        fb       = STATIC_INDICATORS.get(currency, {}).get(ind, {})
        actual   = fb.get("actual")
        previous = fb.get("previous")
        forecast = fb.get("forecast")
        date_val = fb.get("date", "")
        impact   = fb.get("impact", "Low")
        source   = "static"

        prev_forecast = None

        # Layer 2: official API override (FRED / ECB / BoE / TE)
        if official and ind in official:
            off = official[ind]
            if off.get("actual") is not None:
                actual   = off["actual"]
                if off.get("previous") is not None:
                    previous = off["previous"]
                if off.get("date"):
                    date_val = off["date"]
                source = off.get("source", source)

        sources_used.add(source)

        # Beat / miss
        beat_miss = "unknown"
        try:
            if actual is not None and forecast is not None:
                lower = LOWER_IS_BETTER.get(ind, False)
                rel   = abs(float(actual) - float(forecast)) / max(abs(float(forecast)), 0.01)
                if rel < 0.005:
                    beat_miss = "inline"
                elif (not lower and float(actual) > float(forecast)) or \
                     (lower     and float(actual) < float(forecast)):
                    beat_miss = "beat"
                else:
                    beat_miss = "miss"
        except Exception:
            beat_miss = "unknown"

        result_rows.append({
            "indicator": ind, "actual": actual, "previous": previous,
            "forecast": forecast, "beat_miss": beat_miss,
            "date": date_val, "impact": impact, "upcoming": False, "source": source,
            "prev_forecast": prev_forecast,
        })

    df = pd.DataFrame(result_rows)

    # Source label for UI
    live_apis = sources_used & {"FRED", "ECB", "BoE", "TE"}
    if live_apis:
        api_str = "/".join(sorted(live_apis))
        label = f"Live ({api_str})"
    else:
        label = "Static (May 2026)"

    return df, label




def calc_bias_score(indicators_df: pd.DataFrame, currency: str) -> dict:
    """
    4-dimensional FX bias scoring engine.
    D1 Absolute Level    (15%) — currency-specific neutral zones, equal-weighted avg
    D2 Forecast Quality  (10%) — consensus expectation: absolute + directional, equal-weighted
    D3 Beat/Miss         (40%) — actual vs forecast, impact-weighted (High=5x Med=2x Low=0.5x)
    D4 Trend/Momentum    (35%) — actual vs previous, impact-weighted
    Final = (D1×0.15 + D2×0.10 + D3×0.40 + D4×0.35) × 1.4  clamped: -1.0 to +1.0
    """
    def _f(v):
        try: return None if v is None else float(v)
        except Exception: return None

    # ── Build lookup: {indicator: {a, p, f, imp}} ─────────────────────────────
    lk: dict[str, dict] = {}
    for _, row in indicators_df.iterrows():
        lk[row["indicator"]] = {
            "a":   _f(row.get("actual")),
            "p":   _f(row.get("previous")),
            "f":   _f(row.get("forecast")),
            "imp": str(row.get("impact", "Low")),
        }

    # ── Currency-specific neutral zones ───────────────────────────────────────
    _IR_NEUTRAL = {
        "USD": (2.5, 3.5), "EUR": (1.5, 2.5), "GBP": (2.0, 3.5),
        "JPY": (0.0, 0.5), "CHF": (0.0, 0.5),
        "AUD": (2.5, 3.5), "CAD": (2.0, 3.0), "NZD": (2.5, 3.5),
    }
    _CPI_CFG = {
        # (critical_floor, target, acceptable_hi, critical_hi)
        "USD": (0.5, 2.0, 3.0, 5.0), "EUR": (0.5, 2.0, 3.0, 5.0),
        "GBP": (0.5, 2.0, 3.0, 5.0), "AUD": (0.5, 2.0, 3.0, 5.0),
        "CAD": (0.5, 2.0, 3.0, 5.0), "NZD": (0.5, 2.0, 3.0, 5.0),
        "JPY": (0.5, 2.0, 2.5, 4.0),
        "CHF": (0.2, 1.0, 1.5, 3.0),
    }
    _UNEMP = {
        "USD": (4.0, 5.5), "EUR": (6.5, 8.0), "GBP": (4.0, 5.5),
        "JPY": (2.5, 3.5), "CHF": (2.5, 3.5),
        "AUD": (4.0, 5.5), "CAD": (5.5, 7.0), "NZD": (4.0, 5.5),
    }

    # ── Absolute-difference surprise/trend thresholds ─────────────────────────
    _SLT = {
        "CPI m/m": 0.05, "Interest Rate": 0.01, "GDP Growth": 0.1,
        "Unemployment Rate": 0.1, "Manufacturing PMI": 1.0, "Services PMI": 1.0,
        "Trade Balance": 0.1, "Retail Sales": 0.1, "Wage Growth": 0.2,
        "PPI": 0.2, "Current Account": 0.1, "Consumer Confidence": 2.0,
        "Business Confidence": 2.0, "Budget Balance": 0.3,
        "Government Debt": 2.0, "Building Permits": 20.0,
    }
    _STR = {
        "CPI m/m": 0.19, "Interest Rate": 0.25, "GDP Growth": 0.3,
        "Unemployment Rate": 0.3, "Manufacturing PMI": 3.0, "Services PMI": 3.0,
        "Trade Balance": 0.3, "Retail Sales": 0.3, "Wage Growth": 0.5,
        "PPI": 0.5, "Current Account": 0.3, "Consumer Confidence": 5.0,
        "Business Confidence": 5.0, "Budget Balance": 0.8,
        "Government Debt": 5.0, "Building Permits": 50.0,
    }
    _IMP_W = {"High": 5, "Medium": 2, "Low": 0.5}

    def _sdiff(diff: float, ind: str) -> float:
        """Map signed absolute diff → -1/-0.5/-0.3/0/+0.3/+0.5/+1."""
        slt = _SLT.get(ind, 0.3); str_ = _STR.get(ind, 0.6)
        half = slt * 0.5
        if diff >  str_:  return  1.0
        if diff >  slt:   return  0.5
        if diff >  half:  return  0.3
        if diff > -half:  return  0.0
        if diff > -slt:   return -0.3
        if diff > -str_:  return -0.5
        return -1.0

    # ── D1: Absolute level → -1.0 to +1.0 ───────────────────────────────────
    def _d1(ind: str, a: float) -> float:
        if ind == "Interest Rate":
            lo, hi = _IR_NEUTRAL.get(currency, (2.0, 3.5))
            if a < lo * 0.5:  return -1.0
            if a < lo:        return -0.6
            if a <= hi:       return  0.2
            if a <= hi * 1.5: return  0.2
            return 1.0
        if ind == "CPI m/m":
            ann = a * 12  # annualise m/m → comparable to 2% annual target
            crit, tgt, acc, crit_hi = _CPI_CFG.get(currency, (0.5, 2.0, 3.0, 5.0))
            if ann < crit:             return -1.0
            if abs(ann - tgt) <= 0.3:  return  1.0
            if ann <= acc:             return  0.2
            if ann <= crit_hi:         return -0.6
            return -1.0
        if ind == "GDP Growth":
            if a > 0.6:   return  1.0
            if a >= 0.2:  return  0.2
            if a >= 0.0:  return -0.6
            return -1.0
        if ind == "Unemployment Rate":
            tight, normal = _UNEMP.get(currency, (4.0, 5.5))
            if a <= tight:         return  1.0
            if a <= normal:        return  0.2
            if a <= normal + 1.5:  return -0.6
            return -1.0
        if ind in ("Manufacturing PMI", "Services PMI"):
            if a > 54:   return  1.0
            if a >= 50:  return  0.2
            if a >= 48:  return -0.6
            return -1.0
        if ind == "Wage Growth":
            # CHF has structurally lower wage growth — different neutral zone
            if currency == "CHF":
                if a > 2.5:  return  1.0
                if a >= 1.0: return  0.2
                if a >= 0.5: return -0.6
                return -1.0
            if a > 4.5:  return  0.2
            if a >= 2.5: return  1.0
            if a >= 1.5: return  0.2
            if a >= 0.5: return -0.6
            return -1.0
        if ind in ("Trade Balance", "Current Account"):
            if a > 5.0:   return  1.0
            if a >= 0.0:  return  0.2
            if a >= -3.0: return -0.6
            return -1.0
        if ind == "Retail Sales":
            if a > 0.5:   return  1.0
            if a >= 0.0:  return  0.2
            if a >= -0.5: return -0.6
            return -1.0
        if ind == "PPI":
            if a < 0.0:   return -0.6
            if a <= 3.0:  return  0.2
            if a <= 5.0:  return -0.6
            return -1.0
        if ind in ("Consumer Confidence", "Business Confidence"):
            # These use mixed/negative scales — use absolute range bands
            if a > 5.0:    return  1.0
            if a >= -10.0: return  0.2
            if a >= -20.0: return -0.6
            return -1.0
        if ind == "Core CPI":
            ann = a * 12
            crit, tgt, acc, crit_hi = _CPI_CFG.get(currency, (0.5, 2.0, 3.0, 5.0))
            if ann < crit:             return -1.0
            if abs(ann - tgt) <= 0.3:  return  1.0
            if ann <= acc:             return  0.2
            if ann <= crit_hi:         return -0.6
            return -1.0
        if ind == "Employment Change":
            if a > 200:  return  1.0
            if a > 100:  return  0.5
            if a > 0:    return  0.2
            if a > -50:  return -0.6
            return -1.0
        if ind == "Industrial Production":
            if a > 0.5:   return  1.0
            if a >= 0.0:  return  0.2
            if a >= -0.5: return -0.6
            return -1.0
        if ind == "M2 Money Supply":
            if a > 5.0:  return -0.3
            if a > 2.0:  return  0.5
            if a > 0.0:  return  0.2
            return -0.6
        return 0.0

    # ── D2: Forecast quality → -1.0 to +1.0 ──────────────────────────────────
    # 50% absolute quality of forecast value + 50% directional expectation vs previous
    def _d2(ind: str, f_: float, p: float | None) -> float:
        base = _d1(ind, f_)
        if p is None: return base
        delta = f_ - p
        if LOWER_IS_BETTER.get(ind, False): delta = -delta
        if ind == "CPI m/m":
            tgt = _CPI_CFG.get(currency, (0.5, 2.0, 3.0, 5.0))[1] / 12
            delta = abs(p - tgt) - abs(f_ - tgt)
        dir_s = _sdiff(delta, ind)
        return 0.5 * base + 0.5 * dir_s

    # ── D3: Beat/Miss → -1.0 to +1.0 ────────────────────────────────────────
    def _d3(ind: str, a: float, f_: float) -> float:
        diff = a - f_
        if LOWER_IS_BETTER.get(ind, False): diff = -diff
        if ind == "CPI m/m":
            tgt = _CPI_CFG.get(currency, (0.5, 2.0, 3.0, 5.0))[1] / 12
            diff = abs(f_ - tgt) - abs(a - tgt)
        return _sdiff(diff, ind)

    # ── D4: Trend/Momentum → -1.0 to +1.0 ───────────────────────────────────
    def _d4(ind: str, a: float, p: float) -> float:
        diff = a - p
        if LOWER_IS_BETTER.get(ind, False): diff = -diff
        if ind == "CPI m/m":
            tgt = _CPI_CFG.get(currency, (0.5, 2.0, 3.0, 5.0))[1] / 12
            diff = abs(p - tgt) - abs(a - tgt)
        return _sdiff(diff, ind)

    # ── Aggregate ─────────────────────────────────────────────────────────────
    def _eq(vals: list[float]) -> float:
        return sum(vals) / len(vals) if vals else 0.0

    def _wt(pairs: list[tuple[float, float]]) -> float:
        tw = sum(w for _, w in pairs)
        return sum(s * w for s, w in pairs) / tw if tw else 0.0

    d1_vals:  list[float]            = []
    d2_vals:  list[float]            = []
    d3_pairs: list[tuple[float,float]] = []
    d4_pairs: list[tuple[float,float]] = []
    details:  list[dict]             = []

    for ind, data in lk.items():
        a, p, f_ = data["a"], data["p"], data["f"]
        w = _IMP_W.get(data["imp"], 1)
        if a is None: continue

        d1v = _d1(ind, a);  d1_vals.append(d1v)
        d2v = _d2(ind, f_, p) if f_ is not None else None
        if d2v is not None: d2_vals.append(d2v)
        d3v = _d3(ind, a, f_) if f_ is not None else None
        if d3v is not None: d3_pairs.append((d3v, w))
        d4v = _d4(ind, a, p) if p is not None else None
        if d4v is not None: d4_pairs.append((d4v, w))

        details.append({"ind": ind, "d1": d1v, "d2": d2v, "d3": d3v, "d4": d4v, "imp": data["imp"]})

    d1_agg = round(max(-1.0, min(1.0, _eq(d1_vals))), 3)
    d2_agg = round(max(-1.0, min(1.0, _eq(d2_vals))), 3) if d2_vals else 0.0
    d3_agg = round(max(-1.0, min(1.0, _wt(d3_pairs))), 3) if d3_pairs else 0.0
    d4_agg = round(max(-1.0, min(1.0, _wt(d4_pairs))), 3) if d4_pairs else 0.0

    _raw = d1_agg * 0.15 + d2_agg * 0.10 + d3_agg * 0.40 + d4_agg * 0.35
    final = round(max(-1.0, min(1.0, _raw * 1.4)), 3)

    # ── Classification ────────────────────────────────────────────────────────
    if   final >  0.60: level, lc = "STRONG BULLISH", "#00a36c"
    elif final >  0.30: level, lc = "SLIGHT BULLISH", C["green"]
    elif final >  0.10: level, lc = "MILD BULLISH",   "#4ecb9e"
    elif final >= 0.0:  level, lc = "MILD BULLISH",   "#4ecb9e"
    elif final > -0.30: level, lc = "MILD BEARISH",   C["yellow"]
    elif final >= -0.60: level, lc = "SLIGHT BEARISH", "#f08080"
    else:                level, lc = "STRONG BEARISH", C["red"]

    # ── Per-indicator tags for bias panel ─────────────────────────────────────
    _IND_LBL = {
        "Interest Rate": "Rate",    "CPI m/m": "CPI",        "GDP Growth": "GDP",
        "Unemployment Rate": "Unemp","Wage Growth": "Wages",  "Manufacturing PMI": "MfgPMI",
        "Services PMI": "SvcPMI",   "Trade Balance": "Trade","Current Account": "CA",
        "Retail Sales": "Retail",   "Consumer Confidence": "ConsConf",
        "PPI": "PPI",               "Government Debt": "GovDebt",
        "Core CPI": "CoreCPI", "Employment Change": "EmpChg",
        "Industrial Production": "IndProd", "M2 Money Supply": "M2",
    }
    scores: list[dict] = []
    for det in details:
        ind   = det["ind"]
        parts = [(det["d1"], 0.20)]
        if det["d2"] is not None: parts.append((det["d2"], 0.15))
        if det["d3"] is not None: parts.append((det["d3"], 0.35))
        if det["d4"] is not None: parts.append((det["d4"], 0.30))
        tw    = sum(w for _, w in parts)
        raw   = sum(s * w for s, w in parts) / tw if tw else 0.0
        color = C["green"] if raw > 0.05 else C["red"] if raw < -0.05 else C["muted"]
        bg    = ("rgba(0,196,140,0.10)" if raw > 0.05
                 else "rgba(240,82,98,0.10)" if raw < -0.05
                 else C["dim"])
        d_parts = [f"D1:{det['d1']:+.1f}"]
        if det["d2"] is not None: d_parts.append(f"D2:{det['d2']:+.1f}")
        if det["d3"] is not None: d_parts.append(f"D3:{det['d3']:+.1f}")
        if det["d4"] is not None: d_parts.append(f"D4:{det['d4']:+.1f}")
        tip = " ".join(d_parts) + f" → {raw:+.2f}"
        lbl = _IND_LBL.get(ind, ind[:7])
        scores.append({
            "label": lbl, "raw": round(raw, 3), "score": round(raw, 3),
            "weighted": round(raw, 3), "dims": tip, "color": color, "bg": bg,
        })

    return {
        "total":       final,
        "level":       level,
        "level_color": lc,
        "d1": d1_agg, "d2": d2_agg, "d3": d3_agg, "d4": d4_agg,
        "scores":      scores,
        "partial":     False,
        "missing":     [],
    }


# ╔══════════════════════════════════════════════════════════════════════════════
# ║  4-DIMENSIONAL INDICATOR ASSESSMENT HELPERS  (used in table rendering)
# ╚══════════════════════════════════════════════════════════════════════════════

# (slight_abs_threshold, strong_abs_threshold) per indicator for D3/D4 intensity
_D_THRESHOLDS: dict[str, tuple[float, float]] = {
    "CPI m/m":             (0.05, 0.19),   # 0.05 slight; >0.19 (≥0.20) = strong
    "Interest Rate":       (0.01, 0.25),
    "GDP Growth":          (0.10, 0.30),
    "Unemployment Rate":   (0.10, 0.30),
    "Manufacturing PMI":   (1.00, 3.00),
    "Services PMI":        (1.00, 3.00),
    "Wage Growth":         (0.20, 0.50),
    "Trade Balance":       (0.10, 0.30),   # tightened
    "Current Account":     (0.10, 0.30),   # tightened
    "Retail Sales":        (0.10, 0.30),   # tightened
    "Consumer Confidence": (2.00, 5.00),
    "PPI":                 (0.20, 0.50),
    "Government Debt":     (2.00, 5.00),
    "Budget Balance":      (0.30, 0.80),
    "Building Permits":    (20.0, 50.0),
    "Business Confidence": (2.00, 5.00),
    "Core CPI":              (0.05, 0.19),
    "Employment Change":     (50.0, 150.0),
    "Industrial Production": (0.20, 0.50),
    "M2 Money Supply":       (0.50, 1.50),
}


def _d1_level(ind: str, val, currency: str = "USD") -> tuple[str, str]:
    """D1: absolute level assessment → (label, hex_color)"""
    try:
        v = float(val)
    except (TypeError, ValueError):
        return "—", C["muted"]

    if ind == "CPI m/m":
        ann = v * 12
        if ann < 1.0:    return "CRITICAL",  C["red"]
        if ann < 2.0:    return "WEAK",      C["yellow"]
        if ann <= 2.5:   return "STRONG",    C["green"]
        if ann <= 3.5:   return "NORMAL",    C["muted"]
        if ann <= 5.0:   return "WEAK",      C["yellow"]
        return               "CRITICAL",     C["red"]
    if ind == "Interest Rate":
        if v > 4.0:    return "STRONG",    C["green"]    # restrictive
        if v >= 2.0:   return "NORMAL",    C["muted"]    # neutral
        if v >= 1.0:   return "WEAK",      C["yellow"]   # accommodative
        return             "CRITICAL",     C["red"]       # near-zero
    if ind == "GDP Growth":
        if v > 3.0:    return "STRONG",    C["green"]
        if v > 1.0:    return "NORMAL",    C["muted"]
        if v >= 0.0:   return "WEAK",      C["yellow"]
        return             "CRITICAL",     C["red"]       # contraction
    if ind == "Unemployment Rate":
        if v < 3.5:    return "NORMAL",    C["muted"]    # overheating labour
        if v <= 5.0:   return "STRONG",    C["green"]    # optimal
        if v <= 6.0:   return "NORMAL",    C["muted"]
        if v <= 8.0:   return "WEAK",      C["yellow"]
        return             "CRITICAL",     C["red"]
    if ind in ("Manufacturing PMI", "Services PMI"):
        if v > 57.0:   return "STRONG",    C["green"]
        if v >= 52.0:  return "NORMAL",    C["muted"]
        if v >= 50.0:  return "WEAK",      C["yellow"]   # barely expanding
        return             "CRITICAL",     C["red"]       # contraction
    if ind == "Wage Growth":
        if currency == "CHF":
            if v >= 2.5: return "STRONG",  C["green"]
            if v >= 1.0: return "NORMAL",  C["muted"]
            if v >= 0.5: return "WEAK",    C["yellow"]
            return           "CRITICAL",   C["red"]
        if v > 4.0:    return "STRONG",    C["green"]
        if v >= 2.0:   return "NORMAL",    C["muted"]
        if v >= 1.0:   return "WEAK",      C["yellow"]
        return             "CRITICAL",     C["red"]
    if ind in ("Trade Balance", "Current Account"):
        if v > 2.0:    return "STRONG",    C["green"]
        if v >= 0.0:   return "NORMAL",    C["muted"]
        if v >= -2.0:  return "WEAK",      C["yellow"]
        return             "CRITICAL",     C["red"]
    if ind == "Retail Sales":
        if v > 0.5:    return "STRONG",    C["green"]
        if v >= 0.0:   return "NORMAL",    C["muted"]
        if v >= -0.5:  return "WEAK",      C["yellow"]
        return             "CRITICAL",     C["red"]
    if ind == "PPI":
        if v < 0.5:    return "WEAK",      C["yellow"]
        if v <= 3.0:   return "NORMAL",    C["muted"]
        if v <= 5.0:   return "WEAK",      C["yellow"]
        return             "CRITICAL",     C["red"]
    if ind in ("Consumer Confidence", "Business Confidence"):
        if v > 5.0:    return "STRONG",    C["green"]
        if v >= -10.0: return "NORMAL",    C["muted"]
        if v >= -20.0: return "WEAK",      C["yellow"]
        return             "CRITICAL",     C["red"]
    if ind == "Core CPI":
        ann = v * 12
        if ann < 1.0:    return "CRITICAL",  C["red"]
        if ann < 2.0:    return "WEAK",      C["yellow"]
        if ann <= 2.5:   return "STRONG",    C["green"]
        if ann <= 3.5:   return "NORMAL",    C["muted"]
        return               "WEAK",         C["yellow"]
    if ind == "Employment Change":
        if v > 200:    return "STRONG",    C["green"]
        if v > 100:    return "NORMAL",    C["muted"]
        if v > 0:      return "WEAK",      C["yellow"]
        return             "CRITICAL",     C["red"]
    if ind == "Industrial Production":
        if v > 0.5:    return "STRONG",    C["green"]
        if v >= 0.0:   return "NORMAL",    C["muted"]
        if v >= -0.5:  return "WEAK",      C["yellow"]
        return             "CRITICAL",     C["red"]
    if ind == "M2 Money Supply":
        if v > 5.0:    return "WEAK",      C["yellow"]
        if v > 1.0:    return "STRONG",    C["green"]
        if v >= 0.0:   return "NORMAL",    C["muted"]
        return             "CRITICAL",     C["red"]
    return "NORMAL", C["muted"]


def _d3_intensity(ind: str, actual, reference, invert: bool = False) -> tuple[str, str]:
    """
    D3 Beat/Miss intensity or D4 Trend intensity.
    invert=True for LOWER_IS_BETTER indicators (Unemployment, Govt Debt).
    Returns (label, hex_color).
    """
    try:
        diff = float(actual) - float(reference)
    except (TypeError, ValueError):
        return "—", C["muted"]
    if invert:
        diff = -diff
    slight, strong = _D_THRESHOLDS.get(ind, (0.30, 0.60))
    if diff >  strong: return "STRONG BEAT",  C["green"]
    if diff >  slight: return "SLIGHT BEAT",  "#4ecb9e"
    if diff > -slight: return "IN LINE",       C["muted"]
    if diff > -strong: return "SLIGHT MISS",  C["yellow"]
    return                    "STRONG MISS",  C["red"]


def _d4_trend(ind: str, actual, previous) -> tuple[str, str]:
    """D4 Trend: actual vs previous → (label, hex_color). 5-level display."""
    # CPI: moving toward target = positive (not raw direction)
    if ind == "CPI m/m":
        try:
            tgt   = 2.0 / 12   # monthly equivalent: 0.167%
            diff  = abs(float(previous) - tgt) - abs(float(actual) - tgt)
        except (TypeError, ValueError):
            diff  = 0.0
        slight, strong = _D_THRESHOLDS.get(ind, (0.30, 0.60))
        if diff >  strong: raw_lbl = "STRONG BEAT"
        elif diff >  slight: raw_lbl = "SLIGHT BEAT"
        elif diff > -slight: raw_lbl = "IN LINE"
        elif diff > -strong: raw_lbl = "SLIGHT MISS"
        else: raw_lbl = "STRONG MISS"
    else:
        invert = LOWER_IS_BETTER.get(ind, False)
        raw_lbl, _ = _d3_intensity(ind, actual, previous, invert=invert)
    _map = {
        "STRONG BEAT": ("↑↑ STRONG IMPR",  C["green"]),
        "SLIGHT BEAT": ("↑ IMPROVING",      "#4ecb9e"),
        "IN LINE":     ("→ STABLE",         C["muted"]),
        "SLIGHT MISS": ("↓ DETERIORATING",  C["yellow"]),
        "STRONG MISS": ("↓↓ STRONG DETER", C["red"]),
        "—":           ("—",                C["muted"]),
    }
    return _map.get(raw_lbl, (raw_lbl, C["muted"]))


# ╔══════════════════════════════════════════════════════════════════════════════
# ║  HTML RENDER FUNCTIONS
# ╚══════════════════════════════════════════════════════════════════════════════

def render_bias_panel(currency: str, bias: dict, source_label: str) -> str:
    score   = bias["total"]
    level   = bias["level"]
    lc      = bias["level_color"]
    scores  = bias.get("scores", [])
    flag    = CURRENCY_FLAG.get(currency, "")
    sign    = "+" if score > 0 else ""
    # Gauge: ±3.0 range → 0–100%
    pct     = max(3.0, min(97.0, (score + 3.0) / 6.0 * 100))
    is_live = "Static" not in source_label

    # Per-indicator contribution tags
    tags = ""
    for item in scores:
        s     = item["weighted"]
        color = item["color"]
        bg    = item.get("bg", C["dim"])
        tip   = item.get("dims", "")
        tags += (
            f"<span title='{tip}' style='background:{bg};color:{color};font-size:9px;"
            f"font-family:monospace;font-weight:700;padding:2px 8px;"
            f"border-radius:10px;border:1px solid {color}33;"
            f"white-space:nowrap;cursor:help;'>{item['label']} {s:+.2f}</span>"
        )

    _cm2 = C["muted"]
    tags_html = (
        f"<details style='margin-top:4px;'>"
        f"<summary style='font-size:9px;color:{_cm2};font-family:monospace;"
        f"cursor:pointer;list-style:none;'>Show indicator breakdown ▼</summary>"
        f"<div style='display:flex;gap:5px;flex-wrap:wrap;margin-top:6px;'>{tags}</div>"
        f"</details>"
    )

    _d_chip_data = [
        ("D1", bias.get("dim1", 0.0), "Current values vs benchmarks"),
        ("D2", bias.get("dim2", 0.0), "Beat/Miss + trend momentum"),
        ("D3", bias.get("dim3", 0.0), "CB action pricing"),
        ("D4", bias.get("dim4", 0.0), "Rate differential & macro structure"),
    ]
    dim_grid = (
        f"<div style='display:grid;grid-template-columns:repeat(4,1fr);"
        f"gap:6px;margin-bottom:10px;'>"
    )
    for dlbl, dval, dtip in _d_chip_data:
        dc  = C["green"] if dval > 0.1 else C["red"] if dval < -0.1 else C["muted"]
        dbg = "rgba(0,196,140,0.08)" if dval > 0.1 else "rgba(240,82,98,0.08)" if dval < -0.1 else C["dim"]
        dim_grid += (
            f"<div title='{dtip}' style='background:{dbg};border:1px solid {dc}33;"
            f"border-radius:8px;padding:6px 8px;text-align:center;cursor:help;'>"
            f"<div style='font-size:8px;color:{C['muted']};font-family:monospace;"
            f"letter-spacing:0.8px;margin-bottom:3px;'>{dlbl}</div>"
            f"<div style='font-size:16px;font-weight:800;color:{dc};"
            f"font-family:monospace;line-height:1;'>{dval:+.2f}</div>"
            f"</div>"
        )
    dim_grid += "</div>"

    _cb = C["border"]; _cm = C["muted"]; _ct = C["text"]
    _cg = C["green"];  _cr = C["red"];   _cy = C["yellow"]
    return f"""
<div style='background:{C["card"]};border:1px solid {_cb};
            border-radius:12px;padding:18px 20px;margin-bottom:12px;'>
  <div style='display:flex;align-items:center;justify-content:space-between;
              margin-bottom:14px;'>
    <div style='display:flex;align-items:center;gap:10px;'>
      <span style='font-size:22px;line-height:1;'>{flag}</span>
      <div>
        <div style='font-size:10px;color:{_cm};font-family:monospace;
                    letter-spacing:1.5px;text-transform:uppercase;'>Overall Bias</div>
        <div style='font-size:16px;font-weight:800;color:{lc};
                    font-family:monospace;letter-spacing:1px;'>{level}</div>
      </div>
    </div>
    <div style='text-align:right;'>
      <div style='font-size:28px;font-weight:800;color:{lc};
                  font-family:monospace;line-height:1;'>{sign}{score:.2f}</div>
      <div style='margin-top:4px;'>{_source_badge(source_label, is_live)}</div>
    </div>
  </div>
  <!-- Gauge bar — needle drawn via CSS multi-layer gradient (no position:absolute needed) -->
  <div style='height:10px;border-radius:5px;margin-bottom:4px;
              background:
                linear-gradient(to right,
                  transparent calc({pct:.1f}% - 1.5px),
                  {_ct}        calc({pct:.1f}% - 1.5px),
                  {_ct}        calc({pct:.1f}% + 1.5px),
                  transparent  calc({pct:.1f}% + 1.5px)),
                linear-gradient(to right,
                  #cc1a2a 0%, {_cr} 20%, {_cy} 50%,
                  {_cg} 80%, #00a36c 100%);'></div>
  <div style='display:flex;justify-content:space-between;font-size:9px;
              font-family:monospace;color:{_cm};margin-bottom:10px;'>
    <span>STR. BEARISH</span><span>SLT. BEARISH</span>
    <span>M. BEARISH</span><span>SLT. BULLISH</span><span>STR. BULLISH</span>
  </div>
  <!-- Dimension grid: D1/D2/D3/D4 -->
  {dim_grid}
  <!-- Per-indicator contribution tags (collapsible) -->
  {tags_html}
</div>"""


def render_indicators_table(
    indicators_df: pd.DataFrame,
    last_refresh_ts: float = 0.0,
    currency: str = "USD",
) -> str:
    _now_ts = time.time()
    # Label → numeric score (for row dot colour)
    _L2S: dict[str, float] = {
        "STRONG": 1.0, "NORMAL": 0.3, "WEAK": -0.3, "CRITICAL": -1.0,
        "STRONG BEAT": 1.0, "SLIGHT BEAT": 0.5, "IN LINE": 0.0,
        "SLIGHT MISS": -0.5, "STRONG MISS": -1.0,
        "↑↑ STRONG IMPR": 1.0, "↑ IMPROVING": 0.5, "→ STABLE": 0.0,
        "↓ DETERIORATING": -0.5, "↓↓ STRONG DETER": -1.0,
    }

    def _src_dot(src: str, dot_color: str) -> str:
        age   = _now_ts - last_refresh_ts if last_refresh_ts > 0 else 999_999
        shape = "◎" if src == "static" else "●"
        if src in ("FRED", "ECB", "BoE", "TE"):
            note = f"Live · {src} · {'fresh' if age < TTL_INDICATORS else 'stale'}"
        else:
            note = "Static fallback"
        return f"<span title='{note}' style='color:{dot_color};font-size:9px;'>{shape}</span>"

    # Label-to-score mapping for intensity cells
    _SCORE_MAP: dict[str, float] = {
        "STRONG BEAT": 1.0, "STR BEAT": 1.0, "SLIGHT BEAT": 0.5, "SLT BEAT": 0.5,
        "IN LINE": 0.0, "SLIGHT MISS": -0.5, "SLT MISS": -0.5,
        "STRONG MISS": -1.0, "STR MISS": -1.0,
        "↑↑ STRONG IMPR": 1.0, "STRONG IMPR": 1.0,
        "↑ IMPROVING": 0.5, "IMPROVING": 0.5,
        "→ STABLE": 0.0, "STABLE": 0.0,
        "↓ DETERIORATING": -0.5, "DETER": -0.5,
        "↓↓ STRONG DETER": -1.0, "STRONG DETER": -1.0,
    }

    def _intensity_cell(label: str, color: str) -> str:
        _cm = C["muted"]
        if label in ("—", ""):
            return f"<span style='color:{_cm};font-family:monospace;'>—</span>"
        # Arrow: double for strong signals
        if "STRONG IMPR" in label or "STR BEAT" in label or "STRONG BEAT" in label:
            arrow = "↑↑"
        elif "BEAT" in label or "IMPROVING" in label:
            arrow = "↑"
        elif "STRONG DETER" in label or "STR MISS" in label or "STRONG MISS" in label:
            arrow = "↓↓"
        elif "MISS" in label or "DETERIORATING" in label:
            arrow = "↓"
        else:
            arrow = "→"
        short = (label.replace("STRONG BEAT","STR BEAT").replace("SLIGHT BEAT","SLT BEAT")
                      .replace("SLIGHT MISS","SLT MISS").replace("STRONG MISS","STR MISS")
                      .replace("↑↑ STRONG IMPR","STRONG IMPR").replace("↑ IMPROVING","IMPROVING")
                      .replace("→ STABLE","STABLE").replace("↓ DETERIORATING","DETER")
                      .replace("↓↓ STRONG DETER","STRONG DETER"))
        sc = _SCORE_MAP.get(short)
        sc_str = f"{sc:+.1f}" if sc is not None else ""
        badge = (
            f"<span style='background:{color}22;color:{color};font-size:9px;"
            f"font-family:monospace;font-weight:700;padding:1px 5px;"
            f"border-radius:3px;margin-left:4px;'>[{sc_str}]</span>"
            if sc_str else ""
        )
        return (
            f"<span style='color:{color};font-size:13px;line-height:1;"
            f"font-weight:700;'>{arrow}</span>{badge}"
        )

    def _level_pill(label: str, color: str) -> str:
        bg = f"{color}18"
        return (
            f"<span style='background:{bg};color:{color};font-size:8px;"
            f"font-family:monospace;font-weight:700;letter-spacing:0.5px;"
            f"padding:1px 5px;border-radius:3px;'>{label}</span>"
        )

    cols = ["Indicator", "Actual", "Prev", "Forecast", "Beat/Miss", "Trend", "Date", "Imp"]
    hdr  = (
        f"<tr style='border-bottom:1px solid {C['border']};'>"
        + "".join(
            f"<th style='padding:7px 7px;font-size:9px;color:{C['muted']};"
            f"font-family:monospace;text-transform:uppercase;letter-spacing:0.5px;"
            f"font-weight:600;text-align:left;white-space:nowrap;'>{h}</th>"
            for h in cols
        ) + "</tr>"
    )

    body = ""
    for i, (_, row) in enumerate(indicators_df.iterrows()):
        ind      = row["indicator"]
        actual   = row.get("actual")
        previous = row.get("previous")
        forecast = row.get("forecast")
        upcoming = bool(row.get("upcoming", False))
        alt_bg   = C["dim"] if (i % 2 == 1) else "transparent"
        row_bg   = C["teal_dim"] if upcoming else alt_bg
        src      = str(row.get("source", ""))

        try:
            raw_date = str(row.get("date", "")).strip()
            dv = pd.Timestamp(raw_date)
            if pd.isnull(dv) or dv.year < 2000:
                # Non-standard string (e.g. "Mar/26") — show raw value trimmed
                date_str = raw_date[:10] if raw_date else "—"
            elif dv.day == 1:
                # Month-only dates from ECB ("2025-12" → "Dec 2025")
                date_str = dv.strftime("%b %Y")
            else:
                date_str = dv.strftime("%d %b %Y")
        except Exception:
            date_str = str(row.get("date", "—"))[:10]

        upcoming_badge = (
            f"<span style='background:{C['teal_bg']};color:{C['teal']};font-size:9px;"
            f"font-family:monospace;font-weight:700;padding:1px 6px;"
            f"border-radius:3px;margin-left:6px;'>◆ NEXT</span>"
            if upcoming else ""
        )

        # D1 — absolute level of actual
        d1_label, d1_color = _d1_level(ind, actual, currency)
        # D2 — absolute level of forecast (expectation quality)
        d2_raw, d2_color = _d1_level(ind, forecast, currency)
        # Consumer/Business Confidence: negative forecast is NEVER bullish
        if ind in ("Consumer Confidence", "Business Confidence"):
            try:
                _fv = float(forecast) if forecast is not None else None
                _av = float(actual)   if actual   is not None else None
            except (TypeError, ValueError):
                _fv = None; _av = None
            if _fv is None:
                d2_label, d2_lc = "MIXED", C["muted"]
            elif _fv >= 0 and d2_raw in ("STRONG", "NORMAL"):
                d2_label, d2_lc = "BULLISH", C["green"]
            elif _av is not None and _fv > _av and _fv >= -20:
                # Negative but improving vs actual — still bearish context
                d2_label, d2_lc = "BEARISH", C["yellow"]
            elif _fv < -10 or (_av is not None and _fv <= _av):
                d2_label, d2_lc = "BEARISH", C["red"]
            else:
                d2_label, d2_lc = "MIXED", C["muted"]
        else:
            d2_label = (
                "BULLISH" if d2_raw in ("STRONG", "NORMAL") else
                "BEARISH" if d2_raw == "CRITICAL" else "MIXED"
            )
            d2_lc = C["green"] if d2_label == "BULLISH" else C["red"] if d2_label == "BEARISH" else C["muted"]
        # D3 — beat/miss intensity
        invert = LOWER_IS_BETTER.get(ind, False)
        d3_label, d3_color = _d3_intensity(ind, actual, forecast, invert=invert)
        # D4 — trend vs previous (5-level)
        d4_label, d4_color = _d4_trend(ind, actual, previous)

        # Row dot colour: composite of D1/D3/D4 scores
        _d1s = _L2S.get(d1_label, 0.0)
        _d3s = _L2S.get(d3_label, 0.0) if d3_label != "—" else None
        _d4s = _L2S.get(d4_label, 0.0) if d4_label not in ("—", "") else None
        _rparts = [(_d1s, 0.20)]
        if _d3s is not None: _rparts.append((_d3s, 0.35))
        if _d4s is not None: _rparts.append((_d4s, 0.30))
        _rtw  = sum(w for _, w in _rparts)
        _rc   = sum(s * w for s, w in _rparts) / _rtw if _rtw else 0.0
        dot_color = (C["green"]  if _rc >  0.5 else
                     C["teal"]   if _rc >  0.2 else
                     C["yellow"] if _rc > -0.2 else
                     "#f07820"   if _rc > -0.5 else
                     C["red"])

        left_border_color = (C["green"]  if _rc >  0.3 else
                             C["yellow"] if _rc > -0.3 else C["red"])

        tip = (
            f"D1 Level: {d1_label} ({_d1s:+.1f})  |  "
            f"D2 Forecast: {d2_label}  |  "
            f"D3 Beat/Miss: {d3_label}  |  "
            f"D4 Trend: {d4_label}"
        )

        body += (
            f"<tr style='border-bottom:1px solid {C['border']};background:{row_bg};"
            f"border-left:3px solid {left_border_color};'>"
            # Indicator + D1 level pill + tooltip
            f"<td style='padding:12px 10px;font-size:11px;color:{C['text']};"
            f"font-family:monospace;white-space:nowrap;' title='{tip}'>"
            f"{_src_dot(src, dot_color)} {ind}"
            f"<br><span style='display:inline-block;margin-top:3px;'>"
            f"{_level_pill(d1_label, d1_color)}</span></td>"
            # Actual
            f"<td style='padding:12px 10px;font-size:11px;color:{C['text']};"
            f"font-family:monospace;font-weight:600;'>{_fmt(actual)}</td>"
            # Previous
            f"<td style='padding:12px 10px;font-size:11px;color:{C['muted']};"
            f"font-family:monospace;'>{_fmt(previous)}</td>"
            # Forecast + D2 expectation pill
            f"<td style='padding:12px 10px;font-size:11px;color:{C['muted']};"
            f"font-family:monospace;'>{_fmt(forecast)}"
            f"<br><span style='display:inline-block;margin-top:3px;'>"
            f"{_level_pill(d2_label, d2_lc)}</span></td>"
            # D3 Beat/Miss intensity
            f"<td style='padding:12px 5px;white-space:nowrap;'>"
            f"{_intensity_cell(d3_label, d3_color)}</td>"
            # D4 Trend
            f"<td style='padding:12px 5px;white-space:nowrap;'>"
            f"{_intensity_cell(d4_label, d4_color)}</td>"
            # Release Date
            f"<td style='padding:12px 10px;font-size:10px;color:{C['muted']};"
            f"font-family:monospace;white-space:nowrap;'>{date_str}{upcoming_badge}</td>"
            # Impact
            f"<td style='padding:12px 5px;'>{_impact_pill(row['impact'])}</td>"
            f"</tr>"
        )

    return (
        f"<div style='background:{C['card']};border:1px solid {C['border']};"
        f"border-radius:10px;overflow-x:auto;max-height:520px;overflow-y:auto;'>"
        f"<table style='width:100%;border-collapse:collapse;'>"
        f"<thead>{hdr}</thead><tbody>{body}</tbody>"
        f"</table></div>"
    )




# ── Comparable indicators for cross-currency G8 z-score comparison ────────────
_REL_INDICATORS: dict[str, tuple[str, float]] = {
    "CPI m/m":              ("high_good", 1.5),
    "Interest Rate":        ("high_good", 2.0),
    "GDP Growth":           ("high_good", 1.5),
    "Unemployment Rate":    ("low_good",  1.5),
    "Manufacturing PMI":    ("high_good", 1.0),
    "Services PMI":         ("high_good", 1.0),
    "Retail Sales":         ("high_good", 1.0),
    "Wage Growth":          ("high_good", 1.2),
    "Core CPI":             ("high_good", 1.2),
    "Industrial Production":("high_good", 0.8),
    "M2 Money Supply":      ("high_good", 0.5),
    "Trade Balance":        ("high_good", 0.7),
}
# Invert z-score for indicators where lower value = better for FX
_LOWER_BETTER_REL: frozenset[str] = frozenset({"Unemployment Rate"})


def calc_relative_score(
    all_histories: dict[str, dict[str, list[float]]],
) -> dict[str, float]:
    """
    Cross-currency G8 relative scoring using 6-month historical data.

    For each comparable indicator, compute the G8 average over 6 months,
    then z-score each currency relative to that average. Currencies with
    better-than-average data score positive; worse score negative.

    Returns {ccy: score} where score ∈ [-3.0, +3.0].
    """
    import math

    MONTH_WEIGHTS = [0.5, 0.7, 0.9, 1.1, 1.3, 1.5]  # recent months weighted more

    ccy_scores: dict[str, list[tuple[float, float]]] = {ccy: [] for ccy in all_histories}

    for ind, (_interp, weight) in _REL_INDICATORS.items():
        for m_idx in range(6):
            vals: dict[str, float] = {}
            for ccy, hist in all_histories.items():
                if ind in hist and len(hist[ind]) > m_idx:
                    try:
                        vals[ccy] = float(hist[ind][m_idx])
                    except (TypeError, ValueError):
                        pass

            if len(vals) < 4:   # need at least half of G8 for meaningful comparison
                continue

            g8_vals  = list(vals.values())
            g8_mean  = sum(g8_vals) / len(g8_vals)
            variance = sum((x - g8_mean) ** 2 for x in g8_vals) / len(g8_vals)
            g8_std   = math.sqrt(variance) if variance > 0 else None
            if g8_std is None or g8_std < 1e-6:
                continue  # no variance → skip

            mw = MONTH_WEIGHTS[m_idx]
            for ccy, v in vals.items():
                z = (v - g8_mean) / g8_std
                if ind in _LOWER_BETTER_REL:
                    z = -z
                z = max(-3.0, min(3.0, z))
                ccy_scores[ccy].append((z * weight, weight * mw))

    result: dict[str, float] = {}
    for ccy, entries in ccy_scores.items():
        if not entries:
            result[ccy] = 0.0
            continue
        total_w = sum(w for _, w in entries)
        raw     = sum(s * w for s, w in entries) / total_w if total_w > 0 else 0.0
        result[ccy] = round(max(-3.0, min(3.0, raw)), 3)

    return result


@st.cache_data(ttl=TTL_NEWS_CTX, show_spinner=False)
def fetch_d3_d4_news() -> dict[str, dict[str, float]]:
    """
    Fetch same-day CB policy news (D3 web adjustment) and general fundamental
    news (D4 adjustment) for all 8 currencies via Google News RSS.
    Returns {"d3": {ccy: adj ∈ [-1,+1]}, "d4": {ccy: adj ∈ [-1,+1]}}.
    Falls back to 0.0 per currency silently on any failure.
    """
    import urllib.parse

    empty: dict[str, float] = {c: 0.0 for c in SUPPORTED_CURRENCIES}
    if not _FEEDPARSER:
        return {"d3": dict(empty), "d4": dict(empty)}

    def _fetch(query: str) -> list[str]:
        try:
            url = (
                "https://news.google.com/rss/search?q="
                + urllib.parse.quote_plus(query)
                + "&hl=en-US&gl=US&ceid=US:en"
            )
            feed = feedparser.parse(url)
            return [
                getattr(e, "title", "") + " " + getattr(e, "summary", "")
                for e in (feed.entries or [])[:6]
            ]
        except Exception:
            return []

    def _hawk_dove(texts: list[str]) -> float:
        """Return hawkish/dovish net score ∈ {-1.0, -0.5, 0.0, +0.5, +1.0}."""
        if not texts:
            return 0.0
        hawk = sum(1 for t in texts if any(k in t.lower() for k in _CB_HAWK_KW))
        dove = sum(1 for t in texts if any(k in t.lower() for k in _CB_DOVE_KW))
        net  = hawk - dove
        if net >= 2:   return  1.0
        if net == 1:   return  0.5
        if net == -1:  return -0.5
        if net <= -2:  return -1.0
        return 0.0

    d3_adj: dict[str, float] = {}
    d4_adj: dict[str, float] = {}
    for ccy in SUPPORTED_CURRENCIES:
        d3_adj[ccy] = _hawk_dove(_fetch(_D3_CB_QUERIES[ccy]))
        d4_adj[ccy] = _hawk_dove(_fetch(_D4_NEWS_QUERIES[ccy]))
    return {"d3": d3_adj, "d4": d4_adj}


def calc_4d_bias(
    indicators_df: pd.DataFrame,
    currency: str,
    bias_old: dict,
    d3_score: float,
    d4_news_adj: float,
    relative_score: float | None = None,
) -> dict:
    """
    4-Dimensional currency bias score. Each dimension ∈ [-3, +3].
    D1 (25%): Current indicator values vs fundamental benchmarks
    D2 (25%): Beat/miss + trend momentum  (reuses calc_bias_score d3/d4 × 3)
    D3 (25%): Next CB action pricing + today's web adjustment
    D4 (25%): Structural geo/rate/inflation context + live news adjustment
    Final = (D1 + D2 + D3 + D4) / 4  ∈ [-3, +3]
    """
    def _f(v):
        try: return None if v is None else float(v)
        except Exception: return None

    _IMP_W = {"High": 0.8, "Medium": 0.6, "Low": 0.3, "Critical": 1.0}

    # ── D1: Current value vs benchmarks ──────────────────────────────────────
    def _d1_bench(ind: str, v: float, prev: float | None) -> float:
        if ind == "Interest Rate":
            if v > 3.0:  return min( 3.0,  2.0 + (v - 3.0) * 0.67)
            if v >= 1.0: return (v - 1.0) / 2.0
            return max(-2.5, -1.5 - (1.0 - v))

        if ind == "CPI m/m":
            ann = v * 12  # annualise
            if abs(ann - 2.0) <= 0.5: return  1.0
            if ann > 3.0:  return max(-2.0, -1.0 - (ann - 3.0) * 0.25)
            if ann < 1.0:  return max(-2.5, -1.5 - (1.0 - ann))
            return 0.3

        if ind == "GDP Growth":
            if v > 2.0:  return min( 2.5, 1.5 + (v - 2.0) * 0.5)
            if v >= 1.0: return v - 1.0
            return max(-2.0, -1.0 - (1.0 - v) * 0.5)

        if ind == "Unemployment Rate":
            if v < 4.0:  return min(2.0, 1.5 + (4.0 - v) * 0.25)
            if v <= 6.0: return (6.0 - v) / 2.0
            return max(-2.0, -1.0 - (v - 6.0) * 0.25)

        if ind in ("Manufacturing PMI", "Services PMI"):
            if v > 52:   return min(2.0, 1.0 + (v - 52) * 0.25)
            if v >= 48:  return 0.0
            return max(-2.0, -1.0 - (48 - v) * 0.25)

        if ind in ("Trade Balance", "Current Account"):
            # Graduated scale with tighter cap — avoids economies being
            # over-rewarded/penalised for absolute balance size vs GDP
            if v > 10:   return  1.0
            if v >  0:   return  0.5
            if v > -10:  return -0.5
            return       -1.0

        if ind == "Retail Sales":
            if v >  0.5: return  1.5
            if v >  0.0: return  0.5
            if v >= -0.5: return -0.5
            return -1.5

        if ind == "PPI":
            if 1.0 <= v <= 4.0: return  0.5
            if v < 0:           return -0.5
            return 0.0

        if ind == "Wage Growth":
            if v > 4.5:  return  0.0   # potentially inflationary
            if v >= 3.0: return  1.0
            if v >= 2.0: return  0.5
            if v >= 1.0: return  0.0
            return -0.5

        if ind in ("Consumer Confidence", "Business Confidence"):
            if v >  5:   return  1.5
            if v >= 0:   return  0.5
            if v >= -20: return -0.5
            return -1.5

        if ind == "Government Debt":
            if v > 100:  return -1.0
            if v >  50:  return -0.5 - (v - 50) / 100 * 0.5
            return 0.0

        if ind in ("Budget Balance", "Building Permits"):
            if prev is not None:
                return 0.5 if v > prev else -0.5
            return 0.0

        if ind == "Core CPI":
            ann = v * 12
            if abs(ann - 2.0) <= 0.5: return  1.0
            if ann > 3.0:  return max(-2.0, -1.0 - (ann - 3.0) * 0.25)
            if ann < 1.0:  return max(-2.5, -1.5 - (1.0 - ann))
            return 0.3
        if ind == "Employment Change":
            if v > 200:  return  2.0
            if v > 100:  return  1.0
            if v > 0:    return  0.5
            if v > -50:  return -1.0
            return -2.0
        if ind == "Industrial Production":
            if v > 0.5:  return  1.5
            if v >= 0:   return  0.5
            if v >= -0.5: return -0.5
            return -1.5
        if ind == "M2 Money Supply":
            if v > 5.0:  return -0.5
            if v > 2.0:  return  0.5
            if v > 0.0:  return  0.3
            return -0.5

        return 0.0

    if relative_score is not None:
        # Use cross-currency G8 relative score as D1 (already ∈ [-3, +3])
        d1_raw = relative_score
    else:
        d1_num, d1_den = 0.0, 0.0
        for _, row in indicators_df.iterrows():
            a = _f(row.get("actual"))
            p = _f(row.get("previous"))
            if a is None:
                continue
            w = _IMP_W.get(str(row.get("impact", "Medium")), 0.5)
            d1_num += _d1_bench(row["indicator"], a, p) * w
            d1_den += w
        d1_raw = d1_num / d1_den if d1_den else 0.0
    d1 = round(max(-3.0, min(3.0, d1_raw)), 3)

    # ── D2: Beat/miss + trend (existing d3/d4 aggregates scaled ×3) ──────────
    d2_raw = (bias_old.get("d3", 0.0) + bias_old.get("d4", 0.0)) / 2.0
    d2     = round(max(-3.0, min(3.0, d2_raw * 3.0)), 3)

    # ── D3: CB action pricing + today's web adjustment ────────────────────────
    d3 = round(max(-3.0, min(3.0, d3_score)), 3)

    # ── D4: Structural geopolitical + live news ───────────────────────────────
    d4 = round(max(-3.0, min(3.0,
        _D4_STRUCTURAL.get(currency, 0.0) + d4_news_adj)), 3)

    # ── Final: simple average of 4 equal dimensions ───────────────────────────
    final = round(max(-3.0, min(3.0, (d1 + d2 + d3 + d4) / 4.0)), 3)

    # ── Classification (new 5-level thresholds, scale −3 to +3) ──────────────
    if   final >= 2.0:  level, lc = "STRONG BULLISH", "#00a36c"
    elif final >= 0.8:  level, lc = "SLIGHT BULLISH", C["green"]
    elif final >= 0.0:  level, lc = "MILD BULLISH",   "#4ecb9e"
    elif final > -0.7:  level, lc = "MILD BEARISH",   C["yellow"]
    elif final >= -2.0: level, lc = "SLIGHT BEARISH",  "#f08080"
    else:               level, lc = "STRONG BEARISH",  C["red"]

    return {
        "total": final, "level": level, "level_color": lc,
        "dim1": d1, "dim2": d2, "dim3": d3, "dim4": d4,
    }


# NOTE: Pair divergence panel removed from Macro Dashboard.
# It will be part of Module 4 (Correlation / Geo Scanner).


def render_all_currencies_overview(selected_ccy: str) -> str:
    """
    Build the All Currencies Bias panel using cached session_state scores.
    Shows all 8 currencies ranked strongest → weakest with color-coded bias labels.
    Falls back to static-only scores if session_state not populated.
    """
    rows_data = []
    for ccy in SUPPORTED_CURRENCIES:
        cached = st.session_state.get(f"macro_scores_{ccy}")
        if cached and cached.get("fmt") == "4d":
            total = cached["total"]
            level = cached["level"]
        else:
            static_rows = []
            for ind in INDICATOR_ORDER:
                fb = STATIC_INDICATORS.get(ccy, {}).get(ind, {})
                if fb:
                    static_rows.append({
                        "indicator": ind,
                        "actual":   fb.get("actual"),
                        "previous": fb.get("previous"),
                        "forecast": fb.get("forecast"),
                        "impact":   fb.get("impact", "Low"),
                    })
            if static_rows:
                import pandas as _pd
                tmp_df = _pd.DataFrame(static_rows)
                _b = calc_bias_score(tmp_df, ccy)
                total = _b["total"]
                level = _b["level"]
            else:
                total = 0.0
                level = "MILD BEARISH"
        rows_data.append({"ccy": ccy, "total": total, "level": level})

    rows_data.sort(key=lambda x: x["total"], reverse=True)

    _LEVEL_COLOR = {
        "STRONG BULLISH": "#00a36c",
        "SLIGHT BULLISH": C["green"],
        "MILD BULLISH":   "#4ecb9e",
        "MILD BEARISH":   C["yellow"],
        "SLIGHT BEARISH": "#f08080",
        "STRONG BEARISH": C["red"],
    }

    rows_html = ""
    for item in rows_data:
        ccy   = item["ccy"]
        total = item["total"]
        level = item["level"]
        lc    = _LEVEL_COLOR.get(level, C["muted"])
        flag  = CURRENCY_FLAG.get(ccy, "")
        sign  = "+" if total > 0 else ""
        is_selected = ccy == selected_ccy
        bg    = C["teal_bg"] if is_selected else "transparent"
        border = f"border-left:3px solid {lc};" if not is_selected else f"border-left:3px solid {C['teal']};"

        bar_pct = max(2.0, min(98.0, (total + 1.0) / 2.0 * 100))
        bar_color = lc

        rows_html += (
            f"<div style='padding:10px 12px;border-bottom:1px solid {C['border']};background:{bg};{border}'>"
            f"<div style='display:flex;align-items:center;justify-content:space-between;margin-bottom:6px;'>"
            f"<div style='display:flex;align-items:center;gap:8px;'>"
            f"<span style='font-size:16px;'>{flag}</span>"
            f"<span style='font-size:13px;font-weight:800;color:{C['text']};font-family:monospace;'>{ccy}</span>"
            + (f"<span style=\"font-size:8px;color:{C['teal']};font-family:monospace;font-weight:700;margin-left:4px;\">◆ SELECTED</span>" if is_selected else "")
            + f"</div>"
            f"<div style='text-align:right;'>"
            f"<span style='font-size:11px;font-weight:800;color:{lc};font-family:monospace;'>{sign}{total:.2f}</span>"
            f"</div>"
            f"</div>"
            f"<div style='display:flex;align-items:center;gap:8px;'>"
            f"<div style='flex:1;height:4px;border-radius:2px;background:{C['dim']};'>"
            f"<div style='height:4px;border-radius:2px;background:{bar_color};width:{bar_pct:.0f}%;'></div>"
            f"</div>"
            f"<span style='font-size:8px;font-family:monospace;font-weight:700;color:{lc};"
            f"letter-spacing:0.5px;white-space:nowrap;'>{level}</span>"
            f"</div>"
            f"</div>"
        )

    return (
        f"<div style='background:{C['card']};border:1px solid {C['border']};border-radius:10px;overflow:hidden;'>"
        f"<div style='padding:10px 14px;border-bottom:1px solid {C['border']};'>"
        f"<div style='font-size:9px;color:{C['muted']};font-family:monospace;letter-spacing:2px;text-transform:uppercase;'>Currency Bias Ranking</div>"
        f"</div>"
        f"{rows_html}"
        f"<div style='padding:6px 12px;font-size:9px;color:{C['muted']};font-family:monospace;border-top:1px solid {C['border']};'>Score range: −1.0 to +1.0 · Navigate currencies above to update</div>"
        f"</div>"
    )


# ╔══════════════════════════════════════════════════════════════════════════════
# ║  MAIN
# ╚══════════════════════════════════════════════════════════════════════════════

def main():
    st.set_page_config(
        page_title="Economic Bias Engine · Trading Terminal",
        page_icon="🗓️",
        layout="wide",
        initial_sidebar_state="collapsed",
    )

    st.markdown(f"""
    <style>
      html, body, [data-testid="stAppViewContainer"],
      [data-testid="stHeader"], [data-testid="stToolbar"],
      [data-testid="stDecoration"] {{
          background-color:{C['bg']} !important;
      }}
      section[data-testid="stSidebar"] {{ display:none !important; }}
      .stMainBlockContainer {{
          padding-top:3rem !important; padding-bottom:2rem !important;
      }}
      /* ── Radio → pill tabs (currency selector + news filter) ── */
      div[data-testid="stRadio"] > label {{ display:none !important; }}
      div[data-testid="stRadio"] > div[role="radiogroup"] {{
          display:flex !important; flex-wrap:wrap !important;
          gap:6px !important; background:transparent !important;
      }}
      div[data-testid="stRadio"] label {{
          background:{C['dim']} !important;
          border:1px solid {C['border']} !important;
          border-radius:20px !important; padding:5px 14px !important;
          cursor:pointer !important; font-family:monospace !important;
          font-size:12px !important; font-weight:600 !important;
          color:{C['muted']} !important; margin:0 !important;
      }}
      div[data-testid="stRadio"] label:has(input:checked) {{
          background:{C['teal']} !important;
          border-color:{C['teal']} !important; color:#0a0c10 !important;
      }}
      div[data-testid="stRadio"] label input {{ display:none !important; }}
      div[data-testid="stRadio"] label > div,
      div[data-testid="stRadio"] label > div > p {{
          display:inline !important; font-family:monospace !important;
          font-size:12px !important; font-weight:600 !important;
      }}
      /* ── Currency selector + other secondary buttons ── */
      button[kind="secondary"] {{
          background:{C['dim']} !important; color:{C['muted']} !important;
          border:1px solid {C['border']} !important;
          font-family:monospace !important; font-weight:600 !important;
          border-radius:20px !important;
      }}
      button[kind="secondary"]:hover {{
          border-color:{C['teal']} !important; color:{C['teal']} !important;
      }}
      /* Active currency button (type="primary") */
      button[kind="primary"] {{
          background:{C['teal']} !important; color:#0a0c10 !important;
          border:1px solid {C['teal']} !important;
          font-family:monospace !important; font-weight:700 !important;
          border-radius:20px !important;
      }}
      button[kind="primary"]:hover {{
          background:{C['teal']} !important; opacity:0.9 !important;
      }}
      button[kind="secondary"]:hover {{ border-color:{C['teal']} !important; }}
      button[kind="primary"] {{
          background:{C['teal']} !important; color:#0a0c10 !important;
          border:none !important; font-weight:700 !important;
          font-family:monospace !important;
      }}
      p, span, label {{ color:{C['text']}; }}
      /* Spinner text */
      div[data-testid="stSpinner"] p {{ color:{C['muted']} !important;
          font-family:monospace !important; font-size:12px !important; }}
      /* Equal-height columns — both columns stretch to the taller one */
      div[data-testid="stHorizontalBlock"] {{
          align-items: stretch !important;
      }}
      div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] {{
          display: flex !important;
          flex-direction: column !important;
      }}
    </style>
    """, unsafe_allow_html=True)

    # ── Session state & auto-refresh timer ────────────────────────────────────
    _now = time.time()
    if "mf_currency" not in st.session_state:
        st.session_state.mf_currency = "USD"
    if "last_refresh_ts" not in st.session_state:
        st.session_state.last_refresh_ts = _now
    if "release_refreshed_events" not in st.session_state:
        st.session_state.release_refreshed_events = set()

    # Auto-rerun every AUTO_RERUN_INTERVAL seconds — clears fast-moving caches
    if _now - st.session_state.last_refresh_ts > AUTO_RERUN_INTERVAL:
        fetch_news_context_scores.clear()
        fetch_fundamental_scores.clear()
        fetch_d3_d4_news.clear()
        st.session_state.last_refresh_ts = _now
        st.rerun()

    # ── Title row ──────────────────────────────────────────────────────────────
    col_back, col_title, _ = st.columns([2, 5, 2])
    with col_back:
        if st.button("← Back to Hub"):
            st.switch_page("app.py")
    with col_title:
        st.markdown(
            f"<div style='text-align:center;'>"
            f"<div style='font-size:20px;font-weight:800;color:{C['text']};"
            f"font-family:monospace;letter-spacing:-0.5px;'>ECONOMIC BIAS ENGINE</div>"
            f"<div style='font-size:11px;color:{C['muted']};font-family:monospace;"
            f"letter-spacing:1px;margin-top:3px;'>"
            f"Monthly Data · 6M Trend · G8 Relative Scoring · Live</div></div>",
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)

    # ── Currency selector ─────────────────────────────────────────────────────
    currency = st.session_state.mf_currency

    st.markdown(
        f"<div style='font-size:10px;color:{C['muted']};font-family:monospace;"
        f"text-transform:uppercase;letter-spacing:1.5px;margin-bottom:6px;'>"
        f"Select Currency</div>",
        unsafe_allow_html=True,
    )
    _ccy_cols = st.columns(len(SUPPORTED_CURRENCIES))
    for _ci, _ccy in enumerate(SUPPORTED_CURRENCIES):
        _is_active = (_ccy == currency)
        _flag  = CURRENCY_FLAG.get(_ccy, "")
        _label = f"● {_flag} {_ccy}" if _is_active else f"○ {_flag} {_ccy}"
        with _ccy_cols[_ci]:
            if st.button(
                _label,
                key=f"ccy_btn_{_ccy}",
                type="primary" if _is_active else "secondary",
                use_container_width=True,
            ):
                st.session_state.mf_currency = _ccy
                currency = _ccy
                st.rerun()

    st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)

    # ── Data fetch — indicators ───────────────────────────────────────────────
    # Official API data
    official: dict = {}
    with st.spinner("⏳ Fetching official API data…"):
        if currency == "USD":
            official = fetch_fred_indicators(FRED_API_KEY)
        else:
            # Layer 1: Trading Economics scrape (broadest coverage for all non-USD)
            official = dict(fetch_te_indicators(currency))
            # Layer 2: higher-authority sources override TE where available
            if currency == "EUR":
                ecb_rate = fetch_ecb_rate()
                if ecb_rate:
                    official["Interest Rate"] = ecb_rate
                ecb_cpi = fetch_ecb_cpi()
                if ecb_cpi:
                    official["CPI m/m"] = ecb_cpi
            elif currency == "GBP":
                boe_rate = fetch_boe_rate()
                if boe_rate:
                    official["Interest Rate"] = boe_rate

    indicators_df, ind_source = build_indicators_table(currency, official)

    bias = calc_bias_score(indicators_df, currency)

    # ── 4-Dimensional bias computation ────────────────────────────────────────
    with st.spinner("⏳ Fetching CB signals & news…"):
        _d3d4 = fetch_d3_d4_news()

    # D3 = base CB pricing + same-day web adjustment
    _d3_score   = _D3_BASE.get(currency, 0.0) + _d3d4["d3"].get(currency, 0.0)
    _d4_news    = _d3d4["d4"].get(currency, 0.0)

    # ── Compute cross-currency relative scores (G8 comparison) ───────────────
    if ("rel_scores" not in st.session_state or
            time.time() - st.session_state.get("rel_scores_ts", 0) > TTL_INDICATORS):
        _all_hist = {ccy: STATIC_HISTORY.get(ccy, {}) for ccy in SUPPORTED_CURRENCIES}
        st.session_state["rel_scores"]    = calc_relative_score(_all_hist)
        st.session_state["rel_scores_ts"] = time.time()
    _rel_scores = st.session_state.get("rel_scores", {})
    _rel_score  = _rel_scores.get(currency, None)

    bias4d = calc_4d_bias(indicators_df, currency, bias, _d3_score, _d4_news, relative_score=_rel_score)

    # Export 4D scores to session_state (used by Module 4 + cross-currency divergence)
    st.session_state[f"macro_scores_{currency}"] = {
        "total":    bias4d["total"],
        "level":    bias4d["level"],
        "dim1":     bias4d.get("dim1", 0.0),
        "dim2":     bias4d.get("dim2", 0.0),
        "dim3":     bias4d.get("dim3", 0.0),
        "dim4":     bias4d.get("dim4", 0.0),
        "currency": currency,
        "fmt":      "4d",
    }

    # ── Pre-compute 4D scores for ALL currencies using static data ────────────
    # This ensures the ranking panel always shows proper 4D scores (incl. rate
    # differential and CB pricing) — not just raw indicator quality metrics.
    for _other_ccy in SUPPORTED_CURRENCIES:
        if f"macro_scores_{_other_ccy}" not in st.session_state:
            _o_rows = []
            for _ind in INDICATOR_ORDER:
                _fb = STATIC_INDICATORS.get(_other_ccy, {}).get(_ind, {})
                if _fb:
                    _o_rows.append({
                        "indicator": _ind,
                        "actual":    _fb.get("actual"),
                        "previous":  _fb.get("previous"),
                        "forecast":  _fb.get("forecast"),
                        "impact":    _fb.get("impact", "Low"),
                    })
            if _o_rows:
                import pandas as _pd_tmp
                _o_df   = _pd_tmp.DataFrame(_o_rows)
                _o_bias = calc_bias_score(_o_df, _other_ccy)
                _o_d3   = _D3_BASE.get(_other_ccy, 0.0) + _d3d4["d3"].get(_other_ccy, 0.0)
                _o_d4n  = _d3d4["d4"].get(_other_ccy, 0.0)
                _o_4d   = calc_4d_bias(_o_df, _other_ccy, _o_bias, _o_d3, _o_d4n, relative_score=_rel_scores.get(_other_ccy))
                st.session_state[f"macro_scores_{_other_ccy}"] = {
                    "total":    _o_4d["total"],
                    "level":    _o_4d["level"],
                    "dim1":     _o_4d.get("dim1", 0.0),
                    "dim2":     _o_4d.get("dim2", 0.0),
                    "dim3":     _o_4d.get("dim3", 0.0),
                    "dim4":     _o_4d.get("dim4", 0.0),
                    "currency": _other_ccy,
                    "fmt":      "4d",
                }

    # Merge indicator breakdown tags for the bias panel (from calc_bias_score)
    bias4d["scores"] = bias.get("scores", [])

    # Override display fields in bias dict for render_bias_panel
    bias = dict(bias)
    bias["total"]       = bias4d["total"]
    bias["level"]       = bias4d["level"]
    bias["level_color"] = bias4d["level_color"]
    bias["dim1"]        = bias4d.get("dim1", 0.0)
    bias["dim2"]        = bias4d.get("dim2", 0.0)
    bias["dim3"]        = bias4d.get("dim3", 0.0)
    bias["dim4"]        = bias4d.get("dim4", 0.0)

    # ── Bias panel ────────────────────────────────────────────────────────────
    st.markdown(render_bias_panel(currency, bias, ind_source), unsafe_allow_html=True)
    st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)

    # ── Status bar + manual refresh button ────────────────────────────────────
    age_secs   = int(_now - st.session_state.last_refresh_ts)
    age_str    = f"{age_secs // 60}m {age_secs % 60}s ago" if age_secs >= 60 else f"{age_secs}s ago"
    status_parts = [
        f"{CURRENCY_FLAG.get(currency,'')} {currency}",
        f"Source: {ind_source}",
        f"Last updated: {age_str}",
    ]

    col_status, col_btn = st.columns([11, 1])
    with col_status:
        st.markdown(
            f"<div style='font-size:11px;color:{C['muted']};font-family:monospace;"
            f"margin-bottom:18px;padding-top:6px;'>"
            f"{' &nbsp;·&nbsp; '.join(status_parts)}</div>",
            unsafe_allow_html=True,
        )
    with col_btn:
        if st.button("🔄", key="manual_refresh", help="Clear all caches and reload data"):
            fetch_fred_indicators.clear()
            fetch_ecb_rate.clear()
            fetch_ecb_cpi.clear()
            fetch_boe_rate.clear()
            fetch_te_indicators.clear()
            fetch_fundamental_scores.clear()
            fetch_news_context_scores.clear()
            fetch_d3_d4_news.clear()
            st.session_state.last_refresh_ts = time.time()
            st.rerun()

    # ── Two-column layout ─────────────────────────────────────────────────────
    col_left, col_right = st.columns([3, 2], gap="medium")

    # LEFT — Macro Indicators
    with col_left:
        st.markdown(_section_header(f"Macro Indicators — {currency}"), unsafe_allow_html=True)
        _cg = C["green"]; _cy = C["yellow"]; _cm2 = C["muted"]
        st.markdown(
            f"<div style='font-size:10px;color:{C['muted']};font-family:monospace;"
            f"margin-bottom:8px;'>"
            f"<span style='color:{_cg};'>●</span> Live/fresh "
            f"&nbsp; <span style='color:{_cy};'>●</span> Stale "
            f"&nbsp; <span style='color:{_cm2};'>◎</span> Static fallback</div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            f"<div style='display:flex;flex-direction:column;flex:1;'>"
            + render_indicators_table(indicators_df, st.session_state.last_refresh_ts, currency)
            + "</div>",
            unsafe_allow_html=True,
        )

    # RIGHT — All Currencies Bias Ranking
    with col_right:
        st.markdown(_section_header("All Currencies — Bias Ranking"), unsafe_allow_html=True)
        st.markdown(render_all_currencies_overview(currency), unsafe_allow_html=True)

    # ── Footer ─────────────────────────────────────────────────────────────────
    st.markdown(
        f"<div style='margin-top:48px;padding-top:16px;"
        f"border-top:1px solid {C['border']};text-align:center;"
        f"font-size:11px;color:{C['muted']};font-family:monospace;'>"
        f"Built by @realedgetraders</div>",
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
