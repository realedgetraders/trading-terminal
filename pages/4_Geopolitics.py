"""
Trading Analytics Terminal — Module 4: Geopolitical Intelligence
Geo events + financial news per currency
Sources (geo): Google News · Reuters · BBC · Al Jazeera
Sources (financial): FXStreet · ForexLive · CNBC · Bloomberg · MarketWatch · Investing
"""

import time
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import pandas as pd
import requests
import streamlit as st

try:
    import feedparser
    _FEEDPARSER = True
except ImportError:
    _FEEDPARSER = False


# ╔══════════════════════════════════════════════════════════════════════════════
# ║  CONSTANTS
# ╚══════════════════════════════════════════════════════════════════════════════

C = {
    "bg":       "#0d0d0d",
    "card":     "#141414",
    "border":   "#252525",
    "panel":    "#111111",
    "dim":      "#171717",
    "text":     "#e8e8e8",
    "muted":    "#666666",
    "teal":     "#e63946",
    "green":    "#00c48c",
    "red":      "#f05262",
    "yellow":   "#f0b429",
    "orange":   "#f08c29",
    "blue":     "#4f8ef7",
    "purple":   "#a78bfa",
}

CURRENCIES    = ["USD", "EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "NZD"]
CURRENCY_FLAG = {
    "USD": "🇺🇸", "EUR": "🇪🇺", "GBP": "🇬🇧", "JPY": "🇯🇵",
    "AUD": "🇦🇺", "CAD": "🇨🇦", "CHF": "🇨🇭", "NZD": "🇳🇿",
}
CURRENCY_NAME = {
    "USD": "US Dollar",        "EUR": "Euro",
    "GBP": "British Pound",    "JPY": "Japanese Yen",
    "AUD": "Australian Dollar","CAD": "Canadian Dollar",
    "CHF": "Swiss Franc",      "NZD": "New Zealand Dollar",
}

# ── Currency geo profile ──────────────────────────────────────────────────────
_CCY_PROFILE: dict[str, dict] = {
    "USD": {
        "role":       "World Reserve Currency",
        "sensitivity":"SAFE HAVEN",
        "sens_col":   "#e63946",
        "context": [
            "Global crises universally drive safe-haven demand for USD.",
            "US-imposed trade tariffs and sanctions reshape cross-border dollar flows.",
            "Middle East conflicts affect USD via oil price and petrodollar dynamics.",
            "Rising US military commitments increase geopolitical risk premium.",
        ],
        "key_risks": ["US-China Trade War", "Middle East", "Russia Sanctions", "Taiwan Strait"],
    },
    "EUR": {
        "role":       "European Single Currency",
        "sensitivity":"GEO-EXPOSED",
        "sens_col":   "#f0b429",
        "context": [
            "Russia-Ukraine war is the dominant geo risk; energy disruptions weigh on EUR.",
            "European political fragmentation (elections, populism) pressures the bloc.",
            "NATO commitments and US-EU trade frictions create ongoing headline risk.",
        ],
        "key_risks": ["Ukraine War", "Russia-EU Energy", "EU Instability", "NATO"],
    },
    "GBP": {
        "role":       "British Pound",
        "sensitivity":"MODERATE EXPOSURE",
        "sens_col":   "#4f8ef7",
        "context": [
            "UK NATO commitments and foreign policy decisions create regular headline risk.",
            "Post-Brexit trade disputes with the EU remain a structural vulnerability.",
            "Political instability in Westminster amplifies external shocks.",
        ],
        "key_risks": ["UK-EU Trade", "NATO", "Political Instability", "Scotland"],
    },
    "JPY": {
        "role":       "Japanese Yen",
        "sensitivity":"SAFE HAVEN + CARRY",
        "sens_col":   "#e63946",
        "context": [
            "North Korean missile tests and China-Taiwan tensions unwind JPY carry trades.",
            "Japan's US security dependency creates asymmetric geopolitical risk.",
            "Asia-Pacific escalation drives JPY safe-haven demand.",
        ],
        "key_risks": ["North Korea", "Taiwan Strait", "China-Japan", "US-Japan Alliance"],
    },
    "AUD": {
        "role":       "Australian Dollar",
        "sensitivity":"RISK CORRELATED",
        "sens_col":   "#f05262",
        "context": [
            "China-Australia tensions directly impact exports (iron ore, coal, LNG).",
            "South China Sea escalation raises risk premium — AUD is a regional proxy.",
            "AUKUS pact ties AUD sentiment to US-Pacific strategic posture.",
        ],
        "key_risks": ["China-Australia Trade", "South China Sea", "Indo-Pacific", "AUKUS"],
    },
    "CAD": {
        "role":       "Canadian Dollar",
        "sensitivity":"OIL / TRADE LINKED",
        "sens_col":   "#f08c29",
        "context": [
            "Middle East conflicts and OPEC supply shocks move CAD via oil price linkage.",
            "Canada-US trade disputes (tariffs, USMCA) directly affect the Loonie.",
            "Energy infrastructure security (pipelines, LNG exports) is a CAD-specific risk.",
        ],
        "key_risks": ["OPEC / Middle East", "US-Canada Trade", "Oil Supply Shocks"],
    },
    "CHF": {
        "role":       "Swiss Franc",
        "sensitivity":"STRONGEST SAFE HAVEN",
        "sens_col":   "#00c48c",
        "context": [
            "Swiss neutrality makes CHF the premier safe-haven — any crisis drives inflows.",
            "European wars and global financial crises generate the sharpest CHF bids.",
            "Nuclear or extreme geopolitical scenarios create the strongest CHF demand.",
        ],
        "key_risks": ["European War Risk", "Global Crisis", "Nuclear Threats"],
    },
    "NZD": {
        "role":       "New Zealand Dollar",
        "sensitivity":"MOST RISK-SENSITIVE",
        "sens_col":   "#f05262",
        "context": [
            "NZD is the most risk-sensitive G10 currency — global escalation hits NZD first.",
            "Pacific Island geopolitics and China's regional influence affect NZD via trade.",
            "Five Eyes commitments align NZD risk with Western geopolitical stance.",
        ],
        "key_risks": ["Pacific Geopolitics", "China Relations", "Five Eyes Alliance"],
    },
}

# ── Per-currency geo news queries (Google News RSS) ───────────────────────────
# Strictly geo/political — no monetary policy, no rate/inflation content
_CCY_GEO_QUERIES: dict[str, list[str]] = {
    "USD": [
        "United States military sanctions trade war foreign policy conflict when:3d",
        "America Pentagon NATO troops war diplomatic crisis when:3d",
    ],
    "EUR": [
        "Ukraine Russia war Europe NATO energy sanctions conflict when:3d",
        "European political crisis elections populism instability war when:3d",
    ],
    "GBP": [
        "UK Britain military NATO sanctions conflict foreign policy when:3d",
        "Britain Russia Ukraine war Europe trade tensions when:3d",
    ],
    "JPY": [
        "Japan North Korea missile China Taiwan military Asia-Pacific when:3d",
        "Japan security US alliance Taiwan Strait conflict geopolitical when:3d",
    ],
    "AUD": [
        "Australia China tensions AUKUS Pacific military conflict when:3d",
        "South China Sea territorial dispute Indo-Pacific military when:3d",
    ],
    "CAD": [
        "OPEC oil supply disruption Middle East war energy crisis when:3d",
        "Canada United States trade war tariffs sanctions dispute when:3d",
    ],
    "CHF": [
        "Europe war conflict crisis instability geopolitical safe-haven when:3d",
        "Middle East war Iran nuclear conflict global crisis when:3d",
    ],
    "NZD": [
        "New Zealand Pacific China military AUKUS geopolitical conflict when:3d",
        "Pacific Islands geopolitics China Solomon Islands PNG military when:3d",
    ],
}

# Verified direct RSS feeds — major international news organisations
_DIRECT_FEEDS: list[tuple[str, str]] = [
    ("Reuters",    "https://feeds.reuters.com/reuters/worldNews"),
    ("BBC World",  "https://feeds.bbci.co.uk/news/world/rss.xml"),
    ("Al Jazeera", "https://www.aljazeera.com/xml/rss/all.xml"),
]

# ── Category detection ────────────────────────────────────────────────────────
_CATEGORIES: dict[str, dict] = {
    "Conflict":  {"color": "#f05262", "kw": [
        "war", "military", "airstrike", "bomb", "attack", "troops", "invasion",
        "battle", "missile", "drone strike", "killed", "combat", "offensive",
        "artillery", "navy", "weapons", "armed forces", "siege", "frontline",
    ]},
    "Sanctions": {"color": "#f0b429", "kw": [
        "sanctions", "embargo", "blockade", "asset freeze", "banned",
        "expelled", "travel ban", "export control", "trade ban",
    ]},
    "Political": {"color": "#4f8ef7", "kw": [
        "coup", "election", "protest", "government collapse", "resign",
        "instability", "opposition", "parliament dissolved", "crisis",
        "overthrow", "dictator", "authoritarian", "civil unrest", "martial law",
    ]},
    "Diplomatic":{"color": "#00c48c", "kw": [
        "ceasefire", "peace deal", "summit", "treaty", "agreement",
        "negotiations", "envoy", "ambassador", "diplomatic talks", "accord",
    ]},
    "Trade War":  {"color": "#f08c29", "kw": [
        "tariffs", "trade war", "trade deal", "import duty", "export ban",
        "trade restrictions", "trade dispute", "wto", "protectionism",
    ]},
    "Energy":    {"color": "#a78bfa", "kw": [
        "oil", "gas pipeline", "energy supply", "opec", "crude", "petroleum",
        "lng", "nuclear plant", "energy crisis", "oil embargo",
    ]},
}

# Articles containing these keywords are economic noise — skip them
_ECON_SKIP_KW: list[str] = [
    "interest rate", "rate decision", "rate cut", "rate hike", "monetary policy",
    "inflation data", "cpi report", "gdp growth", "gdp data", "gdp figures",
    "employment report", "nonfarm payroll", "jobs report", "retail sales data",
    "pmi report", "balance sheet", "quantitative easing", "bond yield",
    "treasury yield", "earnings report", "quarterly earnings", "ipo",
    "stock split", "dividend", "market rally", "market crash",
]

# Keywords to confirm an article is relevant to a specific currency
_CCY_RELEVANCE: dict[str, list[str]] = {
    "USD": ["united states", "us military", "america", "pentagon", "washington dc",
            "us sanctions", "us tariffs", "nato", "american troops"],
    "EUR": ["europe", "ukraine", "russia", "nato", "european union", "brussels",
            "germany", "france", "poland", "eu sanctions"],
    "GBP": ["britain", " uk ", "england", "british", "london", "scotland",
            "northern ireland", "westminster"],
    "JPY": ["japan", "japanese", "north korea", "tokyo", "taiwan",
            "asia pacific", "east asia", "china sea"],
    "AUD": ["australia", "australian", "aukus", "indo-pacific",
            "south china sea", "canberra"],
    "CAD": ["canada", "canadian", "ottawa", "opec", "oil supply",
            "alberta", "us-canada"],
    "CHF": ["switzerland", "swiss", "safe haven", "geneva",
            "zurich", "neutral country"],
    "NZD": ["new zealand", "wellington", "pacific island",
            "five eyes", "nz "],
}

# ── Per-currency × category impact interpretations ───────────────────────────
_CCY_CAT_INTERP: dict[str, dict[str, str]] = {
    "USD": {
        "Conflict":   "Military escalation typically strengthens USD as global safe-haven demand surges.",
        "Sanctions":  "US-led sanctions reinforce dollar dominance — secondary sanctions tighten global USD dependency.",
        "Political":  "US political instability can briefly pressure USD, but reserve currency status limits downside.",
        "Diplomatic": "Peace progress reduces risk premiums; USD may soften as safe-haven flows unwind.",
        "Trade War":  "US tariffs support short-term dollar strength but risk eroding long-term reserve currency credibility.",
        "Energy":     "Oil price spikes via petrodollar dynamics sustain USD demand from energy exporters.",
    },
    "EUR": {
        "Conflict":   "European war risk drives EUR lower as energy costs surge and capital flees the continent.",
        "Sanctions":  "EU-Russia sanctions hit European energy supply, raising inflation and weighing on EUR.",
        "Political":  "EU political fragmentation undermines bloc cohesion and directly pressures EUR credibility.",
        "Diplomatic": "De-escalation in Europe removes war risk premium — EUR typically rallies on ceasefire news.",
        "Trade War":  "US-EU trade disputes add uncertainty to eurozone export outlook, bearish for EUR.",
        "Energy":     "European energy disruptions are directly bearish for EUR via inflation and growth headwinds.",
    },
    "GBP": {
        "Conflict":   "UK military involvement raises fiscal risk and may weigh on GBP through defence spending concerns.",
        "Sanctions":  "UK-aligned sanctions signal foreign policy commitment but add trade friction for GBP.",
        "Political":  "Westminster instability historically drives sharp GBP selloffs — political risk is priced fast.",
        "Diplomatic": "UK diplomatic progress reduces safe-haven outflows and supports GBP stability.",
        "Trade War":  "UK-EU trade friction post-Brexit is a structural drag — new disputes amplify GBP weakness.",
        "Energy":     "UK energy security concerns raise inflation expectations and complicate BoE policy outlook.",
    },
    "JPY": {
        "Conflict":   "Asia-Pacific conflict triggers JPY safe-haven inflows as yen carry trades rapidly unwind.",
        "Sanctions":  "Sanctions on regional actors escalate JPY demand as risk-off positioning intensifies.",
        "Political":  "Asian political instability accelerates carry trade unwinding, sharply strengthening JPY.",
        "Diplomatic": "Regional tension reduction softens safe-haven demand — carry trades may gradually resume.",
        "Trade War":  "US-Japan trade tensions can weaken JPY via export growth concerns and policy uncertainty.",
        "Energy":     "Japan imports ~90% of its energy — sustained oil price spikes are structurally negative for JPY.",
    },
    "AUD": {
        "Conflict":   "Global conflict reduces risk appetite, hitting AUD as commodity demand outlook weakens.",
        "Sanctions":  "China-targeted sanctions disrupt iron ore and coal trade, directly bearish for AUD.",
        "Political":  "Indo-Pacific political tensions elevate risk premium on AUD as a regional risk proxy.",
        "Diplomatic": "China-Australia diplomatic normalisation removes trade barriers and is strongly AUD-positive.",
        "Trade War":  "China-Australia trade restrictions on key exports (iron ore, LNG) are highly bearish for AUD.",
        "Energy":     "LNG export disruptions have mixed impact — supply cuts can support AUD terms-of-trade.",
    },
    "CAD": {
        "Conflict":   "Middle East conflict typically lifts oil prices — directly positive for CAD as a petrocurrency.",
        "Sanctions":  "OPEC sanctions or supply disruptions raise oil prices, providing direct upside for CAD.",
        "Political":  "Canadian political uncertainty weighs on investment and creates short-term CAD pressure.",
        "Diplomatic": "OPEC output agreements and diplomatic resolutions directly move oil price and thus CAD.",
        "Trade War":  "US-Canada trade disputes threaten bilateral trade flows and are directly bearish for the Loonie.",
        "Energy":     "Oil supply shocks are the primary CAD driver — higher energy prices strongly support CAD.",
    },
    "CHF": {
        "Conflict":   "Any global escalation drives the strongest safe-haven flows into CHF — Swiss neutrality premium peaks.",
        "Sanctions":  "Financial sanctions and capital flight from conflict zones boost Swiss banking inflows into CHF.",
        "Political":  "Global political crises reinforce Swiss neutrality premium and drive CHF appreciation.",
        "Diplomatic": "Peace deals reduce the urgency of safe-haven positioning — CHF tends to soften on risk-on.",
        "Trade War":  "CHF benefits indirectly from trade war uncertainty as investors seek neutral safe assets.",
        "Energy":     "European energy crises drive safe-haven demand for CHF from regional capital outflows.",
    },
    "NZD": {
        "Conflict":   "Global conflict risk-off is highly bearish for NZD — it's the most risk-sensitive G10 currency.",
        "Sanctions":  "Sanctions targeting regional trade partners raise supply chain risk and weigh on NZD.",
        "Political":  "Pacific political instability raises uncertainty around Five Eyes alliances and pressures NZD.",
        "Diplomatic": "Regional diplomatic progress reduces risk premium and supports NZD on improved sentiment.",
        "Trade War":  "China-NZ trade friction threatens dairy and agricultural exports — directly bearish for NZD.",
        "Energy":     "Global energy disruptions reduce growth expectations and compound NZD's risk-sensitive weakness.",
    },
}

TTL_CCY    = 300   # 5-min — per-currency Google News cache
TTL_GLOBAL = 600   # 10-min — direct RSS feed cache
TTL_FIN    = 300   # 5-min — financial RSS feed cache
TTL_CAL    = 1800  # 30-min — ForexFactory calendar cache TTL

# ── ForexFactory calendar constants (used by calendar tab) ───────────────────
COUNTRY_TO_CURRENCY_M4: dict[str, str] = {
    "United States":  "USD", "US":             "USD",
    "Euro Zone":      "EUR", "Eurozone":        "EUR", "European Union": "EUR",
    "United Kingdom": "GBP", "UK":              "GBP",
    "Japan":          "JPY",
    "Australia":      "AUD",
    "Canada":         "CAD",
    "Switzerland":    "CHF",
    "New Zealand":    "NZD",
}
_SUPPORTED_CCY_M4 = ["USD", "EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "NZD"]

_CALENDAR_CCY_KEYWORDS_M4: dict[str, list[str]] = {
    # Note: "us" and "uk" removed — 2-letter substrings cause false positives
    # ("Australian" contains "us", "bulk"/"truck" contain "uk", etc.)
    # Direct 3-letter code lookup in _resolve_calendar_ccy_m4 handles FF feeds.
    "USD": ["usd", "united states", "federal reserve", "fed", "fomc", "powell"],
    "EUR": ["eur", "euro", "european", "ecb", "eurozone", "euro zone", "lagarde"],
    "GBP": ["gbp", "british", "united kingdom", "boe", "bank of england", "bailey"],
    "JPY": ["jpy", "japanese", "japan", "boj", "bank of japan", "ueda"],
    "AUD": ["aud", "australian", "australia", "rba", "reserve bank of australia"],
    "CAD": ["cad", "canadian", "canada", "boc", "bank of canada", "macklem"],
    "CHF": ["chf", "swiss", "switzerland", "snb", "swiss national bank"],
    "NZD": ["nzd", "new zealand", "rbnz", "reserve bank of new zealand"],
}

_RAW_IND_MAP_M4: dict[str, str] = {
    "consumer price index": "CPI y/y", "consumer confidence": "Consumer Confidence",
    "average hourly earnings": "Wage Growth", "markit manufacturing": "Manufacturing PMI",
    "manufacturing pmi": "Manufacturing PMI", "ism manufacturing": "Manufacturing PMI",
    "services pmi": "Services PMI", "ism non-mfg": "Services PMI",
    "ism services": "Services PMI", "building permits": "Building Permits",
    "producer price": "PPI", "government debt": "Government Debt",
    "gross domestic": "GDP Growth", "current account": "Current Account",
    "trade balance": "Trade Balance", "budget balance": "Budget Balance",
    "retail sales": "Retail Sales", "interest rate": "Interest Rate",
    "cash rate": "Interest Rate", "overnight rate": "Interest Rate",
    "policy rate": "Interest Rate", "fed funds": "Interest Rate",
    "base rate": "Interest Rate", "unemployment": "Unemployment Rate",
    "claimant count": "Unemployment Rate", "jobless": "Unemployment Rate",
    "wage growth": "Wage Growth", "labor cost": "Wage Growth",
    "labour cost": "Wage Growth", "gdp": "GDP Growth", "cpi": "CPI y/y",
    "ppi": "PPI",
}
_INDICATOR_MAP_M4: list[tuple[str, str]] = sorted(
    _RAW_IND_MAP_M4.items(), key=lambda x: len(x[0]), reverse=True
)

# Events to always skip regardless of impact (bond auctions, technical revisions)
_CAL_NOISE_KW_M4: tuple[str, ...] = (
    "bond auction", "treasury auction", "bill auction", "note auction",
    "gbond auction", "btp auction", "jgb auction", "linker auction",
    "t-bill", "t-note auction", "t-bond auction",
)

_FF_HDR_JSON_M4 = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept":          "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer":         "https://www.forexfactory.com/",
    "Origin":          "https://www.forexfactory.com",
}
_FF_HDR_XML_M4 = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept":          "application/xml, text/xml, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer":         "https://www.forexfactory.com/",
}
_FF_ENDPOINTS_M4 = [
    ("json", "https://nfs.faireconomy.media/ff_calendar_thisweek.json"),
    ("json", "https://nfs.faireconomy.media/ff_calendar_nextweek.json"),
    ("json", "https://nfs.faireconomy.media/ff_calendar_month.json"),
    ("xml",  "https://cdn-nfs.faireconomy.media/ff_calendar_thisweek.xml"),
    ("xml",  "https://cdn-nfs.faireconomy.media/ff_calendar_nextweek.xml"),
]

