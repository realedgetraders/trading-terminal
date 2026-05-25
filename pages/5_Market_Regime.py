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
    "bg":     "#0a0f1e",
    "card":   "#0d1526",
    "border": "#1a2540",
    "panel":  "#0f1a2e",
    "dim":    "#192038",
    "text":   "#dde4f0",
    "muted":  "#445066",
    "teal":   "#45c4b0",
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
            "font": {"size": 13, "color": C["muted"], "family": "monospace"},
        },
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

    # Regime zone labels inside gauge
    zone_labels = ["LOW\nVOL", "NORMAL", "MOD.", "ELEV.", "EXTREME"]
    zone_midpoints = [10, 30, 50, 70, 90]
    import math
    for mid, label in zip(zone_midpoints, zone_labels):
        # Convert percentile to angle (180° arc from left to right)
        angle_deg = 180 - (mid / 100 * 180)
        angle_rad = math.radians(angle_deg)
        r = 0.72
        x = 0.5 + r * 0.5 * math.cos(angle_rad)
        y = 0.22 + r * 0.5 * math.sin(angle_rad)
        fig.add_annotation(
            x=x, y=y, text=label,
            showarrow=False,
            font={"size": 8, "color": C["muted"], "family": "monospace"},
            xref="paper", yref="paper",
            align="center",
        )

    fig.update_layout(
        height=300,
        margin=dict(t=40, b=10, l=30, r=30),
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
        height=450,
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=60, r=80, t=40, b=50),
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

    st.markdown(
        f"<div style='margin-bottom:20px;padding-bottom:16px;"
        f"border-bottom:1px solid {C['border']};'></div>",
        unsafe_allow_html=True,
    )

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
            _metric_card("Current VIX", f"{current_vix:.2f}", f"as of {last_date}"),
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

    st.markdown("<div style='height:20px;'></div>", unsafe_allow_html=True)

    # ── ROW 2 — Gauge + ROW 3 — Line chart (side by side) ─────────────────────
    col_gauge, col_line = st.columns([1, 1.6], gap="large")

    with col_gauge:
        st.markdown(
            f"<div style='background:{C['card']};border:1px solid {C['border']};"
            f"border-radius:12px;padding:4px 8px 0;'>",
            unsafe_allow_html=True,
        )
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
<div style='font-size:11px; color:#888; line-height:2; margin-top:8px;'>
<span style='color:#00c896'>●</span> <b style='color:#ccc'>LOW VOL</b> &nbsp;&nbsp; VIX &lt; 15<br>
<span style='color:#f0c040'>●</span> <b style='color:#ccc'>NORMAL</b> &nbsp;&nbsp;&nbsp; VIX 15–18<br>
<span style='color:#f07840'>●</span> <b style='color:#ccc'>MODERATE</b> &nbsp; VIX 18–22<br>
<span style='color:#e03030'>●</span> <b style='color:#ccc'>ELEVATED</b> &nbsp; VIX 22–28<br>
<span style='color:#a000c8'>●</span> <b style='color:#ccc'>EXTREME</b> &nbsp;&nbsp; VIX &gt; 28
</div>
""", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    with col_line:
        st.markdown(
            f"<div style='background:{C['card']};border:1px solid {C['border']};"
            f"border-radius:12px;padding:14px 16px 4px;'>"
            f"<div style='font-size:10px;color:{C['muted']};font-family:monospace;"
            f"letter-spacing:1.5px;text-transform:uppercase;margin-bottom:4px;'>"
            f"VIX 12-Month History — Market Regime Context</div>",
            unsafe_allow_html=True,
        )
        st.plotly_chart(
            _line_chart(vix),
            use_container_width=True,
            config={"displayModeBar": False},
        )
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div style='height:20px;'></div>", unsafe_allow_html=True)

    # ── ROW 5 — Statistics table ───────────────────────────────────────────────
    col_stats, col_spacer = st.columns([1, 1])
    with col_stats:
        st.markdown(
            _stats_table(vix, current_vix, percentile),
            unsafe_allow_html=True,
        )

    # ── Regime legend ──────────────────────────────────────────────────────────
    with col_spacer:
        legend_rows = "".join(
            f"<div style='display:flex;align-items:center;gap:12px;padding:8px 0;"
            f"border-bottom:1px solid {C['border']};'>"
            f"<span style='font-size:14px;'>{emoji}</span>"
            f"<span style='font-size:11px;color:{col};font-family:monospace;"
            f"font-weight:700;width:140px;'>{lbl}</span>"
            f"<span style='font-size:11px;color:{C['muted']};font-family:monospace;'>"
            f"P{prev}–P{pct}</span>"
            f"</div>"
            for (pct, lbl, emoji, col, _), prev in zip(
                REGIMES, [0, 20, 40, 60, 80]
            )
        )
        st.markdown(
            f"<div style='background:{C['card']};border:1px solid {C['border']};"
            f"border-radius:12px;padding:14px 16px;'>"
            f"<div style='font-size:10px;color:{C['muted']};font-family:monospace;"
            f"letter-spacing:1.5px;text-transform:uppercase;margin-bottom:10px;'>"
            f"Regime Reference</div>"
            f"{legend_rows}</div>",
            unsafe_allow_html=True,
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
