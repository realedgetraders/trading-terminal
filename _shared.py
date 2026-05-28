"""
EdgeLab — Shared Utilities
==========================
Single source of truth for data-fetch and computation functions used by
Pair Intelligence and any future multi-module aggregator.

Rules:
  • This file is imported by pages/7_Pair_Intelligence.py.
  • When fetch logic changes in a main module (1_Seasonality, 2_COT_Analysis,
    4_Geopolitics) the corresponding function here MUST be kept in sync.
  • Never add Streamlit rendering code here — only data + constants.
  • Functions decorated with @st.cache_data share their cache with any caller
    that imports the same function object from this module.
"""

import io
import time
import zipfile
from datetime import datetime, timedelta, date as dt_date

import numpy as np
import pandas as pd
import requests
import streamlit as st
import yfinance as yf

# ╔══════════════════════════════════════════════════════════════════════════════
# ║  DESIGN SYSTEM  (canonical — mirrors all module C dicts)
# ╚══════════════════════════════════════════════════════════════════════════════
C: dict[str, str] = {
    "bg":       "#0d0d0d",
    "card":     "#141414",
    "border":   "#252525",
    "panel":    "#111111",
    "dim":      "#171717",
    "text":     "#e8e8e8",
    "muted":    "#909090",
    "teal":     "#4f8ef7",
    "teal_bg":  "rgba(79,142,247,0.14)",
    "teal_dim": "rgba(79,142,247,0.06)",
    "green":    "#1a9b6a",
    "green_bg": "rgba(26,155,106,0.09)",
    "red":      "#f05262",
    "red_bg":   "rgba(240,82,98,0.09)",
    "yellow":   "#f0b429",
    "blue":     "#4f8ef7",
}

# ╔══════════════════════════════════════════════════════════════════════════════
# ║  CURRENCY METADATA
# ╚══════════════════════════════════════════════════════════════════════════════
CURRENCY_FLAG: dict[str, str] = {
    "USD": "🇺🇸", "EUR": "🇪🇺", "GBP": "🇬🇧", "JPY": "🇯🇵",
    "AUD": "🇦🇺", "CAD": "🇨🇦", "CHF": "🇨🇭", "NZD": "🇳🇿",
}
SUPPORTED_CCYS: set[str] = set(CURRENCY_FLAG.keys())

# CFTC Legacy COT — market name per non-USD currency
# Source: CFTC deacot ZIPs, "Market_and_Exchange_Names" column
# If CFTC renames a market entry, update here and it propagates everywhere.
CFTC_CCY_MAP: dict[str, str] = {
    "EUR": "EURO FX - CHICAGO MERCANTILE EXCHANGE",
    "GBP": "BRITISH POUND - CHICAGO MERCANTILE EXCHANGE",
    "JPY": "JAPANESE YEN - CHICAGO MERCANTILE EXCHANGE",
    "CHF": "SWISS FRANC - CHICAGO MERCANTILE EXCHANGE",
    "CAD": "CANADIAN DOLLAR - CHICAGO MERCANTILE EXCHANGE",
    "AUD": "AUSTRALIAN DOLLAR - CHICAGO MERCANTILE EXCHANGE",
    "NZD": "NZ DOLLAR - CHICAGO MERCANTILE EXCHANGE",
}

