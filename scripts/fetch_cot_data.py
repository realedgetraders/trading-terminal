#!/usr/bin/env python3
"""Fetch CFTC Commitments-of-Traders positioning and upsert it into Supabase.

Source: the CFTC Legacy COT history files (deacot{YEAR}.zip) published at
https://www.cftc.gov/files/dea/history/ — free, no API key. This reuses the
exact fetch and computation logic from the Streamlit COT module
(pages/2_COT_Analysis.py), with no Streamlit/UI code.

Coverage: 8 major FX currencies, weekly.
  - net_position : Commercial (hedger) net = Long - Short,
                   FUTURES-ONLY ("(Old)" columns in the Legacy report).
                   Matches the lead category in pages/2_COT_Analysis.py
                   (default group + divergence screener) and Module 7's
                   "Commercials COT Index" consumer.
  - cot_index    : 26-week stochastic min-max normalization of net_position:
                   (current - min_26w) / (max_26w - min_26w) * 100
                   (100 = most net-long in 26 weeks, 0 = most net-short;
                   None while the 26-week window is not yet full).

Rows are written to the ``cot_data`` table (columns: currency, report_date,
net_position, cot_index, source) via upsert on the natural key
(currency, report_date), so re-runs never create duplicates. A market that is
missing or renamed is reported and skipped — one bad market never aborts the run.

This module is intentionally provider-agnostic at the plumbing layer: adding a
new market later means appending one entry to ``MARKETS`` — the fetch/parse and
Supabase-load code stays untouched.

Required environment variables (never hardcode credentials):
  SUPABASE_URL         Supabase project URL
  SUPABASE_SECRET_KEY  Supabase secret (service) key

Run:
  python scripts/fetch_cot_data.py
"""
from __future__ import annotations

import io
import os
import sys
import zipfile
from datetime import datetime

import pandas as pd
import requests
from supabase import create_client

SOURCE = "cftc"
START_YEAR = 2020          # ~5y history — ample context for the 26-week index
REQUEST_TIMEOUT = 30       # seconds per CFTC request
UPSERT_CHUNK = 500         # rows per Supabase upsert call
COT_INDEX_WINDOW = 26      # weeks — stochastic normalization window

# currency -> exact "Market and Exchange Names" string from deacot{YEAR}.zip
# (Forex group, taken verbatim from pages/2_COT_Analysis.py). Raw CFTC numbers,
# no inversion applied to any market.
MARKETS = {
    "USD": "USD INDEX - ICE FUTURES U.S.",
    "EUR": "EURO FX - CHICAGO MERCANTILE EXCHANGE",
    "GBP": "BRITISH POUND - CHICAGO MERCANTILE EXCHANGE",
    "JPY": "JAPANESE YEN - CHICAGO MERCANTILE EXCHANGE",
    "AUD": "AUSTRALIAN DOLLAR - CHICAGO MERCANTILE EXCHANGE",
    "NZD": "NZ DOLLAR - CHICAGO MERCANTILE EXCHANGE",
    "CAD": "CANADIAN DOLLAR - CHICAGO MERCANTILE EXCHANGE",
    "CHF": "SWISS FRANC - CHICAGO MERCANTILE EXCHANGE",
}

# Exact column names from deacot{YEAR}.zip (Legacy COT format).
# "(Old)" = Futures only (not Futures+Options). Commercials = hedgers/producers.
_NAME_COL = "Market and Exchange Names"
_DATE_COL = "As of Date in Form YYYY-MM-DD"
_LONG_COL = "Commercial Positions-Long (Old)"
_SHORT_COL = "Commercial Positions-Short (Old)"


def _require_env() -> tuple[str, str]:
    """Read Supabase credentials from the environment; exit if either is absent."""
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SECRET_KEY")
    if not url or not key:
        sys.exit("ERROR: SUPABASE_URL and SUPABASE_SECRET_KEY must be set in the environment.")
    return url, key


def fetch_cot_raw(start_year: int) -> pd.DataFrame:
    """Download and concatenate the Legacy COT zips from start_year to now.

    Returns an empty DataFrame if every year fails. A single bad year (network
    error, missing file) is reported and skipped.
    """
    current_year = datetime.now().year
    frames: list[pd.DataFrame] = []
    for yr in range(start_year, current_year + 1):
        url = f"https://www.cftc.gov/files/dea/history/deacot{yr}.zip"
        try:
            resp = requests.get(url, timeout=REQUEST_TIMEOUT)
            if resp.status_code != 200:
                print(f"  skip  {yr}: HTTP {resp.status_code}")
                continue
            with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
                with z.open(z.namelist()[0]) as f:
                    frames.append(pd.read_csv(f, low_memory=False))
        except Exception as exc:  # network / zip / parse — never abort the whole run
            print(f"  skip  {yr}: {exc}")
    if not frames:
        return pd.DataFrame()
    combined = pd.concat(frames, ignore_index=True)
    combined.columns = combined.columns.str.strip()
    return combined


