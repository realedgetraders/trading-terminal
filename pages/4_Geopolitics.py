"""
Trading Analytics Terminal — Module 4: Geopolitical Dashboard
Live geo-risk tracker — conflicts, sanctions, political crises & FX currency impact
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
}

CURRENCIES    = ["USD", "EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "NZD"]
CURRENCY_FLAG = {
    "USD": "🇺🇸", "EUR": "🇪🇺", "GBP": "🇬🇧", "JPY": "🇯🇵",
    "AUD": "🇦🇺", "CAD": "🇨🇦", "CHF": "🇨🇭", "NZD": "🇳🇿",
}

# ── Google News RSS queries per category ──────────────────────────────────────
_GEO_QUERIES: dict[str, str] = {
    "War":       "war military conflict airstrike battle troops invasion when:2d",
    "Trade War": "trade war tariffs sanctions trade restrictions embargo when:2d",
    "Political": "political crisis government instability coup election when:2d",
    "Energy":    "oil energy prices OPEC supply disruption crisis when:2d",
    "Diplomacy": "ceasefire peace deal diplomatic agreement summit when:2d",
}

_CAT_COLOR: dict[str, str] = {
    "War":       "#f05262",
    "Trade War": "#f08c29",
    "Sanctions": "#f0b429",
    "Political": "#4f8ef7",
    "Energy":    "#45c4b0",
    "Diplomacy": "#00c48c",
}

# ── Keyword scoring: positive weight = tension/risk-off ───────────────────────
_RISK_KW: list[tuple[str, float]] = [
    ("nuclear threat",        3.0), ("war declared",          3.0),
    ("military invasion",     3.0), ("nuclear strike",        3.0),
    ("airstrike",             2.5), ("missile attack",        2.5),
    ("shoot down",            2.0), ("naval blockade",        2.0),
    ("military conflict",     2.0), ("conflict escalat",      2.0),
    ("oil embargo",           2.0), ("oil spike",             2.0),
    ("military buildup",      1.5), ("energy crisis",         1.5),
    ("sanctions imposed",     1.5), ("new sanctions",         1.5),
    ("trade war",             1.5), ("government collapse",   1.5),
    ("coup",                  1.5), ("terrorist",             1.5),
    ("political crisis",      1.0), ("hostage",               1.0),
    ("supply disruption",     1.0), ("oil price surge",       1.5),
    ("ceasefire",            -2.5), ("peace deal",           -2.5),
    ("peace agreement",      -2.5), ("sanctions lifted",     -2.0),
    ("sanctions removed",    -2.0), ("diplomatic breakthrough", -2.0),
    ("de-escalat",           -1.5), ("peace talks",          -1.5),
    ("trade deal",           -1.5), ("agreement reached",    -1.0),
    ("withdraw troops",      -1.5), ("normalized relations", -1.5),
    ("stability restored",   -1.0), ("oil supply restored",  -1.5),
]

# Currency geo-sensitivity: positive = benefits from tension (safe-haven inflow)
# Negative = hurt by tension (risk-correlated selling)
_CCY_GEO: dict[str, float] = {
    "CHF":  1.5,   # strongest safe-haven
    "JPY":  1.5,   # strong safe-haven (carry unwind)
    "USD":  0.8,   # reserve-currency safe-haven bid
    "CAD":  0.5,   # oil exporter: energy shock offset
    "EUR": -0.5,   # geopolitically exposed (Ukraine proximity)
    "GBP": -0.3,   # moderate exposure
    "AUD": -0.8,   # risk-correlated commodity currency
    "NZD": -1.0,   # most risk-sensitive G10
}

TTL_GEO = 300  # 5-min cache


# ╔══════════════════════════════════════════════════════════════════════════════
# ║  DATA
# ╚══════════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=TTL_GEO)
def fetch_geo_news() -> list[dict]:
    """
    Fetch geo-political news per category via Google News RSS.
    Returns list of article dicts: title, source, url, published, category, score.
    Falls back to empty list on any failure.
    """
    if not _FEEDPARSER:
        return []

    articles: list[dict] = []
    seen:     set[str]   = set()

    for category, query in _GEO_QUERIES.items():
        try:
            url = (
                "https://news.google.com/rss/search?q="
                + urllib.parse.quote_plus(query)
                + "&hl=en-US&gl=US&ceid=US:en"
            )
            feed = feedparser.parse(url)
            for entry in (feed.entries or [])[:6]:
                title  = getattr(entry, "title", "") or ""
                link   = getattr(entry, "link",  "") or ""
                src    = getattr(entry, "source", None)
                source = getattr(src, "title", "Reuters") if src else "Reuters"

                pub_tuple = getattr(entry, "published_parsed", None)
                published = ""
                if pub_tuple:
                    try:
                        published = datetime(*pub_tuple[:6]).strftime("%b %d, %H:%M")
                    except Exception:
                        pass
                if not published:
                    published = getattr(entry, "published", "") or ""

                key = title[:60].lower().strip()
                if not key or key in seen:
                    continue
                seen.add(key)

                text  = title.lower()
                score = sum(w for kw, w in _RISK_KW if kw in text)

                articles.append({
                    "title":     title,
                    "source":    source,
                    "url":       link,
                    "published": published,
                    "category":  category,
                    "score":     score,
                })
        except Exception:
            continue

    articles.sort(key=lambda x: abs(x["score"]), reverse=True)
    return articles


def calc_tension_score(articles: list[dict]) -> float:
    """
    Aggregate geo tension score ∈ [-3.0, +3.0].
    Positive = risk-off / high tension. Negative = calm / risk-on.
    """
    if not articles:
        return 0.0
    total = sum(a["score"] for a in articles)
    raw   = (total / len(articles)) * 1.5
    return round(max(-3.0, min(3.0, raw)), 2)


def calc_ccy_impacts(tension: float) -> dict[str, dict]:
    """Return per-currency geo impact. Each dict: score, label, color, direction."""
    out: dict[str, dict] = {}
    for ccy in CURRENCIES:
        score = round(max(-3.0, min(3.0, tension * _CCY_GEO[ccy])), 2)
        if score >= 1.5:
            label, color = "STRONG BULLISH", C["green"]
        elif score >= 0.5:
            label, color = "SLIGHT BULLISH", C["teal"]
        elif score >= -0.5:
            label, color = "NEUTRAL",        C["muted"]
        elif score >= -1.5:
            label, color = "SLIGHT BEARISH", C["yellow"]
        else:
            label, color = "STRONG BEARISH", C["red"]
        direction = "↑" if score > 0.1 else ("↓" if score < -0.1 else "→")
        out[ccy] = {"score": score, "label": label, "color": color,
                    "direction": direction, "geo_factor": _CCY_GEO[ccy]}
    return out


# ╔══════════════════════════════════════════════════════════════════════════════
# ║  RENDER
# ╚══════════════════════════════════════════════════════════════════════════════

def _tension_meta(score: float) -> tuple[str, str, str]:
    """Returns (level_label, hex_color, description)."""
    if score >= 2.0:
        return ("EXTREME RISK-OFF", C["red"],
                "Severe global tensions — strong safe-haven demand")
    if score >= 0.8:
        return ("RISK-OFF", C["yellow"],
                "Elevated geopolitical stress — safe-haven bid active")
    if score >= -0.7:
        return ("NEUTRAL", C["muted"],
                "Moderate backdrop — no strong directional geo bias")
    if score >= -2.0:
        return ("RISK-ON", C["teal"],
                "Calm conditions — risk appetite broadly supported")
    return ("EXTREME RISK-ON", C["green"],
            "De-escalation / stable conditions — full risk-on")


def render_risk_gauge(tension: float) -> str:
    level, lcolor, desc = _tension_meta(tension)
    pct       = (tension + 3.0) / 6.0 * 100.0
    right_pct = 100.0 - pct

    return f"""
