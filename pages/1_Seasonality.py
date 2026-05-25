"""
Trading Analytics Terminal — Module 1: Seasonal Analysis
Seasonax-style UX
"""

import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, timedelta, date as dt_date
from dateutil.relativedelta import relativedelta

# DOY → "Mon DD" label for every day of a non-leap year (index 0 = DOY 1)
_DOY_LABELS: list[str] = [
    (datetime(2001, 1, 1) + timedelta(days=i)).strftime("%b %d")
    for i in range(365)
]

# ─── Asset Universe ───────────────────────────────────────────────────────────

FOREX_PAIRS = {
    # Majors
    "EUR/USD": "EURUSD=X",
    "GBP/USD": "GBPUSD=X",
    "USD/JPY": "USDJPY=X",
    "USD/CHF": "USDCHF=X",
    "AUD/USD": "AUDUSD=X",
    "NZD/USD": "NZDUSD=X",
    "USD/CAD": "USDCAD=X",
    # EUR Crosses
    "EUR/GBP": "EURGBP=X",
    "EUR/JPY": "EURJPY=X",
    "EUR/CHF": "EURCHF=X",
    "EUR/AUD": "EURAUD=X",
    "EUR/NZD": "EURNZD=X",
    "EUR/CAD": "EURCAD=X",
    # GBP Crosses
    "GBP/JPY": "GBPJPY=X",
    "GBP/CHF": "GBPCHF=X",
    "GBP/AUD": "GBPAUD=X",
    "GBP/NZD": "GBPNZD=X",
    "GBP/CAD": "GBPCAD=X",
    # Other Crosses
    "AUD/JPY": "AUDJPY=X",
    "AUD/NZD": "AUDNZD=X",
    "AUD/CAD": "AUDCAD=X",
    "AUD/CHF": "AUDCHF=X",
    "NZD/JPY": "NZDJPY=X",
    "NZD/CAD": "NZDCAD=X",
    "NZD/CHF": "NZDCHF=X",
    "CAD/JPY": "CADJPY=X",
    "CAD/CHF": "CADCHF=X",
    "CHF/JPY": "CHFJPY=X",
}

RADAR_ASSETS: dict[str, tuple[str, str]] = {
    # Forex — Majors
    "EUR/USD": ("EURUSD=X", "Forex"),
    "GBP/USD": ("GBPUSD=X", "Forex"),
    "USD/JPY": ("USDJPY=X", "Forex"),
    "USD/CHF": ("USDCHF=X", "Forex"),
    "AUD/USD": ("AUDUSD=X", "Forex"),
    "NZD/USD": ("NZDUSD=X", "Forex"),
    "USD/CAD": ("USDCAD=X", "Forex"),
    # Forex — Crosses
    "EUR/JPY": ("EURJPY=X", "Forex"),
    "EUR/GBP": ("EURGBP=X", "Forex"),
    "EUR/AUD": ("EURAUD=X", "Forex"),
    "EUR/CAD": ("EURCAD=X", "Forex"),
    "GBP/JPY": ("GBPJPY=X", "Forex"),
    "AUD/JPY": ("AUDJPY=X", "Forex"),
    # Commodities
    "Gold":    ("GC=F",   "Commodity"),
    "Silver":  ("SI=F",   "Commodity"),
    "Oil WTI": ("CL=F",   "Commodity"),
    # Indices
    "S&P 500": ("^GSPC",  "Index"),
    "Nasdaq":  ("^IXIC",  "Index"),
    "Dow":     ("^DJI",   "Index"),
}

# DOY tick positions for each month (non-leap reference year 2001)
MONTH_DOYS   = [1, 32, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335]
MONTH_LABELS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# Reference year for seasonal curve x-axis (non-leap so Feb 29 never appears)
_REF_YEAR = 2023

# ─── Theme ────────────────────────────────────────────────────────────────────

C = {
    "bg":       "#0d0d0d",
    "card":     "#141414",
    "border":   "#252525",
    "panel":    "#111111",
    "text":     "#e8e8e8",
    "muted":    "#666666",
    "dim":      "#171717",
    "teal":     "#e63946",
    "teal_bg":  "rgba(230, 57, 70, 0.14)",
    "teal_dim": "rgba(230, 57, 70, 0.06)",
    "green":    "#00c48c",
    "green_bg": "rgba(0, 196, 140, 0.09)",
    "red":      "#f05262",
    "red_bg":   "rgba(240, 82, 98, 0.09)",
    "yellow":   "#f0b429",
    "blue":     "#4f8ef7",
}

# ─── Data Layer ───────────────────────────────────────────────────────────────

# Synthetic cross-rate map: cross_key → (numerator_USD_pair, denominator_USD_pair)
# Cross = numerator / denominator   (both expressed as XXX/USD)
SYNTHETIC_CROSSES = {
    "GBPAUD": ("GBPUSD", "AUDUSD"),
    "GBPCAD": ("GBPUSD", "CADUSD"),
    "GBPCHF": ("GBPUSD", "CHFUSD"),
    "GBPJPY": ("GBPUSD", "JPYUSD"),
    "GBPNZD": ("GBPUSD", "NZDUSD"),
    "EURAUD": ("EURUSD", "AUDUSD"),
    "EURCAD": ("EURUSD", "CADUSD"),
    "EURCHF": ("EURUSD", "CHFUSD"),
    "EURJPY": ("EURUSD", "JPYUSD"),
    "EURGBP": ("EURUSD", "GBPUSD"),
    "EURNZD": ("EURUSD", "NZDUSD"),
    "AUDCAD": ("AUDUSD", "CADUSD"),
    "AUDCHF": ("AUDUSD", "CHFUSD"),
    "AUDJPY": ("AUDUSD", "JPYUSD"),
    "AUDNZD": ("AUDUSD", "NZDUSD"),
    "CADCHF": ("CADUSD", "CHFUSD"),
    "CADJPY": ("CADUSD", "JPYUSD"),
    "NZDCAD": ("NZDUSD", "CADUSD"),
    "NZDCHF": ("NZDUSD", "CHFUSD"),
    "NZDJPY": ("NZDUSD", "JPYUSD"),
    "CHFJPY": ("CHFUSD", "JPYUSD"),
}

# yfinance tickers for each XXX/USD leg
_USD_YF = {
    "GBPUSD": "GBPUSD=X", "EURUSD": "EURUSD=X",
    "AUDUSD": "AUDUSD=X", "NZDUSD": "NZDUSD=X",
    "CADUSD": "CAD=X",    "CHFUSD": "CHF=X",
    "JPYUSD": "JPY=X",
}

def _yf_close(yf_ticker: str, start: datetime, end: datetime) -> pd.Series:
    """Download daily Close from yfinance, apply -1d shift for forex, return Series."""
    raw = yf.download(yf_ticker, start=start, end=end,
                      auto_adjust=False, progress=False)
    if raw.empty:
        return pd.Series(dtype=float)
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)
    s = raw["Close"].dropna()
    s.index = pd.to_datetime(s.index).tz_localize(None) - pd.Timedelta(days=1)
    return s

