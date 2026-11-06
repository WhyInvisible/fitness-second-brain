"""Apple Health / Apple Watch provider.

Apple has no cloud API for Health data, so this provider reads files that the
iPhone exports. Two routes — use either or both:

1. One-off / occasional: Health app -> profile picture -> "Export All Health
   Data" -> AirDrop/save `export.zip` into data/inbox/apple-health/.
   Good for a historical backfill: `python scripts/sync.py --source apple_health --start 2024-01-01`

2. Automatic (recommended for daily use): the third-party iOS app
   "Health Auto Export" can write JSON on a schedule to an iCloud Drive /
   Dropbox folder. Point APPLE_HEALTH_DIR at that synced folder (or copy files
   into data/inbox/apple-health/). Each sync reads every *.json there.

.env:
  APPLE_HEALTH_DIR=      # optional; defaults to data/inbox/apple-health

Notes:
  * Apple reports HRV as SDNN, Garmin as RMSSD. They are different statistics
    and must not be compared with each other — hrv_method records which one.
  * iPhone and Watch both record steps and sleep; to avoid double counting,
    each day takes the single source with the largest total.
  * The JSON mapping is defensive because the export app's format has changed
    across versions. If a metric comes through empty, inspect one file and
    extend the key lists below.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import zipfile
from collections import defaultdict
from pathlib import Path
from xml.etree.ElementTree import iterparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from datastore import INBOX_DIR, ProviderNotConfigured, activity, wellness  # noqa: E402

NAME = "apple_health"
CLOUD_SAFE = False  # needs files from the phone; the cloud bot skips it

HK = "HKQuantityTypeIdentifier"
ASLEEP = {"HKCategoryValueSleepAnalysisAsleep", "HKCategoryValueSleepAnalysisAsleepUnspecified",
          "HKCategoryValueSleepAnalysisAsleepCore", "HKCategoryValueSleepAnalysisAsleepDeep",
          "HKCategoryValueSleepAnalysisAsleepREM"}


def _dir() -> Path:
    custom = os.getenv("APPLE_HEALTH_DIR", "").strip()
    return Path(custom).expanduser() if custom else INBOX_DIR / "apple-health"


def _ts(s: str | None) -> dt.datetime | None:
    """Apple timestamps carry the device's local offset; keep the wall-clock time."""
    if not s:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S %z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(s.strip(), fmt).replace(tzinfo=None)
        except ValueError:
            continue
    try:
        return dt.datetime.fromisoformat(s.strip()).replace(tzinfo=None)
    except ValueError:
        return None


def _km(value: float | None, unit: str | None) -> float | None:
    if value is None:
        return None
    u = (unit or "km").lower()
    if u in ("mi", "mile", "miles"):
        return value * 1.609344
    if u == "m":
        return value / 1000
    return value


def _kcal(value: float | None, unit: str | None) -> float | None:
    if value is None:
        return None
    return value / 4.184 if (unit or "").lower() == "kj" else value


def _kg(value: float | None, unit: str | None) -> float | None:
    if value is None:
        return None
    return value * 0.45359237 if (unit or "").lower() in ("lb", "lbs") else value


class _Days:
    """Accumulates per-day wellness from either input format."""

    def __init__(self):
        self.rhr: dict[str, float] = {}
        self.hrv: dict[str, list[float]] = defaultdict(list)
        self.vo2: dict[str, float] = {}
        self.weight: dict[str, float] = {}
        self.steps: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        # sleep[date][source] = {"total":..., "deep":..., "rem":...}
        self.sleep: dict[str, dict[str, dict[str, float]]] = defaultdict(
            lambda: defaultdict(lambda: defaultdict(float)))

    def records(self, start: dt.date, end: dt.date) -> list[dict]:
        dates = set(self.rhr) | set(self.hrv) | set(self.vo2) | set(self.weight) | set(self.steps) | set(self.sleep)
        out = []
        for d in sorted(dates):
            if not (start.isoformat() <= d <= end.isoformat()):
                continue
            sl = max(self.sleep[d].values(), key=lambda s: s["total"], default=None) if d in self.sleep else None
            steps = max(self.steps[d].values(), default=None) if d in self.steps else None
            out.append(wellness(
                date=d,
                resting_hr=self.rhr.get(d),
                hrv_last_night_ms=round(sum(self.hrv[d]) / len(self.hrv[d]), 1) if self.hrv.get(d) else None,
                hrv_method="sdnn" if self.hrv.get(d) else None,
                vo2max_running=self.vo2.get(d),
                weight_kg=round(self.weight[d], 1) if d in self.weight else None,
                steps=int(steps) if steps else None,
                sleep_total_min=round(sl["total"], 1) if sl and sl["total"] else None,
                sleep_deep_min=round(sl["deep"], 1) if sl and sl["deep"] else None,
                sleep_rem_min=round(sl["rem"], 1) if sl and sl["rem"] else None,
            ))
        return out


