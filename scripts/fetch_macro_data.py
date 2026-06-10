#!/usr/bin/env python3
"""Fetch core macro indicators from DBnomics and upsert them into Supabase.

Source: the DBnomics public API (https://api.db.nomics.world) — free, no API key.
DBnomics aggregates OECD, Eurostat, BIS and IMF series under one API, so every
series below is pulled through the same endpoint and tagged ``source = "dbnomics"``.

Coverage: 8 major FX currencies x 4 core indicators
  - CPI            (consumer prices, YoY %)
  - Interest Rate  (central-bank policy rate, %)
  - Unemployment   (harmonised unemployment rate, %)
  - GDP Growth     (real GDP, YoY %)

Rows are written to the ``macro_data`` table (columns: currency, indicator,
date, value, source) via upsert on the natural key (currency, indicator, date),
so re-runs never create duplicates. Missing or empty series are skipped
cleanly — one bad series never aborts the run.

This module is intentionally provider-agnostic at the plumbing layer: adding a
new provider later (e.g. PMI or forecast data) means writing one more
``collect_*`` function and appending its rows in ``main`` — the fetch/parse and
Supabase-load code stays untouched.

Required environment variables (never hardcode credentials):
  SUPABASE_URL         Supabase project URL
  SUPABASE_SECRET_KEY  Supabase secret (service) key

Run:
  python scripts/fetch_macro_data.py
"""
from __future__ import annotations

import math
import os
import sys
from datetime import date, timedelta

import requests
from supabase import create_client

from _incremental import fetch_start, is_backfill, latest_date, resolve_mode

DBNOMICS_API = "https://api.db.nomics.world/v22/series"
SOURCE = "dbnomics"
LOOKBACK_YEARS = 3          # keep >= 12 months of history per series
REQUEST_TIMEOUT = 30        # seconds per DBnomics request
UPSERT_CHUNK = 500          # rows per Supabase upsert call

CURRENCIES = ["USD", "EUR", "GBP", "JPY", "AUD", "NZD", "CAD", "CHF"]

