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
from _incremental import fetch_start, is_backfill, latest_dates, resolve_mode

HISTORY_YEARS = 3
UPSERT_CHUNK = 1000        # rows per Supabase upsert call
RETRY_SLEEP = 2            # seconds before the single retry of a transient fail
PACE_EVERY = 50            # pause every N per-ticker downloads (rate-limit pacing)
PACE_SLEEP = 1.5           # seconds paused at each pacing interval
MIN_SUCCESS_RATIO = 0.5    # below this share of symbols written → fatal (red job)

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

    NB: kept per-ticker (NOT batched). yfinance's `auto_adjust=True` adjustment
    factor is rounded slightly differently in batched vs single-ticker downloads
    (~1e-5 on dividend-paying stocks), so a bulk path would not be byte-identical
    to the stored series — unacceptable here. Seasonality (auto_adjust=False, raw
    OHLC) has no such drift and IS batched. The per-ticker loop is paced instead.
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
    backfill_start = (end - timedelta(days=int(HISTORY_YEARS * 365.25))).date()
    symbols = _symbol_universe()

    mode = resolve_mode()
    latest = {} if mode == "backfill" else latest_dates(
        client, "valuation_prices", "date", "symbol", symbols)
    n_backfill = sum(is_backfill(mode, latest.get(tk)) for tk in symbols)
    print(f"[mode={mode}] daily adjusted close for {len(symbols)} symbols "
          f"({n_backfill} backfill, {len(symbols) - n_backfill} tail; end {end.date()})...")

    total_written = 0
    summary: list[dict] = []
    failed: list[str] = []

    for idx, ticker in enumerate(symbols):
        if idx and idx % PACE_EVERY == 0:
            time.sleep(PACE_SLEEP)  # pace bursts to limit yfinance rate-limiting
        start = fetch_start(mode, latest.get(ticker), backfill_start, end.date())
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
        try:
            written = upsert_rows(client, rows)
        except Exception as exc:  # transient Supabase/throttle — skip, never abort
            print(f"  skip  {ticker:10s}: upsert failed: {exc}")
            failed.append(ticker)
            continue
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

    # ── Tolerant exit (see fetch_seasonality_prices) ────────────────────────────
    # Red only on a systemic failure: nothing written (Supabase down) or fewer
    # than MIN_SUCCESS_RATIO of symbols written. A few throttled skips heal on the
    # next idempotent daily run.
    ratio = len(summary) / len(symbols) if symbols else 0.0
    if not summary or ratio < MIN_SUCCESS_RATIO:
        sys.exit(f"ERROR: only {len(summary)}/{len(symbols)} symbols written "
                 f"({ratio:.0%} < {MIN_SUCCESS_RATIO:.0%} min) — treating as fatal.")
    print(f"OK: {len(summary)}/{len(symbols)} symbols written ({ratio:.0%} ≥ "
          f"{MIN_SUCCESS_RATIO:.0%}) — run successful (skips heal on the next daily run).")


if __name__ == "__main__":
    main()
