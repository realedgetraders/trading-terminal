#!/usr/bin/env python3
"""Shared incremental / backfill mode helpers for the Supabase collectors.

Adds a fetch *mode* so scheduled runs only pull the recent tail per series and
converge to complete, current data — while still full-backfilling any new or
empty series:

  auto         (default) per series: full backfill if it has no stored data,
               otherwise a tail fetch from (latest stored date − OVERLAP_DAYS).
  backfill     force full history for every series (re-seed).
  incremental  force tail-only for every series (never backfill, even if empty).

Mode resolution precedence: ``--mode <m>`` / ``--mode=<m>`` CLI flag, then the
``COLLECTOR_MODE`` env var, then the caller's default.

"Latest stored date" — why one indexed query per series, not one grouped query
--------------------------------------------------------------------------------
The brief asked for a single grouped ``max(date) GROUP BY key`` per table. That
is not available on this Supabase project:
  * PostgREST aggregate functions are disabled (PGRST123) — ``date.max()`` errors.
  * The large price tables (seasonality_prices, valuation_prices) have no
    standalone ``date`` index; any date-only filter/sort scans the whole table
    and hits the statement timeout. seasonality_prices also holds a much larger
    foreign symbol universe than this collector writes, so a windowed scan would
    return mostly unrelated rows.
The one access path that is fast on every table is the ``(key, date)`` composite
index that backs each upsert conflict target: ``WHERE key=<v> ORDER BY date DESC
LIMIT 1`` returns in ~0.1 s. With ≤ ~56 series per table that is a few seconds —
negligible next to a multi-minute full backfill, and it never times out.
"""
from __future__ import annotations

import os
import sys
import time
from datetime import date, timedelta

MODES = ("auto", "backfill", "incremental")

# Calendar-day overlap re-fetched before the latest stored date. Self-heals the
# recent tail (late prints, revisions) without pulling meaningful history.
OVERLAP_DAYS = 5


def resolve_mode(default: str = "auto") -> str:
    """Return the run mode from --mode CLI flag, COLLECTOR_MODE env, or default."""
    mode: str | None = None
    argv = sys.argv[1:]
    for i, arg in enumerate(argv):
        if arg == "--mode" and i + 1 < len(argv):
            mode = argv[i + 1]
        elif arg.startswith("--mode="):
            mode = arg.split("=", 1)[1]
    if mode is None:
        mode = os.environ.get("COLLECTOR_MODE")
    if mode is None:
        mode = default
    mode = mode.lower()
    if mode not in MODES:
        sys.exit(f"ERROR: invalid mode '{mode}' (expected one of {', '.join(MODES)}).")
    return mode


_RETRY_SLEEP = 1  # seconds before the single retry of a transient lookup failure


def latest_date(client, table: str, date_col: str,
                filters: dict | None = None) -> date | None:
    """Most recent stored ``date_col`` for one series, or None if it has no rows.

    One indexed round-trip via the (key, date) composite index: equality on the
    series key columns + ORDER BY date DESC LIMIT 1. Never scans the whole table.

    Retried once on a transient API error: a collector probes one query per
    series, so over a large universe a single network/PostgREST blip would
    otherwise abort the whole run.
    """
    def _run():
        query = client.table(table).select(date_col)
        for col, val in (filters or {}).items():
            query = query.eq(col, val)
        return query.order(date_col, desc=True).limit(1).execute()

    try:
        resp = _run()
    except Exception:
        time.sleep(_RETRY_SLEEP)
        resp = _run()
    if not resp.data:
        return None
    return date.fromisoformat(resp.data[0][date_col])


def latest_dates(client, table: str, date_col: str, key_col: str,
                 keys: list[str]) -> dict[str, date | None]:
    """{key: latest stored date or None} for a list of single-column series keys."""
    return {
        key: latest_date(client, table, date_col, {key_col: key})
        for key in keys
    }


def is_backfill(mode: str, latest: date | None) -> bool:
    """Whether this series gets a full history pull this run."""
    return mode == "backfill" or (mode == "auto" and latest is None)


def fetch_start(mode: str, latest: date | None, backfill_start: date,
                today: date | None = None) -> date:
    """Start date for one series: ``backfill_start`` for a full pull, else a tail
    start = (latest or today) − OVERLAP_DAYS."""
    if is_backfill(mode, latest):
        return backfill_start
    anchor = latest if latest is not None else (today or date.today())
    return anchor - timedelta(days=OVERLAP_DAYS)
