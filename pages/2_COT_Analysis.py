"""
Trading Analytics Terminal — Module 2: COT Analysis
CFTC Commitments of Traders weekly positioning data
"""

import io
import zipfile
import requests
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime

# ─── Theme ────────────────────────────────────────────────────────────────────

C = {
    "bg":       "#0d0d0d",
    "card":     "#141414",
    "border":   "#252525",
    "panel":    "#111111",
    "text":     "#e8e8e8",
    "muted":    "#666666",
    "dim":      "#171717",
    "teal":     "#4f8ef7",
    "teal_bg":  "rgba(79, 142, 247, 0.14)",
    "teal_dim": "rgba(79, 142, 247, 0.06)",
    "green":    "#1a9b6a",
    "green_bg": "rgba(26, 155, 106, 0.09)",
    "red":      "#f05262",
    "red_bg":   "rgba(240, 82, 98, 0.09)",
    "yellow":   "#f0b429",
    "blue":     "#4f8ef7",
}

# ─── Market Universe ──────────────────────────────────────────────────────────
# display_name → exact "Market and Exchange Names" string from deacot{YEAR}.zip
# A list of names is supported for markets that were renamed across years
# (get_market_data handles OR logic and deduplicates by date).
# Raw CFTC numbers only — no inversion applied to any market.

MARKET_GROUPS = {
    "Forex": {
        "EUR": "EURO FX - CHICAGO MERCANTILE EXCHANGE",
        "GBP": "BRITISH POUND - CHICAGO MERCANTILE EXCHANGE",
        "JPY": "JAPANESE YEN - CHICAGO MERCANTILE EXCHANGE",
        "CHF": "SWISS FRANC - CHICAGO MERCANTILE EXCHANGE",
        "CAD": "CANADIAN DOLLAR - CHICAGO MERCANTILE EXCHANGE",
        "AUD": "AUSTRALIAN DOLLAR - CHICAGO MERCANTILE EXCHANGE",
        "NZD": "NZ DOLLAR - CHICAGO MERCANTILE EXCHANGE",
    },
    "Commodities": {
        "Gold":   "GOLD - COMMODITY EXCHANGE INC.",
        "Silver": "SILVER - COMMODITY EXCHANGE INC.",
        # WTI crude was renamed: NYMEX (2001-2022) → WTI-PHYSICAL (2022-present)
        "Oil (WTI)": [
            "CRUDE OIL, LIGHT SWEET - NEW YORK MERCANTILE EXCHANGE",
            "WTI-PHYSICAL - NEW YORK MERCANTILE EXCHANGE",
        ],
    },
    "Indices": {
        "S&P 500":     "S&P 500 Consolidated - CHICAGO MERCANTILE EXCHANGE",
        "Nasdaq-100":  "NASDAQ-100 Consolidated - CHICAGO MERCANTILE EXCHANGE",
        "Dow Jones":   "DJIA Consolidated - CHICAGO BOARD OF TRADE",
        "Russell 2000":"RUSSELL E-MINI - CHICAGO MERCANTILE EXCHANGE",
    },
    "Bonds": {
        "10Y T-Note": "UST 10Y NOTE - CHICAGO BOARD OF TRADE",
        "30Y T-Bond": "UST BOND - CHICAGO BOARD OF TRADE",
        "2Y T-Note":  "UST 2Y NOTE - CHICAGO BOARD OF TRADE",
        "5Y T-Note":  "UST 5Y NOTE - CHICAGO BOARD OF TRADE",
    },
}

GROUP_CFG = {
    "Commercials":    {"col": "Net_Comm",  "long": "Comm_Long",  "short": "Comm_Short",  "color": "#3B82F6", "fill": "rgba(59,130,246,0.08)"},
    "Non-Commercials":{"col": "Net_Large", "long": "Large_Long", "short": "Large_Short", "color": "#6B7280", "fill": "rgba(107,114,128,0.08)"},
    "Non-Reportable": {"col": "Net_Small", "long": "Small_Long", "short": "Small_Short", "color": "#EAB308", "fill": "rgba(234,179,8,0.08)"},
}

