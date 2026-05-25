"""
Trading Analytics Terminal — Module 5: Market Regime Volatility Index
VIX percentile rank vs. 12-month history → regime classification + trading implications
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

try:
    from scipy.stats import percentileofscore as _pct_score
    _SCIPY = True
except ImportError:
    _SCIPY = False


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
    "muted":  "#666666",
    "teal":   "#e63946",
    "green":  "#00c896",
    "yellow": "#f0c040",
    "orange": "#f07840",
    "red":    "#e03030",
    "purple": "#a000c8",
}

# Regime definitions: (max_pct, label, emoji, color, bg_color)
REGIMES = [
    (20,  "LOW VOLATILITY",  "🟢", C["green"],  "rgba(0,200,150,0.12)"),
    (40,  "NORMAL",          "🟡", C["yellow"], "rgba(240,192,64,0.12)"),
    (60,  "MODERATE",        "🟠", C["orange"], "rgba(240,120,64,0.12)"),
    (80,  "ELEVATED",        "🔴", C["red"],    "rgba(224,48,48,0.12)"),
    (100, "EXTREME STRESS",  "⚫", C["purple"], "rgba(160,0,200,0.12)"),
]


# ╔══════════════════════════════════════════════════════════════════════════════
# ║  DATA
# ╚══════════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_vix() -> pd.Series | None:
    """Fetch VIX Close prices for the last 12 months. Returns None on failure."""
    try:
        df = yf.download("^VIX", period="1y", interval="1d", progress=False, auto_adjust=True)
        if df.empty:
            return None
        close = df["Close"].dropna()
        if isinstance(close, pd.DataFrame):
            close = close.iloc[:, 0]
        close.index = pd.to_datetime(close.index)
        return close.sort_index()
    except Exception:
        return None


def classify_regime(vix_level: float) -> tuple[str, str, str, str, str]:
    """Return (label, emoji, color, bg_color, description) based on fixed VIX thresholds."""
    if vix_level < 15:
        idx = 0  # LOW VOLATILITY
    elif vix_level < 18:
        idx = 1  # NORMAL
    elif vix_level < 22:
        idx = 2  # MODERATE
    elif vix_level < 28:
        idx = 3  # ELEVATED
    else:
        idx = 4  # EXTREME STRESS
    _, label, emoji, color, bg = REGIMES[idx]
    return label, emoji, color, bg, label


def calc_percentile(history: pd.Series, current: float) -> float:
    """Percentile rank of current within history (0–100)."""
    if _SCIPY:
        return float(_pct_score(history.values, current, kind="rank"))
    # Fallback: manual percentile rank
    below = (history < current).sum()
    return float(below / len(history) * 100)


def calc_trend(history: pd.Series) -> tuple[str, str]:
    """Compare latest value to 5-day MA. Returns (arrow_label, color)."""
    if len(history) < 6:
        return "→ Stable", "#aaaaaa"
    ma5 = history.iloc[-5:].mean()
    current = history.iloc[-1]
    diff_pct = (current - ma5) / ma5 * 100
    if diff_pct > 2.0:
        return "↑ Rising", "#f07840"
    if diff_pct < -2.0:
        return "↓ Falling", "#aaaaaa"
    return "→ Stable", "#aaaaaa"


# ╔══════════════════════════════════════════════════════════════════════════════
# ║  CHARTS
# ╚══════════════════════════════════════════════════════════════════════════════

def _gauge_chart(percentile: float, regime_color: str) -> go.Figure:
    """Half-circle gauge showing current percentile rank with colored zones."""
    # Zone boundaries and colors
    zone_colors  = [r[3] for r in REGIMES]   # colors
    zone_widths  = [20, 20, 20, 20, 20]      # each zone = 20 percentile points

    fig = go.Figure(go.Indicator(
        mode    = "gauge+number",
        value   = round(percentile, 1),
        number  = {"suffix": "%", "font": {"size": 36, "color": C["text"], "family": "monospace"}},
        title   = {
            "text": "Current Percentile Rank",
            "font": {"size": 17, "color": C["text"], "family": "monospace"},
        },
        domain  = {"x": [0.05, 0.95], "y": [0, 0.82]},
        gauge=dict(
            axis=dict(
                range=[0, 100],
                tickwidth=1,
                tickcolor="white",
                tickfont=dict(color="white", size=10)
            ),
            bar=dict(color=regime_color, thickness=0.15),
            bgcolor="rgba(0,0,0,0)",
            borderwidth=0,
            steps=[
                dict(range=[0,   20], color="#1a1f2e"),
                dict(range=[20,  40], color="#1a1f2e"),
                dict(range=[40,  60], color="#1a1f2e"),
                dict(range=[60,  80], color="#1a1f2e"),
                dict(range=[80, 100], color="#1a1f2e"),
            ]
        ),
    ))

    fig.update_layout(
        height=280,
        margin=dict(t=55, b=10, l=30, r=30),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="monospace"),
    )
    return fig


def _line_chart(history: pd.Series) -> go.Figure:
    """VIX line chart with colored background zones per regime (hrect)."""
    fig = go.Figure()

    # ── Background zones (fixed VIX levels) ──────────────────────────────────
    fig.add_hrect(y0=0,  y1=15, fillcolor="#00c896", opacity=0.08, layer="below", line_width=0)
    fig.add_hrect(y0=15, y1=18, fillcolor="#f0c040", opacity=0.08, layer="below", line_width=0)
    fig.add_hrect(y0=18, y1=22, fillcolor="#f07840", opacity=0.09, layer="below", line_width=0)
    fig.add_hrect(y0=22, y1=28, fillcolor="#e03030", opacity=0.10, layer="below", line_width=0)
    fig.add_hrect(y0=28, y1=60, fillcolor="#a000c8", opacity=0.10, layer="below", line_width=0)

    # ── Zone labels — right of chart ──────────────────────────────────────────
    zone_labels = [
        (7.5,  "#00c896", "LOW VOL"),
        (16.5, "#f0c040", "NORMAL"),
        (20.0, "#f07840", "MODERATE"),
        (25.0, "#e03030", "ELEVATED"),
        (32.0, "#a000c8", "EXTREME"),
    ]
    for y_mid, color, label in zone_labels:
        fig.add_annotation(
            x=1.01, xref="paper",
            y=y_mid, yref="y",
            text=label,
            showarrow=False,
            font=dict(color=color, size=9, family="monospace"),
            xanchor="left",
        )

    # ── VIX line ──────────────────────────────────────────────────────────────
    fig.add_trace(go.Scatter(
        x=history.index,
        y=history.values,
        mode="lines",
        name="VIX",
        line=dict(color=C["teal"], width=2),
        fill="tozeroy",
        fillcolor="rgba(69,196,176,0.08)",
        hovertemplate="%{x|%b %d, %Y}<br>VIX: %{y:.2f}<extra></extra>",
        showlegend=False,
    ))

    fig.update_layout(
        height=480,
        title=dict(
            text="VIX 12-Month History — Market Regime Context",
            font=dict(size=11, color=C["muted"], family="monospace"),
            x=0,
            xanchor="left",
            pad=dict(l=4),
        ),
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=60, r=80, t=50, b=50),
        showlegend=False,
        xaxis=dict(
            showgrid=False,
            zeroline=False,
            tickfont=dict(size=10, color=C["muted"], family="monospace"),
            linecolor=C["border"],
        ),
        yaxis=dict(
            range=[float(history.min()) * 0.85, max(float(history.max()) * 1.15, 35)],
            title=dict(
                text="VIX Level",
                font=dict(size=11, color=C["muted"], family="monospace"),
            ),
            showgrid=True,
            gridcolor=C["border"],
            zeroline=False,
            tickfont=dict(size=10, color=C["muted"], family="monospace"),
            linecolor=C["border"],
        ),
        font=dict(family="monospace"),
        hoverlabel=dict(
            bgcolor=C["card"],
            bordercolor=C["border"],
            font=dict(family="monospace", size=11, color=C["text"]),
        ),
    )
    return fig


# ╔══════════════════════════════════════════════════════════════════════════════
# ║  RENDER HELPERS
# ╚══════════════════════════════════════════════════════════════════════════════

def _metric_card(label: str, value: str, sub: str = "", color: str = "") -> str:
    val_color = color if color else C["text"]
    sub_html = (
        f"<div style='font-size:11px;color:{C['muted']};font-family:monospace;"
        f"margin-top:3px;'>{sub}</div>"
        if sub else ""
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



def _stats_table(history: pd.Series, current: float, percentile: float) -> str:
    stats = {
        "Min (12M)":    f"{history.min():.2f}",
        "Max (12M)":    f"{history.max():.2f}",
        "Mean (12M)":   f"{history.mean():.2f}",
        "Median (12M)": f"{history.median():.2f}",
        "Std Dev":     f"{history.std():.2f}",
        "Current VIX": f"{current:.2f}",
        "Percentile":  f"{percentile:.1f}%",
    }

    rows = ""
    for i, (k, v) in enumerate(stats.items()):
        bg = C["dim"] if i % 2 == 0 else "transparent"
        val_color = C["teal"] if k in ("Current VIX", "Percentile") else C["text"]
        rows += (
            f"<tr style='background:{bg};'>"
            f"<td style='padding:8px 14px;font-size:12px;color:{C['muted']};"
            f"font-family:monospace;'>{k}</td>"
            f"<td style='padding:8px 14px;font-size:13px;color:{val_color};"
            f"font-family:monospace;font-weight:700;text-align:right;'>{v}</td>"
            f"</tr>"
        )

    return (
        f"<div style='background:{C['card']};border:1px solid {C['border']};"
        f"border-radius:12px;overflow:hidden;'>"
        f"<div style='padding:12px 14px 8px;font-size:10px;color:{C['muted']};"
        f"font-family:monospace;letter-spacing:1.5px;text-transform:uppercase;"
        f"border-bottom:1px solid {C['border']};'>12-Month Statistics</div>"
        f"<table style='width:100%;border-collapse:collapse;'>"
        f"<tbody>{rows}</tbody></table></div>"
    )


# ╔══════════════════════════════════════════════════════════════════════════════
# ║  ENTRY POINT
# ╚══════════════════════════════════════════════════════════════════════════════

def main():
    st.set_page_config(
        page_title="Market Regime · Trading Terminal",
        page_icon="⚡",
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
      div[data-testid="stMetric"] {{
          background:{C['card']} !important;
          border:1px solid {C['border']} !important;
          border-radius:12px !important;
          padding:16px !important;
      }}
      div[data-testid="stMetricLabel"] p {{
          font-family:monospace !important;
          font-size:11px !important;
          letter-spacing:1px !important;
          text-transform:uppercase !important;
          color:{C['muted']} !important;
      }}
      div[data-testid="stMetricValue"] {{
          font-family:monospace !important;
          font-weight:800 !important;
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
      p, span, label {{ color:{C['text']}; }}
      /* Remove auto-rendered hr separators between column blocks */
      hr {{ display: none !important; }}
      [data-testid="stHorizontalBlock"] {{
          margin-bottom: 0 !important;
          padding-bottom: 0 !important;
      }}
      [data-testid="stVerticalBlockBorderWrapper"] {{
          padding-top: 0 !important;
          padding-bottom: 0 !important;
      }}
    </style>
    """, unsafe_allow_html=True)

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
            f"MARKET REGIME VOLATILITY INDEX</div>"
            f"<div style='font-size:11px;color:{C['muted']};font-family:monospace;"
            f"letter-spacing:1px;margin-top:4px;'>"
            f"Real-time volatility regime detection · VIX percentile rank vs. 12-month rolling window</div>"
            f"</div>",
            unsafe_allow_html=True,
        )
    with col_right:
        _, btn_col = st.columns([1, 1])
        with btn_col:
            if st.button("🔄 Refresh", key="regime_refresh"):
                fetch_vix.clear()
                st.rerun()

    # ── Data fetch ─────────────────────────────────────────────────────────────
    with st.spinner("Fetching VIX data..."):
        vix = fetch_vix()

    if vix is None or len(vix) == 0:
        st.error(
            "⚠ Could not load VIX data from Yahoo Finance. "
            "Check your internet connection and try refreshing."
        )
        return

    if len(vix) < 60:
        st.warning(
            f"⚠ Only {len(vix)} data points available (expected ≥ 60). "
            "Calculations may be less reliable."
        )

    # ── Core calculations ──────────────────────────────────────────────────────
    current_vix  = float(vix.iloc[-1])
    percentile   = calc_percentile(vix, current_vix)
    label, emoji, color, bg_color, _ = classify_regime(current_vix)
    trend_label, trend_color         = calc_trend(vix)
    last_date    = vix.index[-1].strftime("%b %d, %Y")
    n_days       = len(vix)

    # ── ROW 1 — Metrics ────────────────────────────────────────────────────────
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.markdown(
            _metric_card("Current VIX", f"{current_vix:.2f}"),
            unsafe_allow_html=True,
        )
    with m2:
        st.markdown(
            _metric_card("12M Percentile", f"{percentile:.1f}%"),
            unsafe_allow_html=True,
        )
    with m3:
        st.markdown(
            _metric_card("Regime", f"{emoji} {label}", "", color),
            unsafe_allow_html=True,
        )
    with m4:
        st.markdown(
            _metric_card("Trend vs 5D MA", trend_label, "", trend_color),
            unsafe_allow_html=True,
        )
    st.markdown("<div style='margin:0;padding:0;line-height:0;font-size:0;'></div>",
                unsafe_allow_html=True)

    # ── ROW 2 — Gauge + ROW 3 — Line chart (side by side) ─────────────────────
    col_gauge, col_line = st.columns([1, 1.8], gap="large")

    with col_gauge:
        st.plotly_chart(
            _gauge_chart(percentile, color),
            use_container_width=True,
            config={"displayModeBar": False},
        )
        # Regime label below gauge
        st.markdown(
            f"<div style='text-align:center;padding:0 0 14px;'>"
            f"<span style='background:{color}20;border:1px solid {color}50;"
            f"color:{color};font-family:monospace;font-size:13px;font-weight:700;"
            f"letter-spacing:1.5px;padding:6px 18px;border-radius:20px;'>"
            f"{emoji} {label}</span></div>",
            unsafe_allow_html=True,
        )
        st.markdown("""
<div style='text-align:center; font-size:10px;
color:#555; margin-top:16px; line-height:1.8;'>
Needle = VIX percentile vs. last 12 months &nbsp;·&nbsp;
{percentile:.1f}% = higher than {percentile:.1f}% of all sessions
</div>
""".format(percentile=percentile), unsafe_allow_html=True)

    with col_line:
        st.plotly_chart(
            _line_chart(vix),
            use_container_width=True,
            config={"displayModeBar": False},
        )

    # ── Footer ─────────────────────────────────────────────────────────────────
    st.markdown(
        f"<div style='margin-top:40px;padding-top:16px;"
        f"border-top:1px solid {C['border']};text-align:center;"
        f"font-size:11px;color:{C['muted']};font-family:monospace;'>"
        f"Built by @realedgetraders"
        f"&nbsp;&nbsp;&middot;&nbsp;&nbsp;"
        f"Data: Yahoo Finance (^VIX) &nbsp;&middot;&nbsp; "
        f"Cached 1h &nbsp;&middot;&nbsp; "
        f"Percentile rank vs. 12-month rolling window"
        f"</div>",
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