# ---------- export.zip / export.xml ----------

def _parse_export(stream, start: dt.date, end: dt.date, days: _Days) -> list[dict]:
    acts = []
    lo, hi = start.isoformat(), (end + dt.timedelta(days=1)).isoformat()
    context = iterparse(stream, events=("start", "end"))
    _, root = next(context)
    for event, el in context:
        if event != "end":
            continue
        tag = el.tag
        if tag == "Record":
            a = el.attrib
            st = _ts(a.get("startDate"))
            en = _ts(a.get("endDate")) or st
            if st is None or not (lo <= en.date().isoformat() <= hi):
                root.clear()
                continue
            t, unit, src = a.get("type", ""), a.get("unit"), a.get("sourceName", "?")
            date = en.date().isoformat()
            try:
                val = float(a.get("value")) if a.get("value") not in (None, "") else None
            except ValueError:
                val = None
            if t == HK + "RestingHeartRate" and val is not None:
                days.rhr[st.date().isoformat()] = val
            elif t == HK + "HeartRateVariabilitySDNN" and val is not None:
                days.hrv[date].append(val)
            elif t == HK + "VO2Max" and val is not None:
                days.vo2[date] = round(val, 1)
            elif t == HK + "BodyMass" and val is not None:
                days.weight[date] = _kg(val, unit)
            elif t == HK + "StepCount" and val is not None:
                days.steps[st.date().isoformat()][src] += val
            elif t == "HKCategoryTypeIdentifierSleepAnalysis":
                v = a.get("value", "")
                if v in ASLEEP:
                    mins = (en - st).total_seconds() / 60
                    bucket = days.sleep[date][src]  # sleep belongs to the morning it ends
                    bucket["total"] += mins
                    if v.endswith("Deep"):
                        bucket["deep"] += mins
                    elif v.endswith("REM"):
                        bucket["rem"] += mins
            root.clear()
        elif tag == "Workout":
            w = _workout_from_xml(el)
            if w and lo <= w["start_local"][:10] < hi:
                acts.append(w)
            root.clear()
    return acts


def _workout_from_xml(el) -> dict | None:
    a = el.attrib
    st, en = _ts(a.get("startDate")), _ts(a.get("endDate"))
    if st is None:
        return None
    dur = float(a.get("duration") or 0)
    if (a.get("durationUnit") or "min") == "s":
        dur /= 60
    if not dur and en:
        dur = (en - st).total_seconds() / 60
    dist = _km(float(a["totalDistance"]), a.get("totalDistanceUnit")) if a.get("totalDistance") else None
    kcal = _kcal(float(a["totalEnergyBurned"]), a.get("totalEnergyBurnedUnit")) if a.get("totalEnergyBurned") else None
    avg_hr = max_hr = elev = None
    for child in el:
        c = child.attrib
        ctype = c.get("type", "")
        if child.tag == "WorkoutStatistics":
            if ctype == HK + "HeartRate":
                avg_hr = float(c["average"]) if c.get("average") else avg_hr
                max_hr = float(c["maximum"]) if c.get("maximum") else max_hr
            elif ctype.startswith(HK + "Distance") and dist is None and c.get("sum"):
                dist = _km(float(c["sum"]), c.get("unit"))
            elif ctype == HK + "ActiveEnergyBurned" and kcal is None and c.get("sum"):
                kcal = _kcal(float(c["sum"]), c.get("unit"))
        elif child.tag == "MetadataEntry" and c.get("key") == "HKElevationAscended":
            val, _, unit = (c.get("value") or "").partition(" ")
            try:
                elev = float(val) / (100 if unit == "cm" else 1)
            except ValueError:
                pass
    raw_type = (a.get("workoutActivityType") or "").replace("HKWorkoutActivityType", "")
    return activity(
        id=f"{st.isoformat()}-{raw_type}",
        name=raw_type or "Workout",
        subtype=raw_type,
        start_local=st.isoformat(),
        duration_min=dur,
        distance_km=dist,
        avg_hr=round(avg_hr) if avg_hr else None,
        max_hr=round(max_hr) if max_hr else None,
        calories=round(kcal) if kcal else None,
        elevation_gain_m=round(elev, 1) if elev else None,
    )


# ---------- Health Auto Export JSON ----------

def _qty(obj, *keys):
    """First numeric value found under any of the given keys ({"qty": n} or n)."""
    for k in keys:
        v = obj.get(k) if isinstance(obj, dict) else None
        if isinstance(v, dict):
            v = v.get("qty", v.get("avg"))
            if isinstance(v, dict):
                v = v.get("qty")
        if isinstance(v, (int, float)):
            return float(v), (obj.get(k) or {}).get("units") if isinstance(obj.get(k), dict) else None
    return None, None