# ─── Data Layer ───────────────────────────────────────────────────────────────

# Exact column names from deacot{YEAR}.zip / annual.txt (Legacy COT format)
_COT_NAME_COL = "Market and Exchange Names"
_COT_DATE_COL = "As of Date in Form YYYY-MM-DD"

# internal_key → source CSV column name  (Old) = Futures only, not Futures+Options
_COT_COLS = {
    "Comm_Long":   "Commercial Positions-Long (Old)",
    "Comm_Short":  "Commercial Positions-Short (Old)",
    "Large_Long":  "Noncommercial Positions-Long (Old)",
    "Large_Short": "Noncommercial Positions-Short (Old)",
    "Small_Long":  "Nonreportable Positions-Long (Old)",
    "Small_Short": "Nonreportable Positions-Short (Old)",
}


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_cot_raw() -> tuple[pd.DataFrame, list[str]]:
    """Fetch CFTC Legacy COT data (deacot{YEAR}.zip) from 2001 to current year."""
    current = datetime.today().year
    frames, errors = [], []
    for yr in range(2001, current + 1):
        url = f"https://www.cftc.gov/files/dea/history/deacot{yr}.zip"
        try:
            resp = requests.get(url, timeout=30)
            if resp.status_code != 200:
                errors.append(f"HTTP {resp.status_code} — {url}")
                continue
            with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
                with z.open(z.namelist()[0]) as f:
                    frames.append(pd.read_csv(f, low_memory=False))
        except Exception as e:
            errors.append(f"ERROR {yr}: {e}")
    if not frames:
        return pd.DataFrame(), errors
    combined = pd.concat(frames, ignore_index=True)
    combined.columns = combined.columns.str.strip()
    return combined, errors


def get_market_data(raw: pd.DataFrame, cftc_name: "str | list[str]") -> pd.DataFrame:
    """Filter raw COT data to one market and return Long/Short/Net columns.
    cftc_name may be a single string or a list of strings (OR logic) for markets
    that were renamed across years. Duplicate dates are dropped (earliest name wins).
    Uses raw CFTC numbers — no inversion applied.
    """
    if raw.empty or _COT_NAME_COL not in raw.columns:
        return pd.DataFrame()

    names = [cftc_name] if isinstance(cftc_name, str) else cftc_name
    # Build OR mask across all name variants — regex=False avoids special-char issues
    mask = pd.Series(False, index=raw.index)
    for n in names:
        mask |= raw[_COT_NAME_COL].str.upper().str.contains(n.upper(), regex=False, na=False)
    df = raw[mask].copy()
    if df.empty or _COT_DATE_COL not in df.columns:
        return pd.DataFrame()

    df["Date"] = pd.to_datetime(df[_COT_DATE_COL], errors="coerce")
    df = (df.dropna(subset=["Date"])
            .sort_values("Date")
            .drop_duplicates(subset=["Date"], keep="first")   # deduplicate transition-year overlaps
            .set_index("Date"))

    out = pd.DataFrame(index=df.index)
    for key, src_col in _COT_COLS.items():
        if src_col in df.columns:
            out[key] = pd.to_numeric(df[src_col], errors="coerce")

    if {"Comm_Long",  "Comm_Short"}  <= set(out.columns):
        out["Net_Comm"]  = out["Comm_Long"]  - out["Comm_Short"]
    if {"Large_Long", "Large_Short"} <= set(out.columns):
        out["Net_Large"] = out["Large_Long"] - out["Large_Short"]
    if {"Small_Long", "Small_Short"} <= set(out.columns):
        out["Net_Small"] = out["Small_Long"] - out["Small_Short"]

    return out.dropna(how="all")


def calc_cot_index(series: pd.Series, window: int = 26) -> pd.Series:
    """Min-max normalization over rolling window (Stochastic-style).
    COT Index = (current - min_N) / (max_N - min_N) * 100
    100 = most long in N weeks, 0 = most short. NaN when range == 0.
    """
    roll = series.rolling(window, min_periods=window)
    mn   = roll.min()
    mx   = roll.max()
    rng  = mx - mn
    return ((series - mn) / rng * 100).where(rng != 0)

