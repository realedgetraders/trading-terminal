#!/usr/bin/env python3
"""Fetch daily OHLC for the Seasonality module's 56 instruments into Supabase.

Source: yfinance (unadjusted, daily). The instrument universe, ticker mapping
and forex handling are reused 1:1 from pages/1_Seasonality.py, with one
deliberate correction (see "Cross fix" below).

Coverage (56 symbols, ~25 years where available):
  - 7  Forex majors   (direct yfinance OHLC, =X, -1 day shift)
  - 21 Forex crosses  (synthetic, built from USD legs; Close only)
  -  7 Commodities,  7 Agriculture,  7 Indices,  5 Bonds,  2 Crypto
                      (direct yfinance OHLC, no shift)

Forex handling (1:1 with the module):
  - auto_adjust=False (unadjusted prices)
  - =X forex tickers and synthetic crosses get a -1 day index shift (UTC fix)
  - rows with Close <= 0 are dropped (e.g. CL=F's negative 2020-04-20 print)

Cross fix (corrected, NOT 1:1 with the module's bug):
  The module builds crosses as numerator/denominator where both legs must be
  expressed as XXX/USD. For CAD/CHF/JPY the Yahoo quote (CAD=X, CHF=X, JPY=X) is
  the USD-base rate (USD/XXX), so the original division yields a wrong series for
  every JPY/CHF/CAD cross. Here those legs are inverted (1/price) to true XXX/USD
  before dividing, so every cross is the real pair series. The synthesis method
  (USD majors → 20y+ history) is otherwise unchanged.

Rows go to the ``seasonality_prices`` table (symbol, category, date, open, high,
low, close) via upsert on (symbol, date) — re-runs never duplicate. A symbol
that fails to download is reported and skipped; one bad symbol never aborts the
run.

Required environment variables (never hardcode credentials):
  SUPABASE_URL         Supabase project URL
  SUPABASE_SECRET_KEY  Supabase secret (service) key

Run:
  python scripts/fetch_seasonality_prices.py
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta

import pandas as pd
import yfinance as yf
from supabase import create_client

HISTORY_YEARS = 25
UPSERT_CHUNK = 1000          # rows per Supabase upsert call
SHORT_HISTORY_YEARS = 20.0   # below this span a symbol is flagged in the report

# ─── Instrument universe (verbatim from pages/1_Seasonality.py) ──────────────

# Forex majors — direct yfinance OHLC.
FOREX_MAJORS = {
    "EUR/USD": "EURUSD=X",
    "GBP/USD": "GBPUSD=X",
    "USD/JPY": "USDJPY=X",
    "USD/CHF": "USDCHF=X",
    "AUD/USD": "AUDUSD=X",
    "NZD/USD": "NZDUSD=X",
    "USD/CAD": "USDCAD=X",
}

# Synthetic crosses: cross_key -> (numerator_leg, denominator_leg), both XXX/USD.
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

# yfinance ticker for each XXX/USD leg.
_USD_YF = {
    "GBPUSD": "GBPUSD=X", "EURUSD": "EURUSD=X",
    "AUDUSD": "AUDUSD=X", "NZDUSD": "NZDUSD=X",
    "CADUSD": "CAD=X",    "CHFUSD": "CHF=X",
    "JPYUSD": "JPY=X",
}
# Legs whose Yahoo quote is USD-base (USD/XXX) and must be inverted to XXX/USD.
# This is the corrected orientation — the module omits it (the cross bug).
_INVERT_LEG = {"CADUSD", "CHFUSD", "JPYUSD"}

# Non-forex categories — display name -> yfinance ticker.
SCREENER_CATEGORIES: dict[str, dict[str, str]] = {
    "Commodities": {
        "Gold":          "GC=F",
        "Silver":        "SI=F",
        "Copper":        "HG=F",
        "Platinum":      "PL=F",
        "Crude Oil WTI": "CL=F",
        "Brent Crude":   "BZ=F",
        "Natural Gas":   "NG=F",
    },
    "Agriculture": {
        "Corn":        "ZC=F",
        "Wheat":       "ZW=F",
        "Soybeans":    "ZS=F",
        "Coffee":      "KC=F",
        "Sugar":       "SB=F",
        "Cotton":      "CT=F",
        "Live Cattle": "LE=F",
    },
    "Indices": {
        "S&P 500":      "^GSPC",
        "Nasdaq 100":   "^NDX",
        "Dow Jones":    "^DJI",
        "Russell 2000": "^RUT",
        "DAX":          "^GDAXI",
        "FTSE 100":     "^FTSE",
        "Nikkei 225":   "^N225",
    },
    "Bonds": {
        "10Y T-Note":   "ZN=F",
        "30Y T-Bond":   "ZB=F",
        "5Y T-Note":    "ZF=F",
        "2Y T-Note":    "ZT=F",
        "Ultra T-Bond": "UB=F",
    },
    "Crypto": {
        "Bitcoin":  "BTC-USD",
        "Ethereum": "ETH-USD",
    },
}


def _require_env() -> tuple[str, str]:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SECRET_KEY")
    if not url or not key:
        sys.exit("ERROR: SUPABASE_URL and SUPABASE_SECRET_KEY must be set in the environment.")
    return url, key


def _to_naive_shift(idx: pd.DatetimeIndex, shift_days: int) -> pd.DatetimeIndex:
    """Drop any timezone and apply a day shift (forex UTC correction)."""
    idx = pd.to_datetime(idx)
    if idx.tz is not None:
        idx = idx.tz_localize(None)
    return idx - pd.Timedelta(days=shift_days)


def _yf_close(ticker: str, start: datetime, end: datetime) -> pd.Series:
    """Daily Close from yfinance with the -1 day forex shift (used for legs)."""
    raw = yf.download(ticker, start=start, end=end, auto_adjust=False, progress=False)
    if raw.empty:
        return pd.Series(dtype=float)
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)
    s = raw["Close"].dropna()
    s.index = _to_naive_shift(s.index, 1)
    return s


def _yf_ohlc(ticker: str, start: datetime, end: datetime, is_forex: bool) -> pd.DataFrame:
    """Daily OHLC from yfinance. -1 day shift only for forex (=X) tickers."""
    raw = yf.download(ticker, start=start, end=end, auto_adjust=False, progress=False)
    if raw.empty:
        return pd.DataFrame()
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)
    df = raw[["Open", "High", "Low", "Close"]].copy().dropna()
    df.index = _to_naive_shift(df.index, 1 if is_forex else 0)
    return df


# Per-run cache so each USD leg is downloaded only once (21 crosses reuse 7 legs).
_LEG_CACHE: dict[str, pd.Series] = {}


def _leg_series(leg_key: str, start: datetime, end: datetime) -> pd.Series:
    """XXX/USD Close for one leg, inverting USD-base quotes (CAD/CHF/JPY)."""
    if leg_key in _LEG_CACHE:
        return _LEG_CACHE[leg_key]
    s = _yf_close(_USD_YF[leg_key], start, end)
    if not s.empty and leg_key in _INVERT_LEG:
        s = 1.0 / s
    _LEG_CACHE[leg_key] = s
    return s


def build_ohlc(kind: str, spec, start: datetime, end: datetime) -> pd.DataFrame:
    """Return an OHLC DataFrame for one instrument (empty on failure)."""
    if kind == "synthetic":
        num_key, den_key = spec
        num_s = _leg_series(num_key, start, end)
        den_s = _leg_series(den_key, start, end)
        common = num_s.index.intersection(den_s.index)
        if len(common) <= 50:
            return pd.DataFrame()
        close = (num_s.loc[common] / den_s.loc[common]).dropna()
        df = close.to_frame(name="Close")
        df["Open"] = df["High"] = df["Low"] = df["Close"]  # synthetic: no intraday
        df = df[["Open", "High", "Low", "Close"]]
    else:  # "direct" — spec is the yfinance ticker
        df = _yf_ohlc(spec, start, end, is_forex=str(spec).endswith("=X"))

    if df.empty:
        return pd.DataFrame()
    df = df[df["Close"] > 0]  # guard: drop non-positive prices
    return df


def instrument_plan() -> list[dict]:
    """Build the ordered 56-instrument work list."""
    plan: list[dict] = []
    for symbol, ticker in FOREX_MAJORS.items():
        plan.append({"symbol": symbol, "category": "Forex", "kind": "direct", "spec": ticker})
    for key, legs in SYNTHETIC_CROSSES.items():
        symbol = f"{key[:3]}/{key[3:]}"
        plan.append({"symbol": symbol, "category": "Forex", "kind": "synthetic", "spec": legs})
    for category, members in SCREENER_CATEGORIES.items():
        for symbol, ticker in members.items():
            plan.append({"symbol": symbol, "category": category, "kind": "direct", "spec": ticker})
    return plan


def df_to_rows(symbol: str, category: str, df: pd.DataFrame) -> list[dict]:
    rows = []
    for ts, r in df.iterrows():
        rows.append({
            "symbol": symbol,
            "category": category,
            "date": pd.Timestamp(ts).date().isoformat(),
            "open": round(float(r["Open"]), 6),
            "high": round(float(r["High"]), 6),
            "low": round(float(r["Low"]), 6),
            "close": round(float(r["Close"]), 6),
        })
    return rows


def upsert_rows(client, rows: list[dict]) -> int:
    written = 0
    for start in range(0, len(rows), UPSERT_CHUNK):
        chunk = rows[start:start + UPSERT_CHUNK]
        client.table("seasonality_prices").upsert(chunk, on_conflict="symbol,date").execute()
        written += len(chunk)
    return written


def main() -> None:
    url, key = _require_env()
    client = create_client(url, key)

    end = datetime.today()
    start = end - timedelta(days=int(HISTORY_YEARS * 365.25))
    plan = instrument_plan()
    print(f"Fetching daily OHLC for {len(plan)} instruments "
          f"({start.date()} .. {end.date()})...")

    summary: list[dict] = []
    total_written = 0

    for item in plan:
        symbol, category = item["symbol"], item["category"]
        try:
            df = build_ohlc(item["kind"], item["spec"], start, end)
        except Exception as exc:  # download / parse — never abort the whole run
            print(f"  skip  {symbol:14s} ({category}): {exc}")
            summary.append({"symbol": symbol, "category": category, "rows": 0,
                            "first": None, "last": None, "years": 0.0})
            continue

        if df.empty:
            print(f"  skip  {symbol:14s} ({category}): no data")
            summary.append({"symbol": symbol, "category": category, "rows": 0,
                            "first": None, "last": None, "years": 0.0})
            continue

        rows = df_to_rows(symbol, category, df)
        written = upsert_rows(client, rows)
        total_written += written
        first, last = df.index[0].date(), df.index[-1].date()
        years = (df.index[-1] - df.index[0]).days / 365.25
        flag = "  ⚠ short" if years < SHORT_HISTORY_YEARS else ""
        print(f"  ok    {symbol:14s} ({category:11s}): {written:>5} rows  "
              f"{first} .. {last}  ({years:4.1f}y){flag}")
        summary.append({"symbol": symbol, "category": category, "rows": written,
                        "first": first.isoformat(), "last": last.isoformat(),
                        "years": years})

    # ── Run report ────────────────────────────────────────────────────────────
    ok = [s for s in summary if s["rows"] > 0]
    short = [s for s in ok if s["years"] < SHORT_HISTORY_YEARS]
    failed = [s for s in summary if s["rows"] == 0]
    print(f"\nDone: upserted {total_written} rows across {len(ok)}/{len(plan)} symbols.")
    if short:
        print(f"\nShort/limited history (< {SHORT_HISTORY_YEARS:.0f}y):")
        for s in short:
            print(f"  {s['category']:11s} {s['symbol']:14s} {s['years']:4.1f}y "
                  f"({s['first']} .. {s['last']})")
    if failed:
        print("\nNo data (skipped):")
        for s in failed:
            print(f"  {s['category']:11s} {s['symbol']}")


if __name__ == "__main__":
    main()
