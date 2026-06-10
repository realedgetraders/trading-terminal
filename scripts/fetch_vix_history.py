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
import time
from datetime import date, datetime, timedelta

import pandas as pd
import yfinance as yf
from supabase import create_client

from _incremental import OVERLAP_DAYS, latest_date, resolve_mode

PERIOD = "2y"          # ~2 years buffer; web app reads the last 12 months
UPSERT_CHUNK = 500     # rows per Supabase upsert call
MAX_ATTEMPTS = 3       # download attempts before giving up (Yahoo throttling)
RETRY_SLEEP = 2        # base seconds before a retry (scaled by attempt = backoff)


def _require_env() -> tuple[str, str]:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SECRET_KEY")
    if not url or not key:
        sys.exit("ERROR: SUPABASE_URL and SUPABASE_SECRET_KEY must be set in the environment.")
    return url, key


def fetch_vix(period: str | None = None, start: datetime | None = None) -> pd.Series:
    """Daily VIX Close series (ascending by date). Empty on failure.

    Full history when ``period`` is given (backfill); only the recent tail when
    ``start`` is given (incremental). Same interval/auto_adjust either way, so
    overlapping dates are byte-identical to a full pull. A transient Yahoo failure
    (exception or empty frame) is retried with a short backoff before giving up —
    only a genuinely empty result after MAX_ATTEMPTS is treated as "no data".
    """
    df = pd.DataFrame()
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            if start is not None:
                df = yf.download("^VIX", start=start, interval="1d", progress=False, auto_adjust=True)
            else:
                df = yf.download("^VIX", period=period, interval="1d", progress=False, auto_adjust=True)
            if df is not None and not df.empty:
                break
        except Exception:
            if attempt == MAX_ATTEMPTS:
                raise
        if attempt < MAX_ATTEMPTS:
            time.sleep(RETRY_SLEEP * attempt)
    if df is None or df.empty:
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

    mode = resolve_mode()
    latest = None if mode == "backfill" else latest_date(client, "vix_history", "date")
    do_backfill = mode == "backfill" or (mode == "auto" and latest is None)

    if do_backfill:
        print(f"[mode={mode}] backfill — fetching ^VIX daily close (period={PERIOD})...")
        vix = fetch_vix(period=PERIOD)
    else:
        start = (latest or date.today()) - timedelta(days=OVERLAP_DAYS)
        print(f"[mode={mode}] tail — fetching ^VIX daily close from {start} "
              f"(latest stored {latest})...")
        vix = fetch_vix(start=datetime.combine(start, datetime.min.time()))
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