# Each indicator maps a currency to a single DBnomics series reference of the
# form "PROVIDER/DATASET/SERIES_CODE". Monthly series are used where published;
# a quarterly series is used where the country reports no monthly figure
# (e.g. NZ CPI, NZ/CH unemployment, all GDP). Every reference below was
# verified to return data against the live DBnomics API.
INDICATORS = {
    # Consumer prices, all items, year-on-year % change.
    "CPI": {
        "USD": "OECD/DSD_PRICES@DF_PRICES_ALL/USA.M.N.CPI.PA._T.N.GY",
        "EUR": "OECD/DSD_PRICES@DF_PRICES_ALL/EA20.M.N.CPI.PA._T.N.GY",
        "GBP": "OECD/DSD_PRICES@DF_PRICES_ALL/GBR.M.N.CPI.PA._T.N.GY",
        "JPY": "IMF/IFS/M.JP.PCPI_PC_CP_A_PT",  # OECD JP national series is stale
        "AUD": "OECD/DSD_PRICES@DF_PRICES_ALL/AUS.M.N.CPI.PA._T.N.GY",
        "NZD": "OECD/DSD_PRICES@DF_PRICES_ALL/NZL.Q.N.CPI.PA._T.N.GY",  # NZ: quarterly only
        "CAD": "OECD/DSD_PRICES@DF_PRICES_ALL/CAN.M.N.CPI.PA._T.N.GY",
        "CHF": "OECD/DSD_PRICES@DF_PRICES_ALL/CHE.M.N.CPI.PA._T.N.GY",
    },
    # Central-bank policy rate, monthly (BIS).
    "Interest Rate": {
        "USD": "BIS/WS_CBPOL/M.US",
        "EUR": "BIS/WS_CBPOL/M.XM",
        "GBP": "BIS/WS_CBPOL/M.GB",
        "JPY": "BIS/WS_CBPOL/M.JP",
        "AUD": "BIS/WS_CBPOL/M.AU",
        "NZD": "BIS/WS_CBPOL/M.NZ",
        "CAD": "BIS/WS_CBPOL/M.CA",
        "CHF": "BIS/WS_CBPOL/M.CH",
    },
    # Harmonised unemployment rate, total persons 15+, seasonally adjusted.
    "Unemployment": {
        "USD": "OECD/DSD_LFS@DF_IALFS_UNE_M/USA.UNE_LF_M.PT_LF_SUB._Z.Y._T.Y_GE15._Z.M",
        "EUR": "Eurostat/une_rt_m/M.SA.TOTAL.PC_ACT.T.EA20",
        "GBP": "OECD/DSD_LFS@DF_IALFS_UNE_M/GBR.UNE_LF_M.PT_LF_SUB._Z.Y._T.Y_GE15._Z.M",
        "JPY": "OECD/DSD_LFS@DF_IALFS_UNE_M/JPN.UNE_LF_M.PT_LF_SUB._Z.Y._T.Y_GE15._Z.M",
        "AUD": "OECD/DSD_LFS@DF_IALFS_UNE_M/AUS.UNE_LF_M.PT_LF_SUB._Z.Y._T.Y_GE15._Z.M",
        "NZD": "OECD/DSD_LFS@DF_IALFS_UNE_M/NZL.UNE_LF_M.PT_LF_SUB._Z.Y._T.Y_GE15._Z.Q",  # NZ: quarterly
        "CAD": "OECD/DSD_LFS@DF_IALFS_UNE_M/CAN.UNE_LF_M.PT_LF_SUB._Z.Y._T.Y_GE15._Z.M",
        "CHF": "OECD/DSD_LFS@DF_IALFS_UNE_M/CHE.UNE_LF_M.PT_LF_SUB._Z.Y._T.Y_GE15._Z.Q",  # CH: quarterly
    },
    # Real GDP, year-on-year % change, quarterly (seasonally adjusted).
    "GDP Growth": {
        "USD": "OECD/DSD_NAMAIN1@DF_QNA/Q.Y.USA.S1.S1.B1GQ._Z._Z._Z.PC.L.GY.T0102",
        "EUR": "Eurostat/namq_10_gdp/Q.CLV_PCH_SM.SCA.B1GQ.EA20",
        "GBP": "OECD/DSD_NAMAIN1@DF_QNA/Q.Y.GBR.S1.S1.B1GQ._Z._Z._Z.PC.L.GY.T0102",
        "JPY": "OECD/DSD_NAMAIN1@DF_QNA/Q.Y.JPN.S1.S1.B1GQ._Z._Z._Z.PC.L.GY.T0102",
        "AUD": "OECD/DSD_NAMAIN1@DF_QNA/Q.Y.AUS.S1.S1.B1GQ._Z._Z._Z.PC.L.GY.T0102",
        "NZD": "OECD/DSD_NAMAIN1@DF_QNA/Q.Y.NZL.S1.S1.B1GQ._Z._Z._Z.PC.L.GY.T0102",
        "CAD": "OECD/DSD_NAMAIN1@DF_QNA/Q.Y.CAN.S1.S1.B1GQ._Z._Z._Z.PC.L.GY.T0102",
        "CHF": "OECD/DSD_NAMAIN1@DF_QNA/Q.Y.CHE.S1.S1.B1GQ._Z._Z._Z.PC.L.GY.T0102",
    },
}


def _require_env() -> tuple[str, str]:
    """Read Supabase credentials from the environment; exit if either is absent."""
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SECRET_KEY")
    if not url or not key:
        sys.exit("ERROR: SUPABASE_URL and SUPABASE_SECRET_KEY must be set in the environment.")
    return url, key


def _parse_period(period: str) -> date | None:
    """Convert a DBnomics period string to the first day of that period.

    Handles monthly ('2026-04'), quarterly ('2026-Q1'), annual ('2026') and
    daily ('2026-04-15') encodings. Returns None for anything unparseable.
    """
    try:
        if "Q" in period:
            year, quarter = period.split("-Q")
            return date(int(year), (int(quarter) - 1) * 3 + 1, 1)
        parts = period.split("-")
        if len(parts) == 1:
            return date(int(parts[0]), 1, 1)
        if len(parts) == 2:
            return date(int(parts[0]), int(parts[1]), 1)
        return date(int(parts[0]), int(parts[1]), int(parts[2]))
    except (ValueError, TypeError):
        return None