_STATIC_CALENDAR_M4: list[dict] = [
    {"currency":"USD","indicator":"GDP Growth",        "title":"GDP Growth Rate QoQ Prelim","date":"2026-05-28","impact":"High",  "forecast": 2.7,  "previous": 2.8 },
    {"currency":"USD","indicator":"Manufacturing PMI", "title":"ISM Manufacturing PMI",     "date":"2026-06-01","impact":"Medium","forecast":50.0,  "previous":49.8 },
    {"currency":"USD","indicator":"Services PMI",      "title":"ISM Services PMI",          "date":"2026-06-03","impact":"Medium","forecast":51.5,  "previous":51.2 },
    {"currency":"USD","indicator":"Unemployment Rate", "title":"Unemployment Rate",         "date":"2026-06-05","impact":"High",  "forecast": 4.0,  "previous": 4.0 },
    {"currency":"USD","indicator":"CPI y/y",           "title":"CPI y/y",                   "date":"2026-06-10","impact":"High",  "forecast": 3.3,  "previous": 3.4 },
    {"currency":"USD","indicator":"Interest Rate",     "title":"Fed Funds Rate",            "date":"2026-06-18","impact":"High",  "forecast": 4.50, "previous": 4.50},
    {"currency":"USD","indicator":"GDP Growth",        "title":"GDP Growth Rate QoQ Final", "date":"2026-06-25","impact":"High",  "forecast": 2.8,  "previous": 2.8 },
    {"currency":"USD","indicator":"Unemployment Rate", "title":"Unemployment Rate",         "date":"2026-07-02","impact":"High",  "forecast": 3.9,  "previous": 4.0 },
    {"currency":"USD","indicator":"CPI y/y",           "title":"CPI y/y",                   "date":"2026-07-14","impact":"High",  "forecast": 3.2,  "previous": 3.3 },
    {"currency":"USD","indicator":"Interest Rate",     "title":"Fed Funds Rate",            "date":"2026-07-29","impact":"High",  "forecast": 4.25, "previous": 4.50},
    {"currency":"EUR","indicator":"CPI y/y",           "title":"CPI Flash y/y",             "date":"2026-06-04","impact":"High",  "forecast": 1.8,  "previous": 1.9 },
    {"currency":"EUR","indicator":"Interest Rate",     "title":"ECB Rate Decision",         "date":"2026-06-05","impact":"High",  "forecast": 2.00, "previous": 2.25},
    {"currency":"EUR","indicator":"GDP Growth",        "title":"GDP Growth Rate QoQ",       "date":"2026-06-30","impact":"High",  "forecast": 0.9,  "previous": 0.8 },
    {"currency":"EUR","indicator":"Interest Rate",     "title":"ECB Rate Decision",         "date":"2026-07-24","impact":"High",  "forecast": 2.00, "previous": 2.00},
    {"currency":"GBP","indicator":"CPI y/y",           "title":"CPI y/y",                   "date":"2026-06-17","impact":"High",  "forecast": 3.0,  "previous": 3.2 },
    {"currency":"GBP","indicator":"Interest Rate",     "title":"BOE Rate Decision",         "date":"2026-06-18","impact":"High",  "forecast": 4.00, "previous": 4.25},
    {"currency":"GBP","indicator":"Interest Rate",     "title":"BOE Rate Decision",         "date":"2026-08-06","impact":"High",  "forecast": 3.75, "previous": 4.00},
    {"currency":"JPY","indicator":"Interest Rate",     "title":"BOJ Rate Decision",         "date":"2026-06-17","impact":"High",  "forecast": 0.50, "previous": 0.50},
    {"currency":"JPY","indicator":"CPI y/y",           "title":"National CPI y/y",          "date":"2026-06-19","impact":"High",  "forecast": 2.6,  "previous": 2.8 },
    {"currency":"JPY","indicator":"Interest Rate",     "title":"BOJ Rate Decision",         "date":"2026-07-30","impact":"High",  "forecast": 0.75, "previous": 0.50},
    {"currency":"AUD","indicator":"Interest Rate",     "title":"RBA Rate Decision",         "date":"2026-06-02","impact":"High",  "forecast": 3.60, "previous": 3.85},
    {"currency":"AUD","indicator":"Unemployment Rate", "title":"Unemployment Rate",         "date":"2026-06-18","impact":"High",  "forecast": 4.2,  "previous": 4.2 },
    {"currency":"AUD","indicator":"CPI y/y",           "title":"CPI y/y",                   "date":"2026-07-29","impact":"High",  "forecast": 2.9,  "previous": 3.2 },
    {"currency":"CAD","indicator":"Interest Rate",     "title":"BOC Rate Decision",         "date":"2026-06-04","impact":"High",  "forecast": 2.50, "previous": 2.75},
    {"currency":"CAD","indicator":"Unemployment Rate", "title":"Unemployment Rate",         "date":"2026-06-05","impact":"High",  "forecast": 7.0,  "previous": 6.9 },
    {"currency":"CAD","indicator":"CPI y/y",           "title":"CPI y/y",                   "date":"2026-06-16","impact":"High",  "forecast": 2.6,  "previous": 2.7 },
    {"currency":"CHF","indicator":"Interest Rate",     "title":"SNB Rate Decision",         "date":"2026-06-18","impact":"High",  "forecast": 0.00, "previous": 0.00},
    {"currency":"CHF","indicator":"CPI y/y",           "title":"CPI y/y",                   "date":"2026-07-02","impact":"Medium","forecast": 0.5,  "previous": 0.4 },
    {"currency":"NZD","indicator":"Interest Rate",     "title":"RBNZ Rate Decision",        "date":"2026-05-27","impact":"High",  "forecast": 3.25, "previous": 3.50},
    {"currency":"NZD","indicator":"GDP Growth",        "title":"GDP Growth Rate QoQ",       "date":"2026-06-18","impact":"High",  "forecast": 0.8,  "previous": 0.7 },
    {"currency":"NZD","indicator":"Interest Rate",     "title":"RBNZ Rate Decision",        "date":"2026-07-08","impact":"High",  "forecast": 3.00, "previous": 3.25},
]

