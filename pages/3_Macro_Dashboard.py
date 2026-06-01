"""
Trading Analytics Terminal — Module 3: Economic Bias Engine (v2)
5-dimension macro scoring engine with password gate and auto-refresh.
"""

import csv as _csv
import io
import time
import zipfile
from datetime import datetime, timedelta

import pandas as pd
import requests
import streamlit as st

# ── FRED API key ──────────────────────────────────────────────────────────────
import os as _os
try:
    FRED_API_KEY: str = st.secrets.get("FRED_API_KEY", "")
except Exception:
    FRED_API_KEY = _os.environ.get("FRED_API_KEY", "")

# True only when the key looks like a real 32-char FRED key (not placeholder).
# Used throughout the module to mark FRED-dependent indicators as live vs static.
_FRED_KEY_VALID: bool = (
    len(FRED_API_KEY) == 32
    and FRED_API_KEY.replace("-", "").isalnum()
    and FRED_API_KEY not in ("your_fred_api_key_here", "")
)

# Set env MACRO_DEBUG=1 to print freshness/fallback diagnostics to the server log.
_MACRO_DEBUG: bool = _os.environ.get("MACRO_DEBUG") == "1"


def _src(live_label: str, is_live: bool) -> str:
    """Return the source label with a '⚠' prefix when falling back to static data."""
    return live_label if is_live else f"⚠ static ({_FB_DATE})"