def fetch_series(ref: str) -> list[tuple[date, float]]:
    """Fetch one DBnomics series and return [(date, value), ...].

    Returns an empty list on any failure (network error, unknown series, empty
    payload, unparseable observations) so the caller can skip and continue.
    """
    try:
        resp = requests.get(f"{DBNOMICS_API}/{ref}", params={"observations": 1}, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        docs = resp.json().get("series", {}).get("docs", [])
    except (requests.RequestException, ValueError):
        return []
    if not docs:
        return []

    doc = docs[0]
    observations: list[tuple[date, float]] = []
    for period, raw in zip(doc.get("period", []), doc.get("value", [])):
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue  # DBnomics encodes missing observations as "NA"
        if math.isnan(value):
            continue
        when = _parse_period(period)
        if when is not None:
            observations.append((when, value))
    return observations


def collect_dbnomics_rows(series_cutoff) -> list[dict]:
    """Pull every configured DBnomics series and build Supabase row dicts.

    ``series_cutoff(indicator, currency)`` returns the per-series cutoff date —
    the backfill window for a full pull, or (latest stored − overlap) for a tail
    pull. DBnomics always returns the whole series; the cutoff bounds which
    observations are upserted. Series with no data at or after the cutoff are
    reported and skipped.
    """
    rows: list[dict] = []
    for indicator, currency_map in INDICATORS.items():
        for currency in CURRENCIES:
            ref = currency_map.get(currency)
            if not ref:
                print(f"  skip  {indicator:<13} {currency}: no series configured")
                continue

            cutoff = series_cutoff(indicator, currency)
            observations = [(d, v) for d, v in fetch_series(ref) if d >= cutoff]
            if not observations:
                print(f"  skip  {indicator:<13} {currency}: no data returned")
                continue

            for when, value in observations:
                rows.append({
                    "currency": currency,
                    "indicator": indicator,
                    "date": when.isoformat(),
                    "value": value,
                    "source": SOURCE,
                })
            latest = max(d for d, _ in observations)
            print(f"  ok    {indicator:<13} {currency}: {len(observations):>3} obs (latest {latest})")
    return rows


def upsert_rows(client, rows: list[dict]) -> int:
    """Upsert rows into macro_data in chunks, deduping on (currency, indicator, date)."""
    written = 0
    for start in range(0, len(rows), UPSERT_CHUNK):
        chunk = rows[start:start + UPSERT_CHUNK]
        client.table("macro_data").upsert(chunk, on_conflict="currency,indicator,date").execute()
        written += len(chunk)
    return written


def main() -> None:
    url, key = _require_env()
    client = create_client(url, key)
    backfill_cutoff = date.today() - timedelta(days=365 * LOOKBACK_YEARS + 31)

    # Per (currency, indicator) cutoff: full backfill window for an empty/forced
    # series, else (latest stored − overlap) so only the recent tail is re-upserted.
    mode = resolve_mode()
    series = [(ind, cur) for ind, cmap in INDICATORS.items()
              for cur in CURRENCIES if cmap.get(cur)]
    latest = {} if mode == "backfill" else {
        (ind, cur): latest_date(client, "macro_data", "date",
                                {"indicator": ind, "currency": cur})
        for ind, cur in series
    }
    n_bf = sum(is_backfill(mode, latest.get(s)) for s in series)
    print(f"[mode={mode}] macro data from DBnomics "
          f"({n_bf} backfill, {len(series) - n_bf} tail)...")

    def series_cutoff(indicator: str, currency: str) -> date:
        return fetch_start(mode, latest.get((indicator, currency)), backfill_cutoff)

    rows = collect_dbnomics_rows(series_cutoff)
    # Future providers (PMI, forecasts, ...) append their rows here, e.g.:
    #   rows += collect_pmi_rows(cutoff)

    if not rows:
        sys.exit("ERROR: no data fetched from any series — nothing to write.")

    print(f"Upserting {len(rows)} rows into macro_data...")
    written = upsert_rows(client, rows)
    print(f"Done: upserted {written} rows (source={SOURCE}).")


if __name__ == "__main__":
    main()
