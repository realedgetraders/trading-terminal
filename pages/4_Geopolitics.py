"""
Trading Analytics Terminal — Module 4: Geopolitical Intelligence
Currency-filtered geo news — no economic data, no trade signals
Sources: Google News · Reuters · BBC · Al Jazeera
"""

import time
import urllib.parse
from datetime import datetime

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
    "bg":       "#0a0f1e",
    "card":     "#0d1526",
    "border":   "#1a2540",
    "panel":    "#0f1a2e",
    "dim":      "#192038",
    "text":     "#dde4f0",
    "muted":    "#445066",
    "teal":     "#45c4b0",
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
        "sens_col":   "#45c4b0",
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
        "sens_col":   "#45c4b0",
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

TTL_CCY    = 300   # 5-min — per-currency Google News cache
TTL_GLOBAL = 600   # 10-min — direct RSS feed cache


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
            feed = feedparser.parse(url)
            for entry in (feed.entries or [])[:8]:
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
                })
        except Exception:
            continue

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
            feed = feedparser.parse(feed_url)
            for entry in (feed.entries or [])[:20]:
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
                })
        except Exception:
            continue

    return articles[:14]


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


def _news_card(art: dict) -> str:
    title  = art["title"].replace("<", "&lt;").replace(">", "&gt;")
    source = art["source"].replace("<", "&lt;").replace(">", "&gt;")
    cc     = art["cat_col"]

    return (
        f"<div style='border-left:3px solid {cc};background:{C['panel']};"
        f"border-radius:0 8px 8px 0;padding:14px 16px;margin-bottom:10px;'>"
        f"<div style='display:flex;align-items:center;gap:8px;margin-bottom:8px;"
        f"flex-wrap:wrap;'>"
        f"<span style='background:{C['dim']};color:{C['muted']};font-family:monospace;"
        f"font-size:9px;font-weight:600;padding:2px 7px;border-radius:4px;'>"
        f"{source}</span>"
        f"<span style='color:{cc};font-family:monospace;font-size:9px;font-weight:700;"
        f"letter-spacing:0.5px;text-transform:uppercase;'>{art['category']}</span>"
        f"<span style='color:{C['muted']};font-family:monospace;font-size:9px;"
        f"margin-left:auto;white-space:nowrap;'>{art['time']}</span>"
        f"</div>"
        f"<div style='font-size:13px;color:{C['text']};font-family:sans-serif;"
        f"line-height:1.5;font-weight:500;'>{title}</div>"
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

    cards = "".join(_news_card(a) for a in articles)
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
        f"</div>"
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


# ╔══════════════════════════════════════════════════════════════════════════════
# ║  ENTRY POINT
# ╚══════════════════════════════════════════════════════════════════════════════

def main():
    st.set_page_config(
        page_title="Geopolitical Intelligence · Trading Terminal",
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
      div[data-testid="stRadio"] label > div,
      div[data-testid="stRadio"] label > div > p {{
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
            f"GEOPOLITICAL INTELLIGENCE</div>"
            f"<div style='display:flex;align-items:center;justify-content:center;"
            f"gap:8px;margin-top:4px;'>"
            f"<span class='geo-live-dot' style='width:6px;height:6px;border-radius:50%;"
            f"background:{C['red']};display:inline-block;'></span>"
            f"<span style='font-size:10px;color:{C['muted']};font-family:monospace;"
            f"letter-spacing:1px;'>LIVE &middot; Conflicts &middot; Sanctions &middot; "
            f"Political &middot; Trade Wars &middot; Diplomacy</span>"
            f"</div></div>",
            unsafe_allow_html=True,
        )
    with col_right:
        _, btn_col = st.columns([1, 1])
        with btn_col:
            if st.button("🔄 Refresh", key="geo_refresh"):
                fetch_ccy_news.clear()
                fetch_global_news.clear()
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

    # ── Data fetch ─────────────────────────────────────────────────────────────
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
        st.markdown(
            render_ccy_feed(ccy_articles, selected_ccy, last_refresh_str),
            unsafe_allow_html=True,
        )

    # ── Footer ─────────────────────────────────────────────────────────────────
    st.markdown(
        f"<div style='margin-top:40px;padding-top:16px;"
        f"border-top:1px solid {C['border']};text-align:center;"
        f"font-size:11px;color:{C['muted']};font-family:monospace;'>"
        f"Built by @realedgetraders"
        f"&nbsp;&nbsp;&middot;&nbsp;&nbsp;"
        f"Sources: Google News &middot; Reuters &middot; BBC &middot; Al Jazeera"
        f"&nbsp;&nbsp;&middot;&nbsp;&nbsp;"
        f"Auto-refresh every 5 min"
        f"</div>",
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