# ╔══════════════════════════════════════════════════════════════════════════════
# ║  FOREXFACTORY CALENDAR — constants
# ╚══════════════════════════════════════════════════════════════════════════════
# Same endpoints used by Module 4 (4_Geopolitics.py).
# TTL on fetch_calendar() should match Module 4 (_FF_CALENDAR_TTL = 1800 there).
_CAL_URLS: list[str] = [
    "https://nfs.faireconomy.media/ff_calendar_thisweek.json",
    "https://nfs.faireconomy.media/ff_calendar_nextweek.json",
    "https://nfs.faireconomy.media/ff_calendar_month.json",
]
_CAL_HDR: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json, text/javascript, */*",
    "Referer": "https://www.forexfactory.com/",
}
# Bond/auction noise keywords — same filter used in Module 4
_CAL_NOISE: frozenset[str] = frozenset([
    "bond", "bill", "treasury", "auction", "note", "jgb", "btp", "gilt",
])

# ╔══════════════════════════════════════════════════════════════════════════════
# ║  COT — FETCH & METRICS
# ╚══════════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_cot_raw() -> tuple[pd.DataFrame, list[str]]:
    """
    Fetch CFTC Legacy COT ZIPs from 2001 to current year.
    Returns (combined_df, errors).

    Sync note: logic mirrors 2_COT_Analysis.py → fetch_cot_raw().
    If the URL pattern or ZIP structure changes there, update here too.
    """
    current = datetime.today().year
    frames: list[pd.DataFrame] = []
    errors: list[str] = []
    for yr in range(2001, current + 1):
        url = f"https://www.cftc.gov/files/dea/history/deacot{yr}.zip"
        try:
            r = requests.get(url, timeout=30)
            if r.status_code != 200:
                errors.append(f"HTTP {r.status_code} — {yr}")
                continue
            with zipfile.ZipFile(io.BytesIO(r.content)) as z:
                with z.open(z.namelist()[0]) as f:
                    frames.append(pd.read_csv(f, low_memory=False))
        except Exception as e:
            errors.append(f"{yr}: {e}")
    if not frames:
        return pd.DataFrame(), errors
    combined = pd.concat(frames, ignore_index=True)
    combined.columns = combined.columns.str.strip()
    return combined, errors


def get_cot_metrics(raw_df: pd.DataFrame, ccy: str) -> dict | None:
    """
    Extract COT metrics for one currency from the raw CFTC DataFrame.
    Returns a metrics dict or None if data is unavailable.

    Sync note: COT Index formula mirrors 2_COT_Analysis.py (26-week min-max).
    Column name mapping covers both naming conventions seen in CFTC CSVs.
    """
    market_name = CFTC_CCY_MAP.get(ccy)
    if not market_name or raw_df.empty:
        return None

    mkt_col = next(
        (c for c in raw_df.columns if "market_and_exchange" in c.lower().replace(" ", "_")),
        None,
    )
    if mkt_col is None:
        return None

    try:
        mkt = raw_df[
            raw_df[mkt_col].str.strip().str.upper() == market_name.upper()
        ].copy()
    except Exception:
        return None

    if mkt.empty:
        return None

    date_col = next(
        (c for c in mkt.columns if "as_of_date" in c.lower().replace(" ", "_")),
        None,
    )
    if date_col is None:
        return None
    try:
        mkt["_date"] = pd.to_datetime(mkt[date_col], format="%y%m%d", errors="coerce")
    except Exception:
        return None

    mkt = mkt.dropna(subset=["_date"]).sort_values("_date").tail(52)
    if len(mkt) < 4:
        return None

    def _find_col(*candidates: str) -> str | None:
        for c in candidates:
            if c in mkt.columns:
                return c
        return None

    comm_l  = _find_col("Commercial Positions-Long (Old)",     "Comm_Positions_Long_All")
    comm_s  = _find_col("Commercial Positions-Short (Old)",    "Comm_Positions_Short_All")
    large_l = _find_col("Noncommercial Positions-Long (Old)",  "NonComm_Positions_Long_All")
    large_s = _find_col("Noncommercial Positions-Short (Old)", "NonComm_Positions_Short_All")

    if not all([comm_l, comm_s, large_l, large_s]):
        return None

    for col in [comm_l, comm_s, large_l, large_s]:
        mkt[col] = pd.to_numeric(mkt[col], errors="coerce")

    mkt["net_comm"]  = mkt[comm_l]  - mkt[comm_s]
    mkt["net_large"] = mkt[large_l] - mkt[large_s]

    def _cot_index(series: pd.Series) -> float:
        """26-week min-max normalisation — same as Module 2."""
        w = series.dropna().tail(26)
        if len(w) < 2:
            return 50.0
        mn, mx = w.min(), w.max()
        return 50.0 if mx == mn else float((w.iloc[-1] - mn) / (mx - mn) * 100.0)

    net_comm  = mkt["net_comm"].dropna()
    net_large = mkt["net_large"].dropna()

    trend_val = (net_comm.iloc[-1] - net_comm.iloc[-4]) if len(net_comm) >= 4 else 0.0
    trend = "↑" if trend_val > 500 else ("↓" if trend_val < -500 else "→")

    return {
        "ccy":       ccy,
        "comm_idx":  _cot_index(net_comm),
        "large_idx": _cot_index(net_large),
        "net_comm":  float(net_comm.iloc[-1]),
        "net_large": float(net_large.iloc[-1]),
        "trend":     trend,
        "date":      mkt["_date"].iloc[-1].strftime("%b %d, %Y"),
    }


# ╔══════════════════════════════════════════════════════════════════════════════
# ║  SEASONALITY — FETCH & COMPUTATION
# ╚══════════════════════════════════════════════════════════════════════════════
# Methodology: Seasonax approach used in 1_Seasonality.py.
# _REF_YEAR = 2023 (non-leap scaffold) — must match Module 1.
_REF_YEAR: int = 2023


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_pair_history(ticker: str) -> pd.DataFrame:
    """
    Fetch 10 years of daily Close for a forex pair via yfinance.
    Applies the -1 day UTC shift for =X tickers (same fix as Module 1).

    Sync note: if Module 1 changes the UTC-shift logic or the period,
    update here accordingly.
    """
    try:
        end   = datetime.today()
        start = end - timedelta(days=int(10 * 365.25) + 10)
        df    = yf.download(
            ticker, start=start, end=end,
            interval="1d", progress=False, auto_adjust=True,
        )
        if df.empty:
            return pd.DataFrame()
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        # UTC shift: all =X forex tickers are one day ahead in yfinance UTC
        if ticker.endswith("=X"):
            df.index = df.index - pd.Timedelta(days=1)
        df = df[["Close"]].dropna()
        df["Year"]  = df.index.year
        df["Month"] = df.index.month
        return df
    except Exception:
        return pd.DataFrame()


def calc_seasonal_curve(df: pd.DataFrame) -> pd.DataFrame:
    """
    Seasonax methodology: normalise each year to 100 at first bar,
    forward-fill to all calendar days, average by (month, day) bucket,
    re-normalise so curve mean = 100, apply 3-day centred smooth.

    Returns DataFrame with columns: date (Timestamp, _REF_YEAR scaffold),
    index (float), n (int sample count).

    Sync note: algorithm mirrors 1_Seasonality.py → _build_seasonal_curve().
    """
    current_year = dt_date.today().year
    by_md: dict[tuple[int, int], list[float]] = {}

    for year, grp in df.groupby("Year"):
        if int(year) >= current_year:
            continue
        grp = grp.sort_index().dropna(subset=["Close"])
        if len(grp) < 20:
            continue
        base = float(grp["Close"].iloc[0])
        if base == 0:
            continue

        norm     = grp["Close"] / base * 100.0
        full_idx = pd.date_range(f"{int(year)}-01-01", f"{int(year)}-12-31", freq="D")
        norm_full = norm.reindex(full_idx).ffill().dropna()

        for ts, val in norm_full.items():
            m, d = ts.month, ts.day
            if m == 2 and d == 29:
                continue
            by_md.setdefault((m, d), []).append(float(val))

    if not by_md:
        return pd.DataFrame()

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
        return pd.DataFrame()

    mean_df    = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)
    curve_mean = mean_df["index"].mean()
    if curve_mean > 0:
        mean_df["index"] = (mean_df["index"] / curve_mean) * 100.0

    mean_df["index"] = (
        mean_df["index"].rolling(window=3, center=True, min_periods=1).mean()
    )
    return mean_df


def seasonal_month_stats(mean_df: pd.DataFrame) -> dict:
    """
    Compute stats for the current calendar month from the seasonal curve.
    Returns: start_val, end_val, direction, pct_change, color.
    """
    today = dt_date.today()
    try:
        m_start = pd.Timestamp(_REF_YEAR, today.month, 1)
        m_end   = (
            pd.Timestamp(_REF_YEAR, today.month + 1, 1) - pd.Timedelta(days=1)
            if today.month < 12
            else pd.Timestamp(_REF_YEAR, 12, 31)
        )
    except Exception:
        return {}

    window = mean_df[(mean_df["date"] >= m_start) & (mean_df["date"] <= m_end)]
    if len(window) < 2:
        return {}

    sv  = float(window["index"].iloc[0])
    ev  = float(window["index"].iloc[-1])
    pct = (ev - sv) / sv * 100 if sv != 0 else 0.0
    return {
        "start_val": sv,
        "end_val":   ev,
        "pct":       pct,
        "direction": "↑ BULLISH" if pct > 0.3 else ("↓ BEARISH" if pct < -0.3 else "→ NEUTRAL"),
        "color":     C["green"] if pct > 0.3 else (C["red"] if pct < -0.3 else C["muted"]),
    }


# ╔══════════════════════════════════════════════════════════════════════════════
# ║  FOREXFACTORY CALENDAR — FETCH
# ╚══════════════════════════════════════════════════════════════════════════════

def parse_num(val: object) -> float | None:
    """Parse a raw ForexFactory value string to float. Returns None if unparseable."""
    if val is None:
        return None
    s = str(val).strip().replace(",", "").replace("%", "").replace("$", "")
    if s in ("", "-", "N/A", "null", "None"):
        return None
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


@st.cache_data(ttl=1800, show_spinner=False)
def fetch_calendar() -> pd.DataFrame:
    """
    Fetch ForexFactory JSON calendar from three endpoints (this week, next week, month).
    Returns a deduplicated DataFrame:
      columns: currency, title, date, impact, actual, forecast, previous

    Sync note: endpoint list, headers, and noise filter mirror 4_Geopolitics.py.
    TTL = 1800s matches Module 4's _FF_CALENDAR_TTL.
    If Module 4 adds new endpoints or changes the noise filter, update here.
    """
    rows: list[dict] = []
    seen: set[tuple] = set()

    for url in _CAL_URLS:
        try:
            r = requests.get(url, timeout=10, headers=_CAL_HDR)
            if r.status_code != 200:
                continue
            data = r.json()
            if not isinstance(data, list):
                continue
            for ev in data:
                title   = str(ev.get("title") or ev.get("name") or "").strip()
                if any(kw in title.lower() for kw in _CAL_NOISE):
                    continue
                ccy_raw = str(ev.get("currency") or ev.get("country") or "").upper().strip()
                ccy     = ccy_raw[:3] if ccy_raw else ""
                if ccy not in SUPPORTED_CCYS:
                    continue
                impact = str(ev.get("impact") or "Low").capitalize()
                if impact == "Holiday":
                    continue
                try:
                    date = pd.to_datetime(ev.get("date"), errors="coerce")
                    if pd.isna(date):
                        continue
                    if date.tzinfo is not None:
                        date = date.tz_localize(None)
                except Exception:
                    continue
                key = (ccy, title, date.date())
                if key in seen:
                    continue
                seen.add(key)
                rows.append({
                    "currency": ccy,
                    "title":    title,
                    "date":     date,
                    "impact":   impact,
                    "actual":   parse_num(ev.get("actual")),
                    "forecast": parse_num(ev.get("forecast")),
                    "previous": parse_num(ev.get("previous")),
                })
        except Exception:
            pass
        time.sleep(0.05)

    if not rows:
        return pd.DataFrame(
            columns=["currency", "title", "date", "impact", "actual", "forecast", "previous"]
        )
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    return df.dropna(subset=["date"]).reset_index(drop=True)