def _yf_ohlc(yf_ticker: str, start: datetime, end: datetime,
             is_forex: bool = True) -> pd.DataFrame:
    """Download daily OHLC from yfinance. Apply -1d shift only for forex pairs."""
    raw = yf.download(yf_ticker, start=start, end=end,
                      auto_adjust=False, progress=False)
    if raw.empty:
        return pd.DataFrame()
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)
    df = raw[["Open", "High", "Low", "Close"]].copy().dropna()
    if is_forex:
        df.index = pd.to_datetime(df.index).tz_localize(None) - pd.Timedelta(days=1)
    else:
        df.index = pd.to_datetime(df.index).tz_localize(None)
    return df

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_data(ticker: str, years: int) -> pd.DataFrame:
    end   = datetime.today()
    start = end - timedelta(days=int(years * 365.25))
    df    = pd.DataFrame()

    # ── Synthetic cross-rate (20+ years via USD major legs) ──────────────────
    cross_key = ticker.replace("=X", "").upper()
    if cross_key in SYNTHETIC_CROSSES:
        num_key, den_key = SYNTHETIC_CROSSES[cross_key]
        num_s = _yf_close(_USD_YF[num_key], start, end)
        den_s = _yf_close(_USD_YF[den_key], start, end)
        # Align on common dates and divide
        common = num_s.index.intersection(den_s.index)
        if len(common) > 50:
            close = (num_s.loc[common] / den_s.loc[common]).dropna()
            df = close.to_frame(name="Close")
            df["Open"]  = df["Close"]   # synthetic: no reliable intraday spread
            df["High"]  = df["Close"]
            df["Low"]   = df["Close"]

    # ── Direct yfinance (majors, indices, commodities) ────────────────────────
    if df.empty:
        is_forex = ticker.endswith("=X")
        df = _yf_ohlc(ticker, start, end, is_forex=is_forex)

    if df.empty:
        return pd.DataFrame()

    df = df[["Open", "High", "Low", "Close"]].copy()
    df["Win"]        = (df["Close"] > df["Open"]).astype(int)
    df["Return"]     = df["Close"].pct_change()
    df["LogReturn"]  = np.log(df["Close"] / df["Close"].shift(1))
    df.dropna(inplace=True)
    df["Year"]       = df.index.year
    df["Month"]      = df.index.month
    df["DayOfMonth"] = df.index.day
    df["DOY"]        = df.index.dayofyear
    df["Weekday"]    = df.index.weekday
    return df

# ─── Analysis Layer ───────────────────────────────────────────────────────────

def calc_overall_stats(df: pd.DataFrame) -> dict:
    n       = len(df)
    years   = (df.index[-1] - df.index[0]).days / 365.25
    total_r = df["Close"].iloc[-1] / df["Close"].iloc[0] - 1
    ann_r   = ((1 + total_r) ** (1 / years) - 1) * 100 if years > 0 else 0
    sharpe  = (df["Return"].mean() / df["Return"].std() * np.sqrt(252)
               if df["Return"].std() > 0 else 0)
    return {
        "n":          n,
        "win_rate":   df["Win"].mean() * 100,
        "avg_return": df["Return"].mean() * 100,
        "ann_return": ann_r,
        "sharpe":     sharpe,
        "date_start": df.index[0],
        "date_end":   df.index[-1],
    }

def calc_seasonal_curve(df: pd.DataFrame):
    """
    Month/Day methodology — matches Seasonax exactly:
    1. Exclude the current (incomplete) calendar year.
    2. Normalize each year's Close to 100 at the first trading day.
    3. Forward-fill each year's prices to ALL calendar dates (weekends included).
    4. Group by (month, day) and average across years (≥2 observations).
    5. Map results to _REF_YEAR (2023, non-leap) for the x-axis.
    Returns (mean_df, year_paths) where:
      mean_df    — DataFrame with columns: date (Timestamp), index, n
      year_paths — dict {year: {"dates": [Timestamp,...], "vals": [float,...]}}
                   (trading days only, mapped to _REF_YEAR month/day)
    """
    current_year = dt_date.today().year
    by_md: dict[tuple, list[float]] = {}
    year_paths: dict[int, dict] = {}

    for year, grp in df.groupby("Year"):
        if int(year) >= current_year:
            continue
        grp = grp.sort_index().dropna(subset=["Close"])
        if len(grp) < 2:
            continue
        base = float(grp["Close"].iloc[0])
        if base == 0:
            continue

        # Normalize to 100 at first trading day
        norm = grp["Close"] / base * 100.0

        # Forward-fill to every calendar date in this year (for the mean)
        full_idx = pd.date_range(f"{int(year)}-01-01", f"{int(year)}-12-31", freq="D")
        norm_full = norm.reindex(full_idx).ffill().dropna()
        for ts, val in norm_full.items():
            m, d = ts.month, ts.day
            if m == 2 and d == 29:
                continue  # skip leap day — _REF_YEAR has no Feb 29
            by_md.setdefault((m, d), []).append(float(val))

        # Individual year path: trading days only, mapped to _REF_YEAR
        yr_dates, yr_vals = [], []
        for ts, val in norm.items():
            m, d = ts.month, ts.day
            if m == 2 and d == 29:
                continue
            try:
                yr_dates.append(pd.Timestamp(_REF_YEAR, m, d))
                yr_vals.append(float(val))
            except Exception:
                continue
        year_paths[int(year)] = {"dates": yr_dates, "vals": yr_vals}

    if not by_md:
        return pd.DataFrame(), {}

    rows = []
    for (m, d), vals in by_md.items():
        if len(vals) < 2:
            continue
        try:
            ref_date = pd.Timestamp(_REF_YEAR, m, d)
        except Exception:
            continue
        rows.append({"date": ref_date, "index": float(np.mean(vals)), "n": len(vals)})

    if not rows:
        return pd.DataFrame(), {}

    mean_df = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)

    # Re-normalize so the mean of the entire curve = 100 (Seasonax methodology)
    curve_mean = mean_df["index"].mean()
    mean_df["index"] = (mean_df["index"] / curve_mean) * 100.0

    # Smooth with a 3-day centered rolling average
    mean_df["index"] = (
        mean_df["index"].rolling(window=3, center=True, min_periods=1).mean()
    )

    return mean_df, year_paths

def _doy(month: int, day: int) -> int:
    return datetime(2001, month, day).timetuple().tm_yday

