#!/usr/bin/env python3
"""Fetch CFTC Commitments-of-Traders positioning and upsert it into Supabase.

Source: the CFTC Legacy COT history files (deacot{YEAR}.zip) published at
https://www.cftc.gov/files/dea/history/ — free, no API key. The market universe,
substring-match logic and "(Old)" futures-only columns are reused 1:1 from the
Streamlit COT module (pages/2_COT_Analysis.py), with no Streamlit/UI code.

Coverage: all 19 markets across 4 categories (Forex, Commodities, Indices,
Bonds), weekly. For every (market, report_date) the RAW long/short contracts of
all three trader categories are written — futures-only ("(Old)" columns):
  - comm_long / comm_short        Commercial (hedger)
  - noncomm_long / noncomm_short  Non-Commercial (large speculator)
  - nonrept_long / nonrept_short  Non-Reportable (small trader)

Net positions and the 26-week COT Index are intentionally NOT stored — the web
app derives both from these raw values, so the database stays a single source of
truth with no redundant pre-computation.

Rows are written to the ``cot_data`` table via upsert on the natural key
(market, report_date), so re-runs never create duplicates. A market that is
missing or renamed, or a year that fails to download, is reported and skipped —
one bad market/year never aborts the run.

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
START_YEAR = 2001          # full Legacy COT history (deacot2001.zip onward)
REQUEST_TIMEOUT = 30       # seconds per CFTC request
UPSERT_CHUNK = 500         # rows per Supabase upsert call

# display_name -> exact "Market and Exchange Names" string from deacot{YEAR}.zip.
# A list of names handles markets renamed across years (OR match, dedup by date).
# Raw CFTC numbers only — no inversion applied. Taken verbatim from
# pages/2_COT_Analysis.py (MARKET_GROUPS).
MARKET_GROUPS = {
    "Forex": {
        "USD": "USD INDEX - ICE FUTURES U.S.",
        "EUR": "EURO FX - CHICAGO MERCANTILE EXCHANGE",
        "GBP": "BRITISH POUND - CHICAGO MERCANTILE EXCHANGE",
        "JPY": "JAPANESE YEN - CHICAGO MERCANTILE EXCHANGE",
        "CHF": "SWISS FRANC - CHICAGO MERCANTILE EXCHANGE",
        "CAD": "CANADIAN DOLLAR - CHICAGO MERCANTILE EXCHANGE",
        "AUD": "AUSTRALIAN DOLLAR - CHICAGO MERCANTILE EXCHANGE",
        "NZD": "NZ DOLLAR - CHICAGO MERCANTILE EXCHANGE",
    },
    "Commodities": {
        "Gold":   "GOLD - COMMODITY EXCHANGE INC.",
        "Silver": "SILVER - COMMODITY EXCHANGE INC.",
        # WTI crude was renamed: NYMEX (2001-2022) -> WTI-PHYSICAL (2022-present)
        "Oil (WTI)": [
            "CRUDE OIL, LIGHT SWEET - NEW YORK MERCANTILE EXCHANGE",
            "WTI-PHYSICAL - NEW YORK MERCANTILE EXCHANGE",
        ],
    },
    "Indices": {
        "S&P 500":      "S&P 500 Consolidated - CHICAGO MERCANTILE EXCHANGE",
        "Nasdaq-100":   "NASDAQ-100 Consolidated - CHICAGO MERCANTILE EXCHANGE",
        "Dow Jones":    "DJIA Consolidated - CHICAGO BOARD OF TRADE",
        "Russell 2000": "RUSSELL E-MINI - CHICAGO MERCANTILE EXCHANGE",
    },
    "Bonds": {
        "10Y T-Note": "UST 10Y NOTE - CHICAGO BOARD OF TRADE",
        "30Y T-Bond": "UST BOND - CHICAGO BOARD OF TRADE",
        "2Y T-Note":  "UST 2Y NOTE - CHICAGO BOARD OF TRADE",
        "5Y T-Note":  "UST 5Y NOTE - CHICAGO BOARD OF TRADE",
    },
}

# Exact column names from deacot{YEAR}.zip (Legacy COT format).
# "(Old)" = Futures only (not Futures+Options).
_NAME_COL = "Market and Exchange Names"
_DATE_COL = "As of Date in Form YYYY-MM-DD"

# target db column -> source CSV column (the six raw long/short fields)
_COT_COLS = {
    "comm_long":     "Commercial Positions-Long (Old)",
    "comm_short":    "Commercial Positions-Short (Old)",
    "noncomm_long":  "Noncommercial Positions-Long (Old)",
    "noncomm_short": "Noncommercial Positions-Short (Old)",
    "nonrept_long":  "Nonreportable Positions-Long (Old)",
    "nonrept_short": "Nonreportable Positions-Short (Old)",
}


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


def market_records(raw: pd.DataFrame, cftc_name: "str | list[str]") -> pd.DataFrame:
    """Return the six raw long/short series for one market, indexed by report
    date (ascending, de-duplicated).

    Mirrors get_market_data() in pages/2_COT_Analysis.py: OR substring match over
    one or more name variants (regex=False), parse the as-of date, drop duplicate
    dates (earliest name wins). Returns an empty DataFrame when the market or the
    required columns are absent.
    """
    if _NAME_COL not in raw.columns:
        return pd.DataFrame()

    names = [cftc_name] if isinstance(cftc_name, str) else cftc_name
    mask = pd.Series(False, index=raw.index)
    for n in names:
        mask |= raw[_NAME_COL].str.upper().str.contains(n.upper(), regex=False, na=False)
    df = raw[mask].copy()
    if df.empty or _DATE_COL not in df.columns:
        return pd.DataFrame()

    df["Date"] = pd.to_datetime(df[_DATE_COL], errors="coerce")
    df = (
        df.dropna(subset=["Date"])
        .sort_values("Date")
        .drop_duplicates(subset=["Date"], keep="first")  # transition-year overlaps
        .set_index("Date")
    )

    out = pd.DataFrame(index=df.index)
    for key, src_col in _COT_COLS.items():
        if src_col in df.columns:
            out[key] = pd.to_numeric(df[src_col], errors="coerce")
    return out.dropna(how="all")


def _to_int(value) -> "int | None":
    """Round a numeric cell to int; None when missing (keeps NULLs out of the DB)."""
    if value is None or pd.isna(value):
        return None
    return int(round(float(value)))


def collect_rows(raw: pd.DataFrame) -> tuple[list[dict], list[dict]]:
    """Build Supabase row dicts for every market x report date.

    Returns (rows, summary) where summary holds one entry per written market for
    the run report (category, week count, latest date, example value).
    """
    rows: list[dict] = []
    summary: list[dict] = []
    for category, markets in MARKET_GROUPS.items():
        for market, cftc_name in markets.items():
            recs = market_records(raw, cftc_name)
            if recs.empty:
                print(f"  skip  {market} ({category}): market not found")
                continue

            for when, rec in recs.iterrows():
                row = {
                    "market": market,
                    "category": category,
                    "report_date": when.date().isoformat(),
                    "source": SOURCE,
                }
                for key in _COT_COLS:
                    row[key] = _to_int(rec.get(key))
                rows.append(row)

            latest = recs.index[-1]
            summary.append({
                "market": market,
                "category": category,
                "weeks": len(recs),
                "latest": latest.date().isoformat(),
                "comm_long": _to_int(recs.iloc[-1].get("comm_long")),
            })
            print(f"  ok    {market:14s} ({category:11s}): {len(recs):>4} weeks (latest {latest.date()})")
    return rows, summary


def upsert_rows(client, rows: list[dict]) -> int:
    """Upsert rows into cot_data in chunks, deduping on (market, report_date)."""
    written = 0
    for start in range(0, len(rows), UPSERT_CHUNK):
        chunk = rows[start:start + UPSERT_CHUNK]
        client.table("cot_data").upsert(chunk, on_conflict="market,report_date").execute()
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

    rows, summary = collect_rows(raw)
    if not rows:
        sys.exit("ERROR: no COT rows built — nothing to write.")

    print(f"Upserting {len(rows)} rows into cot_data...")
    written = upsert_rows(client, rows)
    print(f"Done: upserted {written} rows (source={SOURCE}).")

    # ── Run report ────────────────────────────────────────────────────────────
    print(f"\nMarkets written: {len(summary)} of {sum(len(m) for m in MARKET_GROUPS.values())}")
    for s in summary:
        print(f"  {s['category']:11s} {s['market']:14s} latest {s['latest']} "
              f"(comm_long={s['comm_long']})")


if __name__ == "__main__":
    main()