<div style="background:{C['card']};border:1px solid {C['border']};border-radius:12px;
            padding:22px 28px 20px;margin-bottom:20px;">
  <div style="display:flex;justify-content:space-between;align-items:flex-start;
              margin-bottom:16px;">
    <div>
      <div style="font-size:10px;color:{C['muted']};font-family:monospace;
                  letter-spacing:2px;text-transform:uppercase;margin-bottom:5px;">
        Geopolitical Tension Level
      </div>
      <div style="font-size:12px;color:{C['muted']};font-family:sans-serif;">
        {desc}
      </div>
    </div>
    <div style="text-align:right;flex-shrink:0;margin-left:20px;">
      <div style="font-size:30px;font-weight:800;color:{lcolor};
                  font-family:monospace;letter-spacing:-1px;line-height:1;">
        {tension:+.2f}
      </div>
      <div style="font-size:9px;color:{C['muted']};font-family:monospace;margin-top:2px;">
        ± 3.0 scale
      </div>
    </div>
  </div>

  <!-- Gradient bar -->
  <div style="width:100%;height:12px;border-radius:6px;overflow:hidden;
              background:linear-gradient(to right,
                {C['green']} 0%, {C['teal']} 20%,
                {C['muted']} 42%, {C['muted']} 58%,
                {C['yellow']} 80%, {C['red']} 100%);
              margin-bottom:2px;">
  </div>
  <!-- Needle: flex spacers -->
  <div style="display:flex;align-items:stretch;height:10px;margin-bottom:4px;">
    <div style="flex:{pct:.2f};"></div>
    <div style="width:2px;background:rgba(255,255,255,0.85);border-radius:1px;
                margin-top:-6px;height:18px;"></div>
    <div style="flex:{right_pct:.2f};"></div>
  </div>
  <!-- Scale labels -->
  <div style="display:flex;justify-content:space-between;
              font-size:9px;font-family:monospace;letter-spacing:0.5px;">
    <span style="color:{C['green']};">RISK-ON  &minus;3.0</span>
    <span style="color:{C['muted']};">NEUTRAL  0.0</span>
    <span style="color:{C['red']};">+3.0  RISK-OFF</span>
  </div>
  <!-- Status badge -->
  <div style="margin-top:14px;text-align:center;">
    <span style="background:{lcolor};color:{C['bg']};font-family:monospace;
                 font-size:11px;font-weight:700;letter-spacing:2px;
                 padding:5px 22px;border-radius:20px;">
      {level}
    </span>
  </div>
