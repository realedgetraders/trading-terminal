"""
Trading Analytics Terminal — Module 3: Economic Bias Engine (v2)
5-dimension macro scoring engine with password gate and auto-refresh.
"""

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
_FB_DATE  = "2026-05-28"

_FB_RATES  = {"USD": 5.33, "EUR": 3.65, "GBP": 4.75, "JPY": 0.50,
              "AUD": 4.10, "NZD": 3.50, "CAD": 2.75, "CHF": 0.25}
_FB_CPI    = {"USD": 2.4,  "EUR": 2.2,  "GBP": 2.6,  "JPY": 2.2,
              "AUD": 3.2,  "NZD": 2.5,  "CAD": 1.7,  "CHF": 0.0}
_FB_CCPI   = {"USD": 2.8,  "EUR": 2.7,  "GBP": 3.4,  "JPY": 2.2,
              "AUD": 3.2,  "NZD": 2.7,  "CAD": 2.3,  "CHF": 1.0}
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

_NEUTRAL_RATE  = {"USD": 2.5, "EUR": 2.0, "GBP": 2.5, "JPY": 0.25,
                  "AUD": 3.0, "NZD": 3.0, "CAD": 2.5, "CHF": 0.5}
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
# ║  FRED FETCH  (ttl=3600)
# ╚══════════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_fred_series(series_id: str, limit: int = 36):
    """Fetch FRED series, return list of (date, value) sorted ascending."""
    if not FRED_API_KEY:
        return []
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

_FF_PATTERNS = {
    "USD": ["CPI m/m", "Core CPI m/m", "Non-Farm Employment Change", "Advance GDP q/q", "ISM Manufacturing PMI"],
    "EUR": ["CPI y/y", "Core CPI y/y", "Employment Change q/q", "Flash GDP q/q", "Manufacturing PMI"],
    "GBP": ["CPI y/y", "Core CPI y/y", "Employment Change", "GDP m/m", "Manufacturing PMI"],
    "JPY": ["National Core CPI y/y", "GDP q/q", "Employment Change", "Unemployment Rate", "Manufacturing PMI"],
    "AUD": ["CPI q/q", "Trimmed Mean CPI q/q", "Employment Change", "GDP q/q", "Manufacturing PMI"],
    "NZD": ["CPI q/q", "Employment Change q/q", "GDP q/q", "Manufacturing PMI"],
    "CAD": ["CPI m/m", "Employment Change", "GDP m/m", "Ivey PMI"],
    "CHF": ["CPI m/m", "Employment Change", "GDP q/q", "Manufacturing PMI"],
}


def _ff_beat_miss(ff_df: pd.DataFrame, ccy: str, pattern: str):
    """Find latest FF event matching pattern for currency. Returns (actual, forecast, surprise_score)."""
    try:
        sub = ff_df[
            (ff_df["currency"] == ccy) &
            (ff_df["title"].str.contains(pattern, case=False, na=False))
        ].sort_values("date")
        if sub.empty:
            return None, None, 0.0
        row = sub.iloc[-1]
        actual = row["actual"]
        forecast = row["forecast"]
        return actual, forecast, _score_surprise(actual, forecast)
    except Exception:
        return None, None, 0.0

# ╔══════════════════════════════════════════════════════════════════════════════
# ║  DIMENSION CALCULATORS
# ╚══════════════════════════════════════════════════════════════════════════════