def calc_pattern_analysis(df: pd.DataFrame,
                           start_month: int, start_day: int,
                           end_month: int,   end_day: int):
    """
    Returns (stats_dict, year_table_df).
    Handles cross-year patterns (e.g., Nov → Feb).
    Entry price = Close of the trading day BEFORE the first day of the window (Seasonax method).
    Skips current year and any year where entry/exit dates fall outside available data.
    """
    s_doy = _doy(start_month, start_day)
    e_doy = _doy(end_month,   end_day)
    cross = s_doy > e_doy

    current_year = dt_date.today().year
    data_start   = df.index[0]   # earliest date in dataset
    rows  = []
    years = sorted(df["Year"].unique())

    for year in years:
        # Skip current (incomplete) year
        if year >= current_year:
            continue

        if cross:
            if year + 1 not in df["Year"].values:
                continue
            pat = pd.concat([
                df[(df["Year"] == year)     & (df["DOY"] >= s_doy)],
                df[(df["Year"] == year + 1) & (df["DOY"] <= e_doy)],
            ]).sort_index()
            label = f"{year}/{str(year+1)[-2:]}"
        else:
            pat   = df[(df["Year"] == year) & (df["DOY"] >= s_doy) & (df["DOY"] <= e_doy)]
            label = str(year)

        if len(pat) < 2:
            continue

        # Skip if window starts before data begins
        if pat.index[0] < data_start:
            continue

        sp  = float(pat["Close"].iloc[0])   # entry = Close on entry date (or next trading day)
        ep  = float(pat["Close"].iloc[-1])  # exit  = Close on exit  date (or prev trading day)
        pnl = ep - sp
        pct = (ep / sp - 1) * 100

        rows.append({
            "Year":        label,
            "Start Date":  pat.index[0].strftime("%b %d, %Y"),
            "Start Price": sp,
            "End Date":    pat.index[-1].strftime("%b %d, %Y"),
            "End Price":   ep,
            "Profit":      round(pnl, 6),
            "Profit %":    round(pct, 2),
            "Max Rise %":  round((float(pat["High"].max()) / sp - 1) * 100, 2),
            "Max Drop %":  round((float(pat["Low"].min())  / sp - 1) * 100, 2),
            "_hold":       len(pat),
        })

    if not rows:
        return None, None

    table   = pd.DataFrame(rows)
    profits = table["Profit %"]
    hold    = table["_hold"].mean()
    std     = profits.std()

    gains  = int((profits > 0).sum())
    losses = int((profits <= 0).sum())

    # Current streak (from most-recent year backwards)
    profit_list = profits.tolist()
    streak_dir  = "W" if profit_list[-1] > 0 else "L"
    streak_cnt  = 0
    for p in reversed(profit_list):
        if (p > 0) == (streak_dir == "W"):
            streak_cnt += 1
        else:
            break

    # Calendar days for the pattern window (used for annualisation)
    if cross:
        duration_days = max(1, 365 - s_doy + e_doy)
    else:
        duration_days = max(1, e_doy - s_doy)

    avg_ret_dec = profits.mean() / 100
    ann_ret     = ((1 + avg_ret_dec) ** (365.0 / duration_days) - 1) * 100

    stats = {
        "avg_ret":    profits.mean(),
        "med_ret":    profits.median(),
        "win_rate":   (profits > 0).mean() * 100,
        "sharpe":     profits.mean() / std if std > 0 else 0,
        "ann_ret":    ann_ret,
        "ann_label":  "Ann. Return (Long)" if ann_ret >= 0 else "Ann. Return (Short)",
        "n":          len(table),
        "hold":       hold,
        "gains":      gains,
        "losses":     losses,
        "best":       float(profits.max()),
        "worst":      float(profits.min()),
        "std_ret":    float(std),
        "streak":     streak_cnt,
        "streak_dir": streak_dir,
    }

    # Rest-of-year avg return
    rest_rows = []
    for year in years:
        yr_df = df[df["Year"] == year]
        if cross:
            rest = yr_df[(yr_df["DOY"] > e_doy) & (yr_df["DOY"] < s_doy)]
        else:
            rest = yr_df[(yr_df["DOY"] < s_doy) | (yr_df["DOY"] > e_doy)]
        if len(rest) >= 2:
            sp = float(rest["Open"].iloc[0])
            ep = float(rest["Close"].iloc[-1])
            rest_rows.append((ep / sp - 1) * 100)
    stats["rest_ret"] = float(np.mean(rest_rows)) if rest_rows else 0.0

    display_table = table.drop(columns=["_hold"])
    return stats, display_table


@st.cache_data(ttl=3600, show_spinner=False)
def calc_radar(today_str: str) -> pd.DataFrame:
    today    = datetime.strptime(today_str, "%Y-%m-%d")
    fallback = today + timedelta(days=31)   # fixed 30d window used when no pattern qualifies

    rows = []
    for display, (ticker, cat) in RADAR_ASSETS.items():
        df = fetch_data(ticker, 10)
        if df.empty:
            continue

        # ── Scan all window combinations for the best qualifying pattern ───────
        best: dict | None = None
        for start_off in range(-3, 8):           # today-3d … today+7d as window start
            win_start = today + timedelta(days=start_off)
            for win_len in (14, 21, 30):
                win_end = win_start + timedelta(days=win_len)
                if win_end < today:              # window must overlap with today
                    continue
                stats, _ = calc_pattern_analysis(
                    df,
                    win_start.month, win_start.day,
                    win_end.month,   win_end.day,
                )
                if stats is None or stats["n"] < 7:
                    continue
                lp   = stats["win_rate"]
                if 30 < lp < 70:               # only extreme signals qualify
                    continue
                dist = abs(lp - 50)
                if best is None or dist > best["dist"]:
                    best = {
                        "dist":      dist,
                        "long_pct":  lp,
                        "avg_ret":   stats["avg_ret"],
                        "sharpe":    stats["sharpe"],
                        "win_start": win_start,
                        "win_end":   win_end,
                        "win_len":   win_len,
                    }

        # ── Fall back to fixed 30d if no window qualifies ─────────────────────
        if best is None:
            stats, _ = calc_pattern_analysis(
                df, today.month, today.day, fallback.month, fallback.day
            )
            if stats is None:
                continue
            lp = stats["win_rate"]
            rows.append({
                "Asset":       display,
                "Category":    cat,
                "Long %":      round(lp, 1),
                "Avg Return":  round(stats["avg_ret"], 2),
                "Win Rate":    round(lp, 1),
                "Sharpe":      round(stats["sharpe"], 2),
                "_dist50":     abs(lp - 50),
                "_qualified":  False,
                "Window":      f"{today.strftime('%d.%m')} – {fallback.strftime('%d.%m')}",
                "Days":        "30d",
            })
        else:
            rows.append({
                "Asset":       display,
                "Category":    cat,
                "Long %":      round(best["long_pct"], 1),
                "Avg Return":  round(best["avg_ret"], 2),
                "Win Rate":    round(best["long_pct"], 1),
                "Sharpe":      round(best["sharpe"], 2),
                "_dist50":     best["dist"],
                "_qualified":  True,
                "Window":      f"{best['win_start'].strftime('%d.%m')} – {best['win_end'].strftime('%d.%m')}",
                "Days":        f"{best['win_len']}d",
            })

    if not rows:
        return pd.DataFrame()
    return (
        pd.DataFrame(rows)
        .sort_values(["_qualified", "_dist50"], ascending=[False, False])
        .reset_index(drop=True)
    )


# ─── Visualization Layer ──────────────────────────────────────────────────────

