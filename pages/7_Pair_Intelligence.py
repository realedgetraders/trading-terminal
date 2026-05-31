"""
Trading Analytics Terminal — Master Terminal
Cross-module signal aggregator: COT · Seasonality · Macro Bias · Calendar

Data functions are imported from _shared.py (project root).
Any change to COT / seasonality / calendar logic in the main modules
should be reflected in _shared.py — this file picks it up automatically.
"""

from datetime import date as dt_date

import plotly.graph_objects as go
import streamlit as st

# All shared data constants + cached fetch functions live in _shared.py.
# Updating _shared.py propagates to this module without any changes here.
from _shared import (
    C,
    CFTC_CCY_MAP,
    CURRENCY_FLAG,
    SUPPORTED_CCYS,
    calc_seasonal_curve,
    fetch_calendar,
    fetch_cot_raw,
    fetch_pair_history,
    get_cot_metrics,
    seasonal_month_stats,
)

# ╔══════════════════════════════════════════════════════════════════════════════
# ║  CONSTANTS
# ╚══════════════════════════════════════════════════════════════════════════════
_PASSWORD = "t26imheim"   # developer access to the in-progress module

# All 28 major forex pairs in standard market notation
PAIRS = [
    "EURUSD", "GBPUSD", "AUDUSD", "NZDUSD", "USDCAD", "USDCHF", "USDJPY",
    "EURGBP", "EURAUD", "EURCAD", "EURCHF", "EURJPY", "EURNZD",
    "GBPAUD", "GBPCAD", "GBPCHF", "GBPJPY", "GBPNZD",
    "AUDCAD", "AUDCHF", "AUDJPY", "AUDNZD",
    "CADCHF", "CADJPY", "CHFJPY",
    "NZDCAD", "NZDCHF", "NZDJPY",
]

# yfinance tickers (all pairs available with =X suffix)
PAIR_TICKERS: dict[str, str] = {p: f"{p}=X" for p in PAIRS}


# ╔══════════════════════════════════════════════════════════════════════════════
# ║  ECONOMIC BIAS — SESSION STATE READ
# ╚══════════════════════════════════════════════════════════════════════════════

def _get_bias(ccy: str) -> dict | None:
    """
    Read bias score for a currency from Module 3 session state.
    Returns {score, label} or None if not yet loaded.
    Key format: macro_scores_{CCY} → {total, level, currency, fmt}
    """
    cached = st.session_state.get(f"macro_scores_{ccy}")
    if cached and cached.get("fmt") == "indicator_12m":
        return {
            "score": float(cached.get("total", 0.0)),
            "label": str(cached.get("level", "NEUTRAL")),
        }
    return None


# ╔══════════════════════════════════════════════════════════════════════════════
# ║  CALENDAR — FILTER (pair-specific, stays here)
# ╚══════════════════════════════════════════════════════════════════════════════

def _filter_calendar(cal_df, base: str, quote: str):
    """Filter calendar to events for base/quote in the next 14 days."""
    import pandas as pd  # local to avoid top-level cost; already cached upstream
    if cal_df.empty:
        return cal_df
    today  = pd.Timestamp.today().normalize()
    cutoff = today + pd.Timedelta(days=14)
    mask = (
        (cal_df["currency"].isin([base, quote])) &
        (cal_df["date"] >= today) &
        (cal_df["date"] <= cutoff)
    )
    return cal_df[mask].sort_values("date").reset_index(drop=True)


# ╔══════════════════════════════════════════════════════════════════════════════
# ║  CSS INJECTION
# ╚══════════════════════════════════════════════════════════════════════════════