def _d1_monetary(ccy: str, ff_df: pd.DataFrame):
    """D1: Monetary Policy — rate level vs neutral, delta, next move expectation."""
    N = _NEUTRAL_RATE[ccy]

    # Rate level
    rate = None
    prev_rate = None
    if ccy == "USD":
        rate, prev_rate = _fred_latest_with_prev("FEDFUNDS", 10)
    elif ccy == "GBP":
        rate, prev_rate = _fred_latest_with_prev("BOERUKM156N", 10)
    elif ccy == "EUR":
        rate = fetch_ecb_series("FM", "M.U2.EUR.RT0.DFR.R.1.Z5.I.A")
    if rate is None:
        rate = _FB_RATES.get(ccy)

    # Rate delta (last change in bps) — derive from the values we already have
    rate_delta = 0.0
    if ccy == "USD":
        if rate is not None and prev_rate is not None:
            rate_delta = (rate - prev_rate) * 100.0
    elif ccy == "GBP":
        if rate is not None and prev_rate is not None:
            rate_delta = (rate - prev_rate) * 100.0
    else:
        # Other CCYs: try to derive from FRED if available
        _rate_series_map = {
            "JPY": None,   # BOJ rate not reliably on FRED
            "AUD": None,
            "NZD": None,
            "CAD": None,
            "CHF": None,
        }
        _rsid = _rate_series_map.get(ccy)
        if _rsid:
            _rv, _rp = _fred_latest_with_prev(_rsid, 10)
            if _rv is not None and _rp is not None:
                rate_delta = (_rv - _rp) * 100.0

    # Expected next move: use FF calendar for rate decision events
    next_move_diff = 0.0
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
    except Exception:
        pass

    s_level = _score(rate, N - 1.0, N - 0.5, N + 0.5, N + 1.0)
    s_delta = _score(rate_delta, -50.0, -25.0, 25.0, 50.0)
    s_next  = _score(next_move_diff, -0.30, -0.10, 0.10, 0.30)
    d1 = _mean(s_level, s_delta, s_next)
    rows = [
        ("Policy Rate", rate, prev_rate, None, None, s_level, "FRED/ECB"),
        ("Rate Delta (bps)", rate_delta, None, None, None, s_delta, "FRED/ECB"),
        ("Next Move Forecast", next_move_diff, None, None, None, s_next, "ForexFactory"),
    ]
    return d1, rows