def plot_seasonal_curve(curve_df: pd.DataFrame,
                        start_month: int | None = None, start_day: int | None = None,
                        end_month:   int | None = None, end_day:   int | None = None,
                        display_name: str = "",
                        years: int = 10,
                        date_start: str = "", date_end: str = "",
                        year_paths: dict | None = None) -> go.Figure:
    fig = go.Figure()

    dates   = curve_df["date"].tolist()   # pd.Timestamps in _REF_YEAR
    index_y = curve_df["index"].tolist()
    ref_year = dates[0].year if dates else _REF_YEAR

    hover_dates = [d.strftime("%b %d") for d in dates]

    # Y-axis range: tight around the actual data with small padding
    y_min = min(index_y)
    y_max = max(index_y)
    y_pad = (y_max - y_min) * 0.12 or 0.05
    y_range = [y_min - y_pad, y_max + y_pad]

    # Month tick positions: first date of each month appearing in curve_df
    seen_months: set[int] = set()
    tick_vals: list[str] = []
    tick_text: list[str] = []
    for d in dates:
        if d.month not in seen_months:
            seen_months.add(d.month)
            tick_vals.append(d.isoformat())
            tick_text.append(d.strftime("%b"))

    # Pattern window: convert (month, day) → date string in ref_year
    has_pattern = all(v is not None for v in [start_month, start_day, end_month, end_day])
    s_date = e_date = None
    if has_pattern:
        try:
            s_date = pd.Timestamp(ref_year, start_month, start_day)
        except Exception:
            pass
        try:
            e_date = pd.Timestamp(ref_year, end_month, end_day)
        except Exception:
            pass
        if s_date is not None and e_date is not None:
            x_min = pd.Timestamp(ref_year, 1, 1).isoformat()
            x_max = pd.Timestamp(ref_year, 12, 31).isoformat()
            shade_kw = dict(fillcolor="rgba(255,255,255,0.05)", layer="below", line_width=0)
            if s_date <= e_date:
                fig.add_vrect(x0=s_date.isoformat(), x1=e_date.isoformat(), **shade_kw)
            else:
                fig.add_vrect(x0=s_date.isoformat(), x1=x_max, **shade_kw)
                fig.add_vrect(x0=x_min, x1=e_date.isoformat(),  **shade_kw)

    # Mean seasonal line
    fig.add_trace(go.Scatter(
        x             = [d.isoformat() for d in dates],
        y             = index_y,
        mode          = "lines",
        line          = dict(color=C["teal"], width=2.5),
        name          = "Seasonal trend",
        hovertemplate = "%{text}  <b>%{y:.3f}</b><extra></extra>",
        text          = hover_dates,
    ))

    # Baseline at 100
    fig.add_hline(y=100, line_color=C["muted"], line_width=0.8, opacity=0.35)

    # Pattern boundary lines — white solid, like Seasonax
    if has_pattern and s_date is not None and e_date is not None:
        for dv in [s_date, e_date]:
            fig.add_vline(x=dv.isoformat(), line_color="rgba(255,255,255,0.7)", line_width=1.5)

    # Inline chart title
    title_text = (
        f"Seasonal Trend of {display_name} Over {years} Years"
        + (f"  ({date_start} – {date_end})" if date_start else "")
    )

    x_range = [
        pd.Timestamp(ref_year, 1, 1).isoformat(),
        pd.Timestamp(ref_year, 12, 31).isoformat(),
    ]

    fig.update_layout(
        title = dict(
            text      = title_text,
            font      = dict(color=C["text"], size=13, family="sans-serif"),
            x         = 0.5,
            xanchor   = "center",
            pad       = dict(t=6),
        ),
        plot_bgcolor  = C["card"],
        paper_bgcolor = C["bg"],
        font          = dict(color=C["text"], family="sans-serif"),
        height        = 440,
        margin        = dict(l=60, r=20, t=48, b=52),
        showlegend    = False,
        hovermode     = "x unified",
        dragmode      = False,
        xaxis = dict(
            type        = "date",
            tickmode    = "array",
            tickvals    = tick_vals,
            ticktext    = tick_text,
            gridcolor   = C["border"],
            gridwidth   = 1,
            linecolor   = "rgba(0,0,0,0)",
            tickfont    = dict(color="#8899aa", size=12),
            showgrid    = True,
            range       = x_range,
            fixedrange  = True,
        ),
        yaxis = dict(
            gridcolor   = C["border"],
            gridwidth   = 1,
            linecolor   = "rgba(0,0,0,0)",
            tickfont    = dict(color="#8899aa", size=11),
            tickformat  = ".2f",
            zeroline    = False,
            fixedrange  = True,
            side        = "left",
            showgrid    = True,
            range       = y_range,
        ),
        hoverlabel = dict(
            bgcolor     = "#1c2030",
            bordercolor = C["teal"],
            font        = dict(color=C["text"], size=12, family="monospace"),
        ),
        modebar_remove = ["zoom","pan","select","lasso2d","zoomIn2d","zoomOut2d",
                          "autoScale2d","resetScale2d","toImage"],
    )
    return fig

def plot_donut(win_rate: float) -> go.Figure:
    loss_rate = 100.0 - win_rate
    fig = go.Figure(go.Pie(
        values        = [win_rate, loss_rate],
        labels        = ["Long", "Short"],
        marker        = dict(
            colors    = [C["teal"], C["red"]],
            line      = dict(color=C["card"], width=2),
        ),
        hole          = 0.64,
        direction     = "clockwise",
        sort          = False,
        textinfo      = "none",
        hovertemplate = "<b>%{label}</b>: %{value:.1f}%<extra></extra>",
    ))

    # Centre annotation
    fig.add_annotation(
        text      = f"<b>{win_rate:.1f}%</b><br><span style='font-size:9px'>Long</span>",
        x=0.5, y=0.5, showarrow=False,
        font      = dict(color=C["teal"], size=14, family="monospace"),
        align     = "center",
    )

    # Legend dots below
    fig.update_layout(
        plot_bgcolor  = "rgba(0,0,0,0)",
        paper_bgcolor = "rgba(0,0,0,0)",
        font          = dict(color=C["text"], family="monospace"),
        height        = 190,
        margin        = dict(l=4, r=4, t=4, b=28),
        showlegend    = True,
        legend        = dict(
            orientation = "h",
            x=0.5, xanchor="center",
            y=-0.04,
            font        = dict(size=10, color=C["muted"]),
        ),
    )
    return fig

# ─── UI Helpers ───────────────────────────────────────────────────────────────

def stat_card(col, label: str, value: str, sub: str = "", color: str = C["text"]):
    col.markdown(
        f"""<div style="background:{C['panel']};border:1px solid {C['border']};
            border-radius:8px;padding:13px 16px;min-height:76px;">
          <div style="font-size:9px;color:{C['muted']};text-transform:uppercase;
                      letter-spacing:1.4px;font-family:monospace;">{label}</div>
          <div style="font-size:19px;font-weight:700;color:{color};
                      margin:4px 0 1px;font-family:monospace;">{value}</div>
          <div style="font-size:10px;color:{C['muted']};font-family:monospace;">{sub}</div>
        </div>""",
        unsafe_allow_html=True,
    )

def pattern_stat(col, label: str, value: str, color: str = C["text"]):
    col.markdown(
        f"""<div style="background:{C['panel']};border:1px solid {C['border']};
            border-radius:7px;padding:11px 14px;">
          <div style="font-size:9px;color:{C['muted']};text-transform:uppercase;
                      letter-spacing:1.2px;font-family:monospace;">{label}</div>
          <div style="font-size:17px;font-weight:700;color:{color};
                      margin-top:3px;font-family:monospace;">{value}</div>
        </div>""",
        unsafe_allow_html=True,
    )