def _inject_css() -> None:
    st.markdown(
        f"""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:ital,wght@0,400;0,500;0,600;0,700;0,800;1,400&display=swap');
  *{{-webkit-font-smoothing:antialiased;-moz-osx-font-smoothing:grayscale;}}
  [style*="font-family:monospace"],[style*="font-family: monospace"]{{font-family:'JetBrains Mono',monospace !important;}}
  [style*="font-family:sans-serif"],[style*="font-family: sans-serif"]{{font-family:'Inter',sans-serif !important;}}
  button{{font-family:'JetBrains Mono',monospace !important;}}
  html, body, [data-testid="stAppViewContainer"] {{
    background: {C['bg']} !important;
  }}
  [data-testid="stHeader"], [data-testid="stToolbar"] {{ display:none !important; }}
  section[data-testid="stSidebar"]                   {{ display:none !important; }}

  /* Buttons */
  button[kind="secondary"] {{
    background:   {C['dim']}    !important;
    color:        {C['muted']}  !important;
    border:       1px solid {C['border']} !important;
    font-family:  monospace     !important;
    font-weight:  600           !important;
    border-radius:8px           !important;
    transition:   border-color 0.22s ease, color 0.22s ease, box-shadow 0.22s ease !important;
  }}
  button[kind="secondary"]:hover {{
    border-color: {C['teal']}70                  !important;
    color:        {C['teal']}                    !important;
    box-shadow:   0 0 12px rgba(79,142,247,0.14) !important;
  }}

  /* Selectbox / text input */
  [data-testid="stSelectbox"] > div > div,
  [data-testid="stTextInput"] input {{
    background:   {C['card']}   !important;
    border:       1px solid {C['border']} !important;
    color:        {C['text']}   !important;
    font-family:  monospace     !important;
    border-radius:8px           !important;
  }}
  [data-testid="stTextInput"] input::placeholder {{
    color: {C['muted']} !important;
  }}

  /* Password input */
  [data-testid="stTextInput"][data-input-type="password"] input {{
    letter-spacing: 3px;
  }}

  /* Divider */
  hr {{ border-color: {C['border']} !important; }}

  /* Spinner */
  [data-testid="stSpinner"] {{ color: {C['muted']} !important; }}
</style>
""",
        unsafe_allow_html=True,
    )


# ╔══════════════════════════════════════════════════════════════════════════════
# ║  RENDER HELPERS
# ╚══════════════════════════════════════════════════════════════════════════════

def _section_hdr(title: str) -> str:
    return (
        f"<div style='font-size:10px;color:{C['teal']};font-family:monospace;"
        f"letter-spacing:2px;text-transform:uppercase;margin:20px 0 10px;'>"
        f"▸ {title}</div>"
    )


