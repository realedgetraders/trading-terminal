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
        "desc":     "Seasonax-style seasonal trend analysis with pattern windows and year-by-year breakdown.",
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
        "title":    "Macro Fundamentals",
        "icon":     "🗓️",
        "desc":     "Currency macro scanner — economic indicators, event calendar, and live news feed per currency.",
        "active":   True,
        "page":     "pages/3_Macro_Dashboard.py",
    },
    {
        "title":    "Geopolitics",
        "icon":     "🌍",
        "desc":     "Live geo-risk tracker — active conflicts, sanctions, political crises and their impact on safe-haven currencies and FX markets.",
        "active":   True,
        "page":     "pages/4_Geopolitics.py",
    },
    {
        "title":    "Volatility",
        "icon":     "⚡",
        "desc":     "Historical vs. implied volatility, ATR regimes, and vol surface analysis.",
        "active":   False,
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

    # ── Module card grid (2 columns × 3 rows) ─────────────────────────────────
    for row_start in range(0, len(MODULES), 2):
        col_l, col_r = st.columns(2, gap="medium")
        for col, mod in zip([col_l, col_r], MODULES[row_start:row_start + 2]):
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
    border = C["teal"] if active else C["border"]
    title_color = C["text"] if active else C["muted"]
    desc_color  = C["muted"]
    badge_bg    = C["teal"] if active else C["dim"]
    badge_color = C["bg"] if active else C["muted"]
    badge_text  = "Live" if active else "Coming Soon"

    with col:
        st.markdown(
            f"""
            <div style="background:{C['card']};border:1px solid {border};
                        border-radius:12px;padding:24px 24px 20px;margin-bottom:16px;
                        min-height:140px;">
              <div style="display:flex;align-items:flex-start;justify-content:space-between;
                          margin-bottom:10px;">
                <div style="display:flex;align-items:center;gap:10px;">
                  <span style="font-size:22px;">{mod['icon']}</span>
                  <span style="font-size:15px;font-weight:700;color:{title_color};
                               font-family:monospace;">{mod['title']}</span>
                </div>
                <span style="background:{badge_bg};color:{badge_color};
                             font-size:9px;font-family:monospace;font-weight:700;
                             letter-spacing:1px;padding:2px 8px;border-radius:4px;
                             text-transform:uppercase;">{badge_text}</span>
              </div>
              <div style="font-size:12px;color:{desc_color};line-height:1.6;
                          font-family:sans-serif;">{mod['desc']}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if active and mod["page"]:
            if st.button(f"Open {mod['title']}", key=f"open_{mod['title']}"):
                st.switch_page(mod["page"])


if __name__ == "__main__":
    main()
