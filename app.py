"""
Trading Analytics Terminal — Home
"""

import streamlit as st

C = {
    "bg":     "#0a0f1e",
    "card":   "#0d1526",
    "border": "#1a2540",
    "panel":  "#0f1a2e",
    "dim":    "#192038",
    "text":   "#dde4f0",
    "muted":  "#445066",
    "teal":   "#45c4b0",
    "blue":   "#4f8ef7",
    "green":  "#00c48c",
    "red":    "#f05262",
    "yellow": "#f0b429",
}

MODULES = [
    {
        "title":    "Seasonality",
        "icon":     "📈",
        "desc":     "Decode recurring price patterns across 25 years — custom windows, win rates, Sharpe, and a full radar of the strongest seasonal setups.",
        "active":   True,
        "page":     "pages/1_Seasonality.py",
    },
    {
        "title":    "COT Analysis",
        "icon":     "📊",
        "desc":     "CFTC Commitments of Traders — net positioning, COT Index, and extreme signals across Forex, Commodities, Indices, and Bonds.",
        "active":   True,
        "page":     "pages/2_COT_Analysis.py",
    },
    {
        "title":    "Economic Bias Engine",
        "icon":     "🗓️",
        "desc":     "Currency bias scanner — economic indicators scored into a 4-dimensional directional bias with event calendar.",
        "active":   True,
        "page":     "pages/3_Macro_Dashboard.py",
    },
    {
        "title":    "Geopolitics & News",
        "icon":     "🌍",
        "desc":     "Live news dashboard — geopolitical events (conflicts, sanctions, political crises) plus financial market news per currency.",
        "active":   True,
        "page":     "pages/4_Geopolitics.py",
    },
    {
        "title":    "Market Regime",
        "icon":     "⚡",
        "desc":     "VIX-based market regime detection — current volatility percentile rank vs. 6-month history with trading implications.",
        "active":   True,
        "page":     "pages/5_Market_Regime.py",
    },
    {
        "title":    "???",
        "icon":     "🔒",
        "desc":     "Something is being built here. Details classified — check back soon.",
        "active":   False,
        "teaser":   True,
        "page":     None,
    },
    {
        "title":    "Correlation",
        "icon":     "🔗",
        "desc":     "Cross-asset correlation matrix and rolling correlation heatmaps.",
        "active":   False,
        "page":     None,
    },
    {
        "title":    "Backtester",
        "icon":     "🧪",
        "desc":     "Strategy backtesting engine with walk-forward validation and drawdown metrics.",
        "active":   False,
        "page":     None,
    },
    {
        "title":    "Portfolio",
        "icon":     "💼",
        "desc":     "Multi-asset portfolio analytics, correlation-adjusted sizing, and risk attribution.",
        "active":   False,
        "page":     None,
    },
]


def main():
    st.set_page_config(
        page_title="Trading Analytics Terminal",
        page_icon="📊",
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
      .stMainBlockContainer {{ padding-top:4rem !important; }}
      button[kind="primary"], button[kind="secondary"] {{
          background:{C['teal']} !important;
          color:#0a0c10 !important;
          border:none !important;
          font-weight:700 !important;
          font-family:monospace !important;
      }}
      p, span, label {{ color:{C['text']}; }}
    </style>
    """, unsafe_allow_html=True)

    # ── Header ────────────────────────────────────────────────────────────────
    st.markdown(
        f"""
        <div style="text-align:center;margin-bottom:48px;">
          <div style="font-size:11px;color:{C['teal']};font-family:monospace;
                      letter-spacing:3px;text-transform:uppercase;margin-bottom:12px;">
            Professional Multi-Module Analysis Suite
          </div>
          <div style="font-size:36px;font-weight:800;color:{C['text']};
                      font-family:monospace;letter-spacing:-1px;line-height:1.1;">
            Trading Analytics Terminal
          </div>
          <div style="width:48px;height:2px;background:{C['teal']};
                      margin:16px auto 0;border-radius:1px;"></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Module card grid — active + teaser modules ───────────────────────────
    visible_modules = [m for m in MODULES if m["active"] or m.get("teaser")]
    for row_start in range(0, len(visible_modules), 2):
        col_l, col_r = st.columns(2, gap="medium")
        for col, mod in zip([col_l, col_r], visible_modules[row_start:row_start + 2]):
            _render_module_card(col, mod)

    # ── Footer ────────────────────────────────────────────────────────────────
    st.markdown(
        f"<div style='margin-top:48px;padding-top:16px;"
        f"border-top:1px solid {C['border']};text-align:center;"
        f"font-size:11px;color:{C['muted']};font-family:monospace;'>"
        f"Built by @realedgetraders"
        f"</div>",
        unsafe_allow_html=True,
    )


def _render_module_card(col, mod: dict):
    active = mod["active"]
    teaser = mod.get("teaser", False)

    if teaser:
        border      = "#1e2d4a"
        title_color = "#2e4060"
        desc_color  = "#243350"
        badge_bg    = "#111827"
        badge_color = "#2e4060"
        badge_text  = "Coming Soon"
        border_style = "dashed"
    elif active:
        border      = C["teal"]
        title_color = C["text"]
        desc_color  = C["muted"]
        badge_bg    = C["teal"]
        badge_color = C["bg"]
        badge_text  = "Live"
        border_style = "solid"
    else:
        border      = C["border"]
        title_color = C["muted"]
        desc_color  = C["muted"]
        badge_bg    = C["dim"]
        badge_color = C["muted"]
        badge_text  = "Coming Soon"
        border_style = "solid"

    with col:
        st.markdown(
            f"""
            <div style="background:{C['card']};border:1px {border_style} {border};
                        border-radius:12px;padding:24px 24px 20px;margin-bottom:16px;
                        min-height:140px;{'opacity:0.55;' if teaser else ''}">
              <div style="display:flex;align-items:flex-start;justify-content:space-between;
                          margin-bottom:10px;">
                <div style="display:flex;align-items:center;gap:10px;">
                  <span style="font-size:22px;{'filter:grayscale(1);' if teaser else ''}">{mod['icon']}</span>
                  <span style="font-size:15px;font-weight:700;color:{title_color};
                               font-family:monospace;letter-spacing:2px;">{mod['title']}</span>
                </div>
                <span style="background:{badge_bg};color:{badge_color};
                             font-size:9px;font-family:monospace;font-weight:700;
                             letter-spacing:1px;padding:2px 8px;border-radius:4px;
                             text-transform:uppercase;border:1px solid {border};">{badge_text}</span>
              </div>
              <div style="font-size:12px;color:{desc_color};line-height:1.6;
                          font-family:sans-serif;{'font-style:italic;' if teaser else ''}">{mod['desc']}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if active and mod["page"]:
            if st.button(f"Open {mod['title']}", key=f"open_{mod['title']}"):
                st.switch_page(mod["page"])


if __name__ == "__main__":
    main()
