#!/usr/bin/env python3
"""Fetch daily OHLC for the Seasonality universe into Supabase.

Source of truth for the universe: the canonical asset feed (/api/assets, loaded
via _assets_feed). Every asset with modules.seasonality is fetched; each asset's
`seasonality` block drives resolution (the fetch LOGIC below is unchanged — only
the work-list source moved from hardcoded dicts to the feed):
  - fx_spot    direct yfinance OHLC of the spot =X pair, with a -1 day index
               shift (UTC fix).
  - synthetic  Close-only cross built from two XXX/USD legs, legA / legB,
               each inverted (1/price) when its `invert` flag is set (Yahoo
               quotes CAD/CHF/JPY USD-base). Legs are =X spot, so they carry the
               same -1 day shift.
  - direct     direct yfinance OHLC of the given ticker, NO shift (cash '^'
               indices, '=F' futures, '-USD' crypto, plain stocks).

The -1 day shift is driven STRICTLY by resolve == 'fx_spot' (and by the spot
legs of a synthetic) — never by a ticker-suffix heuristic, so stocks/indices are
never shifted.

Guards (unchanged): auto_adjust=False (unadjusted prices); rows with Close <= 0
are dropped (e.g. CL=F's negative 2020-04-20 print). Transient yfinance failures
are retried once; a symbol that still fails is reported and skipped — one bad
symbol never aborts the run.

Rows go to the ``seasonality_prices`` table (symbol, category, date, open, high,
low, close) keyed by the feed's `symbol` + `category`, via upsert on
(symbol, date) — re-runs never duplicate.

Required environment variables (never hardcode credentials):
  SUPABASE_URL         Supabase project URL
  SUPABASE_SECRET_KEY  Supabase secret (service) key

Run:
  python scripts/fetch_seasonality_prices.py
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

HISTORY_YEARS = 25
UPSERT_CHUNK = 1000          # rows per Supabase upsert call
SHORT_HISTORY_YEARS = 20.0   # below this span a symbol is flagged in the report
RETRY_SLEEP = 2              # seconds before the single retry of a transient fail


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


def _download(ticker: str, start: datetime, end: datetime) -> pd.DataFrame:
    """yfinance daily download with one retry on a transient failure.

    A transient failure is an exception OR an empty frame on the first attempt
    (rate-limit / hiccup); after the retry an empty frame is treated as "no data"
    (genuinely invalid ticker) and returned empty. auto_adjust=False (unadjusted)
    is preserved.
    """
    for attempt in (1, 2):
        try:
            raw = yf.download(ticker, start=start, end=end,
                              auto_adjust=False, progress=False)
            if raw is not None and not raw.empty:
                return raw
        except Exception:
            if attempt == 2:
                raise
        if attempt == 1:
            time.sleep(RETRY_SLEEP)
    return pd.DataFrame()


def _yf_close(ticker: str, start: datetime, end: datetime) -> pd.Series:
    """Daily Close from yfinance with the -1 day spot shift (used for FX legs)."""
    raw = _download(ticker, start, end)
    if raw.empty:
        return pd.Series(dtype=float)
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)
    s = raw["Close"].dropna()
    s.index = _to_naive_shift(s.index, 1)
    return s


def _yf_ohlc(ticker: str, start: datetime, end: datetime, shift: bool) -> pd.DataFrame:
    """Daily OHLC from yfinance. -1 day shift applied only when `shift` is set."""
    raw = _download(ticker, start, end)
    if raw.empty:
        return pd.DataFrame()
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)
    df = raw[["Open", "High", "Low", "Close"]].copy().dropna()
    df.index = _to_naive_shift(df.index, 1 if shift else 0)
    return df


# Per-run cache so each spot leg is downloaded only once (crosses reuse 7 legs).
_LEG_CACHE: dict[str, pd.Series] = {}


def _leg_series(ticker: str, invert: bool, start: datetime, end: datetime) -> pd.Series:
    """XXX/USD Close for one leg, inverting USD-base quotes when flagged."""
    if ticker not in _LEG_CACHE:
        _LEG_CACHE[ticker] = _yf_close(ticker, start, end)
    s = _LEG_CACHE[ticker]
    if not s.empty and invert:
        s = 1.0 / s
    return s


def build_ohlc(seasonality: dict, start: datetime, end: datetime) -> pd.DataFrame:
    """Return an OHLC DataFrame for one asset (empty on failure).

    Resolution is taken from the feed's `seasonality` block. The -1 day shift is
    driven strictly by resolve == 'fx_spot' (spot legs of a synthetic carry it
    too via _yf_close); 'direct' assets are never shifted.
    """
    resolve = seasonality["resolve"]
    if resolve == "synthetic":
        leg_a, leg_b = seasonality["legA"], seasonality["legB"]
        num_s = _leg_series(leg_a["ticker"], leg_a["invert"], start, end)
        den_s = _leg_series(leg_b["ticker"], leg_b["invert"], start, end)
        common = num_s.index.intersection(den_s.index)
        if len(common) <= 50:
            return pd.DataFrame()
        close = (num_s.loc[common] / den_s.loc[common]).dropna()
        df = close.to_frame(name="Close")
        df["Open"] = df["High"] = df["Low"] = df["Close"]  # synthetic: no intraday
        df = df[["Open", "High", "Low", "Close"]]
    elif resolve == "fx_spot":
        df = _yf_ohlc(seasonality["ticker"], start, end, shift=True)
    else:  # "direct"
        df = _yf_ohlc(seasonality["ticker"], start, end, shift=False)

    if df.empty:
        return pd.DataFrame()
    df = df[df["Close"] > 0]  # guard: drop non-positive prices
    return df


def instrument_plan() -> list[dict]:
    """Work list from the feed: every asset with modules.seasonality, in order."""
    plan: list[dict] = []
    for asset in with_module(load_assets(), "seasonality"):
        block = asset.get("seasonality")
        if not block:  # capability set without a resolution block — skip safely
            print(f"  skip  {asset.get('symbol')}: no seasonality block in feed")
            continue
        plan.append({"symbol": asset["symbol"], "category": asset["category"],
                     "seasonality": block})
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
            df = build_ohlc(item["seasonality"], start, end)
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
