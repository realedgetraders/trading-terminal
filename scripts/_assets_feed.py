#!/usr/bin/env python3
"""Shared loader for the canonical asset registry feed.

The Next.js app (edgelabweb) publishes lib/assets.ts as JSON at /api/assets. The
three price collectors consume that feed as their single source of truth instead
of hardcoding their own lists, so the registry stays the one place an asset is
defined.

Resilience: every good response is cached to ``scripts/.assets_cache.json``. On a
network failure the last good cache is used; if neither the network nor a cache
is available the caller fails loudly (so a collector never runs on no data).

Environment:
  ASSETS_URL  Override the feed URL (default: the deployed edgelabweb feed).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import requests

DEFAULT_URL = "https://edgelabweb.vercel.app/api/assets"
CACHE_PATH = Path(__file__).with_name(".assets_cache.json")
REQUEST_TIMEOUT = 30  # seconds


def load_assets(url: str | None = None) -> list[dict]:
    """Return the asset list from the feed, falling back to the local cache.

    On success the response is cached. On any network/parse error the last good
    cache is returned; if no cache exists the process exits with an error.
    """
    url = url or os.environ.get("ASSETS_URL", DEFAULT_URL)
    try:
        resp = requests.get(url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, list) or not data:
            raise ValueError("feed did not return a non-empty JSON array")
        CACHE_PATH.write_text(json.dumps(data))
        print(f"assets feed: {len(data)} assets from {url}")
        return data
    except Exception as exc:  # network / HTTP / parse — fall back to cache
        if CACHE_PATH.exists():
            data = json.loads(CACHE_PATH.read_text())
            print(f"assets feed: fetch failed ({exc}); using cache "
                  f"{CACHE_PATH.name} ({len(data)} assets)")
            return data
        sys.exit(f"ERROR: could not fetch asset feed from {url} ({exc}) and no "
                 f"cache at {CACHE_PATH} — refusing to run on no data.")


def with_module(assets: list[dict], flag: str) -> list[dict]:
    """Assets whose ``modules.<flag>`` capability is true, in feed order."""
    return [a for a in assets if a.get("modules", {}).get(flag)]
