"""
Trading Analytics Terminal — Module 3: Economic Bias Engine
Currency-filtered macro scanner: 12-month indicator trend analysis
"""

import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

import pandas as pd
import plotly.graph_objects as go
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
# ║  Set via st.secrets (Streamlit Cloud) or FRED_API_KEY env var (local).
# ╚══════════════════════════════════════════════════════════════════════════════
import os as _os
FRED_API_KEY: str = (
    st.secrets.get("FRED_API_KEY", "")
    if hasattr(st, "secrets")
    else _os.environ.get("FRED_API_KEY", "")
)

# ── Refresh intervals ─────────────────────────────────────────────────────────
AUTO_RERUN_INTERVAL = 300   # 5 min — auto-rerun timer (seconds)
TTL_INDICATORS      = 3600  # 1 h   — FRED / ECB cache TTL
TTL_NEWS            = 300   # 5 min — RSS news cache TTL
TTL_HISTORY         = 3600  # 1 h   — 12M history fetch cache TTL

# ── Colour palette (matches app.py exactly) ──────────────────────────────────
C = {
    "bg":       "#0d0d0d",
    "card":     "#141414",
    "border":   "#252525",
    "panel":    "#111111",
    "dim":      "#171717",
    "text":     "#e8e8e8",
    "muted":    "#666666",
    "teal":     "#e63946",
    "teal_bg":  "rgba(230,57,70,0.12)",
    "teal_dim": "rgba(230,57,70,0.06)",
    "green":    "#1a9b6a",
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
    "Composite PMI": False,
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
    "Manufacturing PMI", "Services PMI", "Composite PMI", "Trade Balance", "Retail Sales",
    "Current Account", "Wage Growth", "PPI", "Consumer Confidence",
    "Government Debt", "Core CPI", "Employment Change", "Industrial Production",
    "M2 Money Supply",
    # Extended — table only
    "Budget Balance", "Building Permits", "Business Confidence",
]

# ── FRED API config ────────────────────────────────────────────────────────────
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

# ── Investing.com economic calendar constants ─────────────────────────────────
_INV_HDR = {
    "User-Agent":       "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "X-Requested-With": "XMLHttpRequest",
    "Referer":          "https://www.investing.com/economic-calendar/",
    "Accept":           "application/json, text/javascript, */*; q=0.01",
    "Accept-Language":  "en-US,en;q=0.9",
}
_INV_URL = "https://www.investing.com/economic-calendar/Service/getCalendarFilteredData"
_INV_CCY_CODE: dict[str, str] = {
    "USD": "5",
    "EUR": "72", "GBP": "4",  "JPY": "35", "AUD": "25",
    "CAD": "6",  "CHF": "11", "NZD": "43",
}

# Investing.com event name fragments → our indicator keys (longest-first for matching)
_INV_NAME_MAP: list[tuple[str, str]] = sorted([
    ("manufacturing pmi",           "Manufacturing PMI"),
    ("services pmi",                "Services PMI"),
    ("composite pmi",               "Composite PMI"),
    ("s&p global manufacturing",    "Manufacturing PMI"),
    ("s&p global services",         "Services PMI"),
    ("s&p global composite",        "Composite PMI"),
    ("hcob eurozone manufacturing", "Manufacturing PMI"),
    ("hcob eurozone services",      "Services PMI"),
    ("hcob eurozone composite",     "Composite PMI"),
    ("jibun bank manufacturing",    "Manufacturing PMI"),
    ("jibun bank services",         "Services PMI"),
    ("nab business confidence",     "Business Confidence"),
    ("westpac consumer confidence", "Consumer Confidence"),
    ("consumer confidence",         "Consumer Confidence"),
    ("business confidence",         "Business Confidence"),
    ("industrial production",       "Industrial Production"),
    ("retail sales mom",            "Retail Sales"),
    ("retail sales m/m",            "Retail Sales"),
    ("retail sales",                "Retail Sales"),
    ("core retail sales",           "Retail Sales"),
    ("unemployment rate",           "Unemployment Rate"),
    ("claimant count",              "Unemployment Rate"),
    ("gdp annualized",              "GDP Growth"),
    ("gdp q/q",                     "GDP Growth"),
    ("gdp qoq",                     "GDP Growth"),
    ("gdp",                         "GDP Growth"),
    ("core cpi",                    "Core CPI"),
    ("cpi y/y",                     "CPI YoY"),
    ("cpi yoy",                     "CPI YoY"),
    ("cpi m/m",                     "CPI m/m"),
    ("cpi mom",                     "CPI m/m"),
    ("cpi",                         "CPI m/m"),
    ("ppi",                         "PPI"),
    ("interest rate",               "Interest Rate"),
    ("ivey pmi",                    "Manufacturing PMI"),
    ("tankan",                      "Business Confidence"),
    ("ifo",                         "Business Confidence"),
    ("zew",                         "Business Confidence"),
], key=lambda x: len(x[0]), reverse=True)