# ╔══════════════════════════════════════════════════════════════════════════════
# ║  DESIGN SYSTEM
# ╚══════════════════════════════════════════════════════════════════════════════
C = {
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

CURRENCIES = ["USD", "EUR", "GBP", "JPY", "AUD", "NZD", "CAD", "CHF"]

CURRENCY_FLAG = {
    "USD": "🇺🇸", "EUR": "🇪🇺", "GBP": "🇬🇧", "JPY": "🇯🇵",
    "AUD": "🇦🇺", "NZD": "🇳🇿", "CAD": "🇨🇦", "CHF": "🇨🇭",
}

# ╔══════════════════════════════════════════════════════════════════════════════
# ║  STATIC FALLBACKS
# ╚══════════════════════════════════════════════════════════════════════════════
_FB_DATE  = "2026-05-31"

_FB_RATES  = {"USD": 3.75, "EUR": 2.00, "GBP": 3.75, "JPY": 0.75,
              "AUD": 4.35, "NZD": 2.25, "CAD": 2.25, "CHF": 0.00}
# AUD: 4.35 after RBA hike 5 May 2026; CAD: 2.25 = Target Overnight Rate (not Bank Rate)
# Static CPI fallbacks — last updated 2026-05-31 (used ONLY when all live sources fail).
# EUR Apr=3.0 (Eurostat flash), GBP Apr=2.82 (ONS D7BT confirmed), JPY Apr=1.4 (MIC),
# AUD Apr=4.2 (ABS Monthly CPI Indicator), CAD Apr=2.8 (StatCan), CHF Mar=0.2 (BFS).
# NZD Q1 2026 (Mar quarter) = 3.1% (Stats NZ, confirmed 2026-04-21); CPI is quarterly so
# the FRED OECD series is gated out by the freshness window → this static value is shown.
_FB_CPI    = {"USD": 2.4,  "EUR": 3.0,  "GBP": 2.8,  "JPY": 1.4,
              "AUD": 4.2,  "NZD": 3.1,  "CAD": 2.8,  "CHF": 0.5}
# CHF Apr=0.50 confirmed Eurostat ei_cphi_m 2026-05-31
# Core CPI — GBP Apr=2.5 confirmed (ONS DKO8, ex energy/food/alc/tobacco); others estimated.
_FB_CCPI   = {"USD": 2.8,  "EUR": 2.8,  "GBP": 2.5,  "JPY": 1.4,
              "AUD": 3.6,  "NZD": 2.7,  "CAD": 2.4,  "CHF": 0.9}
_FB_GDP    = {"USD": 2.4,  "EUR": 0.4,  "GBP": 0.7,  "JPY": 0.2,
              "AUD": 0.3,  "NZD": -0.2, "CAD": 1.2,  "CHF": 0.3}
_FB_PMI    = {"USD": 49.0, "EUR": 45.3, "GBP": 45.4, "JPY": 48.7,
              "AUD": 51.7, "NZD": 53.9, "CAD": 47.8, "CHF": 46.2}
_FB_UNEMP  = {"USD": 4.2,  "EUR": 6.2,  "GBP": 4.5,  "JPY": 2.5,
              "AUD": 4.1,  "NZD": 5.1,  "CAD": 6.9,  "CHF": 2.8}
_FB_TRADE  = {"USD": -70.0,"EUR": 30.0, "GBP": -5.0, "JPY": 0.5,
              "AUD": 5.0,  "NZD": -0.8, "CAD": -2.5, "CHF": 5.0}
_FB_RETAIL = {"USD": 0.1,  "EUR": 0.1,  "GBP": 0.0,  "JPY": -1.1,
              "AUD": 0.3,  "NZD": -0.1, "CAD": -0.4, "CHF": 0.0}

# Previous-period fallbacks — used when live API is unavailable so PREV column never shows "—"
_FB_PREV_RATES = {"USD": 4.00, "EUR": 2.25, "GBP": 4.00, "JPY": 0.50,
                  "AUD": 4.10, "NZD": 2.50, "CAD": 2.50, "CHF": 0.25}
# AUD prev: 4.10 (rate before 5 May 2026 hike to 4.35, not 3.85); CAD prev: 2.50 (before last cut)
# Previous-month CPI — GBP Mar=3.30 confirmed (ONS); others estimated from trend.
_FB_PREV_CPI   = {"USD": 2.6,  "EUR": 2.6,  "GBP": 3.3,  "JPY": 1.5,
                  "AUD": 4.6,  "NZD": 3.1,  "CAD": 2.3,  "CHF": 0.6}
# EUR prev=2.6 (Mar), AUD prev=4.6 (Mar), CHF prev=0.6 (Mar) confirmed Eurostat/ABS
_FB_PREV_CCPI  = {"USD": 3.0,  "EUR": 2.7,  "GBP": 3.1,  "JPY": 1.6,
                  "AUD": 3.6,  "NZD": 2.7,  "CAD": 2.4,  "CHF": 1.0}
_FB_PREV_GDP   = {"USD": 2.4,  "EUR": 0.4,  "GBP": 0.6,  "JPY": 0.1,
                  "AUD": 0.4,  "NZD": -0.1, "CAD": 1.1,  "CHF": 0.2}
_FB_PREV_UNEMP = {"USD": 4.1,  "EUR": 6.3,  "GBP": 4.4,  "JPY": 2.5,
                  "AUD": 4.1,  "NZD": 5.0,  "CAD": 6.8,  "CHF": 2.8}
# Employment change fallback — units: K persons for USD/GBP/AUD/CAD/JPY; % q/q for EUR/NZD/CHF
_FB_EMPLOY     = {"USD": 177.0, "EUR": 0.3,  "GBP": 40.0,  "JPY": 10.0,
                  "AUD": 30.0,  "NZD": 0.4,  "CAD": 20.0,  "CHF": 0.2}
_FB_PREV_EMPLOY= {"USD": 185.0, "EUR": 0.2,  "GBP": 45.0,  "JPY": 12.0,
                  "AUD": 35.0,  "NZD": 0.3,  "CAD": 25.0,  "CHF": 0.1}
# EUR/NZD/CHF report employment change as QoQ % (not K persons)
_EMPLOY_IS_PCT = {"EUR", "NZD", "CHF"}
# PMI, Trade Balance, Retail Sales previous-period fallbacks (FF calendar source)
_FB_PREV_PMI   = {"USD": 50.3, "EUR": 45.5, "GBP": 44.9, "JPY": 48.4,
                  "AUD": 52.0, "NZD": 53.5, "CAD": 47.5, "CHF": 46.0}
_FB_PREV_TRADE = {"USD": -72.0, "EUR": 28.0, "GBP": -5.5, "JPY": 0.3,
                  "AUD": 4.5,   "NZD": -1.0, "CAD": -2.8, "CHF": 4.5}
_FB_PREV_RETAIL= {"USD": 0.2, "EUR": 0.2, "GBP": 0.1, "JPY": -1.0,
                  "AUD": 0.4, "NZD": -0.2, "CAD": -0.3, "CHF": 0.1}
# Consumer confidence fallback (USD = UMich UMCSENT scale 0-100)
_FB_CONF_USD   = 67.0

_NEUTRAL_RATE  = {"USD": 2.5, "EUR": 2.0, "GBP": 2.5, "JPY": 0.5,
                  "AUD": 3.0, "NZD": 2.5, "CAD": 2.5, "CHF": 0.0}

# Rate delta displayed when no live rate series is available (static fallback path).
# Represents the most recent CB decision in bps: 0 = hold, +N = hike, -N = cut.
# *** MUST BE MANUALLY UPDATED when any of these CBs change rates ***
# Last reviewed: 2026-05-31
_FB_RATE_DELTA = {
    "USD": 0.0,    # Fed: holding at 3.75 (last cut Dec 2024)
    "EUR": 0.0,    # ECB: holding at 2.00
    "GBP": 0.0,    # BoE: holding at 3.75
    "JPY": 0.0,    # BoJ: held at 0.75 (last move was hike in early 2026; held Mar/Apr)
    "AUD": 25.0,   # RBA: hiked +25 bps to 4.35 on 5 May 2026 (from 4.10)
    "NZD": 0.0,    # RBNZ: holding at 2.25
    "CAD": 0.0,    # BoC: handled by live V39079 data; fallback = holding
    "CHF": 0.0,    # SNB: holding at 0.00
}
_NEUTRAL_UNEMP = {"USD": 4.5, "EUR": 7.5, "GBP": 4.5, "JPY": 3.0,
                  "AUD": 5.0, "NZD": 5.0, "CAD": 6.0, "CHF": 3.0}

_TRADE_THRESH = {
    "USD": (-100, -70,  10,  30),
    "EUR": (   0,  20,  50,  80),
    "GBP": ( -15,  -8,  -1,   2),
    "JPY": (  -5,   0,   5,  10),
    "AUD": (   0,   3,   8,  15),
    "NZD": (  -2, -0.5, 0.5,  2),
    "CAD": (  -5,  -2,   2,   6),
    "CHF": (   2,   4,   8,  12),
}
# Per-currency trade balance delta thresholds (month-over-month change, same units as _TRADE_THRESH)
_TRADE_DELTA_THRESH = {
    "USD": (-10.0, -2.0,  2.0, 10.0),
    "EUR": ( -5.0, -1.0,  1.0,  5.0),
    "GBP": ( -2.0, -0.5,  0.5,  2.0),
    "JPY": ( -0.5, -0.1,  0.1,  0.5),    # JPY: tightened so 0.20T improvement scores +0.5
    "AUD": ( -2.0, -0.5,  0.5,  2.0),
    "NZD": ( -0.5, -0.1,  0.1,  0.5),
    "CAD": ( -2.0, -0.5,  0.5,  2.0),
    "CHF": ( -2.0, -0.5,  0.5,  2.0),
}
# Per-currency employment change delta thresholds (change vs previous print, same units as employment)
_EMPLOY_DELTA_THRESH = {
    "USD": (-50.0, -10.0, 10.0, 50.0),
    "EUR": ( -0.5,  -0.1,  0.1,  0.5),   # QoQ % (pct)
    "GBP": (-20.0,  -3.0,  3.0, 20.0),   # K persons
    "JPY": (-10.0,  -1.5,  1.5, 10.0),   # K persons — tightened so 2K miss scores -0.5
    "AUD": (-20.0,  -3.0,  3.0, 20.0),   # K persons
    "NZD": ( -0.5,  -0.1,  0.1,  0.5),   # QoQ % (pct)
    "CAD": (-20.0,  -3.0,  3.0, 20.0),   # K persons
    "CHF": ( -0.5,  -0.1,  0.1,  0.5),   # QoQ % (pct)
}

_CFTC_MAP = {
    "EUR": "EURO FX - CHICAGO MERCANTILE EXCHANGE",
    "GBP": "BRITISH POUND - CHICAGO MERCANTILE EXCHANGE",
    "JPY": "JAPANESE YEN - CHICAGO MERCANTILE EXCHANGE",
    "CHF": "SWISS FRANC - CHICAGO MERCANTILE EXCHANGE",
    "CAD": "CANADIAN DOLLAR - CHICAGO MERCANTILE EXCHANGE",
    "AUD": "AUSTRALIAN DOLLAR - CHICAGO MERCANTILE EXCHANGE",
    "NZD": "NZ DOLLAR - CHICAGO MERCANTILE EXCHANGE",
}

# ╔══════════════════════════════════════════════════════════════════════════════
# ║  SCORING HELPERS
# ╚══════════════════════════════════════════════════════════════════════════════

def _score(v, t0, t1, t2, t3, invert=False):
    """Score value -1.0 to +1.0 using 4 thresholds."""
    if v is None:
        return 0.0
    try:
        v = float(v)
    except (TypeError, ValueError):
        return 0.0
    if invert:
        v = -v
        t0, t1, t2, t3 = -t3, -t2, -t1, -t0
    if v >= t3:
        return 1.0
    if v >= t2:
        return 0.5
    if v >= t1:
        return 0.0
    if v >= t0:
        return -0.5
    return -1.0


def _score_surprise(actual, forecast):
    """Beat/miss score. Returns None (not 0.0) when data is missing so _mean skips it."""
    if actual is None or forecast is None:
        return None
    try:
        actual = float(actual)
        forecast = float(forecast)
    except (TypeError, ValueError):
        return None
    diff = actual - forecast
    ref = abs(forecast) if abs(forecast) > 0.1 else 1.0
    pct = diff / ref * 100.0
    if pct >= 10:
        return 1.0
    if pct > 0:
        return 0.5
    if pct == 0:
        return 0.0
    if pct >= -10:
        return -0.5
    return -1.0


def _mean(*vals):
    """Mean of non-None values, return 0.0 if none."""
    clean = [float(v) for v in vals if v is not None]
    if not clean:
        return 0.0
    return sum(clean) / len(clean)


def _level(s):
    """Convert score float to label string."""
    if s > 0.60:
        return "STRONG BULLISH"
    if s > 0.30:
        return "SLIGHT BULLISH"
    if s > 0.10:
        return "MILD BULLISH"
    if s >= -0.10:
        return "NEUTRAL"
    if s >= -0.30:
        return "MILD BEARISH"
    if s >= -0.60:
        return "SLIGHT BEARISH"
    return "STRONG BEARISH"


def _parse_num(s):
    """Parse strings like '1.2K', '-0.3%', '$1.2B', '2.4' to float or None."""
    if s is None:
        return None
    if isinstance(s, (int, float)):
        try:
            f = float(s)
            return None if pd.isna(f) else f
        except (TypeError, ValueError):
            return None
    s = str(s).strip()
    if not s or s in ("", "-", "—", "N/A", "n/a", "null"):
        return None
    mult = 1.0
    s = s.replace("$", "").replace(",", "").replace("%", "").strip()
    if s.endswith("K") or s.endswith("k"):
        mult = 1_000.0
        s = s[:-1]
    elif s.endswith("M") or s.endswith("m"):
        mult = 1_000_000.0
        s = s[:-1]
    elif s.endswith("B") or s.endswith("b"):
        mult = 1_000_000_000.0
        s = s[:-1]
    try:
        return float(s) * mult
    except (ValueError, TypeError):
        return None

# ╔══════════════════════════════════════════════════════════════════════════════
# ║  FRESHNESS UTILITIES
# ╚══════════════════════════════════════════════════════════════════════════════

def _check_freshness(name: str, date_str: str, max_days: int) -> None:
    """Print console warning if the latest data point is older than max_days."""
    try:
        d = datetime.strptime(str(date_str)[:10], "%Y-%m-%d")
        age = (datetime.now() - d).days
        if age > max_days and _MACRO_DEBUG:
            print(
                f"[MACRO FRESHNESS] {name}: last obs {date_str[:10]} "
                f"is {age}d old (threshold {max_days}d)"
            )
    except Exception:
        pass


def _fred_fresh(series_id: str, name: str, max_days: int, limit: int = 10):
    """Fetch FRED series, run freshness check, return (current, prev).
    Returns (None, None) if data is stale (age > max_days) — caller should
    then try an alternative source (e.g. FF calendar)."""
    data = fetch_fred_series(series_id, limit)
    if data:
        try:
            age = (datetime.now() - datetime.strptime(data[-1][0][:10], "%Y-%m-%d")).days
            if age > max_days:
                if _MACRO_DEBUG:
                    print(f"[MACRO FRESHNESS] {name}: {data[-1][0]} is {age}d old (>{max_days}d), discarding")
                return None, None
        except Exception:
            pass
        return (data[-1][1], data[-2][1] if len(data) >= 2 else None)
    return None, None


def _fred_qoq_yoy_fresh(series_id: str, name: str, max_days: int):
    """Fetch quarterly index series, compute YoY% via 4-quarter comparison.

    Used for currencies whose CPI is published quarterly (AUD, NZD).
    Returns (current_yoy_pct, prev_yoy_pct) or (None, None) if stale/unavailable.
    Requires at least 6 quarterly observations (5 for current YoY, 6 for prev YoY).
    """
    data = fetch_fred_series(series_id, 8)
    if not data:
        return None, None
    try:
        age = (datetime.now() - datetime.strptime(data[-1][0][:10], "%Y-%m-%d")).days
        if age > max_days:
            if _MACRO_DEBUG:
                print(f"[MACRO FRESHNESS] {name}: {data[-1][0]} is {age}d old (>{max_days}d), discarding")
            return None, None
    except Exception:
        pass
    if len(data) < 5:
        return None, None
    try:
        curr = (data[-1][1] / data[-5][1] - 1.0) * 100.0
    except (ZeroDivisionError, TypeError):
        return None, None
    prev = None
    if len(data) >= 6:
        try:
            prev = (data[-2][1] / data[-6][1] - 1.0) * 100.0
        except (ZeroDivisionError, TypeError):
            pass
    return curr, prev

# ╔══════════════════════════════════════════════════════════════════════════════
# ║  FRED FETCH  (ttl=3600)
# ╚══════════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=3600, show_spinner=False)
def _fetch_fred_series_cached(series_id: str, limit: int = 36):
    """Internal implementation — only called when _FRED_KEY_VALID is True.
    Cached with 1-hour TTL so API calls are not repeated on every rerun."""
    try:
        url = (
            f"https://api.stlouisfed.org/fred/series/observations"
            f"?series_id={series_id}&api_key={FRED_API_KEY}"
            f"&file_type=json&sort_order=desc&limit={limit}"
        )
        r = requests.get(url, timeout=10)
        if r.status_code != 200:
            return []
        obs = r.json().get("observations", [])
        result = []
        for o in obs:
            try:
                val = float(o["value"])
                result.append((o["date"], val))
            except (KeyError, ValueError, TypeError):
                pass
        result.sort(key=lambda x: x[0])
        return result
    except Exception:
        return []


def fetch_fred_series(series_id: str, limit: int = 36):
    """Fetch FRED series, return list of (date_str, value) sorted ascending.

    Public wrapper: returns [] immediately (without touching the cache) when
    the API key is absent or invalid.  This prevents empty results from an
    invalid key being stored in the cache and masking a later valid key — the
    exact failure mode that caused USD GDP to appear static after first deploying
    with a placeholder key.  Once _FRED_KEY_VALID is True the inner cached
    function is called normally and the result is cached for 1 hour.
    """
    if not _FRED_KEY_VALID:
        return []
    return _fetch_fred_series_cached(series_id, limit)


def _fred_latest(series_id: str, limit: int = 36):
    """Return latest value or None."""
    data = fetch_fred_series(series_id, limit)
    if not data:
        return None
    return data[-1][1]


def _fred_latest_with_prev(series_id: str, limit: int = 10):
    """Return (current_value, previous_value) sorted ascending — both may be None."""
    data = fetch_fred_series(series_id, limit)   # fetch_fred_series already sorts asc
    if not data:
        return None, None
    if len(data) == 1:
        return data[0][1], None
    # data is sorted ascending: data[-1] = most recent, data[-2] = one before
    return data[-1][1], data[-2][1]


def _fred_yoy(series_id: str):
    """Calculate YoY % change from level series."""
    data = fetch_fred_series(series_id, 15)
    if len(data) < 13:
        return None
    try:
        current = data[-1][1]
        year_ago = data[-13][1]
        return (current / year_ago - 1.0) * 100.0
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def _gdp_qoq_from_fred(series_id: str, max_days: int = 270) -> tuple:
    """Fetch OECD GDP series from FRED; return (current_qoq_pct, prev_qoq_pct).

    Auto-detects whether the series returns a % change or an absolute level:
    - If |latest value| > 5  → treated as a GDP level (millions/billions of currency)
      and QoQ % = (curr / prev - 1) * 100 is computed from consecutive observations.
    - Otherwise → assumed to be already a % change (used as-is).

    max_days=270 (9 months): OECD publishes GDP with a 1-2 quarter lag on FRED;
    for AUD/NZD the observation date (end of reference quarter) can be ~8 months
    old by the time it appears on FRED (Q3 2025 = Sep 30 → ~243 days on 2026-05-31).
    The 270-day ceiling still rejects data older than ~3 quarters (genuinely stale).
    """
    data = fetch_fred_series(series_id, 6)
    if not data:
        return None, None
    try:
        age = (datetime.now() - datetime.strptime(data[-1][0][:10], "%Y-%m-%d")).days
        if age > max_days:
            if _MACRO_DEBUG:
                print(f"[MACRO FRESHNESS] GDP/{series_id}: {data[-1][0]} is {age}d old (>{max_days}d), discarding")
            return None, None
    except Exception:
        pass
    last_val = data[-1][1]
    if last_val is None:
        return None, None

    if abs(last_val) > 5.0:
        # Absolute level series — compute QoQ%
        if len(data) < 2 or not data[-2][1]:
            return None, None
        try:
            curr = (data[-1][1] / data[-2][1] - 1.0) * 100.0
        except (ZeroDivisionError, TypeError):
            return None, None
        prev = None
        if len(data) >= 3 and data[-3][1]:
            try:
                prev = (data[-2][1] / data[-3][1] - 1.0) * 100.0
            except (ZeroDivisionError, TypeError):
                pass
        return curr, prev
    else:
        # Already a % change series
        curr = data[-1][1]
        prev = data[-2][1] if len(data) >= 2 else None
        return curr, prev


def _fred_yoy_with_prev(series_id: str):
    """Return (current YoY %, previous month's YoY %) from monthly level series."""
    data = fetch_fred_series(series_id, 20)   # 20 obs — buffer for "." gaps in FRED
    curr = None
    prev = None
    if len(data) >= 13:
        try:
            curr = (data[-1][1] / data[-13][1] - 1.0) * 100.0
        except (TypeError, ValueError, ZeroDivisionError):
            pass
    if len(data) >= 14:
        try:
            prev = (data[-2][1] / data[-14][1] - 1.0) * 100.0
        except (TypeError, ValueError, ZeroDivisionError):
            pass
    return curr, prev


def _fred_mom_change(series_id: str, limit: int = 10):
    """Calculate MoM change (level diff) from series."""
    data = fetch_fred_series(series_id, limit)
    if len(data) < 2:
        return None
    try:
        return data[-1][1] - data[-2][1]
    except (TypeError, ValueError):
        return None


def _fred_mom_pct(series_id: str, limit: int = 10):
    """Calculate MoM % change from level series."""
    data = fetch_fred_series(series_id, limit)
    if len(data) < 2:
        return None
    try:
        prev = data[-2][1]
        if prev == 0:
            return None
        return (data[-1][1] / prev - 1.0) * 100.0
    except (TypeError, ValueError):
        return None

# ╔══════════════════════════════════════════════════════════════════════════════
# ║  ECB SDW FETCH  (ttl=3600)
# ╚══════════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_ecb_series(flow: str, key: str):
    """Fetch ECB SDW series, return latest float value or None."""
    try:
        url = (
            f"https://data-api.ecb.europa.eu/service/data/{flow}/{key}"
            f"?format=jsondata&lastNObservations=5"
        )
        r = requests.get(url, timeout=12)
        if r.status_code != 200:
            return None
        data = r.json()
        series_dict = data["dataSets"][0]["series"]
        first_key = list(series_dict.keys())[0]
        obs = series_dict[first_key]["observations"]
        latest_key = str(max(int(k) for k in obs.keys()))
        val = obs[latest_key][0]
        return float(val) if val is not None else None
    except Exception:
        return None


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_ecb_series_with_prev(flow: str, key: str):
    """Fetch ECB SDW series, return (latest, prev) from last 3 observations.
    Both may be None if the API is unavailable."""
    try:
        url = (
            f"https://data-api.ecb.europa.eu/service/data/{flow}/{key}"
            f"?format=jsondata&lastNObservations=3"
        )
        r = requests.get(url, timeout=12)
        if r.status_code != 200:
            return None, None
        data = r.json()
        series_dict = data["dataSets"][0]["series"]
        first_key = list(series_dict.keys())[0]
        obs = series_dict[first_key]["observations"]
        # obs keys are integer time-series indices; sort descending → newest first
        sorted_keys = sorted(obs.keys(), key=lambda x: int(x), reverse=True)
        vals = []
        for k in sorted_keys:
            v = obs[k][0]
            if v is not None:
                try:
                    vals.append(float(v))
                except (TypeError, ValueError):
                    pass
            if len(vals) >= 2:
                break
        return (vals[0] if vals else None,
                vals[1] if len(vals) >= 2 else None)
    except Exception:
        return None, None

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_ecb_series_dated(flow: str, key: str, n: int = 5):
    """Fetch ECB series; return [(period_str, value)] sorted ascending.
    period_str uses ECB's own format, e.g. '2026-04' for April 2026.
    Enables caller-side freshness checks without a second round-trip.
    """
    try:
        url = (f"https://data-api.ecb.europa.eu/service/data/{flow}/{key}"
               f"?format=jsondata&lastNObservations={n}")
        r = requests.get(url, timeout=12)
        if r.status_code != 200:
            return []
        data = r.json()
        series_dict = data["dataSets"][0]["series"]
        fk = list(series_dict.keys())[0]
        obs = series_dict[fk]["observations"]
        time_dim = data["structure"]["dimensions"]["observation"][0]
        rows = []
        for k, v in obs.items():
            if v[0] is not None:
                period = time_dim["values"][int(k)]["id"]
                rows.append((period, float(v[0])))
        rows.sort(key=lambda x: x[0])
        return rows
    except Exception:
        return []


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_ons_cpi_yoy():
    """GBP CPI All Items YoY% via ONS public CSV (series D7BT, index 2015=100).

    Confirmed working 2026-05-31: April 2026 = 2.82 %, age 31 days.
    No API key required. ONS releases ~3 weeks after month end.
    Returns (current_yoy, prev_yoy) or (None, None).
    """
    try:
        r = requests.get(
            "https://www.ons.gov.uk/generator?format=csv"
            "&uri=/economy/inflationandpriceindices/timeseries/d7bt/mm23",
            timeout=12, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200:
            return None, None
        rows = list(_csv.reader(io.StringIO(r.text)))
        monthly = [
            (row[0].strip(), float(row[1].strip()))
            for row in rows
            if len(row) >= 2
            and row[0].strip()[:4].isdigit()
            and " " in row[0].strip()
            and "Q" not in row[0].strip()
        ]
        if len(monthly) < 13:
            return None, None
        cur = monthly[-1]; p12 = monthly[-13]
        p1  = monthly[-2]; p13 = monthly[-14] if len(monthly) >= 14 else None
        yoy      = (cur[1] / p12[1] - 1.0) * 100.0
        prev_yoy = (p1[1]  / p13[1] - 1.0) * 100.0 if p13 else None
        return yoy, prev_yoy
    except Exception:
        return None, None


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_abs_cpi():
    """AUD Monthly CPI Indicator via ABS Data API (dataset 'CPI', no key required).

    Dynamically locates the 'All groups CPI' (headline) and
    'All groups CPI excluding food and energy' (core proxy) monthly YoY% series
    for Australia + Original estimate.

    Confirmed 2026-05-31: April 2026 = 4.20% headline / 3.30% core, ~31 d old.
    Freshness gate: 60 days (rejects if latest period is >2 months old).
    Returns (cpi_yoy, cpi_prev, core_yoy, core_prev) or (None, None, None, None).
    """
    try:
        r = requests.get("https://api.data.abs.gov.au/data/CPI?lastNObservations=4",
                         timeout=15)
        if r.status_code != 200:
            return None, None, None, None
        d = r.json()
        struct = d["structure"]
        dims = struct["dimensions"]["series"]
        time_vals = [v["id"] for v in struct["dimensions"]["observation"][0]["values"]]

        def _n(dim): return {i: v.get("name", "") for i, v in enumerate(dim.get("values", []))}
        def _c(dim): return {i: v.get("id", "")   for i, v in enumerate(dim.get("values", []))}

        m_n = _n(dims[0]); i_n = _n(dims[1]); t_n = _n(dims[2]); r_n = _n(dims[3]); f_c = _c(dims[4])

        m_yoy  = next((i for i, n in m_n.items() if "previous year" in n.lower()), None)
        i_all  = next((i for i, n in i_n.items() if n.lower().strip() == "all groups cpi"), None)
        i_core = next((i for i, n in i_n.items() if "food and energy" in n.lower() and "excluding" in n.lower()), None)
        r_aus  = next((i for i, n in r_n.items() if n.lower().strip() == "australia"), None)
        t_orig = next((i for i, n in t_n.items() if "original" in n.lower()), None)
        f_m    = next((i for i, c in f_c.items() if c == "M"), None)

        if None in (m_yoy, i_all, i_core, r_aus, t_orig, f_m):
            return None, None, None, None

        series_data = d["dataSets"][0]["series"]

        def _extract(idx_dim):
            key = f"{m_yoy}:{idx_dim}:{t_orig}:{r_aus}:{f_m}"
            s = series_data.get(key, {})
            obs = [(time_vals[int(k)], ob[0])
                   for k, ob in s.get("observations", {}).items()
                   if int(k) < len(time_vals) and "Q" not in time_vals[int(k)]]
            obs.sort(key=lambda x: x[0])
            if not obs:
                return None, None, None
            last = obs[-1]; prev = obs[-2] if len(obs) >= 2 else (None, None)
            return last[0], last[1], (prev[1] if prev[0] else None)

        h_period, h_val, h_prev = _extract(i_all)
        _, c_val, c_prev        = _extract(i_core)

        if not h_period:
            return None, None, None, None

        # Freshness gate: 60 days for monthly data
        try:
            _y, _m = map(int, h_period.split("-"))
            import calendar as _cal
            _ld = _cal.monthrange(_y, _m)[1]
            _age = (datetime.now().date() - datetime(_y, _m, _ld).date()).days
            if _age > 60:
                if _MACRO_DEBUG:
                    print(f"[MACRO FRESHNESS] CPI/AUD ABS: {h_period} is {_age}d old (>60d), discarding")
                return None, None, None, None
        except Exception:
            pass

        return h_val, h_prev, c_val, c_prev
    except Exception:
        return None, None, None, None


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_eurostat_hicp(geo: str):
    """HICP annual rate of change (YoY%) via Eurostat ei_cphi_m dataset.

    Works for any EEA geo code, confirmed locally:
      geo='EA' → Euro Area,   April 2026 = 3.00% / core 2.20%  (age 31 d)
      geo='CH' → Switzerland, April 2026 = 0.50% / core 0.30%  (age 31 d)

    Query filtered to RT12 unit + since 2025-01 → ~10 KB payload.
    Freshness gate: 45 days.
    Returns (headline_yoy, headline_prev, core_yoy, core_prev) or (None,None,None,None).
    """
    try:
        r = requests.get(
            f"https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/"
            f"ei_cphi_m?geo={geo}&unit=RT12&sinceTimePeriod=2025-01&format=JSON&lang=EN",
            timeout=15)
        if r.status_code != 200:
            return None, None, None, None
        d = r.json()
        ids  = d.get("id", [])
        sizes= d.get("size", [])
        vals = d.get("value", {})
        time_labels = list(d["dimension"]["time"]["category"]["label"].values())
        indic_index = {k: i for i, k in enumerate(
            d["dimension"]["indic"]["category"]["label"].keys())}
        n_time  = sizes[ids.index("time")]  if "time"  in ids else len(time_labels)
        # With unit=RT12 filtered, flat index = indic_i * n_time + time_i
        def _val(indic_key, t_off):
            i = indic_index.get(indic_key)
            t = n_time + t_off        # t_off=-1 → latest, -2 → prev
            return float(vals[str(i * n_time + t)]) if i is not None and 0 <= t < n_time and str(i * n_time + t) in vals else None
        h_val  = _val("TOTAL",      -1);  h_prev = _val("TOTAL",      -2)
        c_val  = _val("CP-HI00XEF", -1);  c_prev = _val("CP-HI00XEF", -2)
        if h_val is None:
            return None, None, None, None
        # Freshness gate: 45 days
        last_period = time_labels[-1] if time_labels else ""
        try:
            _ey, _em = map(int, last_period.split("-"))
            import calendar as _cal2
            _ld = _cal2.monthrange(_ey, _em)[1]
            _age = (datetime.now().date() - datetime(_ey, _em, _ld).date()).days
            if _age > 45:
                if _MACRO_DEBUG:
                    print(f"[MACRO FRESHNESS] HICP/{geo}: {last_period} is {_age}d old (>45d), discarding")
                return None, None, None, None
        except Exception:
            pass
        return h_val, h_prev, c_val, c_prev
    except Exception:
        return None, None, None, None


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_statcan_cpi():
    """CAD CPI All-items via Statistics Canada WDS API.

    Table 18-10-0004-01, coordinate 1.1 (All items, Canada, NSA, 2002=100).
    YoY% computed from 14-month window of monthly index values.
    Timeout 25 s + 1 retry. Times out from some networks (incl. local dev)
    but expected to succeed from Streamlit Cloud's server IP.
    Freshness gate: 60 days.
    Returns (cpi_yoy, prev_yoy) or (None, None).
    """
    url = ("https://www150.statcan.gc.ca/t1/tbl1/en/tv.action/"
           "getDataFromCubePidCoordAndLatestNPeriods/1810000401/1.1/14")
    for _attempt in range(2):
        try:
            r = requests.get(url, timeout=25, headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code != 200:
                break
            data = r.json()
            obs  = data if isinstance(data, list) else data.get("object", data.get("data", []))
            obs  = sorted([o for o in obs if o.get("value") is not None],
                          key=lambda x: x.get("refPer", ""))
            if len(obs) < 13:
                break
            curr   = float(obs[-1]["value"]);  y12  = float(obs[-13]["value"])
            prev1  = float(obs[-2]["value"]);   y13  = float(obs[-14]["value"]) if len(obs) >= 14 else None
            yoy      = (curr  / y12  - 1.0) * 100.0
            prev_yoy = (prev1 / y13  - 1.0) * 100.0 if y13 else None
            # Freshness gate: 60 days
            ref = obs[-1].get("refPer", "")
            try:
                _cy, _cm = map(int, ref[:7].split("-"))
                import calendar as _cal3
                _cld = _cal3.monthrange(_cy, _cm)[1]
                if (datetime.now().date() - datetime(_cy, _cm, _cld).date()).days > 60:
                    return None, None
            except Exception:
                pass
            return yoy, prev_yoy
        except requests.Timeout:
            if _attempt == 0:
                continue
            break
        except Exception:
            break
    return None, None


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_ons_core_cpi_yoy():
    """GBP Core CPI YoY% via ONS public CSV (series DKO8, ex energy, food,
    alcohol & tobacco — the true UK core measure).

    DKO8 is published as a direct YoY % — no index conversion needed.
    (D7G7, used previously, is the ALL-ITEMS headline annual rate, not core.)
    Confirmed 2026-05-31: April 2026 = 2.5 %, age 31 days.
    No API key required.  Returns (current_yoy, prev_yoy) or (None, None).
    """
    try:
        r = requests.get(
            "https://www.ons.gov.uk/generator?format=csv"
            "&uri=/economy/inflationandpriceindices/timeseries/dko8/mm23",
            timeout=12, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200:
            return None, None
        rows = list(_csv.reader(io.StringIO(r.text)))
        monthly = [
            (row[0].strip(), float(row[1].strip()))
            for row in rows
            if len(row) >= 2
            and row[0].strip()[:4].isdigit()
            and " " in row[0].strip()
            and "Q" not in row[0].strip()
        ]
        if not monthly:
            return None, None
        cur  = monthly[-1]
        prev = monthly[-2] if len(monthly) >= 2 else None
        return cur[1], (prev[1] if prev else None)
    except Exception:
        return None, None


# ╔══════════════════════════════════════════════════════════════════════════════
# ║  YFINANCE FETCH  (ttl=900)
# ╚══════════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=900, show_spinner=False)
def fetch_yf_price(ticker: str):
    """Fetch latest close price from yfinance."""
    try:
        import yfinance as yf
        df = yf.download(ticker, period="10d", progress=False, auto_adjust=True)
        if df.empty:
            return None
        close = df["Close"]
        # Handle MultiIndex columns returned by newer yfinance versions
        if isinstance(close, pd.DataFrame):
            close = close.iloc[:, 0]
        vals = close.dropna()
        if vals.empty:
            return None
        return float(vals.iloc[-1])
    except Exception:
        return None


@st.cache_data(ttl=900, show_spinner=False)
def fetch_yf_price_with_prev(ticker: str, lookback: int = 20):
    """Fetch latest close + ~lookback trading-days-ago close from yfinance.
    Returns (current, prev) — prev is approx 1 calendar month ago."""
    try:
        import yfinance as yf
        df = yf.download(ticker, period="60d", progress=False, auto_adjust=False)
        if df.empty:
            return None, None
        close = df["Close"]
        if isinstance(close, pd.DataFrame):
            close = close.iloc[:, 0]
        vals = close.dropna()
        if vals.empty:
            return None, None
        current = float(vals.iloc[-1])
        if len(vals) > lookback:
            prev = float(vals.iloc[-lookback])
        elif len(vals) > 1:
            prev = float(vals.iloc[0])
        else:
            prev = None
        return current, prev
    except Exception:
        return None, None

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_boc_rate(limit: int = 200):
    """Bank of Canada Target Overnight Rate via BoC Valet API (series V39079).
    V39079 = Target for the overnight rate (daily).
    V122530 = Bank Rate (target + 25 bps) — NOT used here.
    Returns [(date_str, value)] sorted ascending, or [] on failure."""
    try:
        url = "https://www.bankofcanada.ca/valet/observations/V39079/json?recent=200"
        r = requests.get(url, timeout=10)
        if r.status_code != 200:
            return []
        obs = r.json().get("observations", [])
        rows = []
        for ob in obs:
            try:
                date_str = ob["d"]
                val = float(ob["V39079"]["v"])
                rows.append((date_str, val))
            except Exception:
                continue
        rows.sort(key=lambda x: x[0])
        return rows[-limit:] if len(rows) > limit else rows
    except Exception:
        return []


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_usd_rate():
    """USD policy rate (target range upper bound) via NY Fed EFFR API.
    No API key required. Fetches ~800 calendar days to expose prior rate levels.
    Returns [(date_str, upper_rate)] sorted ascending, or [] on failure."""
    try:
        start_dt = (datetime.today() - timedelta(days=800)).strftime("%Y-%m-%d")
        end_dt   = datetime.today().strftime("%Y-%m-%d")
        url = (
            f"https://markets.newyorkfed.org/read?productCode=50"
            f"&startDt={start_dt}&endDt={end_dt}&eventCodes=500&format=json"
        )
        r = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200:
            return []
        rows = []
        for e in r.json().get("refRates", []):
            if e.get("type") != "EFFR":
                continue
            try:
                # Use published upper target when available; fall back to effective rate
                upper = e.get("targetRateTo") or e.get("percentRate")
                if upper is not None:
                    rows.append((e["effectiveDate"], float(upper)))
            except Exception:
                continue
        rows.sort(key=lambda x: x[0])
        return rows
    except Exception:
        return []


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_boe_rate():
    """GBP policy rate (Official Bank Rate) via BoE Statistics iadb API.
    No API key required. Fetches from 2020-01-01 to expose prior rate levels.
    Returns [(date_str, rate)] sorted ascending, or [] on failure."""
    try:
        url = (
            "https://www.bankofengland.co.uk/boeapps/iadb/fromshowcolumns.asp"
            "?csv.x=yes&Datefrom=01/Jan/2020&Dateto=now"
            "&SeriesCodes=IUDBEDR&UsingCodes=Y&CSVF=TT&html.x=66&html.y=26"
        )
        r = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200:
            return []
        rows = []
        data_started = False
        for line in r.text.strip().split("\n"):
            line = line.strip()
            if line.startswith("DATE"):
                data_started = True
                continue
            if not data_started or not line:
                continue
            parts = line.split(",")
            if len(parts) >= 2:
                try:
                    date_val = datetime.strptime(parts[0].strip(), "%d %b %Y")
                    rows.append((date_val.strftime("%Y-%m-%d"), float(parts[1].strip())))
                except Exception:
                    continue
        rows.sort(key=lambda x: x[0])
        return rows
    except Exception:
        return []


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_ecb_estr(limit: int = 200):
    """Euro Short-Term Rate (€STR) via ECB Data Portal — series EST/B.EU000A2X2A25.WT.
    No API key required. €STR tracks the ECB Deposit Facility Rate (DFR) within ~10 bps.
    Rounding to the nearest 25 bps recovers the exact DFR level reliably.
    Returns [(date_str, estr_rate)] sorted ascending, or [] on failure.
    """
    try:
        url = (
            "https://data-api.ecb.europa.eu/service/data/EST/B.EU000A2X2A25.WT"
            f"?format=jsondata&lastNObservations={limit}"
        )
        r = requests.get(url, timeout=12)
        if r.status_code != 200:
            return []
        data = r.json()
        series = data["dataSets"][0]["series"]
        k = list(series.keys())[0]
        obs = series[k]["observations"]
        periods = data["structure"]["dimensions"]["observation"][0]["values"]
        rows = []
        for idx_str, val_list in obs.items():
            try:
                date_str = periods[int(idx_str)]["id"]
                rows.append((date_str, float(val_list[0])))
            except Exception:
                continue
        rows.sort(key=lambda x: x[0])
        return rows
    except Exception:
        return []


def _estr_to_dfr(estr_rate: float) -> float:
    """Convert €STR to ECB DFR by rounding to the nearest 25 bps.
    €STR typically trades 0–10 bps below the DFR. Since the ECB always
    sets the DFR as a multiple of 25 bps, this rounding is exact."""
    return round(estr_rate / 0.25) * 0.25


# ╔══════════════════════════════════════════════════════════════════════════════
# ║  FOREXFACTORY CALENDAR  (ttl=1800)
# ╚══════════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=1800, show_spinner=False)
def fetch_ff_calendar():
    """Fetch ForexFactory calendar, return DataFrame."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Referer": "https://www.forexfactory.com/",
    }
    endpoints = [
        "https://nfs.faireconomy.media/ff_calendar_thisweek.json",
        "https://nfs.faireconomy.media/ff_calendar_lastweek.json",
        "https://nfs.faireconomy.media/ff_calendar_nextweek.json",
        "https://nfs.faireconomy.media/ff_calendar_month.json",
    ]
    rows = []
    seen = set()
    for url in endpoints:
        try:
            r = requests.get(url, headers=headers, timeout=10)
            if r.status_code != 200:
                continue
            for ev in r.json():
                try:
                    ccy = str(ev.get("currency") or ev.get("country") or "").upper()
                    title = str(ev.get("title", ""))
                    date_str = str(ev.get("date", ""))
                    impact = str(ev.get("impact", "")).lower()
                    actual = _parse_num(ev.get("actual"))
                    forecast = _parse_num(ev.get("forecast"))
                    previous = _parse_num(ev.get("previous"))
                    try:
                        date_val = pd.to_datetime(date_str, utc=True).tz_convert(None)
                    except Exception:
                        date_val = pd.Timestamp.now()
                    key = (ccy, title, date_val.date())
                    if key in seen:
                        continue
                    seen.add(key)
                    rows.append({
                        "currency": ccy,
                        "title": title,
                        "date": date_val,
                        "impact": impact,
                        "actual": actual,
                        "forecast": forecast,
                        "previous": previous,
                    })
                except Exception:
                    pass
        except Exception:
            pass
    if not rows:
        return pd.DataFrame(columns=["currency", "title", "date", "impact",
                                      "actual", "forecast", "previous"])
    df = pd.DataFrame(rows)
    df = df.sort_values("date").reset_index(drop=True)
    return df

# ╔══════════════════════════════════════════════════════════════════════════════
# ║  CFTC COT  (ttl=86400)
# ╚══════════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=86400, show_spinner=False)
def fetch_cot_data():
    """Fetch CFTC COT legacy data for recent years. Return combined DataFrame."""
    current_year = datetime.now().year
    years = range(2020, current_year + 1)
    dfs = []
    for yr in years:
        try:
            url = f"https://www.cftc.gov/files/dea/history/deacot{yr}.zip"
            r = requests.get(url, timeout=30)
            if r.status_code != 200:
                continue
            with zipfile.ZipFile(io.BytesIO(r.content)) as z:
                name = z.namelist()[0]
                with z.open(name) as f:
                    df = pd.read_csv(f, low_memory=False)
                    dfs.append(df)
        except Exception:
            pass
    if not dfs:
        return pd.DataFrame()
    return pd.concat(dfs, ignore_index=True)


def _cot_index(ccy: str):
    """Return COT index (0-100) for currency using 26-week min-max normalization."""
    if ccy not in _CFTC_MAP:
        return 50.0
    market_name = _CFTC_MAP[ccy]
    try:
        df = fetch_cot_data()
        if df.empty:
            return 50.0
        col_map = str(list(df.columns))
        name_col = "Market_and_Exchange_Names" if "Market_and_Exchange_Names" in df.columns else df.columns[0]
        mask = df[name_col].str.upper().str.contains(market_name.split(" - ")[0], na=False)
        sub = df[mask].copy()
        if sub.empty:
            return 50.0
        date_col = None
        for c in df.columns:
            if "date" in c.lower() or "report" in c.lower():
                date_col = c
                break
        if date_col:
            sub["_date"] = pd.to_datetime(sub[date_col], errors="coerce")
            sub = sub.sort_values("_date").tail(26)
        long_col = None
        short_col = None
        for c in df.columns:
            cl = c.lower()
            if "comm" in cl and "long" in cl and "all" in cl:
                long_col = c
            if "comm" in cl and "short" in cl and "all" in cl:
                short_col = c
        if long_col is None:
            for c in df.columns:
                if "comm" in c.lower() and "long" in c.lower():
                    long_col = c
                    break
        if short_col is None:
            for c in df.columns:
                if "comm" in c.lower() and "short" in c.lower():
                    short_col = c
                    break
        if long_col is None or short_col is None:
            return 50.0
        sub["_net"] = pd.to_numeric(sub[long_col], errors="coerce") - pd.to_numeric(sub[short_col], errors="coerce")
        sub = sub.dropna(subset=["_net"])
        if len(sub) < 3:
            return 50.0
        latest = sub["_net"].iloc[-1]
        mn = sub["_net"].min()
        mx = sub["_net"].max()
        if mx == mn:
            return 50.0
        return float((latest - mn) / (mx - mn) * 100.0)
    except Exception:
        return 50.0

# ╔══════════════════════════════════════════════════════════════════════════════
# ║  FF CALENDAR HELPERS — BEAT/MISS LOOKUP
# ╚══════════════════════════════════════════════════════════════════════════════


def _ff_beat_miss(ff_df: pd.DataFrame, ccy: str, pattern: str):
    """Find latest FF event matching pattern that has both actual+forecast populated.
    Iterates newest-first so a future event (no actual yet) doesn't shadow a past
    release. NaN (pandas' missing-value marker, which `is not None` does NOT catch)
    is treated as absent, so an unreleased event or one with no published forecast
    can never produce a spurious surprise.
    Returns (actual, forecast, surprise_score) — forecast/score are None when no
    genuine actual-vs-consensus comparison is available."""
    try:
        sub = ff_df[
            (ff_df["currency"] == ccy) &
            (ff_df["title"].str.contains(pattern, case=False, na=False))
        ].sort_values("date", ascending=False)   # newest first
        if sub.empty:
            return None, None, None
        # Best: most recent event where both actual AND forecast are present
        for _, row in sub.iterrows():
            if pd.notna(row["actual"]) and pd.notna(row["forecast"]):
                return (float(row["actual"]), float(row["forecast"]),
                        _score_surprise(row["actual"], row["forecast"]))
        # Released but no published forecast: surface the actual, no score
        for _, row in sub.iterrows():
            if pd.notna(row["actual"]):
                return float(row["actual"]), None, None
        return None, None, None
    except Exception:
        return None, None, None


def _ff_latest_two(ff_df: pd.DataFrame, ccy: str, pattern: str):
    """Return (current_val, prev_val) by scanning the last two actual releases.
    This is the canonical PREV source for FF-backed indicators — it finds two
    real released values rather than relying on the unreliable 'previous' field
    which ForexFactory often leaves null."""
    try:
        sub = ff_df[
            (ff_df["currency"] == ccy) &
            ff_df["title"].str.contains(pattern, case=False, na=False)
        ].sort_values("date", ascending=False)
        vals = []
        for _, row in sub.iterrows():
            if row["actual"] is not None:
                vals.append(float(row["actual"]))
            if len(vals) >= 2:
                break
        return (vals[0] if vals else None,
                vals[1] if len(vals) >= 2 else None)
    except Exception:
        return None, None

# ╔══════════════════════════════════════════════════════════════════════════════
# ║  DIMENSION CALCULATORS
# ╚══════════════════════════════════════════════════════════════════════════════

def _last_rate_changes(series_data):
    """Extract policy rate info from a step-function time series.

    Works for both daily (USD/GBP/CAD via live APIs) and monthly (FRED OECD) series.

    rate_delta_bps reflects the MOST RECENT CB DECISION:
      - Hold → 0 bps (rate unchanged from ~1 meeting cycle ago)
      - Cut/hike → ±N bps (change vs 1 meeting cycle ago)
    This is achieved by comparing the current rate to the rate ~1 meeting interval ago,
    NOT by finding the last distinct level (which would always show the last change,
    even if the CB has held for many consecutive meetings).

    Returns (current_rate, prev_rate, rate_delta_bps, prev_delta_bps):
      current_rate     — latest observed rate
      prev_rate        — rate in effect before the most recent change (for display)
      rate_delta_bps   — change vs ~1 meeting cycle ago (0 when CB is holding)
      prev_delta_bps   — size of the change before the most recent one
    """
    if not series_data:
        return None, None, 0.0, 0.0

    current_rate = series_data[-1][1]

    # ── Detect daily vs monthly by checking the gap between the last two dates ──
    is_daily = False
    if len(series_data) >= 2:
        try:
            d1 = datetime.strptime(series_data[-1][0][:10], "%Y-%m-%d")
            d2 = datetime.strptime(series_data[-2][0][:10], "%Y-%m-%d")
            is_daily = abs((d1 - d2).days) <= 7
        except Exception:
            pass

    # ── rate_delta: current vs 1 CB meeting cycle ago ──
    # Daily: ~44 trading days ≈ 9 calendar weeks (covers 2-3 typical meeting gaps)
    # Monthly: 2 months (covers 1-1.5 typical meeting gaps)
    lookback_n = 44 if is_daily else 2
    if len(series_data) > lookback_n:
        comparison_rate = series_data[-(lookback_n + 1)][1]
    elif len(series_data) > 1:
        comparison_rate = series_data[0][1]
    else:
        comparison_rate = current_rate
    rate_delta_bps = (current_rate - comparison_rate) * 100.0

    # ── prev_rate: rate before the most recent change (for Prev column display) ──
    # Walk backwards to find the last distinct level.
    levels = [current_rate]
    for i in range(len(series_data) - 2, -1, -1):
        val = series_data[i][1]
        if abs(val - levels[-1]) > 0.001:
            levels.append(val)
            if len(levels) >= 3:
                break

    prev_rate = levels[1] if len(levels) >= 2 else current_rate

    prev_delta_bps = 0.0
    if len(levels) >= 3:
        prev_delta_bps = (levels[1] - levels[2]) * 100.0

    return current_rate, prev_rate, rate_delta_bps, prev_delta_bps


def _d1_monetary(ccy: str, ff_df: pd.DataFrame):
    """D1: Monetary Policy — rate level vs neutral, delta, next move expectation."""
    N = _NEUTRAL_RATE[ccy]

    # ── Policy rate — layered fetch (no-key primary → FRED secondary → static fallback) ──
    #
    # Tier 1 — no API key needed (always attempted first):
    #   USD → NY Fed EFFR API  (targetRateTo = upper bound, daily)
    #   GBP → BoE iadb Stats API  (IUDBEDR daily)
    #   CAD → BoC Valet API  (V39079 = Target Overnight Rate, daily)
    #
    # Tier 2 — FRED daily/monthly (requires valid FRED_API_KEY in secrets):
    #   USD → DFEDTARU   EUR → ECBDFR   GBP → BOEBR   CAD → IRSTCB01CAM156N
    #
    # Tier 3 — ECB SDW monthly (no key, EUR only):
    #   EUR → FM/M.U2.EUR.RT0.DFR.R.1.Z5.I.A
    #
    # Tier 4 — OECD monthly FRED (JPY/AUD/NZD/CHF, requires FRED key):
    #   IRSTCB01{CCY}M156N
    #
    # Tier 5 — _FB_RATES static fallback (correct 2026 values, last resort)

    _CB_MONTHLY_FRED = {
        "JPY": "IRSTCB01JPM156N",
        "AUD": "IRSTCB01AUM156N",
        "NZD": "IRSTCB01NZM156N",
        "CHF": "IRSTCB01CHM156N",
    }

    rate            = None
    prev_rate       = None
    rate_delta      = 0.0
    prev_rate_delta = 0.0
    _r_data         = []
    _rate_is_live   = False   # True if rate came from a live API (not static fallback)

    if ccy == "USD":
        # Tier 1: NY Fed EFFR (no key)
        _r_data = fetch_usd_rate()
        if not _r_data:
            # Tier 2: FRED DFEDTARU (requires key)
            _r_data = fetch_fred_series("DFEDTARU", 500)
        if _r_data:
            _check_freshness("PolicyRate/USD", _r_data[-1][0], 5)
            rate, prev_rate, rate_delta, prev_rate_delta = _last_rate_changes(_r_data)
            _rate_is_live = True

    elif ccy == "EUR":
        # Tier 1: ECB €STR (no key) → round to nearest 25 bps = ECB DFR level.
        # The ECB FM dataset is unavailable on the new ECB Data Portal (HTTP 400).
        # €STR tracks the DFR within <10 bps; rounding to 25 bps recovers the exact DFR.
        _estr_data = fetch_ecb_estr(200)
        if _estr_data:
            # Convert each ESTR observation to DFR equivalent (round to 25 bps)
            _r_data = [(_d, _estr_to_dfr(_v)) for _d, _v in _estr_data]
            _check_freshness("PolicyRate/EUR", _r_data[-1][0], 5)
            rate, prev_rate, rate_delta, prev_rate_delta = _last_rate_changes(_r_data)
            # €STR can dip a few bps on individual days, causing _estr_to_dfr() to round
            # to a different 25-bps step (e.g. 1.874% → 1.75 instead of 2.00).
            # A single such outlier in the -(lookback+1) position produces a false ±25 bps
            # delta even when the ECB has been holding for months.
            # Fix: replace single-point lookback with a consensus (mode) over two windows.
            # • recent  = last 20 obs  (~4 calendar weeks)
            # • older   = obs [-90:-40] (~2–3 months ago, well past the last meeting)
            # Delta registers only when the two consensus levels genuinely differ.
            _n = len(_r_data)
            _recent_vals = [v for _, v in _r_data[max(0, _n - 20)          :      ]]
            _older_vals  = [v for _, v in _r_data[max(0, _n - 90): max(1, _n - 40)]]
            if _recent_vals:
                _mode_recent = max(set(_recent_vals), key=_recent_vals.count)
                rate = _mode_recent
                if _older_vals:
                    _mode_older = max(set(_older_vals), key=_older_vals.count)
                    rate_delta  = (_mode_recent - _mode_older) * 100.0
            _rate_is_live = True
        else:
            # Tier 2: FRED ECBDFR daily (requires key) — fallback if ECB API down
            _r_data = fetch_fred_series("ECBDFR", 500)
            if _r_data:
                _check_freshness("PolicyRate/EUR", _r_data[-1][0], 5)
                rate, prev_rate, rate_delta, prev_rate_delta = _last_rate_changes(_r_data)
                _rate_is_live = True

    elif ccy == "GBP":
        # Tier 1: BoE iadb Stats API (no key)
        _r_data = fetch_boe_rate()
        if not _r_data:
            # Tier 2: FRED BOEBR (requires key)
            _r_data = fetch_fred_series("BOEBR", 500)
        if _r_data:
            _check_freshness("PolicyRate/GBP", _r_data[-1][0], 5)
            rate, prev_rate, rate_delta, prev_rate_delta = _last_rate_changes(_r_data)
            _rate_is_live = True

    elif ccy == "CAD":
        # Tier 1: BoC Valet API (no key, daily — V39079 = Target Overnight Rate)
        _r_data = fetch_boc_rate(200)
        if _r_data:
            _check_freshness("PolicyRate/CAD", _r_data[-1][0], 10)  # daily data
            rate, prev_rate, rate_delta, prev_rate_delta = _last_rate_changes(_r_data)
            _rate_is_live = True
        else:
            # Tier 2: FRED OECD monthly (requires key)
            _r_data = fetch_fred_series("IRSTCB01CAM156N", 15)
            if _r_data:
                _check_freshness("PolicyRate/CAD", _r_data[-1][0], 60)
                rate, prev_rate, rate_delta, prev_rate_delta = _last_rate_changes(_r_data)
                _rate_is_live = True

    elif ccy in _CB_MONTHLY_FRED:
        # Tier 2/4: FRED OECD monthly (requires key).
        # REJECT if data is >90 days old: OECD series often lags 2-4 months and would
        # show the wrong (stale) rate. Fall through to static fallback in that case.
        _r_data_raw = fetch_fred_series(_CB_MONTHLY_FRED[ccy], 15)
        if _r_data_raw:
            try:
                _age = (datetime.now() - datetime.strptime(_r_data_raw[-1][0][:10], "%Y-%m-%d")).days
            except Exception:
                _age = 0
            if _age <= 90:
                _r_data = _r_data_raw
                _check_freshness(f"PolicyRate/{ccy}", _r_data[-1][0], 60)
                rate, prev_rate, rate_delta, prev_rate_delta = _last_rate_changes(_r_data)
                _rate_is_live = True
            elif _MACRO_DEBUG:
                print(f"[MACRO] PolicyRate/{ccy}: FRED data {_age}d old, using static fallback")

    # Tier 5: static fallback (correct 2026 values — only reached if all APIs fail/stale)
    if rate is None:
        rate = _FB_RATES.get(ccy)
    # prev_rate is resolved after the next-move block

    # Expected next move: use FF calendar for rate decision events
    next_move_diff = 0.0
    _next_is_live = False
    try:
        patterns = {"USD": "Fed", "EUR": "ECB", "GBP": "BOE", "JPY": "BOJ",
                    "AUD": "RBA", "NZD": "RBNZ", "CAD": "BOC", "CHF": "SNB"}
        pat = patterns.get(ccy, "")
        if pat and not ff_df.empty:
            sub = ff_df[
                (ff_df["currency"] == ccy) &
                (ff_df["title"].str.contains(pat, case=False, na=False))
            ].sort_values("date")
            if not sub.empty:
                row = sub.iloc[-1]
                actual = row["actual"]
                forecast = row["forecast"]
                if actual is not None and forecast is not None:
                    next_move_diff = float(actual) - float(forecast)
                    _next_is_live = True
    except Exception:
        pass

    if prev_rate is None:
        prev_rate = _FB_PREV_RATES.get(ccy)

    # When no live rate series was available, use the explicitly maintained _FB_RATE_DELTA.
    # This encodes the actual most-recent CB decision (0 = hold, ±N = change).
    # Computing it from (rate - prev_rate) would incorrectly show the *last change ever*,
    # not the last decision — e.g. EUR holding at 2.00 would show -25 bps from the prev
    # fallback of 2.25, even though ECB has been on hold for months.
    if not _r_data and rate_delta == 0.0:
        rate_delta = _FB_RATE_DELTA.get(ccy, 0.0)

    # Per-currency policy rate level thresholds
    if ccy == "JPY":
        # Asymmetric: near-zero neutral, >0.5% is genuinely restrictive/bullish
        s_level = _score(rate, -0.25, 0.0, 0.5, 1.0)
    elif ccy == "CHF":
        # SNB: neutral rate is 0.0; positive rates bullish, negative rates bearish
        # t2=0.25 ensures 0.00 falls in the neutral band (0.0 < 0.25)
        s_level = _score(rate, -0.75, -0.25, 0.25, 0.75)
    else:
        s_level = _score(rate, N - 1.0, N - 0.5, N + 0.5, N + 1.0)

    # Rate Delta: tighten neutral band so ±25 bps registers as directional
    if ccy == "JPY":
        # Hike = bullish for BoJ; hold (0 bps) must be neutral, not bullish
        # Neutral band [-5, +5] ensures exactly 0 bps scores 0.0
        s_delta = _score(rate_delta, -25.0, -5.0, 5.0, 15.0)
    else:
        s_delta = _score(rate_delta, -50.0, -10.0, 10.0, 50.0)

    s_next  = _score(next_move_diff, -0.30, -0.10, 0.10, 0.30)
    d1 = _mean(s_level, s_delta, s_next)
    # Source label reflects the actual data provider per currency. USD/EUR/GBP/CAD
    # have dedicated no-key APIs; JPY/AUD/NZD/CHF come from the FRED OECD series.
    _rate_label = {"USD": "NY Fed", "EUR": "ECB", "GBP": "BoE", "CAD": "BoC"}.get(ccy, "FRED OECD")
    _rate_src = _src(_rate_label, _rate_is_live)
    rows = [
        ("Policy Rate",        rate,           prev_rate,        None, None, s_level, _rate_src),
        ("Rate Delta (bps)",   rate_delta,     prev_rate_delta,  None, None, s_delta, _rate_src),
        ("Next Move Forecast", next_move_diff, None,             None, None, s_next,  _src("ForexFactory", _next_is_live)),
    ]
    return d1, rows


def _d2_inflation_growth(ccy: str, ff_df: pd.DataFrame):
    """D2: Inflation & Growth — CPI, core CPI, GDP, PMI."""
    cpi = None
    core_cpi = None
    gdp = None
    pmi = _FB_PMI.get(ccy)
    _pmi_is_live = False
    prev_cpi = None
    prev_core_cpi = None
    prev_gdp = None
    _cpi_is_live = False
    _gdp_is_live = False
    _cpi_src_label = "FRED/ECB"  # overridden below per actual source
    _ccpi_is_live   = False
    _ccpi_src_label = "FRED/ECB"  # core CPI source, tracked independently of headline

    # ── USD: FRED BLS (unchanged) ─────────────────────────────────────────────
    if ccy == "USD":
        cpi, prev_cpi           = _fred_yoy_with_prev("CPIAUCSL")
        core_cpi, prev_core_cpi = _fred_yoy_with_prev("CPILFESL")
        if cpi is not None: _cpi_is_live = True; _cpi_src_label = "FRED"
        if core_cpi is not None: _ccpi_is_live = True; _ccpi_src_label = "FRED"
        gdp_data = fetch_fred_series("A191RL1Q225SBEA", 5)
        gdp      = gdp_data[-1][1] if gdp_data else None
        prev_gdp = gdp_data[-2][1] if len(gdp_data) >= 2 else None
        if gdp_data:
            _check_freshness("GDP/USD", gdp_data[-1][0], 120)
            _gdp_is_live = True

    # ── CPI fetch hierarchy (non-USD) ─────────────────────────────────────────
    # Priority: ForexFactory → national primary API → FRED/ECB with tight gate → static.
    # Gates are now a safety net (reject >45 d monthly / >100 d quarterly), not a workaround.
    # ECB ICP and Eurostat prc_hicp_manr are confirmed to only carry data through Dec 2025
    # (5 months old) — they will be silently rejected until the APIs catch up.
    if ccy != "USD":
        # Step 1 — ForexFactory: carries the latest actual released value.
        # "CPI y/y" substring matches: EUR "Flash CPI y/y", GBP "CPI y/y",
        #   JPY "National CPI y/y"/"National Core CPI y/y", AUD "Monthly CPI Indicator y/y".
        # FF calendar on Streamlit Cloud has thisweek + lastweek + nextweek + month windows;
        # all April 2026 CPI releases (published May) fall within this rolling window.
        if ccy in ("EUR", "GBP", "JPY", "AUD") and not ff_df.empty:
            _ff_c, _ff_cp = _ff_latest_two(ff_df, ccy, "CPI y/y")
            if _ff_c is not None:
                cpi = _ff_c; prev_cpi = _ff_cp
                _cpi_is_live = True; _cpi_src_label = "ForexFactory"

        # Step 2 — ONS (GBP only): public CSV, no key, confirmed April 2026 = 2.82 %, 31 d.
        if cpi is None and ccy == "GBP":
            cpi, prev_cpi = fetch_ons_cpi_yoy()
            if cpi is not None:
                _cpi_is_live = True; _cpi_src_label = "ONS"

        # Step 3 — FRED / ECB with tight freshness gates.
        # 45 d monthly: accepts current-month release (~30 d), rejects 2-month-old OECD.
        # 100 d quarterly: accepts Q1 2026 (61 d from Mar 31); rejects Q4 2025+ (151 d).
        if cpi is None:
            if ccy == "EUR":
                # Eurostat ei_cphi_m: correct dataset, confirmed April 2026 = 3.00%.
                # prc_hicp_manr was the wrong dataset (frozen at Dec 2025); ei_cphi_m
                # is Eurostat's Euro Indicators series, updated same day as the press release.
                _eur_h, _eur_hp, _eur_c, _eur_cp = fetch_eurostat_hicp("EA")
                if _eur_h is not None:
                    cpi = _eur_h; prev_cpi = _eur_hp
                    _cpi_is_live = True; _cpi_src_label = "Eurostat"
                    if core_cpi is None and _eur_c is not None:
                        core_cpi = _eur_c; prev_core_cpi = _eur_cp
                        _ccpi_is_live = True; _ccpi_src_label = "Eurostat"

            elif ccy == "GBP":
                cpi, prev_cpi = _fred_fresh("CPALTT01GBM659N", "CPI/GBP", 45, 10)
                if cpi is not None: _cpi_is_live = True; _cpi_src_label = "FRED"

            elif ccy == "JPY":
                # JPNCPIALLMINMEI (MEI monthly index 2010=100) — 12-month YoY comparison.
                _jpy_raw = fetch_fred_series("JPNCPIALLMINMEI", 20)
                if _jpy_raw:
                    try:
                        _j_age = (datetime.now()
                                  - datetime.strptime(_jpy_raw[-1][0][:10], "%Y-%m-%d")).days
                        if _j_age <= 45 and len(_jpy_raw) >= 13:
                            cpi = (_jpy_raw[-1][1] / _jpy_raw[-13][1] - 1.0) * 100.0
                            prev_cpi = ((_jpy_raw[-2][1] / _jpy_raw[-14][1] - 1.0) * 100.0
                                        if len(_jpy_raw) >= 14 else None)
                            _cpi_is_live = True; _cpi_src_label = "FRED"
                    except Exception:
                        pass

            elif ccy == "AUD":
                # ABS Monthly CPI Indicator API (key-free, confirmed Apr 2026 = 4.20%, 31 d).
                _abs_h, _abs_hp, _abs_c, _abs_cp = fetch_abs_cpi()
                if _abs_h is not None:
                    cpi = _abs_h; prev_cpi = _abs_hp
                    _cpi_is_live = True; _cpi_src_label = "ABS"
                    if core_cpi is None and _abs_c is not None:
                        core_cpi = _abs_c; prev_core_cpi = _abs_cp
                        _ccpi_is_live = True; _ccpi_src_label = "ABS"
                else:
                    cpi, prev_cpi = _fred_qoq_yoy_fresh("AUSCPIALLQINMEI", "CPI/AUD", 100)
                    if cpi is not None: _cpi_is_live = True; _cpi_src_label = "FRED"

            elif ccy == "NZD":
                # FRED OECD quarterly CPI index (100-day gate, 4-quarter YoY).
                # Stats NZ API returns 502 from some networks; FRED is the reliable fallback.
                cpi, prev_cpi = _fred_qoq_yoy_fresh("NZLCPIALLQINMEI", "CPI/NZD", 100)
                if cpi is not None: _cpi_is_live = True; _cpi_src_label = "FRED"

            elif ccy == "CAD":
                # Statistics Canada WDS: 25 s timeout + 1 retry. Times out from some
                # networks (incl. local dev) but expected to work from Streamlit Cloud.
                _cad_h, _cad_hp = fetch_statcan_cpi()
                if _cad_h is not None:
                    cpi = _cad_h; prev_cpi = _cad_hp
                    _cpi_is_live = True; _cpi_src_label = "StatCan"
                else:
                    # FRED fallback with 45-day gate
                    cpi, prev_cpi = _fred_fresh("CPALTT01CAM659N", "CPI/CAD", 45, 10)
                    if cpi is not None: _cpi_is_live = True; _cpi_src_label = "FRED"

            elif ccy == "CHF":
                # Eurostat ei_cphi_m with geo=CH: confirmed April 2026 = 0.50%, 31 d old.
                _chf_h, _chf_hp, _chf_c, _chf_cp = fetch_eurostat_hicp("CH")
                if _chf_h is not None:
                    cpi = _chf_h; prev_cpi = _chf_hp
                    _cpi_is_live = True; _cpi_src_label = "Eurostat"
                    if core_cpi is None and _chf_c is not None:
                        core_cpi = _chf_c; prev_core_cpi = _chf_cp
                        _ccpi_is_live = True; _ccpi_src_label = "Eurostat"
                else:
                    cpi, prev_cpi = _fred_fresh("CPALTT01CHM659N", "CPI/CHF", 45, 10)
                    if cpi is not None: _cpi_is_live = True; _cpi_src_label = "FRED"

    # ── GDP fetch (non-USD) ───────────────────────────────────────────────────
    if ccy == "EUR":
        gdp, prev_gdp = _gdp_qoq_from_fred("NAEXKP01EZQ652S")
        if gdp is not None: _gdp_is_live = True
    elif ccy == "GBP":
        gdp, prev_gdp = _gdp_qoq_from_fred("NAEXKP01GBQ652S")
        if gdp is not None: _gdp_is_live = True
    elif ccy == "JPY":
        gdp, prev_gdp = _gdp_qoq_from_fred("JPNRGDPEXP")
        if gdp is not None: _gdp_is_live = True
    elif ccy == "AUD":
        gdp, prev_gdp = _gdp_qoq_from_fred("NAEXKP01AUQ657S")
        if gdp is not None: _gdp_is_live = True
    elif ccy == "NZD":
        gdp, prev_gdp = _gdp_qoq_from_fred("NAEXKP01NZQ657S")
        if gdp is not None: _gdp_is_live = True
    elif ccy == "CAD":
        gdp, prev_gdp = _gdp_qoq_from_fred("NAEXKP01CAQ652S")
        if gdp is not None: _gdp_is_live = True
    elif ccy == "CHF":
        gdp, prev_gdp = _gdp_qoq_from_fred("NAEXKP01CHQ652S")
        if gdp is not None: _gdp_is_live = True

    # ── Core CPI ──────────────────────────────────────────────────────────────
    # GBP: ONS DKO8 core (ex energy/food/alc/tobacco, direct YoY%, Apr 2026 = 2.5 %, 31 d). No key.
    # EUR: ECB ICP core with 45-day gate (currently Dec 2025, 151 d → rejected → static).
    # Others: FRED OECD 659N with 45-day gate — accepts if FRED has current month's data.
    if core_cpi is None and ccy == "GBP":
        core_cpi, prev_core_cpi = fetch_ons_core_cpi_yoy()
        if core_cpi is not None:
            _ccpi_is_live = True; _ccpi_src_label = "ONS"

    if core_cpi is None and ccy == "EUR":
        # Eurostat ei_cphi_m CP-HI00XEF (ex energy, food, alcohol, tobacco).
        # Populated from the same call as headline CPI above; this is a safety net
        # if that path was skipped (e.g. FF provided headline but not core).
        _, _, _eur_c2, _eur_cp2 = fetch_eurostat_hicp("EA")
        if _eur_c2 is not None:
            core_cpi = _eur_c2; prev_core_cpi = _eur_cp2
            _ccpi_is_live = True; _ccpi_src_label = "Eurostat"

    _CORE_CPI_FRED = {
        "JPY": "CPGRLE01JPM659N",
        "AUD": "CPGRLE01AUM659N",
        "NZD": "CPGRLE01NZM659N",
        "CAD": "CPGRLE01CAM659N",
        "CHF": "CPGRLE01CHM659N",
    }
    if core_cpi is None and ccy in _CORE_CPI_FRED:
        _cc_data = fetch_fred_series(_CORE_CPI_FRED[ccy], 10)
        if _cc_data:
            try:
                _cc_age = (datetime.now()
                           - datetime.strptime(_cc_data[-1][0][:10], "%Y-%m-%d")).days
            except Exception:
                _cc_age = 999
            if _cc_age <= 45:
                core_cpi = _cc_data[-1][1]
                prev_core_cpi = _cc_data[-2][1] if len(_cc_data) >= 2 else None
                _ccpi_is_live = True; _ccpi_src_label = "FRED"

    # Fallback — current values (static constants, updated periodically)
    if cpi is None:
        cpi = _FB_CPI.get(ccy)
    if core_cpi is None:
        core_cpi = _FB_CCPI.get(ccy)
    if gdp is None:
        gdp = _FB_GDP.get(ccy)
    # Fallback — previous period values (used when FRED is unavailable)
    if prev_cpi is None:
        prev_cpi = _FB_PREV_CPI.get(ccy)
    if prev_core_cpi is None:
        prev_core_cpi = _FB_PREV_CCPI.get(ccy)
    if prev_gdp is None:
        prev_gdp = _FB_PREV_GDP.get(ccy)

    # PMI from FF calendar — PREV via _ff_latest_two (last two actual releases)
    pmi_prev = None
    pmi_fcst = None
    pmi_bm   = None
    try:
        if not ff_df.empty:
            pat_map = {"USD": "ISM Manufacturing", "EUR": "Manufacturing PMI",
                       "GBP": "Manufacturing PMI", "JPY": "Manufacturing PMI",
                       "AUD": "Manufacturing PMI", "NZD": "Manufacturing PMI",
                       "CAD": "Ivey PMI", "CHF": "Manufacturing PMI"}
            pat = pat_map.get(ccy, "Manufacturing PMI")
            # Get current + prev from last two actual releases (reliable)
            pmi_live, pmi_prev = _ff_latest_two(ff_df, ccy, pat)
            if pmi_live is not None:
                pmi = pmi_live
                _pmi_is_live = True
            # Fetch forecast from the most recent event (for beat/miss label)
            sub_p = ff_df[
                (ff_df["currency"] == ccy) &
                ff_df["title"].str.contains(pat, case=False, na=False)
            ].sort_values("date", ascending=False)
            for _, r in sub_p.iterrows():
                if r["actual"] is not None:
                    pmi_fcst = r["forecast"]
                    pmi_bm   = _beat_miss_label(_score_surprise(pmi, pmi_fcst))
                    break
    except Exception:
        pass
    if pmi_prev is None:
        pmi_prev = _FB_PREV_PMI.get(ccy)

    # CPI: score by movement toward the 2% CB target.
    # Non-JPY — improvement = distance reduction from 2.0% vs previous period.
    #   Cooling from 3% toward 2% = bullish. Heating above 3% = bearish.
    #   Rising toward 2% from below 2% = bullish. Falling below 1% further = bearish.
    # JPY exception: any rising CPI = bullish (BoJ hiking trigger).
    _CPI_TGT = 2.0
    if ccy == "JPY":
        cpi_d  = (cpi      - prev_cpi)      if (cpi      is not None and prev_cpi      is not None) else None
        ccpi_d = (core_cpi - prev_core_cpi) if (core_cpi is not None and prev_core_cpi is not None) else None
        s_cpi  = _score(cpi_d,  -0.2, -0.05, 0.05, 0.2) if cpi_d  is not None else 0.0
        s_ccpi = _score(ccpi_d, -0.2, -0.05, 0.05, 0.2) if ccpi_d is not None else 0.0
    else:
        # Directional improvement toward the 2% CB target.
        # If prev was above target: cooling (curr < prev) = bullish → impr = prev - curr
        # If prev was below target: rising (curr > prev) = bullish → impr = curr - prev
        # This correctly handles the crossover case (e.g. 2.10→1.90: impr = 2.10-1.90 = +0.20).
        def _cpi_impr(curr, prev):
            if curr is None or prev is None:
                return None
            return (prev - curr) if prev > _CPI_TGT else (curr - prev)
        cpi_impr  = _cpi_impr(cpi,      prev_cpi)
        ccpi_impr = _cpi_impr(core_cpi, prev_core_cpi)
        s_cpi  = _score(cpi_impr,  -0.3, -0.05, 0.05, 0.3) if cpi_impr  is not None else 0.0
        s_ccpi = _score(ccpi_impr, -0.3, -0.05, 0.05, 0.3) if ccpi_impr is not None else 0.0
    # GDP: USD series is annualized QoQ %; all others are raw QoQ % (different scales).
    # Non-USD: score DIRECTION vs previous — accelerating growth = bullish, slowing = bearish.
    # Thresholds calibrated so a 0.10pp change in QoQ registers (e.g. 0.10 rise → +0.5).
    if ccy == "USD":
        s_gdp = _score(gdp, -0.5, 0.5, 1.5, 2.5)
    elif gdp is not None and prev_gdp is not None:
        s_gdp = _score(gdp - prev_gdp, -0.3, -0.05, 0.05, 0.3)
    else:
        s_gdp = _score(gdp, -0.2, 0.0, 0.3, 0.6)
    s_pmi  = _score(pmi, 47.0, 49.0, 51.0, 53.0)
    d2 = _mean(s_cpi, s_ccpi, s_gdp, s_pmi)
    _cpi_src = _src(_cpi_src_label, _cpi_is_live)
    _gdp_src = _src("FRED",        _gdp_is_live)
    rows = [
        ("CPI YoY %",         cpi,      prev_cpi,      None,     None,   s_cpi,  _cpi_src),
        ("Core CPI YoY %",    core_cpi, prev_core_cpi, None,     None,   s_ccpi, _src(_ccpi_src_label, _ccpi_is_live)),
        ("GDP QoQ %",         gdp,      prev_gdp,      None,     None,   s_gdp,  _gdp_src),
        ("Manufacturing PMI", pmi,      pmi_prev,      pmi_fcst, pmi_bm, s_pmi,  _src("ForexFactory", _pmi_is_live)),
    ]
    return d2, rows


def _d3_labour_activity(ccy: str, ff_df: pd.DataFrame):
    """D3: Labour & Activity — unemployment, trade balance, retail sales."""
    N_u = _NEUTRAL_UNEMP[ccy]
    t0, t1, t2, t3 = _TRADE_THRESH[ccy]

    unemp = None
    employ_change = None
    trade = _FB_TRADE.get(ccy)
    retail = _FB_RETAIL.get(ccy)

    # Unemployment
    fred_unemp_map = {
        "USD": "UNRATE",
        "EUR": "LRHUTTTTEZM156S",
        "GBP": "LRHUTTTTGBM156S",
        "JPY": "LRUNTTTTJPM156S",
        "AUD": "LRHUTTTTAUM156S",
        "CAD": "LRHUTTTTCAM156S",
        "CHF": "LRHUTTTTCHM156S",
        "NZD": "LRUNTTTTNUM156S",
    }
    prev_unemp = None
    unemp_is_live = False
    fred_key = fred_unemp_map.get(ccy)
    if fred_key:
        # 75-day gate: FRED dates monthly series at the PERIOD START, so a freshly
        # released figure is already ~30-65 days old by this measure. 45 wrongly
        # rejected the current release (e.g. USD UNRATE 61d) → static. 75 accepts the
        # latest monthly print while still rejecting genuinely stale (>2.5 month) data.
        unemp, prev_unemp = _fred_fresh(fred_key, f"Unemployment/{ccy}", 75, 10)
        if unemp is not None:
            unemp_is_live = True
    if unemp is None:
        unemp = _FB_UNEMP.get(ccy)
    if prev_unemp is None:
        prev_unemp = _FB_PREV_UNEMP.get(ccy)

    # Employment change — USD uses FRED PAYEMS (last two obs = current + prev MoM diff);
    # non-USD uses _ff_latest_two (last two actual releases, not row["previous"]).
    # All paths fall back to static dicts when live sources are unavailable.
    employ_prev = None
    try:
        if ccy == "USD":
            payems = fetch_fred_series("PAYEMS", 15)
            if len(payems) >= 2:
                employ_change = payems[-1][1] - payems[-2][1]
                employ_prev   = payems[-2][1] - payems[-3][1] if len(payems) >= 3 else None
            # FF fallback: _ff_latest_two for last two Nonfarm Payrolls actual releases
            if employ_change is None and not ff_df.empty:
                employ_change, employ_prev = _ff_latest_two(ff_df, "USD", "Non-Farm Employment Change")
                # FF stores NFP as "177K" → _parse_num gives 177000 (absolute).
                # FRED PAYEMS MoM diff is in thousands (177 for 177K jobs). Normalise.
                if employ_change is not None and abs(employ_change) > 1000:
                    employ_change /= 1000.0
                if employ_prev is not None and abs(employ_prev) > 1000:
                    employ_prev /= 1000.0
        else:
            # Non-USD: _ff_latest_two returns last two actual Employment Change releases
            if not ff_df.empty:
                employ_change, employ_prev = _ff_latest_two(ff_df, ccy, "Employment Change")
                # K-unit currencies: FF stores "38.5K" → 38500 → normalise to 38.5
                if ccy not in _EMPLOY_IS_PCT:
                    if employ_change is not None and abs(employ_change) > 1000:
                        employ_change /= 1000.0
                    if employ_prev is not None and abs(employ_prev) > 1000:
                        employ_prev /= 1000.0
    except Exception:
        employ_change = None
    employ_is_live = employ_change is not None
    # Static fallback for all currencies — ensures VALUE+PREV never both show "—"
    if employ_change is None:
        employ_change = _FB_EMPLOY.get(ccy)
    if employ_prev is None:
        employ_prev = _FB_PREV_EMPLOY.get(ccy)

    # Trade balance — USD: FRED BOPGSTB (monthly, USD millions → billions, ~45d lag)
    # Others: ForexFactory last two actual releases
    trade_prev = None
    trade_is_live = False
    if ccy == "USD":
        _tb_data = fetch_fred_series("BOPGSTB", 5)
        if _tb_data:
            trade = _tb_data[-1][1] / 1000.0          # millions → billions
            trade_prev = (_tb_data[-2][1] / 1000.0) if len(_tb_data) >= 2 else None
            trade_is_live = True
            _check_freshness("TradeBalance/USD", _tb_data[-1][0], 45)
    if trade == _FB_TRADE.get(ccy) or trade is None:
        try:
            if not ff_df.empty:
                trade_live, trade_prev = _ff_latest_two(ff_df, ccy, "Trade Balance")
                if trade_live is not None:
                    trade = trade_live
                    trade_is_live = True
        except Exception:
            pass
    if trade_prev is None:
        trade_prev = _FB_PREV_TRADE.get(ccy)

    # Retail sales — _ff_latest_two: last two actual releases (not row["previous"])
    retail_prev = None
    retail_is_live = False
    try:
        if not ff_df.empty:
            retail_live, retail_prev = _ff_latest_two(ff_df, ccy, "Retail Sales")
            if retail_live is not None:
                retail = retail_live
                retail_is_live = True
    except Exception:
        pass
    if retail_prev is None:
        retail_prev = _FB_PREV_RETAIL.get(ccy)

    # USD retail from FRED (overrides FF if we still have the fallback value)
    if ccy == "USD" and retail == _FB_RETAIL.get(ccy):
        retail_fred = _fred_mom_pct("RSXFS")
        if retail_fred is not None:
            retail = retail_fred
            retail_is_live = True

    # Unemployment: score direction of change — rising = bearish, falling = bullish
    # Tightened neutral band so a 0.10pp move registers (+0.10 >= 0.05 → -0.5 bearish)
    if prev_unemp is not None:
        s_unemp = _score(unemp - prev_unemp, -0.3, -0.05, 0.05, 0.3, invert=True)
    else:
        # No previous: fall back to absolute level vs natural rate
        s_unemp = _score(unemp, N_u - 1.5, N_u - 0.5, N_u + 0.5, N_u + 1.5, invert=True)
    # Employment Change: score the direction vs previous period.
    # Fewer jobs than last month = bearish regardless of absolute level.
    # Per-currency delta thresholds account for each economy's typical swing size.
    ed = _EMPLOY_DELTA_THRESH[ccy]
    if employ_prev is not None:
        employ_delta = employ_change - employ_prev
        s_employ = _score(employ_delta, ed[0], ed[1], ed[2], ed[3])
    else:
        # No previous: fall back to absolute level as crude signal
        if ccy in _EMPLOY_IS_PCT:
            s_employ = _score(employ_change, -1.0, -0.2, 0.2, 1.0)
        else:
            s_employ = _score(employ_change, -50.0, -10.0, 10.0, 50.0)
    # Trade Balance: score improvement vs previous — less negative / more positive = bullish
    # Per-currency delta thresholds account for each economy's typical swing size.
    td = _TRADE_DELTA_THRESH[ccy]
    if trade_prev is not None:
        s_trade = _score(trade - trade_prev, td[0], td[1], td[2], td[3])
    else:
        s_trade = _score(trade, t0, t1, t2, t3)
    s_retail = _score(retail, -0.3, 0.0, 0.5, 1.0)
    d3 = _mean(s_unemp, s_employ, s_trade, s_retail)
    rows = [
        ("Unemployment %",     unemp,         prev_unemp,  None, None, s_unemp,  _src("FRED/ECB", unemp_is_live)),
        ("Employment Change",  employ_change, employ_prev, None, None, s_employ, _src("FRED/FF", employ_is_live)),
        ("Trade Balance",      trade,         trade_prev,  None, None, s_trade,  _src("ForexFactory", trade_is_live)),
        ("Retail Sales MoM %", retail,        retail_prev, None, None, s_retail, _src("FRED/FF", retail_is_live)),
    ]
    return d3, rows


# ForexFactory event title substrings used to source each D4 surprise component.
# D4 scores ONLY genuine surprises — released ACTUAL vs published CONSENSUS forecast —
# so each component is matched to the FF release that carries a real forecast. A pattern
# that doesn't match (or a release with no published forecast) degrades safely: the
# component is dropped from the average and flagged, never back-filled with the prior
# reading. Strings follow ForexFactory's own event titles (e.g. "Non-Farm Employment
# Change", not "Nonfarm Payrolls").
_D4_SURPRISE_FF = {
    "USD": ("CPI m/m",                "GDP q/q", "Non-Farm Employment Change"),
    "EUR": ("CPI Flash Estimate y/y", "GDP q/q", "Employment Change q/q"),
    "GBP": ("CPI y/y",                "GDP m/m", "Employment Change"),
    "JPY": ("National Core CPI y/y",  "GDP q/q", "Employment Change"),
    "AUD": ("CPI q/q",                "GDP q/q", "Employment Change"),
    "NZD": ("CPI q/q",                "GDP q/q", "Employment Change q/q"),
    "CAD": ("CPI m/m",                "GDP m/m", "Employment Change"),
    "CHF": ("CPI m/m",                "GDP q/q", "Employment Change"),
}


def _d4_surprises(ccy: str, ff_df: pd.DataFrame):
    """D4: Economic Surprises — released ACTUAL vs published CONSENSUS forecast.

    A surprise only exists relative to a genuine market expectation, so every
    component (CPI, GDP, Employment) for every currency is scored exclusively
    from ForexFactory releases that carry BOTH an actual and a consensus
    forecast. When no published forecast is available the component is removed
    from the D4 average entirely — never back-filled with the prior reading
    (which would merely re-measure the change already scored in D2) — and
    flagged '⚠ no consensus' so the gap is visible, like the static-data flags.
    """
    cpi_pat, gdp_pat, emp_pat = _D4_SURPRISE_FF.get(ccy, ("CPI", "GDP", "Employment"))

    cpi_act, cpi_fore, s_cpi = _ff_beat_miss(ff_df, ccy, cpi_pat)
    gdp_act, gdp_fore, s_gdp = _ff_beat_miss(ff_df, ccy, gdp_pat)
    emp_act, emp_fore, s_emp = _ff_beat_miss(ff_df, ccy, emp_pat)

    # Employment is reported in thousands of persons for most currencies; scale the
    # DISPLAYED actual/forecast down so the value column stays readable (the surprise
    # score is scale-invariant). EUR/NZD/CHF report % q/q → leave untouched.
    if ccy not in _EMPLOY_IS_PCT:
        if emp_act  is not None and abs(emp_act)  > 1000: emp_act  /= 1000.0
        if emp_fore is not None and abs(emp_fore) > 1000: emp_fore /= 1000.0

    # Average only components that produced a real surprise (score not None);
    # 'Surprise Momentum' and the D4 score follow the same rule automatically.
    _subs = [s for s in (s_cpi, s_gdp, s_emp) if s is not None]
    momentum = (sum(_subs) / len(_subs)) if _subs else None
    _all  = [s for s in (s_cpi, s_gdp, s_emp, momentum) if s is not None]
    d4 = (sum(_all) / len(_all)) if _all else 0.0

    def _surprise_src(score, actual):
        # ⚠-prefixed sources render amber in the table, like the static-data flags.
        if score is not None:
            return "ForexFactory"
        return "⚠ no consensus" if actual is not None else "⚠ no data"

    rows = [
        ("CPI Surprise",        cpi_act,  None, cpi_fore, _beat_miss_label(s_cpi), s_cpi, _surprise_src(s_cpi, cpi_act)),
        ("GDP Surprise",        gdp_act,  None, gdp_fore, _beat_miss_label(s_gdp), s_gdp, _surprise_src(s_gdp, gdp_act)),
        ("Employment Surprise", emp_act,  None, emp_fore, _beat_miss_label(s_emp), s_emp, _surprise_src(s_emp, emp_act)),
        ("Surprise Momentum",   momentum, None, None,     None, momentum, "Composite"),
    ]
    return d4, rows


def _beat_miss_label(s):
    if s is None:
        return "—"
    if s > 0.3:
        return "BEAT"
    if s < -0.3:
        return "MISS"
    return "IN LINE"


def _d5_proxies(ccy: str, ff_df: pd.DataFrame):
    """D5: Currency-specific proxy indicators.
    PREV column = ~1 month ago value for market prices (20 trading days via yfinance),
    derived from component prev values for computed metrics (real rate, spread, carry).
    COT index rows leave PREV as None — no natural prior-period normalised comparison.
    """
    cot = _cot_index(ccy)

    rows = []
    scores = []

    if ccy == "USD":
        N = _NEUTRAL_RATE["USD"]

        # ── 10Y Yield — FRED (daily) with yfinance ^TNX fallback; both current + prev ──
        dgs10, dgs10_prev = None, None
        _dgs10_data = fetch_fred_series("DGS10", 60)
        if _dgs10_data:
            dgs10 = _dgs10_data[-1][1]
            dgs10_prev = _dgs10_data[-2][1] if len(_dgs10_data) >= 2 else None
        if dgs10 is None:
            dgs10, dgs10_prev = fetch_yf_price_with_prev("^TNX", 20)
        if dgs10_prev is None:
            dgs10_prev = 4.55  # static fallback: ~month-ago 10Y yield

        # ── 2Y Yield — FRED (daily) with yfinance ^IRX fallback ─────────────────
        dgs2, dgs2_prev = None, None
        _dgs2_data = fetch_fred_series("DGS2", 60)
        if _dgs2_data:
            dgs2 = _dgs2_data[-1][1]
            dgs2_prev = _dgs2_data[-2][1] if len(_dgs2_data) >= 2 else None
        if dgs2 is None:
            dgs2, dgs2_prev = fetch_yf_price_with_prev("^IRX", 20)

        # ── DXY — yfinance primary; alternative ticker fallback ──────────────────
        dxy, dxy_prev = fetch_yf_price_with_prev("DX-Y.NYB", 20)
        if dxy is None:
            dxy, dxy_prev = fetch_yf_price_with_prev("DX=F", 20)
        if dxy_prev is None:
            dxy_prev = 100.5  # static fallback: ~month-ago DXY level

        # ── Spread = 10Y – 2Y ────────────────────────────────────────────────────
        spread      = (dgs10 - dgs2)           if dgs10 is not None and dgs2 is not None else None
        spread_prev = (dgs10_prev - dgs2_prev) if dgs10_prev is not None and dgs2_prev is not None else None
        if spread_prev is None:
            spread_prev = -0.15  # static fallback: recent 2s10s spread

        # ── Fed Funds — current + prev for Rate vs Neutral ──────────────────────
        rate, rate_prev_raw = _fred_latest_with_prev("FEDFUNDS", 10)
        _usd_rate_live = rate is not None
        if rate is None:
            rate = _FB_RATES["USD"]
        if rate_prev_raw is None:
            rate_prev_raw = _FB_PREV_RATES["USD"]
        rate_vs_neutral      = rate - N
        rate_vs_neutral_prev = rate_prev_raw - N

        # ── Consumer Confidence — FRED UMCSENT + FF fallback ────────────────────
        conf, conf_prev = _fred_latest_with_prev("UMCSENT", 30)
        if conf is None:
            try:
                if not ff_df.empty:
                    for _cs_pat in ("Consumer Sentiment", "UoM Consumer", "Michigan Sentiment"):
                        sub_cs = ff_df[
                            (ff_df["currency"] == "USD") &
                            ff_df["title"].str.contains(_cs_pat, case=False, na=False)
                        ].sort_values("date", ascending=False)
                        for _, r in sub_cs.iterrows():
                            if r["actual"] is not None:
                                conf = float(r["actual"])
                                if conf_prev is None:
                                    conf_prev = r["previous"]
                                break
                        if conf is not None:
                            break
            except Exception:
                pass
        _conf_live = conf is not None
        if conf is None:
            conf = _FB_CONF_USD
        if conf_prev is None:
            conf_prev = 70.0  # static fallback: prior month UMich

        # DGS10: >4.0% = positive for USD (higher yields = tighter = bullish)
        # DXY: >98 = positive, <95 = negative; no invert — higher DXY = stronger USD
        # Conf: calibrated to UMCSENT scale (0-100); 70-90 = neutral-mild, >90 = strong
        # Rate vs Neutral: score the CHANGE (shrinking buffer = bearish, widening = bullish)
        rate_vs_neutral_delta = rate_vs_neutral - rate_vs_neutral_prev
        s1 = _score(dgs10, 3.0, 3.5, 4.0, 4.5)
        s2 = _score(dxy,   90.0, 95.0, 98.0, 102.0)
        s3 = _score(spread, -1.0, -0.2, 0.5, 1.0)
        s4 = _score(rate_vs_neutral_delta, -0.5, -0.1, 0.1, 0.5)
        s5 = _score(conf, 60.0, 70.0, 80.0, 90.0)
        scores = [s1, s2, s3, s4, s5]
        rows = [
            ("10Y Yield (DGS10)",   dgs10,             dgs10_prev,            None, None, s1, _src("FRED/yfinance", dgs10 is not None)),
            ("DXY Level",           dxy,               dxy_prev,              None, None, s2, _src("yfinance", dxy is not None)),
            ("2s10s Spread",        spread,            spread_prev,           None, None, s3, _src("FRED/yfinance", spread is not None)),
            ("Rate vs Neutral",     rate_vs_neutral,   rate_vs_neutral_prev,  None, None, s4, _src("FRED", _usd_rate_live)),
            ("Consumer Confidence", conf,              conf_prev,             None, None, s5, _src("FRED", _conf_live)),
        ]

    elif ccy == "EUR":
        eurchf, eurchf_prev = fetch_yf_price_with_prev("EURCHF=X", 20)
        # EUR/USD level — independent from D1 policy rate (no duplicate)
        eurusd, eurusd_prev = fetch_yf_price_with_prev("EURUSD=X", 20)
        _eurusd_live = eurusd is not None
        if eurusd is None:
            eurusd = 1.08
        if eurusd_prev is None:
            eurusd_prev = 1.06
        _eur_cpi_raw  = fetch_ecb_series("ICP", "M.U2.N.000000.4.ANR")
        cpi  = _eur_cpi_raw or _FB_CPI["EUR"]
        _eur_rate_raw = fetch_ecb_series("FM", "M.U2.EUR.RT0.DFR.R.1.Z5.I.A")
        rate = _eur_rate_raw or _FB_RATES["EUR"]
        rate_prev = _FB_PREV_RATES["EUR"]
        cpi_prev  = _FB_PREV_CPI["EUR"]
        pmi, pmi_prev = _FB_PMI["EUR"], None
        _eur_pmi_live = False
        try:
            if not ff_df.empty:
                sub = ff_df[(ff_df["currency"] == "EUR") &
                            ff_df["title"].str.contains("Manufacturing PMI", case=False, na=False)]
                sub_s = sub.sort_values("date")
                if not sub_s.empty and sub_s.iloc[-1]["actual"] is not None:
                    pmi      = float(sub_s.iloc[-1]["actual"])
                    pmi_prev = sub_s.iloc[-1]["previous"]
                    _eur_pmi_live = True
        except Exception:
            pass
        if pmi_prev is None:
            pmi_prev = _FB_PREV_PMI.get("EUR")
        real_rate      = (rate - cpi)           if rate and cpi else None
        real_rate_prev = (rate_prev - cpi_prev) if rate_prev and cpi_prev else None
        s1 = _score(cot, 30.0, 40.0, 60.0, 70.0)
        s2 = _score(pmi, 47.0, 49.0, 51.0, 53.0)
        s3 = _score(eurchf, 0.93, 0.95, 0.97, 0.99)
        # Real Rate: score DIRECTION of change — rising = bullish, falling = bearish
        s4 = (_score(real_rate - real_rate_prev, -0.5, -0.1, 0.1, 0.5)
              if real_rate is not None and real_rate_prev is not None
              else _score(real_rate, -1.0, -0.5, 0.5, 1.5))
        # EUR/USD: score direction vs previous — rising = bullish, flat = neutral
        s5 = _score(eurusd - eurusd_prev, -0.02, -0.005, 0.005, 0.02)
        scores = [s1, s2, s3, s4, s5]
        rows = [
            ("EUR COT Index",        cot,       None,           None, None, s1, _src("CFTC", cot is not None)),
            ("Mfg PMI",              pmi,       pmi_prev,       None, None, s2, _src("ForexFactory", _eur_pmi_live)),
            ("EURCHF Level",         eurchf,    eurchf_prev,    None, None, s3, _src("yfinance", eurchf is not None)),
            ("Real Rate (rate-CPI)", real_rate, real_rate_prev, None, None, s4, _src("FRED/ECB", bool(_eur_rate_raw) and bool(_eur_cpi_raw))),
            ("EUR/USD Level",        eurusd,    eurusd_prev,    None, None, s5, _src("yfinance", _eurusd_live)),
        ]

    elif ccy == "GBP":
        rate, rate_prev_raw = _fred_latest_with_prev("BOERUKM156N", 5)
        _gbp_rate_live = bool(rate)
        rate = rate or _FB_RATES["GBP"]
        rate_prev_raw = rate_prev_raw or _FB_PREV_RATES["GBP"]
        _gbp_cpi_raw = _fred_latest("CPALTT01GBM659N", 5)
        _gbp_cpi_live = bool(_gbp_cpi_raw)
        cpi      = _gbp_cpi_raw or _FB_CPI["GBP"]
        cpi_prev = _FB_PREV_CPI["GBP"]
        real_rate      = rate - cpi
        real_rate_prev = rate_prev_raw - cpi_prev
        N_gbp = _NEUTRAL_RATE["GBP"]

        # Services PMI — _ff_latest_two for reliable prev
        # UK is a services-led economy; Services PMI ≠ Manufacturing PMI (D2 already has Mfg)
        # Static fallback: 50.5 (Services historically runs above Manufacturing in UK)
        svc_pmi, svc_pmi_prev = 50.5, None
        _gbp_svc_live = False
        try:
            if not ff_df.empty:
                svc_live, svc_pmi_prev = _ff_latest_two(ff_df, "GBP", "Services PMI")
                if svc_live is not None:
                    svc_pmi = svc_live
                    _gbp_svc_live = True
        except Exception:
            pass
        if svc_pmi_prev is None:
            svc_pmi_prev = 50.0  # Services PMI prior period fallback

        # FTSE 100 — UK equity market as economic health / risk proxy
        # Replaces the duplicate CPI YoY % (already shown in D2)
        ftse, ftse_prev = fetch_yf_price_with_prev("^FTSE", 20)
        _gbp_ftse_live = ftse is not None
        if ftse is None:
            ftse = 7800.0
        if ftse_prev is None:
            ftse_prev = 7600.0

        # Services PMI: above 50 = expanding; t2=50.0 ensures 50.5 scores +0.5
        s1 = _score(svc_pmi, 46.0, 48.0, 50.0, 52.0)
        s2 = _score(cot, 30.0, 40.0, 60.0, 70.0)
        # Real Rate: score DIRECTION of change — rising = bullish, falling = bearish
        s3 = _score(real_rate - real_rate_prev, -0.5, -0.1, 0.1, 0.5)
        # Rate vs Neutral: score the CHANGE in buffer, not absolute level
        s4 = _score((rate - N_gbp) - (rate_prev_raw - N_gbp), -0.5, -0.1, 0.1, 0.5)
        s5 = _score(ftse, 7000.0, 7500.0, 8000.0, 8500.0)
        scores = [s1, s2, s3, s4, s5]
        rows = [
            ("UK Services PMI",      svc_pmi,          svc_pmi_prev,      None, None, s1, _src("ForexFactory", _gbp_svc_live)),
            ("GBP COT Index",        cot,               None,              None, None, s2, _src("CFTC", cot is not None)),
            ("Real Rate (rate-CPI)", real_rate,         real_rate_prev,    None, None, s3, _src("FRED", _gbp_rate_live and _gbp_cpi_live)),
            ("Rate vs Neutral",      rate - N_gbp,      rate_prev_raw - N_gbp, None, None, s4, _src("FRED", _gbp_rate_live)),
            ("FTSE 100",             ftse,              ftse_prev,         None, None, s5, _src("yfinance", _gbp_ftse_live)),
        ]

    elif ccy == "JPY":
        jpy_rate     = _FB_RATES["JPY"]
        # Capture both current AND prev FEDFUNDS so carry_prev reflects actual prior rate
        usd_rate, usd_rate_prev_live = _fred_latest_with_prev("FEDFUNDS", 10)
        _jpy_usdrate_live = bool(usd_rate)
        usd_rate     = usd_rate or _FB_RATES["USD"]
        usd_rate_prev = usd_rate_prev_live if usd_rate_prev_live is not None else _FB_PREV_RATES["USD"]
        _jpy_cpi_raw = _fred_latest("CPALTT01JPM659N", 5)
        jpy_cpi      = _jpy_cpi_raw or _FB_CPI["JPY"]
        jpy_cpi_prev = _FB_PREV_CPI["JPY"]
        carry        = usd_rate - jpy_rate
        carry_prev   = usd_rate_prev - jpy_rate
        vix,    vix_prev    = fetch_yf_price_with_prev("^VIX",  20)
        nikkei, nikkei_prev = fetch_yf_price_with_prev("^N225", 20)
        sp500,  sp500_prev  = fetch_yf_price_with_prev("^GSPC", 20)
        nk_sp      = (nikkei / sp500)           if nikkei and sp500 and sp500 > 0 else None
        nk_sp_prev = (nikkei_prev / sp500_prev) if nikkei_prev and sp500_prev and sp500_prev > 0 else None
        real_rate      = jpy_rate - jpy_cpi
        real_rate_prev = jpy_rate - jpy_cpi_prev  # BOJ rate unchanged; prior CPI

        s1 = _score(carry, 3.0, 4.0, 5.5, 6.5, invert=True)
        # VIX: score direction — rising VIX = more fear = safe-haven demand = bullish JPY
        # falling VIX = risk-on = bearish JPY
        s2 = _score(vix - vix_prev, -5.0, -1.0, 1.0, 5.0) if vix_prev is not None \
             else _score(vix, 12.0, 15.0, 22.0, 30.0)
        s3 = _score(cot, 30.0, 40.0, 60.0, 70.0)
        s4 = _score(nk_sp, 0.20, 0.22, 0.27, 0.30, invert=True)
        # Real Rate: score DIRECTION of change — rising = bullish, falling = bearish.
        # JPY real rates are deeply negative; use wider thresholds so a 0.60pp rise scores +0.5.
        s5 = (_score(real_rate - real_rate_prev, -1.5, -0.3, 0.3, 1.5)
              if real_rate_prev is not None
              else _score(real_rate, -3.0, -1.5, -0.5, 0.5))
        scores = [s1, s2, s3, s4, s5]
        rows = [
            ("USD-JPY Carry (inverted)",  carry,     carry_prev,    None, None, s1, _src("FRED", _jpy_usdrate_live)),
            ("VIX (inverted)",            vix,       vix_prev,      None, None, s2, _src("yfinance", vix is not None)),
            ("JPY COT Index",             cot,       None,          None, None, s3, _src("CFTC", cot is not None)),
            ("Nikkei/S&P ratio (inv)",    nk_sp,     nk_sp_prev,    None, None, s4, _src("yfinance", nk_sp is not None)),
            ("Real Rate (JPY rate-CPI)",  real_rate, real_rate_prev,None, None, s5, _src("FRED", bool(_jpy_cpi_raw))),
        ]

    elif ccy == "AUD":
        iron,  iron_prev  = fetch_yf_price_with_prev("BHP",  20)   # BHP — iron ore proxy
        crude, crude_prev = fetch_yf_price_with_prev("CL=F", 20)
        rate     = _FB_RATES["AUD"]
        _aud_cpi_raw = _fred_latest("CPALTT01AUM659N", 5)
        cpi      = _aud_cpi_raw or _FB_CPI["AUD"]
        cpi_prev = _FB_PREV_CPI["AUD"]
        real_rate      = rate - cpi
        real_rate_prev = rate - cpi_prev
        pmi = _FB_PMI["AUD"]
        try:
            if not ff_df.empty:
                sub = ff_df[(ff_df["currency"] == "AUD") &
                            ff_df["title"].str.contains("Manufacturing PMI", case=False, na=False)]
                sub_s = sub.sort_values("date")
                if not sub_s.empty and sub_s.iloc[-1]["actual"] is not None:
                    pmi = float(sub_s.iloc[-1]["actual"])
        except Exception:
            pass
        # Caixin PMI — _ff_latest_two returns last two CNY actual releases
        caixin, caixin_prev = _FB_PMI["AUD"], None
        _aud_caixin_live = False
        try:
            if not ff_df.empty:
                caixin_live, caixin_prev = _ff_latest_two(ff_df, "CNY", "Caixin")
                if caixin_live is not None:
                    caixin = caixin_live
                    _aud_caixin_live = True
        except Exception:
            pass
        if caixin_prev is None:
            caixin_prev = _FB_PREV_PMI.get("AUD")

        s1 = _score(iron, 35.0, 42.0, 52.0, 62.0)   # BHP NYSE price (~$40–60 range)
        # WTI: score direction vs previous — falling oil = bearish for AUD
        s2 = _score(crude - crude_prev, -10.0, -2.0, 2.0, 10.0) if crude_prev is not None \
             else _score(crude, 55.0, 65.0, 80.0, 95.0)
        s3 = _score(caixin, 47.0, 49.0, 51.0, 53.0)
        s4 = _score(cot, 30.0, 40.0, 60.0, 70.0)
        # Real Rate: score DIRECTION of change — rising = bullish, falling = bearish
        s5 = _score(real_rate - real_rate_prev, -0.5, -0.1, 0.1, 0.5)
        scores = [s1, s2, s3, s4, s5]
        rows = [
            ("Iron Ore (BHP proxy)",  iron,      iron_prev,      None, None, s1, _src("yfinance", iron is not None)),
            ("WTI Crude",             crude,     crude_prev,     None, None, s2, _src("yfinance", crude is not None)),
            ("Caixin PMI (China)",    caixin,    caixin_prev,    None, None, s3, _src("ForexFactory", _aud_caixin_live)),
            ("AUD COT Index",         cot,       None,           None, None, s4, _src("CFTC", cot is not None)),
            ("Real Rate (RBA-CPI)",   real_rate, real_rate_prev, None, None, s5, _src("FRED", bool(_aud_cpi_raw))),
        ]

    elif ccy == "NZD":
        # Dairy proxy — Fonterra Cooperative Group (FCG.NZ) on NZX; dairy drives ~25% of NZ exports
        dairy, dairy_prev = fetch_yf_price_with_prev("FCG.NZ", 20)
        _nzd_dairy_live = dairy is not None
        if dairy is None:
            dairy = 4.5   # static fallback: FCG.NZ ~NZD 4-5 range
        if dairy_prev is None:
            dairy_prev = 4.3
        # Gold — use spot XAUUSD=X (no futures roll distortion)
        gold, gold_prev = fetch_yf_price_with_prev("XAUUSD=X", 20)
        _nzd_gold_live = gold is not None
        if gold is None:
            gold = 3300.0
        if gold_prev is None:
            gold_prev = 3100.0
        rate     = _FB_RATES["NZD"]
        _nzd_cpi_raw = _fred_latest("CPALTT01NZM659N", 5)
        cpi      = _nzd_cpi_raw or _FB_CPI["NZD"]
        cpi_prev = _FB_PREV_CPI["NZD"]
        real_rate      = rate - cpi
        real_rate_prev = rate - cpi_prev
        # Caixin PMI — _ff_latest_two returns last two CNY actual releases
        caixin, caixin_prev = _FB_PMI["AUD"], None
        _nzd_caixin_live = False
        try:
            if not ff_df.empty:
                caixin_live, caixin_prev = _ff_latest_two(ff_df, "CNY", "Caixin")
                if caixin_live is not None:
                    caixin = caixin_live
                    _nzd_caixin_live = True
        except Exception:
            pass
        if caixin_prev is None:
            caixin_prev = _FB_PREV_PMI.get("AUD")

        # Dairy: score DIRECTION of change — rising price = bullish for NZD (25% of exports)
        # Thresholds calibrated for FCG.NZ NZD range (~$3-6); 0.12 rise scores +0.5
        s1 = (_score(dairy - dairy_prev, -0.3, -0.05, 0.05, 0.3)
              if dairy_prev is not None else _score(dairy, 3.0, 3.5, 4.5, 5.5))
        s2 = _score(caixin, 47.0, 49.0, 51.0, 53.0)
        s3 = _score(cot, 30.0, 40.0, 60.0, 70.0)
        # Real Rate: score DIRECTION of change — rising = bullish, falling = bearish
        s4 = _score(real_rate - real_rate_prev, -0.5, -0.1, 0.1, 0.5)
        # Gold: risk-off asset — higher gold = risk-off = bearish for NZD
        s5 = _score(gold, 2500.0, 2800.0, 3200.0, 3600.0, invert=True)
        scores = [s1, s2, s3, s4, s5]
        rows = [
            ("Dairy (Fonterra FCG.NZ)", dairy,     dairy_prev,     None, None, s1, _src("yfinance", _nzd_dairy_live)),
            ("Caixin PMI (China)",      caixin,    caixin_prev,    None, None, s2, _src("ForexFactory", _nzd_caixin_live)),
            ("NZD COT Index",           cot,       None,           None, None, s3, _src("CFTC", cot is not None)),
            ("Real Rate (RBNZ-CPI)",    real_rate, real_rate_prev, None, None, s4, _src("FRED", bool(_nzd_cpi_raw))),
            ("Gold (risk proxy)",       gold,      gold_prev,      None, None, s5, _src("yfinance", _nzd_gold_live)),
        ]

    elif ccy == "CAD":
        crude, crude_prev = fetch_yf_price_with_prev("CL=F", 20)
        rate     = _FB_RATES["CAD"]
        _cad_cpi_raw = _fred_latest("CPALTT01CAM659N", 5)
        cpi      = _cad_cpi_raw or _FB_CPI["CAD"]
        cpi_prev = _FB_PREV_CPI["CAD"]
        real_rate      = rate - cpi
        real_rate_prev = rate - cpi_prev
        usdcad, usdcad_prev = None, None
        try:
            usdcad, usdcad_prev = fetch_yf_price_with_prev("USDCAD=X", 20)
        except Exception:
            pass

        # TSX Composite — Canadian equity market as economic / commodity health proxy
        # Replaces duplicate "Oil Price (2nd proxy)" row (WTI already shown as row 1)
        tsx, tsx_prev = fetch_yf_price_with_prev("^GSPTSE", 20)
        _cad_tsx_live = tsx is not None
        if tsx is None:
            tsx = 22000.0
        if tsx_prev is None:
            tsx_prev = 21000.0
        # WTI: score direction vs previous — falling oil = bearish for CAD
        s1 = _score(crude - crude_prev, -10.0, -2.0, 2.0, 10.0) if crude_prev is not None \
             else _score(crude, 55.0, 65.0, 80.0, 95.0)
        s2 = _score(cot, 30.0, 40.0, 60.0, 70.0)
        # Real Rate: score DIRECTION of change — rising = bullish, falling = bearish
        s3 = _score(real_rate - real_rate_prev, -0.5, -0.1, 0.1, 0.5)
        # USD/CAD: score direction — rising USD/CAD = CAD weakening = bearish
        s4 = _score(usdcad - usdcad_prev, -0.03, -0.01, 0.01, 0.03, invert=True) \
             if usdcad_prev is not None else _score(usdcad, 1.28, 1.32, 1.38, 1.42, invert=True)
        s5 = _score(tsx, 18000.0, 20000.0, 22000.0, 24000.0)
        scores = [s1, s2, s3, s4, s5]
        rows = [
            ("WTI Crude",                crude,     crude_prev,     None, None, s1, _src("yfinance", crude is not None)),
            ("CAD COT Index",            cot,       None,           None, None, s2, _src("CFTC", cot is not None)),
            ("Real Rate (BOC-CPI)",      real_rate, real_rate_prev, None, None, s3, _src("FRED", bool(_cad_cpi_raw))),
            ("USD/CAD Level (inverted)", usdcad,    usdcad_prev,    None, None, s4, _src("yfinance", usdcad is not None)),
            ("TSX Composite",            tsx,       tsx_prev,       None, None, s5, _src("yfinance", _cad_tsx_live)),
        ]

    elif ccy == "CHF":
        # Gold — use spot XAUUSD=X (no futures roll distortion)
        gold,   gold_prev   = fetch_yf_price_with_prev("XAUUSD=X", 20)
        _chf_gold_live = gold is not None
        if gold is None:
            gold = 3300.0
        if gold_prev is None:
            gold_prev = 3100.0
        eurchf, eurchf_prev = fetch_yf_price_with_prev("EURCHF=X", 20)
        vix,    vix_prev    = fetch_yf_price_with_prev("^VIX",    20)
        rate     = _FB_RATES["CHF"]
        _chf_cpi_raw = _fred_latest("CPALTT01CHM659N", 5)
        cpi      = _chf_cpi_raw or _FB_CPI["CHF"]
        cpi_prev = _FB_PREV_CPI["CHF"]
        real_rate      = rate - cpi
        real_rate_prev = rate - cpi_prev

        # Gold: higher = bullish for CHF (safe-haven correlation)
        s1 = _score(gold, 2500.0, 2800.0, 3200.0, 3600.0)
        # EUR/CHF: higher = EUR stronger = CHF weaker = bearish for CHF
        s2 = _score(eurchf, 0.92, 0.94, 0.96, 0.98, invert=True)
        # VIX: score direction — rising VIX = fear = safe-haven demand = bullish CHF
        # falling VIX = risk-on = bearish CHF
        s3 = _score(vix - vix_prev, -5.0, -1.0, 1.0, 5.0) if vix_prev is not None \
             else _score(vix, 12.0, 15.0, 22.0, 30.0)
        s4 = _score(cot, 30.0, 40.0, 60.0, 70.0)
        # Real Rate: score DIRECTION of change — rising = bullish, falling = bearish
        s5 = _score(real_rate - real_rate_prev, -0.5, -0.1, 0.1, 0.5)
        scores = [s1, s2, s3, s4, s5]
        rows = [
            ("Gold Price",           gold,      gold_prev,      None, None, s1, _src("yfinance", _chf_gold_live)),
            ("EUR/CHF Level",        eurchf,    eurchf_prev,    None, None, s2, _src("yfinance", eurchf is not None)),
            ("VIX (inverted)",       vix,       vix_prev,       None, None, s3, _src("yfinance", vix is not None)),
            ("CHF COT Index",        cot,       None,           None, None, s4, _src("CFTC", cot is not None)),
            ("Real Rate (SNB-CPI)",  real_rate, real_rate_prev, None, None, s5, _src("FRED", bool(_chf_cpi_raw))),
        ]

    else:
        rows = []
        scores = [0.0]

    d5 = _mean(*scores) if scores else 0.0
    return d5, rows


# ╔══════════════════════════════════════════════════════════════════════════════
# ║  COMPOSITE SCORE CALCULATOR
# ╚══════════════════════════════════════════════════════════════════════════════

def _compute_currency_scores(ccy: str, ff_df: pd.DataFrame):
    """Compute all 5 dimensions and composite score for one currency."""
    d1, rows_d1 = _d1_monetary(ccy, ff_df)
    d2, rows_d2 = _d2_inflation_growth(ccy, ff_df)
    d3, rows_d3 = _d3_labour_activity(ccy, ff_df)
    d4, rows_d4 = _d4_surprises(ccy, ff_df)
    d5, rows_d5 = _d5_proxies(ccy, ff_df)

    # Average only over dimensions that actually carry data. A dimension is "empty"
    # (no data) when none of its indicator rows holds a numeric sub-score — e.g. D4
    # when no release in the window carries a consensus forecast. An empty dimension
    # is dropped from BOTH numerator and divisor so it can't dilute the bias toward
    # neutral; a dimension that HAS data but nets to 0.0 keeps numeric row scores and
    # still counts. This mirrors how _mean() already skips missing sub-scores WITHIN a
    # dimension. Divisor stays ≥1 in practice (D1/D2/D3/D5 are always populated via
    # static fallbacks). The *1.3 gain and _level() thresholds are unchanged.
    def _has_data(rows):
        return any(isinstance(r[5], float) for r in rows)

    _dims = [(d1, rows_d1), (d2, rows_d2), (d3, rows_d3), (d4, rows_d4), (d5, rows_d5)]
    _active = [score for score, rows in _dims if _has_data(rows)]
    composite = (sum(_active) / len(_active)) if _active else 0.0
    final = max(-1.0, min(1.0, composite * 1.3))

    all_rows = rows_d1 + rows_d2 + rows_d3 + rows_d4 + rows_d5

    return {
        "total": final,
        "level": _level(final),
        "d1": d1,
        "d2": d2,
        "d3": d3,
        "d4": d4,
        "d5": d5,
        "fmt": "indicator_12m",
        "currency": ccy,
    }, all_rows


# ╔══════════════════════════════════════════════════════════════════════════════
# ║  CACHE FUNCTION LIST (for .clear() on refresh)
# ╚══════════════════════════════════════════════════════════════════════════════
_CACHE_FUNS = [
    # fetch_fred_series is a plain wrapper; the cached inner function is below
    _fetch_fred_series_cached,
    fetch_ecb_series,
    fetch_ecb_series_with_prev,
    fetch_ecb_series_dated,
    fetch_ecb_estr,
    fetch_yf_price,
    fetch_yf_price_with_prev,
    fetch_usd_rate,
    fetch_boe_rate,
    fetch_boc_rate,
    fetch_ff_calendar,
    fetch_cot_data,
    # New key-free national CPI sources
    fetch_eurostat_hicp,
    fetch_abs_cpi,
    fetch_statcan_cpi,
    fetch_ons_cpi_yoy,
    fetch_ons_core_cpi_yoy,
]


def _clear_caches():
    """Clear all st.cache_data fetchers. Defensive: only calls .clear() on
    entries that actually expose it, so a plain wrapper accidentally left in
    the list can never raise AttributeError and crash the refresh path."""
    for fn in _CACHE_FUNS:
        clear = getattr(fn, "clear", None)
        if callable(clear):
            clear()

# ╔══════════════════════════════════════════════════════════════════════════════
# ║  CSS
# ╚══════════════════════════════════════════════════════════════════════════════

def _inject_css():
    _teal    = C["teal"]
    _teal70  = C["teal"] + "70"
    _bg      = C["bg"]
    _card    = C["card"]
    _border  = C["border"]
    _dim     = C["dim"]
    _muted   = C["muted"]
    _text    = C["text"]
    st.markdown(
        f"""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:ital,wght@0,400;0,500;0,600;0,700;0,800;1,400&display=swap');
  *{{-webkit-font-smoothing:antialiased;-moz-osx-font-smoothing:grayscale;}}
  [style*="font-family:monospace"],[style*="font-family: monospace"]{{font-family:'JetBrains Mono',monospace !important;}}
  [style*="font-family:sans-serif"],[style*="font-family: sans-serif"]{{font-family:'Inter',sans-serif !important;}}
  button{{font-family:'JetBrains Mono',monospace !important;}}
  html, body, [data-testid="stAppViewContainer"] {{
    background: {_bg} !important;
  }}
  [data-testid="stHeader"], [data-testid="stToolbar"] {{ display:none !important; }}
  section[data-testid="stSidebar"]                   {{ display:none !important; }}

  button[kind="secondary"] {{
    background:   {_dim}   !important;
    color:        {_muted} !important;
    border:       1px solid {_border} !important;
    font-family:  monospace  !important;
    font-weight:  600        !important;
    border-radius:8px        !important;
    transition:   border-color 0.22s ease, color 0.22s ease, box-shadow 0.22s ease !important;
  }}
  button[kind="secondary"]:hover {{
    border-color: {_teal70}                  !important;
    color:        {_teal}                    !important;
    box-shadow:   0 0 12px rgba(79,142,247,0.14) !important;
  }}
  [data-testid="stSelectbox"] > div > div,
  [data-testid="stTextInput"] input {{
    background:  {_card}   !important;
    border:      1px solid {_border} !important;
    color:       {_text}   !important;
    font-family: monospace !important;
    border-radius:8px      !important;
  }}
  [data-testid="stTextInput"] input::placeholder {{
    color: {_muted} !important;
  }}
  hr {{ border-color: {_border} !important; }}
  [data-testid="stSpinner"] {{ color: {_muted} !important; }}
</style>
""",
        unsafe_allow_html=True,
    )

# ╔══════════════════════════════════════════════════════════════════════════════
# ║  RENDER HELPERS
# ╚══════════════════════════════════════════════════════════════════════════════

def _fmt_val(v):
    """Format a value for display."""
    if v is None:
        return "—"
    try:
        f = float(v)
        if abs(f) >= 1000:
            return f"{f:,.0f}"
        if abs(f) >= 10:
            return f"{f:.1f}"
        return f"{f:.2f}"
    except (TypeError, ValueError):
        return str(v)


def _score_color(s):
    """Return color for a score."""
    if s is None:
        return C["muted"]
    try:
        s = float(s)
    except (TypeError, ValueError):
        return C["muted"]
    if s >= 0.5:
        return C["green"]
    if s <= -0.5:
        return C["red"]
    if s > 0.1:
        return C["yellow"]
    if s < -0.1:
        return C["yellow"]
    return C["muted"]


def _render_bias_bar(score: float, level: str):
    """Render horizontal bias bar from -1 to +1."""
    pct = int((score + 1.0) / 2.0 * 100.0)
    pct = max(0, min(100, pct))
    _green  = C["green"]
    _red    = C["red"]
    _muted  = C["muted"]
    _card   = C["card"]
    _border = C["border"]
    _text   = C["text"]
    if score > 0.10:
        bar_color = _green
        score_color = _green
    elif score < -0.10:
        bar_color = _red
        score_color = _red
    else:
        bar_color = _muted
        score_color = _muted
    sign = "+" if score > 0 else ""
    st.markdown(
        f"""
<div style='background:{_card};border:1px solid {_border};border-radius:12px;
            padding:20px 24px;margin-bottom:16px;'>
  <div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;'>
    <span style='font-size:11px;color:{_muted};font-family:monospace;
                 letter-spacing:2px;text-transform:uppercase;'>OVERALL BIAS</span>
    <span style='font-size:22px;font-weight:700;font-family:monospace;
                 color:{score_color};'>{sign}{score:.2f}</span>
  </div>
  <div style='background:#252525;border-radius:4px;height:8px;margin-bottom:10px;position:relative;'>
    <div style='background:{bar_color};border-radius:4px;height:8px;width:{pct}%;
                transition:width 0.4s ease;'></div>
    <div style='position:absolute;left:50%;top:0;width:1px;height:8px;
                background:rgba(255,255,255,0.15);'></div>
  </div>
  <div style='text-align:center;font-size:13px;font-weight:600;font-family:monospace;
              color:{score_color};letter-spacing:1px;'>{level}</div>
</div>
""",
        unsafe_allow_html=True,
    )


def _render_dim_chips(d1, d2, d3, d4, d5):
    """Render 5 dimension score chips."""
    dims = [
        ("D1 MONETARY", d1),
        ("D2 INFLATION", d2),
        ("D3 LABOUR", d3),
        ("D4 SURPRISE", d4),
        ("D5 PROXIES", d5),
    ]
    _card   = C["card"]
    _border = C["border"]
    _muted  = C["muted"]
    _text   = C["text"]

    html = "<div style='display:flex;gap:8px;flex-wrap:wrap;margin-bottom:20px;'>"
    for label, val in dims:
        col = _score_color(val)
        sign = "+" if val > 0 else ""
        html += (
            f"<div style='flex:1;min-width:90px;background:{_card};border:1px solid {col}40;"
            f"border-radius:8px;padding:10px 8px;text-align:center;'>"
            f"<div style='font-size:9px;color:{_muted};font-family:monospace;"
            f"letter-spacing:1.5px;margin-bottom:6px;'>{label}</div>"
            f"<div style='font-size:16px;font-weight:700;font-family:monospace;"
            f"color:{col};'>{sign}{val:.2f}</div>"
            f"</div>"
        )
    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)


def _render_indicators_table(rows: list):
    """Render indicators table with 20 rows."""
    _card   = C["card"]
    _border = C["border"]
    _muted  = C["muted"]
    _text   = C["text"]
    _bg     = C["bg"]

    _warn = "#f0b429"  # amber for ⚠ static markers

    hdr_style = (
        f"background:{_bg};color:{_muted};font-size:9px;font-family:monospace;"
        "letter-spacing:1.5px;padding:7px 10px;text-transform:uppercase;"
        "border-bottom:1px solid #252525;"
    )
    cell_style = (
        f"color:{_text};font-size:11px;font-family:monospace;"
        "padding:6px 10px;border-bottom:1px solid #1a1a1a;"
    )

    html = (
        f"<div style='background:{_card};border:1px solid {_border};border-radius:10px;"
        "overflow:hidden;margin-top:12px;'>"
        "<table style='width:100%;border-collapse:collapse;'>"
        "<thead><tr>"
        f"<th style='{hdr_style}'>Indicator</th>"
        f"<th style='{hdr_style};text-align:right;'>Value</th>"
        f"<th style='{hdr_style};text-align:right;'>Previous</th>"
        f"<th style='{hdr_style};text-align:right;'>Score</th>"
        f"<th style='{hdr_style};'>Source</th>"
        "</tr></thead><tbody>"
    )
    for row in rows:
        indicator, value, prev, forecast, beat_miss, score, source = row
        score_col = _score_color(score)
        score_val = f"{score:+.2f}" if isinstance(score, float) else "—"
        is_static = source.startswith("⚠")
        # Amber colour for ⚠ source entries so stale/static data is immediately visible
        src_col   = _warn if is_static else _muted
        src_disp  = source
        html += (
            "<tr>"
            f"<td style='{cell_style}'>{indicator}</td>"
            f"<td style='{cell_style};text-align:right;'>{_fmt_val(value)}</td>"
            f"<td style='{cell_style};text-align:right;color:{_muted};'>{_fmt_val(prev)}</td>"
            f"<td style='{cell_style};text-align:right;font-weight:700;color:{score_col};'>{score_val}</td>"
            f"<td style='{cell_style};font-size:9px;color:{src_col};'>{src_disp}</td>"
            "</tr>"
        )
    html += "</tbody></table></div>"
    st.markdown(html, unsafe_allow_html=True)


def _render_calendar(ff_df: pd.DataFrame, ccy: str):
    """Render ForexFactory calendar for currency, next 14 days."""
    _card   = C["card"]
    _border = C["border"]
    _muted  = C["muted"]
    _text   = C["text"]
    _red    = C["red"]
    _yellow = C["yellow"]
    _green  = C["green"]

    st.markdown(
        f"<div style='font-size:10px;color:{_muted};font-family:monospace;"
        "letter-spacing:2px;text-transform:uppercase;margin-bottom:10px;'>"
        f"▸ UPCOMING EVENTS — {CURRENCY_FLAG.get(ccy,'')} {ccy}</div>",
        unsafe_allow_html=True,
    )

    if ff_df.empty:
        st.markdown(f"<p style='color:{_muted};font-family:monospace;font-size:11px;'>No calendar data.</p>",
                    unsafe_allow_html=True)
        return

    today = pd.Timestamp.now().normalize()
    cutoff = today + pd.Timedelta(days=14)

    sub = ff_df[
        (ff_df["currency"] == ccy) &
        (ff_df["date"] >= today) &
        (ff_df["date"] <= cutoff)
    ].sort_values("date").reset_index(drop=True)

    # filter noise
    noise = ["bond", "treasury", "bill", "note", "jgb", "btp", "auction"]
    mask_noise = sub["title"].str.lower().apply(
        lambda t: not any(n in t for n in noise)
    )
    sub = sub[mask_noise].reset_index(drop=True)

    if sub.empty:
        st.markdown(
            f"<p style='color:{_muted};font-family:monospace;font-size:11px;'>"
            "No events in next 14 days.</p>",
            unsafe_allow_html=True,
        )
        return

    impact_color = {"high": _red, "medium": _yellow, "low": _muted}

    grouped = {}
    for _, row in sub.iterrows():
        day_key = row["date"].strftime("%a %b %d")
        if day_key not in grouped:
            grouped[day_key] = []
        grouped[day_key].append(row)

    html = (
        f"<div style='background:{_card};border:1px solid {_border};border-radius:10px;"
        "padding:12px;max-height:480px;overflow-y:auto;'>"
    )
    for day, events in grouped.items():
        html += (
            f"<div style='font-size:9px;color:{_muted};font-family:monospace;"
            f"letter-spacing:2px;text-transform:uppercase;margin:10px 0 6px;"
            f"padding-bottom:4px;border-bottom:1px solid #252525;'>{day}</div>"
        )
        for ev in events:
            impact = str(ev.get("impact", "")).lower()
            col = impact_color.get(impact, _muted)
            actual = _fmt_val(ev.get("actual"))
            forecast = _fmt_val(ev.get("forecast"))
            title = str(ev.get("title", ""))[:40]
            time_str = ev["date"].strftime("%H:%M") if hasattr(ev["date"], "strftime") else ""
            html += (
                f"<div style='display:flex;justify-content:space-between;align-items:center;"
                f"padding:4px 0;border-bottom:1px solid #1a1a1a;'>"
                f"<div style='display:flex;align-items:center;gap:6px;'>"
                f"<div style='width:6px;height:6px;border-radius:50%;background:{col};"
                f"flex-shrink:0;'></div>"
                f"<span style='font-size:11px;color:{_text};font-family:monospace;'>{title}</span>"
                f"</div>"
                f"<div style='display:flex;gap:10px;align-items:center;flex-shrink:0;'>"
                f"<span style='font-size:10px;color:{_muted};font-family:monospace;'>{time_str}</span>"
                f"<span style='font-size:10px;color:{_green if actual != '—' else _muted};"
                f"font-family:monospace;min-width:36px;text-align:right;'>A:{actual}</span>"
                f"<span style='font-size:10px;color:{_muted};font-family:monospace;"
                f"min-width:36px;text-align:right;'>F:{forecast}</span>"
                f"</div></div>"
            )
    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)


def _render_password_gate():
    """Render PRO password gate — blue theme, amber PRO badge only."""
    _card = C["card"]
    _muted = C["muted"]
    _text  = C["text"]
    _red   = C["red"]

    # Blue-toned CSS — PRO badge is the only amber element
    st.markdown(
        f"<style>"
        f"[data-testid='stTextInput'] input{{"
        f"background:#1c1c1c !important;"
        f"border:1px solid rgba(79,142,247,0.28) !important;"
        f"color:{_text} !important;"
        f"font-family:monospace !important;"
        f"border-radius:8px !important;"
        f"font-size:13px !important;"
        f"}}"
        f"[data-testid='stTextInput'] input::placeholder{{color:#555 !important;}}"
        f"[data-testid='stTextInput'] input:focus{{"
        f"border-color:rgba(79,142,247,0.65) !important;"
        f"box-shadow:0 0 0 3px rgba(79,142,247,0.10) !important;"
        f"}}"
        f"button[kind='secondary']{{"
        f"background:rgba(79,142,247,0.10) !important;"
        f"border:1px solid rgba(79,142,247,0.35) !important;"
        f"color:#4f8ef7 !important;"
        f"font-family:monospace !important;font-weight:700 !important;"
        f"font-size:11px !important;letter-spacing:3px !important;"
        f"border-radius:8px !important;"
        f"transition:all 0.22s ease !important;"
        f"}}"
        f"button[kind='secondary']:hover{{"
        f"background:rgba(79,142,247,0.18) !important;"
        f"border-color:rgba(79,142,247,0.65) !important;"
        f"box-shadow:0 0 16px rgba(79,142,247,0.18) !important;"
        f"}}"
        f"</style>",
        unsafe_allow_html=True,
    )

    _m3_back_col, _ = st.columns([1, 6])
    with _m3_back_col:
        if st.button("← Back to Hub", key="m3_back_gate"):
            st.switch_page("app.py")
    st.markdown("<div style='height:5vh;'></div>", unsafe_allow_html=True)
    _, col, _ = st.columns([2, 3, 2])
    with col:
        # Card
        st.markdown(
            f"<div style='background:{_card};"
            f"border:1px solid rgba(79,142,247,0.22);"
            f"border-radius:16px;"
            f"padding:48px 48px 40px;"
            f"text-align:center;"
            f"box-shadow:0 0 48px rgba(79,142,247,0.08),0 6px 32px rgba(0,0,0,0.35);'>"
            f"<div style='margin-bottom:24px;'>"
            f"<span style='background:#f0b429;color:#0a0c10;"
            f"font-size:10px;font-family:monospace;font-weight:800;"
            f"letter-spacing:3px;padding:4px 16px;border-radius:20px;"
            f"text-transform:uppercase;'>PRO</span>"
            f"</div>"
            f"<div style='font-size:40px;line-height:1;margin-bottom:22px;'>🔒</div>"
            f"<div style='font-size:24px;font-weight:800;color:{_text};"
            f"font-family:monospace;letter-spacing:-0.5px;margin-bottom:8px;'>"
            f"Economic Bias Engine</div>"
            f"<div style='font-size:10px;color:#4f8ef7;font-family:monospace;"
            f"letter-spacing:2px;text-transform:uppercase;margin-bottom:16px;'>"
            f"Module 3 &nbsp;·&nbsp; Real Edge Terminal</div>"
            f"<div style='font-size:12px;color:{_muted};"
            f"font-family:monospace;line-height:1.7;'>"
            f"5-dimension macro scoring &nbsp;·&nbsp; 8 major currencies</div>"
            f"</div>",
            unsafe_allow_html=True,
        )
        st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)
        pwd = st.text_input("", type="password", placeholder="Enter access code ···",
                            label_visibility="collapsed", key="m3_pwd_input")
        st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
        if st.button("UNLOCK", use_container_width=True, key="m3_unlock_btn"):
            if pwd == "12345":
                st.session_state["m3_auth"] = True
                st.rerun()
            else:
                st.markdown(
                    f"<p style='color:{_red};font-family:monospace;font-size:11px;"
                    "text-align:center;margin-top:8px;'>Incorrect access code.</p>",
                    unsafe_allow_html=True,
                )
    return False


def _render_header():
    """Render page header row."""
    _muted = C["muted"]
    _teal  = C["teal"]
    _text  = C["text"]

    col_back, col_title, col_refresh = st.columns([2, 5, 2])
    with col_back:
        if st.button("← Back to Terminal", key="m3_back"):
            st.switch_page("app.py")
    with col_title:
        st.markdown(
            f"""
<div style='text-align:center;'>
  <div style='font-size:10px;color:{_teal};font-family:monospace;
              letter-spacing:3px;text-transform:uppercase;margin-bottom:4px;'>
    ▸ MODULE 3
  </div>
  <div style='font-size:22px;font-weight:700;color:{_text};font-family:monospace;'>
    ECONOMIC BIAS ENGINE
  </div>
  <div style='font-size:11px;color:{_muted};font-family:monospace;margin-top:4px;'>
    5-Dimension macro scoring · 8 major currencies
  </div>
</div>
""",
            unsafe_allow_html=True,
        )
    with col_refresh:
        st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
        if st.button("🔄 Refresh", key="m3_refresh", use_container_width=True):
            _clear_caches()
            st.session_state["last_refresh_ts"] = time.time()
            for ccy in CURRENCIES:
                st.session_state.pop(f"macro_scores_{ccy}", None)
                st.session_state.pop(f"macro_rows_{ccy}",   None)
            st.rerun()


def _render_currency_pills(selected: str):
    """Render 8 currency pill buttons, return selected."""
    _card    = C["card"]
    _border  = C["border"]
    _muted   = C["muted"]
    _teal    = C["teal"]
    _teal_bg = C["teal_bg"]
    _text    = C["text"]

    cols = st.columns(8)
    new_selected = selected
    for i, ccy in enumerate(CURRENCIES):
        with cols[i]:
            flag = CURRENCY_FLAG.get(ccy, "")
            is_active = (ccy == selected)
            if is_active:
                st.markdown(
                    f"""
<div style='background:{_teal_bg};border:1px solid {_teal};border-radius:8px;
            padding:8px 4px;text-align:center;cursor:default;'>
  <div style='font-size:14px;'>{flag}</div>
  <div style='font-size:10px;color:{_teal};font-family:monospace;font-weight:700;'>{ccy}</div>
</div>
""",
                    unsafe_allow_html=True,
                )
            else:
                if st.button(f"{flag}\n{ccy}", key=f"m3_ccy_{ccy}", use_container_width=True):
                    new_selected = ccy
    return new_selected


# ╔══════════════════════════════════════════════════════════════════════════════
# ║  MAIN
# ╚══════════════════════════════════════════════════════════════════════════════

def main():
    st.set_page_config(
        page_title="Economic Bias Engine — EdgeLab",
        page_icon="📊",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    _inject_css()

    # ── Password gate ─────────────────────────────────────────────────────────
    if not st.session_state.get("m3_auth", False):
        _render_password_gate()
        _render_footer()
        return

    # ── Auto-refresh (5 min) ──────────────────────────────────────────────────
    now = time.time()
    last_ts = st.session_state.get("last_refresh_ts", 0.0)
    if (now - last_ts) >= 300:
        _clear_caches()
        st.session_state["last_refresh_ts"] = now
        for _ccy in CURRENCIES:
            st.session_state.pop(f"macro_scores_{_ccy}", None)
            st.session_state.pop(f"macro_rows_{_ccy}",   None)

    # ── Header ────────────────────────────────────────────────────────────────
    _render_header()
    st.markdown("<hr style='border-color:#252525;margin:8px 0 16px;'>", unsafe_allow_html=True)

    # ── Currency selection ────────────────────────────────────────────────────
    if "macro_currency" not in st.session_state:
        st.session_state["macro_currency"] = "USD"

    selected = _render_currency_pills(st.session_state["macro_currency"])
    if selected != st.session_state["macro_currency"]:
        st.session_state["macro_currency"] = selected
        st.rerun()

    ccy = st.session_state["macro_currency"]

    st.markdown("<hr style='border-color:#252525;margin:10px 0 20px;'>", unsafe_allow_html=True)

    # ── Fetch calendar (shared across dimensions) ─────────────────────────────
    with st.spinner("Loading data…"):
        ff_df = fetch_ff_calendar()

    # ── Compute scores ────────────────────────────────────────────────────────
    cache_key = f"macro_scores_{ccy}"
    rows_key  = f"macro_rows_{ccy}"

    # Recompute if either scores OR rows are missing (rows were discarded in older sessions)
    if cache_key not in st.session_state or rows_key not in st.session_state:
        with st.spinner(f"Scoring {ccy}…"):
            scores_dict, indicator_rows = _compute_currency_scores(ccy, ff_df)
            st.session_state[cache_key] = scores_dict
            st.session_state[rows_key]  = indicator_rows
            # Pre-compute all other currencies for Pair Intelligence — store BOTH scores AND rows
            for other_ccy in CURRENCIES:
                if other_ccy != ccy and f"macro_scores_{other_ccy}" not in st.session_state:
                    try:
                        od, o_rows = _compute_currency_scores(other_ccy, ff_df)
                        st.session_state[f"macro_scores_{other_ccy}"] = od
                        st.session_state[f"macro_rows_{other_ccy}"]   = o_rows
                    except Exception:
                        pass
    else:
        scores_dict    = st.session_state[cache_key]
        indicator_rows = st.session_state[rows_key]

    total = scores_dict["total"]
    level = scores_dict["level"]
    d1    = scores_dict["d1"]
    d2    = scores_dict["d2"]
    d3    = scores_dict["d3"]
    d4    = scores_dict["d4"]
    d5    = scores_dict["d5"]

    # ── Main layout ───────────────────────────────────────────────────────────
    left_col, right_col = st.columns([7, 5], gap="large")

    with left_col:
        _render_bias_bar(total, level)
        _render_dim_chips(d1, d2, d3, d4, d5)

        # Dimension labels
        _muted = C["muted"]
        _teal  = C["teal"]
        st.markdown(
            f"<div style='font-size:10px;color:{_teal};font-family:monospace;"
            f"letter-spacing:2px;text-transform:uppercase;margin-bottom:8px;'>"
            "▸ INDICATOR BREAKDOWN</div>",
            unsafe_allow_html=True,
        )
        _render_indicators_table(indicator_rows)

    with right_col:
        _render_calendar(ff_df, ccy)

        # All-currencies ranking
        st.markdown(
            f"<div style='font-size:10px;color:{_teal};font-family:monospace;"
            f"letter-spacing:2px;text-transform:uppercase;margin:20px 0 10px;'>"
            "▸ ALL CURRENCIES RANKING</div>",
            unsafe_allow_html=True,
        )
        _render_all_currencies_ranking()

    _render_data_health(indicator_rows)
    _render_footer()


def _render_data_health(indicator_rows: list):
    """Compact Data Health panel — shows live vs static status for every indicator.

    Displayed as a collapsed expander so it doesn't clutter the default view.
    Includes FRED key guidance when the key is invalid.
    """
    _card   = C["card"]
    _border = C["border"]
    _muted  = C["muted"]
    _text   = C["text"]
    _warn   = "#f0b429"
    _green  = C["green"]

    # "⚠ static" = static fallback value; other "⚠ …" (e.g. D4 "⚠ no consensus"/
    # "⚠ no data") = component unavailable, NOT a static fallback — counted separately.
    static_rows  = [r for r in indicator_rows if r[6].startswith("⚠ static")]
    unavail_rows = [r for r in indicator_rows
                    if r[6].startswith("⚠") and not r[6].startswith("⚠ static")]
    live_rows    = [r for r in indicator_rows if not r[6].startswith("⚠")]
    n_static  = len(static_rows)
    n_unavail = len(unavail_rows)
    n_live    = len(live_rows)

    _issues = n_static + n_unavail
    if _issues:
        _parts = []
        if n_static:
            _parts.append(f"{n_static} static")
        if n_unavail:
            _parts.append(f"{n_unavail} unavailable")
        expander_label = f"🟡 Data Health — {', '.join(_parts)}"
    else:
        expander_label = "🟢 Data Health — all indicators live"

    with st.expander(expander_label, expanded=(_issues > 0)):
        # ── FRED key status ──────────────────────────────────────────────────
        if not _FRED_KEY_VALID:
            st.markdown(
                f"""<div style='background:#1a1200;border:1px solid {_warn}44;border-radius:8px;
                padding:12px 16px;margin-bottom:14px;font-family:monospace;font-size:11px;'>
                <span style='color:{_warn};font-weight:700;'>⚠ FRED API KEY INVALID</span><br>
                <span style='color:{_muted};'>The FRED_API_KEY in <code>.streamlit/secrets.toml</code>
                is a placeholder ("<code>your_fred_api_key_here</code>").<br>
                Without a valid key, GDP, CPI, and some policy rates use static fallbacks instead of live data.<br><br>
                <b style='color:{_text};'>Action required:</b><br>
                1. Register for a free key at
                <span style='color:{_warn};'>fred.stlouisfed.org/docs/api/api_key.html</span><br>
                2. Replace <code>FRED_API_KEY = "your_fred_api_key_here"</code> in
                <code>.streamlit/secrets.toml</code> with your 32-character key.<br>
                3. Redeploy / restart the app.</span>
                </div>""",
                unsafe_allow_html=True,
            )

        # ── Summary counts ────────────────────────────────────────────────
        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown(
                f"<div style='font-family:monospace;font-size:11px;color:{_green};'>"
                f"✓ {n_live} live</div>", unsafe_allow_html=True)
        with c2:
            col = _warn if n_static else _green
            st.markdown(
                f"<div style='font-family:monospace;font-size:11px;color:{col};'>"
                f"{'⚠ ' if n_static else '✓ '}{n_static} static fallback</div>",
                unsafe_allow_html=True)
        with c3:
            col = _warn if n_unavail else _green
            st.markdown(
                f"<div style='font-family:monospace;font-size:11px;color:{col};'>"
                f"{'⚠ ' if n_unavail else '✓ '}{n_unavail} unavailable</div>",
                unsafe_allow_html=True)

        # ── Full source table ─────────────────────────────────────────────
        hdr = (f"background:{_card};color:{_muted};font-size:9px;font-family:monospace;"
               "letter-spacing:1.5px;padding:6px 10px;text-transform:uppercase;"
               "border-bottom:1px solid #252525;")
        cell = (f"color:{_text};font-size:10px;font-family:monospace;"
                "padding:5px 10px;border-bottom:1px solid #181818;")

        html = (
            f"<div style='background:{_card};border:1px solid {_border};border-radius:8px;"
            "overflow:hidden;margin-top:10px;'>"
            "<table style='width:100%;border-collapse:collapse;'>"
            "<thead><tr>"
            f"<th style='{hdr}'>Indicator</th>"
            f"<th style='{hdr}'>Source</th>"
            f"<th style='{hdr};text-align:center;'>Status</th>"
            "</tr></thead><tbody>"
        )
        for row in indicator_rows:
            indicator = row[0]; source = row[6]
            if source.startswith("⚠ static"):
                status_col  = _warn;  status_icon = "⚠ STATIC"
            elif source.startswith("⚠"):
                status_col  = _muted; status_icon = "○ UNAVAILABLE"
            else:
                status_col  = _green; status_icon = "✓ LIVE"
            src_display = source.replace("⚠ ", "")
            html += (
                "<tr>"
                f"<td style='{cell}'>{indicator}</td>"
                f"<td style='{cell};color:{_muted};font-size:9px;'>{src_display}</td>"
                f"<td style='{cell};text-align:center;color:{status_col};font-weight:700;"
                f"font-size:9px;'>{status_icon}</td>"
                "</tr>"
            )
        html += "</tbody></table></div>"
        st.markdown(html, unsafe_allow_html=True)

        # ── No-key live sources note ──────────────────────────────────────
        st.markdown(
            f"<div style='font-size:9px;color:{_muted};font-family:monospace;margin-top:8px;'>"
            "No-key live sources: NY Fed (USD rate) · BoE (GBP rate) · BoC V39079 (CAD rate) · "
            "ECB €STR→DFR (EUR rate) · ECB ICP (EUR CPI) · ForexFactory (PMI/Employment/Trade) · "
            "yfinance (equity/commodity proxies) · CFTC (COT). "
            "FRED key unlocks: USD CPI · GDP (all) · additional CB rates."
            "</div>",
            unsafe_allow_html=True,
        )


def _render_all_currencies_ranking():
    """Render a compact ranking of all 8 currencies by score."""
    _card   = C["card"]
    _border = C["border"]
    _muted  = C["muted"]
    _text   = C["text"]
    _teal   = C["teal"]

    items = []
    for ccy in CURRENCIES:
        data = st.session_state.get(f"macro_scores_{ccy}")
        if data:
            items.append((ccy, data.get("total", 0.0), data.get("level", "—")))
        else:
            items.append((ccy, 0.0, "—"))
    items.sort(key=lambda x: x[1], reverse=True)

    html = (
        f"<div style='background:{_card};border:1px solid {_border};border-radius:10px;"
        "overflow:hidden;'>"
        "<table style='width:100%;border-collapse:collapse;'>"
    )
    for rank, (ccy, score, level) in enumerate(items, 1):
        flag = CURRENCY_FLAG.get(ccy, "")
        col  = _score_color(score)
        sign = "+" if score > 0 else ""
        bg   = "rgba(26,155,106,0.04)" if score > 0.10 else ("rgba(240,82,98,0.04)" if score < -0.10 else "transparent")
        html += (
            f"<tr style='background:{bg};border-bottom:1px solid #1a1a1a;'>"
            f"<td style='padding:7px 10px;font-size:10px;color:{_muted};"
            f"font-family:monospace;width:24px;'>{rank}</td>"
            f"<td style='padding:7px 6px;font-size:12px;'>{flag}</td>"
            f"<td style='padding:7px 6px;font-size:11px;font-family:monospace;"
            f"color:{_text};font-weight:600;'>{ccy}</td>"
            f"<td style='padding:7px 10px;font-size:11px;font-family:monospace;"
            f"color:{_muted};'>{level}</td>"
            f"<td style='padding:7px 10px;font-size:12px;font-weight:700;"
            f"font-family:monospace;color:{col};text-align:right;'>{sign}{score:.2f}</td>"
            "</tr>"
        )
    html += "</table></div>"
    st.markdown(html, unsafe_allow_html=True)


def _render_footer():
    """Render footer."""
    _muted  = C["muted"]
    _border = C["border"]
    st.markdown(
        f"""
<div style='margin-top:48px;padding-top:16px;border-top:1px solid {_border};
            text-align:center;'>
  <span style='font-size:11px;color:{_muted};font-family:monospace;'>
    Built by @realedgetraders
  </span>
</div>
""",
        unsafe_allow_html=True,
    )


main()