# ── Financial news RSS feeds (moved from Module 3) ────────────────────────────
_FIN_FEEDS: list[tuple[str, str]] = [
    ("FXStreet",    "https://www.fxstreet.com/rss/news"),
    ("ForexLive",   "https://www.forexlive.com/feed/news"),
    ("CNBC",        "https://search.cnbc.com/rs/search/combinedcms/view.xml"
                    "?partnerId=wrss01&id=100003114"),
    ("Bloomberg",   "https://feeds.bloomberg.com/markets/news.rss"),
    ("MarketWatch", "https://feeds.content.dowjones.io/public/rss/mw_realtimeheadlines"),
    ("Investing",   "https://www.investing.com/rss/news.rss"),
]
_FIN_SOURCE_NAMES: list[str] = ["All"] + [s for s, _ in _FIN_FEEDS]

_FIN_HEADERS: dict[str, str] = {
    "User-Agent":      "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/124.0.0.0 Safari/537.36",
    "Accept":          "application/rss+xml, application/xml, text/xml, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer":         "https://www.google.com/",
}

# Currency keyword filter for financial news (same as Module 3)
_CCY_FIN_KW: dict[str, list[str]] = {
    "USD": ["dollar", "fed", "federal reserve", "usd", "powell", "fomc"],
    "EUR": ["euro", "ecb", "eur", "lagarde", "eurozone", "european central bank"],
    "GBP": ["pound", "boe", "gbp", "sterling", "bank of england", "bailey"],
    "JPY": ["yen", "boj", "jpy", "japan", "ueda", "bank of japan"],
    "AUD": ["aussie", "rba", "aud", "australia", "reserve bank of australia"],
    "CAD": ["loonie", "boc", "cad", "canada", "bank of canada", "macklem"],
    "CHF": ["franc", "snb", "chf", "switzerland", "swiss national bank"],
    "NZD": ["kiwi", "rbnz", "nzd", "new zealand", "reserve bank of new zealand"],
}


