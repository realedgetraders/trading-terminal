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
from collections import defaultdict
from datetime import datetime, timedelta

import pandas as pd
import yfinance as yf
from supabase import create_client

from _assets_feed import load_assets, with_module
from _incremental import fetch_start, is_backfill, latest_dates, resolve_mode

HISTORY_YEARS = 25
UPSERT_CHUNK = 1000          # rows per Supabase upsert call
SHORT_HISTORY_YEARS = 20.0   # below this span a symbol is flagged in the report
RETRY_SLEEP = 2              # seconds before the single retry of a transient fail
BATCH_SIZE = 50              # tickers per bulk yfinance download (direct assets)
BATCH_SLEEP = 1.5            # seconds paced between bulk batches


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
# Keyed by (ticker, start) so a leg shared by a tail cross and a backfill cross —
# which need different start dates — is not served the wrong (too-short) window.
_LEG_CACHE: dict[tuple, pd.Series] = {}


def _leg_series(ticker: str, invert: bool, start, end: datetime) -> pd.Series:
    """XXX/USD Close for one leg, inverting USD-base quotes when flagged."""
    cache_key = (ticker, start)
    if cache_key not in _LEG_CACHE:
        _LEG_CACHE[cache_key] = _yf_close(ticker, start, end)
    s = _LEG_CACHE[cache_key]
    if not s.empty and invert:
        s = 1.0 / s
    return s


def build_ohlc(seasonality: dict, start: datetime, end: datetime,
               min_overlap: int = 50) -> pd.DataFrame:
    """Return an OHLC DataFrame for one asset (empty on failure).

    Resolution is taken from the feed's `seasonality` block. The -1 day shift is
    driven strictly by resolve == 'fx_spot' (spot legs of a synthetic carry it
    too via _yf_close); 'direct' assets are never shifted.

    ``min_overlap`` is the minimum number of shared leg dates required to build a
    synthetic cross. The default 50 rejects barely-overlapping (invalid) pairs on
    a full backfill; a tail run passes a smaller value, since a few recent days of
    overlap is all a known-valid cross can have in the short tail window.
    """
    resolve = seasonality["resolve"]
    if resolve == "synthetic":
        leg_a, leg_b = seasonality["legA"], seasonality["legB"]
        num_s = _leg_series(leg_a["ticker"], leg_a["invert"], start, end)
        den_s = _leg_series(leg_b["ticker"], leg_b["invert"], start, end)
        common = num_s.index.intersection(den_s.index)
        if len(common) <= min_overlap:
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


def _process_direct(raw) -> pd.DataFrame:
    """Process a downloaded frame exactly like build_ohlc('direct'): OHLC, dropna,
    NO shift, drop Close<=0 — so the bulk path is byte-identical to the per-symbol
    `_yf_ohlc(shift=False)` path. Used only for direct-resolve assets."""
    if raw is None or raw.empty:
        return pd.DataFrame()
    if isinstance(raw.columns, pd.MultiIndex):
        raw = raw.copy()
        raw.columns = raw.columns.get_level_values(0)
    if not {"Open", "High", "Low", "Close"}.issubset(raw.columns):
        return pd.DataFrame()
    df = raw[["Open", "High", "Low", "Close"]].copy().dropna()
    if df.empty:
        return pd.DataFrame()
    df.index = _to_naive_shift(df.index, 0)
    df = df[df["Close"] > 0]
    return df


