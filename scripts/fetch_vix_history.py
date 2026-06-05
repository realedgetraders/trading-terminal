#!/usr/bin/env python3
"""Fetch daily VIX close prices and upsert them into Supabase.

Source: yfinance ^VIX (CBOE Volatility Index), reused 1:1 from the Market Phase
Scanner module (pages/5_Market_Regime.py): interval="1d", auto_adjust=True,
Close only. ~2 years of history are stored as a buffer; the web app reads the
trailing 12 months to reproduce the module's rolling-window percentile/phase.

Rows go to the ``vix_history`` table (date, close) via upsert on ``date`` — so
re-runs never duplicate and a daily run simply appends the newest close.

Required environment variables (never hardcode credentials):
  SUPABASE_URL         Supabase project URL
  SUPABASE_SECRET_KEY  Supabase secret (service) key

Run:
  python scripts/fetch_vix_history.py
"""
from __future__ import annotations

import os
import sys

import pandas as pd
import yfinance as yf
from supabase import create_client

PERIOD = "2y"          # ~2 years buffer; web app reads the last 12 months
UPSERT_CHUNK = 500     # rows per Supabase upsert call


def _require_env() -> tuple[str, str]:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SECRET_KEY")
    if not url or not key:
        sys.exit("ERROR: SUPABASE_URL and SUPABASE_SECRET_KEY must be set in the environment.")
    return url, key


def fetch_vix() -> pd.Series:
    """Daily VIX Close series (ascending by date). Empty on failure."""
    df = yf.download("^VIX", period=PERIOD, interval="1d", progress=False, auto_adjust=True)
    if df.empty:
        return pd.Series(dtype=float)
    close = df["Close"].dropna()
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    close.index = pd.to_datetime(close.index)
    return close.sort_index()


def upsert_rows(client, rows: list[dict]) -> int:
    written = 0
    for start in range(0, len(rows), UPSERT_CHUNK):
        chunk = rows[start:start + UPSERT_CHUNK]
        client.table("vix_history").upsert(chunk, on_conflict="date").execute()
        written += len(chunk)
    return written


def main() -> None:
    url, key = _require_env()
    client = create_client(url, key)

    print(f"Fetching ^VIX daily close ({PERIOD})...")
    vix = fetch_vix()
    if vix.empty:
        sys.exit("ERROR: no VIX data fetched from Yahoo Finance — nothing to write.")

    rows = [
        {"date": ts.date().isoformat(), "close": round(float(val), 2)}
        for ts, val in vix.items()
    ]

    print(f"Upserting {len(rows)} rows into vix_history...")
    written = upsert_rows(client, rows)

    first, last = vix.index[0].date(), vix.index[-1].date()
    print(f"Done: upserted {written} rows  ({first} .. {last})")
    print(f"Latest: {last}  close={round(float(vix.iloc[-1]), 2)}")


if __name__ == "__main__":
    main()
