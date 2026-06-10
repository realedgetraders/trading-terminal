#!/usr/bin/env python3
"""Fetch daily adjusted close for the Valuation universe into Supabase.

Source: yfinance (adjusted, daily). The symbol universe comes from the canonical
asset feed (/api/assets, loaded via _assets_feed): every asset with
modules.valuation, keyed by its `yfinanceTicker`. The four macro-anchor / fixed
benchmark sources (primary + fallback tickers) stay hardcoded here — they are
fixed comparison series, not part of the tradable universe. ~3 years of history
are stored, enough lookback for the 12-month rolling-range (stochastic %K) the
web app computes; newer tickers store whatever is available.

Rows go to the ``valuation_prices`` table (symbol, date, close) via upsert on
(symbol, date), so re-runs never duplicate. Transient yfinance failures are
retried once; a symbol that still fails is reported and skipped — one bad symbol
never aborts the run.

Required environment variables (never hardcode credentials):
  SUPABASE_URL         Supabase project URL
  SUPABASE_SECRET_KEY  Supabase secret (service) key

Run:
  python scripts/fetch_valuation_prices.py
"""
from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timedelta

import pandas as pd
import yfinance as yf
from supabase import create_client

from _assets_feed import load_assets, with_module

HISTORY_YEARS = 3
UPSERT_CHUNK = 1000        # rows per Supabase upsert call
RETRY_SLEEP = 2            # seconds before the single retry of a transient fail

# Macro-anchor tickers — primary sources + fallbacks (ANCHORS in the module).
# Fixed benchmark series (not part of the tradable feed universe), so kept here.
# (The metals-basket tickers GC=F/SI=F/PL=F/PA=F are already in the universe.)
ANCHOR_PRIMARY  = ["DX-Y.NYB", "ZN=F", "ACWI"]
ANCHOR_FALLBACK = ["DX=F", "IEF", "VT", "GLD"]


def _symbol_universe() -> list[str]:
    """All distinct tickers to collect, de-duplicated, in a stable order.

    The tradable universe is every asset with modules.valuation (keyed by its
    yfinanceTicker) from the feed; the fixed macro anchors are appended.
    """
    seen: set[str] = set()
    out: list[str] = []
    universe = [a["yfinanceTicker"] for a in with_module(load_assets(), "valuation")]
    for tk in universe + ANCHOR_PRIMARY + ANCHOR_FALLBACK:
        if tk and tk not in seen:
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
    """Daily adjusted Close from yfinance (ascending by date). Empty on failure.

    One retry on a transient failure (exception or first-attempt empty); after
    the retry an empty frame is treated as "no data" (invalid ticker).
    """
    raw = None
    for attempt in (1, 2):
        try:
            raw = yf.download(ticker, start=start, end=end, interval="1d",
                              auto_adjust=True, progress=False)
            if raw is not None and not raw.empty:
                break
        except Exception:
            if attempt == 2:
                raise
        if attempt == 1:
            time.sleep(RETRY_SLEEP)
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
