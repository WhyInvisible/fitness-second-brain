#!/usr/bin/env python3
"""Read-only reports over already-synced training data (any provider).

Does NOT call any API — reads data/sync-cache.json, which scripts/sync.py
maintains for Garmin, Apple Health, Strava or file imports alike.

Modes:
  python scripts/report.py                       # weekly digest (last completed week)
  python scripts/report.py --current-week        # this week so far
  python scripts/report.py --weeks 4             # last 4 weeks summary
  python scripts/report.py --month 2026-04       # one month's training
  python scripts/report.py --archive             # full-history summary

Output is markdown, suitable for pasting into a log or weekly review.
Add --json for machine-readable output.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import datastore  # noqa: E402



# ---------- loaders ----------

def load_cache() -> dict:
    if not datastore.CACHE.exists():
        print("No data/sync-cache.json yet — run scripts/sync.py first", file=sys.stderr)
        sys.exit(1)
    return datastore.load_cache()


# ---------- filtering ----------

def in_range(item_date: str, start: dt.date, end: dt.date) -> bool:
    try:
        d = dt.date.fromisoformat(item_date[:10])
    except (ValueError, TypeError):
        return False
    return start <= d <= end


def activities_in(cache: dict, start: dt.date, end: dt.date) -> list[dict]:
    out = []
    for a in cache.get("activities", []):
        sl = a.get("start_local") or ""
        if in_range(sl, start, end):
            out.append(a)
    return sorted(out, key=lambda x: x.get("start_local") or "")


def wellness_in(items: Iterable[dict], start: dt.date, end: dt.date) -> list[dict]:
    return sorted(
        [w for w in items if in_range(w.get("date", ""), start, end)],
        key=lambda x: x.get("date", ""),
    )


# ---------- aggregations ----------

def sum_distance_km(acts: list[dict], type_filter: str | None = None) -> float:
    return round(sum(
        (a.get("distance_km") or 0)
        for a in acts
        if type_filter is None or a.get("type") == type_filter
    ), 1)


def sum_duration_min(acts: list[dict], type_filter: str | None = None) -> float:
    return round(sum(
        (a.get("duration_min") or 0)
        for a in acts
        if type_filter is None or a.get("type") == type_filter
    ), 0)


def by_type(acts: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    for a in acts:
        out[a.get("type") or "unknown"].append(a)
    return out


def avg(vals: list, ignore_zero: bool = False) -> float | None:
    """Mean of non-None values. If ignore_zero, also drop zeros (used for sleep / HRV
    where some devices record 0 when the night wasn't tracked)."""
    vals = [v for v in vals if v is not None and (not ignore_zero or v != 0)]
    return round(sum(vals) / len(vals), 1) if vals else None


def stats_block(wellness: list[dict]) -> dict:
    sleep_avg_min = avg([w.get("sleep_total_min") for w in wellness], ignore_zero=True)
    steps_avg = avg([w.get("steps") for w in wellness], ignore_zero=True)
    return {
        "days_with_data": len(wellness),
        "avg_rhr": avg([w.get("resting_hr") for w in wellness], ignore_zero=True),
        "avg_hrv_ms": avg([w.get("hrv_last_night_ms") for w in wellness], ignore_zero=True),
        "avg_sleep_h": round(sleep_avg_min / 60, 2) if sleep_avg_min else None,
        "avg_sleep_score": avg([w.get("sleep_score") for w in wellness], ignore_zero=True),
        "avg_steps": int(steps_avg) if steps_avg else None,
        "avg_stress": avg([w.get("stress_avg") for w in wellness], ignore_zero=True),
    }


# ---------- output formatters ----------

def fmt_activity_line(a: dict) -> str:
    parts = [a.get("start_local", "?")[:16].replace("T", " ")]
    parts.append(a.get("type") or "?")
    if a.get("distance_km"):
        parts.append(f"{a['distance_km']} km")
    if a.get("duration_min"):
        m = int(a["duration_min"])
        parts.append(f"{m//60}h{m%60:02d}" if m >= 60 else f"{m} min")
    if a.get("avg_pace_per_km"):
        parts.append(f"@ {a['avg_pace_per_km']}")
    if a.get("avg_hr"):
        parts.append(f"HR {int(a['avg_hr'])}/{int(a.get('max_hr') or 0) or '?'}")
    if a.get("training_load"):
        parts.append(f"load {round(a['training_load'])}")
    return "- " + " | ".join(parts)


def fmt_weekly(start: dt.date, end: dt.date, acts: list[dict], wellness: list[dict]) -> str:
    lines = [f"## Training week: {start} -- {end} ({(end - start).days + 1} days)", ""]

    by_t = by_type(acts)
    lines.append(f"**Volume:** {len(acts)} sessions, "
                 f"running {sum_distance_km(acts, 'running')} km "
                 f"({sum_duration_min(acts, 'running'):.0f} min), "
                 f"all activities {sum_duration_min(acts):.0f} min")
    if by_t:
        breakdown = ", ".join(f"{t} {len(v)}" for t, v in sorted(by_t.items()))
        lines.append(f"**By type:** {breakdown}")
    lines.append("")

    if acts:
        lines.append("**Sessions:**")
        for a in acts:
            lines.append(fmt_activity_line(a))
        lines.append("")

    if wellness:
        s = stats_block(wellness)
        bits = []
        if s["avg_rhr"]: bits.append(f"RHR {s['avg_rhr']} bpm")
        if s["avg_hrv_ms"]: bits.append(f"HRV {s['avg_hrv_ms']} ms")
        if s["avg_sleep_h"]: bits.append(f"sleep {s['avg_sleep_h']}h"
                                          + (f" (score {s['avg_sleep_score']})" if s["avg_sleep_score"] else ""))
        if s["avg_steps"]: bits.append(f"{s['avg_steps']:,} steps/day")
        if s["avg_stress"]: bits.append(f"stress {s['avg_stress']}")
        lines.append(f"**Wellness averages ({s['days_with_data']}d):** " + " | ".join(bits))
        lines.append("")

        # Day-by-day RHR/HRV/sleep
        lines.append("**Daily wellness:**")
        lines.append("| Date | RHR | HRV | Sleep | Score | BB lo-hi |")
        lines.append("|---|---|---|---|---|---|")
        for w in wellness:
            rhr = w.get("resting_hr") or ""
            hrv = w.get("hrv_last_night_ms") or ""
            sleep = f"{w['sleep_total_min']/60:.1f}h" if w.get("sleep_total_min") else ""
            score = w.get("sleep_score") or ""
            bb = (f"{w['body_battery_low']}-{w['body_battery_high']}"
                  if w.get("body_battery_low") and w.get("body_battery_high") else "")
            lines.append(f"| {w['date']} | {rhr} | {hrv} | {sleep} | {score} | {bb} |")
        lines.append("")

    return "\n".join(lines)


def fmt_monthly(year_month: str, acts: list[dict], wellness: list[dict]) -> str:
    lines = [f"## Training month: {year_month}", ""]

    by_t = by_type(acts)
    lines.append(f"**Total:** {len(acts)} sessions, "
                 f"running {sum_distance_km(acts, 'running')} km, "
                 f"all activities {sum_duration_min(acts):.0f} min")
    if by_t:
        for t, v in sorted(by_t.items()):
            km = sum_distance_km(v, t)
            mins = sum_duration_min(v, t)
            lines.append(f"- **{t}**: {len(v)} sessions |{km} km |{mins:.0f} min")
    lines.append("")

    if wellness:
        s = stats_block(wellness)
        bits = []
        if s["avg_rhr"]: bits.append(f"RHR {s['avg_rhr']}")
        if s["avg_hrv_ms"]: bits.append(f"HRV {s['avg_hrv_ms']} ms")
        if s["avg_sleep_h"]: bits.append(f"sleep {s['avg_sleep_h']}h")
        if s["avg_sleep_score"]: bits.append(f"score {s['avg_sleep_score']}")
        lines.append(f"**Wellness avg ({s['days_with_data']}d):** " + " | ".join(bits))
        lines.append("")

    return "\n".join(lines)


def fmt_archive(cache: dict, wellness: list[dict]) -> str:
    acts = cache.get("activities", [])
    if not acts and not wellness:
        return "No data in cache or archive."

    # Date range
    act_dates = [a.get("start_local", "")[:10] for a in acts if a.get("start_local")]
    well_dates = [w["date"] for w in wellness if w.get("date")]
    all_dates = sorted(d for d in act_dates + well_dates if d)
    first = all_dates[0] if all_dates else "?"
    last = all_dates[-1] if all_dates else "?"

    sources = ", ".join(f"{k} (last sync {v.get('last_sync')})"
                        for k, v in cache.get("sources", {}).items()) or "none"
    lines = [
        "## Archive summary",
        "",
        f"**Date range:** {first} -- {last}",
        f"**Activities (in cache):** {len(acts)}",
        f"**Wellness days:** {len(wellness)}",
        f"**Sources:** {sources}",
        "",
        "### Monthly volume",
        "",
        "| Month | Sessions | Run km | Total min |",
        "|---|---|---|---|",
    ]
    by_month: dict[str, list[dict]] = defaultdict(list)
    for a in acts:
        sl = a.get("start_local") or ""
        if len(sl) >= 7:
            by_month[sl[:7]].append(a)
    for ym in sorted(by_month.keys()):
        ms = by_month[ym]
        lines.append(f"| {ym} | {len(ms)} | {sum_distance_km(ms, 'running')} | {sum_duration_min(ms):.0f} |")
    lines.append("")

    # Type breakdown
    by_t = by_type(acts)
    if by_t:
        lines.append("### Activity types (all-time)")
        lines.append("")
        lines.append("| Type | Count | km | Total min |")
        lines.append("|---|---|---|---|")
        for t, v in sorted(by_t.items(), key=lambda x: -len(x[1])):
            lines.append(f"| {t} | {len(v)} | {sum_distance_km(v, t)} | {sum_duration_min(v, t):.0f} |")
        lines.append("")

    if wellness:
        s = stats_block(wellness)
        lines.append("### Wellness (all archived days)")
        lines.append("")
        bits = []
        if s["avg_rhr"]: bits.append(f"avg RHR {s['avg_rhr']} bpm")
        if s["avg_hrv_ms"]: bits.append(f"avg HRV {s['avg_hrv_ms']} ms")
        if s["avg_sleep_h"]: bits.append(f"avg sleep {s['avg_sleep_h']}h")
        lines.append(" | ".join(bits))
        lines.append("")

    return "\n".join(lines)


# ---------- main ----------

def last_completed_week() -> tuple[dt.date, dt.date]:
    """Return Mon-Sun of the most recently completed week. If today is Mon, return last week."""
    today = dt.date.today()
    # Most recent Sunday on or before today
    days_since_sun = (today.weekday() + 1) % 7  # Mon=0 -> 1, Sun=6 -> 0
    last_sun = today - dt.timedelta(days=days_since_sun)
    last_mon = last_sun - dt.timedelta(days=6)
    return last_mon, last_sun


def current_week() -> tuple[dt.date, dt.date]:
    today = dt.date.today()
    mon = today - dt.timedelta(days=today.weekday())
    sun = mon + dt.timedelta(days=6)
    return mon, sun


def main() -> int:
    ap = argparse.ArgumentParser(description="Reports over synced training data (no API calls)")
    ap.add_argument("--weeks", type=int, help="Last N weeks (e.g. --weeks 4)")
    ap.add_argument("--month", help="Specific month YYYY-MM")
    ap.add_argument("--archive", action="store_true", help="Full archive summary")
    ap.add_argument("--current-week", action="store_true",
                    help="Use current week instead of last completed week")
    ap.add_argument("--json", action="store_true", help="JSON output instead of markdown")
    args = ap.parse_args()

    cache = load_cache()
    wellness_all = cache.get("wellness", [])
    # Wellness from cache (most recent sync) takes precedence over archive duplicates
    cache_wellness_by_date = {w["date"]: w for w in cache.get("wellness", []) if w.get("date")}
    well_by_date = {w["date"]: w for w in wellness_all}
    well_by_date.update(cache_wellness_by_date)
    wellness_all = sorted(well_by_date.values(), key=lambda x: x["date"])

    if args.archive:
        out = fmt_archive(cache, wellness_all)
        if args.json:
            print(json.dumps({"summary": out}, indent=2))
        else:
            print(out)
        return 0

    if args.month:
        try:
            year, month = map(int, args.month.split("-"))
        except ValueError:
            print(f"Invalid --month '{args.month}', expected YYYY-MM", file=sys.stderr)
            return 1
        start = dt.date(year, month, 1)
        end = (dt.date(year + (month == 12), (month % 12) + 1, 1) - dt.timedelta(days=1))
        acts = activities_in(cache, start, end)
        well = wellness_in(wellness_all, start, end)
        out = fmt_monthly(args.month, acts, well) if not args.json else json.dumps(
            {"month": args.month, "activities": acts, "wellness": well}, indent=2)
        print(out)
        return 0

    # Weekly digest (default)
    if args.weeks:
        end = current_week()[1] if args.current_week else last_completed_week()[1]
        start = end - dt.timedelta(days=7 * args.weeks - 1)
    elif args.current_week:
        start, end = current_week()
    else:
        start, end = last_completed_week()

    acts = activities_in(cache, start, end)
    well = wellness_in(wellness_all, start, end)
    out = fmt_weekly(start, end, acts, well) if not args.json else json.dumps(
        {"start": start.isoformat(), "end": end.isoformat(),
         "activities": acts, "wellness": well}, indent=2, default=str)
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