def _parse_auto_export(doc: dict, start: dt.date, end: dt.date, days: _Days) -> list[dict]:
    data = doc.get("data", doc)
    lo, hi = start.isoformat(), end.isoformat()
    for metric in data.get("metrics", []):
        name, units = metric.get("name", ""), metric.get("units")
        for row in metric.get("data", []):
            ts = _ts(row.get("date"))
            if ts is None:
                continue
            date = ts.date().isoformat()
            qty = row.get("qty", row.get("Avg"))
            src = row.get("source", "auto-export")
            if name == "sleep_analysis":
                end_ts = _ts(row.get("sleepEnd") or row.get("inBedEnd")) or ts
                d = end_ts.date().isoformat()
                if not (lo <= d <= hi):
                    continue
                factor = 1 if (units or "hr").lower().startswith("min") else 60
                total = row.get("totalSleep") or row.get("asleep") or sum(
                    row.get(k) or 0 for k in ("core", "deep", "rem"))
                bucket = days.sleep[d][src]
                bucket["total"] = max(bucket["total"], (total or 0) * factor)
                bucket["deep"] = max(bucket["deep"], (row.get("deep") or 0) * factor)
                bucket["rem"] = max(bucket["rem"], (row.get("rem") or 0) * factor)
                continue
            if not (lo <= date <= hi) or not isinstance(qty, (int, float)):
                continue
            if name == "resting_heart_rate":
                days.rhr[date] = qty
            elif name == "heart_rate_variability":
                days.hrv[date].append(qty)
            elif name == "vo2_max":
                days.vo2[date] = round(qty, 1)
            elif name in ("weight_body_mass", "body_mass"):
                days.weight[date] = _kg(qty, units)
            elif name == "step_count":
                days.steps[date][src] += qty

    acts = []
    for w in data.get("workouts", []):
        st = _ts(w.get("start"))
        if st is None or not (lo <= st.date().isoformat() <= hi):
            continue
        en = _ts(w.get("end"))
        dur = w.get("duration")
        dur = dur / 60 if isinstance(dur, (int, float)) else ((en - st).total_seconds() / 60 if en else None)
        dist, dist_u = _qty(w, "distance", "totalDistance")
        kcal, kcal_u = _qty(w, "activeEnergyBurned", "activeEnergy", "totalEnergy")
        avg_hr, _ = _qty(w, "avgHeartRate", "heartRateAvg")
        max_hr, _ = _qty(w, "maxHeartRate", "heartRateMax")
        hr = w.get("heartRate")
        if isinstance(hr, dict):
            avg_hr = avg_hr or (hr.get("avg") or {}).get("qty")
            max_hr = max_hr or (hr.get("max") or {}).get("qty")
        elev, elev_u = _qty(w, "elevationUp", "elevation")
        if elev is not None and (elev_u or "m").lower() in ("ft", "feet"):
            elev *= 0.3048
        acts.append(activity(
            id=w.get("id") or f"{st.isoformat()}-{w.get('name', 'workout')}",
            name=w.get("name") or "Workout",
            subtype=w.get("name"),
            start_local=st.isoformat(),
            duration_min=dur,
            distance_km=_km(dist, dist_u),
            avg_hr=round(avg_hr) if avg_hr else None,
            max_hr=round(max_hr) if max_hr else None,
            calories=round(_kcal(kcal, kcal_u)) if kcal else None,
            elevation_gain_m=round(elev, 1) if elev else None,
        ))
    return acts


# ---------- entry point ----------

def fetch(start: dt.date, end: dt.date, opts) -> tuple[list[dict], list[dict]]:
    folder = Path(opts.file).expanduser() if getattr(opts, "file", None) else _dir()
    files = [folder] if folder.is_file() else (
        sorted(folder.glob("*.zip")) + sorted(folder.glob("*.xml")) + sorted(folder.glob("*.json"))
        if folder.exists() else [])
    if not files:
        raise ProviderNotConfigured(
            f"no export.zip / export.xml / *.json found in {folder} — "
            "export from the Health app or set APPLE_HEALTH_DIR")

    days, acts = _Days(), []
    for f in files:
        print(f"  reading {f.name}")
        if f.suffix == ".zip":
            with zipfile.ZipFile(f) as z:
                inner = next((n for n in z.namelist() if n.endswith("export.xml")), None)
                if inner:
                    with z.open(inner) as stream:
                        acts += _parse_export(stream, start, end, days)
        elif f.suffix == ".xml":
            with f.open("rb") as stream:
                acts += _parse_export(stream, start, end, days)
        elif f.suffix == ".json":
            try:
                acts += _parse_auto_export(json.loads(f.read_text(encoding="utf-8")), start, end, days)
            except (json.JSONDecodeError, AttributeError) as e:
                print(f"  ! skipped {f.name}: {e}", file=sys.stderr)
    return acts, days.records(start, end)
