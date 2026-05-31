"""
Trading Analytics Terminal — Module 07: Valuation Tool
Measures the selected asset against four macro anchors (Gold · USD · Bonds ·
World Equities) on a 0–100 rolling-range scale to flag under-/overvaluation.
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

# ╔══════════════════════════════════════════════════════════════════════════════
# ║  CONSTANTS
# ╚══════════════════════════════════════════════════════════════════════════════

C = {
    "bg":     "#0d0d0d",
    "card":   "#141414",
    "border": "#252525",
    "panel":  "#111111",
    "dim":    "#171717",
    "text":   "#e8e8e8",
    "muted":  "#909090",
    "teal":   "#4f8ef7",
    "green":  "#1a9b6a",
    "red":    "#f05262",
    "yellow": "#f0b429",
}

_PASSWORD = "12345"

# 28 major forex pairs (same set as the Master Terminal)
PAIRS = [
    "EURUSD", "GBPUSD", "AUDUSD", "NZDUSD", "USDCAD", "USDCHF", "USDJPY",
    "EURGBP", "EURAUD", "EURCAD", "EURCHF", "EURJPY", "EURNZD",
    "GBPAUD", "GBPCAD", "GBPCHF", "GBPJPY", "GBPNZD",
    "AUDCAD", "AUDCHF", "AUDJPY", "AUDNZD",
    "CADCHF", "CADJPY", "CHFJPY",
    "NZDCAD", "NZDCHF", "NZDJPY",
]
PAIR_TICKERS = {p: f"{p}=X" for p in PAIRS}

# Four macro anchors — (label, primary ticker, fallback ticker, line colour)
# Bonds use a PRICE proxy (high price = expensive = low yield), never the yield.
ANCHORS = [
    {"label": "Gold",           "primary": "GC=F",      "fallback": "GLD", "color": "#b8902f"},
    {"label": "USD (DXY)",      "primary": "DX-Y.NYB",  "fallback": "DX=F", "color": "#7f8a99"},
    {"label": "10Y Bonds",      "primary": "ZN=F",      "fallback": "IEF", "color": "#4a8c7a"},
    {"label": "World Equities", "primary": "ACWI",      "fallback": "VT",  "color": "#9a7fc0"},
]

# Lookback → rolling-window length and displayed trailing span (trading days)
LOOKBACKS = {
    "6M": dict(window=126,  disp=126),
    "1Y": dict(window=252,  disp=252),
    "2Y": dict(window=504,  disp=504),
    "5Y": dict(window=1260, disp=1260),
}
_DEFAULT_LOOKBACK = "2Y"


# ╔══════════════════════════════════════════════════════════════════════════════
# ║  DATA
# ╚══════════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_one(ticker: str, period: str = "max") -> pd.Series | None:
    """Daily adjusted-close series for a ticker. None if unavailable/too short."""
    try:
        df = yf.download(ticker, period=period, interval="1d",
                         progress=False, auto_adjust=True)
        if df is None or df.empty or "Close" not in df:
            return None
        close = df["Close"]
        if isinstance(close, pd.DataFrame):
            close = close.iloc[:, 0]
        close = close.dropna()
        if len(close) < 30:
            return None
        close.index = pd.to_datetime(close.index)
        return close.sort_index()
    except Exception:
        return None


def fetch_anchor(primary: str, fallback: str) -> tuple[pd.Series | None, str]:
    """Try the primary ticker, fall back to a more robust source if unreliable."""
    s = fetch_one(primary)
    if s is not None and len(s) >= 60:
        return s, primary
    s2 = fetch_one(fallback)
    if s2 is not None and len(s2) >= 60:
        return s2, fallback
    return (s, primary) if s is not None else (None, primary)


def stochastic_norm(s: pd.Series, window: int) -> pd.Series:
    """Rolling 0–100 position of price within its own range (stochastic %K)."""
    mp = max(20, window // 4)
    mn = s.rolling(window, min_periods=mp).min()
    mx = s.rolling(window, min_periods=mp).max()
    rng = (mx - mn).replace(0, np.nan)
    return ((s - mn) / rng * 100).clip(0, 100)


# ╔══════════════════════════════════════════════════════════════════════════════
# ║  LABELS
# ╚══════════════════════════════════════════════════════════════════════════════

def val_label(v: float) -> tuple[str, str]:
    """0–100 value → (label, colour)."""
    if v >= 80:
        return "Strongly Overvalued", C["red"]
    if v >= 60:
        return "Overvalued", C["red"]
    if v > 40:
        return "Fair Value", C["teal"]
    if v > 20:
        return "Undervalued", C["green"]
    return "Strongly Undervalued", C["green"]


def relative_label(diff: float) -> tuple[str, str]:
    """Asset value minus macro-anchor average → (phrase, colour)."""
    if diff >= 10:
        return "richer than the macro complex", C["red"]
    if diff <= -10:
        return "cheaper than the macro complex", C["green"]
    return "in line with the macro complex", C["teal"]


# ╔══════════════════════════════════════════════════════════════════════════════
# ║  CHART
# ╚══════════════════════════════════════════════════════════════════════════════

def _val_chart(frame: pd.DataFrame, asset_label: str,
               anchor_colors: dict[str, str], lookback_label: str) -> go.Figure:
    fig = go.Figure()

    # ── Valuation zones (style like Module 05) ───────────────────────────────
    fig.add_hrect(y0=70, y1=100, fillcolor=C["red"],   opacity=0.06, layer="below", line_width=0)
    fig.add_hrect(y0=0,  y1=30,  fillcolor=C["green"], opacity=0.06, layer="below", line_width=0)
    fig.add_hline(y=50, line=dict(color=C["border"], width=1, dash="dot"))

    for y_mid, color, label in [
        (85, C["red"],   "OVERVALUED"),
        (50, C["muted"], "FAIR"),
        (15, C["green"], "UNDERVALUED"),
    ]:
        fig.add_annotation(
            x=1.005, xref="paper", y=y_mid, yref="y",
            text=label, showarrow=False, xanchor="left",
            font=dict(color=color, size=9, family="monospace"),
        )

    # ── Macro anchors (muted, thin, in the background) ───────────────────────
    for label, color in anchor_colors.items():
        if label not in frame:
            continue
        fig.add_trace(go.Scatter(
            x=frame.index, y=frame[label], mode="lines", name=label,
            line=dict(color=color, width=1.4), opacity=0.6,
            hovertemplate="%{x|%b %d, %Y}<br>" + label + ": %{y:.0f}/100<extra></extra>",
        ))

    # ── Selected asset (bright, thick, foreground) ───────────────────────────
    fig.add_trace(go.Scatter(
        x=frame.index, y=frame[asset_label], mode="lines", name=asset_label,
        line=dict(color=C["teal"], width=3.4),
        hovertemplate="%{x|%b %d, %Y}<br>" + asset_label + ": %{y:.0f}/100<extra></extra>",
    ))

    fig.update_layout(
        height=520,
        title=dict(
            text=f"Valuation vs. Macro Anchors — {lookback_label} rolling range",
            font=dict(size=11, color=C["muted"], family="monospace"),
            x=0, xanchor="left", pad=dict(l=4),
        ),
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=55, r=95, t=70, b=45),
        legend=dict(
            orientation="h", yanchor="bottom", y=1.04, xanchor="left", x=0,
            font=dict(size=10, color=C["muted"], family="monospace"),
            bgcolor="rgba(0,0,0,0)",
        ),
        xaxis=dict(
            showgrid=False, zeroline=False,
            tickfont=dict(size=10, color=C["muted"], family="monospace"),
            linecolor=C["border"],
        ),
        yaxis=dict(
            range=[0, 100], dtick=20,
            title=dict(text="Valuation (0–100)",
                       font=dict(size=11, color=C["muted"], family="monospace")),
            showgrid=True, gridcolor=C["border"], zeroline=False,
            tickfont=dict(size=10, color=C["muted"], family="monospace"),
            linecolor=C["border"],
        ),
        font=dict(family="monospace"),
        hoverlabel=dict(bgcolor=C["card"], bordercolor=C["border"],
                        font=dict(family="monospace", size=11, color=C["text"])),
    )
    return fig


def _metric_card(label: str, value: str, sub: str = "", color: str = "") -> str:
    val_color = color if color else C["text"]
    sub_html = (
        f"<div style='font-size:11px;color:{C['muted']};font-family:monospace;"
        f"margin-top:4px;'>{sub}</div>" if sub else ""
    )
    return (
        f"<div style='background:{C['card']};border:1px solid {C['border']};"
        f"border-radius:12px;padding:18px 20px;text-align:center;'>"
        f"<div style='font-size:10px;color:{C['muted']};font-family:monospace;"
        f"letter-spacing:1.5px;text-transform:uppercase;margin-bottom:8px;'>{label}</div>"
        f"<div style='font-size:26px;font-weight:800;color:{val_color};"
        f"font-family:monospace;letter-spacing:-0.5px;'>{value}</div>"
        f"{sub_html}</div>"
    )


# ╔══════════════════════════════════════════════════════════════════════════════
# ║  CSS + GATE
# ╚══════════════════════════════════════════════════════════════════════════════

def _inject_css() -> None:
    st.markdown(f"""
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:ital,wght@0,400;0,500;0,600;0,700;0,800;1,400&display=swap');
      *{{-webkit-font-smoothing:antialiased;-moz-osx-font-smoothing:grayscale;}}
      [style*="font-family:monospace"],[style*="font-family: monospace"]{{font-family:'JetBrains Mono',monospace !important;}}
      [style*="font-family:sans-serif"],[style*="font-family: sans-serif"]{{font-family:'Inter',sans-serif !important;}}
      button{{font-family:'JetBrains Mono',monospace !important;}}
      html, body, [data-testid="stAppViewContainer"],
      [data-testid="stHeader"], [data-testid="stToolbar"],
      [data-testid="stDecoration"] {{ background-color:{C['bg']} !important; }}
      section[data-testid="stSidebar"] {{ display:none !important; }}
      .stMainBlockContainer {{ padding-top:3rem !important; padding-bottom:2rem !important; }}
      p, span, label {{ color:{C['text']}; }}
      hr {{ display:none !important; }}
      button[kind="secondary"] {{
          background:{C['dim']} !important; color:{C['muted']} !important;
          border:1px solid {C['border']} !important;
          font-family:monospace !important; font-weight:600 !important;
          border-radius:8px !important;
          transition:border-color 0.22s ease,color 0.22s ease,box-shadow 0.22s ease !important;
      }}
      button[kind="secondary"]:hover {{
          border-color:{C['teal']}70 !important; color:{C['teal']} !important;
          box-shadow:0 0 12px rgba(79,142,247,0.14) !important;
      }}
      [data-testid="stTextInput"] input {{
          background:#1c1c1c !important; border:1px solid rgba(79,142,247,0.28) !important;
          color:{C['text']} !important; font-family:monospace !important;
          border-radius:8px !important; font-size:13px !important;
      }}
      [data-testid="stTextInput"] input::placeholder {{ color:#555 !important; }}
      [data-testid="stTextInput"] input:focus {{
          border-color:rgba(79,142,247,0.65) !important;
          box-shadow:0 0 0 3px rgba(79,142,247,0.10) !important;
      }}
    </style>
    """, unsafe_allow_html=True)


def _render_footer() -> None:
    st.markdown(
        f"<div style='margin-top:40px;padding-top:16px;"
        f"border-top:1px solid {C['border']};text-align:center;"
        f"font-size:11px;color:{C['muted']};font-family:monospace;'>"
        f"Built by @realedgetraders &nbsp;&middot;&nbsp; "
        f"Data: Yahoo Finance &nbsp;&middot;&nbsp; Cached 1h &nbsp;&middot;&nbsp; "
        f"Rolling-range valuation (0–100)</div>",
        unsafe_allow_html=True,
    )


def _render_gate() -> None:
    _back, _ = st.columns([1, 6])
    with _back:
        if st.button("← Back to Hub", key="val_gate_back"):
            st.switch_page("app.py")
    st.markdown("<div style='height:7vh;'></div>", unsafe_allow_html=True)
    _, col, _ = st.columns([2, 3, 2])
    with col:
        st.markdown(
            f"<div style='background:{C['card']};border:1px solid rgba(79,142,247,0.22);"
            f"border-radius:16px;padding:46px 46px 38px;text-align:center;"
            f"box-shadow:0 0 48px rgba(79,142,247,0.07);'>"
            f"<div style='margin-bottom:22px;'>"
            f"<span style='background:{C['yellow']};color:#0a0c10;font-size:10px;"
            f"font-family:monospace;font-weight:800;letter-spacing:3px;"
            f"padding:4px 14px;border-radius:20px;text-transform:uppercase;'>PRO</span>"
            f"</div>"
            f"<div style='font-size:42px;line-height:1;margin-bottom:18px;'>⚖️</div>"
            f"<div style='font-size:24px;font-weight:800;color:{C['text']};"
            f"font-family:monospace;letter-spacing:-0.5px;margin-bottom:8px;'>"
            f"Valuation Tool</div>"
            f"<div style='font-size:10px;color:{C['teal']};font-family:monospace;"
            f"letter-spacing:2px;text-transform:uppercase;margin-bottom:14px;'>"
            f"Module 07 &nbsp;·&nbsp; Valuation Tool</div>"
            f"<div style='font-size:12px;color:{C['muted']};font-family:monospace;'>"
            f"Enter password to continue</div></div>",
            unsafe_allow_html=True,
        )
        st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)
        pw = st.text_input("Password", type="password", placeholder="Enter password…",
                           label_visibility="collapsed", key="val_pw")
        st.markdown("<div style='height:6px;'></div>", unsafe_allow_html=True)
        if st.button("Unlock →", use_container_width=True, key="val_unlock"):
            if pw == _PASSWORD:
                st.session_state["valuation_auth"] = True
                st.rerun()
            else:
                st.error("Incorrect password.")


# ╔══════════════════════════════════════════════════════════════════════════════
# ║  MAIN
# ╚══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    st.set_page_config(
        page_title="Valuation Tool — EdgeLab",
        page_icon="⚖️",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    _inject_css()

    # ── PRO gate ─────────────────────────────────────────────────────────────
    if not st.session_state.get("valuation_auth"):
        _render_gate()
        _render_footer()
        return

    # ── Title row ────────────────────────────────────────────────────────────
    col_back, col_title, col_right = st.columns([2, 6, 2])
    with col_back:
        if st.button("← Back to Terminal", key="val_back"):
            st.switch_page("app.py")
    with col_title:
        st.markdown(
            f"<div style='text-align:center;'>"
            f"<div style='font-size:20px;font-weight:800;color:{C['text']};"
            f"font-family:monospace;letter-spacing:-0.5px;'>VALUATION TOOL</div>"
            f"<div style='font-size:11px;color:{C['muted']};font-family:monospace;"
            f"letter-spacing:1px;margin-top:4px;'>"
            f"Under-/overvaluation vs. Gold · USD · Bonds · World Equities</div>"
            f"</div>",
            unsafe_allow_html=True,
        )
    with col_right:
        _, btn_col = st.columns([1, 1])
        with btn_col:
            if st.button("🔄 Refresh", key="val_refresh"):
                fetch_one.clear()
                st.rerun()
    st.divider()

    # ── Controls: asset dropdown + custom ticker + lookback ──────────────────
    col_dd, col_custom, col_lb = st.columns([2, 2, 3])
    with col_dd:
        selected_pair = st.selectbox("Select Asset", options=PAIRS, index=0, key="val_select")
    with col_custom:
        custom = st.text_input("Custom Ticker (overrides dropdown)",
                               placeholder="e.g. AAPL, BTC-USD, CL=F", key="val_custom")
    with col_lb:
        lookback_label = st.radio("Lookback", options=list(LOOKBACKS.keys()),
                                  index=list(LOOKBACKS.keys()).index(_DEFAULT_LOOKBACK),
                                  horizontal=True, key="val_lookback")

    # Resolve asset → label + yfinance ticker
    if custom.strip():
        asset_label  = custom.strip().upper()
        asset_ticker = custom.strip()
    else:
        asset_label  = selected_pair
        asset_ticker = PAIR_TICKERS.get(selected_pair, f"{selected_pair}=X")

    window = LOOKBACKS[lookback_label]["window"]
    disp   = LOOKBACKS[lookback_label]["disp"]

    # ── Fetch ────────────────────────────────────────────────────────────────
    with st.spinner("Loading price data…"):
        asset_close = fetch_one(asset_ticker)
        anchors_raw = {a["label"]: (*fetch_anchor(a["primary"], a["fallback"]), a["color"])
                       for a in ANCHORS}

    if asset_close is None or len(asset_close) < 60:
        st.error(
            f"⚠ Could not load reliable data for '{asset_ticker}'. "
            f"Check the ticker symbol (Yahoo Finance format) and try again."
        )
        _render_footer()
        return

    # ── Normalise each row independently (0–100) ─────────────────────────────
    asset_norm = stochastic_norm(asset_close, window).dropna()
    if asset_norm.empty:
        st.warning("⚠ Not enough history to compute a valuation for this asset.")
        _render_footer()
        return

    disp_idx = asset_norm.index[-disp:]

    frame = pd.DataFrame(index=disp_idx)
    frame[asset_label] = asset_norm.reindex(disp_idx)

    anchor_colors: dict[str, str] = {}
    anchor_used:   dict[str, str] = {}
    for label, (series, used, color) in anchors_raw.items():
        if series is None:
            continue
        a_norm = stochastic_norm(series, window)
        frame[label] = a_norm.reindex(disp_idx, method="ffill")
        anchor_colors[label] = color
        anchor_used[label]   = used

    frame = frame.ffill().bfill()

    # ── Current readings + verdict ───────────────────────────────────────────
    asset_val   = float(frame[asset_label].iloc[-1])
    anchor_vals = {lbl: float(frame[lbl].iloc[-1]) for lbl in anchor_colors}
    anchor_avg  = float(np.mean(list(anchor_vals.values()))) if anchor_vals else 50.0
    diff        = asset_val - anchor_avg

    a_label, a_color   = val_label(asset_val)
    rel_phrase, r_color = relative_label(diff)

    # ── Metric cards ─────────────────────────────────────────────────────────
    m1, m2, m3 = st.columns(3)
    with m1:
        st.markdown(_metric_card("Asset Valuation", f"{asset_val:.0f}/100",
                                 a_label, a_color), unsafe_allow_html=True)
    with m2:
        st.markdown(_metric_card("Macro-Anchor Avg", f"{anchor_avg:.0f}/100",
                                 "Gold · USD · Bonds · Equities", C["teal"]),
                    unsafe_allow_html=True)
    with m3:
        st.markdown(_metric_card("Relative Position", f"{diff:+.0f}",
                                 "vs. anchor average", r_color), unsafe_allow_html=True)

    # ── Verdict line ─────────────────────────────────────────────────────────
    st.markdown(
        f"<div style='background:{C['card']};border:1px solid {C['border']};"
        f"border-left:3px solid {a_color};border-radius:10px;padding:14px 20px;"
        f"margin-top:14px;font-family:sans-serif;font-size:13px;color:{C['text']};"
        f"line-height:1.6;'>"
        f"<b style='font-family:monospace;color:{a_color};'>{asset_label}</b> sits at "
        f"<b style='font-family:monospace;color:{a_color};'>{asset_val:.0f}/100</b> "
        f"of its {lookback_label} range — <b style='color:{a_color};'>{a_label}</b>. "
        f"Against the four macro anchors (avg "
        f"<span style='font-family:monospace;'>{anchor_avg:.0f}</span>) it is currently "
        f"<b style='color:{r_color};'>{rel_phrase}</b>."
        f"</div>",
        unsafe_allow_html=True,
    )

    # ── Chart ────────────────────────────────────────────────────────────────
    st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
    st.plotly_chart(
        _val_chart(frame, asset_label, anchor_colors, lookback_label),
        use_container_width=True,
        config={"displayModeBar": False},
    )

    # ── Anchor readings (chips) ──────────────────────────────────────────────
    chips = ""
    for lbl, val in anchor_vals.items():
        _, c = val_label(val)
        chips += (
            f"<span style='display:inline-block;background:{C['card']};"
            f"border:1px solid {C['border']};border-radius:8px;padding:7px 14px;"
            f"margin:4px 6px 4px 0;font-family:monospace;font-size:12px;'>"
            f"<span style='color:{anchor_colors[lbl]};'>●</span> "
            f"<span style='color:{C['muted']};'>{lbl}</span> "
            f"<b style='color:{c};'>{val:.0f}</b>"
            f"<span style='color:#555;font-size:10px;'> · {anchor_used[lbl]}</span>"
            f"</span>"
        )
    st.markdown(f"<div style='margin-top:6px;'>{chips}</div>", unsafe_allow_html=True)

    _render_footer()


main()