# ─── Formatting helpers ────────────────────────────────────────────────────────

def _fmt_contracts(n: float) -> str:
    n = int(n)
    if abs(n) >= 1_000_000:
        return f"{n/1_000_000:.2f}M"
    if abs(n) >= 1_000:
        return f"{n/1_000:.1f}K"
    return f"{n:,}"


def _signal(idx_val) -> tuple[str, str]:
    if pd.isna(idx_val):
        return "—", C["muted"]
    if idx_val >= 80:
        return "Extreme Long", C["green"]
    if idx_val <= 20:
        return "Extreme Short", C["red"]
    return "Neutral", C["muted"]

# ─── Charts ───────────────────────────────────────────────────────────────────

_AXIS = dict(
    gridcolor=C["border"],
    gridwidth=1,
    zerolinecolor=C["border"],
    tickfont=dict(family="monospace", size=10, color=C["muted"]),
    showgrid=True,
)

_LAYOUT_BASE = dict(
    plot_bgcolor=C["bg"],
    paper_bgcolor=C["bg"],
    margin=dict(l=60, r=20, t=30, b=40),
    legend=dict(
        orientation="h",
        yanchor="bottom", y=1.01,
        xanchor="left",   x=0,
        font=dict(family="monospace", size=11, color=C["muted"]),
        bgcolor="rgba(0,0,0,0)",
    ),
    hovermode="x unified",
    hoverlabel=dict(bgcolor=C["card"], font=dict(family="monospace", size=11)),
)


def plot_net_positioning(df: pd.DataFrame, groups: list[str], x_range=None) -> go.Figure:
    """Raw net contracts (Long − Short).
    Non-Reportable plotted on a separate right Y-axis (much smaller scale).
    Commercials + Non-Commercials share the left Y-axis.
    """
    _RIGHT = "Non-Reportable"
    fig = go.Figure()
    fig.add_hline(y=0, line=dict(color=C["muted"], width=1, dash="dot"))

    for grp in groups:
        cfg    = GROUP_CFG[grp]
        col    = cfg["col"]
        if col not in df.columns:
            continue
        s       = df[col].dropna()
        on_right = grp == _RIGHT
        fig.add_trace(go.Scatter(
            x=s.index, y=s.values,
            name=grp,
            yaxis="y2" if on_right else "y",
            mode="lines",
            line=dict(color=cfg["color"], width=1.8),
            fill="tozeroy",
            fillcolor=cfg["fill"],
            hovertemplate=f"<b>{grp}</b>: %{{y:,.0f}}<extra></extra>",
        ))

    xaxis = dict(**_AXIS, title=None)
    if x_range:
        xaxis["range"] = x_range

    layout = {**_LAYOUT_BASE, "height": 420, "xaxis": xaxis,
              "yaxis": dict(**_AXIS, title="Net Contracts (Long − Short)")}
    layout["margin"] = dict(l=60, r=90, t=30, b=40)   # override: extra right room for y2 label
    if _RIGHT in groups:
        _rc = GROUP_CFG[_RIGHT]["color"]
        layout["yaxis2"] = {
            "overlaying": "y",
            "side": "right",
            "showgrid": False,
            "zeroline": False,
            "tickfont": {"family": "monospace", "size": 10, "color": _rc},
            "title": {"text": "Non-Reportable (right scale)",
                      "font": {"family": "monospace", "size": 10, "color": _rc}},
        }
    fig.update_layout(**layout)
    return fig