# ── COT card ──────────────────────────────────────────────────────────────────
def _render_cot_card(m: dict) -> str:
    ccy   = m["ccy"]
    flag  = CURRENCY_FLAG.get(ccy, "")
    ci    = m["comm_idx"]
    li    = m["large_idx"]
    nc    = m["net_comm"]
    nl    = m["net_large"]
    trend = m["trend"]

    ci_col  = C["green"] if ci >= 70 else (C["red"] if ci <= 30 else C["muted"])
    ci_lbl  = "HIGH" if ci >= 70 else ("LOW" if ci <= 30 else "MID")
    nc_col  = C["green"] if nc > 0 else C["red"]
    nl_col  = C["green"] if nl > 0 else C["red"]
    tr_col  = C["green"] if trend == "↑" else (C["red"] if trend == "↓" else C["muted"])
    nc_sign = "+" if nc > 0 else ""
    nl_sign = "+" if nl > 0 else ""

    return f"""
<div style='background:{C['card']};border:1px solid {C['border']};
            border-radius:10px;padding:16px 18px;height:100%;'>
  <!-- Header -->
  <div style='display:flex;align-items:center;justify-content:space-between;
              margin-bottom:14px;'>
    <div style='display:flex;align-items:center;gap:8px;'>
      <span style='font-size:22px;'>{flag}</span>
      <span style='font-size:15px;font-weight:800;color:{C['text']};
                  font-family:monospace;'>{ccy}</span>
    </div>
    <span style='font-size:9px;color:{C['muted']};font-family:monospace;'>
      as of {m['date']}</span>
  </div>
  <!-- COT Index bar -->
  <div style='margin-bottom:12px;'>
    <div style='font-size:9px;color:{C['muted']};font-family:monospace;
                letter-spacing:1px;text-transform:uppercase;margin-bottom:5px;'>
      COT Index — Commercials</div>
    <div style='display:flex;align-items:center;gap:8px;'>
      <div style='flex:1;height:5px;background:{C['dim']};border-radius:3px;'>
        <div style='height:5px;background:{ci_col};border-radius:3px;
                    width:{ci:.0f}%;'></div>
      </div>
      <span style='font-size:13px;font-weight:800;color:{ci_col};
                  font-family:monospace;min-width:32px;text-align:right;'>
        {ci:.0f}</span>
      <span style='font-size:9px;color:{ci_col};font-family:monospace;
                  min-width:24px;'>{ci_lbl}</span>
    </div>
  </div>
  <!-- Net positions grid -->
  <div style='display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;
              margin-top:8px;'>
    <div style='text-align:center;'>
      <div style='font-size:9px;color:{C['muted']};font-family:monospace;
                  letter-spacing:0.8px;text-transform:uppercase;'>Comm Net</div>
      <div style='font-size:14px;font-weight:800;color:{nc_col};
                  font-family:monospace;margin-top:3px;'>
        {nc_sign}{int(nc):,}</div>
    </div>
    <div style='text-align:center;'>
      <div style='font-size:9px;color:{C['muted']};font-family:monospace;
                  letter-spacing:0.8px;text-transform:uppercase;'>Spec Net</div>
      <div style='font-size:14px;font-weight:800;color:{nl_col};
                  font-family:monospace;margin-top:3px;'>
        {nl_sign}{int(nl):,}</div>
    </div>
    <div style='text-align:center;'>
      <div style='font-size:9px;color:{C['muted']};font-family:monospace;
                  letter-spacing:0.8px;text-transform:uppercase;'>4-Wk</div>
      <div style='font-size:20px;color:{tr_col};margin-top:1px;'>
        {trend}</div>
    </div>
  </div>
</div>
"""


