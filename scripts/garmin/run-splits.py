#!/usr/bin/env python3
"""Per-kilometre split analysis on MOVING time, with auto-pauses removed.

WHY THIS EXISTS
---------------
Garmin's activity detail stream is sampled on a wall-clock timestamp. When
auto-pause triggers (traffic lights, water stops), no samples are written, so
the stream contains a GAP. Naively differencing timestamps therefore charges
the pause to whichever kilometre it fell in, inflating that split.

A 40-second stop at a crossing can turn a 6:00/km kilometre into a "6:40/km"
split -- and a wrong conclusion about pacing discipline. Always use this script,
not raw timestamps. Needs: python scripts/sync.py --source garmin --with-details

Garmin's own figures for reference:
  elapsedDuration = wall clock, includes pauses
  duration        = timer, pauses removed   <-- what the app shows as avg pace
  movingDuration  = duration minus slow-but-unpaused crawling

Usage:
  python scripts/garmin/run-splits.py <activityId> [--gap SECONDS]
  python scripts/garmin/run-splits.py --latest [--halves]
"""
import json, sys, glob, os, statistics, argparse

DETAILS = os.path.join(os.path.dirname(__file__), "..", "..", "data", "raw", "garmin", "details")


def load(aid):
    with open(os.path.join(DETAILS, f"{aid}.json")) as fh:
        return json.load(fh)


def splits(detail, gap_thresh=None):
    idx = {m["key"]: m["metricsIndex"] for m in detail["metricDescriptors"]}
    need = ("directTimestamp", "sumDistance")
    if not all(k in idx for k in need):
        raise SystemExit("not a distance activity -- no sumDistance stream")

    def get(m, key):
        return m[idx[key]] if key in idx else None

    pts = []
    for row in detail["activityDetailMetrics"]:
        m = row["metrics"]
        if get(m, "sumDistance") is None:
            continue
        pts.append({
            "t": get(m, "directTimestamp") / 1000.0,
            "d": get(m, "sumDistance"),
            "hr": get(m, "directHeartRate"),
            "cad": get(m, "directRunCadence"),
            "gct": get(m, "directGroundContactTime"),
            "sl": get(m, "directStrideLength"),
            "pc": get(m, "directPerformanceCondition"),
        })

    # Garmin's sample rate is NOT constant: short runs record every 1-2 s, but
    # longer ones drop to 4 s (smart recording). A fixed 3 s pause threshold
    # therefore classified every ordinary sample of the 22 km on 2026-10-10 as a
    # pause and reported 7,730 s of "pausing" on a 128-minute run. Derive the
    # threshold from the activity's own median sample interval instead.
    deltas = sorted(b["t"] - a["t"] for a, b in zip(pts, pts[1:]))
    median = deltas[len(deltas) // 2] if deltas else 1.0
    if gap_thresh is None:
        gap_thresh = max(3.0, 2.5 * median)

    # Moving-time axis: any inter-sample gap longer than gap_thresh is a pause
    # and contributes zero elapsed time.
    moving, prev, paused = 0.0, None, 0.0
    for p in pts:
        if prev is not None:
            g = p["t"] - prev
            if g > gap_thresh:
                paused += g
            else:
                moving += g
        p["mt"] = moving
        prev = p["t"]
    return pts, paused, median, gap_thresh


def fmt(sec):
    return f"{int(sec // 60)}:{int(sec % 60):02d}"


def mean(vals):
    vals = [v for v in vals if v is not None]
    return statistics.mean(vals) if vals else None


def report(pts, paused, median, thresh, every=1000.0):
    print(f"moving {fmt(pts[-1]['mt'])}  ·  elapsed {fmt(pts[-1]['t'] - pts[0]['t'])}  "
          f"·  paused {paused:.0f}s  ·  {pts[-1]['d'] / 1000:.2f} km")
    print(f"sampling: {median:.0f}s median  ·  pause threshold {thresh:.0f}s")
    print(f"\n{'km':>3} {'MOVING':>7} {'elapsed':>8} {'paused':>7} {'HR':>6} "
          f"{'cad':>6} {'GCT':>5} {'SL':>4} {'PC':>4} {'cost':>6}")
    mark, bucket = every, [pts[0]]
    for p in pts[1:]:
        bucket.append(p)
        if p["d"] >= mark or p is pts[-1]:
            dd = bucket[-1]["d"] - bucket[0]["d"]
            if dd > 0:
                dm = bucket[-1]["mt"] - bucket[0]["mt"]
                de = bucket[-1]["t"] - bucket[0]["t"]
                pm, pe = dm / (dd / 1000), de / (dd / 1000)
                hr, pc = mean(x["hr"] for x in bucket), mean(x["pc"] for x in bucket)
                cad, gct, sl = (mean(x["cad"] for x in bucket),
                                mean(x["gct"] for x in bucket),
                                mean(x["sl"] for x in bucket))
                partial = "" if dd > every * 0.6 else "  (partial)"
                print(f"{int(mark / every):>3} {fmt(pm):>7} {fmt(pe):>8} {de - dm:>6.0f}s "
                      f"{hr:>6.1f} {cad * 2:>6.1f} {gct:>5.0f} {sl:>4.0f} "
                      f"{round(pc) if pc is not None else '-':>4} {hr * pm / 60:>6.0f}{partial}")
            mark += every
            bucket = [p]


def segment(pts, lo, hi, label):
    s = [p for p in pts if lo <= p["d"] <= hi]
    if len(s) < 2:
        return
    dd = s[-1]["d"] - s[0]["d"]
    pm = (s[-1]["mt"] - s[0]["mt"]) / (dd / 1000)
    hr = mean(x["hr"] for x in s)
    print(f"  {label:<14} {fmt(pm)}/km  HR {hr:.1f}  cost {hr * pm / 60:.0f}  "
          f"GCT {mean(x['gct'] for x in s):.0f}  SL {mean(x['sl'] for x in s):.0f}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("activity", nargs="?")
    ap.add_argument("--latest", action="store_true")
    ap.add_argument("--gap", type=float, default=None,
                    help="inter-sample gap (s) treated as a pause "
                         "(default: 2.5x the activity's median sample interval, min 3)")
    ap.add_argument("--halves", action="store_true", help="also print half-by-half")
    a = ap.parse_args()

    if a.latest or not a.activity:
        files = sorted(glob.glob(os.path.join(DETAILS, "*.json")), key=os.path.getmtime)
        aid = None
        for f in reversed(files):
            try:
                d = json.load(open(f))
                if any(m["key"] == "sumDistance" for m in d["metricDescriptors"]):
                    aid = os.path.basename(f)[:-5]
                    break
            except Exception:
                continue
        if aid is None:
            raise SystemExit("no distance activity found in details/")
    else:
        aid = a.activity

    print(f"activity {aid}")
    pts, paused, median, thresh = splits(load(aid), a.gap)
    report(pts, paused, median, thresh)
    if a.halves:
        total = pts[-1]["d"]
        print()
        segment(pts, 0, total / 2, "first half")
        segment(pts, total / 2, total, "second half")