def plot_long_short_donuts(df: pd.DataFrame, groups: list[str]) -> go.Figure:
    """Side-by-side donuts (one per group): green=Long %, red=Short %.
    Plain figure — no make_subplots — so domain is fully explicit and consistent.
    """
    n = len(groups)
    if n == 0:
        return go.Figure()

    # Explicit x-domains per column count so donuts never shift
    x_domains = {
        1: [(0.20, 0.80)],
        2: [(0.02, 0.46), (0.54, 0.98)],
        3: [(0.01, 0.31), (0.35, 0.65), (0.69, 0.99)],
    }
    x_doms = x_domains.get(n, [(i/n + 0.01, (i+1)/n - 0.01) for i in range(n)])
    # x-centres for annotations
    xs = [(lo + hi) / 2 for lo, hi in x_doms]

    # y-domain — donut floats in the middle: space above AND below before next section
    Y_DOM = (0.18, 0.88)
    ANN_Y = 0.10   # annotation top sits just below donut bottom

    fig = go.Figure()

    annotations = []
    for i, grp in enumerate(groups):
        cfg   = GROUP_CFG[grp]
        l_col = cfg["long"]
        s_col = cfg["short"]
        l_val = float(df[l_col].iloc[-1]) if l_col in df.columns and len(df) > 0 else 0.0
        s_val = float(df[s_col].iloc[-1]) if s_col in df.columns and len(df) > 0 else 0.0

        fig.add_trace(go.Pie(
            values=[l_val, s_val],
            labels=["Long", "Short"],
            hole=0.58,
            marker_colors=[C["green"], C["red"]],
            marker_line=dict(color=C["bg"], width=3),
            textinfo="percent",
            textfont=dict(family="monospace", size=14, color="#FFFFFF"),
            insidetextfont=dict(family="monospace", size=14, color="#FFFFFF"),
            outsidetextfont=dict(family="monospace", size=14, color="#FFFFFF"),
            hovertemplate="<b>%{label}</b>: %{value:,.0f} (%{percent})<extra></extra>",
            showlegend=(i == 0),
            name=grp,
            domain=dict(x=list(x_doms[i]), y=list(Y_DOM)),
        ))

        # Title above donut
        annotations.append(dict(
            x=xs[i], y=0.92,
            xref="paper", yref="paper",
            xanchor="center", yanchor="bottom",
            text=f"<b>{grp}</b>",
            showarrow=False,
            font=dict(family="monospace", size=12, color=GROUP_CFG[grp]["color"]),
        ))

        # Long / Short raw numbers directly below donut
        annotations.append(dict(
            x=xs[i], y=ANN_Y,
            xref="paper", yref="paper",
            xanchor="center", yanchor="top",
            text=(
                f"<span style='color:{C['green']}'>Long: {_fmt_contracts(l_val)}</span>"
                f" &nbsp;·&nbsp; "
                f"<span style='color:{C['red']}'>Short: {_fmt_contracts(s_val)}</span>"
            ),
            showarrow=False,
            font=dict(family="monospace", size=13, color="#FFFFFF"),
            align="center",
        ))

    fig.update_layout(
        plot_bgcolor=C["bg"],
        paper_bgcolor=C["bg"],
        margin=dict(l=20, r=20, t=30, b=50),
        height=310,
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="top", y=-0.04,
            xanchor="center", x=0.5,
            font=dict(family="monospace", size=11, color=C["muted"]),
            bgcolor="rgba(0,0,0,0)",
        ),
        annotations=annotations,
    )
    return fig


