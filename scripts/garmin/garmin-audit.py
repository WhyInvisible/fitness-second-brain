#!/usr/bin/env python3
"""Scan Garmin activity details for recording anomalies.

WHY THIS EXISTS
---------------
Watch recording faults silently corrupt analysis, for example:

  * a step-count glitch writing an impossible number of steps into one
    15-minute bucket, which truncates that night's sleep window and makes the
    morning's readiness numbers unusable;
  * a GPS acquisition error jumping the distance a few hundred metres in two
    seconds, inflating one kilometre's split and the whole run's average pace.

Left alone they get caught by chance, after a wrong conclusion. This finds them
deliberately. Needs per-second details: python scripts/sync.py --source garmin --with-details

Usage:
  python scripts/garmin/garmin-audit.py              # last 35 days
  python scripts/garmin/garmin-audit.py --days 90
  python scripts/garmin/garmin-audit.py --activity <id>
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import json
import os
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DETAILS = ROOT / "data" / "raw" / "garmin" / "details"
CACHE = ROOT / "data" / "sources" / "garmin.json"   # Garmin's own records, before cross-source merging

# Thresholds — tune the two marked ones to the athlete (see profile.md).
MAX_PLAUSIBLE_MS = 8.0          # 2:05/km sustained is a recording fault, not running
FAST_KM_SEC = 210               # TUNE: a split faster than this (3:30/km) is implausible for this athlete
HR_JUMP_BPM = 30                # bpm change within ~4 s = wrist-sensor artefact
MAX_STEPS_PER_MIN = 230         # elite sprint cadence is ~250; sustained >230 is false
# TUNE: recreational running power typically sits at 200-400 W and elite sprinters peak
# around 1,200-1,500 W, so anything above this comes from a corrupted speed reading.
MAX_PLAUSIBLE_WATTS = 700


def load(aid: str) -> dict:
    with open(DETAILS / f"{aid}.json") as fh:
        return json.load(fh)


def series(detail: dict) -> tuple[list[dict], float]:
    idx = {m["key"]: m["metricsIndex"] for m in detail["metricDescriptors"]}
    if "sumDistance" not in idx:
        return [], 1.0
    get = lambda m, k: m[idx[k]] if k in idx else None
    pts = []
    for row in detail["activityDetailMetrics"]:
        m = row["metrics"]
        if get(m, "sumDistance") is None:
            continue
        pts.append({"t": get(m, "directTimestamp") / 1000.0,
                    "d": get(m, "sumDistance"),
                    "hr": get(m, "directHeartRate"),
                    "pw": get(m, "directPower")})
    if len(pts) < 10:
        return pts, 1.0
    deltas = sorted(b["t"] - a["t"] for a, b in zip(pts, pts[1:]))
    return pts, deltas[len(deltas) // 2]


def audit_activity(aid: str, meta: dict | None) -> list[str]:
    pts, median = series(load(aid))
    if len(pts) < 10:
        return []
    issues = []

    # 1. distance jumps -- implausible implied speed between samples
    jumps = []
    for a, b in zip(pts, pts[1:]):
        dt_s, dd = b["t"] - a["t"], b["d"] - a["d"]
        if 0 < dt_s <= 30 and dd / dt_s > MAX_PLAUSIBLE_MS:
            jumps.append((a["t"] - pts[0]["t"], dd, dt_s, dd / dt_s))
    if jumps:
        total = sum(j[1] for j in jumps)
        early = [j for j in jumps if j[0] < 120]
        issues.append(
            f"DISTANCE JUMPS: {len(jumps)} implausible step(s), {total:.0f} m total"
            + (f" -- {len(early)} in the first 2 min (GPS acquisition)" if early else "")
            + "; worst " + f"{max(j[1] for j in jumps):.0f} m in "
            + f"{[j[2] for j in jumps if j[1] == max(k[1] for k in jumps)][0]:.0f} s"
            + f" at t={min(j[0] for j in jumps):.0f}s")

    # 2. impossible kilometre splits
    mark, bucket, bad = 1000.0, [pts[0]], []
    for p in pts[1:]:
        bucket.append(p)
        if p["d"] >= mark:
            dd = bucket[-1]["d"] - bucket[0]["d"]
            span = bucket[-1]["t"] - bucket[0]["t"]
            if dd > 0:
                pace = span / (dd / 1000)
                if pace < FAST_KM_SEC:
                    bad.append((int(mark / 1000), pace))
            mark += 1000.0
            bucket = [p]
    if bad:
        issues.append("IMPOSSIBLE SPLITS: " + ", ".join(
            f"km {k} at {int(p // 60)}:{int(p % 60):02d}/km" for k, p in bad))

    # 3. heart-rate artefacts
    hrs = [(p["t"], p["hr"]) for p in pts if p["hr"]]
    spikes = sum(1 for (t1, h1), (t2, h2) in zip(hrs, hrs[1:])
                 if t2 - t1 <= 4 and abs(h2 - h1) >= HR_JUMP_BPM)
    if spikes:
        issues.append(f"HR ARTEFACTS: {spikes} jump(s) of {HR_JUMP_BPM}+ bpm within 4 s")

    # A gap in the HR series is only a strap/sensor dropout if the DISTANCE
    # series kept recording through it. When the whole stream stops, that is
    # auto-pause -- a traffic light, not a fault. The first version of this
    # script reported every auto-pause as an HR dropout.
    stream_gaps = [(a["t"], b["t"]) for a, b in zip(pts, pts[1:])
                   if b["t"] - a["t"] > 30]
    def inside_pause(t1, t2):
        return any(t1 >= g0 - 2 and t2 <= g1 + 2 for g0, g1 in stream_gaps)
    real = [(a[0], b[0]) for a, b in zip(hrs, hrs[1:])
            if b[0] - a[0] > 30 and not inside_pause(a[0], b[0])]
    if real:
        issues.append(f"HR DROPOUTS: {len(real)} sensor gap(s) over 30 s with the watch still "
                      f"recording distance, longest {max(b - a for a, b in real):.0f} s")
    paused = len(stream_gaps)
    if paused:
        issues.append(f"(auto-pauses: {paused}, totalling "
                      f"{sum(b - a for a, b in stream_gaps):.0f} s -- normal, not a fault)")

    # 4. running power -- Garmin derives it partly from speed, so a GPS speed
    # spike produces a power spike. This is the SAME fault as the distance
    # jumps above, seen through a second metric, and it is the loudest signal:
    # a GPS jump of a few hundred metres can show up as several thousand watts.
    pw = [(p["t"] - pts[0]["t"], p["pw"]) for p in pts if p["pw"]]
    if pw:
        vals = [v for _, v in pw]
        early = [v for t, v in pw if t <= 60]
        rest = [v for t, v in pw if t > 120]
        if max(vals) > MAX_PLAUSIBLE_WATTS:
            issues.append(f"POWER SPIKE: peak {max(vals):.0f} W (plausibility ceiling {MAX_PLAUSIBLE_WATTS} W)")
        if early and rest:
            ratio = statistics.mean(early) / statistics.mean(rest)
            if ratio > 1.25:
                issues.append(f"EARLY POWER INFLATED: first 60 s averaged "
                              f"{statistics.mean(early):.0f} W vs {statistics.mean(rest):.0f} W "
                              f"for the rest (+{100 * (ratio - 1):.0f}%)")

    # 5. sampling rate -- flags the run-splits pause-threshold trap
    if median >= 3.5:
        issues.append(f"SAMPLE RATE {median:.0f}s (smart recording) -- "
                      "a fixed 3 s pause threshold misreads this activity")
    return issues


def audit_steps(days: int) -> list[str]:
    """Intraday step buckets, from the wellness cache if present."""
    out = []
    if not CACHE.exists():
        return out
    data = json.loads(CACHE.read_text(encoding="utf-8"))
    for w in sorted(data.get("wellness", {}).values(), key=lambda x: x["date"]):
        steps = w.get("steps")
        if steps and steps > 30000:
            out.append(f"{w['date']}: {steps:,} steps -- implausibly high daily total")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=35)
    ap.add_argument("--activity")
    a = ap.parse_args()

    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    by_id = {str(k): v for k, v in cache.get("activities", {}).items()}

    if a.activity:
        targets = [a.activity]
    else:
        cutoff = dt.date.today() - dt.timedelta(days=a.days)
        targets = []
        for f in glob.glob(str(DETAILS / "*.json")):
            aid = os.path.basename(f)[:-5]
            meta = by_id.get(aid)
            if meta:
                if dt.date.fromisoformat(meta["start_local"][:10]) >= cutoff:
                    targets.append(aid)
            elif dt.date.fromtimestamp(os.path.getmtime(f)) >= cutoff:
                targets.append(aid)

    rows = []
    for aid in targets:
        meta = by_id.get(aid)
        if meta and meta.get("type") != "running":
            continue
        try:
            issues = audit_activity(aid, meta)
        except Exception as exc:
            issues = [f"could not parse: {exc}"]
        if issues:
            if meta:
                label = (f"{meta['start_local'][:16]}  {meta['distance_km']:.2f} km  "
                         f"{meta['avg_pace_per_km']}")
                key = meta["start_local"]
            else:
                pts0, _ = series(load(aid))
                stamp = (dt.datetime.fromtimestamp(pts0[0]["t"]).strftime("%Y-%m-%d %H:%M")
                         if pts0 else "?")
                label = f"{stamp}  {(pts0[-1]['d'] / 1000 if pts0 else 0):.2f} km"
                key = stamp
            rows.append((key, label, aid, issues))

    rows.sort()
    print(f"Scanned {len(targets)} activity detail file(s) over the last {a.days} days.")
    print(f"{len(rows)} with anomalies.\n")
    for _, label, aid, issues in rows:
        print(f"{label}   [{aid}]")
        for i in issues:
            print(f"    - {i}")
        print()

    step_issues = audit_steps(a.days)
    if step_issues:
        print("DAILY STEP TOTALS:")
        for s in step_issues:
            print(f"    - {s}")
