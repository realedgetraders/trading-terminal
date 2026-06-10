#!/usr/bin/env python3
"""Fetch CFTC Commitments-of-Traders positioning and upsert it into Supabase.

Source: the CFTC Legacy COT history files (deacot{YEAR}.zip) published at
https://www.cftc.gov/files/dea/history/ — free, no API key. The market universe,
substring-match logic and "(Old)" futures-only columns are reused 1:1 from the
Streamlit COT module (pages/2_COT_Analysis.py), with no Streamlit/UI code.

Coverage: every asset with modules.cot in the canonical asset feed (/api/assets,
loaded via _assets_feed) — currently the 19 markets across 4 categories (Forex,
Commodities, Indices, Bonds). Each asset carries its CFTC match strings
(cot.match, incl. rename variants) and exclude tokens (cot.exclude); the match /
"(Old)" futures-only logic is unchanged. For every (market, report_date) the RAW
long/short contracts of all three trader categories are written — futures-only
("(Old)" columns):
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

from _assets_feed import load_assets, with_module
from _incremental import latest_dates, resolve_mode

SOURCE = "cftc"
START_YEAR = 2001          # full Legacy COT history (deacot2001.zip onward)
REQUEST_TIMEOUT = 30       # seconds per CFTC request
UPSERT_CHUNK = 500         # rows per Supabase upsert call

# Feed category -> the cot_data `category` label the web app's screener groups by
# (lib/cot.ts MARKET_GROUPS keys). Preserves the existing 4 display categories.
COT_CATEGORY_DISPLAY = {
    "fx": "Forex",
    "commodity": "Commodities",
    "index": "Indices",
    "rate": "Bonds",
}


def build_market_groups(assets: list[dict]) -> dict[str, dict[str, dict]]:
    """display_category -> {market_name -> {"match": [...], "exclude": [...]}}.

    Built from every asset with modules.cot: `cotMarketName` is the market name
    written to cot_data, `cot.match` the CFTC "Market and Exchange Names"
    substrings (incl. rename variants), `cot.exclude` the look-alike tokens
    (MICRO/ULTRA). Feed-driven — no hardcoded market list.
    """
    groups: dict[str, dict[str, dict]] = {}
    for asset in with_module(assets, "cot"):
        cot = asset.get("cot") or {}
        market = asset.get("cotMarketName")
        match = cot.get("match")
        if not market or not match:
            print(f"  skip  {asset.get('symbol')}: cot capability without "
                  f"cotMarketName/match in feed")
            continue
        category = COT_CATEGORY_DISPLAY.get(asset["category"], asset["category"])
        groups.setdefault(category, {})[market] = {
            "match": match,
            "exclude": cot.get("exclude", []),
        }
    return groups

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


def market_records(raw: pd.DataFrame, names: list[str], exclude: list[str]) -> pd.DataFrame:
    """Return the six raw long/short series for one market, indexed by report
    date (ascending, de-duplicated).

    Mirrors get_market_data() in pages/2_COT_Analysis.py: OR substring match over
    one or more name variants (regex=False), drop look-alike rows whose name
    contains an `exclude` token (MICRO/ULTRA), parse the as-of date, drop
    duplicate dates (earliest name wins). Returns an empty DataFrame when the
    market or the required columns are absent.
    """
    if _NAME_COL not in raw.columns:
        return pd.DataFrame()

    upper = raw[_NAME_COL].str.upper()
    mask = pd.Series(False, index=raw.index)
    for n in names:
        mask |= upper.str.contains(n.upper(), regex=False, na=False)
    for tok in exclude:  # drop MICRO/ULTRA look-alikes that share a base name
        mask &= ~upper.str.contains(tok.upper(), regex=False, na=False)
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


def collect_rows(raw: pd.DataFrame, groups: dict[str, dict[str, dict]]) -> tuple[list[dict], list[dict]]:
    """Build Supabase row dicts for every market x report date.

    Returns (rows, summary) where summary holds one entry per written market for
    the run report (category, week count, latest date, example value).
    """
    rows: list[dict] = []
    summary: list[dict] = []
    for category, markets in groups.items():
        for market, spec in markets.items():
            recs = market_records(raw, spec["match"], spec["exclude"])
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

    groups = build_market_groups(load_assets())
    market_count = sum(len(m) for m in groups.values())
    if not market_count:
        sys.exit("ERROR: no COT markets in the asset feed — nothing to write.")

    # Mode: backfill downloads every yearly zip from 2001; an incremental run only
    # needs the CURRENT year's zip (weekly cadence, idempotent upsert) — plus the
    # prior year's in January, when late-December reports are still landing. Full
    # multi-year backfill happens only when cot_data holds no data yet (auto), or
    # when forced (--mode backfill).
    mode = resolve_mode()
    markets = [m for cat in groups.values() for m in cat]
    latest = {} if mode == "backfill" else latest_dates(
        client, "cot_data", "report_date", "market", markets)
    table_empty = not any(latest.values())
    do_backfill = mode == "backfill" or (mode == "auto" and table_empty)

    current_year = datetime.now().year
    if do_backfill:
        fetch_year = START_YEAR
        print(f"[mode={mode}] backfill — CFTC COT deacot{START_YEAR}..{current_year} "
              f"for {market_count} markets...")
    else:
        fetch_year = current_year - 1 if datetime.now().month == 1 else current_year
        print(f"[mode={mode}] incremental — CFTC COT deacot{fetch_year}..{current_year} "
              f"for {market_count} markets...")
    raw = fetch_cot_raw(fetch_year)
    if raw.empty:
        sys.exit("ERROR: no COT data fetched from CFTC — nothing to write.")
    if _NAME_COL not in raw.columns:
        sys.exit(f"ERROR: unexpected CFTC schema (missing '{_NAME_COL}' column).")

    rows, summary = collect_rows(raw, groups)
    if not rows:
        sys.exit("ERROR: no COT rows built — nothing to write.")

    print(f"Upserting {len(rows)} rows into cot_data...")
    written = upsert_rows(client, rows)
    print(f"Done: upserted {written} rows (source={SOURCE}).")

    # ── Run report ────────────────────────────────────────────────────────────
    print(f"\nMarkets written: {len(summary)} of {market_count}")
    for s in summary:
        print(f"  {s['category']:11s} {s['market']:14s} latest {s['latest']} "
              f"(comm_long={s['comm_long']})")


if __name__ == "__main__":
    main()
