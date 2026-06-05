#!/usr/bin/env python3
"""Fetch daily adjusted close for the Valuation Tool's symbols into Supabase.

Source: yfinance (adjusted, daily). The symbol universe is reused 1:1 from
pages/7_Valuation.py — the 38 tradable futures (FUTURES_BY_CAT) plus the four
macro-anchor sources (primary + fallback tickers). ~3 years of history are
stored, enough lookback for the 12-month rolling-range (stochastic %K) the web
app computes; newer tickers (crypto futures) store whatever is available.

Rows go to the ``valuation_prices`` table (symbol, date, close) via upsert on
(symbol, date), so re-runs never duplicate. A symbol that fails to download is
reported and skipped — one bad symbol never aborts the run.

Required environment variables (never hardcode credentials):
  SUPABASE_URL         Supabase project URL
  SUPABASE_SECRET_KEY  Supabase secret (service) key

Run:
  python scripts/fetch_valuation_prices.py
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta

import pandas as pd
import yfinance as yf
from supabase import create_client

HISTORY_YEARS = 3
UPSERT_CHUNK = 1000        # rows per Supabase upsert call

# ─── Symbol universe (verbatim from pages/7_Valuation.py) ────────────────────

# Tradable futures, grouped by screener category — FUTURES_BY_CAT.
FUTURES_BY_CAT = {
    "Forex": {
        "Euro FX":            "6E=F",
        "British Pound":      "6B=F",
        "Japanese Yen":       "6J=F",
        "Australian Dollar":  "6A=F",
        "Canadian Dollar":    "6C=F",
        "Swiss Franc":        "6S=F",
        "New Zealand Dollar": "6N=F",
        "Mexican Peso":       "6M=F",
    },
    "Commodities": {
        "Crude Oil (WTI)":    "CL=F",
        "Brent Crude":        "BZ=F",
        "Natural Gas":        "NG=F",
        "RBOB Gasoline":      "RB=F",
        "Heating Oil":        "HO=F",
        "Gold":               "GC=F",
        "Silver":             "SI=F",
        "Platinum":           "PL=F",
        "Palladium":          "PA=F",
        "Copper":             "HG=F",
    },
    "Agriculture": {
        "Corn":               "ZC=F",
        "Wheat":              "ZW=F",
        "Soybeans":           "ZS=F",
        "Soybean Oil":        "ZL=F",
        "Soybean Meal":       "ZM=F",
        "Coffee":             "KC=F",
        "Cocoa":              "CC=F",
        "Cotton":             "CT=F",
        "Sugar":              "SB=F",
        "Orange Juice":       "OJ=F",
        "Live Cattle":        "LE=F",
        "Feeder Cattle":      "GF=F",
        "Lean Hogs":          "HE=F",
    },
    "Indices": {
        "S&P 500":            "ES=F",
        "Nasdaq 100":         "NQ=F",
        "Dow Jones":          "YM=F",
        "Russell 2000":       "RTY=F",
        "Nikkei 225":         "NKD=F",
    },
    "Crypto": {
        "Bitcoin":            "BTC=F",
        "Ethereum":           "ETH=F",
    },
}

# Macro-anchor tickers — primary sources + fallbacks (ANCHORS in the module).
# (The metals-basket tickers GC=F/SI=F/PL=F/PA=F are already in the futures.)
ANCHOR_PRIMARY  = ["DX-Y.NYB", "ZN=F", "ACWI"]
ANCHOR_FALLBACK = ["DX=F", "IEF", "VT", "GLD"]


def _symbol_universe() -> list[str]:
    """All distinct tickers to collect, de-duplicated, in a stable order."""
    seen: set[str] = set()
    out: list[str] = []
    groups = [tk for cat in FUTURES_BY_CAT.values() for tk in cat.values()]
    for tk in groups + ANCHOR_PRIMARY + ANCHOR_FALLBACK:
        if tk not in seen:
            seen.add(tk)
            out.append(tk)
    return out


def _require_env() -> tuple[str, str]:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SECRET_KEY")
    if not url or not key:
        sys.exit("ERROR: SUPABASE_URL and SUPABASE_SECRET_KEY must be set in the environment.")
    return url, key


def fetch_close(ticker: str, start: datetime, end: datetime) -> pd.Series:
    """Daily adjusted Close from yfinance (ascending by date). Empty on failure."""
    raw = yf.download(ticker, start=start, end=end, interval="1d",
                      auto_adjust=True, progress=False)
    if raw is None or raw.empty or "Close" not in raw:
        return pd.Series(dtype=float)
    close = raw["Close"]
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    close = close.dropna()
    if close.empty:
        return pd.Series(dtype=float)
    close.index = pd.to_datetime(close.index)
    return close.sort_index()


def upsert_rows(client, rows: list[dict]) -> int:
    written = 0
    for start in range(0, len(rows), UPSERT_CHUNK):
        chunk = rows[start:start + UPSERT_CHUNK]
        client.table("valuation_prices").upsert(chunk, on_conflict="symbol,date").execute()
        written += len(chunk)
    return written


def main() -> None:
    url, key = _require_env()
    client = create_client(url, key)

    end = datetime.today()
    start = end - timedelta(days=int(HISTORY_YEARS * 365.25))
    symbols = _symbol_universe()
    print(f"Fetching daily adjusted close for {len(symbols)} symbols "
          f"({start.date()} .. {end.date()})...")

    total_written = 0
    summary: list[dict] = []
    failed: list[str] = []

    for ticker in symbols:
        try:
            close = fetch_close(ticker, start, end)
        except Exception as exc:  # download / parse — never abort the whole run
            print(f"  skip  {ticker:10s}: {exc}")
            failed.append(ticker)
            continue

        if close.empty:
            print(f"  skip  {ticker:10s}: no data")
            failed.append(ticker)
            continue

        rows = [
            {"symbol": ticker, "date": ts.date().isoformat(), "close": round(float(val), 6)}
            for ts, val in close.items()
        ]
        written = upsert_rows(client, rows)
        total_written += written
        first, last = close.index[0].date(), close.index[-1].date()
        print(f"  ok    {ticker:10s}: {written:>4} rows  {first} .. {last}")
        summary.append({"symbol": ticker, "rows": written,
                        "first": first.isoformat(), "last": last.isoformat()})

    # ── Run report ────────────────────────────────────────────────────────────
    print(f"\nDone: upserted {total_written} rows across {len(summary)}/{len(symbols)} symbols.")
    if failed:
        print(f"\nFailed / no data ({len(failed)}):")
        for tk in failed:
            print(f"  {tk}")


if __name__ == "__main__":
    main()