# ╔══════════════════════════════════════════════════════════════════════════════
# ║  CALENDAR HELPERS
# ╚══════════════════════════════════════════════════════════════════════════════

def _parse_numeric_m4(val) -> float | None:
    if not val or not str(val).strip():
        return None
    s = str(val).strip().replace(",", "").replace("$", "").replace(" ", "")
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
    except ValueError:
        return None


def _normalize_indicator_m4(title: str) -> str | None:
    t = title.lower()
    for key, canonical in _INDICATOR_MAP_M4:
        if key in t:
            return canonical
    return None


def _resolve_calendar_ccy_m4(country: str, title: str) -> str | None:
    """Map a raw FF country string + title to one of the 8 supported CCY codes.

    FF JSON sends lowercase 3-letter codes (e.g. "usd", "eur").  The original
    dict/list lookups were case-sensitive and always failed, pushing every event
    into the keyword fallback where "us" matched "Australian", "business",
    "surplus", etc., mis-tagging AUD/GBP events as USD.

    Resolution order:
    1. COUNTRY_TO_CURRENCY_M4 — handles English names ("Euro Zone", "Japan" …)
    2. Direct uppercase match against _SUPPORTED_CCY_M4 — handles "usd"→"USD"
    3. Keyword fallback (only for unusual country strings) — "us"/"uk" removed
    """
    c = country.strip()
    # 1. English name lookup (original dict — unchanged)
    ccy = COUNTRY_TO_CURRENCY_M4.get(c) or COUNTRY_TO_CURRENCY_M4.get(c.title())
    if ccy:
        return ccy
    # 2. Case-normalised 3-letter code (handles lowercase FF codes like "usd")
    c_up = c.upper()
    if c_up in _SUPPORTED_CCY_M4:
        return c_up
    # 3. Keyword fallback — only reached for unusual or composite country strings
    haystack = (c + " " + title).lower()
    for ccy_code, keywords in _CALENDAR_CCY_KEYWORDS_M4.items():
        if any(kw in haystack for kw in keywords):
            return ccy_code
    return None


def _generate_static_calendar_m4() -> pd.DataFrame:
    rows = []
    for ev in _STATIC_CALENDAR_M4:
        rows.append({
            "currency":  ev["currency"],
            "indicator": ev["indicator"],
            "title":     ev["title"],
            "date":      pd.to_datetime(ev["date"]),
            "impact":    ev["impact"],
            "actual":    None,
            "forecast":  ev.get("forecast"),
            "previous":  ev.get("previous"),
        })
    return pd.DataFrame(rows)


@st.cache_data(ttl=TTL_CAL, show_spinner=False)
def fetch_ff_calendar_m4() -> pd.DataFrame:
    """Fetch ForexFactory calendar for Module 4 — JSON + XML CDN endpoints."""
    rows: list[dict] = []

    def _append_json(data: list) -> None:
        for ev in data:
            title       = str(ev.get("title") or ev.get("name") or "")
            country_raw = str(ev.get("country", ""))
            ccy         = _resolve_calendar_ccy_m4(country_raw, title)
            if not ccy: continue
            impact_raw  = str(ev.get("impact") or "Low").capitalize()
            if impact_raw == "Holiday": continue
            if any(kw in title.lower() for kw in _CAL_NOISE_KW_M4): continue
            ind = _normalize_indicator_m4(title) or title
            rows.append({
                "currency": ccy, "indicator": ind, "title": title,
                "date":     pd.to_datetime(ev.get("date"), errors="coerce"),
                "impact":   impact_raw,
                "actual":   _parse_numeric_m4(str(ev.get("actual")   or "")),
                "forecast": _parse_numeric_m4(str(ev.get("forecast") or "")),
                "previous": _parse_numeric_m4(str(ev.get("previous") or "")),
            })

    def _append_xml(content: bytes) -> None:
        try: root = ET.fromstring(content)
        except Exception: return
        for event in root.findall("event"):
            def _t(tag: str) -> str:
                el = event.find(tag)
                return (el.text or "").strip() if el is not None else ""
            title      = _t("title")
            impact_raw = _t("impact").capitalize() or "Low"
            if impact_raw == "Holiday": continue
            if any(kw in title.lower() for kw in _CAL_NOISE_KW_M4): continue
            ccy = _resolve_calendar_ccy_m4(_t("country"), title)
            if not ccy: continue
            ind = _normalize_indicator_m4(title) or title
            rows.append({
                "currency": ccy, "indicator": ind, "title": title,
                "date":     pd.to_datetime(_t("date"), errors="coerce"),
                "impact":   impact_raw,
                "actual":   _parse_numeric_m4(_t("actual")),
                "forecast": _parse_numeric_m4(_t("forecast")),
                "previous": _parse_numeric_m4(_t("previous")),
            })

    for fmt, url in _FF_ENDPOINTS_M4:
        hdr = _FF_HDR_JSON_M4 if fmt == "json" else _FF_HDR_XML_M4
        try:
            r = requests.get(url, timeout=10, headers=hdr)
            if r.status_code == 200:
                if fmt == "json":
                    data = r.json()
                    if isinstance(data, list) and data:
                        _append_json(data)
                else:
                    _append_xml(r.content)
        except Exception:
            pass
        time.sleep(0.08)

    if not rows:
        return pd.DataFrame(columns=[
            "currency", "indicator", "title", "date", "impact",
            "actual", "forecast", "previous",
        ])
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    if df["date"].dt.tz is not None:
        df["date"] = df["date"].dt.tz_localize(None)
    return df.drop_duplicates(subset=["currency", "title", "date"])


