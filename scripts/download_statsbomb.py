#!/usr/bin/env python3
"""Reproducible downloader for StatsBomb Open Data — FIFA World Cup 2022.

Acquires the raw event + lineup JSON consumed by statsbomb_parser.py into
``data/statsbomb/`` (gitignored). Source: github.com/statsbomb/open-data.

- competition_id: 43 (FIFA World Cup), season_id: 106 (2022) -> 64 matches
- downloads ``matches/43/106.json``, ``events/<match_id>.json`` and
  ``lineups/<match_id>.json``, mirroring the upstream repo layout
- idempotent: existing non-empty files are skipped unless ``--force``

This script ONLY acquires raw data — no parsing or business logic lives here.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import requests

BASE_URL = "https://raw.githubusercontent.com/statsbomb/open-data/master/data/"
COMPETITION_ID = 43  # FIFA World Cup
SEASON_ID = 106  # 2022
EXPECTED_MATCH_COUNT = 64
MATCHES_URL = f"{BASE_URL}matches/{COMPETITION_ID}/{SEASON_ID}.json"


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def download(url: str, path: Path, *, force: bool) -> bool:
    """Fetch ``url`` to ``path``; returns True if a file was written.

    Skips (returns False) when the target already exists non-empty unless
    ``force`` is set.
    """
    if not force and path.exists() and path.stat().st_size > 0:
        return False
    resp = requests.get(url, timeout=120)
    resp.raise_for_status()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(resp.text, encoding="utf-8")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download StatsBomb Open Data (World Cup 2022) raw JSON.")
    parser.add_argument("--force", action="store_true",
                        help="re-download files that already exist")
    parser.add_argument("--data-dir", type=Path, default=None,
                        help="output directory (default: <repo>/data/statsbomb)")
    args = parser.parse_args()

    data_dir = args.data_dir or (repo_root() / "data" / "statsbomb")

    # 1. Match list (source of the 64 match IDs)
    matches_path = (data_dir / "matches" / str(COMPETITION_ID)
                    / f"{SEASON_ID}.json")
    downloaded = download(MATCHES_URL, matches_path, force=args.force)
    matches = json.loads(matches_path.read_text(encoding="utf-8"))
    match_ids = sorted(m["match_id"] for m in matches)
    if len(match_ids) != EXPECTED_MATCH_COUNT:
        print(f"WARNING: expected {EXPECTED_MATCH_COUNT} matches for "
              f"comp {COMPETITION_ID}/season {SEASON_ID}, "
              f"found {len(match_ids)}", file=sys.stderr)
    print(f"matches: {len(match_ids)} match_ids "
          f"({'downloaded' if downloaded else 'cached'})")

    # 2. Events + lineups per match (idempotent)
    n_downloaded = n_skipped = 0
    for match_id in match_ids:
        for kind, suffix in (("events", "events"), ("lineups", "lineups")):
            url = f"{BASE_URL}{suffix}/{match_id}.json"
            path = data_dir / kind / f"{match_id}.json"
            if download(url, path, force=args.force):
                n_downloaded += 1
            else:
                n_skipped += 1

    print(f"events+lineups: {n_downloaded} downloaded, "
          f"{n_skipped} skipped (cached)")
    print(f"data dir: {data_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