# ── Seasonality chart ─────────────────────────────────────────────────────────
def _render_seasonal_chart(mean_df, pair: str) -> go.Figure:
    from _shared import _REF_YEAR  # same scaffold constant
    today = dt_date.today()
    try:
        import pandas as pd
        m_start = pd.Timestamp(_REF_YEAR, today.month, 1)
        m_end   = (pd.Timestamp(_REF_YEAR, today.month + 1, 1) - pd.Timedelta(days=1)
                   if today.month < 12 else pd.Timestamp(_REF_YEAR, 12, 31))
    except Exception:
        m_start = m_end = None

    fig = go.Figure()

    if m_start and m_end:
        fig.add_vrect(
            x0=m_start, x1=m_end,
            fillcolor=C["teal"], opacity=0.07,
            layer="below", line_width=0,
        )

    fig.add_hline(y=100, line=dict(color=C["border"], width=1, dash="dot"))

    fig.add_trace(go.Scatter(
        x=mean_df["date"],
        y=mean_df["index"],
        mode="lines",
        line=dict(color=C["teal"], width=2),
        fill="tozeroy",
        fillcolor="rgba(79,142,247,0.06)",
        hovertemplate="<b>%{x|%b %d}</b><br>Index: %{y:.1f}<extra></extra>",
    ))

    fig.update_layout(
        height=200,
        margin=dict(l=0, r=10, t=6, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
        xaxis=dict(
            showgrid=False,
            tickformat="%b",
            dtick="M1",
            tickfont=dict(size=9, color=C["muted"], family="monospace"),
            linecolor=C["border"],
        ),
        yaxis=dict(
            showgrid=True,
            gridcolor=C["border"],
            tickfont=dict(size=9, color=C["muted"], family="monospace"),
            linecolor=C["border"],
            zeroline=False,
        ),
    )
    return fig


# ── Bias pair card ────────────────────────────────────────────────────────────
def _render_bias_card(ccy: str, score: float, label: str) -> str:
    flag  = CURRENCY_FLAG.get(ccy, "")
    lu    = label.upper()
    lc    = C["green"] if "BULL" in lu else (C["red"] if "BEAR" in lu else C["muted"])
    sign  = "+" if score > 0 else ""
    return f"""
<div style='background:{C['card']};border:1px solid {C['border']};
            border-radius:10px;padding:20px 18px;text-align:center;'>
  <div style='font-size:24px;margin-bottom:6px;'>{flag}</div>
  <div style='font-size:16px;font-weight:800;color:{C['text']};
              font-family:monospace;margin-bottom:6px;'>{ccy}</div>
  <div style='font-size:30px;font-weight:800;color:{lc};
              font-family:monospace;line-height:1;margin-bottom:6px;'>
    {sign}{score:.2f}</div>
  <div style='font-size:10px;font-weight:700;color:{lc};
              font-family:monospace;letter-spacing:1px;'>{lu}</div>
</div>
"""


def _render_pair_bias(base: str, quote: str, b_score: float, q_score: float) -> str:
    """Render the derived pair bias (base minus quote)."""
    diff = b_score - q_score
    if diff > 0.3:
        lbl = f"BULLISH BIAS FOR {base}"
        lc  = C["green"]
    elif diff < -0.3:
        lbl = f"BEARISH BIAS FOR {base}"
        lc  = C["red"]
    else:
        lbl = "NEUTRAL — NO CLEAR BIAS"
        lc  = C["muted"]
    sign = "+" if diff > 0 else ""
    return f"""
<div style='background:{C['panel']};border:1px solid {C['border']};
            border-radius:10px;padding:14px 18px;margin-top:10px;
            display:flex;align-items:center;justify-content:space-between;'>
  <div>
    <div style='font-size:9px;color:{C['muted']};font-family:monospace;
                letter-spacing:1px;text-transform:uppercase;margin-bottom:4px;'>
      Pair Bias  ·  {base} score − {quote} score</div>
    <div style='font-size:15px;font-weight:800;color:{lc};
                font-family:monospace;letter-spacing:0.5px;'>{lbl}</div>
  </div>
  <div style='font-size:26px;font-weight:800;color:{lc};
              font-family:monospace;'>{sign}{diff:.2f}</div>
</div>
"""


# ── Calendar table ────────────────────────────────────────────────────────────
def _render_calendar(cal) -> str:
    if cal.empty:
        return (
            f"<div style='padding:24px;text-align:center;color:{C['muted']};"
            f"font-family:monospace;font-size:12px;background:{C['card']};"
            f"border:1px solid {C['border']};border-radius:10px;'>"
            f"No upcoming events in the next 14 days for this pair.</div>"
        )

    IMP_COL = {
        "High":   C["red"],
        "Medium": C["yellow"],
        "Low":    C["muted"],
    }

    rows_html = ""
    prev_date = ""
    for _, row in cal.iterrows():
        ds     = row["date"].strftime("%a, %b %d")
        ccy    = row["currency"]
        flag   = CURRENCY_FLAG.get(ccy, "")
        title  = row["title"]
        impact = str(row.get("impact", "Low"))
        ic     = IMP_COL.get(impact, C["muted"])
        fc     = row.get("forecast")
        fc_s   = f"{fc:.2f}" if fc is not None else "—"

        if ds != prev_date:
            rows_html += (
                f"<tr><td colspan='4' style='padding:8px 14px 3px;"
                f"font-size:9px;color:{C['muted']};font-family:monospace;"
                f"letter-spacing:1px;text-transform:uppercase;"
                f"border-bottom:1px solid {C['border']};'>{ds}</td></tr>"
            )
            prev_date = ds

        rows_html += (
            f"<tr style='border-bottom:1px solid {C['dim']};'>"
            f"<td style='padding:7px 14px;font-size:11px;color:{C['text']};"
            f"font-family:monospace;white-space:nowrap;'>{flag} {ccy}</td>"
            f"<td style='padding:7px 14px;font-size:11px;color:{C['text']};"
            f"font-family:monospace;'>{title}</td>"
            f"<td style='padding:7px 14px;font-size:11px;color:{C['muted']};"
            f"font-family:monospace;text-align:right;white-space:nowrap;'>{fc_s}</td>"
            f"<td style='padding:7px 14px;font-size:9px;font-weight:700;"
            f"color:{ic};font-family:monospace;text-align:right;"
            f"letter-spacing:0.5px;white-space:nowrap;'>{impact.upper()}</td>"
            f"</tr>"
        )

    return (
        f"<div style='background:{C['card']};border:1px solid {C['border']};"
        f"border-radius:10px;overflow:hidden;'>"
        f"<table style='width:100%;border-collapse:collapse;'>"
        f"<thead><tr style='border-bottom:1px solid {C['border']};'>"
        f"<th style='padding:8px 14px;font-size:9px;color:{C['muted']};"
        f"font-family:monospace;text-transform:uppercase;letter-spacing:1px;"
        f"text-align:left;font-weight:600;'>CCY</th>"
        f"<th style='padding:8px 14px;font-size:9px;color:{C['muted']};"
        f"font-family:monospace;text-transform:uppercase;letter-spacing:1px;"
        f"text-align:left;font-weight:600;'>Event</th>"
        f"<th style='padding:8px 14px;font-size:9px;color:{C['muted']};"
        f"font-family:monospace;text-transform:uppercase;letter-spacing:1px;"
        f"text-align:right;font-weight:600;'>Forecast</th>"
        f"<th style='padding:8px 14px;font-size:9px;color:{C['muted']};"
        f"font-family:monospace;text-transform:uppercase;letter-spacing:1px;"
        f"text-align:right;font-weight:600;'>Impact</th>"
        f"</tr></thead>"
        f"<tbody>{rows_html}</tbody>"
        f"</table></div>"
    )


# ╔══════════════════════════════════════════════════════════════════════════════
# ║  MAIN
# ╚══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    st.set_page_config(
        page_title="Master Terminal — EdgeLab",
        page_icon="🔬",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    _inject_css()

    # ── Construction gate (developer access only) ──────────────────────────────
    if not st.session_state.get("pair_intel_auth"):
        _p7_back_col, _ = st.columns([1, 6])
        with _p7_back_col:
            if st.button("← Back to Hub", key="pair_intel_back"):
                st.switch_page("app.py")
        st.markdown("<div style='height:7vh;'></div>", unsafe_allow_html=True)
        _, col_c, _ = st.columns([2, 3, 2])
        with col_c:
            st.markdown(
                f"<div style='background:{C['card']};border:1px dashed {C['border']};"
                f"border-radius:16px;padding:44px 44px 36px;text-align:center;"
                f"box-shadow:inset 0 0 80px rgba(0,0,0,0.4);'>"
                f"<div style='font-size:46px;line-height:1;margin-bottom:18px;'>🚧</div>"
                f"<div style='margin-bottom:16px;'>"
                f"<span style='background:#1a1a1a;color:#8a8a8a;font-size:10px;"
                f"font-family:monospace;font-weight:800;letter-spacing:2.5px;"
                f"padding:5px 16px;border-radius:20px;text-transform:uppercase;"
                f"border:1px solid #333333;'>In Arbeit</span>"
                f"</div>"
                f"<div style='font-size:24px;font-weight:800;color:{C['text']};"
                f"font-family:monospace;letter-spacing:-0.5px;margin-bottom:8px;'>"
                f"Master Terminal</div>"
                f"<div style='font-size:12px;color:{C['muted']};font-family:sans-serif;"
                f"line-height:1.7;max-width:360px;margin:0 auto;'>"
                f"This module is currently under construction and not yet available. "
                f"Check back soon.</div>"
                f"</div>",
                unsafe_allow_html=True,
            )
            st.markdown("<div style='height:18px;'></div>", unsafe_allow_html=True)
            st.markdown(
                f"<div style='text-align:center;font-size:9px;color:#555555;"
                f"font-family:monospace;letter-spacing:2px;text-transform:uppercase;"
                f"margin-bottom:8px;'>Developer Access</div>",
                unsafe_allow_html=True,
            )
            pw = st.text_input(
                "Password",
                type="password",
                placeholder="Developer password…",
                label_visibility="collapsed",
                key="pair_intel_pw",
            )
            if st.button("Enter →", use_container_width=True, key="pair_intel_unlock"):
                if pw == _PASSWORD:
                    st.session_state["pair_intel_auth"] = True
                    st.rerun()
                else:
                    st.error("Incorrect password.")
        return

    # ── Title row ──────────────────────────────────────────────────────────────
    col_back, col_title, _ = st.columns([2, 5, 2])
    with col_back:
        st.markdown("<div style='margin-top:6px;'>", unsafe_allow_html=True)
        if st.button("← Back to Terminal", key="back_btn"):
            st.switch_page("app.py")
        st.markdown("</div>", unsafe_allow_html=True)
    with col_title:
        st.markdown(
            f"<div style='text-align:center;margin-bottom:14px;'>"
            f"<div style='font-size:20px;font-weight:700;color:{C['text']};"
            f"font-family:monospace;letter-spacing:-0.5px;line-height:1.2;'>"
            f"Master Terminal</div>"
            f"<div style='font-size:11px;color:{C['muted']};font-family:monospace;"
            f"margin-top:3px;'>COT · Seasonality · Macro Bias · Calendar</div>"
            f"</div>",
            unsafe_allow_html=True,
        )
    st.divider()

    # ── Pair selection ─────────────────────────────────────────────────────────
    col_dd, col_custom, col_info = st.columns([2, 2, 3])
    with col_dd:
        selected_pair = st.selectbox(
            "Select Pair",
            options=PAIRS,
            index=0,
            key="pi_pair_select",
        )
    with col_custom:
        custom = st.text_input(
            "Custom Pair (overrides dropdown)",
            placeholder="e.g. GBPNZD",
            key="pi_custom",
        )

    # Resolve pair
    raw_pair = custom.strip().upper() if custom.strip() else selected_pair
    pair     = raw_pair.replace("/", "")
    ticker   = PAIR_TICKERS.get(pair, f"{pair}=X")

    # Derive base / quote
    if len(pair) >= 6:
        base  = pair[:3]
        quote = pair[3:6]
    else:
        st.warning(f"⚠ Cannot parse pair '{pair}' — expected 6-character format like EURUSD.")
        return

    if base not in SUPPORTED_CCYS or quote not in SUPPORTED_CCYS:
        st.warning(
            f"⚠ Unrecognized currency in '{pair}'. "
            f"Both currencies must be one of: {', '.join(sorted(SUPPORTED_CCYS))}."
        )
        return

    with col_info:
        st.markdown(
            f"<div style='margin-top:26px;'>"
            f"<span style='font-size:22px;font-weight:800;color:{C['text']};"
            f"font-family:monospace;'>"
            f"{CURRENCY_FLAG.get(base,'')} {base} / {quote} {CURRENCY_FLAG.get(quote,'')}"
            f"</span>"
            f"<span style='font-size:10px;color:{C['muted']};font-family:monospace;"
            f"margin-left:10px;'>{ticker}</span>"
            f"</div>",
            unsafe_allow_html=True,
        )

    st.markdown("<div style='margin-top:4px;'></div>", unsafe_allow_html=True)

    # ══════════════════════════════════════════════════════════════════════════
    # SECTION 1 — COT POSITIONING
    # ══════════════════════════════════════════════════════════════════════════
    st.markdown(_section_hdr("COT Positioning"), unsafe_allow_html=True)
    try:
        with st.spinner("Loading COT data…"):
            raw_df, cot_errors = fetch_cot_raw()

        # Determine which currencies have CFTC futures data
        if base == "USD":
            cot_ccys = [quote] if quote in CFTC_CCY_MAP else []
        elif quote == "USD":
            cot_ccys = [base] if base in CFTC_CCY_MAP else []
        else:
            cot_ccys = [c for c in [base, quote] if c in CFTC_CCY_MAP]

        if not cot_ccys:
            st.info("No CFTC COT futures data available for this pair.")
        else:
            cols = st.columns(len(cot_ccys))
            for i, ccy in enumerate(cot_ccys):
                metrics = get_cot_metrics(raw_df, ccy)
                with cols[i]:
                    if metrics:
                        st.markdown(_render_cot_card(metrics), unsafe_allow_html=True)
                    else:
                        st.markdown(
                            f"<div style='background:{C['card']};border:1px solid {C['border']};"
                            f"border-radius:10px;padding:24px;text-align:center;"
                            f"color:{C['muted']};font-family:monospace;font-size:12px;'>"
                            f"COT data unavailable for {ccy}</div>",
                            unsafe_allow_html=True,
                        )

        if cot_errors and raw_df.empty:
            st.warning("⚠ Could not reach CFTC servers. COT data unavailable.")
    except Exception as exc:
        st.warning(f"⚠ COT section error: {exc}")

    # ══════════════════════════════════════════════════════════════════════════
    # SECTION 2 — SEASONALITY
    # ══════════════════════════════════════════════════════════════════════════
    st.markdown(_section_hdr("Seasonal Pattern"), unsafe_allow_html=True)
    try:
        with st.spinner("Loading seasonal data…"):
            hist_df = fetch_pair_history(ticker)

        if hist_df.empty:
            st.info(f"No price history available for {pair}.")
        else:
            mean_df = calc_seasonal_curve(hist_df)
            if mean_df.empty:
                st.info("Insufficient data to compute seasonal pattern.")
            else:
                stats      = seasonal_month_stats(mean_df)
                month_name = dt_date.today().strftime("%B")
                n_years    = hist_df["Year"].nunique()

                col_a, col_b, col_c2 = st.columns(3)
                with col_a:
                    st.markdown(
                        f"<div style='background:{C['card']};border:1px solid {C['border']};"
                        f"border-radius:10px;padding:12px 16px;text-align:center;'>"
                        f"<div style='font-size:9px;color:{C['muted']};font-family:monospace;"
                        f"letter-spacing:1px;text-transform:uppercase;'>Data Span</div>"
                        f"<div style='font-size:18px;font-weight:800;color:{C['text']};"
                        f"font-family:monospace;margin-top:4px;'>{n_years}Y</div>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )
                with col_b:
                    pct   = stats.get("pct", 0.0)
                    pcol  = C["green"] if pct > 0 else (C["red"] if pct < 0 else C["muted"])
                    psign = "+" if pct > 0 else ""
                    st.markdown(
                        f"<div style='background:{C['card']};border:1px solid {C['border']};"
                        f"border-radius:10px;padding:12px 16px;text-align:center;'>"
                        f"<div style='font-size:9px;color:{C['muted']};font-family:monospace;"
                        f"letter-spacing:1px;text-transform:uppercase;'>{month_name} Δ</div>"
                        f"<div style='font-size:18px;font-weight:800;color:{pcol};"
                        f"font-family:monospace;margin-top:4px;'>"
                        f"{psign}{pct:.1f}%</div>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )
                with col_c2:
                    direction = stats.get("direction", "—")
                    dcol      = stats.get("color", C["muted"])
                    st.markdown(
                        f"<div style='background:{C['card']};border:1px solid {C['border']};"
                        f"border-radius:10px;padding:12px 16px;text-align:center;'>"
                        f"<div style='font-size:9px;color:{C['muted']};font-family:monospace;"
                        f"letter-spacing:1px;text-transform:uppercase;'>Seasonal Bias</div>"
                        f"<div style='font-size:13px;font-weight:800;color:{dcol};"
                        f"font-family:monospace;margin-top:5px;letter-spacing:0.5px;'>"
                        f"{direction}</div>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )

                st.markdown("<div style='margin-top:8px;'></div>", unsafe_allow_html=True)
                st.plotly_chart(
                    _render_seasonal_chart(mean_df, pair),
                    use_container_width=True,
                    config={"displayModeBar": False},
                )
                st.markdown(
                    f"<div style='font-size:9px;color:{C['muted']};font-family:monospace;"
                    f"margin-top:-8px;'>Shaded band = {month_name} · "
                    f"Baseline 100 = annual mean · {n_years} years of data</div>",
                    unsafe_allow_html=True,
                )
    except Exception as exc:
        st.warning(f"⚠ Seasonality section error: {exc}")

    # ══════════════════════════════════════════════════════════════════════════
    # SECTION 3 — ECONOMIC BIAS
    # ══════════════════════════════════════════════════════════════════════════
    st.markdown(_section_hdr("Economic Bias"), unsafe_allow_html=True)
    try:
        b_bias = _get_bias(base)
        q_bias = _get_bias(quote)

        missing = [c for c, b in [(base, b_bias), (quote, q_bias)] if b is None]
        if missing:
            st.info(
                f"Bias scores not loaded for: **{', '.join(missing)}**. "
                f"Open the Economic Bias Engine and select each currency to cache its score.",
                icon="ℹ️",
            )

        if b_bias and q_bias:
            col_base, col_quote = st.columns(2)
            with col_base:
                st.markdown(
                    _render_bias_card(base, b_bias["score"], b_bias["label"]),
                    unsafe_allow_html=True,
                )
            with col_quote:
                st.markdown(
                    _render_bias_card(quote, q_bias["score"], q_bias["label"]),
                    unsafe_allow_html=True,
                )
            st.markdown(
                _render_pair_bias(base, quote, b_bias["score"], q_bias["score"]),
                unsafe_allow_html=True,
            )

        elif b_bias or q_bias:
            loaded = [(base, b_bias)] if b_bias else [(quote, q_bias)]
            col_l, col_r = st.columns(2)
            for i, (ccy, bias) in enumerate(loaded):
                col = col_l if i == 0 else col_r
                with col:
                    st.markdown(
                        _render_bias_card(ccy, bias["score"], bias["label"]),
                        unsafe_allow_html=True,
                    )

    except Exception as exc:
        st.warning(f"⚠ Economic bias section error: {exc}")

    # ══════════════════════════════════════════════════════════════════════════
    # SECTION 4 — NEWS & EVENTS CALENDAR
    # ══════════════════════════════════════════════════════════════════════════
    st.markdown(_section_hdr(f"Upcoming Events — {base} / {quote}"), unsafe_allow_html=True)
    try:
        with st.spinner("Loading calendar…"):
            cal_df   = fetch_calendar()
        filtered = _filter_calendar(cal_df, base, quote)
        st.markdown(_render_calendar(filtered), unsafe_allow_html=True)
        if cal_df.empty:
            st.warning("⚠ ForexFactory calendar currently unavailable.")
    except Exception as exc:
        st.warning(f"⚠ Calendar section error: {exc}")

    # ── Footer ─────────────────────────────────────────────────────────────────
    st.markdown(
        f"<div style='margin-top:48px;padding-top:16px;"
        f"border-top:1px solid {C['border']};text-align:center;"
        f"font-size:11px;color:{C['muted']};font-family:monospace;'>"
        f"Built by @realedgetraders</div>",
        unsafe_allow_html=True,
    )


main()
