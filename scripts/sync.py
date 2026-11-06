#!/usr/bin/env python3
"""Sync training data from every configured source into data/sync-cache.json.

Sources are listed in .env, highest priority first:
  DATA_SOURCES=garmin                 # Garmin watch
  DATA_SOURCES=apple_health,strava    # Apple Watch wellness + Strava activities
  DATA_SOURCES=files                  # FIT/GPX/TCX files dropped into data/inbox/files/

Usage:
  python scripts/sync.py                          # all sources, last 7 days
  python scripts/sync.py --days 30
  python scripts/sync.py --start 2025-01-01       # backfill from a date
  python scripts/sync.py --source garmin --with-fit
  python scripts/sync.py --source garmin --backfill --start 2025-01-01
  python scripts/sync.py --source apple_health --file ~/Downloads/export.zip
  python scripts/sync.py --source strava --auth   # one-time Strava OAuth
  python scripts/sync.py --cloud                  # only sources that can run unattended (bot host)
  python scripts/sync.py --status                 # what's configured, last sync per source

Exit codes: 0 ok (including "nothing configured yet"), 1 a source failed,
2 a source needs the human to re-authenticate.

After a sync, new activities are printed so the agent can log them and the
published pages (artifacts/) are rebuilt by the Claude Code hook.
"""
from __future__ import annotations

import argparse
import datetime as dt
import importlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import datastore  # noqa: E402
from datastore import ProviderAuthError, ProviderNotConfigured  # noqa: E402

PROVIDERS = ("garmin", "apple_health", "strava", "files")
FILE_BASED = {"apple_health", "files"}  # their input files define the history, not --days


def _provider(name: str):
    if name not in PROVIDERS:
        raise SystemExit(f"Unknown source '{name}'. Known: {', '.join(PROVIDERS)}")
    return importlib.import_module(f"providers.{name}")


def status() -> int:
    sources = datastore.configured_sources()
    cache = datastore.load_cache()
    print(f"DATA_SOURCES = {', '.join(sources) if sources else '(none — run /setup or edit .env)'}")
    print(f"merged cache = {datastore.CACHE.relative_to(datastore.ROOT)}: "
          f"{len(cache['activities'])} activities, {len(cache['wellness'])} wellness days, "
          f"last merged {cache.get('synced_at') or 'never'}")
    for s in sorted(set(sources) | set(cache.get("sources", {}))):
        info = cache.get("sources", {}).get(s, {})
        print(f"  {s:<13} last sync {info.get('last_sync') or 'never':<20} "
              f"{info.get('activities', 0)} activities, {info.get('wellness_days', 0)} days")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", help="sync just this source (default: all in DATA_SOURCES)")
    ap.add_argument("--days", type=int, help="look back N days (default 7; file sources default to all)")
    ap.add_argument("--start", help="start date YYYY-MM-DD (overrides --days)")
    ap.add_argument("--file", help="apple_health/files: read this file or folder instead of the inbox")
    ap.add_argument("--with-details", action="store_true", help="garmin: save per-second streams")
    ap.add_argument("--with-fit", action="store_true", help="garmin: save original FIT files")
    ap.add_argument("--backfill", action="store_true", help="garmin: details + FIT + raw wellness")
    ap.add_argument("--cloud", action="store_true", help="skip sources that need local files")
    ap.add_argument("--auth", action="store_true", help="strava: run the one-time OAuth flow")
    ap.add_argument("--code", help="strava: authorization code from the redirect URL")
    ap.add_argument("--activity-id", help="garmin: dump one activity's raw detail JSON")
    ap.add_argument("--status", action="store_true", help="show configuration and last syncs")
    ap.add_argument("--json", action="store_true", help="print new activities as JSON")
    args = ap.parse_args()

    datastore.load_env()
    if args.status:
        return status()

    if args.auth:
        _provider(args.source or "strava").auth(args.code)
        return 0
    if args.activity_id:
        print(json.dumps(_provider("garmin").dump_activity(args.activity_id), indent=2, default=str))
        return 0

    sources = [args.source] if args.source else datastore.configured_sources()
    if not sources:
        print("No data sources configured. Set DATA_SOURCES in .env (see docs/data-sources.md) "
              "or run /setup. Manual logging still works without one.")
        return 0

    end = dt.date.today()
    exit_code = 0
    new_acts: list[dict] = []
    for name in sources:
        mod = _provider(name)
        if args.cloud and not getattr(mod, "CLOUD_SAFE", False):
            print(f"[{name}] skipped (needs local files; not cloud-safe)")
            continue
        if args.start:
            start = dt.date.fromisoformat(args.start)
        elif args.days is not None:
            start = end - dt.timedelta(days=args.days)
        elif name in FILE_BASED:
            start = dt.date(2000, 1, 1)
        else:
            start = end - dt.timedelta(days=7)
        print(f"[{name}] {start} -> {end}")
        try:
            acts, days = mod.fetch(start, end, args)
        except ProviderNotConfigured as e:
            print(f"[{name}] not configured: {e}")
            continue
        except ProviderAuthError as e:
            print(f"[{name}] AUTH FAILURE: {e}", file=sys.stderr)
            exit_code = 2
            continue
        except Exception as e:
            print(f"[{name}] FAILED: {e}", file=sys.stderr)
            exit_code = max(exit_code, 1)
            continue
        n_a, n_d, new = datastore.save_source(name, acts, days)
        new_acts += new
        print(f"[{name}] {n_a} activities ({len(new)} new), {n_d} wellness days")

    cache = datastore.rebuild_cache(datastore.configured_sources())
    print(f"merged -> {datastore.CACHE.relative_to(datastore.ROOT)}: "
          f"{len(cache['activities'])} activities, {len(cache['wellness'])} wellness days")

    if args.json:
        print(json.dumps(new_acts, indent=2))
    elif new_acts:
        print("\nNEW ACTIVITIES (not seen before — log these):")
        for a in sorted(new_acts, key=lambda x: x.get("start_local") or ""):
            bits = [a["start_local"][:16].replace("T", " "), a["type"]]
            if a.get("distance_km"):
                bits.append(f"{a['distance_km']} km")
            if a.get("duration_min"):
                bits.append(f"{round(a['duration_min'])} min")
            if a.get("avg_pace_per_km"):
                bits.append(f"@ {a['avg_pace_per_km']}")
            if a.get("avg_hr"):
                bits.append(f"HR {round(a['avg_hr'])}")
            print("  - " + " | ".join(bits) + f"  [{a['source']}:{a['id']}]")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