def _d2_inflation_growth(ccy: str, ff_df: pd.DataFrame):
    """D2: Inflation & Growth — CPI, core CPI, GDP, PMI."""
    cpi = None
    core_cpi = None
    gdp = None
    pmi = _FB_PMI.get(ccy)

    if ccy == "USD":
        cpi = _fred_yoy("CPIAUCSL")
        core_cpi = _fred_yoy("CPILFESL")
        gdp_data = fetch_fred_series("A191RL1Q225SBEA", 5)
        gdp = gdp_data[-1][1] if gdp_data else None
    elif ccy == "EUR":
        cpi = fetch_ecb_series("ICP", "M.U2.N.000000.4.ANR")
        core_cpi = fetch_ecb_series("ICP", "M.U2.N.XEF000.4.ANR")
        gdp_data = fetch_fred_series("NAEXKP01EZQ652S", 5)
        gdp = gdp_data[-1][1] if gdp_data else None
    elif ccy == "GBP":
        cpi = _fred_latest("CPALTT01GBM659N", 5)
        gdp_data = fetch_fred_series("NAEXKP01GBQ652S", 5)
        gdp = gdp_data[-1][1] if gdp_data else None
    elif ccy == "JPY":
        cpi = _fred_latest("CPALTT01JPM659N", 5)
        gdp_data = fetch_fred_series("NAEXKP01JPQ652S", 5)
        gdp = gdp_data[-1][1] if gdp_data else None
    elif ccy == "AUD":
        cpi = _fred_latest("CPALTT01AUM659N", 5)
        gdp_data = fetch_fred_series("NAEXKP01AUQ652S", 5)
        gdp = gdp_data[-1][1] if gdp_data else None
    elif ccy == "NZD":
        cpi = _fred_latest("CPALTT01NZM659N", 5)
        gdp_data = fetch_fred_series("NAEXKP01NZQ652S", 5)
        gdp = gdp_data[-1][1] if gdp_data else None
    elif ccy == "CAD":
        cpi = _fred_latest("CPALTT01CAM659N", 5)
        gdp_data = fetch_fred_series("NAEXKP01CAQ652S", 5)
        gdp = gdp_data[-1][1] if gdp_data else None
    elif ccy == "CHF":
        cpi = _fred_latest("CPALTT01CHM659N", 5)
        gdp_data = fetch_fred_series("NAEXKP01CHQ652S", 5)
        gdp = gdp_data[-1][1] if gdp_data else None

    # Fallback
    if cpi is None:
        cpi = _FB_CPI.get(ccy)
    if core_cpi is None:
        core_cpi = _FB_CCPI.get(ccy)
    if gdp is None:
        gdp = _FB_GDP.get(ccy)

    # PMI from FF calendar
    try:
        if not ff_df.empty:
            pat_map = {"USD": "ISM Manufacturing", "EUR": "Manufacturing PMI",
                       "GBP": "Manufacturing PMI", "JPY": "Manufacturing PMI",
                       "AUD": "Manufacturing PMI", "NZD": "Manufacturing PMI",
                       "CAD": "Ivey PMI", "CHF": "Manufacturing PMI"}
            pat = pat_map.get(ccy, "Manufacturing PMI")
            sub = ff_df[(ff_df["currency"] == ccy) & ff_df["title"].str.contains(pat, case=False, na=False)]
            if not sub.empty:
                row = sub.sort_values("date").iloc[-1]
                if row["actual"] is not None:
                    pmi = float(row["actual"])
    except Exception:
        pass

    s_cpi  = _score(cpi, 1.0, 1.5, 2.5, 3.5)
    s_ccpi = _score(core_cpi, 1.0, 1.5, 2.5, 3.0)
    s_gdp  = _score(gdp, 0.0, 0.2, 0.8, 1.2)
    s_pmi  = _score(pmi, 47.0, 49.0, 51.0, 53.0)
    d2 = _mean(s_cpi, s_ccpi, s_gdp, s_pmi)
    rows = [
        ("CPI YoY %", cpi, None, None, None, s_cpi, "FRED/ECB"),
        ("Core CPI YoY %", core_cpi, None, None, None, s_ccpi, "FRED/ECB"),
        ("GDP QoQ %", gdp, None, None, None, s_gdp, "FRED"),
        ("Manufacturing PMI", pmi, None, None, None, s_pmi, "ForexFactory"),
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
    fred_key = fred_unemp_map.get(ccy)
    if fred_key:
        unemp, prev_unemp = _fred_latest_with_prev(fred_key, 10)
    if unemp is None:
        unemp = _FB_UNEMP.get(ccy)

    # Employment change
    try:
        if ccy == "USD":
            employ_change = _fred_mom_change("PAYEMS")
            if employ_change is not None:
                employ_change = employ_change  # already in thousands
        else:
            if not ff_df.empty:
                sub = ff_df[
                    (ff_df["currency"] == ccy) &
                    ff_df["title"].str.contains("Employment Change", case=False, na=False)
                ].sort_values("date")
                if not sub.empty:
                    row = sub.iloc[-1]
                    if row["actual"] is not None:
                        employ_change = float(row["actual"])
    except Exception:
        employ_change = None

    # Trade balance from FF
    try:
        if not ff_df.empty:
            sub = ff_df[
                (ff_df["currency"] == ccy) &
                ff_df["title"].str.contains("Trade Balance", case=False, na=False)
            ].sort_values("date")
            if not sub.empty:
                row = sub.iloc[-1]
                if row["actual"] is not None:
                    trade = float(row["actual"])
    except Exception:
        pass

    # Retail sales from FF
    try:
        if not ff_df.empty:
            sub = ff_df[
                (ff_df["currency"] == ccy) &
                ff_df["title"].str.contains("Retail Sales", case=False, na=False)
            ].sort_values("date")
            if not sub.empty:
                row = sub.iloc[-1]
                if row["actual"] is not None:
                    retail = float(row["actual"])
    except Exception:
        pass

    # USD retail from FRED
    if ccy == "USD" and retail == _FB_RETAIL.get(ccy):
        retail_fred = _fred_mom_pct("RSXFS")
        if retail_fred is not None:
            retail = retail_fred

    s_unemp  = _score(unemp, N_u - 1.5, N_u - 0.5, N_u + 0.5, N_u + 1.5, invert=True)
    s_employ = _score(employ_change, -50.0, -10.0, 10.0, 50.0)
    s_trade  = _score(trade, t0, t1, t2, t3)
    s_retail = _score(retail, -0.3, 0.0, 0.5, 1.0)
    d3 = _mean(s_unemp, s_employ, s_trade, s_retail)
    rows = [
        ("Unemployment %", unemp, prev_unemp, None, None, s_unemp, "FRED/ECB"),
        ("Employment Change", employ_change, None, None, None, s_employ, "FRED/FF"),
        ("Trade Balance", trade, None, None, None, s_trade, "ForexFactory"),
        ("Retail Sales MoM %", retail, None, None, None, s_retail, "FRED/FF"),
    ]
    return d3, rows


def _d4_surprises(ccy: str, ff_df: pd.DataFrame):
    """D4: Economic Surprises — beat/miss for CPI, GDP, Employment."""
    patterns = _FF_PATTERNS.get(ccy, [])
    cpi_pat    = patterns[0] if len(patterns) > 0 else "CPI"
    gdp_pat    = patterns[3] if len(patterns) > 3 else "GDP"
    employ_pat = patterns[2] if len(patterns) > 2 else "Employment"

    cpi_act, cpi_fore, s_cpi = _ff_beat_miss(ff_df, ccy, cpi_pat)
    gdp_act, gdp_fore, s_gdp = _ff_beat_miss(ff_df, ccy, gdp_pat)
    emp_act, emp_fore, s_emp = _ff_beat_miss(ff_df, ccy, employ_pat)

    # Only average non-None scores — None means "no data", not "neutral (0.0)"
    _subs = [s for s in (s_cpi, s_gdp, s_emp) if s is not None]
    momentum = (sum(_subs) / len(_subs)) if _subs else None
    _all  = [s for s in (s_cpi, s_gdp, s_emp, momentum) if s is not None]
    d4 = (sum(_all) / len(_all)) if _all else 0.0

    # _beat_miss_label(None) already returns "—"; score=None renders as "—" in table
    rows = [
        (f"CPI Surprise ({cpi_pat[:20]})", cpi_act, None, cpi_fore, _beat_miss_label(s_cpi), s_cpi, "ForexFactory"),
        (f"GDP Surprise ({gdp_pat[:20]})", gdp_act, None, gdp_fore, _beat_miss_label(s_gdp), s_gdp, "ForexFactory"),
        ("Employment Surprise",            emp_act, None, emp_fore, _beat_miss_label(s_emp), s_emp, "ForexFactory"),
        ("Surprise Momentum",              momentum, None, None, None, momentum, "Composite"),
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
    """D5: Currency-specific proxy indicators."""
    cot = _cot_index(ccy)

    rows = []
    scores = []

    if ccy == "USD":
        dgs10 = _fred_latest("DGS10", 30)   # daily series — 30 obs covers ~6 weeks incl. holidays
        if dgs10 is None:
            _tnx = fetch_yf_price("^TNX")   # yfinance ^TNX = 10Y Treasury yield (same % units)
            if _tnx is not None:
                dgs10 = _tnx
        dgs2 = _fred_latest("DGS2", 30)
        # No reliable yfinance 2Y fallback; spread is None if DGS2 unavailable — that's OK
        dxy  = fetch_yf_price("DX-Y.NYB")
        if dxy is None:
            dxy = fetch_yf_price("DX=F")    # alternative DXY futures ticker
        rate = _fred_latest("FEDFUNDS", 10) or _FB_RATES["USD"]
        N    = _NEUTRAL_RATE["USD"]
        conf = _fred_latest("UMCSENT", 12)
        spread = None
        if dgs10 is not None and dgs2 is not None:
            spread = dgs10 - dgs2

        s1 = _score(dgs10, 3.5, 4.0, 5.0, 5.5)
        s2 = _score(dxy, 95.0, 98.0, 104.0, 107.0, invert=True)
        s3 = _score(spread, -1.0, -0.2, 0.5, 1.0)
        s4 = _score(rate - N, -1.0, -0.5, 0.5, 1.0)
        s5 = _score(conf, 60.0, 70.0, 90.0, 100.0)
        scores = [s1, s2, s3, s4, s5]
        rows = [
            ("10Y Yield (DGS10)", dgs10, None, None, None, s1, "FRED"),
            ("DXY (inverted)", dxy, None, None, None, s2, "yfinance"),
            ("2s10s Spread", spread, None, None, None, s3, "FRED"),
            ("Rate vs Neutral", rate - N if rate is not None else None, None, None, None, s4, "FRED"),
            ("Consumer Confidence", conf, None, None, None, s5, "FRED"),
        ]

    elif ccy == "EUR":
        eurchf = fetch_yf_price("EURCHF=X")
        cpi  = fetch_ecb_series("ICP", "M.U2.N.000000.4.ANR") or _FB_CPI["EUR"]
        rate = fetch_ecb_series("FM", "M.U2.EUR.RT0.DFR.R.1.Z5.I.A") or _FB_RATES["EUR"]
        pmi  = _FB_PMI["EUR"]
        try:
            if not ff_df.empty:
                sub = ff_df[(ff_df["currency"] == "EUR") & ff_df["title"].str.contains("Manufacturing PMI", case=False, na=False)]
                if not sub.empty and sub.sort_values("date").iloc[-1]["actual"] is not None:
                    pmi = float(sub.sort_values("date").iloc[-1]["actual"])
        except Exception:
            pass
        real_rate = rate - cpi if rate and cpi else None
        s1 = _score(cot, 30.0, 40.0, 60.0, 70.0)
        s2 = _score(pmi, 47.0, 49.0, 51.0, 53.0)
        s3 = _score(eurchf, 0.93, 0.95, 0.97, 0.99)
        s4 = _score(real_rate, -1.0, -0.5, 0.5, 1.5)
        s5 = _score(rate, 3.5, 4.0, 5.0, 5.5, invert=True)
        scores = [s1, s2, s3, s4, s5]
        rows = [
            ("EUR COT Index", cot, None, None, None, s1, "CFTC"),
            ("Mfg PMI", pmi, None, None, None, s2, "ForexFactory"),
            ("EURCHF Level", eurchf, None, None, None, s3, "yfinance"),
            ("Real Rate (rate-CPI)", real_rate, None, None, None, s4, "FRED/ECB"),
            ("Deposit Rate (inverted)", rate, None, None, None, s5, "ECB"),
        ]

    elif ccy == "GBP":
        rate  = _fred_latest("BOERUKM156N", 5) or _FB_RATES["GBP"]
        cpi   = _fred_latest("CPALTT01GBM659N", 5) or _FB_CPI["GBP"]
        real_rate = rate - cpi
        pmi = _FB_PMI["GBP"]
        try:
            if not ff_df.empty:
                sub = ff_df[(ff_df["currency"] == "GBP") & ff_df["title"].str.contains("Services PMI", case=False, na=False)]
                if not sub.empty and sub.sort_values("date").iloc[-1]["actual"] is not None:
                    pmi = float(sub.sort_values("date").iloc[-1]["actual"])
        except Exception:
            pass
        s1 = _score(pmi, 47.0, 49.0, 51.0, 53.0)
        s2 = _score(cot, 30.0, 40.0, 60.0, 70.0)
        s3 = _score(real_rate, -1.0, -0.5, 0.5, 1.5)
        s4 = _score(rate - _NEUTRAL_RATE["GBP"], -1.0, -0.5, 0.5, 1.0)
        s5 = _score(cpi, 1.0, 1.5, 2.5, 3.5)
        scores = [s1, s2, s3, s4, s5]
        rows = [
            ("UK Services PMI", pmi, None, None, None, s1, "ForexFactory"),
            ("GBP COT Index", cot, None, None, None, s2, "CFTC"),
            ("Real Rate (rate-CPI)", real_rate, None, None, None, s3, "FRED"),
            ("Rate vs Neutral", rate - _NEUTRAL_RATE["GBP"], None, None, None, s4, "FRED"),
            ("CPI YoY %", cpi, None, None, None, s5, "FRED"),
        ]

    elif ccy == "JPY":
        jpy_rate = _FB_RATES["JPY"]
        usd_rate = _fred_latest("FEDFUNDS", 5) or _FB_RATES["USD"]
        jpy_cpi  = _fred_latest("CPALTT01JPM659N", 5) or _FB_CPI["JPY"]
        carry    = usd_rate - jpy_rate
        vix      = fetch_yf_price("^VIX")
        nikkei   = fetch_yf_price("^N225")
        sp500    = fetch_yf_price("^GSPC")
        nk_sp    = (nikkei / sp500) if nikkei and sp500 and sp500 > 0 else None
        real_rate = jpy_rate - jpy_cpi

        s1 = _score(carry, 3.0, 4.0, 5.5, 6.5, invert=True)
        s2 = _score(vix, 30.0, 22.0, 15.0, 12.0, invert=True)
        s3 = _score(cot, 30.0, 40.0, 60.0, 70.0)
        s4 = _score(nk_sp, 0.20, 0.22, 0.27, 0.30, invert=True)
        s5 = _score(real_rate, -3.0, -1.5, -0.5, 0.5)
        scores = [s1, s2, s3, s4, s5]
        rows = [
            ("USD-JPY Carry (inverted)", carry, None, None, None, s1, "FRED"),
            ("VIX (inverted)", vix, None, None, None, s2, "yfinance"),
            ("JPY COT Index", cot, None, None, None, s3, "CFTC"),
            ("Nikkei/S&P ratio (inv)", nk_sp, None, None, None, s4, "yfinance"),
            ("Real Rate (JPY rate-CPI)", real_rate, None, None, None, s5, "FRED"),
        ]

    elif ccy == "AUD":
        iron  = fetch_yf_price("BHP")   # BHP Group — major iron ore proxy (TIO=F unavailable)
        crude = fetch_yf_price("CL=F")
        rate  = _FB_RATES["AUD"]
        cpi   = _fred_latest("CPALTT01AUM659N", 5) or _FB_CPI["AUD"]
        real_rate = rate - cpi
        pmi   = _FB_PMI["AUD"]
        try:
            if not ff_df.empty:
                sub = ff_df[(ff_df["currency"] == "AUD") & ff_df["title"].str.contains("Manufacturing PMI", case=False, na=False)]
                if not sub.empty and sub.sort_values("date").iloc[-1]["actual"] is not None:
                    pmi = float(sub.sort_values("date").iloc[-1]["actual"])
        except Exception:
            pass
        caixin = _FB_PMI["AUD"]
        try:
            if not ff_df.empty:
                sub = ff_df[(ff_df["currency"] == "CNY") & ff_df["title"].str.contains("Caixin", case=False, na=False)]
                if not sub.empty and sub.sort_values("date").iloc[-1]["actual"] is not None:
                    caixin = float(sub.sort_values("date").iloc[-1]["actual"])
        except Exception:
            pass

        s1 = _score(iron, 35.0, 42.0, 52.0, 62.0)   # BHP NYSE price (~$40–60 range)
        s2 = _score(crude, 55.0, 65.0, 80.0, 95.0)
        s3 = _score(caixin, 47.0, 49.0, 51.0, 53.0)
        s4 = _score(cot, 30.0, 40.0, 60.0, 70.0)
        s5 = _score(real_rate, -1.0, -0.5, 0.5, 1.5)
        scores = [s1, s2, s3, s4, s5]
        rows = [
            ("Iron Ore (BHP proxy)", iron, None, None, None, s1, "yfinance"),
            ("WTI Crude", crude, None, None, None, s2, "yfinance"),
            ("Caixin PMI (China)", caixin, None, None, None, s3, "ForexFactory"),
            ("AUD COT Index", cot, None, None, None, s4, "CFTC"),
            ("Real Rate (RBA-CPI)", real_rate, None, None, None, s5, "FRED"),
        ]

    elif ccy == "NZD":
        bhp   = fetch_yf_price("BHP")   # BHP — commodity / iron ore proxy
        gold  = fetch_yf_price("GC=F")
        rate  = _FB_RATES["NZD"]
        cpi   = _fred_latest("CPALTT01NZM659N", 5) or _FB_CPI["NZD"]
        real_rate = rate - cpi
        caixin = _FB_PMI["AUD"]
        try:
            if not ff_df.empty:
                sub = ff_df[(ff_df["currency"] == "CNY") & ff_df["title"].str.contains("Caixin", case=False, na=False)]
                if not sub.empty and sub.sort_values("date").iloc[-1]["actual"] is not None:
                    caixin = float(sub.sort_values("date").iloc[-1]["actual"])
        except Exception:
            pass

        s1 = _score(bhp, 35.0, 42.0, 52.0, 62.0)    # BHP NYSE price as commodity proxy
        s2 = _score(caixin, 47.0, 49.0, 51.0, 53.0)
        s3 = _score(cot, 30.0, 40.0, 60.0, 70.0)
        s4 = _score(real_rate, -1.0, -0.5, 0.5, 1.5)
        s5 = _score(gold, 1800.0, 1950.0, 2300.0, 2500.0)
        scores = [s1, s2, s3, s4, s5]
        rows = [
            ("Commodity (BHP proxy)", bhp, None, None, None, s1, "yfinance"),
            ("Caixin PMI (China)", caixin, None, None, None, s2, "ForexFactory"),
            ("NZD COT Index", cot, None, None, None, s3, "CFTC"),
            ("Real Rate (RBNZ-CPI)", real_rate, None, None, None, s4, "FRED"),
            ("Gold (risk proxy)", gold, None, None, None, s5, "yfinance"),
        ]

    elif ccy == "CAD":
        crude = fetch_yf_price("CL=F")
        rate  = _FB_RATES["CAD"]
        cpi   = _fred_latest("CPALTT01CAM659N", 5) or _FB_CPI["CAD"]
        real_rate = rate - cpi
        usdcad = None
        try:
            usdcad = fetch_yf_price("USDCAD=X")
        except Exception:
            pass

        s1 = _score(crude, 55.0, 65.0, 80.0, 95.0)
        s2 = _score(cot, 30.0, 40.0, 60.0, 70.0)
        s3 = _score(real_rate, -1.0, -0.5, 0.5, 1.5)
        s4 = _score(usdcad, 1.28, 1.32, 1.38, 1.42, invert=True)
        s5 = _score(crude, 55.0, 65.0, 80.0, 95.0)  # oil again as proxy for oil/gas ratio
        scores = [s1, s2, s3, s4, s5]
        rows = [
            ("WTI Crude", crude, None, None, None, s1, "yfinance"),
            ("CAD COT Index", cot, None, None, None, s2, "CFTC"),
            ("Real Rate (BOC-CPI)", real_rate, None, None, None, s3, "FRED"),
            ("USD/CAD Level (inverted)", usdcad, None, None, None, s4, "yfinance"),
            ("Oil Price (2nd proxy)", crude, None, None, None, s5, "yfinance"),
        ]

    elif ccy == "CHF":
        gold  = fetch_yf_price("GC=F")
        eurchf = fetch_yf_price("EURCHF=X")
        vix   = fetch_yf_price("^VIX")
        rate  = _FB_RATES["CHF"]
        cpi   = _fred_latest("CPALTT01CHM659N", 5) or _FB_CPI["CHF"]
        real_rate = rate - cpi

        s1 = _score(gold, 1800.0, 1950.0, 2300.0, 2500.0)
        s2 = _score(eurchf, 0.92, 0.94, 0.96, 0.98)
        s3 = _score(vix, 30.0, 22.0, 15.0, 12.0, invert=True)
        s4 = _score(cot, 30.0, 40.0, 60.0, 70.0)
        s5 = _score(real_rate, -2.0, -1.0, 0.0, 1.0)
        scores = [s1, s2, s3, s4, s5]
        rows = [
            ("Gold Price", gold, None, None, None, s1, "yfinance"),
            ("EUR/CHF Level", eurchf, None, None, None, s2, "yfinance"),
            ("VIX (inverted)", vix, None, None, None, s3, "yfinance"),
            ("CHF COT Index", cot, None, None, None, s4, "CFTC"),
            ("Real Rate (SNB-CPI)", real_rate, None, None, None, s5, "FRED"),
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

    composite = (d1 + d2 + d3 + d4 + d5) / 5.0
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
    fetch_fred_series,
    fetch_ecb_series,
    fetch_yf_price,
    fetch_ff_calendar,
    fetch_cot_data,
]

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
        f"<th style='{hdr_style}'>INDICATOR</th>"
        f"<th style='{hdr_style};text-align:right;'>VALUE</th>"
        f"<th style='{hdr_style};text-align:right;'>PREV</th>"
        f"<th style='{hdr_style};text-align:right;'>FCST</th>"
        f"<th style='{hdr_style};text-align:right;'>BEAT/MISS</th>"
        f"<th style='{hdr_style};text-align:right;'>SCORE</th>"
        f"<th style='{hdr_style};text-align:right;'>SOURCE</th>"
        "</tr></thead><tbody>"
    )
    for row in rows:
        indicator, value, prev, forecast, beat_miss, score, source = row
        score_col = _score_color(score)
        score_val = f"{score:+.2f}" if isinstance(score, float) else "—"
        bm_str = beat_miss if beat_miss else "—"
        html += (
            "<tr>"
            f"<td style='{cell_style}'>{indicator}</td>"
            f"<td style='{cell_style};text-align:right;'>{_fmt_val(value)}</td>"
            f"<td style='{cell_style};text-align:right;color:{_muted};'>{_fmt_val(prev)}</td>"
            f"<td style='{cell_style};text-align:right;color:{_muted};'>{_fmt_val(forecast)}</td>"
            f"<td style='{cell_style};text-align:right;color:{_muted};'>{bm_str}</td>"
            f"<td style='{cell_style};text-align:right;font-weight:700;color:{score_col};'>{score_val}</td>"
            f"<td style='{cell_style};text-align:right;color:{_muted};font-size:9px;'>{source}</td>"
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

    st.markdown("<div style='height:7vh;'></div>", unsafe_allow_html=True)
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
            for fn in _CACHE_FUNS:
                fn.clear()
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
        for fn in _CACHE_FUNS:
            fn.clear()
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

    # ── 🔧 DEBUG EXPANDER (temporary — remove once fetches confirmed working) ──
    with st.expander("🔧 Debug: Fetch Status (USD)", expanded=False):
        import traceback as _tb

        # FRED API key
        st.markdown("**FRED API Key**")
        st.write({"key_present": bool(FRED_API_KEY), "key_length": len(FRED_API_KEY)})

        # Policy rate + prev
        st.markdown("**FEDFUNDS — Policy Rate (current, prev)**")
        try:
            _r, _rp = _fred_latest_with_prev("FEDFUNDS", 10)
            _raw_ff = fetch_fred_series("FEDFUNDS", 10)
            st.write({"current": _r, "previous": _rp, "raw_tail": _raw_ff[-5:] if _raw_ff else []})
        except Exception as _e:
            st.error(f"FEDFUNDS error: {_e}")

        # CPI YoY
        st.markdown("**CPIAUCSL — CPI YoY %**")
        try:
            _cpi_raw = fetch_fred_series("CPIAUCSL", 15)
            st.write({"yoy": _fred_yoy("CPIAUCSL"), "raw_tail": _cpi_raw[-4:] if _cpi_raw else []})
        except Exception as _e:
            st.error(f"CPIAUCSL error: {_e}")

        # GDP
        st.markdown("**A191RL1Q225SBEA — GDP QoQ %**")
        try:
            _gdp_raw = fetch_fred_series("A191RL1Q225SBEA", 5)
            st.write({"series": _gdp_raw})
        except Exception as _e:
            st.error(f"GDP error: {_e}")

        # Unemployment + prev
        st.markdown("**UNRATE — Unemployment (current, prev)**")
        try:
            _u, _up = _fred_latest_with_prev("UNRATE", 10)
            _uraw = fetch_fred_series("UNRATE", 10)
            st.write({"current": _u, "previous": _up, "raw_tail": _uraw[-5:] if _uraw else []})
        except Exception as _e:
            st.error(f"UNRATE error: {_e}")

        # PAYEMS employment change
        st.markdown("**PAYEMS — Employment Change MoM**")
        try:
            _pay_raw = fetch_fred_series("PAYEMS", 10)
            st.write({"mom_change": _fred_mom_change("PAYEMS"), "raw_tail": _pay_raw[-4:] if _pay_raw else []})
        except Exception as _e:
            st.error(f"PAYEMS error: {_e}")

        # DGS10
        st.markdown("**DGS10 — 10Y Treasury Yield (limit=30)**")
        try:
            _d10 = fetch_fred_series("DGS10", 30)
            st.write({"count": len(_d10), "latest": _d10[-1] if _d10 else None, "tail": _d10[-5:] if _d10 else []})
        except Exception as _e:
            st.error(f"DGS10 error: {_e}")

        # DGS2
        st.markdown("**DGS2 — 2Y Treasury Yield (limit=30)**")
        try:
            _d2 = fetch_fred_series("DGS2", 30)
            st.write({"count": len(_d2), "latest": _d2[-1] if _d2 else None})
        except Exception as _e:
            st.error(f"DGS2 error: {_e}")

        # UMCSENT
        st.markdown("**UMCSENT — Consumer Sentiment (limit=12)**")
        try:
            _ums = fetch_fred_series("UMCSENT", 12)
            st.write({"count": len(_ums), "all": _ums})
        except Exception as _e:
            st.error(f"UMCSENT error: {_e}")

        # yfinance DXY
        st.markdown("**yfinance DX-Y.NYB — DXY**")
        try:
            _dxy_dbg = fetch_yf_price("DX-Y.NYB")
            st.write({"value": _dxy_dbg})
        except Exception as _e:
            st.error(f"DXY error: {_e}")

        # yfinance BHP
        st.markdown("**yfinance BHP — Iron Ore proxy**")
        try:
            _bhp_dbg = fetch_yf_price("BHP")
            st.write({"value": _bhp_dbg})
        except Exception as _e:
            st.error(f"BHP error: {_e}")

        # FF Calendar — raw first 10 events (Step 3: verify field names & currency format)
        st.markdown("**ForexFactory Calendar — raw first 10 events**")
        if not ff_df.empty:
            st.write(ff_df.head(10).to_dict(orient="records"))
            _currencies_found = sorted(ff_df["currency"].unique().tolist())
            _usd_count = int((ff_df["currency"] == "USD").sum())
            st.write({"total_events": len(ff_df), "usd_events": _usd_count,
                      "all_currencies": _currencies_found})
        else:
            st.warning("⚠️ FF calendar returned EMPTY DataFrame — all endpoints failed")
            # Attempt one raw fetch to expose the error
            try:
                import requests as _req
                _test = _req.get(
                    "https://nfs.faireconomy.media/ff_calendar_thisweek.json",
                    headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.forexfactory.com/"},
                    timeout=10,
                )
                st.write({"status": _test.status_code, "first_event": _test.json()[0] if _test.ok else _test.text[:200]})
            except Exception as _e2:
                st.error(f"Raw FF fetch error: {_e2}")

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

    _render_footer()


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