def plot_cot_index(df: pd.DataFrame, groups: list[str], x_range=None) -> go.Figure:
    fig = go.Figure()

    # Overbought / oversold bands
    fig.add_hrect(y0=80, y1=100, fillcolor=C["green_bg"], line_width=0, layer="below")
    fig.add_hrect(y0=0,  y1=20,  fillcolor=C["red_bg"],   line_width=0, layer="below")

    # Threshold lines
    fig.add_hline(y=80, line=dict(color=C["green"], width=1, dash="dot"))
    fig.add_hline(y=20, line=dict(color=C["red"],   width=1, dash="dot"))
    fig.add_hline(y=50, line=dict(color=C["muted"], width=1, dash="dot"))

    # COT Index uses swapped colors vs other charts:
    #   Commercials → blue, Non-Commercials → gray, Non-Reportable → yellow
    _IDX_COLOR = {
        "Commercials":    {"color": "#3B82F6", "fill": "rgba(59,130,246,0.08)"},
        "Non-Commercials":{"color": "#6B7280", "fill": "rgba(107,114,128,0.08)"},
        "Non-Reportable": {"color": "#EAB308", "fill": "rgba(234,179,8,0.08)"},
    }

    # One line per group — each percentile calculated independently from its own history
    for grp in groups:
        cfg  = GROUP_CFG[grp]
        icfg = _IDX_COLOR.get(grp, cfg)   # fall back to GROUP_CFG for unknown groups
        col  = cfg["col"]
        if col not in df.columns:
            continue
        idx = calc_cot_index(df[col]).dropna()
        if idx.empty:
            continue

        fig.add_trace(go.Scatter(
            x=idx.index, y=idx.values,
            name=grp,
            mode="lines",
            line=dict(color=icfg["color"], width=2),
            fill="tozeroy" if len(groups) == 1 else "none",
            fillcolor=icfg["fill"] if len(groups) == 1 else None,
            hovertemplate=f"<b>{grp}</b>: %{{y:.1f}}<extra></extra>",
        ))

    xaxis_cot = dict(**_AXIS, title=None)
    if x_range:
        xaxis_cot["range"] = x_range
    fig.update_layout(
        **_LAYOUT_BASE,
        height=460,
        xaxis=xaxis_cot,
        yaxis=dict(**_AXIS, title=None, range=[-2, 105], tickvals=[0, 20, 50, 80, 100]),
        showlegend=True,
    )
    return fig

# ─── Divergence Screener ──────────────────────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner=False)
def build_divergence_table(_raw: pd.DataFrame) -> pd.DataFrame:
    """Compute Commercials vs Non-Reportable COT Index divergence for every market.
    Filters to notable rows only: divergence > 70 OR either group in extreme territory
    (Comm or NRept >= 75 or <= 25). Returns top 10 by divergence.
    """
    _cache_version = 3
    rows = []
    for cat, markets in MARKET_GROUPS.items():
        for display, cftc_name in markets.items():
            df = get_market_data(_raw, cftc_name)
            if df.empty:
                continue
            comm_s  = df["Net_Comm"].dropna()  if "Net_Comm"  in df.columns else pd.Series(dtype=float)
            nrept_s = df["Net_Small"].dropna() if "Net_Small" in df.columns else pd.Series(dtype=float)
            if comm_s.empty or nrept_s.empty:
                continue
            comm_idx  = calc_cot_index(comm_s)
            nrept_idx = calc_cot_index(nrept_s)
            comm_val  = float(comm_idx.iloc[-1])  if not comm_idx.dropna().empty  else float("nan")
            nrept_val = float(nrept_idx.iloc[-1]) if not nrept_idx.dropna().empty else float("nan")
            if pd.isna(comm_val) or pd.isna(nrept_val):
                continue
            div = abs(comm_val - nrept_val)
            notable = (
                div > 70
                or comm_val  >= 75 or comm_val  <= 25
                or nrept_val >= 75 or nrept_val <= 25
            )
            if not notable:
                continue
            rows.append({
                "Market":     display,
                "Category":   cat,
                "Comm_COT":   comm_val,
                "NRept_COT":  nrept_val,
                "Divergence": div,
            })
    df_out = (
        pd.DataFrame(rows)
        .sort_values("Divergence", ascending=False)
        .head(10)
        .reset_index(drop=True)
    )
    return df_out