def render_year_table(table: pd.DataFrame):
    rows_html = ""
    for _, r in table.iterrows():
        pct   = r["Profit %"]
        color = C["green"] if pct >= 0 else C["red"]
        bg    = C["green_bg"] if pct >= 0 else C["red_bg"]
        rows_html += f"""
        <tr style="border-bottom:1px solid {C['border']};">
          <td style="color:{C['muted']};padding:7px 10px;">{r['Year']}</td>
          <td style="padding:7px 10px;">{r['Start Date']}</td>
          <td style="padding:7px 10px;font-family:monospace;">{r['Start Price']:.5g}</td>
          <td style="padding:7px 10px;">{r['End Date']}</td>
          <td style="padding:7px 10px;font-family:monospace;">{r['End Price']:.5g}</td>
          <td style="padding:7px 10px;font-family:monospace;">{r['Profit']:.5g}</td>
          <td style="padding:7px 10px;text-align:center;">
            <span style="background:{bg};color:{color};border-radius:4px;
                         padding:2px 8px;font-weight:700;font-family:monospace;">
              {pct:+.2f}%
            </span>
          </td>
          <td style="color:{C['green']};padding:7px 10px;font-family:monospace;">{r['Max Rise %']:+.2f}%</td>
          <td style="color:{C['red']};padding:7px 10px;font-family:monospace;">{r['Max Drop %']:+.2f}%</td>
        </tr>"""

    return f"""
    <div style="overflow-x:auto;margin-top:12px;">
    <table style="width:100%;border-collapse:collapse;font-size:12px;color:{C['text']};">
      <thead>
        <tr style="border-bottom:1px solid {C['dim']};">
          <th style="text-align:left;padding:7px 10px;color:{C['muted']};
                     font-weight:600;text-transform:uppercase;font-size:10px;
                     letter-spacing:1px;">Year</th>
          <th style="text-align:left;padding:7px 10px;color:{C['muted']};
                     font-weight:600;text-transform:uppercase;font-size:10px;
                     letter-spacing:1px;">Start Date</th>
          <th style="text-align:left;padding:7px 10px;color:{C['muted']};
                     font-weight:600;text-transform:uppercase;font-size:10px;
                     letter-spacing:1px;">Start Price</th>
          <th style="text-align:left;padding:7px 10px;color:{C['muted']};
                     font-weight:600;text-transform:uppercase;font-size:10px;
                     letter-spacing:1px;">End Date</th>
          <th style="text-align:left;padding:7px 10px;color:{C['muted']};
                     font-weight:600;text-transform:uppercase;font-size:10px;
                     letter-spacing:1px;">End Price</th>
          <th style="text-align:left;padding:7px 10px;color:{C['muted']};
                     font-weight:600;text-transform:uppercase;font-size:10px;
                     letter-spacing:1px;">Profit</th>
          <th style="text-align:center;padding:7px 10px;color:{C['muted']};
                     font-weight:600;text-transform:uppercase;font-size:10px;
                     letter-spacing:1px;">Profit %</th>
          <th style="text-align:left;padding:7px 10px;color:{C['muted']};
                     font-weight:600;text-transform:uppercase;font-size:10px;
                     letter-spacing:1px;">Max Rise</th>
          <th style="text-align:left;padding:7px 10px;color:{C['muted']};
                     font-weight:600;text-transform:uppercase;font-size:10px;
                     letter-spacing:1px;">Max Drop</th>
        </tr>
      </thead>
      <tbody>{rows_html}</tbody>
    </table>
    </div>"""