# ── Trading Economics historical page map ─────────────────────────────────────
# Maps currency → {indicator_name: (country_slug, indicator_slug)}
# Used by fetch_te_history() to scrape 12-month historical data
_TE_HISTORY_MAP: dict[str, dict[str, tuple[str, str]]] = {
    "EUR": {
        "Manufacturing PMI":     ("euro-area", "manufacturing-pmi"),
        "Services PMI":          ("euro-area", "services-pmi"),
        "Consumer Confidence":   ("euro-area", "consumer-confidence"),
        "Business Confidence":   ("euro-area", "business-confidence"),
        "GDP Growth":            ("euro-area", "gdp-growth-rate"),
        "Retail Sales":          ("euro-area", "retail-sales-mom"),
        "Industrial Production": ("euro-area", "industrial-production"),
        "Core CPI":              ("euro-area", "core-inflation-rate"),
        "PPI":                   ("euro-area", "producer-prices-change"),
    },
    "GBP": {
        "Manufacturing PMI":     ("united-kingdom", "manufacturing-pmi"),
        "Services PMI":          ("united-kingdom", "services-pmi"),
        "Consumer Confidence":   ("united-kingdom", "consumer-confidence"),
        "Business Confidence":   ("united-kingdom", "business-confidence"),
        "GDP Growth":            ("united-kingdom", "gdp-growth-rate"),
        "Retail Sales":          ("united-kingdom", "retail-sales-mom"),
        "Industrial Production": ("united-kingdom", "industrial-production"),
        "Core CPI":              ("united-kingdom", "core-inflation-rate"),
        "PPI":                   ("united-kingdom", "producer-prices-change"),
    },
    "JPY": {
        "Manufacturing PMI":     ("japan", "manufacturing-pmi"),
        "Services PMI":          ("japan", "services-pmi"),
        "Consumer Confidence":   ("japan", "consumer-confidence"),
        "Business Confidence":   ("japan", "business-confidence"),
        "GDP Growth":            ("japan", "gdp-growth-rate"),
        "Retail Sales":          ("japan", "retail-sales-annual"),
        "Industrial Production": ("japan", "industrial-production"),
        "Core CPI":              ("japan", "core-inflation-rate"),
        "PPI":                   ("japan", "producer-prices-change"),
    },
    "AUD": {
        "Manufacturing PMI":     ("australia", "manufacturing-pmi"),
        "Services PMI":          ("australia", "services-pmi"),
        "Consumer Confidence":   ("australia", "consumer-confidence"),
        "Business Confidence":   ("australia", "business-confidence"),
        "GDP Growth":            ("australia", "gdp-growth-rate"),
        "Retail Sales":          ("australia", "retail-sales-mom"),
        "Industrial Production": ("australia", "industrial-production"),
        "Core CPI":              ("australia", "core-inflation-rate"),
        "PPI":                   ("australia", "producer-prices-change"),
    },
    "CAD": {
        "Manufacturing PMI":     ("canada", "manufacturing-pmi"),
        "Services PMI":          ("canada", "services-pmi"),
        "Consumer Confidence":   ("canada", "consumer-confidence"),
        "Business Confidence":   ("canada", "business-confidence"),
        "GDP Growth":            ("canada", "gdp-growth-rate"),
        "Retail Sales":          ("canada", "retail-sales-mom"),
        "Industrial Production": ("canada", "industrial-production"),
        "Core CPI":              ("canada", "core-inflation-rate"),
        "PPI":                   ("canada", "producer-prices-change"),
    },
    "CHF": {
        "Manufacturing PMI":     ("switzerland", "manufacturing-pmi"),
        "Services PMI":          ("switzerland", "services-pmi"),
        "Consumer Confidence":   ("switzerland", "consumer-confidence"),
        "Business Confidence":   ("switzerland", "business-confidence"),
        "GDP Growth":            ("switzerland", "gdp-growth-rate"),
        "Retail Sales":          ("switzerland", "retail-sales-annual"),
        "Industrial Production": ("switzerland", "industrial-production"),
        "Core CPI":              ("switzerland", "core-inflation-rate"),
        "PPI":                   ("switzerland", "producer-prices-change"),
    },
    "NZD": {
        "Manufacturing PMI":     ("new-zealand", "manufacturing-pmi"),
        "Services PMI":          ("new-zealand", "services-pmi"),
        "Consumer Confidence":   ("new-zealand", "consumer-confidence"),
        "Business Confidence":   ("new-zealand", "business-confidence"),
        "GDP Growth":            ("new-zealand", "gdp-growth-rate"),
        "Retail Sales":          ("new-zealand", "retail-sales-mom"),
        "Industrial Production": ("new-zealand", "industrial-production"),
        "Core CPI":              ("new-zealand", "core-inflation-rate"),
        "PPI":                   ("new-zealand", "producer-prices-change"),
    },
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

# ── Retained geo constants (reserved for Module 4) ───────────────────────────
_GEO_QUERY = "Iran war oil energy prices geopolitical risk conflict sanctions when:2d"
_GEO_CCY_IMPACT: dict[str, float] = {
    "USD":  0.8, "CHF":  1.5, "JPY":  1.5, "CAD":  1.2,
    "EUR": -0.5, "GBP": -0.3, "AUD": -0.8, "NZD": -1.0,
}
_GEO_BULL_KW: list[str] = [
    "iran war", "oil spike", "energy surge", "conflict escalat",
    "sanctions", "military strike", "airstrike", "oil embargo",
]
_GEO_BEAR_KW: list[str] = [
    "ceasefire", "de-escalat", "peace talks", "sanctions lifted",
    "supply normaliz", "oil surplus",
]
_CY = datetime.today().year
_NY = _CY + 1

TTL_NEWS_CTX    = 600   # 10 min — retained for compatibility
TTL_FUNDAMENTAL = 1800  # 30 min — retained for compatibility

# ── New 12M bias engine: direction + weight maps ──────────────────────────────
_IND_DIRECTION: dict[str, str] = {
    "CPI YoY":             "target",   # new — annual inflation rate, 2% target
    "GDP Growth":           "high",
    "Manufacturing PMI":    "high",
    "Services PMI":         "high",
    "Composite PMI":        "high",
    "Retail Sales":         "high",
    "Employment Change":    "high",
    "Wage Growth":          "high",
    "Industrial Production":"high",
    "Interest Rate":        "high",
    "Trade Balance":        "high",
    "Current Account":      "high",
    "M2 Money Supply":      "high",
    "Consumer Confidence":  "high",
    "Business Confidence":  "high",
    "Budget Balance":       "high",
    "Building Permits":     "high",
    "Unemployment Rate":    "low",
    "Government Debt":      "low",
    "CPI m/m":              "target",
    "Core CPI":             "target",
    "PPI":                  "target",
}

_IND_WEIGHTS: dict[str, float] = {
    # Tier 1 — CB-critical (directly drives rate decisions & FX moves)
    "Interest Rate":        2.0,
    "CPI YoY":              2.0,
    "CPI m/m":              2.0,
    "GDP Growth":           2.0,
    "Core CPI":             1.8,
    # Tier 2 — activity / labour (swing-relevant, market-moving)
    "Unemployment Rate":    1.0,
    "Employment Change":    1.0,
    "Wage Growth":          1.0,
    "Manufacturing PMI":    1.0,
    "Services PMI":         1.0,
    "Composite PMI":        1.0,
    "Trade Balance":        1.0,
    "Retail Sales":         0.8,
    "Industrial Production":0.8,
    "Current Account":      0.8,
    # Tier 3 — sentiment / structural (low swing relevance)
    "Consumer Confidence":  0.5,
    "Business Confidence":  0.5,
    "PPI":                  0.4,
    "M2 Money Supply":      0.4,
    "Budget Balance":       0.3,
    "Government Debt":      0.3,
    "Building Permits":     0.3,
}

# ╔══════════════════════════════════════════════════════════════════════════════
# ║  STATIC FALLBACK DATA  (May 2026 — displayed when live fetch fails)
# ╚══════════════════════════════════════════════════════════════════════════════
STATIC_INDICATORS: dict[str, dict[str, dict]] = {
    # ── USD  (FRED live — Apr 2026 verified 2026-05-24)
    "USD": {
        "CPI m/m":            {"actual": 0.64,   "previous": 0.87,   "forecast": 0.3,    "date": "2026-05-13", "impact": "High"},
        "Interest Rate":      {"actual": 3.64,   "previous": 3.64,   "forecast": 3.50,   "date": "2026-05-07", "impact": "High"},
        "GDP Growth":         {"actual": 2.0,    "previous": 0.5,    "forecast": 1.5,    "date": "2026-04-30", "impact": "High"},
        "Unemployment Rate":  {"actual": 4.3,    "previous": 4.3,    "forecast": 4.3,    "date": "2026-05-02", "impact": "High"},
        "Manufacturing PMI":  {"actual": 49.8,   "previous": 49.3,   "forecast": 50.0,   "date": "2026-05-01", "impact": "Medium"},
        "Services PMI":       {"actual": 51.2,   "previous": 51.7,   "forecast": 51.5,   "date": "2026-05-05", "impact": "Medium"},
        "Trade Balance":      {"actual": -60.3,  "previous": -57.8,  "forecast": -59.0,  "date": "2026-05-06", "impact": "Medium"},
        "Retail Sales":       {"actual": 0.49,   "previous": 1.63,   "forecast": 0.4,    "date": "2026-05-15", "impact": "High"},
        "Current Account":    {"actual": -3.2,   "previous": -3.5,   "forecast": -3.3,   "date": "2026-03-20", "impact": "Medium"},
        "Wage Growth":        {"actual": 3.57,   "previous": 3.43,   "forecast": 3.5,    "date": "2026-05-02", "impact": "High"},
        "PPI":                {"actual": 3.8,    "previous": 3.4,    "forecast": 3.5,    "date": "2026-05-14", "impact": "Medium"},
        "Consumer Confidence":{"actual": 49.8,   "previous": 53.3,   "forecast": 50.0,   "date": "2026-05-16", "impact": "Medium"},
        "Government Debt":    {"actual": 124.0,  "previous": 121.3,  "forecast": 122.0,  "date": "2026-04-01", "impact": "Low"},
        "Budget Balance":     {"actual": -5.8,   "previous": -6.1,   "forecast": -6.0,   "date": "2026-04-15", "impact": "Low"},
        "Building Permits":   {"actual": 1442.0, "previous": 1363.0, "forecast": 1420.0, "date": "2026-05-16", "impact": "Medium"},
        "Business Confidence":{"actual": 52.3,   "previous": 50.1,   "forecast": 50.5,   "date": "2026-05-15", "impact": "Low"},
        "Core CPI":           {"actual": 0.38,   "previous": 0.20,   "forecast": 0.3,    "date": "2026-05-13", "impact": "High"},
        "Employment Change":  {"actual": 115.0,  "previous": 185.0,  "forecast": 150.0,  "date": "2026-05-02", "impact": "High"},
        "Industrial Production":{"actual": 0.68, "previous": -0.29,  "forecast": 0.3,    "date": "2026-05-15", "impact": "Medium"},
        "M2 Money Supply":    {"actual": 4.57,   "previous": 4.69,   "forecast": 4.5,    "date": "2026-05-07", "impact": "Low"},
    },
    # ── EUR  (ECB live — May 2026: DFR 2.00%, HICP data through Dec 2025)
    "EUR": {
        "CPI m/m":            {"actual": 0.2,    "previous": 0.2,    "forecast": 0.2,    "date": "2026-05-06", "impact": "High"},
        "Interest Rate":      {"actual": 2.00,   "previous": 2.25,   "forecast": 1.75,   "date": "2026-04-17", "impact": "High"},
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
        "CPI YoY":            {"actual": 1.9,    "previous": 2.1,    "forecast": 2.0,    "date": "2026-01-17", "impact": "High"},
    },
    # ── GBP  (BOE live — Apr 2026 verified 2026-05-24: rate 3.75%)
    "GBP": {
        "CPI m/m":            {"actual": 0.3,    "previous": 0.4,    "forecast": 0.3,    "date": "2026-05-21", "impact": "High"},
        "Interest Rate":      {"actual": 3.75,   "previous": 3.75,   "forecast": 3.50,   "date": "2026-05-08", "impact": "High"},
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
    # ── CAD  (BOC Valet live — May 2026: rate 2.25%)
    "CAD": {
        "CPI m/m":            {"actual": 0.2,    "previous": 0.2,    "forecast": 0.2,    "date": "2026-05-20", "impact": "High"},
        "Interest Rate":      {"actual": 2.25,   "previous": 2.50,   "forecast": 2.00,   "date": "2026-04-16", "impact": "High"},
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
        "CPI YoY":            {"actual": 0.60,   "previous": 0.31,   "forecast": 0.5,    "date": "2026-05-05", "impact": "Medium"},
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
# ║  12-MONTH STATIC HISTORY FALLBACK  (Jun 2025 → May 2026, index 0=oldest)
# ║  Used when live API fetch is unavailable.
# ║  Latest 6 values (index 6-11) match the STATIC_INDICATORS "actual" series.
# ╚══════════════════════════════════════════════════════════════════════════════
HISTORY_FALLBACK: dict[str, dict[str, list[float]]] = {
    "USD": {
        # FRED live — verified 2026-05-24  (Jun 2025 → Apr/May 2026, oldest first)
        "CPI m/m":           [0.25, 0.23, 0.35, 0.30, 0.25, 0.25,  0.30, 0.17, 0.27, 0.87, 0.64, 0.64],
        "Interest Rate":     [4.33, 4.33, 4.33, 4.22, 4.09, 3.88,  3.72, 3.64, 3.64, 3.64, 3.64, 3.64],
        "GDP Growth":        [3.8,  3.8,  3.8,  4.4,  4.4,  4.4,   0.5,  0.5,  0.5,  2.0,  2.0,  2.0],
        "Unemployment Rate": [4.1,  4.3,  4.3,  4.4,  4.5,  4.4,   4.3,  4.4,  4.3,  4.3,  4.3,  4.3],
        "Manufacturing PMI": [48.7, 49.3, 50.1, 50.9, 51.3, 50.5,  49.7, 51.2, 52.7, 49.0, 50.2, 49.8],
        "Services PMI":      [53.8, 54.2, 53.7, 55.1, 54.8, 55.0,  56.1, 52.9, 51.0, 54.4, 50.8, 51.2],
        "Retail Sales":      [0.97, 0.65, 0.55, 0.07,-0.16, 0.50,   0.00,-0.03, 0.92, 1.63, 0.49, 0.50],
        "Wage Growth":       [3.86, 3.96, 3.98, 3.85, 3.92, 3.93,  3.73, 3.66, 3.70, 3.43, 3.57, 3.57],
        "Trade Balance":     [-57.6,-74.2,-56.0,-49.2,-31.1,-56.0,-72.9,-54.7,-57.8,-60.3,-60.0,-60.0],
        "Core CPI":          [0.23, 0.31, 0.31, 0.22, 0.19, 0.23,  0.30, 0.22, 0.20, 0.38, 0.38, 0.38],
        "Employment Change": [-20,   64,  -70,   76, -140,   41,   -17,  160, -156,  185,  115,  115],
        "Industrial Production":[0.51,0.41,-0.26,0.04,-0.44,-0.18, 0.48,-0.05, 0.62,-0.29, 0.68, 0.68],
        "M2 Money Supply":   [4.13, 4.38, 4.25, 4.24, 4.28, 3.85,  4.04, 4.09, 4.69, 4.57, 4.57, 4.57],
        "Consumer Confidence":[60.7, 61.7, 58.2, 55.1, 53.6, 51.0, 52.9, 56.4, 56.6, 53.3, 49.8, 49.8],
        "Government Debt":   [120., 121., 121., 122., 122., 122.,  122., 122., 123., 123., 124., 124.],
        "PPI":               [0.2,  0.3,  0.4,  0.3,  0.2,  0.3,   0.3,  0.5,  0.0, -0.4, -0.5,  0.2],
        "Budget Balance":    [-6.1,-6.0, -5.9, -5.9, -5.8, -5.8,  -5.8, -5.9, -6.0, -5.9, -5.9, -5.8],
        "Building Permits":  [1399,1400, 1347, 1444, 1418, 1414,  1482, 1393, 1540, 1363, 1442, 1442],
        "Business Confidence":[54.5,54.2,53.8, 53.5, 53.2, 52.5,  52.3, 51.5, 51.0, 51.5, 51.0, 52.3],
    },
    "EUR": {
        "CPI m/m":           [0.3, 0.3, 0.2, 0.2, 0.1, 0.2,   0.3, 0.2,-0.1, 0.0, 0.2, 0.2],
        "Interest Rate":     [3.25,3.00,2.75,2.75,2.50,2.50,   2.25,2.25,2.00,2.00,2.00,2.00],
        "GDP Growth":        [0.9, 1.0, 1.1, 1.0, 1.1, 1.2,   1.2, 1.2, 1.7, 1.7, 1.7, 1.7],
        "Unemployment Rate": [6.5, 6.4, 6.4, 6.3, 6.3, 6.3,   6.3, 6.2, 6.2, 6.1, 6.1, 6.2],
        "Manufacturing PMI": [43.6,44.2,44.8,45.1,45.3,45.1,  45.1,46.6,47.6,48.7,49.0,49.4],
        "Services PMI":      [53.2,53.0,52.7,52.2,51.8,51.7,  51.6,51.3,50.6,51.0,50.3,50.1],
        "Retail Sales":      [0.2, 0.1, 0.0,-0.1, 0.2, 0.0,  -0.1, 0.3, 0.0, 0.3, 0.2, 0.1],
        "Wage Growth":       [4.4, 4.3, 4.2, 4.1, 4.0, 4.1,   4.1, 4.2, 3.8, 3.6, 3.3, 3.1],
        "Trade Balance":     [12., 14., 15., 10., 12., 11.,    8.5,16.3,10.5,18.0,20.5, 8.5],
        "Core CPI":          [0.3, 0.2, 0.2, 0.1, 0.1, 0.2,   0.0, 0.3, 0.1, 0.3, 0.3, 0.2],
        "Employment Change": [310, 295, 285, 300, 290, 280,   300, 280, 220, 180, 190, 210],
        "Industrial Production":[-0.3,0.2,0.4,0.3,-0.2,0.1, -1.1, 0.5, 0.7,-1.8, 0.5, 0.4],
        "M2 Money Supply":   [3.3, 3.4, 3.5, 3.7, 3.8, 3.7,   3.7, 3.8, 4.0, 3.9, 3.9, 4.1],
        "Consumer Confidence":[-11.,-12.,-12.,-13.,-14.,-14., -14.2,-14.2,-13.3,-16.5,-16.7,-18.0],
        "Government Debt":   [88., 88., 89., 89., 89., 89.5,  89.5,89.5,90.0,90.0,90.8,91.0],
        "PPI":               [0.2, 0.1, 0.2, 0.1, 0.0, 0.1,   0.0, 0.2, 0.0, 0.1, 0.0, 0.1],
        "Current Account":   [0.5, 0.5, 0.6, 0.6, 0.7, 0.7,  0.7, 0.7, 0.8, 0.8, 0.8, 0.8],
        "Budget Balance":    [-3.5,-3.5,-3.4,-3.4,-3.3,-3.3, -3.3,-3.3,-3.2,-3.2,-3.2,-3.2],
        "Building Permits":  [96.5,95.8,95.2,94.8,94.2,93.8, 93.5,95.1,94.8,94.2,93.5,92.3],
        "Business Confidence":[103.,102.,101.5,101.,100.5,100., 99.5,99.2,99.2,99.5,99.2,98.5],
        "CPI YoY":           [2.9, 2.7, 2.6, 2.4, 2.3, 2.2,   2.0, 2.0, 2.2, 2.1, 2.1, 1.9],
    },
    "GBP": {
        "CPI m/m":           [0.5, 0.4, 0.4, 0.3, 0.4, 0.3,   0.3, 0.3, 0.5, 0.2, 0.4, 0.3],
        "Interest Rate":     [4.25,4.25,4.05,4.00,4.00,4.00,  3.90,3.75,3.75,3.75,3.75,3.75],
        "GDP Growth":        [0.3, 0.4, 0.4, 0.5, 0.5, 0.5,   0.5, 0.5, 1.1, 1.1, 1.6, 1.6],
        "Unemployment Rate": [4.2, 4.2, 4.3, 4.3, 4.3, 4.3,   4.3, 4.4, 4.4, 4.5, 4.5, 4.5],
        "Manufacturing PMI": [46.2,47.0,47.3,47.3,48.1,47.5,  47.3,48.3,46.9,44.9,45.4,46.0],
        "Services PMI":      [52.0,52.1,51.8,51.5,51.3,51.2,  51.1,51.0,51.0,52.5,49.9,50.3],
        "Retail Sales":      [0.1, 0.0,-0.2,-0.4, 0.1,-0.1,  -0.6, 0.0, 1.0,-0.4, 0.4,-0.3],
        "Wage Growth":       [6.5, 6.4, 6.3, 6.2, 6.1, 6.0,   6.0, 5.9, 5.8, 5.6, 5.3, 5.0],
        "Trade Balance":     [-4.5,-4.2,-4.8,-4.9,-5.1,-4.7,  -5.1,-3.7,-4.5,-3.8,-3.7,-5.1],
        "Core CPI":          [0.6, 0.5, 0.5, 0.5, 0.4, 0.5,   0.5, 0.6, 0.4, 0.5, 0.3, 0.3],
        "Employment Change": [95,  88,  82,  77,  76,  76,     76,  73,  27, -25, -50, -72],
        "Industrial Production":[0.3,0.4,0.5,0.5,0.6,0.5,    0.5, 0.7,-0.6, 0.2, 0.8, 0.4],
        "M2 Money Supply":   [2.7, 2.8, 2.9, 3.0, 3.0, 3.0,   3.0, 3.1, 3.2, 3.3, 3.2, 3.1],
        "Consumer Confidence":[-14.,-15.,-16.,-16.,-17.,-17., -17.,-22.,-20.,-18.,-23.,-20.],
        "Government Debt":   [97., 97.5,98.0,98.5,98.5,98.5,  98.5,99.0,99.5,100.,100.5,101.],
        "PPI":               [0.3, 0.2, 0.2, 0.2, 0.2, 0.2,   0.2, 0.1, 0.2,-0.1, 0.1, 0.2],
        "Current Account":   [-3.2,-3.3,-3.4,-3.5,-3.5,-3.5, -3.5,-3.5,-3.5,-3.5,-3.6,-3.8],
        "Budget Balance":    [-5.5,-5.3,-5.1,-4.9,-4.7,-4.6, -4.5,-4.7,-4.4,-4.3,-4.4,-4.3],
        "Building Permits":  [192.,190.,188.,186.,185.,183.,  183.,185.,182.,180.,179.,178.],
        "Business Confidence":[52.5,52.0,51.5,51.0,50.5,50.0, 49.5,49.3,49.2,48.8,48.5,48.2],
    },
    "JPY": {
        "CPI m/m":           [0.5, 0.4, 0.4, 0.4, 0.3, 0.4,   0.4, 0.4, 0.3, 0.2, 0.3, 0.3],
        "Interest Rate":     [0.50,0.50,0.50,0.50,0.50,0.50,  0.50,0.50,0.50,0.50,0.50,0.50],
        "GDP Growth":        [0.8, 0.9, 1.0, 1.1, 1.0, 1.0,   1.0, 1.0, 1.2, 1.2, 1.2, 1.2],
        "Unemployment Rate": [2.6, 2.5, 2.6, 2.5, 2.5, 2.5,   2.5, 2.4, 2.5, 2.4, 2.5, 2.4],
        "Manufacturing PMI": [49.4,49.2,49.5,49.5,50.1,49.8,  49.5,50.1,49.0,48.4,48.7,48.5],
        "Services PMI":      [53.8,53.5,53.0,51.3,52.0,51.0,  50.6,53.0,53.7,50.0,52.4,52.4],
        "Retail Sales":      [0.2, 0.0,-0.1,-0.3, 0.1,-0.2,  -0.3, 0.0, 1.0,-1.1, 0.0, 0.2],
        "Wage Growth":       [3.2, 3.3, 3.4, 3.5, 3.4, 3.5,   3.5, 3.1, 2.8, 3.5, 3.5, 3.2],
        "Trade Balance":     [-0.5,-0.7,-0.8,-0.8,-1.0,-0.9,  -0.8,-1.2,-0.5,-0.3,-1.2,-0.8],
        "Core CPI":          [0.3, 0.3, 0.3, 0.3, 0.3, 0.3,   0.3, 0.4, 0.3, 0.2, 0.2, 0.2],
        "Employment Change": [10,   8,   6,   5,   5,   5,      5,  -4,  18,  15,  20,  15],
        "Industrial Production":[-0.5,-0.2,0.3,-0.8,-1.2,-1.5,-2.3,-1.1,2.2, 0.2,-1.1, 0.5],
        "M2 Money Supply":   [0.8, 0.9, 0.9, 1.0, 1.0, 1.0,   1.0, 1.1, 1.3, 1.4, 1.4, 1.5],
        "Consumer Confidence":[36.5,36.8,37.0,36.5,36.0,35.5, 35.0,36.2,35.5,34.2,33.8,34.1],
        "Government Debt":   [252.,252.,253.,254.,254.,254.,   254.,254.,255.,255.,255.,255.],
        "PPI":               [0.3, 0.2, 0.2, 0.1, 0.3, 0.2,   0.1, 0.4, 0.3, 0.5, 0.4, 0.2],
        "Current Account":   [1.8, 1.7, 1.6, 1.8, 1.7, 1.8,  1.8, 1.8, 1.5, 1.6, 1.7, 1.5],
        "Budget Balance":    [-4.8,-5.0,-5.2,-5.4,-5.5,-5.5, -5.5,-5.6,-5.5,-5.5,-5.6,-5.5],
        "Building Permits":  [75.5,75.2,74.8,74.5,74.2,74.0, 73.8,71.2,72.5,72.0,72.5,73.5],
        "Business Confidence":[7.,  8.,  9., 10., 11., 11.,   11., 11., 12., 12., 12., 13.],
    },
    "AUD": {
        "CPI m/m":           [0.4, 0.3, 0.3, 0.3, 0.2, 0.3,   0.3, 0.3, 0.2, 0.1, 0.2, 0.3],
        "Interest Rate":     [4.35,4.35,4.35,4.35,4.35,4.35,  4.35,4.35,4.10,4.10,3.85,3.85],
        "GDP Growth":        [0.8, 0.9, 1.0, 1.0, 1.0, 1.0,   1.0, 1.0, 1.3, 1.3, 1.3, 1.3],
        "Unemployment Rate": [4.0, 4.0, 4.1, 4.1, 4.1, 4.1,   4.1, 4.0, 4.1, 4.2, 4.1, 4.2],
        "Manufacturing PMI": [48.8,48.5,48.9,49.0,50.3,49.5,  49.0,50.3,49.8,51.0,50.3,51.7],
        "Services PMI":      [51.0,51.2,51.5,50.8,51.4,50.7,  50.4,51.6,50.8,51.6,51.6,51.0],
        "Retail Sales":      [0.3, 0.2, 0.4, 0.4, 0.3, 0.4,   0.4, 0.3, 0.2, 0.3, 0.2, 0.3],
        "Wage Growth":       [3.4, 3.4, 3.3, 3.3, 3.3, 3.3,   3.3, 3.3, 3.4, 3.4, 3.3, 3.6],
        "Trade Balance":     [5.5, 5.2, 5.0, 4.8, 4.7, 4.7,   4.7, 4.7, 5.1, 4.7, 4.7, 5.1],
        "Core CPI":          [0.3, 0.3, 0.2, 0.2, 0.3, 0.2,   0.2, 0.3, 0.2, 0.2, 0.3, 0.2],
        "Employment Change": [60,  55,  58,  57,  57,  56,     56,  90,  53,  90,  52,  38],
        "Industrial Production":[0.3,0.2,0.2,0.2,0.2,0.2,    0.2, 0.2, 0.3, 0.4, 0.2, 0.4],
        "M2 Money Supply":   [4.2, 4.3, 4.4, 4.5, 4.6, 4.5,   4.5, 4.7, 4.8, 5.0, 4.8, 5.2],
        "Consumer Confidence":[96., 97., 97., 98., 98., 97.,   97., 99.,101.,100.5,99.,102.],
        "Government Debt":   [49., 49., 49.5,50.0,50.5,50.5,  50.5,50.5,51.0,51.5,51.5,52.0],
        "PPI":               [0.4, 0.3, 0.3, 0.3, 0.2, 0.3,   0.3, 0.2, 0.2, 0.3, 0.2, 0.3],
        "Current Account":   [-2.1,-2.2,-2.3,-2.3,-2.4,-2.5, -2.5,-2.8,-2.6,-2.6,-2.5,-2.5],
        "Budget Balance":    [-0.2,-0.3,-0.4,-0.5,-0.6,-0.8, -0.8,-1.2,-1.0,-0.9,-0.8,-0.8],
        "Building Permits":  [16.5,16.2,16.0,15.8,15.5,15.3, 15.3,14.8,15.0,14.9,14.9,15.2],
        "Business Confidence":[3.,  3.,  3.,  4.,  4.,  4.,   4.,  3.,  4.,  4.,  4.,  5.],
    },
    "CAD": {
        "CPI m/m":           [0.3, 0.4, 0.3, 0.3, 0.4, 0.3,   0.3, 0.4, 0.1, 0.1, 0.3, 0.2],
        "Interest Rate":     [4.25,4.00,3.75,3.50,3.25,3.00,  3.00,2.75,2.50,2.50,2.25,2.25],
        "GDP Growth":        [1.8, 1.8, 1.7, 1.7, 1.6, 1.6,   1.6, 1.6, 1.5, 1.5, 1.5, 1.5],
        "Unemployment Rate": [6.3, 6.4, 6.5, 6.6, 6.7, 6.7,   6.7, 6.8, 6.8, 6.9, 6.9, 6.9],
        "Manufacturing PMI": [51.5,51.5,51.8,51.7,52.0,51.6,  51.6,47.8,47.9,46.3,46.5,46.8],
        "Services PMI":      [49.5,49.3,48.5,48.2,48.0,47.8,  47.5,47.5,44.6,48.6,41.5,41.9],
        "Retail Sales":      [0.3, 0.5, 0.6, 0.7, 0.5, 0.7,   0.7, 0.4,-0.4,-0.2,-0.4, 0.1],
        "Wage Growth":       [3.5, 3.4, 3.5, 3.4, 3.3, 3.3,   3.3, 3.3, 3.3, 3.5, 3.4, 3.3],
        "Trade Balance":     [0.5, 0.6, 0.8, 0.7, 0.8, 0.7,   0.7,-0.4, 0.3,-0.8,-0.4, 0.7],
        "Core CPI":          [0.3, 0.4, 0.3, 0.4, 0.4, 0.4,   0.4, 0.3, 0.2, 0.1, 0.2, 0.2],
        "Employment Change": [30,  40,  55,  70,  76,  76,     76,  76, -33, -33, -33,   7],
        "Industrial Production":[0.2,0.1,0.0,-0.1,-0.2,-0.3,  -0.4, 0.2, 0.3,-0.3, 0.1, 0.2],
        "M2 Money Supply":   [2.3, 2.4, 2.4, 2.5, 2.5, 2.5,   2.5, 2.6, 2.7, 2.7, 2.8, 2.9],
        "Consumer Confidence":[52., 50., 48., 46., 44., 43.6,  43.6,43.7,52.0,48.8,50.9,47.0],
        "Government Debt":   [104.,105.,105.,105.5,106.,106.,  106.,106.5,106.5,107.,107.,107.],
        "PPI":               [0.2, 0.1, 0.1, 0.0,-0.1, 0.0,  -0.1, 0.1, 0.2, 0.1, 0.1, 0.0],
        "Current Account":   [-1.8,-1.9,-2.0,-2.1,-2.2,-2.3, -2.3,-2.2,-2.3,-2.4,-2.5,-2.5],
        "Budget Balance":    [-1.2,-1.3,-1.4,-1.5,-1.5,-1.5, -1.5,-1.8,-1.6,-1.5,-1.5,-1.5],
        "Building Permits":  [265.,262.,258.,255.,252.,250.,  250.,253.,248.,245.,243.,238.],
        "Business Confidence":[-5.,-6.,-8.,-10.,-12.,-13.,  -13.,-12.,-14.,-15.,-14.,-15.],
    },
    "CHF": {
        "CPI m/m":           [0.2, 0.1, 0.1, 0.1, 0.2, 0.1,   0.1, 0.2,-0.1, 0.0, 0.1, 0.1],
        "Interest Rate":     [0.25,0.25,0.25,0.00,0.00,0.00,  0.00,0.00,0.00,0.00,0.00,0.00],
        "GDP Growth":        [0.8, 1.0, 1.2, 1.3, 1.4, 1.5,   1.5, 1.5, 1.7, 1.7, 2.0, 2.0],
        "Unemployment Rate": [2.4, 2.4, 2.5, 2.5, 2.5, 2.5,   2.5, 2.6, 2.5, 2.5, 2.6, 2.5],
        "Manufacturing PMI": [47.8,48.0,48.3,48.5,48.4,48.5,  48.5,48.4,49.0,48.8,49.1,48.9],
        "Services PMI":      [51.0,50.8,50.5,50.3,49.5,50.0,  50.3,49.0,50.5,49.4,49.4,49.1],
        "Retail Sales":      [0.1, 0.0,-0.1, 0.0,-0.2,-0.1,  -0.3, 0.0, 0.3, 0.1,-0.2, 0.2],
        "Wage Growth":       [2.2, 2.1, 2.0, 1.9, 1.8, 1.8,   1.8, 2.0, 1.8, 2.1, 2.0, 1.8],
        "Trade Balance":     [5.0, 4.8, 4.7, 4.8, 4.5, 4.8,   4.8, 4.2, 4.5, 3.5, 4.2, 4.8],
        "Core CPI":          [0.1, 0.1, 0.0, 0.1, 0.1, 0.1,   0.0, 0.1, 0.0, 0.0, 0.1, 0.1],
        "Employment Change": [7,   6,   5,   5,   5,   5,      5,   4,   3,   2,   3,   4],
        "Industrial Production":[0.2,0.1,0.0,-0.1,-0.2,-0.3,  -0.3, 0.1, 0.2, 0.0, 0.1, 0.2],
        "M2 Money Supply":   [-1.5,-1.3,-1.2,-1.1,-1.0,-1.0,  -1.0,-0.8,-0.5,-0.3, 0.0, 0.2],
        "Consumer Confidence":[-41.,-39.,-37.,-38.,-39.,-38.3, -38.3,-30.1,-24.1,-26.3,-24.8,-20.5],
        "Government Debt":   [37., 37., 37.5,37.5,37.5,37.5,  37.5,37.5,38.0,38.0,38.0,38.0],
        "PPI":               [0.0, 0.0,-0.1, 0.0, 0.0,-0.1,  -0.1, 0.0, 0.1, 0.0,-0.1, 0.0],
        "Current Account":   [8.0, 8.1, 8.2, 8.2, 8.3, 8.3,  8.3, 8.2, 8.5, 8.5, 8.4, 8.5],
        "Budget Balance":    [0.5, 0.4, 0.3, 0.2, 0.2, 0.2,  0.2, 0.2,-0.1, 0.0, 0.1, 0.3],
        "Building Permits":  [3.1, 3.1, 3.0, 3.0, 3.0, 2.9,  2.9, 2.9, 2.8, 2.8, 2.9, 2.8],
        "Business Confidence":[-2.5,-2.0,-1.5,-1.2,-1.0,-0.8,-0.8,-0.8,-0.5,-0.4,-0.3,-0.3],
        "CPI YoY":           [1.3, 1.1, 1.0, 0.9, 1.0, 1.2,   1.3, 1.1, 0.8, 0.6, 0.3, 0.6],
    },
    "NZD": {
        "CPI m/m":           [0.4, 0.3, 0.3, 0.2, 0.3, 0.2,   0.2, 0.3, 0.1, 0.1, 0.2, 0.2],
        "Interest Rate":     [5.25,5.00,5.00,4.75,4.50,4.25,  4.25,3.75,3.75,3.50,3.50,3.50],
        "GDP Growth":        [-0.3,-0.3,-0.4,-0.5,-0.5,-0.5,  -0.5,-0.5, 0.6, 0.6, 0.7, 0.7],
        "Unemployment Rate": [4.6, 4.7, 4.8, 4.9, 5.0, 5.0,   5.0, 5.1, 5.2, 5.1, 5.3, 5.2],
        "Manufacturing PMI": [44.2,45.0,45.5,46.2,50.1,46.8,  46.2,50.1,52.7,53.9,54.3,53.5],
        "Services PMI":      [47.0,47.5,47.8,47.8,49.1,47.8,  47.8,49.1,50.2,49.1,50.1,49.8],
        "Retail Sales":      [-0.3,-0.2, 0.0, 0.1,-0.3, 0.0,   0.0,-0.5, 0.7, 0.4,-0.2, 0.0],
        "Wage Growth":       [3.5, 3.5, 3.4, 3.4, 3.3, 3.3,   3.3, 3.3, 2.9, 2.9, 2.9, 3.0],
        "Trade Balance":     [-0.2,-0.3,-0.2,-0.1,-0.2,-0.1,  -0.1,-0.4, 0.0,-0.1,-0.4,-0.1],
        "Core CPI":          [0.3, 0.2, 0.2, 0.1, 0.2, 0.1,   0.1, 0.2, 0.1, 0.1, 0.1, 0.2],
        "Employment Change": [5,   6,   7,   8,   5,   8,      8,   5,  -3,   2,   1,   3],
        "Industrial Production":[0.2,0.1,0.0, 0.0,-0.1, 0.0,   0.0,-0.1, 0.2, 0.1, 0.0, 0.1],
        "M2 Money Supply":   [5.5, 5.3, 5.2, 5.1, 5.2, 5.0,   5.0, 5.2, 5.0, 5.1, 5.0, 5.1],
        "Consumer Confidence":[-70.,-68.,-66.,-66.,-53.,-65.7,-65.7,-50.4,-47.3,-47.7,-45.3,-43.5],
        "Government Debt":   [44., 44.5,45.0,45.5,46.5,46.5,  46.5,46.5,47.0,47.5,47.5,48.0],
        "PPI":               [0.3, 0.2, 0.2, 0.1, 0.2, 0.1,   0.1, 0.2, 0.1, 0.2, 0.1, 0.2],
        "Current Account":   [-2.8,-2.9,-3.0,-3.1,-3.2,-3.2, -3.2,-3.2,-3.3,-3.4,-3.5,-3.5],
        "Budget Balance":    [-2.2,-2.3,-2.5,-2.7,-2.8,-2.9, -2.9,-2.8,-3.0,-3.0,-3.1,-3.1],
        "Building Permits":  [2.8, 2.7, 2.7, 2.6, 2.5, 2.5,  2.4, 2.3, 2.2, 2.2, 2.1, 2.1],
        "Business Confidence":[25., 22., 20., 18., 16., 15.,  15., 18., 15., 14., 14., 14.5],
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
    color, bg = (C["green"], "rgba(26,155,106,0.10)") if is_live else (C["yellow"], "rgba(240,180,41,0.10)")
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
    Provides live values for PMI, GDP Growth, Retail Sales, Wage Growth,
    Unemployment Rate, Trade Balance, Current Account.
    Does NOT return Interest Rate or CPI (those use dedicated CB APIs).
    Returns {indicator_key: {actual, previous, date, source}} or {} on any failure.
    Cached 30 min.  Never raises — always returns {} on error.
    """
    if not _BS4:
        return {}
    url = _TE_URLS.get(currency)
    if not url:
        return {}
    # Indicators we accept from TE (only %-based or index values with consistent units)
    # Skipped: Interest Rate, CPI — handled by dedicated CB APIs
    # Skipped: Trade Balance, Current Account — TE shows local-currency millions (not normalised)
    # Skipped: Wage Growth — TE shows absolute wage levels for most currencies, not % change
    _TE_SKIP = {
        "Interest Rate", "CPI m/m", "CPI YoY",
        "Trade Balance", "Current Account", "Wage Growth",
    }

    def _parse_te_date(txt: str) -> str:
        """Convert TE date 'Mar/26' → '2026-03' → '2026-03-01' approx."""
        txt = txt.strip()
        if not txt:
            return ""
        _MONTHS = {"jan":"01","feb":"02","mar":"03","apr":"04","may":"05","jun":"06",
                   "jul":"07","aug":"08","sep":"09","oct":"10","nov":"11","dec":"12"}
        parts = txt.lower().replace("/", " ").split()
        if len(parts) == 2:
            mon = _MONTHS.get(parts[0][:3], "")
            yr  = parts[1] if len(parts[1]) == 4 else f"20{parts[1]}" if len(parts[1]) == 2 else ""
            if mon and yr:
                return f"{yr}-{mon}-01"
        return txt

    try:
        r = requests.get(url, headers=_TE_HEADERS, timeout=12)
        if r.status_code != 200:
            return {}
        soup = BeautifulSoup(r.text, "html.parser")

        result: dict = {}
        assigned: set[str] = set()

        for row in soup.select("table tr"):
            cells = row.find_all(["td", "th"])
            if len(cells) < 3:
                continue
            row_name = cells[0].get_text(strip=True).lower()

            matched_key: str | None = None
            for fragment, ind_key in _TE_ROW_MAP:
                if fragment in row_name and ind_key not in assigned:
                    if ind_key not in _TE_SKIP:
                        matched_key = ind_key
                    break  # still mark as seen so we don't re-match later
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
            date_raw = cells[6].get_text(strip=True) if len(cells) > 6 else ""
            date_fmt = _parse_te_date(date_raw)

            if actual is None:
                continue

            result[matched_key] = {
                "actual":   actual,
                "previous": previous,
                "date":     date_fmt,
                "source":   "TE",
            }
            assigned.add(matched_key)

        return result
    except Exception:
        return {}


# ── FRED series map for international currencies ──────────────────────────────
# FRED international series — only include series with data within ~6 months
# Verified current as of May 2026.
# OECD CCI (Consumer Confidence) and BCI (Business Confidence) series included.
# OECD Industrial Production series included where available.
_FRED_INTL: dict[str, dict[str, tuple[str, str]]] = {
    "GBP": {
        # FRED OECD series stale ~2 months; ONS will override below (more current)
        "Unemployment Rate":    ("LRHUTTTTGBM156S",   "pct"),
        "Consumer Confidence":  ("CSCICP03GBM665S",   "idx"),
        "Business Confidence":  ("BSCICP03GBM665S",   "idx"),
        "Industrial Production":("GBRIPMISMEI",        "idx"),
    },
    "JPY": {
        "Unemployment Rate":    ("LRUN74TTJPM156S",   "pct"),
        "Consumer Confidence":  ("CSCICP03JPM665S",   "idx"),
        "Business Confidence":  ("BSCICP03JPM665S",   "idx"),
        "Industrial Production":("JPNPROINDMISMEI",   "idx"),
    },
    "CAD": {
        "Unemployment Rate":    ("LRUNTTTTCAM156S",   "pct"),
        "Consumer Confidence":  ("CSCICP03CAM665S",   "idx"),
        "Business Confidence":  ("BSCICP03CAM665S",   "idx"),
        "Industrial Production":("CAIPMISMEI",         "idx"),
    },
    "AUD": {
        "Unemployment Rate":    ("LRUNTTTTAUM156S",   "pct"),
        "Consumer Confidence":  ("CSCICP03AUM665S",   "idx"),
        "Business Confidence":  ("BSCICP03AUM665S",   "idx"),
        "Industrial Production":("AUSPROINDMISMEI",   "idx"),
    },
    "NZD": {
        "Interest Rate":        ("IR3TIB01NZM156N",   "pct"),
        "Unemployment Rate":    ("LRUNTTTTNZQ156S",   "pct"),   # quarterly, ~Jan 2026
        "Consumer Confidence":  ("CSCICP03NZM665S",   "idx"),
        "Business Confidence":  ("BSCICP03NZM665S",   "idx"),
        "Industrial Production":("NZLPROINDMISMEI",   "idx"),
    },
    "EUR": {
        "Consumer Confidence":  ("CSCICP03EZM665S",   "idx"),
        "Business Confidence":  ("BSCICP03EZM665S",   "idx"),
        "Industrial Production":("ZGEAINDMISMEI",     "idx"),
    },
    "CHF": {
        "Consumer Confidence":  ("CSCICP03CHM665S",   "idx"),
        "Business Confidence":  ("BSCICP03CHM665S",   "idx"),
        "Industrial Production":("CHEPROINDMISMEI",   "idx"),
    },
}

# ONS (UK) series via www.ons.gov.uk web API
_ONS_SERIES: dict[str, str] = {
    "CPI YoY":          "/economy/inflationandpriceindices/timeseries/d7g7/mm23",
    "Unemployment Rate": "/employmentandlabourmarket/peoplenotinwork/unemployment/timeseries/mgsx/lms",
}


@st.cache_data(ttl=1800, show_spinner=False)
def fetch_international_indicators(currency: str, fred_api_key: str = "") -> dict:
    """
    Fetch current indicator values for non-USD currencies using:
      - FRED international OECD/ILO series (unemployment, CPI where available)
      - ONS web API for GBP (CPI YoY, Unemployment Rate — current data)
    Returns {indicator_name: {actual, previous, date, source}} or {} on failure.
    Never raises.
    """
    result: dict = {}
    _key = fred_api_key or FRED_API_KEY

    _max_stale_months = 5   # skip series with data older than this
    _cutoff = (datetime.today() - timedelta(days=_max_stale_months * 31)).strftime("%Y-%m")

    # ── 1. FRED international series ─────────────────────────────────────────
    for ind_name, (sid, transform) in _FRED_INTL.get(currency, {}).items():
        try:
            url = (
                f"https://api.stlouisfed.org/fred/series/observations"
                f"?series_id={sid}&api_key={_key}&sort_order=desc&limit=4&file_type=json"
            )
            r = requests.get(url, timeout=10)
            if r.status_code != 200:
                continue
            obs = [o for o in r.json().get("observations", []) if o.get("value") != "."]
            if len(obs) < 2:
                continue
            date_str = obs[0]["date"][:7]
            if date_str < _cutoff:
                continue    # skip stale series
            actual_val   = float(obs[0]["value"])
            previous_val = float(obs[1]["value"])
            result[ind_name] = {
                "actual":   round(actual_val, 3),
                "previous": round(previous_val, 3),
                "date":     date_str,
                "source":   "FRED",
            }
        except Exception:
            continue

    # ── 2. ONS for GBP (current data, higher priority than FRED) ─────────────
    if currency == "GBP":
        for ind_name, ons_path in _ONS_SERIES.items():
            try:
                r = requests.get(
                    f"https://www.ons.gov.uk{ons_path}/data",
                    timeout=10,
                )
                if r.status_code != 200:
                    continue
                d = r.json()
                items = d.get("months") or d.get("quarters") or []
                valid = [
                    (m["date"], float(m["value"]))
                    for m in items
                    if m.get("value") and m["value"].replace(".", "").replace("-", "").isdigit()
                ]
                if len(valid) < 2:
                    continue
                actual_val   = valid[-1][1]
                previous_val = valid[-2][1]
                date_str     = valid[-1][0]
                result[ind_name] = {
                    "actual":   round(actual_val, 3),
                    "previous": round(previous_val, 3),
                    "date":     date_str,
                    "source":   "ONS",
                }
            except Exception:
                continue

    # ── 3. ECB live values for EUR (interest rate + CPI YoY already in fetch_ecb_*) ──
    if currency == "EUR":
        try:
            r = requests.get(
                "https://data-api.ecb.europa.eu/service/data/ICP/M.U2.N.000000.4.ANR"
                "?format=csvdata&startPeriod=2025-06",
                timeout=10,
            )
            if r.ok:
                lines = [l for l in r.text.splitlines() if l.strip()]
                hdr = lines[0].split(",")
                tc  = hdr.index("TIME_PERIOD");  vc = hdr.index("OBS_VALUE")
                pairs = []
                for l in lines[1:]:
                    p = l.split(",")
                    try: pairs.append((p[tc].strip(), float(p[vc].strip())))
                    except: pass
                pairs.sort()
                if len(pairs) >= 2:
                    result["CPI YoY"] = {
                        "actual":   pairs[-1][1],
                        "previous": pairs[-2][1],
                        "date":     pairs[-1][0],
                        "source":   "ECB",
                    }
        except Exception:
            pass

    return result


# ╔══════════════════════════════════════════════════════════════════════════════
# ║  FOREXFACTORY MACRO DATA MINER
# ╚══════════════════════════════════════════════════════════════════════════════

_FF_MACRO_HDR = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept":          "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer":         "https://www.forexfactory.com/",
    "Origin":          "https://www.forexfactory.com",
}
_FF_MACRO_URLS = [
    "https://nfs.faireconomy.media/ff_calendar_month.json",
    "https://nfs.faireconomy.media/ff_calendar_thisweek.json",
    "https://nfs.faireconomy.media/ff_calendar_nextweek.json",
]

# Indicator names in FF we want to skip (interest rate/CPI handled by precise APIs)
_FF_SKIP_INDICATORS = {"Interest Rate", "CPI m/m"}

# ── Upcoming calendar: keyword sets for Tier classification ───────────────
_CAL_CURRENCIES: frozenset[str] = frozenset({"usd","eur","gbp","jpy","aud","cad","chf","nzd"})

# Positive match → Tier 1 (CB-critical)
_CAL_TIER1_KW: tuple[str, ...] = (
    "interest rate",      # Interest Rate Decision
    "rate decision",      # explicit decision label
    "cash rate",          # Official Cash Rate (RBA, RBNZ)
    "policy rate",        # ECB / SNB style
    "monetary policy",    # Monetary Policy Statement / Decision
    "press conference",   # CB press conference (always follows decision)
    "cpi",                # CPI m/m, CPI y/y
    "core cpi",           # Core CPI
    "inflation",          # Inflation Rate / Index
    "gdp",                # GDP q/q, GDP Growth, GDP Annualized
    "gross domestic",     # alternate GDP naming
    "non-farm",           # NFP (US Nonfarm Payrolls)
    "nonfarm",
    "employment change",  # AUD / CAD Employment Change
)

# Positive match → Tier 2 (Activity indicators in _IND_WEIGHTS)
_CAL_TIER2_KW: tuple[str, ...] = (
    "pmi",                # Manufacturing PMI, Services PMI, Composite PMI
    "trade balance",      # Trade Balance
    "unemployment",       # Unemployment Rate
    "jobless",            # Jobless Claims (USD)
    "wage",               # Wage Growth / Average Earnings
)

# Negative filter — skip regardless of impact or tier match
# Covers duplicates, speeches without data, and non-standard variants
_CAL_SKIP_KW: tuple[str, ...] = (
    "trimmed mean",       # non-standard CPI variant (AUD) — duplicate noise
    "rate statement",     # e.g. "RBNZ Rate Statement" — words only, no new number
    "speech",             # speeches without a data release
    "speaks",
    "remarks",
    "testimony",
    "minutes",            # FOMC / BOE minutes — backward-looking, no new data
    "forum",
    "vote count",
)


@st.cache_data(ttl=1800, show_spinner=False)
def fetch_ff_macro_data(currency: str) -> dict:
    """
    Mine ForexFactory JSON calendar feeds for live macro indicator values:
    PMI, GDP, Retail Sales, Unemployment, Wage Growth, Trade Balance, etc.

    Strategy:
    - Past events (actual != null): use actual as current value, previous as prior
    - Future/upcoming events (actual == null): use 'previous' field as most recent release
    - Returns most recent entry per indicator (by date, preferring events with actuals)
    - Never overrides Interest Rate / CPI (those have more precise dedicated sources)
    - Returns {indicator_name: {actual, previous, forecast, date, source}} or {} on failure
    """
    events: list[dict] = []
    for url in _FF_MACRO_URLS:
        try:
            r = requests.get(url, timeout=10, headers=_FF_MACRO_HDR)
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, list) and data:
                    events.extend(data)
        except Exception:
            pass
        time.sleep(0.05)

    if not events:
        return {}

    ccy_lower = currency.lower()

    def _num(val) -> float | None:
        """Parse numeric string: strips %, $, K/M/B multipliers."""
        if val is None:
            return None
        s = str(val).strip().replace(",", "").replace("$", "").replace(" ", "")
        if s in ("", "-", "N/A", "None", "null"):
            return None
        if s.endswith("%"):
            s = s[:-1]
        mult = 1.0
        if s.upper().endswith("K"):
            mult = 1_000; s = s[:-1]
        elif s.upper().endswith("M"):
            mult = 1_000_000; s = s[:-1]
        elif s.upper().endswith("B"):
            mult = 1_000_000_000; s = s[:-1]
        try:
            return float(s) * mult
        except (ValueError, TypeError):
            return None

    def _map_ind(title: str) -> str | None:
        t = title.lower().strip()
        for fragment, ind_key in INDICATOR_MAP:  # longest-first sorted
            if fragment in t:
                return ind_key
        return None

    # Collect best candidate per indicator
    # key: ind_name → {actual, previous, forecast, date_str, has_actual: bool}
    best: dict[str, dict] = {}

    for ev in events:
        # Match currency — FF uses 'currency' field (e.g. "USD", "EUR")
        ev_ccy = str(ev.get("currency") or ev.get("country") or "").lower().strip()
        if ev_ccy != ccy_lower:
            continue

        impact = str(ev.get("impact") or "Low").lower()
        if impact in ("low", "holiday", ""):
            continue

        title    = str(ev.get("title") or ev.get("name") or "").strip()
        ind_name = _map_ind(title)
        if not ind_name or ind_name in _FF_SKIP_INDICATORS:
            continue

        actual_val   = _num(ev.get("actual"))
        previous_val = _num(ev.get("previous"))
        forecast_val = _num(ev.get("forecast"))

        # Parse event date
        try:
            ev_date = pd.to_datetime(ev.get("date"), errors="coerce")
            if pd.isna(ev_date):
                continue
            if ev_date.tzinfo is not None:
                ev_date = ev_date.tz_localize(None)
            date_str = ev_date.strftime("%Y-%m-%d")
        except Exception:
            continue

        # Build candidate
        if actual_val is not None:
            candidate = {
                "actual":     actual_val,
                "previous":   previous_val,
                "forecast":   forecast_val,
                "date":       date_str,
                "has_actual": True,
            }
        elif previous_val is not None:
            # Event not yet released: 'previous' = last release's actual value
            candidate = {
                "actual":     previous_val,
                "previous":   None,
                "forecast":   forecast_val,
                "date":       None,          # date unknown for prev release
                "has_actual": False,
            }
        else:
            continue

        existing = best.get(ind_name)
        if existing is None:
            best[ind_name] = candidate
        elif candidate["has_actual"] and not existing["has_actual"]:
            best[ind_name] = candidate  # prefer confirmed actual over estimate
        elif candidate["has_actual"] == existing["has_actual"]:
            # same quality → take most recent
            c_date = candidate["date"] or ""
            e_date = existing["date"] or ""
            if c_date > e_date:
                best[ind_name] = candidate

    # Convert to official-dict format
    result: dict = {}
    for ind_name, b in best.items():
        result[ind_name] = {
            "actual":   b["actual"],
            "previous": b["previous"],
            "forecast": b["forecast"],
            "date":     b["date"],
            "source":   "ForexFactory",
        }

    return result


@st.cache_data(ttl=900, show_spinner=False)
def fetch_upcoming_events() -> list[dict]:
    """
    Fetch upcoming Tier-1/2 economic events for all 8 currencies from ForexFactory feeds.

    Filters:
    - actual is null (not yet released)
    - date is in the future
    - currency in the 8 major FX currencies
    - impact is High (Medium excluded — too noisy)
    - title NOT in _CAL_SKIP_KW (removes duplicates / speeches / noise)
    - title matches Tier-1 or Tier-2 keyword sets (no High-impact fallback)

    Returns list of dicts sorted by date (max 7 events):
      {dt, date_str, weekday, currency, title, tier, impact, forecast}
    Returns [] on any failure — callers must handle empty list gracefully.
    """
    from datetime import timezone as _tz
    events: list[dict] = []
    for url in _FF_MACRO_URLS:
        try:
            r = requests.get(url, timeout=10, headers=_FF_MACRO_HDR)
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, list):
                    events.extend(data)
        except Exception:
            pass
        time.sleep(0.05)

    if not events:
        return []

    now = datetime.now(_tz.utc)
    upcoming: list[dict] = []

    for ev in events:
        # Skip already-released events
        if ev.get("actual") not in (None, ""):
            continue
        # Currency filter
        ccy = (ev.get("country") or "").lower().strip()
        if ccy not in _CAL_CURRENCIES:
            continue
        # Impact filter — High only (Medium too noisy for direct-bias events)
        impact = (ev.get("impact") or "").strip()
        if impact != "High":
            continue
        # Parse ISO date
        date_raw = ev.get("date") or ""
        try:
            dt = datetime.fromisoformat(date_raw.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=_tz.utc)
        except Exception:
            continue
        if dt <= now:
            continue

        title = (ev.get("title") or "").strip()
        tl = title.lower()

        # Skip noise: duplicates, speeches, non-standard variants
        if any(kw in tl for kw in _CAL_SKIP_KW):
            continue

        # Tier classification — explicit keyword match required, no High-impact fallback
        if any(kw in tl for kw in _CAL_TIER1_KW):
            tier = "1"
        elif any(kw in tl for kw in _CAL_TIER2_KW):
            tier = "2"
        else:
            continue  # High-impact but no matching keyword → skip

        upcoming.append({
            "dt":       dt,
            "date_str": dt.strftime("%b %d"),
            "weekday":  dt.strftime("%a"),
            "currency": ccy.upper(),
            "title":    title,
            "tier":     tier,
            "impact":   impact,
            "forecast": (ev.get("forecast") or "—").strip() or "—",
        })

    # Sort chronologically, deduplicate same event on same day, cap at 7
    upcoming.sort(key=lambda x: x["dt"])
    seen: set[tuple] = set()
    result: list[dict] = []
    for ev in upcoming:
        key = (ev["currency"], ev["title"][:20], ev["date_str"])
        if key not in seen:
            seen.add(key)
            result.append(ev)
        if len(result) >= 7:
            break

    return result


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_investing_history(currency: str) -> dict[str, list[tuple[str, float]]]:
    """
    Fetch 12-month economic indicator history from Investing.com economic calendar.

    Fetches in two ~210-day chunks to stay under the 200-row API cap per request,
    merges both results, and deduplicates by row-id and by month.

    Returns {indicator_name: [(YYYY-MM, value) pairs oldest→newest]} for:
    Manufacturing PMI, Services PMI, Composite PMI, GDP Growth (QoQ only),
    Retail Sales, Industrial Production, Consumer Confidence, Business Confidence,
    Unemployment Rate, CPI m/m, Core CPI, PPI

    Does NOT return Interest Rate (CB APIs are more precise).
    Never raises — returns {} on any failure.
    Cache: 1 hour.
    """
    import re as _re
    from collections import defaultdict

    if not _BS4:
        return {}

    cc = _INV_CCY_CODE.get(currency)
    if not cc:
        return {}

    today = datetime.today()
    # USD calendar is denser (~200 events per 5 months) — use 3 × 5-month chunks.
    # Other currencies use 2 × 7-month chunks.  5-day overlaps prevent gaps.
    if currency == "USD":
        chunks = [
            ((today - timedelta(days=450)).strftime("%Y-%m-%d"),
             (today - timedelta(days=295)).strftime("%Y-%m-%d")),
            ((today - timedelta(days=300)).strftime("%Y-%m-%d"),
             (today - timedelta(days=145)).strftime("%Y-%m-%d")),
            ((today - timedelta(days=150)).strftime("%Y-%m-%d"),
             today.strftime("%Y-%m-%d")),
        ]
    else:
        chunks = [
            ((today - timedelta(days=420)).strftime("%Y-%m-%d"),
             (today - timedelta(days=210)).strftime("%Y-%m-%d")),
            ((today - timedelta(days=215)).strftime("%Y-%m-%d"),
             today.strftime("%Y-%m-%d")),
        ]

    def _fetch_chunk(d_from: str, d_to: str):
        """POST one request and return a BeautifulSoup or None."""
        post_data = {
            "dateFrom":      d_from,
            "dateTo":        d_to,
            "country[]":     cc,
            "timeZone":      "55",
            "timeFilter":    "timeRemain",
            "currentTab":    "custom",
            "submitFilters": "1",
            "limit_from":    "0",
            "importance[]":  ["2", "3"],
        }
        try:
            r = requests.post(_INV_URL, headers=_INV_HDR, data=post_data, timeout=20)
            if r.status_code != 200:
                return None
            html = r.json().get("data", "")
            return BeautifulSoup(html, "html.parser") if html else None
        except Exception:
            return None

    def _num(txt: str) -> float | None:
        s = str(txt).strip().replace(",", "").replace("%", "").replace(" ", "")
        if s in ("", "-", "N/A", "None"):
            return None
        if s.upper().endswith("K"):
            try:
                return float(s[:-1]) * 1_000
            except Exception:
                return None
        try:
            return float(s)
        except (ValueError, TypeError):
            return None

    # Alternative event-name fragments that Investing.com uses for Consumer Confidence
    # (not in the global map to avoid conflicts with Business Confidence / ZEW)
    _CC_ALT = ("consumer sentiment", "economic sentiment")

    def _map_name(raw: str) -> str | None:
        """Map Investing.com event name to our indicator key."""
        t = raw.lower().strip()
        t = _re.sub(r'\s*\([^)]*\)', '', t).strip()
        for fragment, ind_key in _INV_NAME_MAP:
            if fragment in t:
                return ind_key
        # Fallback: check alternative Consumer Confidence synonyms
        if any(kw in raw.lower() for kw in _CC_ALT):
            return "Consumer Confidence"
        return None

    # GDP: only keep QoQ official releases; skip YoY, GDPNow, Atlanta Fed
    _GDP_KEEP_KW = ("q/q", "qoq", "advance", "second", "third", "annualized")
    _GDP_SKIP_KW = ("y/y", "yoy", "atlanta", "gdpnow")

    # Skip indicators handled by more precise dedicated sources
    _SKIP = {"Interest Rate"}

    ind_events: dict[str, list[tuple[str, float]]] = defaultdict(list)
    seen_row_ids: set[str] = set()

    for d_from, d_to in chunks:
        soup = _fetch_chunk(d_from, d_to)
        if not soup:
            continue

        for row in soup.find_all("tr", id=_re.compile(r"^eventRowId_")):
            row_id = row["id"].replace("eventRowId_", "")
            if row_id in seen_row_ids:
                continue                        # already processed from other chunk
            seen_row_ids.add(row_id)

            dt_str = row.get("data-event-datetime", "")[:10]  # "2025/05/02"
            if not dt_str:
                continue

            name_td = row.find("td", class_="event")
            raw_name = name_td.get_text(strip=True) if name_td else ""
            if not raw_name:
                continue

            ind_name = _map_name(raw_name)
            if not ind_name or ind_name in _SKIP:
                continue

            # GDP: enforce QoQ-only, exclude GDPNow / Atlanta estimates
            if ind_name == "GDP Growth":
                rl = raw_name.lower()
                if any(kw in rl for kw in _GDP_SKIP_KW):
                    continue
                if not any(kw in rl for kw in _GDP_KEEP_KW):
                    continue

            act_td = soup.find(id=f"eventActual_{row_id}")
            actual = _num(act_td.get_text(strip=True)) if act_td else None
            if actual is None and act_td:
                sp = act_td.find("span")
                actual = _num(sp.get_text(strip=True)) if sp else None

            if actual is None:
                continue

            ind_events[ind_name].append((dt_str, actual))

    # For each indicator: sort by date, deduplicate by month (keep final/revised),
    # return oldest→newest, capped at 14 values
    result: dict[str, list[float]] = {}
    for ind_name, events_list in ind_events.items():
        events_list.sort(key=lambda x: x[0])
        monthly: dict[str, float] = {}
        for dt, val in events_list:
            month_key = dt.replace("/", "-")[:7]   # "2025/05/02" → "2025-05"
            monthly[month_key] = val               # overwrite → keeps later (final) release
        sorted_pairs = sorted(monthly.items())   # [(YYYY-MM, value), ...] oldest→newest
        if len(sorted_pairs) >= 2:
            result[ind_name] = sorted_pairs[-14:]

    return result


# ╔══════════════════════════════════════════════════════════════════════════════
# ║  12-MONTH HISTORY FETCHERS
# ╚══════════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=TTL_HISTORY, show_spinner=False)
def fetch_fred_history(api_key: str) -> dict[str, list[tuple[str, float]]]:
    """
    Fetch 12-month rolling history for USD indicators via FRED.
    Returns {indicator_name: [(YYYY-MM, value), ...]} oldest→newest, up to 14 entries.
    """
    if not api_key or api_key.strip() in ("", "your_key_here", "your_fred_api_key_here"):
        return {}

    FRED_HIST = {
        "CPI m/m":               ("CPIAUCSL",          "mom"),
        "Core CPI":               ("CPILFESL",          "mom"),
        "Interest Rate":          ("FEDFUNDS",          "latest"),
        "Unemployment Rate":      ("UNRATE",            "latest"),
        "Retail Sales":           ("RSXFS",             "mom"),
        "Industrial Production":  ("INDPRO",            "mom"),
        "Employment Change":      ("PAYEMS",            "diff"),
        "M2 Money Supply":        ("M2SL",              "yoy"),
        "Wage Growth":            ("CES0500000003",     "yoy"),
        "Trade Balance":          ("BOPGSTB",           "latest"),
        # Quarterly, already annualised QoQ rate — no derivation needed
        "GDP Growth":             ("A191RL1Q225SBEA",   "latest"),
    }
    result: dict[str, list[tuple[str, float]]] = {}
    for ind, (sid, mode) in FRED_HIST.items():
        try:
            limit = 28 if mode == "yoy" else 18
            r = requests.get(
                FRED_BASE,
                params={"series_id": sid, "api_key": api_key,
                        "sort_order": "desc", "limit": limit, "file_type": "json"},
                timeout=8,
            )
            if r.status_code != 200:
                continue
            obs = [o for o in r.json().get("observations", []) if o.get("value", ".") != "."]
            if len(obs) < 2:
                continue
            obs.reverse()  # oldest first

            # Each pair: (YYYY-MM, derived_value). Date = observation month of obs[i].
            if mode == "latest":
                pairs = [(o["date"][:7], float(o["value"])) for o in obs]
            elif mode == "mom":
                pairs = []
                for i in range(1, len(obs)):
                    c = float(obs[i]["value"]); p = float(obs[i - 1]["value"])
                    pairs.append((obs[i]["date"][:7],
                                  round((c - p) / max(abs(p), 0.001) * 100, 3)))
            elif mode == "diff":
                pairs = []
                for i in range(1, len(obs)):
                    pairs.append((obs[i]["date"][:7],
                                  round(float(obs[i]["value"]) - float(obs[i - 1]["value"]), 1)))
            elif mode == "yoy":
                if len(obs) < 13:
                    continue
                pairs = []
                for i in range(12, len(obs)):
                    c = float(obs[i]["value"]); y = float(obs[i - 12]["value"])
                    pairs.append((obs[i]["date"][:7],
                                  round((c - y) / max(abs(y), 0.001) * 100, 3)))
            else:
                continue
            # FRED Trade Balance is in millions USD — convert to billions
            if ind == "Trade Balance":
                pairs = [(d, round(v / 1000.0, 2)) for d, v in pairs]
            result[ind] = pairs[-14:]
        except Exception:
            continue
    return result


# ── helper: parse ECB/Eurostat CSV (comma-sep, TIME_PERIOD + OBS_VALUE cols) ──
def _parse_ecb_csv(text: str) -> list[tuple[str, float]]:
    lines = [l for l in text.splitlines() if l.strip()]
    if not lines:
        return []
    headers = [h.strip().upper() for h in lines[0].split(",")]
    try:
        tc = headers.index("TIME_PERIOD")
        vc = headers.index("OBS_VALUE")
    except ValueError:
        return []
    pairs: list[tuple[str, float]] = []
    for line in lines[1:]:
        parts = line.split(",")
        if len(parts) <= max(tc, vc):
            continue
        try:
            pairs.append((parts[tc].strip(), float(parts[vc].strip())))
        except (ValueError, IndexError):
            continue
    pairs.sort(key=lambda x: x[0])
    return pairs


# ── helper: resample daily ECB series to monthly last value ───────────────────
def _daily_to_monthly(pairs: list[tuple[str, float]]) -> list[tuple[str, float]]:
    monthly: dict[str, float] = {}
    for date_str, val in pairs:
        ym = date_str[:7]        # "YYYY-MM"
        monthly[ym] = val        # last daily value of each month wins
    return sorted(monthly.items())


@st.cache_data(ttl=TTL_HISTORY, show_spinner=False)
def fetch_ecb_history() -> dict[str, list[tuple[str, float]]]:
    """EUR: ECB API (rate, CPI YoY) + Eurostat (unemployment).
    Returns {indicator: [(YYYY-MM, value), ...]} oldest→newest."""
    START = "2025-01"
    result: dict[str, list[tuple[str, float]]] = {}

    # 1 — ECB Deposit Facility Rate (daily → monthly)
    try:
        r = requests.get(
            "https://data-api.ecb.europa.eu/service/data/FM/D.U2.EUR.4F.KR.DFR.LEV"
            f"?format=csvdata&startPeriod={START}", timeout=10,
        )
        if r.status_code == 200:
            pairs   = _parse_ecb_csv(r.text)
            monthly = _daily_to_monthly(pairs)
            if monthly:
                result["Interest Rate"] = list(monthly[-14:])
    except Exception:
        pass

    # 2 — ECB HICP annual rate (monthly, %)
    try:
        r = requests.get(
            "https://data-api.ecb.europa.eu/service/data/ICP/M.U2.N.000000.4.ANR"
            f"?format=csvdata&startPeriod={START}", timeout=10,
        )
        if r.status_code == 200:
            pairs = _parse_ecb_csv(r.text)
            if pairs:
                result["CPI YoY"] = list(pairs[-14:])
    except Exception:
        pass

    # 3 — Eurostat unemployment (monthly JSON-stat)
    try:
        r = requests.get(
            "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/ei_lmhr_m"
            "?format=JSON&geo=EA20&s_adj=NSA&unit=PC_ACT&indic=LM-UN-T-TOT", timeout=12,
        )
        if r.status_code == 200:
            js   = r.json()
            cats = (js.get("dimension", {}).get("time", {})
                    .get("category", {}).get("label", {}))
            # cats: {"0": "2024-01", "1": "2024-02", ...} — keys are numeric strings
            vals_dict = js.get("value", {})
            pairs_u: list[tuple[str, float]] = []
            for idx_str, period in cats.items():
                # Keys in vals_dict may be int or string — try both without int() on period
                val = vals_dict.get(idx_str)
                if val is None:
                    val = vals_dict.get(int(idx_str)) if idx_str.isdigit() else None
                if val is not None:
                    pairs_u.append((period, float(val)))
            pairs_u.sort(key=lambda x: x[0])  # ISO date strings sort correctly
            recent = [(p, v) for p, v in pairs_u if p >= START]
            if recent:
                result["Unemployment Rate"] = list(recent[-14:])
    except Exception:
        pass

    return result


@st.cache_data(ttl=TTL_HISTORY, show_spinner=False)
def fetch_boe_history() -> dict[str, list[float]]:
    """GBP: BOE CSV — Interest Rate monthly (already live)."""
    result: dict[str, list[float]] = {}
    try:
        from_y = datetime.today().year - 2
        to_y   = datetime.today().year + 1
        # Use the CSV download endpoint (not the HTML viewer)
        url = (
            "https://www.bankofengland.co.uk/boeapps/database/_iadb-fromshowcolumns.asp"
            f"?csv.x=yes&Datefrom=01/Jan/{from_y}&Dateto=31/Dec/{to_y}"
            "&SeriesCodes=IUMABEDR&CSVF=TT&UsingCodes=Y"
        )
        r = requests.get(url, timeout=12, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code == 200 and "DATE" in r.text:
            pairs: list[tuple[str, float]] = []
            for line in r.text.splitlines():
                parts = line.strip().split(",")
                if len(parts) < 2:
                    continue
                try:
                    # date is "DD Mon YYYY" → convert to "YYYY-MM"
                    from datetime import datetime as _dt
                    d    = _dt.strptime(parts[0].strip(), "%d %b %Y")
                    ym   = d.strftime("%Y-%m")
                    pairs.append((ym, float(parts[1].strip())))
                except (ValueError, IndexError):
                    continue
            pairs.sort(key=lambda x: x[0])
            if pairs:
                result["Interest Rate"] = [v for _, v in pairs[-14:]]
    except Exception:
        pass
    return result


# RBA blocks "Mozilla/*" User-Agent but accepts the default python-requests UA
# Omit User-Agent to let requests use its default ("python-requests/X.X.X")
_RBA_HDR: dict[str, str] = {}

def _parse_rba_csv(text: str, series_id: str) -> list[tuple[str, float]]:
    """
    Parse RBA CSV table. Row 10 contains Series IDs; data starts row 11.
    Returns list of (YYYY-MM, value) pairs sorted oldest-first.
    """
    lines = text.splitlines()
    if len(lines) < 12:
        return []
    id_row   = lines[10].split(",")          # "Series ID,FIRMMCRT,FIRMMCRI,..."
    try:
        col = id_row.index(series_id)        # 1-based position in split
    except ValueError:
        return []
    pairs: list[tuple[str, float]] = []
    for line in lines[11:]:
        parts = line.split(",")
        if len(parts) <= col:
            continue
        try:
            # date is "DD/MM/YYYY"
            d  = datetime.strptime(parts[0].strip(), "%d/%m/%Y")
            ym = d.strftime("%Y-%m")
            v  = float(parts[col].strip())
            pairs.append((ym, v))
        except (ValueError, IndexError):
            continue
    pairs.sort(key=lambda x: x[0])
    return pairs


@st.cache_data(ttl=TTL_HISTORY, show_spinner=False)
def fetch_rba_history() -> dict[str, list[float]]:
    """AUD: RBA public CSV tables — rate, unemployment, trade, CPI (quarterly)."""
    START = "2025-01"
    result: dict[str, list[float]] = {}

    # 1 — Cash Rate Target (f1.1, FIRMMCRT)
    try:
        r = requests.get("https://www.rba.gov.au/statistics/tables/csv/f1.1-data.csv",
                         headers=_RBA_HDR, timeout=12)
        if r.status_code == 200:
            pairs = _parse_rba_csv(r.text, "FIRMMCRT")
            recent = [(p, v) for p, v in pairs if p >= START]
            if recent:
                result["Interest Rate"] = [v for _, v in recent[-14:]]
    except Exception:
        pass

    # 2 — Unemployment Rate (h5, GLFSURSA = seasonally adjusted)
    try:
        r = requests.get("https://www.rba.gov.au/statistics/tables/csv/h5-data.csv",
                         headers=_RBA_HDR, timeout=12)
        if r.status_code == 200:
            pairs = _parse_rba_csv(r.text, "GLFSURSA")
            recent = [(p, v) for p, v in pairs if p >= START]
            if recent:
                result["Unemployment Rate"] = [v for _, v in recent[-14:]]
    except Exception:
        pass

    # 3 — Trade Balance (i1) — compute as HXEGSCVTOT minus HMIGSCVTOT (both $M)
    try:
        r = requests.get("https://www.rba.gov.au/statistics/tables/csv/i1-data.csv",
                         headers=_RBA_HDR, timeout=12)
        if r.status_code == 200:
            lines_i1 = r.text.splitlines()
            if len(lines_i1) >= 12:
                id_row_i1 = lines_i1[10].split(",")
                try:
                    exp_col = id_row_i1.index("HXEGSCVTOT")
                    imp_col = id_row_i1.index("HMIGSCVTOT")
                    tb_pairs: list[tuple[str, float]] = []
                    for line in lines_i1[11:]:
                        parts = line.split(",")
                        if len(parts) <= max(exp_col, imp_col):
                            continue
                        try:
                            d  = datetime.strptime(parts[0].strip(), "%d/%m/%Y")
                            ym = d.strftime("%Y-%m")
                            ev = float(parts[exp_col].strip())
                            iv = float(parts[imp_col].strip())
                            tb_pairs.append((ym, round((ev - iv) / 1000.0, 2)))  # → $B
                        except (ValueError, IndexError):
                            continue
                    tb_pairs.sort(key=lambda x: x[0])
                    recent = [(p, v) for p, v in tb_pairs if p >= START]
                    if recent:
                        result["Trade Balance"] = [v for _, v in recent[-8:]]  # quarterly
                except ValueError:
                    pass
    except Exception:
        pass

    # 4 — CPI quarterly (g1) — GCPIAG = CPI all groups SA
    try:
        r = requests.get("https://www.rba.gov.au/statistics/tables/csv/g1-data.csv",
                         headers=_RBA_HDR, timeout=12)
        if r.status_code == 200:
            # GCPIAG = CPI All Groups, seasonally adjusted index
            pairs = _parse_rba_csv(r.text, "GCPIAG")
            if len(pairs) >= 2:
                # Convert index to quarterly % change
                qoq: list[tuple[str, float]] = []
                for i in range(1, len(pairs)):
                    prev = pairs[i-1][1]
                    if prev and abs(prev) > 1e-6:
                        pct = (pairs[i][1] - prev) / prev * 100
                        qoq.append((pairs[i][0], round(pct, 3)))
                recent = [(p, v) for p, v in qoq if p >= START]
                if recent:
                    result["CPI m/m"] = [v for _, v in recent[-8:]]  # quarterly
    except Exception:
        pass

    return result


@st.cache_data(ttl=TTL_HISTORY, show_spinner=False)
def fetch_boc_history() -> dict[str, list[float]]:
    """CAD: Bank of Canada Valet API — policy rate (V39079), CPI (V41690973)."""
    START = "2025-01"
    result: dict[str, list[float]] = {}

    def _valet(series: str) -> list[tuple[str, float]]:
        r = requests.get(
            f"https://www.bankofcanada.ca/valet/observations/{series}/json?recent=500",
            timeout=10,
        )
        if r.status_code != 200:
            return []
        pairs: list[tuple[str, float]] = []
        for obs in r.json().get("observations", []):
            try:
                d   = obs["d"][:7]          # "YYYY-MM"
                val = float(obs[series]["v"])
                pairs.append((d, val))
            except (KeyError, ValueError, TypeError):
                continue
        # deduplicate by month (last value wins)
        monthly: dict[str, float] = {}
        for d, v in pairs:
            monthly[d] = v
        return sorted(monthly.items())

    # 1 — Policy Rate (V39079, daily → monthly)
    try:
        pairs = _valet("V39079")
        recent = [(p, v) for p, v in pairs if p >= START]
        if recent:
            result["Interest Rate"] = [v for _, v in recent[-14:]]
    except Exception:
        pass

    # 2 — CPI All-items index (V41690973) → convert to m/m %
    try:
        pairs = _valet("V41690973")
        if len(pairs) >= 2:
            mom: list[tuple[str, float]] = []
            for i in range(1, len(pairs)):
                prev = pairs[i-1][1]
                if abs(prev) > 1e-6:
                    pct = (pairs[i][1] - prev) / prev * 100
                    mom.append((pairs[i][0], round(pct, 3)))
            recent = [(p, v) for p, v in mom if p >= START]
            if recent:
                result["CPI m/m"] = [v for _, v in recent[-14:]]
    except Exception:
        pass

    return result


@st.cache_data(ttl=TTL_HISTORY, show_spinner=False)
def fetch_snb_history() -> dict[str, list[float]]:
    """CHF: SNB Data Portal API — policy rate (LZ) + CPI YoY (VVP)."""
    START = "2025-01"
    result: dict[str, list[float]] = {}

    def _snb_cube(cube: str, d0_filter: str) -> list[tuple[str, float]]:
        r = requests.get(
            f"https://data.snb.ch/api/cube/{cube}/data/csv/en"
            f"?fromDate={START}",   # SNB uses "YYYY-MM" format with dashes
            timeout=10,
        )
        if r.status_code != 200:
            return []
        pairs: list[tuple[str, float]] = []
        for line in r.text.splitlines():
            line = line.strip().lstrip("﻿").strip('"')
            parts = [p.strip().strip('"') for p in line.split(";")]
            if len(parts) < 3:
                continue
            if parts[1] != d0_filter:
                continue
            try:
                ym  = parts[0][:7]          # "YYYY-MM" or "YYYY/MM"
                ym  = ym.replace("/", "-")
                val = float(parts[2])
                pairs.append((ym, val))
            except (ValueError, IndexError):
                continue
        pairs.sort(key=lambda x: x[0])
        return pairs

    # 1 — SNB sight deposit rate (= policy rate, D0="LZ")
    try:
        pairs = _snb_cube("snboffzisa", "LZ")
        if pairs:
            result["Interest Rate"] = [v for _, v in pairs[-14:]]
    except Exception:
        pass

    # 2 — CPI YoY % change (D0="VVP")
    try:
        pairs = _snb_cube("plkopr", "VVP")
        if pairs:
            result["CPI YoY"] = [v for _, v in pairs[-14:]]
    except Exception:
        pass

    return result


@st.cache_data(ttl=TTL_HISTORY, show_spinner=False)
def fetch_dbnomics_cpi(currency: str) -> dict[str, list[float]]:
    """
    Fetch CPI monthly % change via DBnomics (IMF PCPI_PC_PP_PT series) for JPY.
    Returns {"CPI m/m": [...]} where available.
    NZD is not available via this endpoint — returns {} for NZD.
    """
    CCY_TO_IMF = {"JPY": "JP"}
    iso = CCY_TO_IMF.get(currency)
    if not iso:
        return {}
    result: dict[str, list[float]] = {}
    try:
        url = (
            f"https://api.db.nomics.world/v22/series/IMF/CPI/M.{iso}.PCPI_PC_PP_PT"
            "?observations=1&limit=20"
        )
        r = requests.get(url, timeout=15)
        if r.status_code == 200:
            docs = r.json().get("series", {}).get("docs", [])
            if docs:
                periods = docs[0].get("period", [])
                vals    = docs[0].get("value", [])
                pairs   = [(p, v) for p, v in zip(periods, vals)
                           if v is not None and str(v) not in ("NA", "None")]
                # Use last 14 values available (no date filter — data may lag)
                recent  = [(p, float(v)) for p, v in pairs]
                if recent:
                    result["CPI m/m"] = [v for _, v in recent[-14:]]
    except Exception:
        pass
    return result


@st.cache_data(ttl=TTL_HISTORY, show_spinner=False)
def fetch_oecd_history(country_code: str) -> dict[str, list[float]]:
    """
    Fetch 12-month history from OECD stats.oecd.org SDMX-JSON endpoint.
    country_code: GBR, JPN, AUS, CAN, CHE, NZL
    Returns {indicator_name: [val_oldest, ..., val_newest]} (up to 14 values)
    Falls back to empty dict on any failure.
    Note: response may contain multiple countries — always filter by LOCATION column.
    """
    OECD_MAP = {
        "CPI m/m":               "CPALTT01",
        "Core CPI":              "CPGRLE01",
        "Unemployment Rate":     "LRUNTTTT",
        "Industrial Production": "PRINTO01",
        "Retail Sales":          "SLRTTO01",
        "Interest Rate":         "IR3TIB01",
    }
    start = (datetime.today() - timedelta(days=450)).strftime("%Y-%m")
    result: dict[str, list[float]] = {}
    for ind_name, subject in OECD_MAP.items():
        try:
            url = (
                f"https://stats.oecd.org/SDMX-JSON/data/MEI/"
                f"{subject}.{country_code}.GP.M"
                f"?startTime={start}&contentType=csv"
            )
            r = requests.get(url, timeout=14, headers={"Accept": "text/csv,*/*"})
            if r.status_code != 200:
                continue
            lines = [l for l in r.text.splitlines() if l.strip()]
            # Find header row
            header_idx = next(
                (i for i, l in enumerate(lines) if "TIME_PERIOD" in l.upper()), None
            )
            if header_idx is None:
                continue
            headers = [h.strip().upper() for h in lines[header_idx].split(",")]
            try:
                time_col  = headers.index("TIME_PERIOD")
                value_col = headers.index("OBS_VALUE")
            except ValueError:
                continue
            # LOCATION column — used to filter when API returns multiple countries
            loc_col = headers.index("LOCATION") if "LOCATION" in headers else None
            pairs: list[tuple[str, float]] = []
            for line in lines[header_idx + 1:]:
                parts = line.split(",")
                if len(parts) <= max(time_col, value_col):
                    continue
                # Skip rows that don't belong to the requested country
                if loc_col is not None and len(parts) > loc_col:
                    if parts[loc_col].strip().upper() != country_code.upper():
                        continue
                try:
                    val_str = parts[value_col].strip()
                    if not val_str:
                        continue
                    pairs.append((parts[time_col].strip(), float(val_str)))
                except (ValueError, IndexError):
                    continue
            pairs.sort(key=lambda x: x[0])  # oldest first
            if pairs:
                result[ind_name] = [v for _, v in pairs[-14:]]
        except Exception:
            continue
    return result


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_te_history(country_slug: str, indicator_slug: str) -> list[float]:
    """
    Scrape Trading Economics historical indicator page for 12 monthly values.
    Returns list of floats oldest→newest (up to 14 values), or [] on failure.
    Uses _TE_HEADERS for a browser-like User-Agent.
    """
    if not _BS4:
        return []
    url = f"https://tradingeconomics.com/{country_slug}/{indicator_slug}/historical-data"
    try:
        time.sleep(0.1)  # polite delay
        r = requests.get(url, headers=_TE_HEADERS, timeout=14)
        if r.status_code != 200:
            return []
        soup = BeautifulSoup(r.text, "html.parser")

        # Try finding the main data table — TE uses various IDs/classes
        table = (
            soup.find("table", id="calendar")
            or soup.find("table", id="historicalData")
            or soup.find("table", {"class": lambda c: c and "table" in c.lower()})
        )
        if table is None:
            # Fall back: any table with at least 5 rows of numeric data
            for t in soup.find_all("table"):
                rows = t.find_all("tr")
                if len(rows) >= 5:
                    table = t
                    break

        if table is None:
            return []

        vals: list[float] = []
        for row in table.find_all("tr"):
            cells = row.find_all(["td", "th"])
            if len(cells) < 2:
                continue
            # Value is typically in 2nd cell (index 1) — try first few cells
            for cell_idx in (1, 2):
                if cell_idx >= len(cells):
                    continue
                txt = cells[cell_idx].get_text(strip=True)
                txt = txt.replace(",", "").replace("%", "").replace(" ", "")
                if not txt or txt in ("-", "N/A", "na", "NA"):
                    continue
                try:
                    v = float(txt)
                    vals.append(v)
                    break
                except (ValueError, TypeError):
                    continue

        if not vals:
            return []

        # TE historical pages show newest first — reverse to oldest-first
        vals.reverse()
        return vals[-14:]

    except Exception:
        return []


def _fetch_fred_series_history(series_id: str, fred_api_key: str = "",
                                max_stale_months: int = 5) -> list[tuple[str, float]]:
    """
    Fetch up to 14 months of history for a single FRED series.
    Returns [(YYYY-MM, value), ...] oldest→newest, or [] if unavailable/stale.
    """
    _key = fred_api_key or FRED_API_KEY
    try:
        url = (
            f"https://api.stlouisfed.org/fred/series/observations"
            f"?series_id={series_id}&api_key={_key}&sort_order=desc&limit=16&file_type=json"
        )
        r = requests.get(url, timeout=10)
        if r.status_code != 200:
            return []
        obs = [o for o in r.json().get("observations", []) if o.get("value") != "."]
        if not obs:
            return []
        # Freshness check — obs[0] is newest (sort_order=desc)
        cutoff = (datetime.today() - timedelta(days=max_stale_months * 31)).strftime("%Y-%m")
        if obs[0]["date"][:7] < cutoff:
            return []
        pairs = [(o["date"][:7], float(o["value"])) for o in reversed(obs)]  # oldest first
        return pairs[-14:]
    except Exception:
        return []


def _assign_approximate_dates(
    plain_history: dict[str, list[float]],
) -> dict[str, list[tuple[str, float]]]:
    """
    Assign approximate calendar dates to plain value lists.
    Assumes vals[-1] corresponds to the current month, vals[-2] to last month, etc.
    Used for CB fetchers and HISTORY_FALLBACK that carry no date metadata.
    """
    today = datetime.today()
    dated: dict[str, list[tuple[str, float]]] = {}
    for ind, vals in plain_history.items():
        n = len(vals)
        pairs: list[tuple[str, float]] = []
        for i, v in enumerate(vals):
            months_back = n - 1 - i          # vals[0] = oldest
            total_month = today.month - months_back
            yr = today.year + (total_month - 1) // 12
            mo = ((total_month - 1) % 12) + 1
            pairs.append((f"{yr:04d}-{mo:02d}", v))
        dated[ind] = pairs
    return dated


def _strip_dates(
    dated_history: dict[str, list[tuple[str, float]]],
) -> dict[str, list[float]]:
    """Strip date strings from a dated history dict, returning plain value lists."""
    return {ind: [v for _, v in pairs] for ind, pairs in dated_history.items()}


@st.cache_data(ttl=TTL_HISTORY, show_spinner=False)
def fetch_currency_history(
    currency: str, fred_api_key: str
) -> dict[str, list[tuple[str, float]]]:
    """
    Get 12-month indicator history for a currency.
    Returns {indicator: [(YYYY-MM, value), ...]} oldest→newest.

    Priority: live API (dated) → HISTORY_FALLBACK with approximate dates.
    Sources that return real dates: FRED, ECB, Investing.com, _fetch_fred_series_history.
    Sources that return plain values (BOE, RBA, BOC, SNB, dbnomics, TE, FRED OECD):
      approximate dates are assigned by counting backwards from today.
    """
    live: dict[str, list[tuple[str, float]]] = {}

    if currency == "USD":
        live = fetch_fred_history(fred_api_key)   # returns dated pairs
    elif currency == "EUR":
        live = fetch_ecb_history()                 # returns dated pairs
    elif currency == "GBP":
        live = _assign_approximate_dates(fetch_boe_history())
        _gbr_unemp = _fetch_fred_series_history("LRHUTTTTGBM156S", fred_api_key)
        if _gbr_unemp:
            live["Unemployment Rate"] = _gbr_unemp   # dated pairs from FRED
    elif currency == "AUD":
        live = _assign_approximate_dates(fetch_rba_history())
        _aud_unemp = _fetch_fred_series_history("LRUNTTTTAUM156S", fred_api_key)
        if _aud_unemp:
            live["Unemployment Rate"] = _aud_unemp
    elif currency == "CAD":
        live = _assign_approximate_dates(fetch_boc_history())
        _cad_unemp = _fetch_fred_series_history("LRUNTTTTCAM156S", fred_api_key)
        if _cad_unemp:
            live["Unemployment Rate"] = _cad_unemp
    elif currency == "CHF":
        live = _assign_approximate_dates(fetch_snb_history())
    elif currency == "JPY":
        live = _assign_approximate_dates(fetch_dbnomics_cpi(currency))
        _jpy_unemp = _fetch_fred_series_history("LRUN74TTJPM156S", fred_api_key)
        if _jpy_unemp:
            live["Unemployment Rate"] = _jpy_unemp
    elif currency == "NZD":
        _nzd_rate  = _fetch_fred_series_history("IR3TIB01NZM156N", fred_api_key)
        _nzd_unemp = _fetch_fred_series_history("LRUNTTTTNZQ156S", fred_api_key)
        if _nzd_rate:  live["Interest Rate"]     = _nzd_rate
        if _nzd_unemp: live["Unemployment Rate"] = _nzd_unemp

    # ── Investing.com: returns dated pairs, fills gaps ────────────────────────
    _USD_INV_INDS = {"Manufacturing PMI", "Services PMI"}
    inv_history = fetch_investing_history(currency)   # now returns dated pairs
    for ind_name, dated_vals in inv_history.items():
        if currency == "USD" and ind_name not in _USD_INV_INDS:
            continue   # FRED is authoritative for all other USD indicators
        if ind_name not in live:
            live[ind_name] = dated_vals

    # ── TE historical (plain values → approximate dates) ─────────────────────
    if currency != "USD":
        te_map = _TE_HISTORY_MAP.get(currency, {})
        for ind_name, (country_slug, ind_slug) in te_map.items():
            if ind_name not in live:
                plain_vals = fetch_te_history(country_slug, ind_slug)
                if plain_vals:
                    live[ind_name] = _assign_approximate_dates({ind_name: plain_vals})[ind_name]

    # ── FRED OECD series (returns dated pairs) ────────────────────────────────
    if currency != "USD":
        for ind_name, (sid, _) in _FRED_INTL.get(currency, {}).items():
            if ind_name not in live:
                dated = _fetch_fred_series_history(sid, fred_api_key, max_stale_months=6)
                if dated:
                    live[ind_name] = dated

    # ── HISTORY_FALLBACK — assign approximate dates for anything missing ──────
    fallback_dated = _assign_approximate_dates(HISTORY_FALLBACK.get(currency, {}))
    result: dict[str, list[tuple[str, float]]] = {}
    all_indicators = set(list(live.keys()) + list(fallback_dated.keys()))
    for ind in all_indicators:
        if ind in live and len(live[ind]) >= 3:
            result[ind] = live[ind]
        elif ind in fallback_dated:
            result[ind] = fallback_dated[ind]
    return result


# ╔══════════════════════════════════════════════════════════════════════════════
# ║  NEW 12-MONTH BIAS ENGINE
# ╚══════════════════════════════════════════════════════════════════════════════

def _score_indicator(name: str, vals: list[float]) -> float:
    """
    Context-aware scoring for a single indicator's 12-month history.
    Returns score in [-1.0, +1.0].
    Handles len(vals) < 3 gracefully (returns 0.0).
    """
    if len(vals) < 3:
        return 0.0

    recent  = vals[-3:]      # last 3 months
    older   = vals[:3]       # first 3 months of window
    current = vals[-1]
    trend   = (sum(recent) / len(recent)) - (sum(older) / len(older))

    # --- PMI indicators (neutral = 50) ---
    if name in ("Manufacturing PMI", "Services PMI", "Composite PMI"):
        level_score = (current - 50) / 10      # +1 at 60, -1 at 40
        trend_score = trend / 5                 # +1 if trend +5 pts over window
        return max(-1.0, min(1.0, level_score * 0.6 + trend_score * 0.4))

    # --- Inflation: falling toward target = POSITIVE for FX ---
    if name in ("CPI m/m", "CPI YoY", "Core CPI", "PPI"):
        target = 2.0 / 12 if name in ("CPI m/m", "Core CPI") else 2.0
        overshoot   = current - target
        # Deflation (current < 0) is not bullish — cap bullish contribution at 0
        if current < 0:
            overshoot = max(overshoot, 0)
        trend_punish = trend * 0.5
        raw = -(overshoot / 3.0) - trend_punish
        return max(-1.0, min(1.0, raw))

    # --- Unemployment (lower = better, falling = positive) ---
    if name in ("Unemployment Rate",):
        level_score = -(current - 5.0) / 5    # -1 at 10%, +1 at 0%
        trend_score = -trend / 2               # falling = positive
        return max(-1.0, min(1.0, level_score * 0.5 + trend_score * 0.5))

    # --- GDP Growth (positive = good, rising = better) ---
    if name in ("GDP Growth",):
        # Detect scale: abs(current) < 3.0 → QoQ % (e.g. 0.3%), else annualized % (e.g. 2.0%)
        if abs(current) < 3.0:
            level_norm = current / 0.5   # 0.3% QoQ → 0.6 normalized (≈ comparable to 1.2% annualized)
            trend_norm = trend  / 0.5
        else:
            level_norm = current / 2.0   # 2.0% annualized → 1.0 normalized
            trend_norm = trend  / 2.0
        return max(-1.0, min(1.0, level_norm * 0.6 + trend_norm * 0.4))

    # --- Consumer / Business Confidence ---
    if name in ("Consumer Confidence", "Business Confidence"):
        # ZEW scale: range −100..+100, baseline 0 (detected when abs(current)>20 or min<50)
        # IFO/OECD scale: indexed ~100 (e.g. IFO Business Climate 95–105)
        if abs(current) > 20 or min(vals) < 50:
            # ZEW-style scale
            level_score = current / 100.0
            trend_score = trend / 50.0
            return max(-1.0, min(1.0, level_score * 0.6 + trend_score * 0.4))
        else:
            # IFO/OECD-style scale — relative-to-mean scoring
            mean_val = sum(vals) / len(vals)
            level_score = (current - mean_val) / max(abs(mean_val) * 0.1 + 1.0, 1.0)
            trend_score = trend / max(abs(mean_val) * 0.05 + 0.5, 0.5)
            return max(-1.0, min(1.0, level_score * 0.5 + trend_score * 0.5))

    # --- Interest Rate (higher = bullish for currency, rising trend = bullish) ---
    if name in ("Interest Rate",):
        trend_score = trend / 1.0              # rising rates = bullish
        level_score = (current - 2.0) / 4.0   # above neutral = positive
        return max(-1.0, min(1.0, level_score * 0.4 + trend_score * 0.6))

    # --- Retail Sales, Industrial Production (positive trend = good) ---
    if name in ("Retail Sales", "Industrial Production", "Employment Change"):
        norm_factor = max(abs(sum(vals) / len(vals)), 0.5) if vals else 1.0
        level_score = current / (norm_factor * 3.0)
        trend_score = trend / (norm_factor * 3.0)
        return max(-1.0, min(1.0, level_score * 0.5 + trend_score * 0.5))

    # --- Trade Balance, Current Account (improving = positive) ---
    if name in ("Trade Balance", "Current Account"):
        mean_val = sum(vals) / len(vals) if vals else 0.0
        trend_capped = max(-15.0, min(15.0, trend))   # cap ±15B to prevent single-month swings dominating
        trend_score = trend_capped / max(abs(mean_val) + 0.5, 1.0)
        return max(-1.0, min(1.0, trend_score * 0.5))

    # --- Wage Growth (moderate positive optimal, very high = inflationary) ---
    if name in ("Wage Growth",):
        optimal_dist = abs(current - 3.0)
        level_score  = 1.0 - optimal_dist / 3.0
        return max(-1.0, min(1.0, level_score))

    # --- Default: positive trend = positive (normalised by mean) ---
    norm = abs(sum(vals) / len(vals)) if vals else 1.0
    return max(-1.0, min(1.0, trend / max(norm, 0.001)))


def _score_indicator_series(values: list[float], indicator: str) -> float:
    """
    Wrapper that routes to _score_indicator() for the new context-aware scoring.
    Kept for backwards compatibility with any direct callers.
    """
    return _score_indicator(indicator, values)


def _calc_raw_score(
    history: dict[str, list[float]],
) -> tuple[dict[str, float], float, list[float]]:
    """
    Compute per-indicator scores and raw weighted average for one currency.
    Returns (indicator_scores, raw_weighted_avg, monthly_scores).
    raw_weighted_avg is in roughly [-1, +1] before any normalization.
    """
    indicator_scores: dict[str, float] = {}
    for ind, values in history.items():
        if len(values) >= 3 and ind in _IND_DIRECTION:
            flat = max(values) - min(values) < 0.01
            if flat:
                if ind == "Interest Rate":
                    level = values[-1]
                    if level > 1.5:
                        indicator_scores[ind] = 0.3
                    elif level < 0.5:
                        indicator_scores[ind] = -0.3
                    else:
                        indicator_scores[ind] = 0.0
                continue
            indicator_scores[ind] = _score_indicator(ind, values)

    total_w = sum(_IND_WEIGHTS.get(ind, 0.5) for ind in indicator_scores)
    if total_w > 0:
        raw = sum(indicator_scores[ind] * _IND_WEIGHTS.get(ind, 0.5)
                  for ind in indicator_scores) / total_w
    else:
        raw = 0.0

    # Monthly rolling composite (absolute scale, for chart continuity)
    n_months = max((len(v) for v in history.values()), default=0)
    monthly_scores: list[float] = []
    for m in range(1, n_months + 1):
        m_total, m_w = 0.0, 0.0
        for ind, values in history.items():
            sub = values[:m]
            if len(sub) >= 3 and ind in _IND_DIRECTION:
                flat = max(sub) - min(sub) < 0.01
                if flat:
                    if ind == "Interest Rate":
                        level = sub[-1]
                        s = 0.3 if level > 1.5 else (-0.3 if level < 0.5 else 0.0)
                    else:
                        continue
                else:
                    s = _score_indicator(ind, sub)
                w = _IND_WEIGHTS.get(ind, 0.5)
                m_total += s * w
                m_w     += w
        if m_w > 0:
            monthly_scores.append(round(max(-3.0, min(3.0, (m_total / m_w) * 6.0)), 3))
        else:
            monthly_scores.append(0.0)

    return indicator_scores, raw, monthly_scores


def _label_from_score(score: float) -> tuple[str, str]:
    """Map a normalized [-3, +3] score to label + color."""
    if   score >  0.4: return "BULLISH", C["teal"]
    elif score < -0.4: return "BEARISH", C["red"]
    else:              return "NEUTRAL", C["muted"]


def calc_all_biases(
    all_histories: dict[str, dict[str, list[float]]],
) -> dict[str, dict]:
    """
    Compute z-score-normalized bias for all currencies in all_histories.

    Step 1: Raw weighted score per currency (in roughly [-1, +1]).
    Step 2: Z-normalize across the peer group:
              normalized = (raw - mean) / max(std, 0.1)
    Step 3: Scale to [-3, +3]:
              final = clamp(normalized * 1.2, -3.0, +3.0)

    Returns {currency: result_dict} with the same keys as calc_currency_bias().
    Currencies rank relative to each other — the group mean always maps to ~0.
    """
    import math

    # Step 1 — raw score per currency
    raw_data: dict[str, tuple] = {}
    for ccy, history in all_histories.items():
        ind_scores, raw, monthly = _calc_raw_score(history)
        raw_data[ccy] = (ind_scores, raw, monthly)

    raw_vals = [raw_data[c][1] for c in raw_data]

    # Step 2 — z-normalize
    n = len(raw_vals)
    mean = sum(raw_vals) / n if n else 0.0
    variance = sum((v - mean) ** 2 for v in raw_vals) / n if n else 0.0
    std = math.sqrt(variance)

    # Step 3 — scale and label
    results: dict[str, dict] = {}
    for ccy, (ind_scores, raw, monthly) in raw_data.items():
        normalized = (raw - mean) / max(std, 0.1)
        final      = round(max(-3.0, min(3.0, normalized * 1.2)), 3)
        label, lc  = _label_from_score(final)
        results[ccy] = {
            "score":            final,
            "label":            label,
            "label_color":      lc,
            "indicator_scores": ind_scores,
            "monthly_scores":   monthly,
            "n_indicators":     len(ind_scores),
        }

    return results


def calc_currency_bias(currency: str, history: dict[str, list[float]]) -> dict:
    """
    Calculate currency economic bias purely from 12-month indicator histories.
    No cross-currency comparison. No news. No hardcoded CB priors.

    Returns:
      score           : float [-3, +3]
      label           : str
      label_color     : str
      indicator_scores: {indicator: score [-1, +1]}
      monthly_scores  : list[float] — rolling monthly composite (for chart)
      n_indicators    : int
    """
    indicator_scores: dict[str, float] = {}
    for ind, values in history.items():
        if len(values) >= 3 and ind in _IND_DIRECTION:
            flat = max(values) - min(values) < 0.01
            if flat:
                # Flat Interest Rate: holding position IS a signal
                if ind == "Interest Rate":
                    level = values[-1]
                    if level > 1.5:
                        indicator_scores[ind] = 0.3   # held at restrictive level
                    elif level < 0.5:
                        indicator_scores[ind] = -0.3  # held at accommodative level
                    else:
                        indicator_scores[ind] = 0.0   # neutral hold
                # All other flat series: no real signal — skip
                continue
            indicator_scores[ind] = _score_indicator(ind, values)

    # Weighted average → scale to [-3, +3]
    total_w = sum(_IND_WEIGHTS.get(ind, 0.5) for ind in indicator_scores)
    if total_w > 0:
        raw   = sum(indicator_scores[ind] * _IND_WEIGHTS.get(ind, 0.5)
                    for ind in indicator_scores) / total_w
        final = round(max(-3.0, min(3.0, raw * 6.0)), 3)   # 6× amplifier (was 5×)
    else:
        final = 0.0

    # Monthly rolling composite (12 points for the timeline chart)
    n_months = max((len(v) for v in history.values()), default=0)
    monthly_scores: list[float] = []
    for m in range(1, n_months + 1):
        m_total, m_w = 0.0, 0.0
        for ind, values in history.items():
            sub = values[:m]
            if len(sub) >= 3 and ind in _IND_DIRECTION:
                flat = max(sub) - min(sub) < 0.01
                if flat:
                    if ind == "Interest Rate":
                        level = sub[-1]
                        if level > 1.5:
                            s = 0.3
                        elif level < 0.5:
                            s = -0.3
                        else:
                            s = 0.0
                    else:
                        continue
                else:
                    s = _score_indicator(ind, sub)
                w = _IND_WEIGHTS.get(ind, 0.5)
                m_total += s * w
                m_w     += w
        if m_w > 0:
            monthly_scores.append(round(max(-3.0, min(3.0, (m_total / m_w) * 6.0)), 3))
        else:
            monthly_scores.append(0.0)

    # Label
    if   final >= 1.5:  label, lc = "STRONG BULLISH", C["green"]
    elif final >= 0.3:  label, lc = "SLIGHT BULLISH", C["teal"]
    elif final >= -0.3: label, lc = "NEUTRAL",         C["muted"]
    elif final >= -1.5: label, lc = "SLIGHT BEARISH",  C["yellow"]
    else:               label, lc = "STRONG BEARISH",  C["red"]

    return {
        "score":             final,
        "label":             label,
        "label_color":       lc,
        "indicator_scores":  indicator_scores,
        "monthly_scores":    monthly_scores,
        "n_indicators":      len(indicator_scores),
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




def _calc_bias_score_legacy(indicators_df: pd.DataFrame, currency: str) -> dict:
    """
    Legacy scoring helper — kept for render_all_currencies_overview fallback path only.
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
        if ind in ("Manufacturing PMI", "Services PMI", "Composite PMI"):
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
    if   final >  0.60: level, lc = "STRONG BULLISH", "#1a9b6a"
    elif final >  0.30: level, lc = "SLIGHT BULLISH", C["green"]
    elif final >  0.10: level, lc = "MILD BULLISH",   "#2ab87a"
    elif final >= 0.0:  level, lc = "MILD BULLISH",   "#2ab87a"
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
        bg    = ("rgba(26,155,106,0.10)" if raw > 0.05
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
    "Composite PMI":       (1.00, 3.00),
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
    if ind in ("Manufacturing PMI", "Services PMI", "Composite PMI"):
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
    if diff >  slight: return "SLIGHT BEAT",  "#2ab87a"
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
        "SLIGHT BEAT": ("↑ IMPROVING",      "#2ab87a"),
        "IN LINE":     ("→ STABLE",         C["muted"]),
        "SLIGHT MISS": ("↓ DETERIORATING",  C["yellow"]),
        "STRONG MISS": ("↓↓ STRONG DETER", C["red"]),
        "—":           ("—",                C["muted"]),
    }
    return _map.get(raw_lbl, (raw_lbl, C["muted"]))


# ╔══════════════════════════════════════════════════════════════════════════════
# ║  HTML RENDER FUNCTIONS
# ╚══════════════════════════════════════════════════════════════════════════════

def render_upcoming_calendar(events: list[dict]) -> str:
    """Render mini upcoming economic events calendar as a dark-theme HTML card."""
    cb = C["border"]; cm = C["muted"]; ct = C["text"]
    cy = C["yellow"]; cteal = C["teal"]; card = C["card"]

    header = (
        f"<div style='font-size:10px;color:{cm};font-family:monospace;"
        f"letter-spacing:1.5px;text-transform:uppercase;margin-bottom:8px;'>"
        f"📅 Upcoming Events</div>"
    )

    if not events:
        return (
            f"<div style='background:{card};border:1px solid {cb};"
            f"border-radius:12px;padding:14px 16px;margin-top:12px;'>"
            f"{header}"
            f"<div style='font-size:10px;color:{cm};font-family:monospace;'>"
            f"⚠ Calendar unavailable — ForexFactory feeds unreachable</div></div>"
        )

    rows_html = ""
    prev_date = None
    for ev in events:
        # Date separator
        if ev["date_str"] != prev_date:
            border_top = f"border-top:1px solid {cb};margin-top:4px;" if prev_date else ""
            rows_html += (
                f"<div style='font-size:9px;color:{cm};font-family:monospace;"
                f"letter-spacing:0.8px;padding:5px 0 2px 0;{border_top}'>"
                f"{ev['weekday']} {ev['date_str']}</div>"
            )
            prev_date = ev["date_str"]

        if ev["tier"] == "1":
            tier_color = "#ef4444"
            tier_label = "HIGH"
        elif ev["tier"] == "2":
            tier_color = "#f97316"
            tier_label = "MEDIUM"
        else:
            tier_color = "#eab308"
            tier_label = "LOW"
        flag = CURRENCY_FLAG.get(ev["currency"], "")
        fc   = ev["forecast"]
        fc_html = (
            f"<span style='font-size:8px;color:{cm};font-family:monospace;"
            f"margin-left:4px;'>{fc}</span>"
            if fc != "—" else ""
        )

        rows_html += (
            f"<div style='display:flex;align-items:center;gap:5px;padding:2px 0;'>"
            f"<span style='font-size:11px;line-height:1;'>{flag}</span>"
            f"<span style='font-size:8px;color:{cm};font-family:monospace;"
            f"width:26px;flex-shrink:0;'>{ev['currency']}</span>"
            f"<span style='font-size:9px;color:{ct};font-family:monospace;"
            f"flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;'>"
            f"{ev['title']}{fc_html}</span>"
            f"<span style='font-size:7px;color:{tier_color};font-family:monospace;"
            f"background:{tier_color}20;border:1px solid {tier_color}40;"
            f"border-radius:3px;padding:1px 4px;flex-shrink:0;'>{tier_label}</span>"
            f"</div>"
        )

    footer = (
        f"<div style='font-size:8px;color:{cm};font-family:monospace;"
        f"margin-top:8px;border-top:1px solid {cb};padding-top:6px;'>"
        f"ForexFactory · auto-refresh 15 min · "
        f"<span style='color:#ef4444;'>HIGH</span> = CB-critical &nbsp;"
        f"<span style='color:#f97316;'>MEDIUM</span> = Activity &nbsp;· Only High-Impact events shown</div>"
    )

    return (
        f"<div style='background:{card};border:1px solid {cb};"
        f"border-radius:12px;padding:14px 16px;margin-top:12px;'>"
        f"{header}{rows_html}{footer}</div>"
    )


def render_bias_panel(currency: str, bias_result: dict) -> str:
    """Render the simplified bias gauge panel (no D1-D4 grid)."""
    score  = bias_result.get("score", 0.0)
    label  = bias_result.get("label", "NEUTRAL")
    lc     = bias_result.get("label_color", C["muted"])
    n_ind  = bias_result.get("n_indicators", 0)
    flag   = CURRENCY_FLAG.get(currency, "")
    sign   = "+" if score > 0 else ""
    pct    = max(3.0, min(97.0, (score + 3.0) / 6.0 * 100))

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
                    letter-spacing:1.5px;text-transform:uppercase;'>Economic Bias — 12M Trend</div>
        <div style='font-size:18px;font-weight:800;color:{lc};
                    font-family:monospace;letter-spacing:1px;'>{label}</div>
      </div>
    </div>
    <div style='text-align:right;'>
      <div style='font-size:32px;font-weight:800;color:{lc};
                  font-family:monospace;line-height:1;'>{sign}{score:.2f}</div>
      <div style='font-size:9px;color:{_cm};font-family:monospace;margin-top:4px;'>
        Based on {n_ind} indicators · 12M trend analysis</div>
    </div>
  </div>
  <!-- Gauge bar -->
  <div style='height:10px;border-radius:5px;margin-bottom:4px;
              background:
                linear-gradient(to right,
                  transparent calc({pct:.1f}% - 1.5px),
                  {_ct}        calc({pct:.1f}% - 1.5px),
                  {_ct}        calc({pct:.1f}% + 1.5px),
                  transparent  calc({pct:.1f}% + 1.5px)),
                linear-gradient(to right,
                  #cc1a2a 0%, {_cr} 20%, {_cy} 50%,
                  {_cg} 80%, #138050 100%);'></div>
  <div style='display:flex;justify-content:space-between;font-size:9px;
              font-family:monospace;color:{_cm};margin-bottom:10px;'>
    <span>BEARISH</span><span>NEUTRAL</span><span>BULLISH</span>
  </div>
  <!-- Disclaimer -->
  <div style='border-top:1px solid {_cb};padding-top:8px;font-size:9px;
              color:{_cm};font-family:monospace;line-height:1.6;letter-spacing:0.3px;'>
    ⚠ Long-term macroeconomic indicator only · Short-term price action may be overridden
    by geopolitical events, central bank surprises, or market sentiment
  </div>
</div>"""


def render_economic_charts(
    currency: str,
    bias_result: dict,
    history_dated: dict[str, list[tuple[str, float]]],
) -> None:
    """Render two Plotly charts side by side: 12M strength timeline + indicator bar chart.

    Chart 1 is a true monthly re-score: for each of the last 12 calendar months,
    each indicator's dated history is filtered to data available at or before that
    month, then _calc_raw_score() is called on the filtered subset.
    The rightmost point uses all available data (filter = current month) and matches
    the current live score on the absolute scale.
    """
    indicator_scores = bias_result.get("indicator_scores", {})
    flag = CURRENCY_FLAG.get(currency, "")

    col1, col2 = st.columns([6, 4], gap="medium")

    # ── Chart 1: true monthly re-score (12 calendar months) ──────────────────
    with col1:
        today = datetime.today()
        # Build last 12 calendar months oldest→newest
        chart_month_strs: list[str] = []
        month_labels:     list[str] = []
        for i in range(11, -1, -1):
            total_month = today.month - i
            yr = today.year + (total_month - 1) // 12
            mo = ((total_month - 1) % 12) + 1
            chart_month_strs.append(f"{yr:04d}-{mo:02d}")
            month_labels.append(datetime(yr, mo, 1).strftime("%b %y"))

        monthly_scores: list[float] = []
        for month_str in chart_month_strs:
            # Filter each indicator to data available at this month
            filtered: dict[str, list[float]] = {}
            for ind, dated_pairs in history_dated.items():
                vals_up_to = [v for d, v in dated_pairs if d <= month_str]
                if len(vals_up_to) >= 3:
                    filtered[ind] = vals_up_to
            if filtered:
                _, raw, _ = _calc_raw_score(filtered)
                score = round(max(-3.0, min(3.0, raw * 6.0)), 3)
            else:
                score = 0.0
            monthly_scores.append(score)

        point_colors = [C["green"] if s >= 0 else C["red"] for s in monthly_scores]
        scores_pos   = [max(0.0, s) for s in monthly_scores]
        scores_neg   = [min(0.0, s) for s in monthly_scores]

        fig1 = go.Figure()
        fig1.add_trace(go.Scatter(
            x=month_labels, y=scores_pos,
            fill="tozeroy", fillcolor="rgba(26,155,106,0.10)",
            line=dict(width=0), showlegend=False, mode="none",
        ))
        fig1.add_trace(go.Scatter(
            x=month_labels, y=scores_neg,
            fill="tozeroy", fillcolor="rgba(240,82,98,0.10)",
            line=dict(width=0), showlegend=False, mode="none",
        ))
        fig1.add_trace(go.Scatter(
            x=month_labels, y=monthly_scores,
            mode="lines+markers",
            line=dict(color=C["teal"], width=2.5),
            marker=dict(size=7, color=point_colors,
                        line=dict(width=1.5, color=C["bg"])),
            showlegend=False,
        ))
        fig1.add_hline(y=0, line_dash="dot", line_color=C["muted"], line_width=1)
        fig1.add_hrect(y0=1.5, y1=3.2, fillcolor="rgba(26,155,106,0.04)", line_width=0)
        fig1.add_hrect(y0=-3.2, y1=-1.5, fillcolor="rgba(240,82,98,0.04)", line_width=0)

        fig1.update_layout(
            paper_bgcolor=C["bg"],
            plot_bgcolor=C["card"],
            title=dict(
                text=f"{flag} {currency} — Economic Strength (12M)",
                font=dict(color=C["text"], size=12, family="monospace"),
                x=0, pad=dict(l=4),
            ),
            yaxis=dict(
                range=[-3.3, 3.3],
                gridcolor=C["border"],
                color=C["muted"],
                tickvals=[-3, -1.5, 0, 1.5, 3],
                ticktext=["−3", "−1.5", "0", "+1.5", "+3"],
                tickfont=dict(size=10, family="monospace"),
                zeroline=False,
            ),
            xaxis=dict(
                gridcolor=C["border"],
                color=C["muted"],
                tickangle=-35,
                tickfont=dict(size=10, family="monospace"),
            ),
            margin=dict(t=44, l=48, r=12, b=44),
            height=280,
            font=dict(family="monospace"),
        )
        st.plotly_chart(fig1, use_container_width=True, config={"displayModeBar": False})

        # ── Upcoming Events Calendar (below 12M chart, left column) ──────
        _upcoming = fetch_upcoming_events()
        st.markdown(render_upcoming_calendar(_upcoming), unsafe_allow_html=True)

    # ── Chart 2: Indicator contribution bar chart ─────────────────────────────
    with col2:
        if indicator_scores:
            sorted_inds = sorted(indicator_scores.items(), key=lambda x: x[1])
            labels = [ind for ind, _ in sorted_inds]
            scores = [s for _, s in sorted_inds]
            bar_colors = [
                C["green"]  if s >  0.25 else
                C["red"]    if s < -0.25 else
                C["yellow"]
                for s in scores
            ]

            fig2 = go.Figure(go.Bar(
                x=scores, y=labels,
                orientation="h",
                marker=dict(color=bar_colors, line=dict(width=0)),
                text=[f"{s:+.2f}" for s in scores],
                textposition="outside",
                textfont=dict(color=C["muted"], size=9, family="monospace"),
                cliponaxis=False,
            ))
            fig2.add_vline(x=0, line_color=C["muted"], line_width=1)

            fig2.update_layout(
                paper_bgcolor=C["bg"],
                plot_bgcolor=C["card"],
                title=dict(
                    text="Indicator Scores",
                    font=dict(color=C["text"], size=12, family="monospace"),
                    x=0, pad=dict(l=4),
                ),
                xaxis=dict(
                    range=[-1.35, 1.35],
                    gridcolor=C["border"],
                    color=C["muted"],
                    zeroline=False,
                    tickformat="+.1f",
                    tickfont=dict(size=10, family="monospace"),
                ),
                yaxis=dict(
                    color=C["text"],
                    tickfont=dict(size=10, family="monospace"),
                    gridcolor=C["border"],
                ),
                margin=dict(t=44, l=8, r=60, b=20),
                height=max(280, len(labels) * 26 + 80),
                font=dict(family="monospace"),
            )
            st.plotly_chart(fig2, use_container_width=True, config={"displayModeBar": False})


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




# NOTE: Pair divergence panel removed from Macro Dashboard.
# It will be part of Module 4 (Correlation / Geo Scanner).


def render_all_currencies_overview(selected_ccy: str) -> str:
    """
    Build the All Currencies Bias panel using cached session_state scores.
    Shows all 8 currencies ranked strongest → weakest with color-coded bias labels.
    Falls back to HISTORY_FALLBACK scores if session_state not populated.
    """
    # If any currency is missing from session state, compute normalized fallback
    # for all 8 at once so rankings remain relative.
    _need_fallback = any(
        not (st.session_state.get(f"macro_scores_{c}")
             and st.session_state[f"macro_scores_{c}"].get("fmt") == "indicator_12m")
        for c in SUPPORTED_CURRENCIES
    )
    _fb_biases: dict = {}
    if _need_fallback:
        _fb_biases = calc_all_biases(
            {c: HISTORY_FALLBACK.get(c, {}) for c in SUPPORTED_CURRENCIES}
        )

    rows_data = []
    for ccy in SUPPORTED_CURRENCIES:
        cached = st.session_state.get(f"macro_scores_{ccy}")
        if cached and cached.get("fmt") == "indicator_12m":
            total = cached["total"]
            level = cached["level"]
        else:
            # Use z-normalized fallback scores (computed once above)
            _b    = _fb_biases.get(ccy, {})
            total = _b.get("score", 0.0)
            level = _b.get("label", "NEUTRAL")
        rows_data.append({"ccy": ccy, "total": total, "level": level})

    rows_data.sort(key=lambda x: x["total"], reverse=True)

    _LEVEL_COLOR = {
        "BULLISH": C["teal"],
        "NEUTRAL": C["muted"],
        "BEARISH": C["red"],
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
        border = (f"border-left:3px solid {C['teal']};" if is_selected
                  else f"border-left:3px solid {lc};")

        bar_pct   = max(2.0, min(98.0, (total + 3.0) / 6.0 * 100))
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
        f"<div style='padding:6px 12px;font-size:9px;color:{C['muted']};font-family:monospace;border-top:1px solid {C['border']};'>Score range: −3.0 to +3.0 · 12M trend analysis · Navigate above to update</div>"
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
      /* ── Radio → pill tabs ── */
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
      button[kind="secondary"] {{
          background:{C['dim']} !important; color:{C['muted']} !important;
          border:1px solid {C['border']} !important;
          font-family:monospace !important; font-weight:600 !important;
          border-radius:20px !important;
      }}
      button[kind="secondary"]:hover {{
          border-color:{C['teal']} !important; color:{C['teal']} !important;
      }}
      button[kind="primary"] {{
          background:{C['teal']} !important; color:#0a0c10 !important;
          border:1px solid {C['teal']} !important;
          font-family:monospace !important; font-weight:700 !important;
          border-radius:20px !important;
      }}
      button[kind="primary"]:hover {{
          background:{C['teal']} !important; opacity:0.9 !important;
      }}
      p, span, label {{ color:{C['text']}; }}
      div[data-testid="stSpinner"] p {{ color:{C['muted']} !important;
          font-family:monospace !important; font-size:12px !important; }}
      div[data-testid="stHorizontalBlock"] {{ align-items: stretch !important; }}
      div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] {{
          display: flex !important; flex-direction: column !important;
      }}
    </style>
    """, unsafe_allow_html=True)

    # ── Session state & auto-refresh timer ────────────────────────────────────
    _now = time.time()
    if "mf_currency" not in st.session_state:
        st.session_state.mf_currency = "USD"
    if "last_refresh_ts" not in st.session_state:
        st.session_state.last_refresh_ts = _now

    if _now - st.session_state.last_refresh_ts > AUTO_RERUN_INTERVAL:
        fetch_currency_history.clear()
        fetch_fred_history.clear()
        fetch_ecb_history.clear()
        fetch_boe_history.clear()
        fetch_rba_history.clear()
        fetch_boc_history.clear()
        fetch_snb_history.clear()
        fetch_oecd_history.clear()
        fetch_te_history.clear()
        fetch_investing_history.clear()
        st.session_state.last_refresh_ts = _now
        st.rerun()

    # ── Title row ──────────────────────────────────────────────────────────────
    col_back, col_title, col_ref = st.columns([2, 5, 2])
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
            f"12M Trend Analysis · Live Official Data · Auto-Refresh</div></div>",
            unsafe_allow_html=True,
        )
    with col_ref:
        if st.button("🔄 Refresh", key="manual_refresh", help="Clear all caches and reload data"):
            fetch_currency_history.clear()
            fetch_fred_history.clear()
            fetch_fred_indicators.clear()
            fetch_ecb_history.clear()
            fetch_ecb_rate.clear()
            fetch_ecb_cpi.clear()
            fetch_boe_rate.clear()
            fetch_boe_history.clear()
            fetch_rba_history.clear()
            fetch_boc_history.clear()
            fetch_snb_history.clear()
            fetch_oecd_history.clear()
            fetch_te_indicators.clear()
            fetch_te_history.clear()
            fetch_ff_macro_data.clear()
            fetch_international_indicators.clear()
            fetch_investing_history.clear()
            st.session_state.last_refresh_ts = time.time()
            st.rerun()

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

    # ── 1. Fetch 12-month history ─────────────────────────────────────────────
    with st.spinner("⏳ Loading 12-month data…"):
        history_dated = fetch_currency_history(currency, FRED_API_KEY)
    # Strip dates for scoring (plain value lists); keep dated for the chart
    history = _strip_dates(history_dated)

    # ── 2. Normalized bias — all 8 currencies in one pass ────────────────────
    # Live history for the selected currency; HISTORY_FALLBACK for the other 7.
    # Scores are z-normalized relative to each other so rankings are meaningful.
    _all_hist: dict[str, dict] = {
        _ccy: (history if _ccy == currency else HISTORY_FALLBACK.get(_ccy, {}))
        for _ccy in SUPPORTED_CURRENCIES
    }
    _all_biases = calc_all_biases(_all_hist)
    bias_result = _all_biases[currency]

    # ── 3. Store all 8 normalized scores in session state ────────────────────
    for _ccy, _b in _all_biases.items():
        st.session_state[f"macro_scores_{_ccy}"] = {
            "total":    _b["score"],
            "level":    _b["label"],
            "currency": _ccy,
            "fmt":      "indicator_12m",
        }

    # ── 5. Bias gauge panel ───────────────────────────────────────────────────
    st.markdown(render_bias_panel(currency, bias_result), unsafe_allow_html=True)
    st.markdown("<div style='height:4px;'></div>", unsafe_allow_html=True)

    # ── 6. Status bar ─────────────────────────────────────────────────────────
    age_secs = int(_now - st.session_state.last_refresh_ts)
    age_str  = f"{age_secs // 60}m {age_secs % 60}s ago" if age_secs >= 60 else f"{age_secs}s ago"
    _live_inds = len([i for i in history if i in _IND_DIRECTION])
    _fallback_inds = len([i for i in HISTORY_FALLBACK.get(currency, {}) if i in _IND_DIRECTION])
    _src_note = "Live API" if _live_inds >= _fallback_inds * 0.5 else "Fallback"
    st.markdown(
        f"<div style='font-size:11px;color:{C['muted']};font-family:monospace;"
        f"margin-bottom:12px;padding-top:2px;'>"
        f"{CURRENCY_FLAG.get(currency,'')} {currency} &nbsp;·&nbsp; "
        f"Source: {_src_note} &nbsp;·&nbsp; Last updated: {age_str} &nbsp;·&nbsp; "
        f"{bias_result['n_indicators']} indicators scored</div>",
        unsafe_allow_html=True,
    )

    # ── 7. Two economic charts ────────────────────────────────────────────────
    render_economic_charts(currency, bias_result, history_dated)

    st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)

    # ── 8. All Currencies Ranking (left) + Raw Indicator Data (right) ───────────
    col_rank, col_raw = st.columns([2, 3], gap="medium")

    with col_rank:
        st.markdown(_section_header("All Currencies — Bias Ranking"), unsafe_allow_html=True)
        st.markdown(render_all_currencies_overview(currency), unsafe_allow_html=True)

    with col_raw:
        st.markdown(_section_header(f"Raw Indicator Data — {currency}"), unsafe_allow_html=True)
        # Fetch current snapshot
        # Priority (lowest → highest, each layer can override the previous):
        #   1. ForexFactory calendar  — PMI/GDP/Retail/Wage via 'previous' field (base)
        #   2. Trading Economics      — PMI, GDP, Retail, Wage, Unemployment (more complete)
        #   3. FRED OECD/ILO + ONS   — Unemployment (GBP/JPY/CAD/AUD/NZD), CPI YoY (GBP ONS)
        #   4. Central bank APIs     — Rate + CPI (ECB, BOE, RBA, BOC, SNB) — highest precision
        official: dict = {}
        with st.spinner("⏳ Fetching current data…"):
            if currency == "USD":
                official = fetch_fred_indicators(FRED_API_KEY)
            else:
                # ── Layer 1: ForexFactory — quick base for upcoming-event previous values ──
                ff_data = fetch_ff_macro_data(currency)
                official.update(ff_data)

                # ── Layer 1b: Investing.com snapshot (current value from most recent release) ──
                inv_hist = fetch_investing_history(currency)  # returns dated pairs
                for _ind_name, _pairs in inv_hist.items():
                    if _pairs and _ind_name not in official:
                        official[_ind_name] = {
                            "actual":   _pairs[-1][1],                              # extract float
                            "previous": _pairs[-2][1] if len(_pairs) >= 2 else None,
                            "date":     None,
                            "source":   "Investing.com",
                        }

                # ── Layer 2: Trading Economics — PMI, GDP, Retail, Wage, Unemployment ──
                te_data = fetch_te_indicators(currency)
                official.update(te_data)   # TE overrides FF where available

                # ── Layer 3: FRED OECD/ILO + ONS — more authoritative unemployment/CPI ──
                intl_data = fetch_international_indicators(currency, FRED_API_KEY)
                official.update(intl_data)

                # ── Layer 3: Central bank APIs — highest precision, always win ──
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
                elif currency == "AUD":
                    _rba = fetch_rba_history()
                    for _ind in ("Interest Rate", "Unemployment Rate"):
                        if _ind in _rba and _rba[_ind]:
                            official[_ind] = {
                                "actual":   _rba[_ind][-1],
                                "previous": _rba[_ind][-2] if len(_rba[_ind]) >= 2 else None,
                                "source":   "RBA",
                            }
                elif currency == "CAD":
                    _boc = fetch_boc_history()
                    for _ind in ("Interest Rate", "CPI m/m"):
                        if _ind in _boc and _boc[_ind]:
                            official[_ind] = {
                                "actual":   _boc[_ind][-1],
                                "previous": _boc[_ind][-2] if len(_boc[_ind]) >= 2 else None,
                                "source":   "BOC",
                            }
                elif currency == "CHF":
                    _snb = fetch_snb_history()
                    for _ind in ("Interest Rate", "CPI YoY"):
                        if _ind in _snb and _snb[_ind]:
                            official[_ind] = {
                                "actual":   _snb[_ind][-1],
                                "previous": _snb[_ind][-2] if len(_snb[_ind]) >= 2 else None,
                                "source":   "SNB",
                            }
        indicators_df, ind_source = build_indicators_table(currency, official)
        _cg = C["green"]; _cy = C["yellow"]; _cm2 = C["muted"]
        st.markdown(
            f"<div style='font-size:10px;color:{C['muted']};font-family:monospace;"
            f"margin-bottom:8px;'>"
            f"<span style='color:{_cg};'>●</span> Live/fresh "
            f"&nbsp; <span style='color:{_cy};'>●</span> Stale "
            f"&nbsp; <span style='color:{_cm2};'>◎</span> Static "
            f"&nbsp;·&nbsp; Source: {ind_source}</div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            render_indicators_table(indicators_df, st.session_state.last_refresh_ts, currency),
            unsafe_allow_html=True,
        )

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