def _screener_html(table: pd.DataFrame) -> str:
    def val_color(v):
        return C["green"] if v >= 75 else (C["red"] if v <= 25 else C["text"])

    header = "".join(
        f"<th style='text-align:{align};color:{C['muted']};font-size:11px;"
        f"text-transform:uppercase;letter-spacing:1px;padding:8px 14px;"
        f"border-bottom:1px solid {C['border']};white-space:nowrap;'>{lbl}</th>"
        for lbl, align in [
            ("Market", "left"), ("Cat", "left"),
            ("Commercials COT", "right"), ("Non-Reportable COT", "right"),
            ("Divergence", "right"),
        ]
    )

    body = ""
    for _, row in table.iterrows():
        cv, nv = row["Comm_COT"], row["NRept_COT"]
        div    = row["Divergence"]
        # Subtle row tint when either group is in extreme territory
        if cv >= 75 or nv >= 75:
            row_bg = "rgba(26,155,106,0.05)"
        elif cv <= 25 or nv <= 25:
            row_bg = "rgba(240,82,98,0.05)"
        else:
            row_bg = "transparent"

        body += (
            f"<tr style='background:{row_bg};border-bottom:1px solid {C['border']};'>"
            f"<td style='padding:7px 14px;color:{C['text']};font-weight:600;'>{row['Market']}</td>"
            f"<td style='padding:7px 14px;color:{C['muted']};font-size:11px;'>{row['Category']}</td>"
            f"<td style='padding:7px 14px;color:{val_color(cv)};font-weight:700;text-align:right;'>{cv:.1f}</td>"
            f"<td style='padding:7px 14px;color:{val_color(nv)};font-weight:700;text-align:right;'>{nv:.1f}</td>"
            f"<td style='padding:7px 14px;color:{C['teal']};font-weight:700;text-align:right;'>{div:.1f}</td>"
            f"</tr>"
        )

    return (
        f"<div style='background:{C['card']};border:1px solid {C['border']};"
        f"border-radius:10px;overflow:hidden;margin-top:4px;'>"
        f"<table style='width:100%;border-collapse:collapse;"
        f"font-family:monospace;font-size:12px;'>"
        f"<thead><tr>{header}</tr></thead>"
        f"<tbody>{body}</tbody>"
        f"</table></div>"
    )


# ─── Main App ─────────────────────────────────────────────────────────────────