def market_net_series(raw: pd.DataFrame, market_name: str) -> pd.Series:
    """Return the weekly Commercial net series (Long - Short, futures-only)
    for one market, indexed by report date (ascending, de-duplicated).

    Mirrors get_market_data() in pages/2_COT_Analysis.py: substring match on the
    market name, parse the as-of date, drop duplicate dates (earliest name wins).
    Returns an empty Series when the market or required columns are absent.
    """
    if _NAME_COL not in raw.columns:
        return pd.Series(dtype=float)
    if _LONG_COL not in raw.columns or _SHORT_COL not in raw.columns:
        return pd.Series(dtype=float)

    mask = raw[_NAME_COL].str.upper().str.contains(
        market_name.upper(), regex=False, na=False
    )
    df = raw[mask].copy()
    if df.empty or _DATE_COL not in df.columns:
        return pd.Series(dtype=float)

    df["Date"] = pd.to_datetime(df[_DATE_COL], errors="coerce")
    df = (
        df.dropna(subset=["Date"])
        .sort_values("Date")
        .drop_duplicates(subset=["Date"], keep="first")  # transition-year overlaps
        .set_index("Date")
    )

    longs = pd.to_numeric(df[_LONG_COL], errors="coerce")
    shorts = pd.to_numeric(df[_SHORT_COL], errors="coerce")
    return (longs - shorts).dropna()


def calc_cot_index(series: pd.Series, window: int = COT_INDEX_WINDOW) -> pd.Series:
    """Stochastic-style min-max normalization over a rolling window.

    COT Index = (current - min_N) / (max_N - min_N) * 100
    100 = most long in N weeks, 0 = most short. NaN when range == 0 or the
    window is not yet full. Identical to calc_cot_index() in the source module.
    """
    roll = series.rolling(window, min_periods=window)
    mn = roll.min()
    mx = roll.max()
    rng = mx - mn
    return ((series - mn) / rng * 100).where(rng != 0)


def collect_cot_rows(raw: pd.DataFrame) -> list[dict]:
    """Build Supabase row dicts for every currency × report date."""
    rows: list[dict] = []
    for currency, market_name in MARKETS.items():
        net = market_net_series(raw, market_name)
        if net.empty:
            print(f"  skip  {currency}: market not found ({market_name})")
            continue

        index = calc_cot_index(net)
        for when, net_val in net.items():
            ci = index.get(when)
            rows.append({
                "currency": currency,
                "report_date": when.date().isoformat(),
                "net_position": int(round(float(net_val))),
                "cot_index": None if pd.isna(ci) else round(float(ci), 2),
                "source": SOURCE,
            })
        print(f"  ok    {currency}: {len(net):>3} weeks (latest {net.index[-1].date()})")
    return rows


def upsert_rows(client, rows: list[dict]) -> int:
    """Upsert rows into cot_data in chunks, deduping on (currency, report_date)."""
    written = 0
    for start in range(0, len(rows), UPSERT_CHUNK):
        chunk = rows[start:start + UPSERT_CHUNK]
        client.table("cot_data").upsert(chunk, on_conflict="currency,report_date").execute()
        written += len(chunk)
    return written


def main() -> None:
    url, key = _require_env()
    client = create_client(url, key)

    print(f"Fetching CFTC COT data (deacot{START_YEAR}..{datetime.now().year})...")
    raw = fetch_cot_raw(START_YEAR)
    if raw.empty:
        sys.exit("ERROR: no COT data fetched from CFTC — nothing to write.")
    if _NAME_COL not in raw.columns:
        sys.exit(f"ERROR: unexpected CFTC schema (missing '{_NAME_COL}' column).")

    rows = collect_cot_rows(raw)
    if not rows:
        sys.exit("ERROR: no COT rows built — nothing to write.")

    print(f"Upserting {len(rows)} rows into cot_data...")
    written = upsert_rows(client, rows)
    print(f"Done: upserted {written} rows (source={SOURCE}).")


if __name__ == "__main__":
    main()