def bulk_ohlc(tickers: list[str], start: datetime, end: datetime) -> dict[str, pd.DataFrame]:
    """Batched bulk OHLC download → {ticker: processed OHLC df}, for direct-resolve
    assets only (stocks/ETFs/crypto/indices/commodities/rates).

    Downloads in BATCH_SIZE chunks (threaded, paced by BATCH_SLEEP) to cut
    round-trips and rate-limit hits. auto_adjust=False is preserved; each ticker
    is processed by `_process_direct`, identical to the per-symbol direct path. A
    ticker missing/empty in the batch (or a batch that errors) falls back to the
    exact per-symbol path `build_ohlc({direct})` (which carries the retry-once guard).
    fx_spot (−1 shift) and synthetic crosses are NOT bulked — they keep per-symbol.
    """
    out: dict[str, pd.DataFrame] = {}
    uniq = list(dict.fromkeys(tickers))
    for i in range(0, len(uniq), BATCH_SIZE):
        batch = uniq[i:i + BATCH_SIZE]
        frames = None
        try:
            frames = yf.download(batch, start=start, end=end, auto_adjust=False,
                                 progress=False, group_by="ticker", threads=True)
        except Exception:
            frames = None
        for tk in batch:
            df = pd.DataFrame()
            if frames is not None and not frames.empty:
                try:
                    sub = frames[tk] if isinstance(frames.columns, pd.MultiIndex) else frames
                    df = _process_direct(sub)
                except Exception:
                    df = pd.DataFrame()
            if df.empty:  # missing/transient → exact per-symbol direct path (retry-once)
                try:
                    df = build_ohlc({"resolve": "direct", "ticker": tk}, start, end)
                except Exception:
                    df = pd.DataFrame()
            if not df.empty:
                out[tk] = df
        if i + BATCH_SIZE < len(uniq):
            time.sleep(BATCH_SLEEP)
    return out


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
    backfill_start = (end - timedelta(days=int(HISTORY_YEARS * 365.25))).date()
    plan = instrument_plan()

    # Per-symbol latest stored date → each instrument fetches from its OWN start:
    # full history when it has no data (auto) or backfill is forced, else just the
    # recent tail (latest − overlap). Crucially the start is per-symbol, NOT a
    # shared minimum — a single stale series must never drag the whole universe
    # back to a multi-year refetch.
    mode = resolve_mode()
    latest = {} if mode == "backfill" else latest_dates(
        client, "seasonality_prices", "date", "symbol", [it["symbol"] for it in plan])
    for it in plan:
        it["backfill"] = is_backfill(mode, latest.get(it["symbol"]))
        it["start"] = fetch_start(mode, latest.get(it["symbol"]), backfill_start, end.date())

    n_bf = sum(it["backfill"] for it in plan)
    print(f"[mode={mode}] daily OHLC for {len(plan)} instruments "
          f"({n_bf} backfill, {len(plan) - n_bf} tail; end {end.date()})...")

    summary: list[dict] = []
    total_written = 0

    # Bulk-download the direct-resolve tickers (the bulk of the universe), grouped
    # by their per-symbol start so the fresh majority (one shared recent start)
    # batches together while a stale/new series only fetches its own gap. fx_spot
    # / synthetic stay per-symbol below (exact −1 shift / leg synthesis).
    direct_by_start: dict = defaultdict(list)
    for it in plan:
        if it["seasonality"]["resolve"] == "direct":
            direct_by_start[it["start"]].append(it["seasonality"]["ticker"])
    bulk_cache: dict[str, pd.DataFrame] = {}
    for s_start, tickers in sorted(direct_by_start.items()):
        print(f"  bulk-downloading {len(tickers)} direct tickers from {s_start} "
              f"in batches of {BATCH_SIZE}…")
        bulk_cache.update(bulk_ohlc(tickers, s_start, end))

    for item in plan:
        symbol, category = item["symbol"], item["category"]
        block = item["seasonality"]
        try:
            if block["resolve"] == "direct":
                df = bulk_cache.get(block["ticker"], pd.DataFrame())
            else:  # fx_spot / synthetic — per-symbol (shift / leg synthesis)
                # Tail runs have only a few overlapping leg days; relax the
                # synthetic min-overlap guard (it's a backfill data-quality check).
                df = build_ohlc(block, item["start"], end,
                                min_overlap=50 if item["backfill"] else 0)
        except Exception as exc:  # download / parse — never abort the whole run
            print(f"  skip  {symbol:14s} ({category}): {exc}")
            summary.append({"symbol": symbol, "category": category, "rows": 0,
                            "first": None, "last": None, "years": 0.0, "backfill": item["backfill"]})
            continue

        if df.empty:
            print(f"  skip  {symbol:14s} ({category}): no data")
            summary.append({"symbol": symbol, "category": category, "rows": 0,
                            "first": None, "last": None, "years": 0.0, "backfill": item["backfill"]})
            continue

        rows = df_to_rows(symbol, category, df)
        written = upsert_rows(client, rows)
        total_written += written
        first, last = df.index[0].date(), df.index[-1].date()
        years = (df.index[-1] - df.index[0]).days / 365.25
        # The short-history flag is only meaningful on a full pull — a tail run
        # fetches only the recent window, so suppress it there.
        flag = "  ⚠ short" if (item["backfill"] and years < SHORT_HISTORY_YEARS) else ""
        print(f"  ok    {symbol:14s} ({category:11s}): {written:>5} rows  "
              f"{first} .. {last}  ({years:4.1f}y){flag}")
        summary.append({"symbol": symbol, "category": category, "rows": written,
                        "first": first.isoformat(), "last": last.isoformat(),
                        "years": years, "backfill": item["backfill"]})

    # ── Run report ────────────────────────────────────────────────────────────
    ok = [s for s in summary if s["rows"] > 0]
    short = [s for s in ok if s["backfill"] and s["years"] < SHORT_HISTORY_YEARS]
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