def main():
    st.set_page_config(
        page_title="COT Analysis · Trading Terminal",
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
      div[data-baseweb="select"] > div {{
          background:{C['panel']} !important;
          border:1px solid {C['border']} !important;
          border-radius:8px !important;
          color:{C['text']};
      }}
      div[data-baseweb="select"] svg {{ fill:{C['muted']}; }}
      div[data-baseweb="popover"] ul {{
          background:{C['panel']} !important;
          border:1px solid {C['border']} !important;
      }}
      div[data-baseweb="popover"] li:hover {{
          background:{C['dim']} !important;
      }}
      div[data-baseweb="input"] > div {{
          background:{C['panel']} !important;
          border:1px solid {C['border']} !important;
          border-radius:8px !important;
      }}
      input, textarea {{ color:{C['text']} !important; }}
      .stMainBlockContainer {{ padding-top:3.5rem !important; }}
      div[data-testid="stRadio"] > div[role="radiogroup"] {{
          display:flex; flex-wrap:wrap; gap:4px; margin-top:2px;
      }}
      div[data-testid="stRadio"] label {{
          background:{C['dim']} !important;
          border:1px solid {C['border']} !important;
          border-radius:5px !important;
          padding:2px 8px !important;
          cursor:pointer;
          font-family:monospace;
          font-size:11px !important;
          color:{C['muted']} !important;
          margin:0 !important;
          line-height:1.6 !important;
      }}
      div[data-testid="stRadio"] label:has(input:checked) {{
          background:{C['teal']} !important;
          border-color:{C['teal']} !important;
          color:#0a0c10 !important;
          font-weight:700 !important;
      }}
      div[data-testid="stRadio"] label span:last-child {{ pointer-events:none; }}
      div[data-testid="stRadio"] input[type="radio"] {{ display:none; }}
      div[data-testid="stMultiSelect"] > div {{
          background:{C['panel']} !important;
          border:1px solid {C['border']} !important;
          border-radius:8px !important;
      }}
      span[data-baseweb="tag"] {{
          background:{C['dim']} !important;
          border:1px solid {C['border']} !important;
          color:{C['text']} !important;
      }}
      p, span, label {{ color:{C['text']}; }}
      hr {{ border-color:{C['border']}; }}
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
    </style>
    """, unsafe_allow_html=True)

    # ── Title row ─────────────────────────────────────────────────────────────
    col_back, col_title, _ = st.columns([2, 5, 2])
    with col_back:
        st.markdown("<div style='margin-top:6px;'>", unsafe_allow_html=True)
        if st.button("← Back to Hub", key="back_btn"):
            st.switch_page("app.py")
        st.markdown("</div>", unsafe_allow_html=True)
    with col_title:
        st.markdown(
            f"<div style='margin-bottom:18px;text-align:center;'>"
            f"<div style='font-size:20px;font-weight:700;color:{C['text']};"
            f"font-family:monospace;letter-spacing:-0.5px;line-height:1.2;'>"
            f"COT Analysis</div>"
            f"<div style='font-size:11px;color:{C['muted']};font-family:monospace;margin-top:3px;'>"
            f"CFTC Commitments of Traders · Weekly Positioning</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

    # ── Controls row ──────────────────────────────────────────────────────────
    col_cat, col_mkt, col_grp = st.columns([1.4, 1.8, 3.8])

    with col_cat:
        st.markdown(f"<div style='font-size:10px;color:{C['muted']};font-family:monospace;text-transform:uppercase;letter-spacing:1px;margin-bottom:4px;'>Category</div>", unsafe_allow_html=True)
        category = st.selectbox("Category", list(MARKET_GROUPS.keys()), label_visibility="collapsed", key="cot_cat")

    with col_mkt:
        st.markdown(f"<div style='font-size:10px;color:{C['muted']};font-family:monospace;text-transform:uppercase;letter-spacing:1px;margin-bottom:4px;'>Market</div>", unsafe_allow_html=True)
        market = st.selectbox("Market", list(MARKET_GROUPS[category].keys()), label_visibility="collapsed", key="cot_mkt")

    with col_grp:
        st.markdown(f"<div style='font-size:10px;color:{C['muted']};font-family:monospace;text-transform:uppercase;letter-spacing:1px;margin-bottom:4px;'>Groups</div>", unsafe_allow_html=True)
        groups = st.multiselect(
            "Groups",
            list(GROUP_CFG.keys()),
            default=["Commercials", "Non-Reportable"],
            label_visibility="collapsed",
            key="cot_grp",
        )

    # ── Fetch data ────────────────────────────────────────────────────────────
    cftc_name = MARKET_GROUPS[category][market]   # exact string from the CSV

    with st.spinner("Loading CFTC data…"):
        raw, fetch_errors = fetch_cot_raw()
        df = get_market_data(raw, cftc_name)

    if df.empty or not any(GROUP_CFG[g]["col"] in df.columns for g in (groups or ["Commercials"])):
        st.markdown(
            f"<div style='padding:32px;text-align:center;color:{C['muted']};font-family:monospace;'>"
            f"No COT data available for <b style='color:{C['text']}'>{market}</b>. "
            f"CFTC data may be unavailable or the market name has changed.</div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            f"<div style='margin-top:48px;padding-top:16px;border-top:1px solid {C['border']};"
            f"text-align:center;font-size:11px;color:{C['muted']};font-family:monospace;'>"
            f"Built by @realedgetraders</div>",
            unsafe_allow_html=True,
        )
        return

    last_date = df.index[-1].strftime("%d %b %Y")

    # ── Info line ─────────────────────────────────────────────────────────────
    st.markdown(
        f"<div style='font-size:11px;color:{C['muted']};font-family:monospace;margin-bottom:8px;'>"
        f"{market} ({category}) &nbsp;·&nbsp; Full History (2001–present) &nbsp;·&nbsp; "
        f"Last Report: {last_date} &nbsp;·&nbsp; Source: CFTC</div>",
        unsafe_allow_html=True,
    )

    active_groups = groups if groups else ["Commercials"]

    # ── Signal cards row (below controls) ─────────────────────────────────────
    sig_cols = st.columns(len(active_groups))
    for i, grp in enumerate(active_groups):
        cfg = GROUP_CFG[grp]
        col = cfg["col"]
        if col in df.columns:
            idx_series = calc_cot_index(df[col])
            cur_idx    = float(idx_series.iloc[-1]) if not idx_series.empty else float("nan")
        else:
            cur_idx = float("nan")
        sig_text, sig_color = _signal(cur_idx)
        idx_str = f"{cur_idx:.1f}" if cur_idx == cur_idx else "—"   # nan check
        # Commercials → blue value, Non-Reportable → yellow value; others use signal color
        _VALUE_OVERRIDE = {"Commercials": "#3B82F6", "Non-Reportable": "#EAB308"}
        val_color = _VALUE_OVERRIDE.get(grp, sig_color)
        with sig_cols[i]:
            st.markdown(
                f"<div style='background:{C['card']};border:1px solid {C['border']};"
                f"border-radius:8px;padding:10px 14px;text-align:center;margin-bottom:10px;'>"
                f"<div style='font-size:10px;color:{cfg['color']};font-family:monospace;"
                f"font-weight:700;text-transform:uppercase;letter-spacing:1px;margin-bottom:4px;'>{grp}</div>"
                f"<div style='font-size:22px;font-weight:700;color:{val_color};"
                f"font-family:monospace;line-height:1.1;'>{idx_str}</div>"
                f"<div style='font-size:10px;color:{sig_color};font-family:monospace;"
                f"margin-top:2px;'>{sig_text}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

    # ── View window: always last 3 years ─────────────────────────────────────
    _three_yr_start = (datetime.today().replace(year=datetime.today().year - 3)).strftime("%Y-%m-%d")
    _today          = datetime.today().strftime("%Y-%m-%d")
    x_range         = [_three_yr_start, _today]

    # ── Chart 1 — COT Index ───────────────────────────────────────────────────
    st.markdown(
        f"<div style='font-size:11px;color:{C['muted']};font-family:monospace;"
        f"text-transform:uppercase;letter-spacing:1px;margin-bottom:4px;'>"
        f"COT Index &nbsp;"
        f"<span style='font-size:9px;'>(26-week percentile rank · green ≥ 80 extreme long · red ≤ 20 extreme short)</span></div>",
        unsafe_allow_html=True,
    )
    st.plotly_chart(plot_cot_index(df, active_groups, x_range=x_range), use_container_width=True, config={"displayModeBar": False})

    # ── Chart 2 — Long vs Short Donuts ───────────────────────────────────────
    st.markdown(
        f"<div style='font-size:11px;color:{C['muted']};font-family:monospace;"
        f"text-transform:uppercase;letter-spacing:1px;margin-top:8px;margin-bottom:4px;'>"
        f"Long vs Short — Latest Report "
        f"<span style='font-size:9px;'>(green = long · red = short · % of total open interest by group)</span></div>",
        unsafe_allow_html=True,
    )
    st.plotly_chart(plot_long_short_donuts(df, active_groups), use_container_width=True, config={"displayModeBar": False})

    # ── Chart 3 — Net Positioning ─────────────────────────────────────────────
    st.markdown(
        f"<div style='font-size:11px;color:{C['muted']};font-family:monospace;"
        f"text-transform:uppercase;letter-spacing:1px;margin-top:8px;margin-bottom:4px;'>"
        f"Net Positioning "
        f"<span style='font-size:9px;'>(Long − Short · raw contracts)</span></div>",
        unsafe_allow_html=True,
    )
    st.plotly_chart(plot_net_positioning(df, active_groups, x_range=x_range), use_container_width=True, config={"displayModeBar": False})

    # ── COT Divergence Screener ───────────────────────────────────────────────
    st.markdown(
        f"<div style='font-size:11px;color:{C['muted']};font-family:monospace;"
        f"text-transform:uppercase;letter-spacing:1px;margin-top:32px;margin-bottom:4px;'>"
        f"COT Divergence Screener "
        f"<span style='font-size:9px;'>(top 10 · divergence &gt;70 or extreme reading ≥75/≤25 · sorted by divergence)</span></div>",
        unsafe_allow_html=True,
    )
    with st.spinner("Computing screener…"):
        screener_df = build_divergence_table(raw)
    if not screener_df.empty:
        st.markdown(_screener_html(screener_df), unsafe_allow_html=True)

    # ── Footer ────────────────────────────────────────────────────────────────
    st.markdown(
        f"<div style='margin-top:48px;padding-top:16px;border-top:1px solid {C['border']};"
        f"text-align:center;font-size:11px;color:{C['muted']};font-family:monospace;'>"
        f"Built by @realedgetraders</div>",
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