def _radar_html(df: pd.DataFrame) -> str:
    def long_color(v: float) -> str:
        return C["green"] if v >= 70 else (C["red"] if v <= 30 else C["text"])

    header = "".join(
        f"<th style='text-align:{align};color:{C['muted']};font-size:10px;"
        f"text-transform:uppercase;letter-spacing:1px;padding:8px 14px;"
        f"border-bottom:1px solid {C['border']};white-space:nowrap;'>{lbl}</th>"
        for lbl, align in [
            ("Asset", "left"), ("Category", "left"),
            ("Window", "left"), ("Days", "center"),
            ("Long %", "right"), ("Avg Return %", "right"),
            ("Win Rate", "right"), ("Sharpe", "right"), ("Signal", "left"),
        ]
    )

    body = ""
    for _, row in df.iterrows():
        lp      = row["Long %"]
        signal  = row.get("_signal", "Extreme" if (lp >= 70 or lp <= 30) else "Neutral")
        is_long  = lp >= 70
        is_short = lp <= 30
        if signal == "Extreme" and is_long:
            row_bg  = "rgba(0,196,140,0.05)"
            sig     = "⚡ Extreme"
            sig_col = C["green"]
        elif signal == "Extreme" and is_short:
            row_bg  = "rgba(240,82,98,0.05)"
            sig     = "⚡ Extreme"
            sig_col = C["red"]
        elif signal == "Watch":
            row_bg  = "rgba(240,180,40,0.04)"
            sig     = "⚠ Watch"
            sig_col = C["yellow"]
        elif signal == "Bias":
            row_bg  = "rgba(68,80,102,0.06)"
            sig     = "📊 Bias"
            sig_col = C["muted"]
        else:
            row_bg, sig, sig_col = "transparent", "Neutral", C["muted"]

        avg_col    = C["teal"] if row["Avg Return"] >= 0 else C["red"]
        sharpe_col = C["teal"] if row["Sharpe"] >= 0 else C["red"]

        win_str  = row.get("Window", "—")
        days_str = row.get("Days",   "—")
        body += (
            f"<tr style='background:{row_bg};border-bottom:1px solid {C['border']};'>"
            f"<td style='padding:7px 14px;color:{C['text']};font-weight:600;'>{row['Asset']}</td>"
            f"<td style='padding:7px 14px;color:{C['muted']};font-size:10px;'>{row['Category']}</td>"
            f"<td style='padding:7px 14px;color:{C['muted']};font-size:10px;white-space:nowrap;'>{win_str}</td>"
            f"<td style='padding:7px 14px;color:{C['muted']};font-size:10px;text-align:center;'>{days_str}</td>"
            f"<td style='padding:7px 14px;color:{long_color(lp)};font-weight:700;text-align:right;'>{lp:.1f}%</td>"
            f"<td style='padding:7px 14px;color:{avg_col};font-weight:700;text-align:right;'>{row['Avg Return']:+.2f}%</td>"
            f"<td style='padding:7px 14px;color:{long_color(lp)};font-weight:700;text-align:right;'>{row['Win Rate']:.1f}%</td>"
            f"<td style='padding:7px 14px;color:{sharpe_col};font-weight:700;text-align:right;'>{row['Sharpe']:.2f}</td>"
            f"<td style='padding:7px 14px;color:{sig_col};font-weight:700;'>{sig}</td>"
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


# ─── Footer ───────────────────────────────────────────────────────────────────

def _render_footer():
    st.markdown(
        f"<div style='margin-top:48px;padding-top:14px;"
        f"border-top:1px solid {C['border']};text-align:center;"
        f"font-size:11px;color:{C['muted']};font-family:monospace;'>"
        f"Built by @realedgetraders</div>",
        unsafe_allow_html=True,
    )

# ─── Main App ─────────────────────────────────────────────────────────────────

def main():
    st.set_page_config(
        page_title="Seasonality Analysis · Trading Terminal",
        page_icon="📈",
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
      /* Selectbox */
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

      /* Text input */
      div[data-baseweb="input"] > div {{
          background:{C['panel']} !important;
          border:1px solid {C['border']} !important;
          border-radius:8px !important;
      }}
      input, textarea {{ color:{C['text']} !important; }}

      /* Reduce overall container top padding */
      .stMainBlockContainer {{ padding-top:3.5rem !important; }}

      /* Radio as pill buttons */
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

      /* Range select_slider — align track with chart plot area.
         Chart has margin l=60px r=20px; baseweb adds 8px thumb-radius on each side.
         So: wrapper padding = chart_margin - thumb_radius → left:52px right:12px */
      div[data-testid="stSlider"] {{
          padding-left:52px !important;
          padding-right:12px !important;
          box-sizing:border-box !important;
      }}
      /* Handles */
      div[data-testid="stSlider"] [data-baseweb="slider"] div[role="slider"] {{
          background:{C['teal']} !important;
          border:2px solid {C['teal']} !important;
          box-shadow:0 0 6px {C['teal']}55 !important;
          width:14px !important; height:14px !important;
      }}
      /* Track rail */
      div[data-testid="stSlider"] [data-baseweb="slider"] [data-testid="stSliderTrack"] {{
          background:#333 !important;
      }}
      /* Filled segment between handles */
      div[data-testid="stSlider"] [data-baseweb="slider"] [data-testid="stSliderTrack"] > div {{
          background:{C['teal']} !important;
      }}
      /* Hide default min/max tick labels */
      div[data-testid="stSlider"] [data-testid="stTickBarMin"],
      div[data-testid="stSlider"] [data-testid="stTickBarMax"] {{ display:none; }}
      /* Value tooltip bubbles */
      div[data-testid="stSlider"] [data-baseweb="tooltip"] {{
          background:{C['card']} !important;
          border:1px solid {C['border']} !important;
          color:{C['teal']} !important;
          font-family:monospace !important;
          font-size:11px !important;
          border-radius:4px !important;
      }}

      /* Date input */
      div[data-testid="stDateInput"] > div {{
          background:{C['panel']} !important;
          border:1px solid {C['border']} !important;
          border-radius:8px !important;
      }}
      div[data-testid="stDateInput"] label {{
          font-size:10px !important;
          color:{C['muted']} !important;
          text-transform:uppercase;
          letter-spacing:1px;
          font-family:monospace;
      }}

      p, span, label {{ color:{C['text']}; }}
      hr {{ border-color:{C['border']}; }}
    </style>
    """, unsafe_allow_html=True)

    # ── Page title + back button ──────────────────────────────────────────────
    _col_back_top, _col_title, _col_empty = st.columns([2, 5, 2])
    with _col_back_top:
        st.markdown("<div style='margin-top:6px;'>", unsafe_allow_html=True)
        if st.button("← Back to Hub", key="back_btn"):
            st.switch_page("app.py")
        st.markdown("</div>", unsafe_allow_html=True)
    with _col_title:
        st.markdown(
            f"<div style='margin-bottom:18px;text-align:center;'>"
            f"<div style='font-size:20px;font-weight:700;color:{C['text']};"
            f"font-family:monospace;letter-spacing:-0.5px;line-height:1.2;'>"
            f"Seasonality Tracker</div>"
            f"<div style='font-size:11px;color:{C['muted']};font-family:monospace;"
            f"margin-top:3px;'>Historical seasonal pattern analysis</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

    # ── Session state bootstrap ───────────────────────────────────────────────
    # Bidirectional sync between the select_slider (key "pat_doy_range") and
    # calendar date_inputs (keys "pat_start_cal" / "pat_end_cal").
    # "_committed_doy" remembers (s_doy, e_doy) from the previous render so we
    # can detect which widget changed this run.
    today    = datetime.today()
    ref_year = today.year
    _def_s = _DOY_LABELS[_doy(today.month, today.day) - 1]   # today
    _def_e_date = (dt_date(today.year, today.month, today.day) + relativedelta(months=1))
    _def_e = _DOY_LABELS[_doy(_def_e_date.month, _def_e_date.day) - 1]  # today + 1 month

    # Read slider value
    _raw   = st.session_state.get("pat_doy_range", (_def_s, _def_e))
    _s_lbl_raw, _e_lbl_raw = (
        (_DOY_LABELS[_raw[0] - 1], _DOY_LABELS[_raw[1] - 1])
        if isinstance(_raw[0], int) else _raw
    )
    _slider_s_doy = _DOY_LABELS.index(_s_lbl_raw) + 1
    _slider_e_doy = _DOY_LABELS.index(_e_lbl_raw) + 1

    # Read calendar values (may be None on first run)
    _cal_s = st.session_state.get("pat_start_cal", None)
    _cal_e = st.session_state.get("pat_end_cal", None)
    _cal_s_doy = _doy(_cal_s.month, _cal_s.day) if _cal_s is not None else _slider_s_doy
    _cal_e_doy = _doy(_cal_e.month, _cal_e.day) if _cal_e is not None else _slider_e_doy

    # Determine source of truth
    _committed = st.session_state.get("_committed_doy", None)
    if _committed is None:
        _s_doy = _slider_s_doy
        _e_doy = _slider_e_doy
    else:
        _comm_s, _comm_e = _committed
        _slider_changed = (_slider_s_doy, _slider_e_doy) != (_comm_s, _comm_e)
        _cal_changed    = (_cal_s_doy,    _cal_e_doy)    != (_comm_s, _comm_e)

        if _slider_changed and not _cal_changed:
            # Slider moved → push to calendar
            _s_doy = _slider_s_doy
            _e_doy = _slider_e_doy
            _tmp_s = datetime(2001, 1, 1) + timedelta(days=_s_doy - 1)
            _tmp_e = datetime(2001, 1, 1) + timedelta(days=_e_doy - 1)
            st.session_state["pat_start_cal"] = dt_date(ref_year, _tmp_s.month, _tmp_s.day)
            st.session_state["pat_end_cal"]   = dt_date(ref_year, _tmp_e.month, _tmp_e.day)
        elif _cal_changed and not _slider_changed:
            # Calendar changed → push to slider
            _s_doy = _cal_s_doy
            _e_doy = _cal_e_doy
            st.session_state["pat_doy_range"] = (
                _DOY_LABELS[_s_doy - 1], _DOY_LABELS[_e_doy - 1]
            )
        else:
            # Neither changed (or both — slider wins)
            _s_doy = _slider_s_doy
            _e_doy = _slider_e_doy

    st.session_state["_committed_doy"] = (_s_doy, _e_doy)

    _s_lbl = _DOY_LABELS[_s_doy - 1]
    _e_lbl = _DOY_LABELS[_e_doy - 1]
    _sr    = datetime(2001, 1, 1) + timedelta(days=_s_doy - 1)
    _er    = datetime(2001, 1, 1) + timedelta(days=_e_doy - 1)
    pat_start  = dt_date(ref_year, _sr.month, _sr.day)
    pat_end    = dt_date(ref_year, _er.month, _er.day)
    pat_active = _s_doy != _e_doy

    # ── Controls row (asset · history · pattern window) ──────────────────────
    _cal_min = dt_date(ref_year, 1, 1)
    _cal_max = dt_date(ref_year, 12, 31)
    pair_options = list(FOREX_PAIRS.keys()) + ["── Custom ──"]
    col_asset, col_hist, col_pat = st.columns([4, 4, 4], gap="small")

    with col_asset:
        st.markdown(
            f"<div style='font-size:10px;color:{C['muted']};text-transform:uppercase;"
            f"letter-spacing:1px;font-family:monospace;margin-bottom:4px;'>Asset</div>",
            unsafe_allow_html=True,
        )
        selected_pair = st.selectbox(
            "Asset",
            pair_options,
            key="asset_search",
            label_visibility="collapsed",
        )

    with col_hist:
        st.markdown(
            f"<div style='font-size:10px;color:{C['muted']};text-transform:uppercase;"
            f"letter-spacing:1px;font-family:monospace;margin-bottom:4px;'>Historical Data</div>",
            unsafe_allow_html=True,
        )
        years = st.radio(
            "Historical Data",
            [5, 10, 15, 20, 25],
            index=1,
            horizontal=True,
            format_func=lambda x: f"{x}y",
            key="years_radio",
            label_visibility="collapsed",
        )

    with col_pat:
        st.markdown(
            f"<div style='font-size:10px;color:{C['muted']};text-transform:uppercase;"
            f"letter-spacing:1px;font-family:monospace;margin-bottom:4px;'>Pattern Window</div>",
            unsafe_allow_html=True,
        )
        _pc_s, _pc_e = st.columns(2)
        with _pc_s:
            st.date_input(
                "Start",
                value=pat_start,
                min_value=_cal_min,
                max_value=_cal_max,
                format="MM/DD/YYYY",
                key="pat_start_cal",
            )
        with _pc_e:
            st.date_input(
                "End",
                value=pat_end,
                min_value=_cal_min,
                max_value=_cal_max,
                format="MM/DD/YYYY",
                key="pat_end_cal",
            )

    if selected_pair == "── Custom ──":
        custom_ticker = st.text_input(
            "Custom ticker",
            value="AAPL",
            placeholder="e.g. AAPL, ^GSPC, GC=F, BTC-USD",
            key="custom_ticker",
        )
        ticker       = custom_ticker.strip().upper()
        display_name = ticker
    else:
        ticker       = FOREX_PAIRS[selected_pair]
        display_name = selected_pair

    # ── Fetch Data ────────────────────────────────────────────────────────────
    with st.spinner(f"Loading {display_name} ({years}y) …"):
        df = fetch_data(ticker, years)

    if df.empty:
        st.error(
            f"No data for **`{ticker}`**. "
            f"Try: `EURUSD=X`, `^GSPC`, `GC=F`, `BTC-USD`"
        )
        return

    # ── Info line ─────────────────────────────────────────────────────────────
    stats    = calc_overall_stats(df)
    _sep = f"<span style='color:{C['dim']};'>&nbsp;·&nbsp;</span>"
    st.markdown(
        f"<div style='font-size:11px;font-family:monospace;padding:4px 0 6px;"
        f"border-bottom:1px solid {C['border']};margin-bottom:2px;"
        f"white-space:nowrap;overflow:hidden;text-overflow:ellipsis;'>"
        f"<span style='color:{C['teal']};font-weight:700;'>{display_name}</span>"
        f"{_sep}"
        f"<span style='color:{C['muted']};'>{years}-Year Analysis</span>"
        f"{_sep}"
        f"<span style='color:{C['muted']};'>{stats['n']:,} Trading Days</span>"
        f"{_sep}"
        f"<span style='color:{C['muted']};'>{stats['date_start']:%b %Y} – {stats['date_end']:%b %Y}</span>"
        f"{_sep}"
        f"<span style='color:{C['muted']};'>Data: Yahoo Finance</span>"
        f"</div>",
        unsafe_allow_html=True,
    )

    # ── Seasonal Curve ────────────────────────────────────────────────────────
    with st.spinner("Computing seasonal curve …"):
        curve, yr_paths = calc_seasonal_curve(df)

    if curve.empty:
        st.warning("Not enough data to compute seasonal curve.")
        return

    sm, sd = (pat_start.month, pat_start.day) if pat_active else (None, None)
    em, ed = (pat_end.month,   pat_end.day)   if pat_active else (None, None)

    fig = plot_seasonal_curve(
        curve, sm, sd, em, ed,
        display_name = display_name,
        years        = years,
        date_start   = stats["date_start"].strftime("%d %b %Y"),
        date_end     = stats["date_end"].strftime("%d %b %Y"),
        year_paths   = yr_paths,
    )

    st.plotly_chart(fig, use_container_width=True)

    st.markdown(
        f"<div style='font-size:10px;color:{C['muted']};font-family:monospace;"
        f"margin:-8px 0 2px;text-align:right;'>"
        f"Normalized price paths averaged per DOY (Seasonax method) &nbsp;·&nbsp; {years}y lookback"
        f"</div>",
        unsafe_allow_html=True,
    )

    # ── Pattern range slider ──────────────────────────────────────────────────
    st.select_slider(
        "Pattern window",
        options=_DOY_LABELS,
        value=(_s_lbl, _e_lbl),
        label_visibility="collapsed",
        key="pat_doy_range",
    )

    # ── Pattern Analysis ──────────────────────────────────────────────────────
    if not pat_active:
        st.markdown(
            f"<div style='background:{C['panel']};border:1px solid {C['border']};"
            f"border-radius:8px;padding:20px 24px;color:{C['muted']};"
            f"font-family:monospace;font-size:12px;text-align:center;'>"
            f"Drag the Pattern Window slider above the chart to activate pattern analysis."
            f"</div>",
            unsafe_allow_html=True,
        )
        _render_footer()
        return

    with st.spinner("Analysing pattern …"):
        pat_stats, pat_table = calc_pattern_analysis(df, sm, sd, em, ed)

    if pat_stats is None:
        st.warning("No complete pattern windows found in the data. Try a wider history or different dates.")
        _render_footer()
        return

    # ── Pattern Header ────────────────────────────────────────────────────────
    cross = _doy(sm, sd) > _doy(em, ed)
    start_label = datetime(2001, sm, sd).strftime("%b %d")
    end_label   = datetime(2001, em, ed).strftime("%b %d")
    period_str  = f"{start_label} → {end_label}" + (" (cross-year)" if cross else "")

    st.markdown(
        f"<div style='display:flex;align-items:center;gap:12px;margin-bottom:16px;'>"
        f"<div style='width:3px;height:28px;background:{C['blue']};border-radius:2px;'></div>"
        f"<div>"
        f"<div style='font-size:13px;font-weight:700;color:{C['text']};"
        f"font-family:monospace;'>Pattern Analysis</div>"
        f"<div style='font-size:11px;color:{C['muted']};font-family:monospace;'>"
        f"{period_str} · {pat_stats['n']} occurrences · "
        f"avg {pat_stats['hold']:.0f} trading days/year"
        f"</div></div></div>",
        unsafe_allow_html=True,
    )

    # ── Row 1: Donut + 5 stat cards ──────────────────────────────────────────
    donut_col, stats_col = st.columns([1, 3], gap="medium")

    with donut_col:
        st.plotly_chart(plot_donut(pat_stats["win_rate"]),
                        use_container_width=True)

    with stats_col:
        c1, c2, c3, c4, c5 = st.columns(5)
        pattern_stat(c1, pat_stats["ann_label"],
                     f"{pat_stats['ann_ret']:+.1f}%",
                     C["teal"] if pat_stats["ann_ret"] >= 0 else C["red"])
        pattern_stat(c2, "Win Rate",
                     f"{pat_stats['win_rate']:.1f}%",
                     C["teal"] if pat_stats["win_rate"] >= 50 else C["red"])
        pattern_stat(c3, "Avg Return",
                     f"{pat_stats['avg_ret']:+.2f}%",
                     C["teal"] if pat_stats["avg_ret"] >= 0 else C["red"])
        pattern_stat(c4, "Median Return",
                     f"{pat_stats['med_ret']:+.2f}%",
                     C["teal"] if pat_stats["med_ret"] >= 0 else C["red"])
        pattern_stat(c5, "Sharpe",
                     f"{pat_stats['sharpe']:.2f}",
                     C["teal"] if pat_stats["sharpe"] >= 0 else C["red"])

    # ── Row 2: Extra stats grid ───────────────────────────────────────────────
    streak_color = C["teal"] if pat_stats["streak_dir"] == "W" else C["red"]
    streak_label = f"{pat_stats['streak']}× {'Win' if pat_stats['streak_dir'] == 'W' else 'Loss'}"

    g1, g2, g3, g4, g5, g6 = st.columns(6)
    pattern_stat(g1, "Gains",      f"{pat_stats['gains']}",            C["teal"])
    pattern_stat(g2, "Losses",     f"{pat_stats['losses']}",           C["red"])
    pattern_stat(g3, "Best Trade", f"{pat_stats['best']:+.2f}%",       C["teal"])
    pattern_stat(g4, "Worst Trade",f"{pat_stats['worst']:+.2f}%",      C["red"])
    pattern_stat(g5, "Std Dev",    f"{pat_stats['std_ret']:.2f}%",     C["muted"])
    pattern_stat(g6, "Streak",     streak_label,                        streak_color)

    # ── Year-by-Year Table ────────────────────────────────────────────────────
    st.markdown(
        f"<div style='font-size:10px;color:{C['muted']};text-transform:uppercase;"
        f"letter-spacing:1px;font-family:monospace;margin:20px 0 4px;'>"
        f"Year-by-Year Breakdown</div>",
        unsafe_allow_html=True,
    )
    st.markdown(render_year_table(pat_table), unsafe_allow_html=True)

    # ── Seasonality Radar — Next 30 Days ─────────────────────────────────────
    _today      = datetime.today()
    _today_str  = _today.strftime("%Y-%m-%d")
    _today_fmt  = _today.strftime("%d.%m.%Y")

    st.markdown("<div style='margin-top:32px;'></div>", unsafe_allow_html=True)
    st.markdown(
        f"<div style='display:flex;align-items:center;gap:12px;margin-bottom:4px;'>"
        f"<div style='width:3px;height:28px;background:{C['teal']};border-radius:2px;'></div>"
        f"<div>"
        f"<div style='font-size:13px;font-weight:700;color:{C['text']};"
        f"font-family:monospace;text-transform:uppercase;letter-spacing:1.5px;'>"
        f"Seasonality Radar — Next 30 Days</div>"
        f"<div style='font-size:10px;color:{C['muted']};font-family:monospace;margin-top:2px;'>"
        f"Next 30 Days from {_today_fmt} · 10Y History · Sorted by Strength</div>"
        f"</div></div>",
        unsafe_allow_html=True,
    )

    with st.spinner("Scanning seasonality across all assets..."):
        radar_df = calc_radar(_today_str)

    if not radar_df.empty:
        # ── Split Forex vs Index/Commodity ────────────────────────────────────
        forex_mask = radar_df["Category"] == "Forex"
        forex_df   = radar_df[forex_mask].copy()
        bias_df    = radar_df[~forex_mask].sort_values("Sharpe", ascending=False).reset_index(drop=True)
        bias_df["_signal"] = "Bias"

        # ── Forex: qualified windows → Extreme, rest → Watch/hidden ─────────────
        extreme_mask = forex_df["_qualified"].fillna(False)
        extreme_df   = forex_df[extreme_mask].copy()
        neutral_df   = forex_df[~extreme_mask].copy()

        extreme_df["_signal"] = "Extreme"
        watch_slots  = max(0, 15 - len(extreme_df))
        watch_df     = neutral_df.head(watch_slots).copy()
        watch_df["_signal"] = "Watch"
        remaining_df = neutral_df.iloc[watch_slots:]

        display_df = pd.concat([extreme_df, watch_df], ignore_index=True)

        n_long    = int((extreme_df["Long %"] >= 70).sum())
        n_short   = int((extreme_df["Long %"] <= 30).sum())
        n_watch   = len(watch_df)
        n_hidden  = len(remaining_df)
        n_bias    = len(bias_df)

        st.markdown(
            f"<div style='font-size:11px;color:{C['muted']};font-family:monospace;margin:6px 0 10px;'>"
            f"<span style='color:{C['green']};font-weight:700;'>{n_long} Forex Long</span>"
            f" &nbsp;·&nbsp; "
            f"<span style='color:{C['red']};font-weight:700;'>{n_short} Forex Short</span>"
            f" &nbsp;·&nbsp; "
            f"<span style='color:{C['yellow']};font-weight:700;'>{n_watch} Watch</span>"
            f" &nbsp;·&nbsp; {n_hidden} hidden"
            f" &nbsp;·&nbsp; <span style='color:{C['muted']};'>{n_bias} Index/Commodity</span></div>",
            unsafe_allow_html=True,
        )
        st.markdown(_radar_html(display_df), unsafe_allow_html=True)

        # ── Indices & Commodities sub-section ─────────────────────────────────
        if not bias_df.empty:
            st.markdown(
                f"<div style='margin-top:18px;margin-bottom:4px;'>"
                f"<span style='font-size:10px;color:{C['muted']};font-family:monospace;"
                f"text-transform:uppercase;letter-spacing:1px;font-weight:700;'>"
                f"Indices &amp; Commodities</span>"
                f"<span style='font-size:10px;color:{C['muted']};font-family:monospace;"
                f"opacity:0.6;'> — structural long bias · interpret with caution</span>"
                f"</div>",
                unsafe_allow_html=True,
            )
            st.markdown(_radar_html(bias_df), unsafe_allow_html=True)
    else:
        st.info("No radar data available for the selected history length.")

    _render_footer()

if __name__ == "__main__":
    main()