def build_calendar_view_m4(ff_df: pd.DataFrame, currency: str) -> pd.DataFrame:
    """Full current week + next 14 weeks — High/Medium/Low impact (noise filtered), sorted descending."""
    now       = pd.Timestamp.today().normalize()
    lookback  = now - pd.Timedelta(days=now.dayofweek)
    lookahead = now + pd.Timedelta(weeks=14)

    source = ff_df if not ff_df.empty else _generate_static_calendar_m4()

    src_dates = source["date"]
    if hasattr(src_dates, "dt") and src_dates.dt.tz is not None:
        source = source.copy()
        source["date"] = src_dates.dt.tz_localize(None)

    sub = source[
        (source["currency"] == currency) &
        (source["date"] >= lookback) &
        (source["date"] <= lookahead) &
        (source["impact"].isin(["High", "Medium", "Low"]))
    ].copy()
    if sub.empty:
        return pd.DataFrame()

    sub["date"]        = pd.to_datetime(sub["date"])
    sub                = sub.sort_values("date", ascending=False)
    sub["days_until"]  = (sub["date"] - now).dt.days
    sub["is_upcoming"] = sub["date"] > now
    return sub[[
        "date", "indicator", "title", "impact", "actual", "forecast", "previous",
        "days_until", "is_upcoming",
    ]].reset_index(drop=True)


def render_calendar_table_m4(calendar_df: pd.DataFrame) -> str:
    """Render the economic calendar as an HTML table."""
    if calendar_df.empty:
        return (
            f"<div style='padding:24px;text-align:center;color:{C['muted']};"
            f"font-family:monospace;font-size:12px;background:{C['card']};"
            f"border:1px solid {C['border']};border-radius:10px;'>"
            f"⚠ Calendar unavailable — ForexFactory unreachable, showing static data</div>"
        )

    def _fmt(val) -> str:
        try:
            if val is None:
                return f"<span style='color:{C['muted']};'>—</span>"
            f = float(val)
            if f != f:
                return f"<span style='color:{C['muted']};'>—</span>"
            s = f"{f:,.2f}".rstrip("0").rstrip(".")
            return s or "0"
        except Exception:
            return f"<span style='color:{C['muted']};'>—</span>"

    def _impact_pill(impact: str) -> str:
        if str(impact or "").strip().lower() == "low":
            return f"<span style='color:{C['muted']};font-size:10px;'>●</span>"
        cfg = {
            "High":   (C["red"],    "rgba(240,82,98,0.15)"),
            "Medium": (C["yellow"], "rgba(240,180,41,0.15)"),
        }
        color, bg = cfg.get(str(impact).capitalize(), (C["muted"], C["card"]))
        return (
            f"<span style='background:{bg};color:{color};font-size:9px;"
            f"font-family:monospace;font-weight:700;letter-spacing:1px;"
            f"padding:2px 7px;border-radius:4px;text-transform:uppercase;'>{impact}</span>"
        )

    cols = ["Time", "Date", "Event", "Actual", "Forecast", "Previous", "Impact"]
    hdr  = (
        f"<tr style='border-bottom:1px solid {C['border']};'>"
        + "".join(
            f"<th style='padding:7px 10px;font-size:10px;color:{C['muted']};"
            f"font-family:monospace;text-transform:uppercase;letter-spacing:1px;"
            f"font-weight:600;text-align:left;'>{h}</th>" for h in cols
        ) + "</tr>"
    )

    body = ""
    for _, row in calendar_df.iterrows():
        days        = int(row.get("days_until", 99))
        is_upcoming = bool(row.get("is_upcoming", True))
        soon        = 0 < days <= 7
        row_bg      = "rgba(69,196,176,0.06)" if soon else "transparent"
        date_color  = C["teal"] if soon else (C["muted"] if is_upcoming else C["text"])

        try:
            ts       = pd.Timestamp(row["date"])
            date_str = ts.strftime("%a %d %b")
            time_str = ts.strftime("%H:%M") if (ts.hour, ts.minute) != (0, 0) else "—"
        except Exception:
            date_str = "—"
            time_str = "—"
        ind_name = str(row.get("title") or row.get("indicator") or "—")

        body += (
            f"<tr style='border-bottom:1px solid {C['border']};background:{row_bg};'>"
            f"<td style='padding:7px 10px;font-size:11px;color:{C['muted']};"
            f"font-family:monospace;white-space:nowrap;'>{time_str}</td>"
            f"<td style='padding:7px 10px;font-size:11px;color:{date_color};"
            f"font-family:monospace;white-space:nowrap;'>{date_str}</td>"
            f"<td style='padding:7px 10px;font-size:11px;color:{C['text']};"
            f"font-family:monospace;'>{ind_name}</td>"
            f"<td style='padding:7px 10px;font-size:11px;color:{C['text']};"
            f"font-family:monospace;'>{_fmt(row.get('actual'))}</td>"
            f"<td style='padding:7px 10px;font-size:11px;color:{C['muted']};"
            f"font-family:monospace;'>{_fmt(row.get('forecast'))}</td>"
            f"<td style='padding:7px 10px;font-size:11px;color:{C['muted']};"
            f"font-family:monospace;'>{_fmt(row.get('previous'))}</td>"
            f"<td style='padding:7px 10px;'>{_impact_pill(row['impact'])}</td>"
            f"</tr>"
        )

    return (
        f"<div style='background:{C['card']};border:1px solid {C['border']};"
        f"border-radius:10px;max-height:520px;overflow-y:auto;'>"
        f"<table style='width:100%;border-collapse:collapse;'>"
        f"<thead>{hdr}</thead><tbody>{body}</tbody>"
        f"</table></div>"
    )


# ╔══════════════════════════════════════════════════════════════════════════════
# ║  DATA
# ╚══════════════════════════════════════════════════════════════════════════════

def _classify(title: str) -> tuple[str, str]:
    """(category, color) from headline keywords. Defaults to General."""
    t = title.lower()
    for cat, meta in _CATEGORIES.items():
        if any(kw in t for kw in meta["kw"]):
            return cat, meta["color"]
    return "General", C["muted"]


def _is_econ_noise(title: str) -> bool:
    t = title.lower()
    return any(kw in t for kw in _ECON_SKIP_KW)


def _fmt_time(entry) -> str:
    pub = getattr(entry, "published_parsed", None)
    if pub:
        try:
            dt   = datetime(*pub[:6])
            now  = datetime.utcnow()
            diff = (now - dt).total_seconds()
            if diff < 3600:
                return f"{int(diff / 60)}m ago"
            if diff < 86400:
                return f"{int(diff / 3600)}h ago"
            return dt.strftime("%b %d")
        except Exception:
            pass
    raw = getattr(entry, "published", "") or ""
    return raw[:16] if raw else ""


def _get_pub_dt(entry) -> "datetime | None":
    """Extract a timezone-aware UTC datetime from a feedparser entry for sorting."""
    pub = getattr(entry, "published_parsed", None)
    if pub:
        try:
            return datetime(*pub[:6], tzinfo=timezone.utc)
        except Exception:
            pass
    return None


def _fetch_rss_entries(url: str) -> list:
    """
    Fetch RSS entries via requests + browser headers, fall back to direct feedparser.
    Using requests with proper headers avoids 403/429 blocks from Google News and others.
    """
    if _FEEDPARSER:
        try:
            r = requests.get(url, timeout=12, headers=_FIN_HEADERS)
            if r.status_code == 200:
                return feedparser.parse(r.content).entries or []
        except Exception:
            pass
        try:
            return feedparser.parse(url).entries or []
        except Exception:
            pass
    return []


