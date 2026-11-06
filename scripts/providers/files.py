"""File-drop provider: FIT, GPX and TCX files.

For any device or app that can export activity files (Coros, Polar, Suunto,
Wahoo, bike computers, phone apps, a Garmin over USB), drop the files into
data/inbox/files/ and run `python scripts/sync.py --source files`.

Files are identified by content hash, so re-running is safe and renaming a file
does not duplicate it. FIT parsing needs `pip install fitparse`; GPX and TCX use
the standard library. Activity files only — no sleep / HRV.

.env:
  ACTIVITY_FILES_DIR=    # optional; defaults to data/inbox/files
"""
from __future__ import annotations

import datetime as dt
import hashlib
import math
import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from datastore import INBOX_DIR, ProviderNotConfigured, activity  # noqa: E402

NAME = "files"
CLOUD_SAFE = False


def _dir() -> Path:
    custom = os.getenv("ACTIVITY_FILES_DIR", "").strip()
    return Path(custom).expanduser() if custom else INBOX_DIR / "files"


def _local(ts: dt.datetime) -> dt.datetime:
    """Files store UTC; convert to this machine's local wall-clock time."""
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=dt.timezone.utc)
    return ts.astimezone().replace(tzinfo=None)


def _parse_time(s: str) -> dt.datetime | None:
    try:
        return dt.datetime.fromisoformat(s.strip().replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _haversine(a, b) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371.0088 * math.asin(math.sqrt(h))


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _gpx(path: Path, fid: str) -> dict | None:
    root = ET.parse(path).getroot()
    pts, hrs = [], []
    sport = None
    for el in root.iter():
        name = _local_name(el.tag)
        if name == "type" and sport is None and el.text:
            sport = el.text
        if name != "trkpt":
            continue
        lat, lon = float(el.get("lat")), float(el.get("lon"))
        t = ele = None
        for child in el.iter():
            cn = _local_name(child.tag)
            if cn == "time":
                t = _parse_time(child.text)
            elif cn == "ele":
                ele = float(child.text)
            elif cn == "hr":
                hrs.append(int(float(child.text)))
        pts.append((lat, lon, t, ele))
    if len(pts) < 2 or pts[0][2] is None:
        return None
    dist = sum(_haversine(pts[i - 1], pts[i]) for i in range(1, len(pts)))
    climb = sum(max(0.0, (pts[i][3] or 0) - (pts[i - 1][3] or 0))
                for i in range(1, len(pts)) if pts[i][3] is not None and pts[i - 1][3] is not None)
    # Moving time: ignore gaps where the device clearly paused (> 10 s with < 5 m moved)
    moving = 0.0
    for i in range(1, len(pts)):
        if pts[i][2] is None or pts[i - 1][2] is None:
            continue
        gap = (pts[i][2] - pts[i - 1][2]).total_seconds()
        if gap <= 10 or _haversine(pts[i - 1], pts[i]) * 1000 > 5:
            moving += gap
    return activity(
        id=fid, name=path.stem, subtype=sport or "running",
        start_local=_local(pts[0][2]).isoformat(timespec="seconds"),
        duration_min=moving / 60, distance_km=dist,
        avg_hr=round(sum(hrs) / len(hrs)) if hrs else None, max_hr=max(hrs) if hrs else None,
        elevation_gain_m=round(climb, 1) if climb else None,
    )


def _tcx(path: Path, fid: str) -> dict | None:
    root = ET.parse(path).getroot()
    act = next((e for e in root.iter() if _local_name(e.tag) == "Activity"), None)
    if act is None:
        return None
    secs = dist = kcal = 0.0
    hr_sum_w, hr_max, start = 0.0, None, None
    for lap in (e for e in act.iter() if _local_name(e.tag) == "Lap"):
        start = start or _parse_time(lap.get("StartTime", ""))
        vals = {_local_name(c.tag): c for c in lap}
        lap_s = float(vals["TotalTimeSeconds"].text) if "TotalTimeSeconds" in vals else 0
        secs += lap_s
        dist += float(vals["DistanceMeters"].text) if "DistanceMeters" in vals else 0
        kcal += float(vals["Calories"].text) if "Calories" in vals else 0
        for key in ("AverageHeartRateBpm", "MaximumHeartRateBpm"):
            if key in vals:
                v = next((float(c.text) for c in vals[key] if _local_name(c.tag) == "Value"), None)
                if v and key.startswith("Average"):
                    hr_sum_w += v * lap_s
                elif v:
                    hr_max = max(hr_max or 0, v)
    if start is None:
        return None
    return activity(
        id=fid, name=path.stem, subtype=act.get("Sport", "other"),
        start_local=_local(start).isoformat(timespec="seconds"),
        duration_min=secs / 60, distance_km=dist / 1000,
        avg_hr=round(hr_sum_w / secs) if hr_sum_w and secs else None,
        max_hr=round(hr_max) if hr_max else None, calories=round(kcal) if kcal else None,
    )


def _fit(path: Path, fid: str) -> dict | None:
    try:
        from fitparse import FitFile
    except ImportError:
        print(f"  ! skipped {path.name}: pip install fitparse to read FIT files", file=sys.stderr)
        return None
    s = next(iter(FitFile(str(path)).get_messages("session")), None)
    if s is None:
        return None
    v = {f.name: f.value for f in s}
    start = v.get("start_time")
    if start is None:
        return None
    return activity(
        id=fid, name=path.stem, subtype=str(v.get("sport") or "other"),
        start_local=_local(start).isoformat(timespec="seconds"),
        duration_min=(v.get("total_timer_time") or 0) / 60,
        distance_km=(v.get("total_distance") or 0) / 1000,
        avg_hr=v.get("avg_heart_rate"), max_hr=v.get("max_heart_rate"),
        calories=v.get("total_calories"), elevation_gain_m=v.get("total_ascent"),
    )


PARSERS = {".gpx": _gpx, ".tcx": _tcx, ".fit": _fit}


def fetch(start: dt.date, end: dt.date, opts) -> tuple[list[dict], list[dict]]:
    folder = Path(opts.file).expanduser() if getattr(opts, "file", None) else _dir()
    files = [folder] if folder.is_file() else (
        sorted(p for p in folder.rglob("*") if p.suffix.lower() in PARSERS) if folder.exists() else [])
    if not files:
        raise ProviderNotConfigured(f"no .fit / .gpx / .tcx files in {folder}")
    acts = []
    for p in files:
        fid = hashlib.sha1(p.read_bytes()).hexdigest()[:16]
        try:
            a = PARSERS[p.suffix.lower()](p, fid)
        except Exception as e:  # a corrupt file shouldn't sink the batch
            print(f"  ! skipped {p.name}: {e}", file=sys.stderr)
            continue
        if a and start.isoformat() <= a["start_local"][:10] <= end.isoformat():
            acts.append(a)
    return acts, []