</div>
"""


def render_event_cards(articles: list[dict]) -> str:
    if not articles:
        return (
            f"<div style='background:{C['card']};border:1px solid {C['border']};"
            f"border-radius:12px;padding:32px;text-align:center;"
            f"color:{C['muted']};font-family:monospace;font-size:13px;'>"
            f"No geo events loaded — feedparser unavailable or network error"
            f"</div>"
        )

    cards_html = ""
    for art in articles[:16]:
        cat     = art["category"]
        cc      = _CAT_COLOR.get(cat, C["muted"])
        score   = art["score"]
        dot_col = (C["red"] if score > 0.5
                   else C["green"] if score < -0.5
                   else C["muted"])
        title   = art["title"].replace("<", "&lt;").replace(">", "&gt;")
        source  = art["source"].replace("<", "&lt;").replace(">", "&gt;")
        pub     = art["published"]

        cards_html += (
            f"<div style='background:{C['panel']};border:1px solid {C['border']};"
            f"border-radius:8px;padding:12px 14px;margin-bottom:8px;'>"
            f"<div style='display:flex;justify-content:space-between;"
            f"align-items:flex-start;margin-bottom:6px;'>"
            f"<span style='background:{cc};color:{C['bg']};font-family:monospace;"
            f"font-size:9px;font-weight:700;letter-spacing:1px;padding:2px 8px;"
            f"border-radius:10px;text-transform:uppercase;flex-shrink:0;'>{cat}</span>"
            f"<span style='width:8px;height:8px;border-radius:50%;background:{dot_col};"
            f"display:inline-block;flex-shrink:0;margin-top:2px;margin-left:8px;'>"
            f"</span></div>"
            f"<div style='font-size:12px;color:{C['text']};font-family:sans-serif;"
            f"line-height:1.5;margin-bottom:6px;'>{title}</div>"
            f"<div style='font-size:10px;color:{C['muted']};font-family:monospace;'>"
            f"{source} &middot; {pub}</div>"
            f"</div>"
        )

    return (
        f"<div style='background:{C['card']};border:1px solid {C['border']};"
        f"border-radius:12px;padding:18px 18px 14px;'>"
        f"<div style='font-size:10px;color:{C['muted']};font-family:monospace;"
        f"letter-spacing:2px;text-transform:uppercase;margin-bottom:14px;'>"
        f"Live Geo Events &nbsp;({len(articles)} items)</div>"
        f"<div style='max-height:580px;overflow-y:auto;padding-right:4px;'>"
        f"{cards_html}"
        f"</div></div>"
    )


def render_safehaven_panel(impacts: dict[str, dict], tension: float) -> str:
    sh_scores = [impacts[c]["score"] for c in ["CHF", "JPY", "USD"]]
    avg_sh    = sum(sh_scores) / 3.0

    if avg_sh >= 0.5:
        flow_col  = C["red"]
        flow_text = "&#9679; Capital flowing INTO safe-havens"
    elif avg_sh <= -0.5:
        flow_col  = C["green"]
        flow_text = "&#9679; Safe-haven outflow — risk-on bid"
    else:
        flow_col  = C["muted"]
        flow_text = "&#9679; Safe-haven flows neutral"

    def _cell(ccy: str) -> str:
        d = impacts[ccy]
        return (
            f"<div style='background:{C['panel']};border:1px solid {C['border']};"
            f"border-radius:8px;padding:12px 8px;text-align:center;flex:1;'>"
            f"<div style='font-size:20px;'>{CURRENCY_FLAG[ccy]}</div>"
            f"<div style='font-size:12px;font-weight:700;color:{C['text']};"
            f"font-family:monospace;margin:4px 0 2px;'>{ccy}</div>"
            f"<div style='font-size:22px;font-weight:800;color:{d['color']};"
            f"font-family:monospace;line-height:1;'>{d['direction']}</div>"
            f"<div style='font-size:10px;color:{d['color']};font-family:monospace;"
            f"margin-top:3px;'>{d['score']:+.1f}</div>"
            f"</div>"
        )

    sh_cells   = "".join(_cell(c) for c in ["CHF", "JPY", "USD"])
    risk_cells = "".join(_cell(c) for c in ["AUD", "NZD", "CAD"])

    return (
        f"<div style='background:{C['card']};border:1px solid {C['border']};"
        f"border-radius:12px;padding:18px 18px 16px;margin-bottom:14px;'>"
        f"<div style='display:flex;justify-content:space-between;align-items:center;"
        f"margin-bottom:12px;'>"
        f"<div style='font-size:10px;color:{C['muted']};font-family:monospace;"
        f"letter-spacing:2px;text-transform:uppercase;'>Safe-Haven Flow</div>"
        f"<div style='font-size:10px;font-family:monospace;color:{flow_col};'>"
        f"{flow_text}</div></div>"
        f"<div style='display:flex;gap:8px;margin-bottom:14px;'>{sh_cells}</div>"
        f"<div style='font-size:10px;color:{C['muted']};font-family:monospace;"
        f"letter-spacing:1px;text-transform:uppercase;margin-bottom:8px;'>"
        f"Risk-Correlated</div>"
        f"<div style='display:flex;gap:8px;'>{risk_cells}</div>"
        f"</div>"
    )


def render_ccy_impact_table(impacts: dict[str, dict]) -> str:
    rows = ""
    for i, ccy in enumerate(CURRENCIES):
        d      = impacts[ccy]
        bg     = C["dim"] if i % 2 == 0 else "transparent"
        barpct = abs(d["score"]) / 3.0 * 100.0

        rows += (
            f"<tr style='background:{bg};'>"
            f"<td style='padding:9px 10px;font-family:monospace;font-size:12px;"
            f"color:{C['text']};white-space:nowrap;'>"
            f"{CURRENCY_FLAG[ccy]} {ccy}</td>"
            f"<td style='padding:9px 10px;font-family:monospace;font-size:20px;"
            f"color:{d['color']};text-align:center;width:28px;'>{d['direction']}</td>"
            f"<td style='padding:9px 10px;width:80px;'>"
            f"<div style='background:{C['border']};border-radius:3px;height:6px;"
            f"overflow:hidden;'>"
            f"<div style='width:{barpct:.1f}%;height:100%;background:{d['color']};"
            f"border-radius:3px;'></div></div></td>"
            f"<td style='padding:9px 10px;font-family:monospace;font-size:10px;"
            f"color:{d['color']};text-align:right;white-space:nowrap;'>{d['label']}</td>"
            f"<td style='padding:9px 10px;font-family:monospace;font-size:11px;"
            f"color:{C['muted']};text-align:right;'>{d['score']:+.2f}</td>"
            f"</tr>"
        )

    header = (
        f"<tr>"
        f"<th style='padding:6px 10px;font-family:monospace;font-size:9px;"
        f"color:{C['muted']};text-align:left;letter-spacing:1px;"
        f"border-bottom:1px solid {C['border']};'>CCY</th>"
        f"<th style='padding:6px 10px;font-family:monospace;font-size:9px;"
        f"color:{C['muted']};text-align:center;letter-spacing:1px;"
        f"border-bottom:1px solid {C['border']};'>DIR</th>"
        f"<th style='padding:6px 10px;font-family:monospace;font-size:9px;"
        f"color:{C['muted']};letter-spacing:1px;"
        f"border-bottom:1px solid {C['border']};'>STRENGTH</th>"
        f"<th style='padding:6px 10px;font-family:monospace;font-size:9px;"
        f"color:{C['muted']};text-align:right;letter-spacing:1px;"
        f"border-bottom:1px solid {C['border']};'>SIGNAL</th>"
        f"<th style='padding:6px 10px;font-family:monospace;font-size:9px;"
        f"color:{C['muted']};text-align:right;letter-spacing:1px;"
        f"border-bottom:1px solid {C['border']};'>SCORE</th>"
        f"</tr>"
    )

    return (
        f"<div style='background:{C['card']};border:1px solid {C['border']};"
        f"border-radius:12px;padding:18px 18px 14px;'>"
        f"<div style='font-size:10px;color:{C['muted']};font-family:monospace;"
        f"letter-spacing:2px;text-transform:uppercase;margin-bottom:12px;'>"
        f"Currency Geo Impact</div>"
        f"<table style='width:100%;border-collapse:collapse;'>"
        f"<thead>{header}</thead>"
        f"<tbody>{rows}</tbody>"
        f"</table></div>"
    )


# ╔══════════════════════════════════════════════════════════════════════════════
# ║  ENTRY POINT
# ╚══════════════════════════════════════════════════════════════════════════════

def main():
    st.set_page_config(
        page_title="Geopolitical Dashboard · Trading Terminal",
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
          border:none !important; font-weight:700 !important;
          font-family:monospace !important;
      }}
      p, span, label {{ color:{C['text']}; }}
      div[data-testid="stSpinner"] p {{
          color:{C['muted']} !important; font-family:monospace !important;
          font-size:12px !important;
      }}
      div[data-testid="stHorizontalBlock"] {{ align-items:stretch !important; }}
      div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] {{
          display:flex !important; flex-direction:column !important;
      }}
    </style>
    """, unsafe_allow_html=True)

    # ── Session state / auto-refresh ───────────────────────────────────────────
    _now = time.time()
    if "geo_last_refresh" not in st.session_state:
        st.session_state.geo_last_refresh = _now

    if _now - st.session_state.geo_last_refresh > TTL_GEO:
        fetch_geo_news.clear()
        st.session_state.geo_last_refresh = _now
        st.rerun()

    # ── Title row ──────────────────────────────────────────────────────────────
    col_back, col_title, col_right = st.columns([2, 5, 2])
    with col_back:
        if st.button("← Back to Hub"):
            st.switch_page("app.py")
    with col_title:
        st.markdown(
            f"<div style='text-align:center;'>"
            f"<div style='font-size:20px;font-weight:800;color:{C['text']};"
            f"font-family:monospace;letter-spacing:-0.5px;'>"
            f"GEOPOLITICAL DASHBOARD</div>"
            f"<div style='font-size:11px;color:{C['muted']};font-family:monospace;"
            f"letter-spacing:1px;margin-top:3px;'>"
            f"Geo Risk &middot; Conflict Tracker &middot; Safe-Haven Flow &middot; "
            f"FX Impact</div></div>",
            unsafe_allow_html=True,
        )
    with col_right:
        _, btn_col = st.columns([1, 1])
        with btn_col:
            if st.button("🔄 Refresh", key="geo_refresh"):
                fetch_geo_news.clear()
                st.session_state.geo_last_refresh = time.time()
                st.rerun()

    st.markdown("<div style='margin-bottom:12px;'></div>", unsafe_allow_html=True)

    # ── Data fetch ─────────────────────────────────────────────────────────────
    if not _FEEDPARSER:
        st.warning("feedparser not installed — run: pip install feedparser")
        articles = []
    else:
        with st.spinner("Scanning geopolitical news sources..."):
            articles = fetch_geo_news()

    tension = calc_tension_score(articles)
    impacts = calc_ccy_impacts(tension)

    # ── Risk gauge ─────────────────────────────────────────────────────────────
    st.markdown(render_risk_gauge(tension), unsafe_allow_html=True)

    # ── Two-column layout ──────────────────────────────────────────────────────
    col_l, col_r = st.columns([3, 2], gap="large")

    with col_l:
        st.markdown(render_event_cards(articles), unsafe_allow_html=True)

    with col_r:
        st.markdown(render_safehaven_panel(impacts, tension), unsafe_allow_html=True)
        st.markdown(render_ccy_impact_table(impacts), unsafe_allow_html=True)

    # ── Footer ─────────────────────────────────────────────────────────────────
    st.markdown(
        f"<div style='margin-top:48px;padding-top:16px;"
        f"border-top:1px solid {C['border']};text-align:center;"
        f"font-size:11px;color:{C['muted']};font-family:monospace;'>"
        f"Built by @realedgetraders"
        f"</div>",
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
