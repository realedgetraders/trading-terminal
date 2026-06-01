"""
Trading Analytics Terminal — Home
"""

import streamlit as st

C = {
    "bg":     "#0d0d0d",
    "card":   "#141414",
    "border": "#252525",
    "panel":  "#111111",
    "dim":    "#171717",
    "text":   "#e8e8e8",
    "muted":  "#666666",
    "teal":   "#4f8ef7",
    "blue":   "#4f8ef7",
    "green":  "#1a9b6a",
    "red":    "#f05262",
    "yellow": "#f0b429",
}

MODULES = [
    {
        "title":    "Seasonality",
        "icon":     "📈",
        "desc":     "Decode recurring price patterns across 25 years — custom windows, win rates, and a seasonality scanner that surfaces the strongest upcoming setups.",
        "active":   True,
        "pro":      True,
        "page":     "pages/1_Seasonality.py",
    },
    {
        "title":    "COT Analysis",
        "icon":     "📊",
        "desc":     "CFTC Commitments of Traders — net positioning, COT Index, and a COT scanner that surfaces the strongest positioning extremes across markets.",
        "active":   True,
        "page":     "pages/2_COT_Analysis.py",
    },
    {
        "title":    "Economic Bias Engine",
        "icon":     "🗓️",
        "desc":     "Aggregates live macroeconomic data across 8 major currencies, scores key indicators by impact, and converts them into a directional bias — geopolitical events can override this signal at any time.",
        "active":   True,
        "pro":      True,
        "maintenance": True,
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
        "title":    "Valuation Tool",
        "icon":     "⚖️",
        "desc":     "Measure any asset against four macro anchors — Precious Metals, USD, Bonds and World Equities — to see whether it is currently under- or overvalued.",
        "active":   True,
        "pro":      True,
        "page":     "pages/7_Valuation.py",
    },
    {
        "title":    "Master Terminal",
        "icon":     "🔬",
        "desc":     "PRO aggregator for any forex pair — COT positioning, seasonal pattern, macro bias, and upcoming events in one unified view.",
        "active":   True,
        "pro":      True,
        "hero":     True,
        "page":     "pages/7_Pair_Intelligence.py",
    },
    {
        "title":    "Market Phase Scanner",
        "icon":     "⚡",
        "desc":     "Volatility index that shows which market phase we are currently in — highly volatile, elevated, calm, or compressed — so you know what kind of market you are trading.",
        "active":   True,
        "page":     "pages/5_Market_Regime.py",
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

# Journal module entry — used in the Journal section view
JOURNAL_MODULE = {
    "title":  "Edge Journal",
    "icon":   "📓",
    "desc":   "Log every trade, track your edge over time, and let the data show where you actually make money. Authentication required.",
    "active": True,
    "pro":    True,
    "page":   "pages/6_Journal.py",
}


def main():
    st.set_page_config(
        page_title="Real Edge",
        page_icon="📊",
        layout="wide",
        initial_sidebar_state="collapsed",
    )

    # ── Session state ──────────────────────────────────────────────────────────
    if "section" not in st.session_state:
        st.session_state.section = None
    section = st.session_state.section

    # Sidebar switch button colour: amber when in analysis, teal when in journal
    sb_color = C["yellow"] if section == "analysis" else C["teal"]

    # Teal button style only needed in section views (module-card buttons).
    # On the landing page (section=None) the CTA buttons get their own colours below.
    _btn_hover_color = C["yellow"] if section == "journal" else C["teal"]
    _btn_hover_rgba  = "rgba(240,180,41,0.14)" if section == "journal" else "rgba(79,142,247,0.14)"
    _section_btn_css = f"""
      button[kind="primary"], button[kind="secondary"] {{
          background: #161616 !important;
          color: {C['text']} !important;
          border: 1px solid #2e2e2e !important;
          font-weight: 600 !important;
          font-family: monospace !important;
          transition: border-color 0.22s ease, color 0.22s ease, box-shadow 0.22s ease !important;
      }}
      button[kind="primary"]:hover, button[kind="secondary"]:hover {{
          border-color: {_btn_hover_color}70 !important;
          color: {_btn_hover_color} !important;
          box-shadow: 0 0 12px {_btn_hover_rgba} !important;
      }}
""" if section is not None else ""

    # ── Global styles ──────────────────────────────────────────────────────────
    st.markdown(f"""
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:ital,wght@0,400;0,500;0,600;0,700;0,800;1,400&display=swap');
      *{{-webkit-font-smoothing:antialiased;-moz-osx-font-smoothing:grayscale;}}
      [style*="font-family:monospace"],[style*="font-family: monospace"]{{font-family:'JetBrains Mono',monospace !important;}}
      [style*="font-family:sans-serif"],[style*="font-family: sans-serif"]{{font-family:'Inter',sans-serif !important;}}
      button{{font-family:'JetBrains Mono',monospace !important;}}
      html, body, [data-testid="stAppViewContainer"],
      [data-testid="stHeader"], [data-testid="stToolbar"],
      [data-testid="stDecoration"] {{
          background: radial-gradient(ellipse at 50% 50%, #0d0d0d 60%, #08090f 100%) !important;
      }}
      .stMainBlockContainer {{ padding-top:4rem !important; }}
      {_section_btn_css}
      p, span, label {{ color:{C['text']}; }}
      /* ── Clickable card overlay ───────────────────────────────────── */
      .ret-module-active {{
          cursor: pointer;
          transition: box-shadow 0.25s ease, border-color 0.25s ease;
      }}
      /* Overlay button is on top (z-index 10) so .ret-module-active never gets :hover.
         Detect hover on the overlay container instead and reach back to the card. */
      div[data-testid="stElementContainer"]:has(.ret-module-active):has(+ div[data-testid="stElementContainer"]:hover) .ret-module-active:not(.ret-module-pro) {{
          box-shadow:
              0 0 0 1px rgba(79,142,247,0.4),
              0 0 16px rgba(79,142,247,0.18),
              0 0 36px rgba(79,142,247,0.07) !important;
          border-color: rgba(79,142,247,0.6) !important;
      }}
      div[data-testid="stElementContainer"]:has(.ret-module-active):has(+ div[data-testid="stElementContainer"]:hover) .ret-module-active.ret-module-pro {{
          box-shadow:
              0 0 0 1px rgba(240,180,41,0.45),
              0 0 16px rgba(240,180,41,0.22),
              0 0 36px rgba(240,180,41,0.08) !important;
          border-color: rgba(240,180,41,0.85) !important;
      }}
      /* Pull the invisible nav-button container up over the card */
      div[data-testid="stElementContainer"]:has(.ret-module-active) {{
          position: relative;
          z-index: 1;
      }}
      div[data-testid="stElementContainer"]:has(.ret-module-active)
        + div[data-testid="stElementContainer"] {{
          margin-top: -176px;
          margin-bottom: 20px;
          height: 160px;
          position: relative;
          z-index: 10;
      }}
      div[data-testid="stElementContainer"]:has(.ret-module-active)
        + div[data-testid="stElementContainer"] button {{
          width: 100% !important;
          height: 160px !important;
          min-height: 0 !important;
          opacity: 0 !important;
          cursor: pointer !important;
          border-radius: 12px !important;
          padding: 0 !important;
          margin: 0 !important;
          display: block !important;
      }}
      /* ── Hero banner clickable overlay (full-width premium flagship) ── */
      .ret-module-hero {{
          cursor: pointer;
          transition: box-shadow 0.25s ease, border-color 0.25s ease;
      }}
      div[data-testid="stElementContainer"]:has(.ret-module-hero):has(+ div[data-testid="stElementContainer"]:hover) .ret-module-hero {{
          box-shadow:
              0 0 0 1px rgba(120,120,120,0.32),
              0 0 18px rgba(120,120,120,0.12) !important;
          border-color: rgba(120,120,120,0.55) !important;
      }}
      div[data-testid="stElementContainer"]:has(.ret-module-hero) {{
          position: relative;
          z-index: 1;
      }}
      div[data-testid="stElementContainer"]:has(.ret-module-hero)
        + div[data-testid="stElementContainer"] {{
          margin-top: -220px;
          margin-bottom: 20px;
          height: 220px;
          position: relative;
          z-index: 10;
      }}
      div[data-testid="stElementContainer"]:has(.ret-module-hero)
        + div[data-testid="stElementContainer"] button {{
          width: 100% !important;
          height: 220px !important;
          min-height: 0 !important;
          opacity: 0 !important;
          cursor: pointer !important;
          border-radius: 14px !important;
          padding: 0 !important;
          margin: 0 !important;
          display: block !important;
      }}
      /* ── WIP module clickable overlay (muted grey, no accent glow) ──── */
      .ret-module-wip {{
          cursor: pointer;
          transition: box-shadow 0.25s ease, border-color 0.25s ease;
      }}
      div[data-testid="stElementContainer"]:has(.ret-module-wip):has(+ div[data-testid="stElementContainer"]:hover) .ret-module-wip {{
          box-shadow:
              0 0 0 1px rgba(120,120,120,0.30),
              0 0 14px rgba(120,120,120,0.10) !important;
          border-color: rgba(120,120,120,0.50) !important;
      }}
      div[data-testid="stElementContainer"]:has(.ret-module-wip) {{
          position: relative;
          z-index: 1;
      }}
      div[data-testid="stElementContainer"]:has(.ret-module-wip)
        + div[data-testid="stElementContainer"] {{
          margin-top: -176px;
          margin-bottom: 20px;
          height: 160px;
          position: relative;
          z-index: 10;
      }}
      div[data-testid="stElementContainer"]:has(.ret-module-wip)
        + div[data-testid="stElementContainer"] button {{
          width: 100% !important;
          height: 160px !important;
          min-height: 0 !important;
          opacity: 0 !important;
          cursor: pointer !important;
          border-radius: 12px !important;
          padding: 0 !important;
          margin: 0 !important;
          display: block !important;
      }}
      /* ── Landing card clickable overlay ─────────────────────────────── */
      .ret-landing-analysis, .ret-landing-journal {{
          cursor: pointer;
          transition: box-shadow 0.25s ease, border-color 0.25s ease, background 0.25s ease;
      }}
      div[data-testid="stElementContainer"]:has(.ret-landing-analysis):has(+ div[data-testid="stElementContainer"]:hover) .ret-landing-analysis {{
          box-shadow: inset 0 0 60px rgba(0,0,0,0.3), 0 0 24px rgba(79,142,247,0.45), 0 0 48px rgba(79,142,247,0.2) !important;
          border-color: #4f8ef7 !important;
          background: linear-gradient(170deg, #1a2030 0%, #151c28 60%, #121520 100%) !important;
      }}
      div[data-testid="stElementContainer"]:has(.ret-landing-journal):has(+ div[data-testid="stElementContainer"]:hover) .ret-landing-journal {{
          box-shadow: inset 0 0 60px rgba(0,0,0,0.3), 0 0 24px rgba(240,165,0,0.55), 0 0 48px rgba(240,165,0,0.25) !important;
          border-color: #f0b429 !important;
          background: linear-gradient(170deg, #252520 0%, #1e1e1a 60%, #1b1b17 100%) !important;
      }}
      div[data-testid="stElementContainer"]:has(.ret-landing-analysis),
      div[data-testid="stElementContainer"]:has(.ret-landing-journal) {{
          position: relative; z-index: 1;
      }}
      div[data-testid="stElementContainer"]:has(.ret-landing-analysis) + div[data-testid="stElementContainer"],
      div[data-testid="stElementContainer"]:has(.ret-landing-journal)  + div[data-testid="stElementContainer"] {{
          margin-top: -356px;
          margin-bottom: 0;
          height: 340px;
          position: relative;
          z-index: 10;
      }}
      div[data-testid="stElementContainer"]:has(.ret-landing-analysis) + div[data-testid="stElementContainer"] button,
      div[data-testid="stElementContainer"]:has(.ret-landing-journal)  + div[data-testid="stElementContainer"] button {{
          width: 100% !important; height: 340px !important;
          min-height: 0 !important; opacity: 0 !important;
          cursor: pointer !important; border-radius: 16px !important;
          padding: 0 !important; margin: 0 !important; display: block !important;
      }}
      /* ── Sidebar switch button ─────────────────────────────────────── */
      section[data-testid="stSidebar"] button {{
          background: transparent !important;
          color: {sb_color} !important;
          border: 1px solid {sb_color}55 !important;
          font-family: monospace !important;
          font-weight: 700 !important;
          font-size: 12px !important;
          border-radius: 8px !important;
          margin-bottom: 4px !important;
      }}
      section[data-testid="stSidebar"] button:hover {{
          background: {sb_color}18 !important;
          border-color: {sb_color} !important;
          color: {sb_color} !important;
      }}
      /* ── Sidebar section labels ────────────────────────────────────── */
      [data-testid="stSidebarNavItems"] li:nth-child(2)::before {{
          content: "ANALYSIS";
          display: block;
          font-family: monospace;
          font-size: 9px;
          letter-spacing: 2px;
          color: {C['teal']};
          padding: 10px 0 4px;
          border-top: 1px solid {C['border']};
          margin-top: 4px;
      }}
      [data-testid="stSidebarNavItems"] li:last-child::before {{
          content: "JOURNAL";
          display: block;
          font-family: monospace;
          font-size: 9px;
          letter-spacing: 2px;
          color: #f0b429;
          padding: 10px 0 4px;
          border-top: 1px solid {C['border']};
          margin-top: 4px;
      }}
    </style>
    """, unsafe_allow_html=True)

    # ── Sidebar switch button ──────────────────────────────────────────────────
    with st.sidebar:
        if section == "analysis":
            if st.button("→ Switch to Journal", key="sw_journal"):
                st.session_state.section = "journal"
                st.rerun()
        elif section == "journal":
            if st.button("→ Switch to Terminal", key="sw_terminal"):
                st.session_state.section = "analysis"
                st.rerun()
        # On landing (section=None): no switch button shown

    # ── Header ─────────────────────────────────────────────────────────────────
    if section is None:
        # Landing: single clean headline — EdgeLab appears exactly once
        st.markdown(
            f"""
            <div style="text-align:center;margin-bottom:44px;">
              <div style="font-size:34px;font-weight:800;color:{C['text']};
                          font-family:monospace;letter-spacing:-0.5px;line-height:1.1;
                          margin-bottom:16px;">
                Welcome to EdgeLab
              </div>
              <div style="width:56px;height:2px;background:#c8c8c8;
                          margin:0 auto;border-radius:1px;
                          box-shadow:0 0 8px rgba(255,255,255,0.55),0 0 18px rgba(255,255,255,0.25);"></div>
              <div style="font-size:11px;color:#888888;font-family:monospace;
                          letter-spacing:2px;text-transform:uppercase;margin-top:16px;">
                A Place Where Traders Build Their Edge
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        # Analysis / Journal sub-sections: keep branded EdgeLab title
        subtitle      = (f"<span style='color:{C['teal']}'>▸ Analysis Suite</span>"
                         if section == "analysis"
                         else f"<span style='color:{C['yellow']}'>▸ Journal Suite</span>")
        divider_color = C["teal"] if section == "analysis" else C["yellow"]
        st.markdown(
            f"""
            <div style="text-align:center;margin-bottom:32px;">
              <div style="font-size:11px;color:{divider_color};font-family:monospace;
                          letter-spacing:2px;text-transform:uppercase;margin-bottom:14px;">
                {subtitle}
              </div>
              <div style="font-size:40px;font-weight:800;color:{C['text']};
                          font-family:monospace;letter-spacing:-1px;line-height:1.1;
                          text-shadow:0 0 60px rgba(79,142,247,0.12),0 0 120px rgba(79,142,247,0.06);">
                {'Real Edge Terminal' if section == 'analysis' else 'Edge Journal'}
              </div>
              <div style="width:56px;height:3px;background:{divider_color};
                          margin:16px auto 0;border-radius:2px;
                          box-shadow:0 0 10px {divider_color},0 0 22px {divider_color}80;"></div>
              {'<div style="font-size:11px;color:#666666;font-family:monospace;letter-spacing:1px;margin-top:14px;">A Place Where Traders Analyze Their Assets</div>' if section == 'analysis' else '<div style="font-size:11px;color:#666666;font-family:monospace;letter-spacing:1px;margin-top:14px;">A Place Where Traders Journal and Improve Their Performance</div>'}
            </div>
            """,
            unsafe_allow_html=True,
        )

    # Landing-specific: dark grey / red-border buttons, red fill on hover
    if section is None:
        st.markdown("""
        <style>
          /* nth-child(2) = Analysis col, nth-child(3) = Journal col
             (col 1 and 4 are empty 0.12 padding columns) */
          [data-testid="stHorizontalBlock"] [data-testid="stColumn"]:nth-child(2) button {
              background: transparent !important;
              color: #666666 !important;
              border: 1.5px solid #4f8ef740 !important;
              font-weight: 700 !important;
              font-family: monospace !important;
              transition: color 0.25s ease, border-color 0.25s ease, box-shadow 0.25s ease !important;
          }
          [data-testid="stHorizontalBlock"] [data-testid="stColumn"]:nth-child(2) button:hover {
              color: #ffffff !important;
              border-color: #4f8ef7 !important;
              box-shadow: 0 0 18px rgba(79,142,247,0.45), 0 0 36px rgba(79,142,247,0.18) !important;
          }
          [data-testid="stHorizontalBlock"] [data-testid="stColumn"]:nth-child(3) button {
              background: transparent !important;
              color: #666666 !important;
              border: 1.5px solid #f0b42940 !important;
              font-weight: 700 !important;
              font-family: monospace !important;
              transition: color 0.25s ease, border-color 0.25s ease, box-shadow 0.25s ease !important;
          }
          [data-testid="stHorizontalBlock"] [data-testid="stColumn"]:nth-child(3) button:hover {
              color: #f0b429 !important;
              border-color: #f0b429 !important;
              box-shadow: 0 0 18px rgba(240,180,41,0.55), 0 0 36px rgba(240,180,41,0.2) !important;
          }
        </style>
        """, unsafe_allow_html=True)

    # Back to Hub button — shown when inside a section
    if section is not None:
        _, back_col, _ = st.columns([3, 1, 3])
        with back_col:
            if st.button("← Back to Hub", key="back_hub", use_container_width=True):
                st.session_state.section = None
                st.rerun()
        st.markdown("<div style='height:20px;'></div>", unsafe_allow_html=True)

    # ── Content routing ────────────────────────────────────────────────────────
    if section is None:
        _render_landing()
    elif section == "analysis":
        _render_analysis()
    else:
        _render_journal_section()

    # ── Footer ─────────────────────────────────────────────────────────────────
    st.markdown(
        f"<div style='margin-top:52px;padding-top:14px;"
        f"border-top:1px solid #2a2a2a;text-align:center;"
        f"font-size:11px;color:#555555;font-family:monospace;'>"
        f"Built by @realedgetraders"
        f"</div>",
        unsafe_allow_html=True,
    )


# ── Section views ──────────────────────────────────────────────────────────────

def _render_landing():
    """Landing hub — two premium section cards, centered, colour-differentiated.
    Cards are directly clickable via invisible overlay buttons (same technique as module grid).
    """
    _BLUE  = "#4f8ef7"
    _AMBER = "#f0b429"

    _, col_l, col_r, _ = st.columns([0.12, 1, 1, 0.12], gap="large")

    with col_l:
        st.markdown(f"""
<div class="ret-landing-analysis"
     style="background:linear-gradient(170deg, #181e2a 0%, #141820 60%, #111318 100%);
            border:1.5px solid rgba(79,142,247,0.35);
            box-shadow:inset 0 0 80px rgba(0,0,0,0.45),0 0 16px rgba(79,142,247,0.08);
            border-radius:16px;padding:52px 40px 36px;text-align:center;
            height:340px;overflow:hidden;
            display:flex;flex-direction:column;align-items:center;justify-content:center;">
  <div style="font-size:56px;margin-bottom:22px;line-height:1;">📊</div>
  <div style="font-size:22px;font-weight:800;color:#ffffff;
              font-family:monospace;letter-spacing:-0.5px;margin-bottom:7px;">
    Real Edge Terminal
  </div>
  <div style="font-size:9px;color:{_BLUE};font-family:monospace;
              letter-spacing:3px;text-transform:uppercase;margin-bottom:22px;">
    6 Live Modules
  </div>
  <div style="font-size:12px;color:#888888;line-height:2.2;font-family:sans-serif;">
    Seasonality &nbsp;·&nbsp; COT Analysis &nbsp;·&nbsp; Macro Bias
    <br>Geopolitics &nbsp;·&nbsp; Market Phase Scanner &nbsp;·&nbsp; Pair Intelligence
  </div>
</div>
        """, unsafe_allow_html=True)
        if st.button(" ", key="land_analysis", use_container_width=True):
            st.session_state.section = "analysis"
            st.rerun()

    with col_r:
        st.markdown(f"""
<div class="ret-landing-journal"
     style="background:linear-gradient(170deg, #212120 0%, #1a1a18 60%, #171715 100%);
            border:1.5px solid {_AMBER};
            box-shadow:inset 0 0 80px rgba(0,0,0,0.45),0 0 16px rgba(240,165,0,0.12);
            border-radius:16px;padding:52px 40px 36px;text-align:center;
            height:340px;overflow:hidden;
            display:flex;flex-direction:column;align-items:center;justify-content:center;">
  <div style="margin-bottom:18px;">
    <span style="background:{_AMBER};color:#07080c;font-size:9px;
                 font-family:monospace;font-weight:800;letter-spacing:2.5px;
                 padding:4px 16px;border-radius:20px;text-transform:uppercase;">PRO</span>
  </div>
  <div style="font-size:56px;margin-bottom:22px;line-height:1;">📓</div>
  <div style="font-size:22px;font-weight:800;color:#ffffff;
              font-family:monospace;letter-spacing:-0.5px;margin-bottom:7px;">
    Edge Journal
  </div>
  <div style="font-size:9px;color:{_AMBER};font-family:monospace;
              letter-spacing:3px;text-transform:uppercase;margin-bottom:22px;">
    Coming Soon
  </div>
  <div style="font-size:12px;color:#888888;line-height:2.2;font-family:sans-serif;">
    Trade logging &nbsp;·&nbsp; Performance analytics
    <br>Edge tracking &nbsp;·&nbsp; Auth required
  </div>
</div>
        """, unsafe_allow_html=True)
        if st.button(" ", key="land_journal", use_container_width=True):
            st.switch_page("pages/6_Journal.py")


def _render_analysis():
    """Analysis module card grid — hero banner on top, then symmetric 2-col grid."""
    visible = [m for m in MODULES if m["active"] or m.get("teaser") or m.get("wip")]
    hero = next((m for m in visible if m.get("hero")), None)
    rest = [m for m in visible if not m.get("hero")]

    # Standard 2-column grid first
    for row_start in range(0, len(rest), 2):
        col_l, col_r = st.columns(2, gap="large")
        for col, mod in zip([col_l, col_r], rest[row_start:row_start + 2]):
            _render_module_card(col, mod)

    # Hero banner at the bottom — spans the full width (two card slots)
    if hero:
        _render_hero_card(hero)


def _render_journal_section():
    """Journal section — amber-themed hub with 3 feature cards (2 + 1 centred)."""
    _AMBER     = "#f0b429"
    _AMBER_BG  = "rgba(240,180,41,0.10)"
    _AMBER_DIM = "rgba(240,180,41,0.28)"

    # ── Auth notice
    st.markdown(
        f"""
        <div style="text-align:center;margin-bottom:32px;">
          <span style="background:rgba(240,180,41,0.08);border:1px solid rgba(240,180,41,0.25);
                       border-radius:8px;padding:8px 20px;
                       font-size:11px;font-family:monospace;color:#888888;letter-spacing:1px;">
            🔒 &nbsp; Authentication required &nbsp;·&nbsp; Launching soon
          </span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    def _journal_card(icon, title, desc):
        st.markdown(
            f"""
            <div class="ret-journal-card"
                 style="background:{C['card']};
                        border:1px solid {_AMBER_DIM};
                        border-radius:12px;padding:24px 24px 20px;
                        height:160px;overflow:hidden;opacity:0.78;
                        cursor:pointer;
                        transition:box-shadow 0.25s ease,border-color 0.25s ease;">
              <div style="display:flex;align-items:flex-start;
                          justify-content:space-between;margin-bottom:10px;">
                <div style="display:flex;align-items:center;gap:10px;">
                  <span style="font-size:22px;">{icon}</span>
                  <span style="font-size:15px;font-weight:700;color:{C['text']};
                               font-family:monospace;letter-spacing:2px;">{title}</span>
                </div>
                <span style="background:{_AMBER_BG};color:{_AMBER};
                             font-size:9px;font-family:monospace;font-weight:700;
                             letter-spacing:1px;padding:2px 8px;border-radius:4px;
                             text-transform:uppercase;border:1px solid {_AMBER_DIM};">
                  Coming Soon
                </span>
              </div>
              <div style="font-size:12px;color:{C['muted']};line-height:1.6;
                          font-family:sans-serif;">{desc}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        # Invisible overlay button — no page yet, just absorbs the click
        st.button(" ", key=f"jcard_{title}", use_container_width=True, disabled=True)

    # ── Row 1: Trade Log + Performance Stats
    col_l, col_r = st.columns(2, gap="large")
    with col_l:
        _journal_card(
            "📝", "Trade Log",
            "Enter and save every trade — symbol, direction, entry, exit, size, and personal notes. The raw data your edge is built on.",
        )
    with col_r:
        _journal_card(
            "📊", "Performance Stats",
            "Analyze your full trading performance in detail. Track Live and Backtest trades separately, let the data evaluate your edge, and export everything as CSV — ready to feed into an AI for deep pattern recognition across your trades.",
        )

    # ── Row 2: Trader Profile (centred, half-width)
    _, col_c, _ = st.columns([1, 2, 1])
    with col_c:
        _journal_card(
            "👤", "Trader Profile",
            "Your personal trading identity — more details coming soon.",
        )

    # ── Amber hover glow (journal cards)
    st.markdown(f"""
    <style>
      div[data-testid="stElementContainer"]:has(.ret-journal-card):has(+ div[data-testid="stElementContainer"]:hover) .ret-journal-card {{
          box-shadow:
              0 0 0 1px rgba(240,180,41,0.45),
              0 0 16px rgba(240,180,41,0.22),
              0 0 36px rgba(240,180,41,0.08) !important;
          border-color: rgba(240,180,41,0.7) !important;
          opacity: 0.95 !important;
      }}
      div[data-testid="stElementContainer"]:has(.ret-journal-card) {{
          position: relative; z-index: 1;
      }}
      div[data-testid="stElementContainer"]:has(.ret-journal-card)
        + div[data-testid="stElementContainer"] {{
          margin-top: -176px;
          margin-bottom: 20px;
          height: 160px;
          position: relative;
          z-index: 10;
      }}
      div[data-testid="stElementContainer"]:has(.ret-journal-card)
        + div[data-testid="stElementContainer"] button {{
          width: 100% !important;
          height: 160px !important;
          min-height: 0 !important;
          opacity: 0 !important;
          cursor: pointer !important;
          border-radius: 12px !important;
          padding: 0 !important;
          margin: 0 !important;
          display: block !important;
      }}
    </style>
    """, unsafe_allow_html=True)


# ── Hero banner renderer (flagship, full-width, centered) ──────────────────────

def _render_hero_card(mod: dict):
    """Full-width centered banner for the flagship module — greyed 'in progress'."""
    st.markdown(
        f"""
<div class="ret-module-hero"
     style="background:linear-gradient(170deg, #161616 0%, #141414 60%, #121212 100%);
            border:1.5px dashed #303030;border-radius:14px;padding:30px 40px;
            height:220px;overflow:hidden;text-align:center;opacity:0.92;
            display:flex;flex-direction:column;align-items:center;justify-content:center;
            box-shadow:inset 0 0 90px rgba(0,0,0,0.5);">
  <div style="margin-bottom:14px;">
    <span style="background:#1a1a1a;color:#8a8a8a;font-size:9px;
                 font-family:monospace;font-weight:800;letter-spacing:2.5px;
                 padding:4px 16px;border-radius:20px;text-transform:uppercase;
                 border:1px solid #333333;">🚧 In Arbeit</span>
  </div>
  <div style="display:flex;align-items:center;justify-content:center;gap:12px;margin-bottom:6px;">
    <span style="font-size:26px;filter:grayscale(1);">{mod['icon']}</span>
    <span style="font-size:23px;font-weight:800;color:#6a6a6a;
                 font-family:monospace;letter-spacing:2px;">{mod['title']}</span>
  </div>
  <div style="font-size:9px;color:#5a5a5a;font-family:monospace;
              letter-spacing:3px;text-transform:uppercase;margin-bottom:14px;">
    Every Module · One View
  </div>
  <div style="font-size:13px;color:#4a4a4a;line-height:1.7;
              font-family:sans-serif;max-width:700px;">
    The premium flagship that will fuse every module into a single screen — COT positioning,
    seasonality, macro bias and the economic calendar for any forex pair, all evaluated
    at one glance. Currently in development.
  </div>
</div>
        """,
        unsafe_allow_html=True,
    )
    # Invisible full-card nav button — overlaid via CSS
    if mod.get("page"):
        if st.button(" ", key=f"open_{mod['title']}", use_container_width=True):
            st.switch_page(mod["page"])


# ── Module card renderer ───────────────────────────────────────────────────────

def _render_module_card(col, mod: dict):
    active = mod["active"]
    teaser = mod.get("teaser", False)
    wip    = mod.get("wip", False)
    pro    = mod.get("pro", False)
    maint  = mod.get("maintenance", False)

    if wip:
        border       = "#2e2e2e"
        title_color  = "#5a5a5a"
        desc_color   = "#3c3c3c"
        badge_bg     = "#1a1a1a"
        badge_color  = "#6a6a6a"
        badge_text   = "Work in Progress"
        border_style = "dashed"
    elif teaser:
        border       = "#252525"
        title_color  = "#383838"
        desc_color   = "#2e2e2e"
        badge_bg     = "#1a1a1a"
        badge_color  = "#3a3a3a"
        badge_text   = "Coming Soon"
        border_style = "dashed"
    elif maint:
        border       = "rgba(240,180,41,0.35)"
        title_color  = C["text"]
        desc_color   = C["muted"]
        badge_bg     = C["yellow"]
        badge_color  = C["bg"]
        badge_text   = "Under Maintenance"
        border_style = "dashed"
    elif active and pro:
        border       = C["yellow"]
        title_color  = C["text"]
        desc_color   = C["muted"]
        badge_bg     = C["yellow"]
        badge_color  = C["bg"]
        badge_text   = "PRO ACCESS ONLY"
        border_style = "solid"
    elif active:
        border       = "rgba(79,142,247,0.3)"
        title_color  = C["text"]
        desc_color   = C["muted"]
        badge_bg     = "rgba(79,142,247,0.12)"
        badge_color  = C["teal"]
        badge_text   = "FREE ACCESS"
        border_style = "solid"
    else:
        border       = C["border"]
        title_color  = C["muted"]
        desc_color   = C["muted"]
        badge_bg     = C["dim"]
        badge_color  = C["muted"]
        badge_text   = "Coming Soon"
        border_style = "solid"

    is_clickable  = (active and not teaser and not maint) or wip
    if wip:
        card_class = "ret-module-wip"
    elif is_clickable:
        card_class = "ret-module-active"
        if pro:
            card_class += " ret-module-pro"
    else:
        card_class = ""
    card_sizing   = "height:160px;overflow:hidden;" if (is_clickable or maint) else "min-height:140px;margin-bottom:16px;"

    with col:
        st.markdown(
            f"""
            <div class="{card_class}"
                 style="background:{C['card']};border:1px {border_style} {border};
                        border-radius:12px;padding:24px 24px 20px;
                        {card_sizing}{'opacity:0.55;' if teaser else ''}">
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
                             text-transform:uppercase;border:1px solid {badge_color}40;">{badge_text}</span>
              </div>
              <div style="font-size:12px;color:{desc_color};line-height:1.6;
                          font-family:sans-serif;{'font-style:italic;' if teaser else ''}">{mod['desc']}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        # Invisible full-card nav button — overlaid via CSS, no visible button below card
        if is_clickable and mod.get("page"):
            if st.button(" ", key=f"open_{mod['title']}", use_container_width=True):
                st.switch_page(mod["page"])


if __name__ == "__main__":
    main()