@st.cache_data(ttl=TTL_CCY)
def fetch_ccy_news(ccy: str) -> list[dict]:
    """
    Fetch geo-political headlines for one currency via Google News RSS.
    Two queries per currency, up to 8 articles each. Filters out economic noise.
    """
    if not _FEEDPARSER:
        return []

    articles: list[dict] = []
    seen: set[str] = set()

    for query in _CCY_GEO_QUERIES.get(ccy, []):
        try:
            url = (
                "https://news.google.com/rss/search?q="
                + urllib.parse.quote_plus(query)
                + "&hl=en-US&gl=US&ceid=US:en"
            )
            for entry in _fetch_rss_entries(url)[:8]:
                title = getattr(entry, "title", "") or ""
                key   = title[:60].lower().strip()
                if not key or key in seen or _is_econ_noise(title):
                    continue
                seen.add(key)

                src    = getattr(entry, "source", None)
                source = getattr(src, "title", "Google News") if src else "Google News"
                cat, cat_col = _classify(title)

                articles.append({
                    "title":   title,
                    "source":  source,
                    "url":     getattr(entry, "link", "") or "",
                    "time":    _fmt_time(entry),
                    "category":cat,
                    "cat_col": cat_col,
                    "_pub_dt": _get_pub_dt(entry),
                })
        except Exception:
            continue

    articles.sort(
        key=lambda a: a["_pub_dt"] or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    return articles


@st.cache_data(ttl=TTL_GLOBAL)
def fetch_global_news() -> list[dict]:
    """
    Fetch top geo headlines from Reuters, BBC, and Al Jazeera RSS feeds.
    Filters to geo-only articles (skips General + economic noise).
    """
    if not _FEEDPARSER:
        return []

    articles: list[dict] = []
    seen: set[str] = set()

    for source_name, feed_url in _DIRECT_FEEDS:
        try:
            for entry in _fetch_rss_entries(feed_url)[:20]:
                title = getattr(entry, "title", "") or ""
                key   = title[:60].lower().strip()
                if not key or key in seen or _is_econ_noise(title):
                    continue
                cat, cat_col = _classify(title)
                if cat == "General":
                    continue  # direct feeds: only keep articles with a geo category
                seen.add(key)
                articles.append({
                    "title":   title,
                    "source":  source_name,
                    "url":     getattr(entry, "link", "") or "",
                    "time":    _fmt_time(entry),
                    "category":cat,
                    "cat_col": cat_col,
                    "_pub_dt": _get_pub_dt(entry),
                })
        except Exception:
            continue

    articles.sort(
        key=lambda a: a["_pub_dt"] or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    return articles[:14]


@st.cache_data(ttl=TTL_FIN, show_spinner=False)
def fetch_financial_news(ccy: str) -> tuple[list[dict], dict[str, str]]:
    """
    Fetch financial RSS news for the selected currency.
    Sources: FXStreet, ForexLive, CNBC, Bloomberg, MarketWatch, Investing.
    Returns (items, source_errors) — items sorted newest-first, max 40.
    """
    import email.utils as _eu
    import xml.etree.ElementTree as ET

    keywords      = [k.lower() for k in _CCY_FIN_KW.get(ccy, [])]
    items:         list[dict]     = []
    source_errors: dict[str, str] = {}

    for source_name, url in _FIN_FEEDS:
        try:
            r = requests.get(url, timeout=12, headers=_FIN_HEADERS)
            if r.status_code != 200:
                source_errors[source_name] = f"HTTP {r.status_code}"
                continue
            content = r.content

            if _FEEDPARSER:
                feed = feedparser.parse(content)
                for entry in (feed.entries or [])[:60]:
                    title = getattr(entry, "title",   "") or ""
                    desc  = (getattr(entry, "summary", "") or
                             getattr(entry, "description", "") or "")
                    link  = getattr(entry, "link",    "") or ""
                    pt    = getattr(entry, "published_parsed", None)
                    pub: datetime | None = None
                    if pt:
                        try:
                            pub = datetime(*pt[:6], tzinfo=timezone.utc)
                        except Exception:
                            pass
                    if any(kw in (title + " " + desc).lower() for kw in keywords):
                        items.append({"title": title.strip(), "source": source_name,
                                      "url": link.strip(), "published": pub})
            else:
                ns   = "{http://www.w3.org/2005/Atom}"
                root = ET.fromstring(content)
                for entry in (root.findall(".//item") or root.findall(f".//{ns}entry")):
                    def _g(tag: str) -> str:
                        el = entry.find(tag) or entry.find(f"{ns}{tag}")
                        return (el.text or "").strip() if el is not None else ""
                    title   = _g("title")
                    desc    = _g("description") or _g("summary")
                    le      = entry.find("link") or entry.find(f"{ns}link")
                    link    = ((le.text or le.get("href", "")) if le is not None else "")
                    pub_str = _g("pubDate") or _g("published") or _g("updated")
                    pub     = None
                    try:
                        pub = _eu.parsedate_to_datetime(pub_str)
                    except Exception:
                        pass
                    if any(kw in (title + " " + desc).lower() for kw in keywords):
                        items.append({"title": title, "source": source_name,
                                      "url": link.strip(), "published": pub})

        except requests.exceptions.ConnectionError:
            source_errors[source_name] = "connection refused"
        except requests.exceptions.Timeout:
            source_errors[source_name] = "timeout"
        except Exception as e:
            source_errors[source_name] = type(e).__name__

    items.sort(
        key=lambda x: x["published"] or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    return items[:40], source_errors


def _time_ago(pub: datetime | None) -> str:
    if pub is None:
        return ""
    try:
        now  = datetime.now(timezone.utc)
        diff = (now - pub).total_seconds()
        if diff < 3600:
            return f"{int(diff / 60)}m ago"
        if diff < 86400:
            return f"{int(diff / 3600)}h ago"
        return pub.strftime("%b %d")
    except Exception:
        return ""


# ╔══════════════════════════════════════════════════════════════════════════════
# ║  RENDER
# ╚══════════════════════════════════════════════════════════════════════════════

def render_ccy_profile(ccy: str) -> str:
    p = _CCY_PROFILE[ccy]

    bullets = "".join(
        f"<li style='margin-bottom:7px;color:{C['text']};font-size:12px;"
        f"font-family:sans-serif;line-height:1.5;'>{txt}</li>"
        for txt in p["context"]
    )
    risk_tags = "".join(
        f"<span style='background:{C['dim']};border:1px solid {C['border']};"
        f"color:{C['muted']};font-family:monospace;font-size:9px;font-weight:600;"
        f"padding:2px 9px;border-radius:10px;display:inline-block;"
        f"margin:0 4px 5px 0;'>{r}</span>"
        for r in p["key_risks"]
    )

    return (
        f"<div style='background:{C['card']};border:1px solid {C['border']};"
        f"border-radius:12px;padding:24px 20px;'>"
        f"<div style='text-align:center;margin-bottom:18px;'>"
        f"<div style='font-size:54px;line-height:1;'>{CURRENCY_FLAG[ccy]}</div>"
        f"<div style='font-size:26px;font-weight:800;color:{C['text']};"
        f"font-family:monospace;margin-top:8px;letter-spacing:1px;'>{ccy}</div>"
        f"<div style='font-size:11px;color:{C['muted']};font-family:sans-serif;"
        f"margin-top:3px;'>{CURRENCY_NAME[ccy]}</div>"
        f"<div style='margin-top:10px;'>"
        f"<span style='background:{p['sens_col']};color:{C['bg']};font-family:monospace;"
        f"font-size:9px;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;"
        f"padding:3px 12px;border-radius:20px;'>{p['sensitivity']}</span>"
        f"</div></div>"
        f"<div style='border-top:1px solid {C['border']};padding-top:16px;'>"
        f"<div style='font-size:9px;color:{C['muted']};font-family:monospace;"
        f"letter-spacing:2px;text-transform:uppercase;margin-bottom:10px;'>"
        f"Geo Sensitivity</div>"
        f"<ul style='margin:0;padding-left:16px;'>{bullets}</ul>"
        f"<div style='margin-top:16px;'>"
        f"<div style='font-size:9px;color:{C['muted']};font-family:monospace;"
        f"letter-spacing:2px;text-transform:uppercase;margin-bottom:8px;'>"
        f"Key Geo Risks</div>"
        f"<div style='display:flex;flex-wrap:wrap;'>{risk_tags}</div>"
        f"</div></div></div>"
    )


def _news_card(art: dict, ccy: str = "") -> str:
    title  = art["title"].replace("<", "&lt;").replace(">", "&gt;")
    source = art["source"].replace("<", "&lt;").replace(">", "&gt;")
    cc     = art["cat_col"]
    cat    = art["category"]

    interp = ""
    if ccy and cat != "General":
        text = _CCY_CAT_INTERP.get(ccy, {}).get(cat, "")
        if text:
            interp = (
                f"<div style='margin-top:8px;padding:8px 10px;"
                f"background:{C['dim']};border-radius:6px;"
                f"font-size:11px;color:{C['teal']};font-family:sans-serif;"
                f"font-style:italic;line-height:1.5;'>"
                f"&#9656; {text}</div>"
            )

    return (
        f"<div style='border-left:3px solid {cc};background:{C['panel']};"
        f"border-radius:0 8px 8px 0;padding:14px 16px;margin-bottom:10px;'>"
        f"<div style='display:flex;align-items:center;gap:8px;margin-bottom:8px;"
        f"flex-wrap:wrap;'>"
        f"<span style='background:{C['dim']};color:{C['muted']};font-family:monospace;"
        f"font-size:9px;font-weight:600;padding:2px 7px;border-radius:4px;'>"
        f"{source}</span>"
        f"<span style='color:{cc};font-family:monospace;font-size:9px;font-weight:700;"
        f"letter-spacing:0.5px;text-transform:uppercase;'>{cat}</span>"
        f"<span style='color:{C['muted']};font-family:monospace;font-size:9px;"
        f"margin-left:auto;white-space:nowrap;'>{art['time']}</span>"
        f"</div>"
        f"<div style='font-size:13px;color:{C['text']};font-family:sans-serif;"
        f"line-height:1.5;font-weight:500;'>{title}</div>"
        + (
            f"<div style='margin-top:4px;'>"
            f"<a href='{art['url']}' target='_blank' rel='noopener' "
            f"style='font-size:10px;color:#6b7280;font-family:monospace;"
            f"text-decoration:none;'>↗ Read more</a></div>"
            if art.get("url") else ""
        )
        + f"{interp}"
        f"</div>"
    )


def render_ccy_feed(articles: list[dict], ccy: str, fetched_at: str) -> str:
    if not articles:
        return (
            f"<div style='background:{C['card']};border:1px solid {C['border']};"
            f"border-radius:12px;padding:40px;text-align:center;'>"
            f"<div style='font-size:32px;margin-bottom:12px;'>🔍</div>"
            f"<div style='font-size:13px;color:{C['muted']};font-family:monospace;"
            f"margin-bottom:6px;'>No geopolitical headlines found for {ccy}</div>"
            f"<div style='font-size:11px;color:{C['muted']};font-family:sans-serif;'>"
            f"Google News may be temporarily rate-limited — try refreshing in 30s</div>"
            f"</div>"
        )

    cards = "".join(_news_card(a, ccy) for a in articles)
    return (
        f"<div style='background:{C['card']};border:1px solid {C['border']};"
        f"border-radius:12px;padding:18px 18px 14px;'>"
        f"<div style='display:flex;justify-content:space-between;align-items:center;"
        f"margin-bottom:14px;flex-wrap:wrap;gap:6px;'>"
        f"<div style='font-size:10px;color:{C['muted']};font-family:monospace;"
        f"letter-spacing:2px;text-transform:uppercase;'>"
        f"Headlines &mdash; {ccy}</div>"
        f"<div style='font-size:10px;color:{C['muted']};font-family:monospace;'>"
        f"{len(articles)} articles &middot; updated {fetched_at}</div>"
        f"</div>"
        f"<div style='max-height:680px;overflow-y:auto;padding-right:4px;'>"
        f"{cards}</div></div>"
    )


def render_global_feed(articles: list[dict]) -> str:
    if not articles:
        return ""

    rows = "".join(
        f"<div style='padding:10px 0;border-bottom:1px solid {C['border']};'>"
        f"<div style='display:flex;align-items:center;gap:8px;margin-bottom:5px;"
        f"flex-wrap:wrap;'>"
        f"<span style='color:{a['cat_col']};font-family:monospace;font-size:9px;"
        f"font-weight:700;text-transform:uppercase;'>{a['category']}</span>"
        f"<span style='background:{C['dim']};color:{C['muted']};font-family:monospace;"
        f"font-size:9px;font-weight:600;padding:1px 6px;border-radius:3px;'>"
        f"{a['source']}</span>"
        f"<span style='color:{C['muted']};font-family:monospace;font-size:9px;"
        f"margin-left:auto;'>{a['time']}</span>"
        f"</div>"
        f"<div style='font-size:12px;color:{C['text']};font-family:sans-serif;"
        f"line-height:1.4;'>"
        f"{a['title'].replace('<','&lt;').replace('>','&gt;')}</div>"
        + (
            f"<div style='margin-top:3px;'>"
            f"<a href='{a['url']}' target='_blank' rel='noopener' "
            f"style='font-size:10px;color:#6b7280;font-family:monospace;"
            f"text-decoration:none;'>↗ Read more</a></div>"
            if a.get("url") else ""
        )
        + f"</div>"
        for a in articles
    )

    return (
        f"<div style='background:{C['card']};border:1px solid {C['border']};"
        f"border-radius:12px;padding:18px 18px 14px;margin-top:14px;'>"
        f"<div style='font-size:10px;color:{C['muted']};font-family:monospace;"
        f"letter-spacing:2px;text-transform:uppercase;margin-bottom:12px;'>"
        f"Global Geo Events &mdash; Reuters &middot; BBC &middot; Al Jazeera</div>"
        f"<div style='max-height:340px;overflow-y:auto;'>{rows}</div>"
        f"</div>"
    )


def render_financial_feed(
    items: list[dict],
    source_errors: dict[str, str],
    ccy: str,
    source_filter: str = "All",
) -> str:
    visible = (
        items if source_filter == "All"
        else [n for n in items if n["source"] == source_filter]
    )

    if not visible and not source_errors:
        return (
            f"<div style='background:{C['card']};border:1px solid {C['border']};"
            f"border-radius:10px;padding:32px;text-align:center;"
            f"color:{C['muted']};font-family:monospace;font-size:13px;'>"
            f"No financial news loaded — check network connection</div>"
        )
    if not visible:
        errs = " &nbsp;&middot;&nbsp; ".join(
            f"{s}: {e}" for s, e in source_errors.items()
        )
        return (
            f"<div style='background:{C['card']};border:1px solid {C['border']};"
            f"border-radius:10px;padding:32px;text-align:center;"
            f"color:{C['muted']};font-family:monospace;font-size:13px;'>"
            f"No {ccy} news matched &nbsp; "
            f"<span style='opacity:0.6;font-size:10px;'>{errs}</span></div>"
        )

    cards = ""
    for item in visible:
        t_str  = _time_ago(item.get("published"))
        title  = item.get("title", "").replace("<", "&lt;").replace(">", "&gt;")
        url    = item.get("url", "#")
        source = item.get("source", "")
        cards += (
            f"<div style='padding:11px 14px;border-bottom:1px solid {C['border']};'>"
            f"<div style='display:flex;align-items:center;gap:8px;margin-bottom:5px;'>"
            f"<span style='background:{C['dim']};color:{C['teal']};font-size:9px;"
            f"font-family:monospace;font-weight:700;letter-spacing:1px;"
            f"padding:2px 7px;border-radius:4px;text-transform:uppercase;'>{source}</span>"
            f"<span style='font-size:10px;color:{C['muted']};font-family:monospace;'>"
            f"{t_str}</span>"
            f"</div>"
            f"<a href='{url}' target='_blank' rel='noopener'"
            f"   style='color:{C['text']};text-decoration:none;font-size:12px;"
            f"          line-height:1.5;font-family:sans-serif;'>{title}</a>"
            + (
                f"<div style='margin-top:3px;'>"
                f"<a href='{url}' target='_blank' rel='noopener' "
                f"style='font-size:10px;color:#6b7280;font-family:monospace;"
                f"text-decoration:none;'>↗ Read more</a></div>"
                if url and url != "#" else ""
            )
            + f"</div>"
        )

    err_banner = ""
    if source_errors:
        err_parts = " &nbsp;&middot;&nbsp; ".join(
            f"&#9888; {s} — {m}" for s, m in source_errors.items()
        )
        err_banner = (
            f"<div style='padding:6px 14px;border-top:1px solid {C['border']};"
            f"font-size:9px;color:{C['muted']};font-family:monospace;"
            f"background:{C['dim']};'>{err_parts}</div>"
        )

    return (
        f"<div style='background:{C['card']};border:1px solid {C['border']};"
        f"border-radius:10px;overflow:hidden;'>"
        f"<div style='max-height:620px;overflow-y:auto;'>{cards}</div>"
        f"{err_banner}"
        f"<div style='padding:8px 14px;border-top:1px solid {C['border']};"
        f"text-align:right;font-size:9px;color:{C['muted']};font-family:monospace;'>"
        f"Sources: FXStreet &middot; ForexLive &middot; CNBC &middot; "
        f"Bloomberg &middot; MarketWatch &middot; Investing.com</div>"
        f"</div>"
    )


# ╔══════════════════════════════════════════════════════════════════════════════
# ║  ENTRY POINT
# ╚══════════════════════════════════════════════════════════════════════════════

def main():
    st.set_page_config(
        page_title="Geopolitics & News · Trading Terminal",
        page_icon="🌍",
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
      /* Currency pill selector */
      div[data-testid="stRadio"] > label {{ display:none !important; }}
      div[data-testid="stRadio"] > div[role="radiogroup"] {{
          display:flex !important; flex-wrap:wrap !important;
          gap:8px !important; background:transparent !important;
      }}
      div[data-testid="stRadio"] label {{
          background:{C['card']} !important;
          border:1px solid {C['border']} !important;
          border-radius:10px !important; padding:8px 16px !important;
          cursor:pointer !important; font-family:monospace !important;
          font-size:13px !important; font-weight:700 !important;
          color:{C['muted']} !important; margin:0 !important;
          transition:all 0.15s !important;
      }}
      div[data-testid="stRadio"] label:has(input:checked) {{
          background:{C['dim']} !important;
          border-color:{C['teal']} !important;
          color:{C['text']} !important;
          box-shadow: 0 0 0 1px {C['teal']} !important;
      }}
      div[data-testid="stRadio"] label input {{ display:none !important; }}
      /* Hide the Streamlit radio indicator circle (outer red / inner white dot) —
         its pseudo-element positioning breaks under display:inline */
      div[data-testid="stRadio"] label > div:not(:has(p)) {{ display:none !important; }}
      /* Apply inline only to the text-content wrapper and its <p> */
      div[data-testid="stRadio"] label > div:has(p),
      div[data-testid="stRadio"] label > div:has(p) > p {{
          display:inline !important; font-family:monospace !important;
          font-size:13px !important; font-weight:700 !important;
      }}
      button[kind="secondary"] {{
          background:{C['dim']} !important; color:{C['muted']} !important;
          border:1px solid {C['border']} !important;
          font-family:monospace !important; font-weight:600 !important;
          border-radius:8px !important;
      }}
      button[kind="secondary"]:hover {{
          border-color:{C['teal']} !important; color:{C['teal']} !important;
      }}
      button[kind="primary"] {{
          background:{C['teal']} !important; color:#0a0c10 !important;
          border:none !important; font-weight:700 !important;
          font-family:monospace !important; border-radius:8px !important;
      }}
      p, span, label {{ color:{C['text']}; }}
      div[data-testid="stSpinner"] p {{
          color:{C['muted']} !important; font-family:monospace !important;
          font-size:12px !important;
      }}
      /* Live pulse dot */
      @keyframes geo-pulse {{
        0%,100% {{ opacity:1; }} 50% {{ opacity:0.3; }}
      }}
      .geo-live-dot {{ animation: geo-pulse 2s ease-in-out infinite; }}
    </style>
    """, unsafe_allow_html=True)

    # ── Session state ──────────────────────────────────────────────────────────
    _now = time.time()
    if "geo_ccy" not in st.session_state:
        st.session_state.geo_ccy = "USD"
    if "geo_last_refresh" not in st.session_state:
        st.session_state.geo_last_refresh = _now

    # Auto-rerun every TTL_CCY seconds — clears both caches
    if _now - st.session_state.geo_last_refresh > TTL_CCY:
        fetch_ccy_news.clear()
        fetch_global_news.clear()
        fetch_financial_news.clear()
        fetch_ff_calendar_m4.clear()
        st.session_state.geo_last_refresh = _now
        st.rerun()

    last_refresh_str = datetime.fromtimestamp(
        st.session_state.geo_last_refresh
    ).strftime("%H:%M:%S")

    # ── Title row ──────────────────────────────────────────────────────────────
    col_back, col_title, col_right = st.columns([2, 6, 2])
    with col_back:
        if st.button("← Back to Hub"):
            st.switch_page("app.py")
    with col_title:
        st.markdown(
            f"<div style='text-align:center;'>"
            f"<div style='font-size:20px;font-weight:800;color:{C['text']};"
            f"font-family:monospace;letter-spacing:-0.5px;'>"
            f"GEOPOLITICS &amp; NEWS</div>"
            f"<div style='display:flex;align-items:center;justify-content:center;"
            f"gap:8px;margin-top:4px;'>"
            f"<span class='geo-live-dot' style='width:6px;height:6px;border-radius:50%;"
            f"background:{C['red']};display:inline-block;'></span>"
            f"<span style='font-size:10px;color:{C['muted']};font-family:monospace;"
            f"letter-spacing:1px;'>LIVE &middot; Geo Events &middot; Conflicts &middot; "
            f"Sanctions &middot; Financial News</span>"
            f"</div></div>",
            unsafe_allow_html=True,
        )
    with col_right:
        _, btn_col = st.columns([1, 1])
        with btn_col:
            if st.button("🔄 Refresh", key="geo_refresh"):
                fetch_ccy_news.clear()
                fetch_global_news.clear()
                fetch_financial_news.clear()
                fetch_ff_calendar_m4.clear()
                st.session_state.geo_last_refresh = time.time()
                st.rerun()

    st.markdown(
        f"<div style='margin-bottom:6px;padding-bottom:16px;"
        f"border-bottom:1px solid {C['border']};'></div>",
        unsafe_allow_html=True,
    )

    # ── Currency selector ──────────────────────────────────────────────────────
    labels = [f"{CURRENCY_FLAG[c]}  {c}" for c in CURRENCIES]
    default_idx = CURRENCIES.index(st.session_state.geo_ccy)

    selected_label = st.radio(
        "currency",
        options=labels,
        index=default_idx,
        horizontal=True,
        label_visibility="collapsed",
    )
    selected_ccy = selected_label.split()[-1]  # extract "USD" from "🇺🇸  USD"
    st.session_state.geo_ccy = selected_ccy

    st.markdown("<div style='margin-bottom:16px;'></div>", unsafe_allow_html=True)

    # ── Data fetch — geo (always) ──────────────────────────────────────────────
    if not _FEEDPARSER:
        st.warning("feedparser not installed — run: pip install feedparser")
        ccy_articles    = []
        global_articles = []
    else:
        with st.spinner(f"Fetching geopolitical news for {selected_ccy}..."):
            ccy_articles    = fetch_ccy_news(selected_ccy)
            global_articles = fetch_global_news()

    # ── Two-column layout ──────────────────────────────────────────────────────
    col_profile, col_news = st.columns([2, 5], gap="large")

    with col_profile:
        st.markdown(render_ccy_profile(selected_ccy), unsafe_allow_html=True)
        st.markdown(render_global_feed(global_articles), unsafe_allow_html=True)

    with col_news:
        # ── Tab switcher: Geo Events | Financial News | Economic Calendar ─────
        news_tab = st.radio(
            "news_tab",
            ["🌍  Geo Events", "📰  Financial News", "📅  Economic Calendar"],
            horizontal=True,
            key="geo_news_tab",
            label_visibility="collapsed",
        )
        st.markdown("<div style='margin-bottom:10px;'></div>", unsafe_allow_html=True)

        if news_tab.startswith("🌍"):
            st.markdown(
                render_ccy_feed(ccy_articles, selected_ccy, last_refresh_str),
                unsafe_allow_html=True,
            )
        elif news_tab.startswith("📰"):
            with st.spinner(f"Fetching financial news for {selected_ccy}..."):
                fin_items, fin_errors = fetch_financial_news(selected_ccy)

            # Source filter
            source_filter = st.radio(
                "fin_source",
                options=_FIN_SOURCE_NAMES,
                horizontal=True,
                key="geo_fin_source",
                label_visibility="collapsed",
            )
            st.markdown("<div style='height:6px;'></div>", unsafe_allow_html=True)
            st.markdown(
                render_financial_feed(fin_items, fin_errors, selected_ccy, source_filter),
                unsafe_allow_html=True,
            )
        else:
            with st.spinner("Loading economic calendar..."):
                cal_df = fetch_ff_calendar_m4()
            calendar_view = build_calendar_view_m4(cal_df, selected_ccy)
            st.markdown(render_calendar_table_m4(calendar_view), unsafe_allow_html=True)

    # ── Footer ─────────────────────────────────────────────────────────────────
    st.markdown(
        f"<div style='margin-top:40px;padding-top:16px;"
        f"border-top:1px solid {C['border']};text-align:center;"
        f"font-size:11px;color:{C['muted']};font-family:monospace;'>"
        f"Built by @realedgetraders"
        f"&nbsp;&nbsp;&middot;&nbsp;&nbsp;"
        f"Sources: Google News &middot; Reuters &middot; BBC &middot; Al Jazeera "
        f"&middot; FXStreet &middot; ForexLive &middot; CNBC &middot; Bloomberg"
        f"&nbsp;&nbsp;&middot;&nbsp;&nbsp;"
        f"Auto-refresh every 5 min"
        f"</div>",
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
